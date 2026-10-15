// TubeVault – Musikspieler
//
// Die eine Stelle für die Musikwiedergabe: Warteschlange, Zufall,
// Wiederholen, Lautstärke und das Audio-Element. Läuft über alle Seiten
// weiter; Musikseite, Abspielleiste und Sperrbildschirm (Media Session)
// lesen und steuern nur hier.
//
// Das Audio-Element hängt unsichtbar im Dokument: so erkennt auch die
// Versionswache laufende Wiedergabe und lädt nicht mitten im Titel neu.
// Startet ein Video, hält die Musik an - und umgekehrt.
import { api } from '../api/client.js';
import { audioSrc, coverUrl, isFile, recordPlay, setFavorite } from '../utils/musicTrack.js';
import { loadSkipRanges, skipTarget } from '../utils/adSkip.js';
import { emitVideoMutation } from '../utils/videoMutations.js';

const STATE_KEY = 'musik.zustand';          // Weiterhören: Warteschlange dieses Geräts
const VOLUME_KEY = 'player.lastVolume';     // wie beim Videoplayer
const COUNT_AFTER_S = 30;                    // ab dann zählt ein Titel als gehört
const RESTART_AFTER_S = 3;                   // "Zurück" springt danach erst an den Titelanfang
const REPEAT_MODES = ['off', 'all', 'one'];
const UNDO_MS = 6000;                        // so lange lässt sich ein Löschen zurücknehmen
// Stille, um die Wiedergabe in einer Nutzeraktion freizuschalten (iOS)
const SILENCE = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=';

function readJson(key) {
  try { return JSON.parse(localStorage.getItem(key) || 'null'); } catch { return null; }
}
function writeJson(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* Speicher gesperrt */ }
}

class MusicPlayer {
  queue = $state([]);            // Titel (wie /api/music/play sie liefert)
  index = $state(-1);
  title = $state('');            // Name der Quelle, z.B. "ABBA" oder "Alles zufällig"
  source = $state(null);
  playing = $state(false);
  loading = $state(false);
  time = $state(0);
  duration = $state(0);
  volume = $state(0.8);
  muted = $state(false);
  shuffle = $state(false);
  repeat = $state('off');
  pendingDelete = $state(null);  // { track } - wird nach UNDO_MS endgültig gelöscht
  audioInfo = $state(null);      // Format und Bitrate des laufenden Titels

  #audio = null;
  #counted = null;               // Kennung, deren Wiedergabe schon gezählt ist
  #skipRanges = [];
  #saveTimer = null;
  #unlocked = false;
  #deleteTimer = null;

  get current() { return this.queue[this.index] || null; }
  get active() { return this.queue.length > 0; }
  get upcoming() { return this.queue.slice(this.index + 1); }

  constructor() {
    if (typeof window === 'undefined') return;
    const saved = readJson(STATE_KEY);
    if (saved?.queue?.length) {
      Object.assign(this, { queue: saved.queue, index: saved.index ?? 0, title: saved.title || '',
                            source: saved.source || null, shuffle: !!saved.shuffle, repeat: saved.repeat || 'off',
                            time: saved.time || 0 });
    }
    const volume = parseFloat(localStorage.getItem(VOLUME_KEY));
    if (volume >= 0 && volume <= 1) this.volume = volume;
    // Wird die Seite geschlossen, gilt ein angestoßenes Löschen sofort
    window.addEventListener('pagehide', () => this.#commitDelete());
  }

  // ─── Audio-Element ───
  #element() {
    if (this.#audio) return this.#audio;
    const audio = document.createElement('audio');
    audio.preload = 'auto';
    audio.style.display = 'none';
    audio.dataset.musik = '1';
    audio.volume = this.volume;
    document.body.appendChild(audio);
    audio.addEventListener('play', () => { this.playing = true; this.#pauseVideos(); });
    audio.addEventListener('pause', () => { this.playing = false; this.#save(); });
    audio.addEventListener('waiting', () => { this.loading = true; });
    audio.addEventListener('playing', () => { this.loading = false; });
    audio.addEventListener('loadedmetadata', () => { this.duration = audio.duration || this.current?.duration || 0; });
    audio.addEventListener('timeupdate', () => this.#onTime());
    audio.addEventListener('ended', () => this.#onEnded());
    audio.addEventListener('error', () => { if (audio.src !== SILENCE && this.active) this.next(); });
    // Startet irgendwo ein Video, hat es Vorrang
    document.addEventListener('play', (e) => {
      if (e.target !== audio && e.target?.tagName === 'VIDEO') audio.pause();
    }, true);
    this.#audio = audio;
    this.#mediaSession();
    return audio;
  }

  #pauseVideos() {
    for (const video of document.querySelectorAll('video')) if (!video.paused) video.pause();
  }

  /** In einer Nutzeraktion aufrufen, bevor etwas Asynchrones passiert: iOS
   *  erlaubt Wiedergabe nur, wenn das Element einmal in einer Nutzeraktion lief */
  #unlock() {
    const audio = this.#element();
    if (this.#unlocked) return;
    this.#unlocked = true;
    if (!audio.getAttribute('src')) audio.src = SILENCE;
    const muted = audio.muted;
    audio.muted = true;
    audio.play().then(() => { audio.pause(); audio.muted = muted; }).catch(() => { audio.muted = muted; });
  }

  // ─── Laden und Abspielen ───
  /** Dynamische Liste abspielen: all, artist:<name>, channel:<id>, favorites, similar:<id> ... */
  async playSource(source, { shuffle = false, start = null } = {}) {
    this.#unlock();
    const list = await api.musicPlay(source, { shuffle, start });
    if (!list.tracks.length) return false;
    this.shuffle = shuffle;
    this.#setQueue(list.tracks, 0, { title: list.title, source });
    return true;
  }

  /** Eine gegebene Titelliste ab startIndex abspielen (z.B. eine sichtbare Liste) */
  playTracks(tracks, startIndex = 0, title = 'Auswahl') {
    if (!tracks.length) return;
    this.#unlock();
    this.shuffle = false;
    this.#setQueue(tracks, startIndex, { title, source: null });
  }

  #setQueue(tracks, startIndex, { title, source }) {
    this.queue = tracks;
    this.title = title;
    this.source = source;
    this.#start(startIndex, 0);
  }

  async #start(index, at = 0) {
    if (index < 0 || index >= this.queue.length) return;
    const audio = this.#element();
    this.index = index;
    const track = this.current;
    this.time = at;
    this.duration = track.duration || 0;
    this.#counted = null;
    audio.src = audioSrc(track);
    audio.currentTime = at;
    this.#updateMetadata();
    this.#save();
    audio.play().catch(() => { this.playing = false; });
    this.audioInfo = null;
    api.musicAudioInfo(track.id).then((info) => { if (this.current?.id === track.id) this.audioInfo = info; }).catch(() => {});
    this.#skipRanges = [];
    // Werbestellen gibt es nur in Videos
    if (!isFile(track)) loadSkipRanges(track.id).then((ranges) => { if (this.current?.id === track.id) this.#skipRanges = ranges; });
  }

  /** Weiterhören: gespeicherte Warteschlange an der gemerkten Stelle fortsetzen */
  resume() {
    if (!this.current) return;
    this.#unlock();
    const audio = this.#element();
    if (audio.src && !audio.src.startsWith('data:') && audio.src.includes(encodeURIComponent(this.current.id))) {
      audio.play().catch(() => {});
    } else {
      this.#start(this.index, this.time || 0);
    }
  }

  toggle() {
    if (!this.current) return;
    const audio = this.#element();
    if (!audio.src || audio.src.startsWith('data:')) return this.resume();
    if (audio.paused) audio.play().catch(() => {}); else audio.pause();
  }

  pause() { this.#audio?.pause(); }

  next() {
    if (this.index + 1 < this.queue.length) return this.#start(this.index + 1);
    if (this.repeat === 'all' && this.queue.length) return this.#start(0);
    this.pause();
  }

  prev() {
    if (this.time > RESTART_AFTER_S || this.index === 0) return this.seek(0);
    this.#start(this.index - 1);
  }

  jump(index) { this.#start(index); }

  seek(seconds) {
    const audio = this.#element();
    audio.currentTime = Math.max(0, Math.min(seconds, this.duration || seconds));
    this.time = audio.currentTime;
  }

  setVolume(value) {
    this.volume = Math.max(0, Math.min(1, value));
    if (this.#audio) this.#audio.volume = this.volume;
    try { localStorage.setItem(VOLUME_KEY, String(this.volume)); } catch { /* Speicher gesperrt */ }
  }

  toggleMute() {
    this.muted = !this.muted;
    if (this.#audio) this.#audio.muted = this.muted;
  }

  /** Zufall: der Rest der Warteschlange wird gemischt (der laufende Titel bleibt) */
  toggleShuffle() {
    this.shuffle = !this.shuffle;
    if (this.shuffle && this.upcoming.length > 1) {
      const rest = [...this.upcoming];
      for (let i = rest.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [rest[i], rest[j]] = [rest[j], rest[i]];
      }
      this.queue = [...this.queue.slice(0, this.index + 1), ...rest];
    }
    this.#save();
  }

  cycleRepeat() {
    this.repeat = REPEAT_MODES[(REPEAT_MODES.indexOf(this.repeat) + 1) % REPEAT_MODES.length];
    this.#save();
  }

  // ─── Warteschlange bearbeiten ───
  playNext(track) {
    if (!this.active) return this.playTracks([track], 0, track.title);
    this.queue = [...this.queue.slice(0, this.index + 1), track, ...this.queue.slice(this.index + 1)];
    this.#save();
  }

  enqueue(track) {
    if (!this.active) return this.playTracks([track], 0, track.title);
    this.queue = [...this.queue, track];
    this.#save();
  }

  remove(position) {
    if (position === this.index) return;
    this.queue = this.queue.filter((_, i) => i !== position);
    if (position < this.index) this.index -= 1;
    this.#save();
  }

  move(from, to) {
    if (from === to) return;
    const items = [...this.queue];
    const [item] = items.splice(from, 1);
    items.splice(to, 0, item);
    let index = this.index;
    if (from === index) index = to;
    else if (from < index && to >= index) index -= 1;
    else if (from > index && to <= index) index += 1;
    this.queue = items;
    this.index = index;
    this.#save();
  }

  stop() {
    this.pause();
    this.queue = [];
    this.index = -1;
    this.title = '';
    this.source = null;
    if (this.#audio) this.#audio.removeAttribute('src');
    this.#save();
    if ('mediaSession' in navigator) navigator.mediaSession.metadata = null;
  }

  // ─── Bei Nichtgefallen: ein Klick ───
  /** Aus der Warteschlange nehmen; ist es der laufende Titel, geht es weiter */
  #drop(track) {
    const position = this.queue.findIndex(t => t.id === track.id);
    if (position < 0) return;
    const wasCurrent = position === this.index;
    this.queue = this.queue.filter((_, i) => i !== position);
    if (position < this.index) this.index -= 1;
    if (wasCurrent) {
      if (this.index < this.queue.length) this.#start(this.index);
      else { this.index = this.queue.length - 1; this.pause(); }
    }
    this.#save();
  }

  /** Läuft gerade eine Wiedergabeliste? Dann deren Nummer */
  get playlistId() {
    return this.source?.startsWith('playlist:') ? this.source.slice(9) : null;
  }

  /** Aus der Wiedergabeliste werfen (oder nur aus der Warteschlange) */
  async removeFromList(track = this.current) {
    if (!track) return;
    if (this.playlistId) await api.removeFromPlaylist(this.playlistId, track.id);
    this.#drop(track);
  }

  /** Löschen: sofort weiter, endgültig erst nach UNDO_MS (Rückgängig möglich) */
  deleteTrack(track = this.current) {
    if (!track) return;
    this.#commitDelete();
    this.#drop(track);
    this.pendingDelete = { track, at: this.index };
    this.#deleteTimer = setTimeout(() => this.#commitDelete(), UNDO_MS);
  }

  undoDelete() {
    if (!this.pendingDelete) return;
    clearTimeout(this.#deleteTimer);
    const { track } = this.pendingDelete;
    this.pendingDelete = null;
    this.queue = [...this.queue.slice(0, this.index + 1), track, ...this.queue.slice(this.index + 1)];
    this.#save();
  }

  #commitDelete() {
    clearTimeout(this.#deleteTimer);
    const pending = this.pendingDelete;
    this.pendingDelete = null;
    if (!pending) return;
    api.deleteVideo(pending.track.id)
      .then(() => emitVideoMutation(pending.track.id, 'deleted'))
      .catch(() => {});
  }

  /** Lieblingssong an- oder abwählen (Favoriten der Bibliothek) */
  async toggleFavorite(track = this.current) {
    if (!track) return;
    await setFavorite(track, !track.favorite);
    const favorite = !track.favorite;
    this.queue = this.queue.map(t => t.id === track.id ? { ...t, favorite } : t);
    return favorite;
  }

  // ─── Ereignisse ───
  #onTime() {
    const audio = this.#audio;
    this.time = audio.currentTime;
    const target = skipTarget(audio.currentTime, this.#skipRanges, audio.duration);
    if (target !== null) audio.currentTime = target;
    if (this.current && this.#counted !== this.current.id && audio.currentTime >= COUNT_AFTER_S) {
      this.#counted = this.current.id;
      recordPlay(this.current).catch(() => {});
    }
    clearTimeout(this.#saveTimer);
    this.#saveTimer = setTimeout(() => this.#save(), 3000);
    if ('mediaSession' in navigator && audio.duration && navigator.mediaSession.setPositionState) {
      try {
        navigator.mediaSession.setPositionState({ duration: audio.duration, position: audio.currentTime, playbackRate: 1 });
      } catch { /* manche Geräte kennen das nicht */ }
    }
  }

  #onEnded() {
    if (this.current && this.#counted !== this.current.id) {
      this.#counted = this.current.id;
      recordPlay(this.current).catch(() => {});
    }
    if (this.repeat === 'one') return this.#start(this.index);
    this.next();
  }

  // ─── Sperrbildschirm und Medientasten ───
  #mediaSession() {
    if (!('mediaSession' in navigator)) return;
    const session = navigator.mediaSession;
    const handlers = {
      play: () => this.toggle(), pause: () => this.pause(),
      previoustrack: () => this.prev(), nexttrack: () => this.next(),
      seekbackward: (d) => this.seek(this.time - (d.seekOffset || 10)),
      seekforward: (d) => this.seek(this.time + (d.seekOffset || 10)),
      seekto: (d) => this.seek(d.seekTime),
    };
    for (const [action, handler] of Object.entries(handlers)) {
      try { session.setActionHandler(action, handler); } catch { /* nicht unterstützt */ }
    }
  }

  #updateMetadata() {
    const track = this.current;
    if (!track || !('mediaSession' in navigator) || typeof MediaMetadata === 'undefined') return;
    const artwork = new URL(coverUrl(track), location.href).href;
    navigator.mediaSession.metadata = new MediaMetadata({
      title: track.title, artist: track.artist, album: track.album || this.title || 'TubeVault',
      artwork: [{ src: artwork, sizes: '480x360', type: 'image/jpeg' }],
    });
  }

  #save() {
    if (!this.queue.length) return writeJson(STATE_KEY, null);
    writeJson(STATE_KEY, { queue: this.queue.slice(0, 500), index: this.index, title: this.title,
                           source: this.source, shuffle: this.shuffle, repeat: this.repeat, time: this.time });
  }
}

export const musicPlayer = new MusicPlayer();

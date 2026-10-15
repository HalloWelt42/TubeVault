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
import { insertItem, moveItem, removeItem } from '../utils/queueOps.js';
import { normalizeRate } from '../utils/playbackRate.js';
import { afterMinutes, afterTrack, frozen, isDue, remainingMs, running } from '../utils/sleepTimer.js';
import { nextSegmentStart, previousSegmentStart, segmentIndexAt, toSegments } from '../utils/segments.js';

const BOOK_PREFIX = 'hoerbuch:';
const RATE_KEY = 'musik.tempo';             // Tempo je Hörbuch: { <Buch>: 1.25 }
const BOOK_SAVE_MS = 10000;
const STATE_KEY = 'musik.zustand';          // Weiterhören: Warteschlange dieses Geräts
const VOLUME_KEY = 'player.lastVolume';     // wie beim Videoplayer
const COUNT_AFTER_S = 30;                    // ab dann zählt ein Titel als gehört
const RESTART_AFTER_S = 3;                   // "Zurück" springt danach erst an den Titelanfang
const BOOK_SKIP_S = 30;                       // Sprungtasten beim Hörbuch (Sperrbildschirm, Uhr)
const REPEAT_MODES = ['off', 'all', 'one'];
export const UNDO_MS = 6000;                 // so lange lässt sich ein Löschen zurücknehmen
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
  rate = $state(1);              // Tempo; nur bei Hörbüchern wählbar, je Buch gemerkt
  sleep = $state(null);          // Schlaf-Zeitgeber (utils/sleepTimer.js), null = aus
  sleepLeft = $state(null);      // Millisekunden bis zum Anhalten, wenn nach Minuten
  segments = $state([]);         // Abschnitte des laufenden Titels (Kapitel eines Mixes, utils/segments.js)
  segmentIndex = $state(-1);     // laufender Abschnitt; ändert sich nur beim Wechsel, nicht mit jeder Sekunde

  #audio = null;
  #counted = null;               // Kennung, deren Wiedergabe schon gezählt ist
  #skipRanges = [];
  #skipsForBook = null;          // für welche Art die Sprungtasten angemeldet sind (#sessionSkips)
  #saveTimer = null;
  #unlocked = false;
  #deleteTimer = null;

  get current() { return this.queue[this.index] || null; }
  get active() { return this.queue.length > 0; }
  get upcoming() { return this.queue.slice(this.index + 1); }

  /** Laufender Abschnitt { index, count, start, end, title } oder null */
  get segment() {
    const index = this.segmentIndex;
    return index < 0 || !this.segments[index] ? null : { index, count: this.segments.length, ...this.segments[index] };
  }

  constructor() {
    if (typeof window === 'undefined') return;
    const saved = readJson(STATE_KEY);
    if (saved?.queue?.length) {
      Object.assign(this, { queue: saved.queue, index: saved.index ?? 0, title: saved.title || '',
                            source: saved.source || null, shuffle: !!saved.shuffle, repeat: saved.repeat || 'off',
                            time: saved.time || 0 });
      this.rate = this.#rateFor(this.source);
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
    audio.addEventListener('play', () => { this.playing = true; this.#pauseVideos(); this.sleep = running(this.sleep, Date.now()); });
    audio.addEventListener('pause', () => { this.playing = false; this.sleep = frozen(this.sleep, Date.now()); this.#save(); });
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
    // Hörbücher laufen nie zufällig; sie beginnen beim gemerkten Teil an der gemerkten Stelle
    this.shuffle = shuffle && !source.startsWith(BOOK_PREFIX);
    this.#setQueue(list.tracks, list.start_index || 0, { title: list.title, source }, list.start_at || 0);
    return true;
  }

  /** Eine gegebene Titelliste ab startIndex abspielen (z.B. eine sichtbare Liste) */
  playTracks(tracks, startIndex = 0, title = 'Auswahl') {
    if (!tracks.length) return;
    this.#unlock();
    this.shuffle = false;
    this.#setQueue(tracks, startIndex, { title, source: null });
  }

  #setQueue(tracks, startIndex, { title, source }, at = 0) {
    this.queue = tracks;
    this.title = title;
    this.source = source;
    this.rate = this.#rateFor(source);
    this.#start(startIndex, at);
  }

  /** Schlüssel des laufenden Hörbuchs, sonst null */
  get audiobook() {
    return this.source?.startsWith(BOOK_PREFIX) ? this.source.slice(BOOK_PREFIX.length) : null;
  }

  async #start(index, at = 0, { autoplay = true } = {}) {
    if (index < 0 || index >= this.queue.length) return;
    const audio = this.#element();
    this.index = index;
    const track = this.current;
    this.time = at;
    this.duration = track.duration || 0;
    this.#counted = null;
    audio.src = audioSrc(track);
    audio.currentTime = at;
    this.#applyRate();
    this.#sessionSkips();
    this.#updateMetadata();
    this.#save();
    if (autoplay) audio.play().catch(() => { this.playing = false; });
    this.audioInfo = null;
    api.musicAudioInfo(track.id).then((info) => { if (this.current?.id === track.id) this.audioInfo = info; }).catch(() => {});
    this.#skipRanges = [];
    this.segments = [];
    this.segmentIndex = -1;
    // Werbestellen und Abschnitte (Kapitel, z.B. die Titelliste eines Mixes) gibt es nur in Videos
    if (!isFile(track)) {
      loadSkipRanges(track.id).then((ranges) => { if (this.current?.id === track.id) this.#skipRanges = ranges; });
      api.getChapters(track.id).then((res) => {
        if (this.current?.id !== track.id) return;
        this.segments = toSegments(res.chapters, track.duration || this.duration);
        this.#followSegment();
      }).catch(() => {});
    }
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

  /** Wohin "Weiter" führt: der nächste Titel, bei "alle wiederholen" wieder der erste, sonst -1 */
  #nextIndex() {
    if (this.index + 1 < this.queue.length) return this.index + 1;
    return this.repeat === 'all' && this.queue.length ? 0 : -1;
  }

  /** Weiter: erst durch die Abschnitte des Titels, danach der nächste Titel */
  next() {
    const segmentStart = nextSegmentStart(this.segments, this.time);
    if (segmentStart !== null) return this.seek(segmentStart);
    const index = this.#nextIndex();
    if (index < 0) return this.pause();
    this.#start(index);
  }

  /** Zurück: an den Anfang des Abschnitts bzw. Titels, kurz danach einen weiter zurück */
  prev() {
    const segmentStart = previousSegmentStart(this.segments, this.time, RESTART_AFTER_S);
    if (segmentStart !== null) return this.seek(segmentStart);
    if (this.time > RESTART_AFTER_S || this.index === 0) return this.seek(0);
    this.#start(this.index - 1);
  }

  /** Direkt zum vorigen Titel bzw. Teil, ohne erst an den Anfang zu springen */
  previousTrack() {
    if (this.index > 0) return this.#start(this.index - 1);
    this.seek(0);
  }

  jump(index, at = 0) { this.#start(index, at); }

  seek(seconds) {
    const audio = this.#element();
    audio.currentTime = Math.max(0, Math.min(seconds, this.duration || seconds));
    this.time = audio.currentTime;
    this.#followSegment();
  }

  /** Um so viele Sekunden springen (negativ = zurück), innerhalb des Titels */
  skipBy(seconds) { this.seek(this.time + seconds); }

  // ─── Tempo (Hörbücher) ───
  /** Tempo des laufenden Hörbuchs setzen und für dieses Buch merken */
  setRate(value) {
    const book = this.audiobook;
    if (!book) return;
    this.rate = normalizeRate(value);
    this.#applyRate();
    writeJson(RATE_KEY, { ...(readJson(RATE_KEY) || {}), [book]: this.rate });
  }

  /** Gemerktes Tempo einer Quelle: je Hörbuch, Musik immer 1 */
  #rateFor(source) {
    if (!source?.startsWith(BOOK_PREFIX)) return 1;
    return normalizeRate(readJson(RATE_KEY)?.[source.slice(BOOK_PREFIX.length)] ?? 1);
  }

  #applyRate() {
    if (!this.#audio) return;
    this.#audio.defaultPlaybackRate = this.rate;   // gilt auch nach dem nächsten Laden
    this.#audio.playbackRate = this.rate;
  }

  // ─── Schlaf-Zeitgeber ───
  /** Nach dem laufenden Titel bzw. Teil anhalten */
  sleepAfterTrack() { this.#setSleep(afterTrack()); }

  /** Nach so vielen Minuten Hörzeit anhalten; Pausen zählen nicht mit */
  sleepAfterMinutes(minutes) { this.#setSleep(afterMinutes(minutes, Date.now(), this.playing)); }

  cancelSleep() { this.#setSleep(null); }

  #setSleep(timer) {
    this.sleep = timer;
    this.sleepLeft = remainingMs(timer, Date.now());
  }

  /** Bei jedem Zeitschritt: fällig? dann anhalten; sonst die Anzeige je Sekunde nachführen */
  #tickSleep() {
    if (this.sleep?.kind !== 'minutes') return;
    const now = Date.now();
    if (isDue(this.sleep, now)) {
      this.#setSleep(null);
      return this.pause();
    }
    const left = remainingMs(this.sleep, now);
    if (Math.ceil(left / 1000) !== Math.ceil((this.sleepLeft ?? 0) / 1000)) this.sleepLeft = left;
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
    if (this.audiobook) return;   // Hörbücher bleiben in ihrer Reihenfolge
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
    this.#arrange(removeItem(this.queue, this.index, position));
  }

  /** Einen Titel an eine Stelle setzen, z.B. Rückgängig nach remove() */
  insertAt(track, position) {
    if (!track) return;
    this.#arrange(insertItem(this.queue, this.index, track, position));
  }

  move(from, to) {
    if (from === to) return;
    this.#arrange(moveItem(this.queue, this.index, from, to));
  }

  #arrange({ queue, index }) {
    this.queue = queue;
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
    this.#setSleep(null);
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

  // ─── Hörbuch ───
  /** Das laufende Hörbuch von vorn; liefert die bisherige Stelle ({ index, time }) für ein Rückgängig */
  restartBook() {
    if (!this.audiobook) return null;
    const before = { index: this.index, time: this.time };
    this.#start(0, 0);
    return before;
  }

  // ─── Übergabe zwischen Geräten (stores/remote.svelte.js) ───
  /** Alles, was ein anderes Gerät braucht, um genau hier weiterzuspielen */
  snapshot() {
    if (!this.current) return null;
    return { queue: $state.snapshot(this.queue), index: this.index, title: this.title, source: this.source,
             time: this.#audio?.currentTime || this.time, shuffle: this.shuffle, repeat: this.repeat };
  }

  /** Eine übergebene Wiedergabe übernehmen und an derselben Stelle fortsetzen */
  adopt(state) {
    if (!state?.queue?.length) return;
    this.shuffle = !!state.shuffle;
    this.repeat = REPEAT_MODES.includes(state.repeat) ? state.repeat : 'off';
    this.#setQueue(state.queue, Math.min(state.index || 0, state.queue.length - 1),
                   { title: state.title || '', source: state.source || null }, state.time || 0);
  }

  /** In der Nutzeraktion vor einer erwarteten Übergabe: Ton freigeben (iOS) */
  prime() { this.#unlock(); }

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
    // Stelle höchstens alle 3 s merken (gedrosselt, nicht entprellt: timeupdate kommt
    // während der Wiedergabe laufend, ein entprellter Merker käme nie zum Zug)
    this.#saveTimer ??= setTimeout(() => { this.#saveTimer = null; this.#save(); }, 3000);
    this.#tickSleep();
    this.#followSegment();
    if ('mediaSession' in navigator && audio.duration && navigator.mediaSession.setPositionState) {
      try {
        navigator.mediaSession.setPositionState({ duration: audio.duration, position: audio.currentTime, playbackRate: this.rate });
      } catch { /* manche Geräte kennen das nicht */ }
    }
  }

  #onEnded() {
    if (this.current && this.#counted !== this.current.id) {
      this.#counted = this.current.id;
      recordPlay(this.current).catch(() => {});
    }
    if (this.sleep?.kind === 'track') return this.#sleepNow();
    if (this.repeat === 'one') return this.#start(this.index);
    this.next();
  }

  /** Schlaf-Zeitgeber "nach diesem Titel": den nächsten bereitlegen, aber nicht spielen */
  #sleepNow() {
    this.#setSleep(null);
    const index = this.#nextIndex();
    if (index >= 0) this.#start(index, 0, { autoplay: false });
  }

  // ─── Sperrbildschirm und Medientasten ───
  #mediaSession() {
    if (!('mediaSession' in navigator)) return;
    const session = navigator.mediaSession;
    const handlers = {
      play: () => this.toggle(), pause: () => this.pause(),
      previoustrack: () => this.prev(), nexttrack: () => this.next(),
      seekto: (d) => this.seek(d.seekTime),
    };
    for (const [action, handler] of Object.entries(handlers)) {
      try { session.setActionHandler(action, handler); } catch { /* nicht unterstützt */ }
    }
    this.#sessionSkips();
  }

  /** Sprungtasten für Sperrbildschirm, Uhr und Kopfhörer. Sind sie angemeldet,
   *  zeigen iPhone und Uhr nur sie statt "Titel vor/zurück". Darum: bei Musik
   *  keine (dort zählen Titel und Abschnitte), beim Hörbuch 30 Sekunden. */
  #sessionSkips() {
    if (!('mediaSession' in navigator)) return;
    const book = !!this.audiobook;
    if (this.#skipsForBook === book) return;
    this.#skipsForBook = book;
    const skip = (direction) => (book ? (d) => this.skipBy(direction * (d.seekOffset || BOOK_SKIP_S)) : null);
    for (const [action, handler] of [['seekbackward', skip(-1)], ['seekforward', skip(1)]]) {
      try { navigator.mediaSession.setActionHandler(action, handler); } catch { /* nicht unterstützt */ }
    }
  }

  /** Abschnitt nachführen; beim Wechsel zeigt der Sperrbildschirm den neuen */
  #followSegment() {
    const index = this.segments.length ? segmentIndexAt(this.segments, this.time) : -1;
    if (index === this.segmentIndex) return;
    this.segmentIndex = index;
    this.#updateMetadata();
  }

  #updateMetadata() {
    const track = this.current;
    if (!track || !('mediaSession' in navigator) || typeof MediaMetadata === 'undefined') return;
    const artwork = new URL(coverUrl(track), location.href).href;
    // In einem Mix zeigt der Sperrbildschirm den laufenden Abschnitt, darunter den Mix
    const segment = this.segments[this.segmentIndex];
    navigator.mediaSession.metadata = new MediaMetadata({
      title: segment?.title || track.title, artist: segment ? track.title : track.artist,
      album: track.album || this.title || 'TubeVault',
      artwork: [{ src: artwork, sizes: '480x360', type: 'image/jpeg' }],
    });
  }

  #bookSentAt = 0;
  #bookSentPart = null;

  /** Stand des Hörbuchs beim Server merken: höchstens alle 10 s, beim Anhalten
   *  und beim Wechsel des Teils sofort */
  #saveBookProgress() {
    const key = this.audiobook;
    if (!key || !this.current) return;
    const now = Date.now();
    if (this.playing && this.#bookSentPart === this.current.id && now - this.#bookSentAt < BOOK_SAVE_MS) return;
    this.#bookSentAt = now;
    this.#bookSentPart = this.current.id;
    api.musicBookProgress(key, this.current.id, Math.floor(this.time)).catch(() => {});
  }

  #save() {
    this.#saveBookProgress();
    if (!this.queue.length) return writeJson(STATE_KEY, null);
    writeJson(STATE_KEY, { queue: this.queue.slice(0, 500), index: this.index, title: this.title,
                           source: this.source, shuffle: this.shuffle, repeat: this.repeat, time: this.time });
  }
}

export const musicPlayer = new MusicPlayer();

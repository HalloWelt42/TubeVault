/**
 * TubeVault – Fernsteuerung und Übergabe zwischen Geräten
 *
 * Jedes Fenster ist ein Gerät (backend/app/services/remote_hub.py). Dieser
 * Store hält die Verbindung, meldet, was hier spielt, führt Befehle anderer
 * Geräte aus und übernimmt oder übergibt die Wiedergabe.
 *
 * Was hier spielt, wissen musicPlayer (Musik, Hörbücher) und videoSession
 * (Video). Was die Oberfläche dazu tun muss (Meldung zeigen, Video öffnen),
 * reicht die jeweilige App beim Start herein:
 *
 *   remote.start({ notify(text), openVideo(paket), openPlayer() })
 */
import { untrack } from 'svelte';
import { wsBaseUrl } from '../api/client.js';
import { musicPlayer } from './musicPlayer.svelte.js';
import { videoSession } from './videoSession.svelte.js';
import { rememberLanguage } from '../utils/audioTrackSync.js';
import {
  KIND_NAMES, deviceKind, musicState, playingElsewhere, positionOf, randomId, videoState, visibleDevices,
} from '../utils/remoteDevices.js';

const BROWSER_KEY = 'geraet.kennung';     // je Browser
const NAME_KEY = 'geraet.name';           // je Browser
const WINDOW_KEY = 'geraet.fenster';      // je Fenster (übersteht Neuladen)
const REPORT_MS = 2000;                   // während der Wiedergabe: Stelle so oft melden
const RECONNECT_MS = 3000;
const PING_MS = 25000;
const STEERING_MS = 120000;               // so lange gilt ein Gerät nach seinem letzten Befehl als Mitsteuerer

// Diese fremden Befehle bekommen eine kurze Meldung; Stelle und Lautstärke nicht
const ANNOUNCED = { pause: 'hat angehalten', abspielen: 'spielt ab', weiter: 'springt weiter', zurueck: 'springt zurück' };

function stored(storage, key, make) {
  try {
    const value = storage.getItem(key);
    if (value) return value;
    const fresh = make();
    storage.setItem(key, fresh);
    return fresh;
  } catch {
    return make();     // ohne Speicher: nur für diese Sitzung
  }
}

function volumeAdjustable() {
  // iOS lässt die Lautstärke nicht per Seite ändern: der Wert bleibt bei 1
  try { const probe = new Audio(); probe.volume = 0.5; return probe.volume === 0.5; } catch { return false; }
}

class Remote {
  me = $state(null);              // { id, geraet, name, art }
  devices = $state([]);           // wie vom Server, je Gerät zusätzlich _an: Empfangszeit des Stands
  connected = $state(false);
  steering = $state(null);        // Name des Geräts, das hier zuletzt mitgesteuert hat

  #ws = null;
  #steeringTimer = null;
  #hooks = {};
  #reportTimer = null;
  #pingTimer = null;
  #reconnectTimer = null;
  #canVolume = false;
  #started = false;

  /** Geräte zum Anzeigen: dieses zuerst, je anderem Browser eins */
  get visible() { return this.me ? visibleDevices(this.devices, this.me.id) : []; }

  /** Ein anderes Gerät, das gerade spielt, sonst null */
  get elsewhere() { return this.me ? playingElsewhere(this.devices, this.me.id) : null; }

  /** Spielt hier etwas (oder ist pausiert geladen)? */
  get localMedia() { return this.#localMedia(); }

  start(hooks = {}) {
    if (this.#started || typeof window === 'undefined') return;
    this.#started = true;
    this.#hooks = hooks;
    this.#canVolume = volumeAdjustable();
    const art = deviceKind(window.matchMedia?.('(pointer: coarse)').matches, screen.width, screen.height);
    this.me = {
      id: stored(sessionStorage, WINDOW_KEY, randomId),
      geraet: stored(localStorage, BROWSER_KEY, randomId),
      name: stored(localStorage, NAME_KEY, () => KIND_NAMES[art]),
      art,
    };
    this.#connect();
    // Stand melden, sobald sich etwas Wesentliches ändert; die Stelle nur im Takt
    $effect.root(() => {
      $effect(() => {
        this.#signature();
        untrack(() => this.#report());
      });
    });
    const foreground = () => { if (document.visibilityState === 'visible') this.#send({ typ: 'aktiv' }); };
    document.addEventListener('visibilitychange', foreground);
    window.addEventListener('focus', foreground);
  }

  // ─── Steuern ───
  /** Befehl an ein anderes Gerät, z.B. send(id, 'stelle', 72) */
  send(deviceId, aktion, wert = null) {
    this.#send({ typ: 'befehl', an: deviceId, aktion, wert });
    // Sofort sichtbar machen, nicht erst mit der nächsten Meldung
    const device = this.devices.find((d) => d.id === deviceId);
    if (device?.zustand && (aktion === 'umschalten' || aktion === 'pause' || aktion === 'abspielen')) {
      const laeuft = aktion === 'umschalten' ? !device.zustand.laeuft : aktion === 'abspielen';
      this.#updateDevice(deviceId, { ...device.zustand, stelle: this.positionOf(device), laeuft });
    }
  }

  /** Die Wiedergabe eines anderen Geräts hierher holen (in der Nutzeraktion aufrufen) */
  fetch(deviceId) {
    musicPlayer.prime();
    this.#send({ typ: 'befehl', an: deviceId, aktion: 'uebergeben', wert: { an: this.me.id } });
  }

  /** Die eigene Wiedergabe an ein anderes Gerät schicken */
  handTo(deviceId) { this.#handOver(deviceId); }

  rename(name) {
    const clean = (name || '').replace(/\s+/g, ' ').trim().slice(0, 40);
    if (!clean || !this.me) return;
    this.me = { ...this.me, name: clean };
    try { localStorage.setItem(NAME_KEY, clean); } catch { /* nur diese Sitzung */ }
    this.#send({ typ: 'name', name: clean });
  }

  /** Stelle eines Geräts jetzt, zwischen zwei Meldungen weitergerechnet */
  positionOf(device, now = performance.now()) {
    return positionOf(device?.zustand, device?._an, now);
  }

  // ─── Verbindung ───
  #connect() {
    const { id, geraet, name, art } = this.me;
    const query = new URLSearchParams({ id, geraet, name, art }).toString();
    const ws = new WebSocket(`${wsBaseUrl()}/api/remote/ws?${query}`);
    this.#ws = ws;
    ws.onopen = () => {
      this.connected = true;
      this.#pingTimer = setInterval(() => ws.readyState === WebSocket.OPEN && ws.send('ping'), PING_MS);
      this.#report();
    };
    ws.onmessage = (e) => {
      if (e.data === 'pong') return;
      try { this.#receive(JSON.parse(e.data)); } catch { /* fremde Nachricht */ }
    };
    ws.onclose = () => {
      this.connected = false;
      this.devices = [];
      clearInterval(this.#pingTimer);
      this.#reconnectTimer = setTimeout(() => this.#connect(), RECONNECT_MS);
    };
    ws.onerror = () => ws.close();
  }

  #send(message) {
    if (this.#ws?.readyState === WebSocket.OPEN) this.#ws.send(JSON.stringify(message));
  }

  #receive(message) {
    const now = performance.now();
    switch (message.typ) {
      case 'willkommen':
      case 'geraete':
        this.devices = message.geraete.map((d) => ({ ...d, _an: now }));
        break;
      case 'zustand':
        this.#updateDevice(message.id, message.zustand, now);
        break;
      case 'befehl':
        this.#execute(message.aktion, message.wert, message.von_name);
        break;
      case 'uebergabe':
        this.#adopt(message.paket, message.von_name);
        break;
      case 'fehler':
        this.#hooks.notify?.(message.text);
        break;
    }
  }

  #updateDevice(id, zustand, now = performance.now()) {
    this.devices = this.devices.map((d) => (d.id === id ? { ...d, zustand, _an: now } : d));
  }

  // ─── Eigenen Stand melden ───
  #localMedia() {
    if (videoSession.el && (videoSession.playing || !musicPlayer.playing)) return 'video';
    return musicPlayer.current ? 'musik' : null;
  }

  /** Liest alle Angaben, deren Änderung eine Meldung wert ist (nicht die Stelle) */
  #signature() {
    const track = musicPlayer.current;
    return [musicPlayer.playing, track?.id, track?.favorite, musicPlayer.index, musicPlayer.queue.length,
            musicPlayer.shuffle, musicPlayer.repeat, musicPlayer.volume, musicPlayer.duration, musicPlayer.segment?.index,
            videoSession.video?.id, videoSession.playing, videoSession.volume, videoSession.changes,
            videoSession.trackId, videoSession.tracks.length].join('|');
  }

  #state() {
    const media = this.#localMedia();
    if (media === 'video') return videoState(videoSession, this.#canVolume);
    if (media === 'musik') return musicState(musicPlayer, this.#canVolume);
    return null;
  }

  #report() {
    const state = this.#state();
    this.#send({ typ: 'zustand', zustand: state });
    clearTimeout(this.#reportTimer);
    if (state?.laeuft) this.#reportTimer = setTimeout(() => this.#report(), REPORT_MS);
  }

  // ─── Befehle anderer Geräte ───
  #execute(aktion, wert, from) {
    if (aktion === 'uebergeben') return this.#handOver(wert?.an);
    const media = this.#localMedia();
    if (!media) return;
    const wasPlaying = media === 'video' ? videoSession.playing : musicPlayer.playing;
    if (media === 'video') this.#videoCommand(aktion, wert);
    else this.#musicCommand(aktion, wert);
    const said = aktion === 'umschalten' ? ANNOUNCED[wasPlaying ? 'pause' : 'abspielen'] : ANNOUNCED[aktion];
    if (said) this.#hooks.notify?.(`${from} ${said}`);
    this.steering = from;
    clearTimeout(this.#steeringTimer);
    this.#steeringTimer = setTimeout(() => { this.steering = null; }, STEERING_MS);
  }

  #musicCommand(aktion, wert) {
    const p = musicPlayer;
    const number = Number(wert) || 0;
    switch (aktion) {
      case 'umschalten': return p.toggle();
      case 'abspielen': return p.playing || p.toggle();
      case 'pause': return p.pause();
      case 'weiter': return p.next();
      case 'zurueck': return p.prev();
      case 'stelle': return p.seek(Math.max(0, number));
      case 'sprung': return p.seek(Math.max(0, p.time + number));
      case 'lautstaerke': return p.setVolume(Math.min(1, Math.max(0, number)));
      case 'zufall': return p.audiobook || p.toggleShuffle();
      case 'wiederholen': return p.audiobook || p.cycleRepeat();
      case 'liebling': return p.toggleFavorite();
    }
  }

  #videoCommand(aktion, wert) {
    const el = videoSession.el;
    const number = Number(wert) || 0;
    switch (aktion) {
      case 'umschalten': return el.paused ? el.play().catch(() => {}) : el.pause();
      case 'abspielen': return el.play().catch(() => {});
      case 'pause': return el.pause();
      case 'weiter': return videoSession.next();
      case 'zurueck': return videoSession.prev();
      case 'stelle': el.currentTime = Math.max(0, number); return;
      case 'sprung': el.currentTime = Math.max(0, el.currentTime + number); return;
      case 'lautstaerke': el.volume = Math.min(1, Math.max(0, number)); return;
      case 'tonspur': return videoSession.chooseTrack(wert);
    }
  }

  // ─── Übergabe ───
  #package() {
    const media = this.#localMedia();
    if (media === 'video' && videoSession.video) {
      return { art: 'video', video: { id: videoSession.video.id, stelle: videoSession.el?.currentTime || 0,
                                      tonspur: videoSession.language, ...videoSession.queue() } };
    }
    const snapshot = media === 'musik' ? musicPlayer.snapshot() : null;
    return snapshot ? { art: musicPlayer.audiobook ? 'hoerbuch' : 'musik', musik: snapshot } : null;
  }

  #handOver(target) {
    const paket = target && this.#package();
    if (!paket) return;
    this.#send({ typ: 'uebergabe', an: target, paket });
    if (paket.art === 'video') videoSession.el?.pause();
    else musicPlayer.pause();
    const name = this.devices.find((d) => d.id === target)?.name || 'das andere Gerät';
    this.#hooks.notify?.(`Wiedergabe an ${name} übergeben`);
  }

  #adopt(paket, from) {
    if (paket.art === 'video' && paket.video) {
      musicPlayer.pause();
      rememberLanguage(paket.video.tonspur || '');
      this.#hooks.openVideo?.(paket.video);
    } else if (paket.musik) {
      videoSession.el?.pause();
      musicPlayer.adopt(paket.musik);
      this.#hooks.openPlayer?.();
    }
    this.#hooks.notify?.(`Von ${from} übernommen`);
  }
}

export const remote = new Remote();

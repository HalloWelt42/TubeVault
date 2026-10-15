// Live-Log: Verbindung zum Meldungsstrom und die Einträge fürs Terminal.
// Das Backend schickt Rahmen { boot, entries, gap, restarted } und liest je
// Verbindung mit eigenem Lesezeiger (routers/system.py, logs_websocket).
// Beim Wiederverbinden meldet das Terminal, was es schon hat (boot + seq);
// nach einem Neustart des Backends (neue boot) beginnt es neu, statt alle
// Einträge mit kleinerer Nummer zu verwerfen. Lücken werden genau gemeldet.
import { wsBaseUrl } from '../api/client.js';

const MAX_ENTRIES = 2500;
const MAX_PAUSED = 2000;
const RECONNECT_MS = 3000;

let localSeq = 0;

/** Eintrag, der im Browser entsteht (Hinweise des Terminals selbst). */
function localEntry(level, msg) {
  const now = Date.now();
  return prepare({
    ts: new Date(now).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    epoch: now / 1000, seq: `L${++localSeq}`, level, name: 'terminal', msg, cat: 'frontend',
  }, 'lokal');
}

/** Einmal beim Einfügen rechnen, was die Anzeige je Zeile braucht. key ist
 *  eindeutig über Neustarts hinweg (seq beginnt je Backend-Prozess bei 1). */
function prepare(entry, boot) {
  entry.key = `${boot}:${entry.seq}`;
  entry.cat ||= 'backend';
  entry.day = entry.epoch ? new Date(entry.epoch * 1000).toDateString() : '';
  return entry;
}

class LiveLog {
  entries = $state.raw([]);
  connected = $state(false);
  paused = $state(false);
  held = $state(0);              // während der Pause zurückgehaltene Einträge

  #socket = null;
  #wanted = false;
  #timer = null;
  #boot = '';
  #lastSeq = 0;
  #heldEntries = [];
  #heldDropped = 0;

  open() {
    this.#wanted = true;
    this.#connect();
  }

  close() {
    this.#wanted = false;
    clearTimeout(this.#timer);
    const socket = this.#socket;
    this.#socket = null;
    socket?.close();
    this.connected = false;
  }

  clear() { this.entries = []; }

  togglePause() {
    this.paused = !this.paused;
    if (this.paused) return;
    const marker = this.#heldDropped ? [localEntry('WARNING', `${this.#heldDropped} Einträge übersprungen (während der Pause zu viele)`)] : [];
    this.#show([...marker, ...this.#heldEntries]);
    this.#heldEntries = [];
    this.#heldDropped = 0;
    this.held = 0;
  }

  #connect() {
    if (this.#socket || !this.#wanted) return;
    const socket = new WebSocket(`${wsBaseUrl()}/api/system/ws/logs?boot=${encodeURIComponent(this.#boot)}&after=${this.#lastSeq}`);
    this.#socket = socket;
    // Jeder Lauscher prüft, ob er noch zur aktuellen Verbindung gehört
    socket.onopen = () => { if (this.#socket === socket) this.connected = true; };
    socket.onmessage = (event) => {
      if (this.#socket !== socket || event.data === 'pong') return;
      try { this.#receive(JSON.parse(event.data)); } catch { /* unlesbarer Rahmen */ }
    };
    socket.onclose = () => {
      if (this.#socket !== socket) return;
      this.#socket = null;
      this.connected = false;
      if (this.#wanted) this.#timer = setTimeout(() => this.#connect(), RECONNECT_MS);
    };
    socket.onerror = () => socket.close();
  }

  #receive(frame) {
    const incoming = [];
    if (frame.boot !== this.#boot) {
      if (frame.restarted) incoming.push(localEntry('WARNING', 'Backend neu gestartet'));
      this.#boot = frame.boot;
      this.#lastSeq = 0;
    }
    if (frame.gap) incoming.push(localEntry('WARNING', `${frame.gap} Einträge nicht mehr verfügbar (älter als der Speicher des Backends)`));
    for (const entry of frame.entries || []) {
      if (entry.seq <= this.#lastSeq) continue;
      this.#lastSeq = entry.seq;
      incoming.push(prepare(entry, this.#boot));
    }
    if (!incoming.length) return;
    if (this.paused) {
      this.#heldEntries.push(...incoming);
      const over = this.#heldEntries.length - MAX_PAUSED;
      if (over > 0) { this.#heldEntries.splice(0, over); this.#heldDropped += over; }
      this.held = this.#heldEntries.length;
      return;
    }
    this.#show(incoming);
  }

  #show(list) {
    if (list.length) this.entries = [...this.entries, ...list].slice(-MAX_ENTRIES);
  }
}

export const liveLog = new LiveLog();

// Versionswache: Nach einem Update soll niemand die Seite von Hand neu laden
// müssen (Vorbild Orbit). Die Oberfläche fragt ihre Versionsdatei
// (app-version.json, aus demselben Build wie die Seite) regelmäßig und beim
// Zurückkehren in den Tab ab. Ist eine neue Version ausgeliefert:
//   - in den ersten Sekunden nach dem Start oder im verdeckten Tab sofort neu laden,
//   - sonst beim nächsten Seitenwechsel; bis dahin zeigt eine Leiste den Knopf.
// Je Version nur ein selbsttätiger Versuch (sessionStorage) - keine Schleifen.
import { writable, get } from 'svelte/store';
import { FE_VERSION } from '../api/client.js';

const QUICK_RELOAD_MS = 10000;    // so lange nach dem Start wird sofort neu geladen
const CHECK_EVERY_MS = 60000;
const GUARD_KEY = 'tv.neu_geladen';

/** Neue, schon ausgelieferte Version (null, solange die laufende aktuell ist). */
export const newVersion = writable(null);

const startedAt = Date.now();

/** Neu laden (eigene Stelle, damit Tests es beobachten können). */
export const page = { reload: () => location.reload() };

// Läuft gerade Video oder Ton (auch im Hintergrund, Sperrbildschirm), wird
// nicht selbsttätig neu geladen - das geschieht dann beim nächsten Seitenwechsel
function mediaPlaying() {
  return [...document.querySelectorAll('video, audio')].some(m => !m.paused && !m.ended);
}

/** Einmal je Version selbsttätig neu laden; false, wenn schon versucht. */
function reloadOnce(version) {
  if (mediaPlaying()) return false;
  try {
    if (sessionStorage.getItem(GUARD_KEY) === version) return false;
    sessionStorage.setItem(GUARD_KEY, version);
  } catch { /* ohne Speicher: trotzdem einmal laden */ }
  page.reload();
  return true;
}

/** Von Hand über die Leiste: immer neu laden. */
export function reloadNow() {
  page.reload();
}

async function check() {
  let version;
  try {
    version = (await (await fetch('/app-version.json', { cache: 'no-store' })).json()).version;
  } catch { return; }   // Server gerade nicht erreichbar: beim nächsten Mal
  if (!version || version === FE_VERSION) return;
  newVersion.set(version);
  if (Date.now() - startedAt < QUICK_RELOAD_MS || document.hidden) reloadOnce(version);
}

/** Wache starten; route: Store, der sich bei jedem Seitenwechsel meldet. */
export function startVersionWatch(route) {
  if (FE_VERSION === 'dev') return;   // ohne eingebaute Version (Tests)
  check();
  setInterval(check, CHECK_EVERY_MS);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) check(); });
  let first = true;
  route.subscribe(() => {
    if (first) { first = false; return; }
    const version = get(newVersion);
    if (version) reloadOnce(version);
  });
}

// TubeVault – Zur Stelle: einen Titel in der Titelliste zeigen
//
// Der Spieler bittet, die Listen erfüllen. Wer eine Titelliste zeigt, meldet
// sich mit claimTrackSpot an ({ accepts(track), reveal(track) }); showTrack
// gibt die Bitte der zuletzt angemeldeten Liste, die den Titel zeigen kann.
// Nimmt keine sie an (gerade keine Liste zu sehen), bleibt sie kurz offen:
// die Liste, die nach dem Seitenwechsel erscheint oder fertig geladen hat,
// holt sie sich (offerTrackSpot). Eine Stelle für Rechner und Handy.
import { tick } from 'svelte';

const PENDING_MS = 10000;          // so lange wartet eine Bitte auf ihre Liste

let lists = [];
let pending = null;                // { track, until }

/** Liste anmelden; gibt die Abmeldung zurück. Eine offene Bitte bekommt sie gleich. */
export function claimTrackSpot(list) {
  lists = [...lists, list];
  offerTrackSpot();
  return () => { lists = lists.filter((l) => l !== list); };
}

/** Den Titel zeigen; true, wenn eine Liste auf dem Schirm ihn übernommen hat */
export function showTrack(track) {
  pending = { track, until: Date.now() + PENDING_MS };
  return offerTrackSpot();
}

/** Offene Bitte anbieten (nach dem Anmelden oder wenn eine Liste fertig geladen hat) */
export function offerTrackSpot() {
  if (!pending) return false;
  if (Date.now() > pending.until) { pending = null; return false; }
  const { track } = pending;
  const list = [...lists].reverse().find((l) => l.accepts(track));
  if (!list) return false;
  pending = null;
  list.reveal(track);
  return true;
}

/** Zeile eines Titels in einem Listenbereich mittig zeigen (Zeilen tragen data-titel) */
export async function scrollToTrack(container, id) {
  await tick();
  const row = container?.querySelector(`[data-titel="${CSS.escape(id)}"]`);
  row?.scrollIntoView({ block: 'center' });
  return !!row;
}

/** Einen Titel in einer seitenweisen Liste (utils/listLoader) zeigen: Stelle beim
 *  Server erfragen; fehlt er wegen Suche oder Filter, beides zurücksetzen und noch
 *  einmal fragen; dann die Seite mit ihm laden. true, wenn er jetzt geladen ist.
 *  locate() liefert die Stelle oder null, clearFilters() true, wenn sich etwas änderte. */
export async function loadAround({ list, pageSize, locate, clearFilters }) {
  let position = await locate();
  if (position === null && clearFilters()) position = await locate();
  if (position === null) return false;
  await list.load(true, { from: Math.floor(position / pageSize) + 1 });
  return true;
}

// Gruppen mit eigener Titelliste (Musikseite ?quelle=); Mixe wie "Alles zufällig" haben keine
const GROUP_KINDS = ['album', 'artist', 'channel', 'playlist', 'sammlung'];

/** Die Gruppe, aus der ein Titel gerade läuft, wenn sie eine eigene Titelliste hat; sonst null */
export function spotSource(source) {
  return GROUP_KINDS.includes(source?.split(':')[0]) ? source : null;
}

/** Vorn etwas anfügen (frühere Titel), ohne dass das Sichtbare springt; change() fügt an */
export async function prependInPlace(container, change) {
  const fromBottom = container ? container.scrollHeight - container.scrollTop : 0;
  await change();
  await tick();
  if (container) container.scrollTop = container.scrollHeight - fromBottom;
}

/**
 * TubeVault - Nachvertonung: Texte der Seite
 *
 * Reine Funktionen (ohne Zustand), damit Seite, Karten und Zeilen dieselben
 * Worte benutzen und sich testen lassen.
 */
import { formatDate, parseServerTime } from './format.js';

export const LANGUAGE_NAMES = {
  de: 'Deutsch', en: 'Englisch', fr: 'Französisch', es: 'Spanisch', it: 'Italienisch',
  nl: 'Niederländisch', pl: 'Polnisch', ja: 'Japanisch',
};

export function languageName(code) {
  return LANGUAGE_NAMES[(code || '').toLowerCase()] || (code || '').toUpperCase();
}

/**
 * Sprachen eines Auftrags: { source, target, revoice }. source ist null,
 * solange die Sprache des Originals unbekannt ist; revoice heißt: gleiche
 * Sprache, nur neu gesprochen.
 */
export function direction(request) {
  const source = request.source_language ? request.source_language.toLowerCase() : null;
  const target = (request.target_language || '').toLowerCase();
  return {
    source: source && source !== target ? languageName(source) : null,
    target: languageName(target),
    revoice: source === target,
  };
}

const DAY = 86400;

/** Zeitabstand in Sekunden als "vor ..." (unter einer Woche), sonst null. */
export function ago(seconds) {
  const s = Math.max(0, Math.floor(Number(seconds) || 0));
  if (s < 60) return 'gerade eben';
  if (s < 3600) return `vor ${Math.floor(s / 60)} Min.`;
  if (s < DAY) return `vor ${Math.floor(s / 3600)} Std.`;
  const days = Math.floor(s / DAY);
  return days === 1 ? 'vor 1 Tag' : `vor ${days} Tagen`;
}

/** Dauer als "seit ..." (für etwas, das ausbleibt oder andauert). */
export function since(seconds) {
  const s = Math.max(0, Math.floor(Number(seconds) || 0));
  if (s < 60) return 'seit eben';
  if (s < 3600) return `seit ${Math.floor(s / 60)} Min.`;
  if (s < DAY) return `seit ${Math.floor(s / 3600)} Std.`;
  const days = Math.floor(s / DAY);
  return days === 1 ? 'seit 1 Tag' : `seit ${days} Tagen`;
}

/** Zeitpunkt vom Server: "vor 3 Tagen", nach einer Woche "am 02.10.2026". */
export function when(timestamp, now = new Date()) {
  if (!timestamp) return '';
  const seconds = (now - parseServerTime(timestamp)) / 1000;
  return seconds < 7 * DAY ? ago(seconds) : `am ${formatDate(timestamp)}`;
}

/** Sekunden seit einem Zeitpunkt vom Server. */
export function secondsSince(timestamp, now = new Date()) {
  return timestamp ? Math.max(0, (now - parseServerTime(timestamp)) / 1000) : 0;
}

/** Geschätzte Restzeit, grob gerundet: "etwa 14 Min.", "etwa 1 Std. 20 Min.". */
export function about(seconds) {
  const minutes = Math.max(1, Math.round((Number(seconds) || 0) / 60));
  if (minutes < 60) return `etwa ${minutes} Min.`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `etwa ${hours} Std. ${rest} Min.` : `etwa ${hours} Std.`;
}

/** Kennzahlen im Kopf: "1 läuft · 2 warten · 8 fertig". */
export function headline(counts) {
  const working = counts?.working || 0;
  const queued = counts?.queued || 0;
  const done = counts?.done || 0;
  return [
    `${working} ${working === 1 ? 'läuft' : 'laufen'}`,
    `${queued} ${queued === 1 ? 'wartet' : 'warten'}`,
    `${done} fertig`,
  ].join(' · ');
}

/** Wann mit dem Auftrag zuletzt etwas geschah, passend zu seinem Zustand. */
export function timing(request, now = new Date()) {
  switch (request.status) {
    case 'done': return `fertig ${when(request.finished_at, now)}`;
    case 'error': return `fehlgeschlagen ${when(request.finished_at, now)}`;
    case 'skipped': return `übersprungen ${when(request.finished_at, now)}`;
    case 'cancelled': return `abgebrochen ${when(request.finished_at, now)}`;
    default: return `vorgemerkt ${when(request.created_at, now)}`;
  }
}

/** Zustand des Nachvertoners für den Kopf. */
export function workerLine(worker, working) {
  if (!worker?.last_seen) return { online: false, text: 'Nachvertoner hat sich noch nie gemeldet' };
  if (!worker.online) return { online: false, text: `Nachvertoner ${since(worker.seconds_ago)} nicht gemeldet` };
  return { online: true, text: `Nachvertoner ${working ? 'arbeitet' : 'bereit'} · ${ago(worker.seconds_ago)}` };
}

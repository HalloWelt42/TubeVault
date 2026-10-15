// Meldungen aus dem Browser ins Live-Log: die eine Stelle dafür.
// Läuft immer (nicht nur bei offenem Live-Log-Fenster), damit Fehler auch
// dann ankommen, wenn niemand hinsieht. Erfasst werden Warnungen und Fehler
// der Konsole, nicht abgefangene Fehler und Promise-Ablehnungen sowie, was
// Teile der App ausdrücklich melden (log.warn / log.error).
//
// Regeln: Das Mitschneiden darf nie selbst werfen (sonst bräche ein
// console.warn im App-Code); der Puffer ist begrenzt und zählt Verworfenes;
// gesendet wird gebündelt, bis nichts mehr ansteht.
import { api } from '../api/client.js';

const FLUSH_DELAY_MS = 2000;
const BATCH = 50;                 // so viele je Anfrage (Backend nimmt höchstens 50)
const MAX_PENDING = 500;
const MAX_MSG = 2000;
const MAX_TRACE = 8000;

let pending = [];
let dropped = 0;
let timer = null;
let sending = false;
let original = null;

/** Beliebige Werte sicher als Text: Fehler mit Name und Meldung, Kreisbezüge ohne Absturz. */
export function describe(value) {
  try {
    if (value instanceof Error) return `${value.name}: ${value.message}`;
    if (typeof value === 'string') return value;
    if (value === undefined) return 'undefined';
    if (typeof value === 'object' && value !== null) {
      const seen = new WeakSet();
      return JSON.stringify(value, (key, inner) => {
        if (typeof inner === 'bigint') return `${inner}n`;
        if (inner instanceof Error) return `${inner.name}: ${inner.message}`;
        if (typeof inner === 'object' && inner !== null) {
          if (seen.has(inner)) return '[Kreisbezug]';
          seen.add(inner);
        }
        return inner;
      });
    }
    return String(value);
  } catch {
    try { return String(value); } catch { return '[nicht darstellbar]'; }
  }
}

function stackOf(values) {
  const error = values.find((value) => value instanceof Error);
  return error?.stack ? error.stack.slice(0, MAX_TRACE) : undefined;
}

/** Eine Meldung vormerken; level: DEBUG | INFO | WARNING | ERROR. */
export function report(level, source, values, trace) {
  try {
    const list = Array.isArray(values) ? values : [values];
    const entry = { level, source, msg: list.map(describe).join(' ').slice(0, MAX_MSG) || '(leer)' };
    const stack = trace || stackOf(list);
    if (stack) entry.trace = stack.slice(0, MAX_TRACE);
    if (pending.length >= MAX_PENDING) { pending.shift(); dropped++; }
    pending.push(entry);
    schedule();
  } catch { /* Mitschnitt darf nie werfen */ }
}

export const log = {
  warn: (source, ...values) => report('WARNING', source, values),
  error: (source, ...values) => report('ERROR', source, values),
};

function schedule() {
  if (!timer && !sending) timer = setTimeout(flush, FLUSH_DELAY_MS);
}

async function flush() {
  timer = null;
  sending = true;
  try {
    while (pending.length || dropped) {
      const batch = pending.splice(0, BATCH);
      if (dropped) {
        batch.unshift({ level: 'WARNING', source: 'frontendLog', msg: `${dropped} Meldungen verworfen (Puffer voll)` });
        dropped = 0;
      }
      const response = await fetch(`${api.baseUrl}/api/system/logs/frontend`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(batch.slice(0, BATCH)),
      });
      if (!response.ok) break;      // Backend lehnt ab oder ist weg: später erneut, Puffer bleibt begrenzt
    }
  } catch { /* Backend nicht erreichbar: beim nächsten Mal */ }
  sending = false;
  if (pending.length) schedule();
}

/** Einmal beim Start der App: Konsole und unbehandelte Fehler mitschneiden. */
export function startFrontendLog() {
  if (original) return;
  original = { warn: console.warn, error: console.error };
  for (const [method, level] of [['warn', 'WARNING'], ['error', 'ERROR']]) {
    console[method] = (...values) => {
      original[method].apply(console, values);
      report(level, 'console', values);
    };
  }
  window.addEventListener('error', (event) =>
    report('ERROR', 'window', [`${event.message} (${event.filename}:${event.lineno})`], event.error?.stack));
  window.addEventListener('unhandledrejection', (event) =>
    report('ERROR', 'promise', ['Nicht abgefangen:', event.reason], event.reason?.stack));
}

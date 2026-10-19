// Reine Rechnungen des Musikspielers: Technikzeile, Schlaf-Zeitgeber,
// Warteschlange und Umordnen, Tempo, Hörbuchstand, Farbton des Covers.
import { describe, it, expect } from 'vitest';
import { audioDetails, audioQuality, codecName, trackFormat, trackOrigin } from '../lib/utils/audioTech.js';
import { SLEEP_MINUTES, afterMinutes, afterTrack, frozen, isDue, remainingMs, running, sleepLabel } from '../lib/utils/sleepTimer.js';
import { dragShift, dragTarget, insertItem, moveItem, removeItem, restoredQueue } from '../lib/utils/queueOps.js';
import { PLAYBACK_RATES, formatRate, normalizeRate } from '../lib/utils/playbackRate.js';
import { bookProgress, bookToResume } from '../lib/utils/bookProgress.js';
import { tintFromPixels } from '../lib/utils/coverTint.js';
import { swipeIntent } from '../mobile/parts/wischen.js';

const FILE = { id: 'f0123456789abcde', kind: 'datei', codec: 'flac' };
const VIDEO = { id: 'dQw4w9WgXcQ', kind: 'video' };

describe('Technikzeile', () => {
  it('nennt bei verlustfreien Dateien Bittiefe und Abtastrate', () => {
    const info = { codec: 'flac', bitrate: 1411000, sample_rate: 44100, bit_depth: 16 };
    expect(codecName(info)).toBe('FLAC');
    expect(audioDetails(info)).toEqual(['16 Bit', '44,1 kHz']);
    expect(audioQuality(info)).toBe('FLAC · 16 Bit · 44,1 kHz');
  });
  it('nennt sonst die Bitrate', () => {
    expect(audioQuality({ codec: 'opus', bitrate: 160123, sample_rate: 48000 })).toBe('OPUS · 160 kbit/s · 48 kHz');
    expect(audioQuality({ codec: 'aac', bitrate: 128000 })).toBe('AAC · 128 kbit/s');
  });
  it('bleibt leer ohne Format', () => {
    expect(audioQuality(null)).toBe('');
    expect(audioQuality({ bitrate: 128000 })).toBe('');
    expect(audioDetails(undefined)).toEqual([]);
  });
  it('kennt die Herkunft und die Kurzform für Listen', () => {
    expect(trackOrigin(FILE).label).toBe('Sammlung');
    expect(trackOrigin(VIDEO).label).toBe('Video');
    expect(trackFormat(FILE)).toBe('FLAC');
    expect(trackFormat({ ...FILE, codec: null })).toBe('Sammlung');
    expect(trackFormat(VIDEO)).toBe('Video');
  });
});

describe('Schlaf-Zeitgeber', () => {
  it('zählt Minuten nur, solange etwas läuft', () => {
    const start = afterMinutes(15, 1000, true);
    expect(remainingMs(start, 1000)).toBe(15 * 60000);
    expect(remainingMs(start, 61000)).toBe(14 * 60000);
    const paused = frozen(start, 61000);
    expect(paused.endsAt).toBeNull();
    expect(remainingMs(paused, 10 * 60000 + 61000)).toBe(14 * 60000);   // Pause zählt nicht
    const resumed = running(paused, 500000);
    expect(remainingMs(resumed, 500000)).toBe(14 * 60000);
    expect(isDue(resumed, 500000 + 14 * 60000)).toBe(true);
    expect(isDue(resumed, 500000)).toBe(false);
  });
  it('beginnt angehalten, wenn gerade nichts läuft', () => {
    const timer = afterMinutes(30, 0, false);
    expect(timer.endsAt).toBeNull();
    expect(remainingMs(timer, 10 ** 9)).toBe(30 * 60000);
    expect(isDue(timer, 10 ** 9)).toBe(false);
  });
  it('lässt "nach dem Titel" und "aus" unverändert', () => {
    expect(frozen(afterTrack(), 5)).toEqual({ kind: 'track' });
    expect(running(null, 5)).toBeNull();
    expect(remainingMs(afterTrack(), 5)).toBeNull();
    expect(isDue(afterTrack(), 5)).toBe(false);
  });
  it('beschriftet den Knopf', () => {
    expect(sleepLabel(null, null)).toBe('Einschlafen');
    expect(sleepLabel(afterTrack(), null, 7)).toBe('Aus nach Teil 7');
    expect(sleepLabel(afterTrack(), null)).toBe('Aus nach diesem Titel');
    expect(sleepLabel(afterMinutes(30, 0, true), 29 * 60000 + 1)).toBe('Aus in 30 Min.');
    expect(sleepLabel(afterMinutes(15, 0, true), 42000)).toBe('Aus in 42 s');
    expect(SLEEP_MINUTES.every((m) => m > 0)).toBe(true);
  });
});

describe('Warteschlange', () => {
  const q = ['a', 'b', 'c', 'd', 'e'];
  it('verschiebt und behält den laufenden Titel', () => {
    expect(moveItem(q, 1, 3, 4)).toEqual({ queue: ['a', 'b', 'c', 'e', 'd'], index: 1 });
    expect(moveItem(q, 2, 0, 4)).toEqual({ queue: ['b', 'c', 'd', 'e', 'a'], index: 1 });
    expect(moveItem(q, 2, 4, 0)).toEqual({ queue: ['e', 'a', 'b', 'c', 'd'], index: 3 });
    expect(moveItem(q, 2, 2, 4).index).toBe(4);
    expect(moveItem(q, 2, 3, 3).queue).toBe(q);
  });
  it('nimmt heraus und setzt beim Rückgängig an dieselbe Stelle', () => {
    const removed = removeItem(q, 2, 0);
    expect(removed).toEqual({ queue: ['b', 'c', 'd', 'e'], index: 1 });
    expect(insertItem(removed.queue, removed.index, 'a', 0)).toEqual({ queue: q, index: 2 });
    const later = removeItem(q, 2, 4);
    expect(insertItem(later.queue, later.index, 'e', 4)).toEqual({ queue: q, index: 2 });
  });
  it('nimmt den laufenden Titel nie heraus', () => {
    expect(removeItem(q, 2, 2).queue).toBe(q);
    expect(removeItem(q, 2, 9).queue).toBe(q);
  });
  it('rechnet beim Ziehen Zielplatz und Ausweichen', () => {
    expect(dragTarget(3, 130, 64, 2, 9)).toBe(5);
    expect(dragTarget(3, -500, 64, 2, 9)).toBe(2);
    expect(dragTarget(3, 2000, 64, 2, 9)).toBe(9);
    expect(dragTarget(3, 20, 0, 2, 9)).toBe(3);
    expect([2, 3, 4, 5, 6].map((i) => dragShift(i, 3, 5))).toEqual([0, 0, -1, -1, 0]);
    expect([2, 3, 4, 5, 6].map((i) => dragShift(i, 5, 3))).toEqual([0, 1, 1, 0, 0]);
  });
});

describe('Tempo', () => {
  it('kennt sinnvolle Stufen mit 1,0 in der Mitte', () => {
    expect(PLAYBACK_RATES).toContain(1);
    expect(PLAYBACK_RATES.map(formatRate)).toEqual(['0,75', '1,0', '1,25', '1,5', '1,75', '2,0']);
  });
  it('fängt ungültige Werte ab', () => {
    expect(normalizeRate('1.5')).toBe(1.5);
    expect(normalizeRate(0)).toBe(1);
    expect(normalizeRate(12)).toBe(1);
    expect(normalizeRate('schnell')).toBe(1);
  });
});

describe('Hörbuch', () => {
  const parts = [{ duration: 600 }, { duration: 1200 }, { duration: 1800 }];
  it('rechnet den Stand über alle Teile', () => {
    expect(bookProgress(parts, 1, 300)).toEqual({ heard: 900, total: 3600, left: 2700, fraction: 0.25 });
  });
  it('rechnet den Rest in Hörzeit beim Tempo', () => {
    expect(bookProgress(parts, 1, 300, 1.5).left).toBe(1800);
  });
  it('bleibt ohne Teile bei null', () => {
    expect(bookProgress([], 0, 50)).toEqual({ heard: 0, total: 0, left: 0, fraction: 0 });
  });
  it('wählt das zuletzt gehörte, nicht fertige Buch', () => {
    const books = [{ key: 'neu' }, { key: 'fertig', current_part: 3, finished: true }, { key: 'halb', current_part: 2 }];
    expect(bookToResume(books)?.key).toBe('halb');
    expect(bookToResume([{ key: 'neu' }])).toBeNull();
  });
});

describe('Farbton des Covers', () => {
  it('dunkelt die mittlere Farbe ab und übergeht durchsichtige Punkte', () => {
    const data = new Uint8ClampedArray([200, 100, 40, 255, 0, 0, 0, 0]);
    expect(tintFromPixels(data, 58)).toBe('rgb(58, 29, 12)');
  });
  it('gibt null ohne deckende Punkte', () => {
    expect(tintFromPixels(new Uint8ClampedArray([1, 2, 3, 0]))).toBeNull();
  });
});

describe('Wischen am Handy', () => {
  it('überlässt senkrechte Bewegungen dem Rollen', () => {
    expect(swipeIntent(4, 30)).toBe('rollen');
    expect(swipeIntent(20, 20)).toBe('rollen');
  });
  it('nimmt deutlich waagerechte Bewegungen als Wischen', () => {
    expect(swipeIntent(-30, 4)).toBe('wischen');
    expect(swipeIntent(25, -12)).toBe('wischen');
  });
  it('entscheidet unterhalb der Schwelle noch nichts', () => {
    expect(swipeIntent(6, 3)).toBeNull();
    expect(swipeIntent(0, 0)).toBeNull();
  });
});

describe('Gemerkte Warteschlange', () => {
  const A = { id: 'a1' }, B = { id: 'b2' };
  it('zieht eine Stelle hinter dem Ende auf den letzten Titel', () => {
    expect(restoredQueue([A, B], 5)).toEqual({ queue: [A, B], index: 1 });
  });
  it('zieht eine negative oder fehlende Stelle auf den ersten Titel', () => {
    expect(restoredQueue([A, B], -1)).toEqual({ queue: [A, B], index: 0 });
    expect(restoredQueue([A, B], undefined)).toEqual({ queue: [A, B], index: 0 });
  });
  it('verwirft leere und kaputte Einträge', () => {
    expect(restoredQueue([null, A, {}, 'x', B], 1)).toEqual({ queue: [A, B], index: 1 });
  });
  it('ohne Titel bleibt die Warteschlange leer', () => {
    expect(restoredQueue([null], 0)).toEqual({ queue: [], index: -1 });
    expect(restoredQueue(undefined, 0)).toEqual({ queue: [], index: -1 });
  });
});

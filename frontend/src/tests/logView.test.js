/**
 * Filter und Bezeichnungen des Live-Logs (lib/components/livelog/logView).
 *
 * Kontrakt: Reiter wählen Bereiche, die Stufe schneidet nach unten ab
 * (Standard ab Info, Details sind die Abfragen), die Suche findet Text ohne
 * Groß/Klein oder ein Muster; ein kaputtes Muster findet nichts statt zu werfen.
 * Bereiche heißen mit ganzen Wörtern.
 */
import { describe, it, expect } from 'vitest';
import { areaOf, exportText, filterEntries } from '../lib/components/livelog/logView.js';

const entries = [
  { level: 'DEBUG', cat: 'api', name: 'api', msg: 'GET /api/jobs → 200 (3ms)', ts: '10:00:00' },
  { level: 'INFO', cat: 'rss', name: 'rss_service', msg: 'Kanal geprüft: 3 neue Videos', ts: '10:00:01' },
  { level: 'WARNING', cat: 'frontend', name: 'console', msg: 'Einstellungen laden fehlgeschlagen', ts: '10:00:02' },
  { level: 'ERROR', cat: 'backend', name: 'api', msg: 'Unbehandelter Fehler bei GET /api/feed', ts: '10:00:03', trace: 'Traceback ...' },
];
const shown = (options) => filterEntries(entries, { tab: 'alle', threshold: 1, query: '', pattern: false, ...options }).map((e) => e.ts);

describe('logView', () => {
  it('Stufe ab Info blendet die Abfragen aus', () => {
    expect(shown({})).toEqual(['10:00:01', '10:00:02', '10:00:03']);
    expect(shown({ threshold: 0 })).toHaveLength(4);
    expect(shown({ threshold: 3 })).toEqual(['10:00:03']);
  });

  it('Reiter wählen Bereiche', () => {
    expect(shown({ tab: 'server' })).toEqual(['10:00:01', '10:00:03']);
    expect(shown({ tab: 'browser' })).toEqual(['10:00:02']);
    expect(shown({ tab: 'abfragen', threshold: 0 })).toEqual(['10:00:00']);
  });

  it('Suche als Text oder Muster', () => {
    expect(shown({ query: 'KANAL' })).toEqual(['10:00:01']);
    expect(shown({ query: 'GET .*feed', pattern: true })).toEqual(['10:00:03']);
    expect(shown({ query: '([', pattern: true })).toEqual([]);
  });

  it('Bereiche mit ganzen Wörtern, Verlauf beim Speichern', () => {
    expect(areaOf('rss').label).toBe('Kanalprüfung');
    expect(areaOf('frontend').label).toBe('Browser');
    expect(exportText(entries.slice(3))).toBe('10:00:03 [Fehler] [Server] api: Unbehandelter Fehler bei GET /api/feed\nTraceback ...');
  });
});

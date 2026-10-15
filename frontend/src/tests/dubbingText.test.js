/**
 * TubeVault - Texte der Seite Nachvertonung
 */
import { describe, it, expect } from 'vitest';
import { about, ago, direction, headline, since, timing, when, workerLine } from '../lib/utils/dubbingText.js';

const NOW = new Date('2026-10-15T12:00:00Z');

describe('direction', () => {
  it('nennt Quelle und Ziel', () => {
    expect(direction({ source_language: 'en', target_language: 'de' }))
      .toEqual({ source: 'Englisch', target: 'Deutsch', revoice: false });
  });
  it('gleiche Sprache heißt neu gesprochen', () => {
    expect(direction({ source_language: 'de', target_language: 'de' }))
      .toEqual({ source: null, target: 'Deutsch', revoice: true });
  });
  it('unbekannte Quelle bleibt leer', () => {
    expect(direction({ source_language: null, target_language: 'de' }).source).toBeNull();
  });
});

describe('ago und since', () => {
  it('rechnet in Minuten, Stunden und Tagen, Einzahl richtig', () => {
    expect(ago(20)).toBe('gerade eben');
    expect(ago(5 * 60)).toBe('vor 5 Min.');
    expect(ago(3 * 3600 + 10)).toBe('vor 3 Std.');
    expect(ago(86400)).toBe('vor 1 Tag');
    expect(ago(3 * 86400)).toBe('vor 3 Tagen');
    expect(since(86400 * 2)).toBe('seit 2 Tagen');
    expect(since(86400)).toBe('seit 1 Tag');
  });
});

describe('when und timing', () => {
  it('relativ bis eine Woche, danach mit Datum', () => {
    expect(when('2026-10-12 12:00:00', NOW)).toBe('vor 3 Tagen');
    expect(when('2026-10-02 18:55:09', NOW)).toBe('am 02.10.2026');
  });
  it('passt das Wort zum Zustand', () => {
    expect(timing({ status: 'done', finished_at: '2026-10-15 11:00:00' }, NOW)).toBe('fertig vor 1 Std.');
    expect(timing({ status: 'queued', created_at: '2026-10-15 11:58:00' }, NOW)).toBe('vorgemerkt vor 2 Min.');
    expect(timing({ status: 'error', finished_at: '2026-10-14 12:00:00' }, NOW)).toBe('fehlgeschlagen vor 1 Tag');
  });
});

describe('about', () => {
  it('rundet auf Minuten, ab einer Stunde mit Stunden', () => {
    expect(about(20)).toBe('etwa 1 Min.');
    expect(about(14 * 60 + 10)).toBe('etwa 14 Min.');
    expect(about(80 * 60)).toBe('etwa 1 Std. 20 Min.');
    expect(about(120 * 60)).toBe('etwa 2 Std.');
  });
});

describe('headline', () => {
  it('Einzahl und Mehrzahl', () => {
    expect(headline({ working: 1, queued: 2, done: 8 })).toBe('1 läuft · 2 warten · 8 fertig');
    expect(headline({ working: 0, queued: 1, done: 0 })).toBe('0 laufen · 1 wartet · 0 fertig');
  });
});

describe('workerLine', () => {
  it('bereit, arbeitend, still und nie gemeldet', () => {
    expect(workerLine({ last_seen: 'x', seconds_ago: 10, online: true }, false))
      .toEqual({ online: true, text: 'Nachvertoner bereit · gerade eben' });
    expect(workerLine({ last_seen: 'x', seconds_ago: 10, online: true }, true).text).toBe('Nachvertoner arbeitet · gerade eben');
    expect(workerLine({ last_seen: 'x', seconds_ago: 3 * 86400, online: false }, false).text)
      .toBe('Nachvertoner seit 3 Tagen nicht gemeldet');
    expect(workerLine({ last_seen: null }, false).online).toBe(false);
  });
});

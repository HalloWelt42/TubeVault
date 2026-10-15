import { describe, it, expect } from 'vitest';
import {
  RULE_KINDS, REASON_LABELS, arrangeCategories, categoryInfo, freeColors, kindOf, overviewInfo, ruleText,
  rulesForSave, saveLabel,
} from '../lib/utils/categoryRules.js';
import { sortItems } from '../lib/utils/collection.js';

const cards = [
  { id: 1, name: 'Konzerte', video_count: 214, duration: 658800, finished_count: 12, last_filled_at: '2026-10-10 10:00:00',
    rules: [{ kind: 'channel', value: 'UCarte', label: 'ARTE Concert' }, { kind: 'semantic', value: 'Live-Auftritt einer Band' }] },
  { id: 2, name: 'Kulturkämpfe', description: 'Jugendkultur', video_count: 37, duration: 0, finished_count: 0,
    last_filled_at: '2026-10-14 10:00:00', rules: [] },
  { id: 3, name: 'Ältere Sachen', video_count: 37, duration: 3600, finished_count: 0, last_filled_at: null,
    created_at: '2026-10-12 10:00:00', rules: [{ kind: 'tag', value: 'Archiv' }] },
];

describe('Kategorien', () => {
  it('kennt jede Regelart mit Bezeichnung, Symbol und Erklärung', () => {
    expect(RULE_KINDS.map((k) => k.label)).toEqual(['Kanal ist', 'Schlagwort enthält', 'Inhaltlich wie']);
    expect(RULE_KINDS.every((k) => k.icon && k.hint && k.placeholder)).toBe(true);
    expect(kindOf('gibtsnicht').kind).toBe('channel');
  });

  it('beschriftet Regel-Chips und Gründe', () => {
    expect(cards[0].rules.map(ruleText)).toEqual(['ARTE Concert', 'inhaltlich wie: Live-Auftritt einer Band']);
    expect(ruleText({ kind: 'channel', value: 'UCx' })).toBe('UCx');
    expect(Object.keys(REASON_LABELS)).toEqual(['hand', 'channel', 'tag', 'semantic']);
  });

  it('sucht in Name, Beschreibung und Regeln und sortiert', () => {
    expect(arrangeCategories(cards, { search: 'arte' }).map((c) => c.id)).toEqual([1]);
    expect(arrangeCategories(cards, { search: 'jugend' }).map((c) => c.id)).toEqual([2]);
    expect(arrangeCategories(cards, { sort: 'groesse' }).map((c) => c.id)).toEqual([1, 3, 2]);   // Gleichstand nach Name
    expect(arrangeCategories(cards, { sort: 'name' }).map((c) => c.id)).toEqual([3, 1, 2]);
    expect(arrangeCategories(cards, { sort: 'gefuellt' }).map((c) => c.id)).toEqual([2, 3, 1]);   // ohne Füllung zählt das Anlegen
  });

  it('fasst Kennzahlen zusammen', () => {
    expect(categoryInfo(cards[0])).toBe('214 Videos · 183:00 Std. · 12 gesehen');
    expect(categoryInfo({ video_count: 1 })).toBe('1 Video');
    expect(overviewInfo({ categories: cards, assigned: 255, unassigned: 32268 }))
      .toBe('3 Kategorien · 255 Videos eingeordnet · 32.268 ohne Kategorie');
  });

  it('schickt nur ausgefüllte Regeln, die Genauigkeit nur bei "inhaltlich wie"', () => {
    expect(rulesForSave([
      { kind: 'channel', value: '', label: '' },
      { kind: 'tag', value: '  Konzert ', precision: 'genau' },
      { kind: 'semantic', value: 'Kochen', precision: 'weit' },
    ])).toEqual([{ kind: 'tag', value: 'Konzert' }, { kind: 'semantic', value: 'Kochen', precision: 'weit' }]);
  });

  it('nennt im Speicherknopf, wie viele neu hineinkommen', () => {
    expect(saveLabel({ new: 1234 })).toBe('Speichern und 1.234 einordnen');
    expect(saveLabel({ new: 0 })).toBe('Speichern');
    expect(saveLabel(null)).toBe('Speichern');
  });

  it('schlägt zuerst freie Farben vor', () => {
    expect(freeColors(['#a', '#b', '#c'], ['#a'], 2)).toEqual(['#b', '#c']);
    expect(freeColors(['#a', '#b'], ['#a', '#b'], 3)).toEqual(['#a', '#b']);
  });

  it('sortiert eine Sammlung nach Erscheinen', () => {
    const items = [{ id: 'a', upload_date: '20230101' }, { id: 'b', upload_date: '20240101' }, { id: 'c' }];
    expect(sortItems(items, 'neueste').map((i) => i.id)).toEqual(['b', 'a', 'c']);
  });
});

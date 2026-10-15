import { describe, it, expect } from 'vitest';
import {
  stateChips, filterItems, sortItems, continueIndex, moveItem, shuffled, dayLabel, groupByDay, sinceOf, totalTime,
} from '../lib/utils/collection.js';

const items = [
  { id: 'a', title: 'Java Tutorial 1', channel_name: 'Brotcrunsher', duration: 400, state: 'finished', added_at: '2026-10-01 10:00:00' },
  { id: 'b', title: 'Atlas Airborne', channel_name: 'Boston Dynamics', duration: 98, state: 'new', added_at: '2026-10-03 10:00:00' },
  { id: 'c', title: 'Java Tutorial 2', channel_name: 'Brotcrunsher', duration: 500, state: 'started', added_at: '2026-10-02 10:00:00' },
  { id: 'd', title: 'Über Ärger', channel_name: 'Ölkanal', duration: 50, state: 'new', added_at: null },
];

describe('Sammlungen', () => {
  it('zählt den Stand für die Chips', () => {
    expect(stateChips({ new: 2, started: 1, finished: 1 }, 4).map((c) => `${c.label} ${c.count}`))
      .toEqual(['Alle 4', 'Neu 2', 'Angefangen 1', 'Gesehen 1']);
  });

  it('filtert nach Wörtern in Titel und Kanal und nach Stand', () => {
    expect(filterItems(items, { search: 'java brot' }).map((i) => i.id)).toEqual(['a', 'c']);
    expect(filterItems(items, { search: 'ärger' }).map((i) => i.id)).toEqual(['d']);
    expect(filterItems(items, { state: 'new' }).map((i) => i.id)).toEqual(['b', 'd']);
  });

  it('sortiert, ohne die eigene Reihenfolge anzutasten', () => {
    expect(sortItems(items, 'eigene')).toBe(items);
    expect(sortItems(items, 'titel').map((i) => i.id)).toEqual(['b', 'a', 'c', 'd']);
    expect(sortItems(items, 'dauer').map((i) => i.id)).toEqual(['d', 'b', 'a', 'c']);
    expect(sortItems(items, 'hinzugefuegt').map((i) => i.id)).toEqual(['b', 'c', 'a', 'd']);
    expect(items.map((i) => i.id)).toEqual(['a', 'b', 'c', 'd']);
  });

  it('fasst die Gesamtdauer kurz', () => {
    expect(totalTime(37 * 60 + 10)).toBe('37 Min.');
    expect(totalTime(21 * 3600 + 37 * 60)).toBe('21:37 Std.');
    expect(totalTime(3599.9)).toBe('1:00 Std.');
  });

  it('setzt beim angefangenen, sonst beim ersten neuen Video fort', () => {
    expect(continueIndex(items)).toBe(2);
    expect(continueIndex(items.filter((i) => i.state !== 'started'))).toBe(1);
    expect(continueIndex([items[0]])).toBe(-1);
  });

  it('verschiebt an die Einfügestelle', () => {
    expect(moveItem(['a', 'b', 'c', 'd'], 3, 1)).toEqual(['a', 'd', 'b', 'c']);
    expect(moveItem(['a', 'b', 'c', 'd'], 0, 3)).toEqual(['b', 'c', 'a', 'd']);
    expect(moveItem(['a', 'b', 'c', 'd'], 0, 4)).toEqual(['b', 'c', 'd', 'a']);
  });

  it('mischt vollständig und stellt Gewünschtes nach vorn', () => {
    const mixed = shuffled(items, 'c');
    expect(mixed[0].id).toBe('c');
    expect(mixed.map((i) => i.id).sort()).toEqual(['a', 'b', 'c', 'd']);
  });

  it('benennt Tage wie im Verlauf', () => {
    const now = new Date(2026, 9, 15, 12, 0);
    expect(dayLabel(new Date(2026, 9, 15, 3, 19), now)).toBe('Heute, 15.10.');
    expect(dayLabel(new Date(2026, 9, 14, 23, 52), now)).toBe('Gestern, 14.10.');
    expect(dayLabel(new Date(2026, 9, 13, 20, 0), now)).toBe('Dienstag, 13.10.');
    expect(dayLabel(new Date(2026, 8, 1, 20, 0), now)).toBe('01.09.');
    expect(dayLabel(new Date(2025, 8, 1, 20, 0), now)).toBe('01.09.2025');
  });

  it('gruppiert nach Kalendertag in Ortszeit', () => {
    const now = new Date(2026, 9, 15, 12, 0);
    const utc = (d) => d.toISOString().slice(0, 19).replace('T', ' ');
    const groups = groupByDay([
      { t: utc(new Date(2026, 9, 15, 3, 0)) }, { t: utc(new Date(2026, 9, 15, 1, 0)) }, { t: utc(new Date(2026, 9, 14, 23, 0)) },
    ], (i) => i.t, now);
    expect(groups.map((g) => `${g.label}:${g.items.length}`)).toEqual(['Heute, 15.10.:2', 'Gestern, 14.10.:1']);
  });

  it('rechnet Zeiträume in Serverzeit um', () => {
    const now = new Date(2026, 9, 15, 12, 0);
    const midnight = new Date(2026, 9, 15).toISOString().slice(0, 19).replace('T', ' ');
    expect(sinceOf('heute', now)).toBe(midnight);
    expect(sinceOf('7', now)).toBe(new Date(2026, 9, 9).toISOString().slice(0, 19).replace('T', ' '));
    expect(sinceOf('', now)).toBeNull();
  });
});

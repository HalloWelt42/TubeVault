// Listen-Baukasten: Titel gezielt aus Alben, Interpreten, Listen übernehmen,
// eine ganze Gruppe auf einmal ohne Doppel (utils/poolSources.js).
import { describe, it, expect } from 'vitest';
import { POOL_SOURCES, addedText, filterGroups, filterTracks, planAdd, sourceById } from '../lib/utils/poolSources.js';

const t = (id, title = id, artist = 'Band', album = null) => ({ id, title, artist, album });

describe('Quellen', () => {
  it('kennt die sechs Quellen, Unbekanntes führt zu allen Titeln', () => {
    expect(POOL_SOURCES.map((s) => s.label)).toEqual(
      ['Alle Titel', 'Alben', 'Interpreten', 'Lieblingssongs', 'Wiedergabelisten', 'Verlauf']);
    expect(sourceById('alben').groups).toBeTypeOf('function');
    expect(sourceById('quatsch').id).toBe('titel');
    expect(sourceById(undefined).id).toBe('titel');
  });

  it('sucht in Gruppen nach Name und Unterzeile, in Titeln nach Titel, Interpret und Album', () => {
    const groups = [{ key: 'a', name: 'Space Night', subtitle: 'Verschiedene Interpreten' }, { key: 'b', name: 'Curtis', subtitle: '50 Cent' }];
    expect(filterGroups(groups, 'cent').map((g) => g.key)).toEqual(['b']);
    expect(filterGroups(groups, '  ')).toBe(groups);
    const tracks = [t('1', 'Weltraum', 'Ambient', 'Space Night'), t('2', 'In da Club', '50 Cent', 'Curtis')];
    expect(filterTracks(tracks, 'space welt').map((x) => x.id)).toEqual(['1']);
    expect(filterTracks(tracks, 'CLUB').map((x) => x.id)).toEqual(['2']);
  });
});

describe('Ganze Gruppe hinzufügen', () => {
  it('nimmt ein ganzes Album in seiner Reihenfolge, ohne was schon in der Liste steht', () => {
    const album = [t('a1'), t('a2'), t('a3'), t('a4')];
    const plan = planAdd(album, new Set(['a2', 'x9']));
    expect(plan.fresh.map((x) => x.id)).toEqual(['a1', 'a3', 'a4']);
    expect(plan.skipped).toBe(1);
    expect(addedText(plan)).toBe('3 Titel hinzugefügt, 1 stand schon drin');
  });

  it('nimmt einen Titel, der in der Gruppe doppelt vorkommt, nur einmal', () => {
    const artist = [t('s1'), t('s2'), t('s1')];
    const plan = planAdd(artist, new Set());
    expect(plan.fresh.map((x) => x.id)).toEqual(['s1', 's2']);
    expect(addedText(plan)).toBe('2 Titel hinzugefügt, 1 stand schon drin');
  });

  it('meldet, wenn alles schon in der Liste steht', () => {
    expect(addedText(planAdd([t('a'), t('b')], new Set(['a', 'b'])))).toBe('Alle stehen schon in der Liste');
    expect(addedText(planAdd([t('a')], new Set(['a'])))).toBe('Steht schon in der Liste');
    expect(addedText(planAdd([t('a'), t('b')], new Set()))).toBe('2 Titel hinzugefügt');
    expect(addedText({ fresh: [t('a')], skipped: 3 })).toBe('1 Titel hinzugefügt, 3 standen schon drin');
  });
});

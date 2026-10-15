import { describe, expect, it } from 'vitest';
import { hitRanges, markParts } from '../lib/utils/searchHighlight.js';
import { activeFilterCount, addressParams, apiParams, emptyFilters, filtersFromSaved, filtersToSaved, readSearch } from '../lib/utils/searchState.js';

const prefix = (word) => ({ words: [word], prefix: true });
const whole = (...words) => ({ words, prefix: false });

describe('Treffer hervorheben', () => {
  it('Wortanfang trifft, auch ohne Akzente und Großschreibung', () => {
    expect(markParts('Kernfusion: Löten am Fusionsreaktor', [prefix('fusion'), prefix('loten')])).toEqual([
      { text: 'Kernfusion: ', hit: false },
      { text: 'Löten', hit: true },
      { text: ' am ', hit: false },
      { text: 'Fusionsreaktor', hit: true },
    ]);
  });

  it('kurze Wörter nur ganz, Wortfolgen am Stück', () => {
    expect(hitRanges('Lem und das Lemma', [whole('lem')])).toEqual([[0, 3]]);
    expect(markParts('Harald Lesch und Lesch', [whole('harald', 'lesch')]).filter((p) => p.hit))
      .toEqual([{ text: 'Harald Lesch', hit: true }]);
  });

  it('ohne Begriffe bleibt der Text ganz', () => {
    expect(markParts('Nichts', [])).toEqual([{ text: 'Nichts', hit: false }]);
    expect(markParts('', [prefix('x')])).toEqual([]);
  });
});

describe('Zustand der Suche', () => {
  it('Adresse, API und gemerkte Suche sprechen dieselben Filter', () => {
    const state = readSearch({ q: 'Kernfusion', bereich: 'gesagt', sprache: 'de,en', laenge: 'lang', ordnung: 'neu' });
    expect(state.section).toBe('gesagt');
    expect(apiParams(state.filters)).toEqual({ language: 'de,en', length: 'lang', order: 'neu' });
    expect(addressParams(state)).toMatchObject({ q: 'Kernfusion', bereich: 'gesagt', sprache: 'de,en', laenge: 'lang', ordnung: 'neu', ort: null });
    expect(filtersFromSaved(filtersToSaved(state.filters))).toEqual(state.filters);
  });

  it('Standardordnung und Leeres stehen nirgends', () => {
    const filters = emptyFilters();
    expect(apiParams(filters)).toEqual({});
    expect(addressParams({ q: '', section: null, filters }).ordnung).toBeNull();
    expect(activeFilterCount(filters)).toBe(0);
    expect(activeFilterCount({ ...filters, sprache: ['de'], ort: 'archiv', genau: 'weit' })).toBe(2);
  });
});

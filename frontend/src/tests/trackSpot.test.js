// Zur Stelle: der Spieler bittet, die Liste auf dem Schirm erfüllt - auch
// nach einem Seitenwechsel und mitten in langen, seitenweise geladenen Listen
// (utils/trackSpot.js, utils/listLoader.svelte.js).
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { claimTrackSpot, loadAround, offerTrackSpot, showTrack, spotSource } from '../lib/utils/trackSpot.js';
import { createListLoader } from '../lib/utils/listLoader.svelte.js';

const TRACK = { id: 'f0123456789abcde', title: 'Lied' };
const claims = [];
const claim = (list) => { const release = claimTrackSpot(list); claims.push(release); return release; };

afterEach(() => { claims.splice(0).forEach((release) => release()); vi.useRealTimers(); });

describe('Bitte und Liste', () => {
  it('gibt den Titel der zuletzt angemeldeten Liste, die ihn zeigen kann', () => {
    const outer = { accepts: () => true, reveal: vi.fn() };
    const inner = { accepts: () => false, reveal: vi.fn() };
    claim(outer);
    claim(inner);
    expect(showTrack(TRACK)).toBe(true);
    expect(outer.reveal).toHaveBeenCalledWith(TRACK);
    expect(inner.reveal).not.toHaveBeenCalled();
  });

  it('wartet ohne passende Liste, bis eine erscheint oder fertig geladen hat', () => {
    expect(showTrack(TRACK)).toBe(false);
    let loaded = false;
    const list = { accepts: () => loaded, reveal: vi.fn() };
    claim(list);
    expect(list.reveal).not.toHaveBeenCalled();
    loaded = true;
    expect(offerTrackSpot()).toBe(true);
    expect(list.reveal).toHaveBeenCalledTimes(1);
    expect(offerTrackSpot()).toBe(false);          // erfüllt ist erfüllt
  });

  it('vergisst eine Bitte, die zu lange auf ihre Liste wartet', () => {
    vi.useFakeTimers();
    showTrack(TRACK);
    vi.advanceTimersByTime(11000);
    const list = { accepts: () => true, reveal: vi.fn() };
    claim(list);
    expect(list.reveal).not.toHaveBeenCalled();
  });

  it('nennt nur Gruppen mit eigener Titelliste, keine Mixe', () => {
    expect(spotSource('album:cover:abc')).toBe('album:cover:abc');
    expect(spotSource('playlist:4')).toBe('playlist:4');
    expect(spotSource('all')).toBeNull();
    expect(spotSource(null)).toBeNull();
  });
});

describe('Mitten in einer langen Liste', () => {
  const PAGE = 100;
  const all = Array.from({ length: 10796 }, (_, i) => ({ id: `t${i}` }));
  let fetchPage;

  beforeEach(() => {
    fetchPage = vi.fn(async (page) => ({ items: all.slice((page - 1) * PAGE, page * PAGE), total: all.length }));
  });

  it('lädt nur die Seite mit dem Titel, frühere einzeln nach vorn', async () => {
    const list = createListLoader(fetchPage);
    const found = await loadAround({ list, pageSize: PAGE, locate: async () => 9876, clearFilters: () => false });
    expect(found).toBe(true);
    expect(fetchPage).toHaveBeenCalledTimes(1);
    expect(fetchPage).toHaveBeenCalledWith(99);
    expect(list.items.some((t) => t.id === 't9876')).toBe(true);
    expect(list.hasEarlier).toBe(true);
    await list.loadEarlier();
    expect(fetchPage).toHaveBeenLastCalledWith(98);
    expect(list.items[0].id).toBe('t9700');
    expect(list.items).toHaveLength(200);
  });

  it('setzt Suche und Filter zurück, wenn sie den Titel verdecken', async () => {
    const list = createListLoader(fetchPage);
    let filtered = true;
    const locate = vi.fn(async () => (filtered ? null : 42));
    const clearFilters = vi.fn(() => { filtered = false; return true; });
    expect(await loadAround({ list, pageSize: PAGE, locate, clearFilters })).toBe(true);
    expect(locate).toHaveBeenCalledTimes(2);
    expect(list.hasEarlier).toBe(false);
  });

  it('meldet, wenn der Titel in der Liste fehlt', async () => {
    const list = createListLoader(fetchPage);
    expect(await loadAround({ list, pageSize: PAGE, locate: async () => null, clearFilters: () => false })).toBe(false);
    expect(fetchPage).not.toHaveBeenCalled();
  });
});

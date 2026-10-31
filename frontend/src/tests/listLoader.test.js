// Nachladen beim Rollen (utils/listLoader.svelte.js, HELF-71): liefert die Schnittstelle einen Cursor, kommt jede
// weitere Seite ab ihm statt ab dem Versatz; fällt zwischendurch etwas aus der Liste, fehlt dahinter nichts. Ein
// Fehlschlag beim Nachladen beendet die Liste nicht.
import { describe, it, expect, vi } from 'vitest';
import { createListLoader } from '../lib/utils/listLoader.svelte.js';

// Ein Bestand wie auf dem Server: Seiten ab Versatz oder ab Cursor (Cursor = letzte gelieferte Kennung)
function server(anzahl, groesse) {
  const bestand = Array.from({ length: anzahl }, (_, i) => ({ id: `v${String(i).padStart(3, '0')}` }));
  return {
    bestand,
    seite(page, after) {
      const ab = after ? bestand.findIndex((v) => v.id > after) : (page - 1) * groesse;
      const start = ab < 0 ? bestand.length : ab;
      const items = bestand.slice(start, start + groesse);
      const weiter = start + groesse < bestand.length;
      return { items, total: bestand.length, hasMore: weiter, next: weiter ? items.at(-1).id : null };
    },
    archivieren(id) { bestand.splice(bestand.findIndex((v) => v.id === id), 1); },
  };
}

describe('listLoader mit Cursor', () => {
  it('lädt ab dem Cursor und verliert nichts, wenn zwischendurch archiviert wird', async () => {
    const s = server(50, 10);
    const vorher = s.bestand.map((v) => v.id);
    const fetchPage = vi.fn(async (page, after) => s.seite(page, after));
    const list = createListLoader(fetchPage);
    await list.load(true);
    while (list.hasMore) {
      s.archivieren(list.items.at(-3).id);     // eine schon gezeigte Kachel archivieren, wie in der Bibliothek
      await list.loadMore();
    }
    expect(list.items.map((v) => v.id)).toEqual(vorher);
    expect(fetchPage.mock.calls[1][1]).toBe('v009');   // zweite Seite ab dem letzten Eintrag der ersten
  });

  it('ein Neuladen beginnt wieder vorn, ohne Cursor', async () => {
    const s = server(30, 10);
    const fetchPage = vi.fn(async (page, after) => s.seite(page, after));
    const list = createListLoader(fetchPage);
    await list.load(true);
    await list.loadMore();
    await list.load(true);
    expect(fetchPage.mock.calls.at(-1)).toEqual([1, null]);
    expect(list.items).toHaveLength(10);
  });

  it('ein Fehler beim Nachladen hält die Liste offen, danach geht es an derselben Stelle weiter', async () => {
    vi.useFakeTimers();
    const s = server(30, 10);
    let kaputt = true;
    const fetchPage = vi.fn(async (page, after) => {
      if (after && kaputt) { kaputt = false; throw new Error('Backend nicht erreichbar'); }
      return s.seite(page, after);
    });
    const list = createListLoader(fetchPage);
    await list.load(true);
    await list.loadMore();
    expect(list.items).toHaveLength(10);
    expect(list.hasMore).toBe(true);
    expect(list.canLoad()).toBe(false);             // kurz Ruhe statt Dauerfeuer
    vi.advanceTimersByTime(3500);
    expect(list.canLoad()).toBe(true);
    await list.loadMore();
    await list.loadMore();
    expect(list.items.map((v) => v.id)).toEqual(s.bestand.map((v) => v.id));
    expect(list.hasMore).toBe(false);
    vi.useRealTimers();
  });
});

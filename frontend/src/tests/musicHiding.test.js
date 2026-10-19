// Minus-Knopf: ein Titel verlässt die ganze Musik, Datei wie Video, gelöscht
// wird nichts. Kurz lässt er sich zurückholen, auch an seine Stelle in der
// Warteschlange (utils/musicHiding.js, stores/musicPlayer.svelte.js).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { musicPlayer as player, UNDO_MS } from '../lib/stores/musicPlayer.svelte.js';
import { toast } from '../lib/stores/notifications.js';
import { excludeAlbum, hideTrack } from '../lib/utils/musicHiding.js';
import { setHidden } from '../lib/utils/musicTrack.js';
import { onMusicChange } from '../lib/utils/musicChanges.js';

const FILE = { id: 'f0123456789abcde', kind: 'datei', title: 'Datei-Titel' };
const VIDEO = { id: 'dQw4w9WgXcQ', kind: 'video', title: 'Video-Titel' };
const OTHER = { id: 'otherVideo1', kind: 'video', title: 'Anderer' };
const NEXT = { id: 'nextVideo01', kind: 'video', title: 'Nächster' };

const ok = (body = {}) => Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
const calls = () => fetch.mock.calls.map(([url, config]) => `${config?.method || 'GET'} ${url}`);
const ids = () => player.queue.map((t) => t.id);

beforeEach(() => {
  fetch.mockReset();
  fetch.mockImplementation(() => ok());
  window.HTMLMediaElement.prototype.play = vi.fn(() => Promise.resolve());
  window.HTMLMediaElement.prototype.pause = vi.fn();
  player.queue = [OTHER, VIDEO, NEXT];
  player.index = 0;
});

describe('Ausblenden je Art', () => {
  it('nimmt für Dateien und Videos ihren eigenen Weg', async () => {
    await setHidden(FILE, true);
    await setHidden(VIDEO, false);
    expect(calls()).toEqual([`PUT /api/music/files/${FILE.id}/hidden`, `PUT /api/music/videos/${VIDEO.id}/hidden`]);
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ hidden: false });
  });
});

describe('Minus-Knopf', () => {
  it('blendet ein Video aus, nimmt es aus der Warteschlange und meldet es allen Listen', async () => {
    const changes = [];
    const stop = onMusicChange((change) => changes.push(change));
    const undo = vi.spyOn(toast, 'undo');
    await hideTrack(VIDEO);
    stop();
    expect(calls()).toEqual([`PUT /api/music/videos/${VIDEO.id}/hidden`]);
    expect(ids()).toEqual([OTHER.id, NEXT.id]);
    expect(changes).toEqual([{ removed: [VIDEO.id], reload: true }]);
    expect(undo).toHaveBeenCalledWith('Ausgeblendet: Video-Titel', expect.any(Function), UNDO_MS);
  });

  it('liefert dasselbe Rückgängig, das der Hinweis anbietet (für die Fernbedienung)', async () => {
    const offer = vi.spyOn(toast, 'undo');
    const undo = await hideTrack(VIDEO);
    expect(offer.mock.calls.at(-1)[1]).toBe(undo);
  });

  it('holt beim Rückgängig zurück, an die alte Stelle', async () => {
    const undo = vi.spyOn(toast, 'undo');
    await hideTrack(VIDEO);
    await undo.mock.calls.at(-1)[1]();
    expect(calls().at(-1)).toBe('POST /api/music/hidden/restore');
    expect(JSON.parse(fetch.mock.calls.at(-1)[1].body)).toEqual({ tracks: [VIDEO.id], albums: [] });
    expect(ids()).toEqual([OTHER.id, VIDEO.id, NEXT.id]);
  });

  it('spielt beim laufenden Titel weiter und stellt ihn beim Rückgängig als nächsten an', async () => {
    player.index = 1;
    const undo = vi.spyOn(toast, 'undo');
    await hideTrack(VIDEO);
    expect(player.current.id).toBe(NEXT.id);
    await undo.mock.calls.at(-1)[1]();
    expect(ids()).toEqual([OTHER.id, NEXT.id, VIDEO.id]);
    expect(player.current.id).toBe(NEXT.id);
  });

  it('war es der einzige Titel, steht er nach dem Rückgängig wieder bereit', async () => {
    player.queue = [FILE];
    player.index = 0;
    const undo = vi.spyOn(toast, 'undo');
    await hideTrack(FILE);
    expect(player.active).toBe(false);
    await undo.mock.calls.at(-1)[1]();
    expect(ids()).toEqual([FILE.id]);
    expect(player.current.id).toBe(FILE.id);
  });

  it('lässt alles, wie es war, wenn der Server ablehnt', async () => {
    fetch.mockImplementation(() => Promise.resolve({ ok: false, status: 404, statusText: 'Not Found',
                                                      json: () => Promise.resolve({ detail: 'Video unbekannt' }) }));
    await expect(hideTrack(VIDEO)).rejects.toThrow('Video unbekannt');
    expect(ids()).toEqual([OTHER.id, VIDEO.id, NEXT.id]);
  });
});

describe('Gefällt nicht', () => {
  it('löscht nur Videos; eine Datei bleibt in der Warteschlange', () => {
    player.queue = [OTHER, FILE, NEXT];
    player.deleteTrack(FILE);
    expect(ids()).toEqual([OTHER.id, FILE.id, NEXT.id]);
    expect(player.pendingDelete).toBeNull();
  });

  it('stellt ein Video beim Rückgängig zurück, ohne zu löschen', () => {
    player.deleteTrack(VIDEO);
    expect(ids()).toEqual([OTHER.id, NEXT.id]);
    player.undoDelete();
    expect(ids()).toEqual([OTHER.id, VIDEO.id, NEXT.id]);
    expect(calls()).not.toContain(`DELETE /api/videos/${VIDEO.id}`);
  });
});

describe('Album ausschließen', () => {
  it('nimmt den heutigen Schlüssel des Servers, auch wenn ein früherer kam', async () => {
    const SPACE = { ...OTHER, album_source: 'album:cover:aaa' };
    player.queue = [SPACE, VIDEO, NEXT];
    fetch.mockImplementation(() => ok({ source: 'album:cover:aaa', name: 'Space Night', count: 2 }));
    const changes = [];
    const stop = onMusicChange((change) => changes.push(change));
    const undo = vi.spyOn(toast, 'undo');
    await excludeAlbum('album:cover:bbb');
    stop();
    expect(ids()).toEqual([VIDEO.id, NEXT.id]);
    expect(changes).toEqual([{ removedAlbums: ['album:cover:aaa'], reload: true }]);
    expect(undo.mock.calls.at(-1)[0]).toBe('Album "Space Night" ausgeschlossen');
    await undo.mock.calls.at(-1)[1]();
    expect(JSON.parse(fetch.mock.calls.at(-1)[1].body)).toEqual({ tracks: [], albums: ['album:cover:aaa'] });
  });
});

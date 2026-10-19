// Minus der Fernbedienung bei einem Video aus einer Playlist: nur die Playlist
// verliert es, die Wiedergabe springt weiter; das Rückgängig setzt es genau an
// seine Stelle zurück (utils/playlistRemoval.js).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { playlistIdOf, removeFromPlaylist } from '../lib/utils/playlistRemoval.js';
import { toast } from '../lib/stores/notifications.js';

const VIDEO = { id: 'dQw4w9WgXcQ', title: 'Ein Video' };
const calls = () => fetch.mock.calls.map(([url, config]) => `${config?.method || 'GET'} ${url}`);

beforeEach(() => {
  fetch.mockReset();
  fetch.mockImplementation((url) => Promise.resolve({
    ok: true, json: () => Promise.resolve(url.endsWith('/entries') ? { ids: ['f0123456789abcde', VIDEO.id, 'zweites11'] } : {}),
  }));
});

describe('Aus der Playlist nehmen', () => {
  it('nimmt heraus, spielt weiter und bietet das Rückgängig an', async () => {
    const next = vi.fn();
    const offer = vi.spyOn(toast, 'undo');
    const undo = await removeFromPlaylist('12', VIDEO, next);
    expect(calls()).toEqual(['GET /api/playlists/12/entries', `DELETE /api/playlists/12/videos/${VIDEO.id}`]);
    expect(next).toHaveBeenCalledTimes(1);
    expect(offer).toHaveBeenCalledWith('Aus der Playlist genommen: Ein Video', undo, expect.any(Number));

    await undo();
    expect(calls().slice(2)).toEqual(['POST /api/playlists/12/videos', 'PUT /api/playlists/12/reorder']);
    expect(JSON.parse(fetch.mock.calls.at(-1)[1].body)).toEqual({ video_ids: ['f0123456789abcde', VIDEO.id, 'zweites11'] });
  });

  it('kennt nur Playlists, keine Favoriten oder Kategorien', () => {
    expect(playlistIdOf('playlist:12')).toBe('12');
    expect(playlistIdOf('favorites:Standard')).toBeNull();
    expect(playlistIdOf(null)).toBeNull();
  });
});

// Wiedergabeliste umbenennen: leer geht nicht, der neue Name wird gemeldet
// (utils/playlistRename.js).
import { describe, it, expect, beforeEach } from 'vitest';
import { EMPTY_NAME, onPlaylistRenamed, renamePlaylist } from '../lib/utils/playlistRename.js';
import { onMusicChange } from '../lib/utils/musicChanges.js';

beforeEach(() => {
  fetch.mockReset();
  fetch.mockImplementation(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ updated: true }) }));
});

describe('Umbenennen', () => {
  it('speichert ohne Ränder und meldet Listen und Musik', async () => {
    const renamed = [];
    const changes = [];
    const stopRenamed = onPlaylistRenamed((detail) => renamed.push(detail));
    const stopChanges = onMusicChange((change) => changes.push(change));
    expect(await renamePlaylist(7, '  Lange Fahrt ')).toBe('Lange Fahrt');
    stopRenamed();
    stopChanges();
    const [url, config] = fetch.mock.calls[0];
    expect([url, config.method, JSON.parse(config.body)]).toEqual(['/api/playlists/7', 'PUT', { name: 'Lange Fahrt' }]);
    expect(renamed).toEqual([{ id: '7', name: 'Lange Fahrt' }]);
    expect(changes).toEqual([{ reload: true }]);
  });

  it('lehnt leere Namen ab, ohne zu speichern', async () => {
    await expect(renamePlaylist(7, '   ')).rejects.toThrow(EMPTY_NAME);
    expect(fetch).not.toHaveBeenCalled();
  });
});

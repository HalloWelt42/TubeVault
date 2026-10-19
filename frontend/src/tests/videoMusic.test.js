// Ein Video von Hand als Musik festlegen oder nicht: ein Weg für Videoansicht,
// Videolisten und Musik; alle Musiklisten erfahren es (utils/videoMusic.js).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { musicMenuItem, setVideoMusic } from '../lib/utils/videoMusic.js';
import { isRemoved, onMusicChange } from '../lib/utils/musicChanges.js';

beforeEach(() => {
  fetch.mockReset();
  fetch.mockImplementation(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ updated: 1 }) }));
});

describe('Musik je Video', () => {
  it('speichert über den bestehenden Weg (ein Video) und meldet es den Musiklisten', async () => {
    const changes = [];
    const stop = onMusicChange((change) => changes.push(change));
    expect(await setVideoMusic('abcdefghijk', false)).toBe(false);
    expect(await setVideoMusic('abcdefghijk', true)).toBe(true);
    stop();
    const [url, config] = fetch.mock.calls[0];
    expect([url, JSON.parse(config.body)]).toEqual(['/api/videos/music/batch', { video_ids: ['abcdefghijk'], is_music: false }]);
    expect(isRemoved(changes[0])({ id: 'abcdefghijk' })).toBe(true);
    expect(changes[0].music).toEqual({ id: 'abcdefghijk', is_music: false });
    expect(changes[1]).toMatchObject({ music: { id: 'abcdefghijk', is_music: true }, restored: true, reload: true });
  });

  it('bietet im Menü das Gegenteil an und meldet die neue Wahl zurück', async () => {
    const changed = vi.fn();
    expect(musicMenuItem({ id: 'v', is_music: 1 }).label).toBe('Keine Musik');
    const item = musicMenuItem({ id: 'v', is_music: 0 }, changed);
    expect(item.label).toBe('Als Musik');
    await item.run();
    expect(changed).toHaveBeenCalledWith(true);
  });
});

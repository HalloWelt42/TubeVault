import { describe, expect, it } from 'vitest';
import {
  deviceKind, musicState, playingElsewhere, positionOf, randomId, videoState, visibleDevices,
} from '../lib/utils/remoteDevices.js';

const device = (id, geraet, extra = {}) => ({ id, geraet, name: id, art: 'rechner', aktiv: 100, zustand: null, ...extra });

describe('Fernsteuerung: Geräte', () => {
  it('erkennt Rechner, Handy und Tablet', () => {
    expect(deviceKind(false, 390, 844)).toBe('rechner');
    expect(deviceKind(true, 390, 844)).toBe('handy');
    expect(deviceKind(true, 1024, 768)).toBe('tablet');
  });

  it('erzeugt Kennungen ohne https', () => {
    const a = randomId();
    expect(a).toMatch(/^[0-9a-f]{32}$/);
    expect(randomId()).not.toBe(a);
  });

  it('zeigt sich selbst zuerst und je Browser ein Fenster, das spielende vor dem zuletzt genutzten', () => {
    const list = [
      device('handy', 'b-handy', { aktiv: 50 }),
      device('ich', 'b-ich'),
      device('ich-zweites-fenster', 'b-ich', { zustand: { laeuft: true } }),
      device('mac-alt', 'b-rechner', { aktiv: 300 }),
      device('mac-spielt', 'b-rechner', { aktiv: 10, zustand: { laeuft: true } }),
    ];
    expect(visibleDevices(list, 'ich').map((d) => d.id)).toEqual(['ich', 'mac-spielt', 'handy']);
    expect(playingElsewhere(list, 'ich').id).toBe('mac-spielt');
    expect(playingElsewhere([device('ich', 'b-ich')], 'ich')).toBeNull();
  });

  it('rechnet die Stelle zwischen zwei Meldungen weiter, nie über das Ende', () => {
    expect(positionOf({ stelle: 72, laeuft: true, dauer: 231 }, 1000, 3500)).toBe(74.5);
    expect(positionOf({ stelle: 72, laeuft: false, dauer: 231 }, 1000, 3500)).toBe(72);
    expect(positionOf({ stelle: 230, laeuft: true, dauer: 231 }, 0, 10000)).toBe(231);
    expect(positionOf(null, 0, 0)).toBe(0);
  });
});

describe('Fernsteuerung: gemeldeter Stand', () => {
  const titel = (id) => ({ id, title: `Titel ${id}`, artist: 'ABBA', favorite: id === 'b' });

  it('meldet Musik mit Quelle, Zufall und Lautstärke nur, wenn das Gerät sie stellen kann', () => {
    const player = { current: titel('b'), queue: [titel('a'), titel('b'), titel('c')], index: 1, title: 'ABBA Gold',
                     time: 72, duration: 231, playing: true, volume: 0.6, shuffle: true, repeat: 'off', audiobook: null };
    const state = musicState(player, true);
    expect(state).toMatchObject({ art: 'musik', kennung: 'b', quelle: 'ABBA Gold', lautstaerke: 0.6, zufall: true, liebling: true });
    expect(state.kann).toContain('weiter');
    expect(musicState(player, false).lautstaerke).toBeNull();
    expect(musicState({ current: null }, true)).toBeNull();
  });

  it('meldet ein Hörbuch mit Teil statt Quelle und ohne Zufall', () => {
    const player = { current: titel('c'), queue: [titel('a'), titel('b'), titel('c')], index: 2, title: 'Die Insel',
                     time: 10, duration: 91, playing: false, volume: 1, shuffle: false, repeat: 'off', audiobook: 'abc' };
    const state = musicState(player, true);
    expect(state).toMatchObject({ art: 'hoerbuch', quelle: 'Teil 3 von 3', zufall: null, wiederholen: null });
    expect(state.kann).not.toContain('weiter');
  });

  it('meldet ein Video mit Tonspuren', () => {
    const session = { el: { currentTime: 324, duration: 853, paused: false, volume: 0.64 },
                      video: { id: 'NxsYhM89B4M', title: 'Why F-35B', channel_name: 'Not What You Think', duration: 853 },
                      tracks: [{ id: 7, label: 'Deutsch', language: 'de' }], trackId: 7, canNext: true, canPrev: false };
    expect(videoState(session, true)).toMatchObject({
      art: 'video', kennung: 'NxsYhM89B4M', stelle: 324, laeuft: true, tonspur: 7,
      tonspuren: [{ id: 7, label: 'Deutsch' }], kann: ['sprung', 'weiter'],
    });
    expect(videoState({ el: null }, true)).toBeNull();
  });

  // Minus der Fernbedienung (Wunsch 19.10.2026): Musik immer, Hörbücher nie, Videos nur aus einer Playlist
  it('meldet das Minus je nach Art', () => {
    const player = { current: titel('a'), queue: [titel('a')], index: 0, time: 0, duration: 100, playing: true,
                     volume: 1, repeat: 'off', audiobook: null };
    expect(musicState(player, true).kann).toContain('minus');
    expect(musicState({ ...player, audiobook: 'buch' }, true).kann).not.toContain('minus');
    const session = { el: { currentTime: 0, duration: 60, paused: false, volume: 1 }, video: { id: 'v', title: 'Video' },
                      tracks: [], trackId: null, canNext: true, canPrev: false };
    expect(videoState({ ...session, canRemove: true }, true).kann).toContain('minus');
    expect(videoState({ ...session, canRemove: false }, true).kann).not.toContain('minus');
  });

  // Je nach Format und Browser kennt das Medienelement die Länge noch nicht (NaN) oder
  // meldet Infinity; JSON macht daraus null, und der Server versteht die Meldung nicht
  it('meldet nur endliche Zahlen, auch wenn das Element die Länge nicht kennt', () => {
    const player = { current: { id: 'a', title: 'Titel', duration: 231 }, queue: [], index: 0,
                     time: 12, duration: Infinity, playing: true, volume: 1, repeat: 'off', audiobook: null };
    expect(musicState(player, true).dauer).toBe(231);
    for (const unknown of [Infinity, NaN, undefined, -1]) {
      const sent = JSON.parse(JSON.stringify(musicState({ ...player, current: { id: 'a' }, duration: unknown, time: NaN }, true)));
      expect(sent).toMatchObject({ dauer: 0, stelle: 0 });
    }

    const session = { el: { currentTime: 5, duration: Infinity, paused: false, volume: 1 },
                      video: { id: 'v', title: 'Video', duration: 853 }, tracks: [], trackId: null };
    expect(videoState(session, true).dauer).toBe(853);
    const stream = JSON.parse(JSON.stringify(videoState({ ...session, el: { ...session.el, duration: NaN }, video: { id: 'v' } }, true)));
    expect(stream).toMatchObject({ dauer: 0, stelle: 5 });
  });
});

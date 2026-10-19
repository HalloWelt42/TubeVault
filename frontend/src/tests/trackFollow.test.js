// Zur Stelle dauerhaft: eingeschaltet folgt die Liste jedem Titelwechsel, aus
// passiert nichts von selbst; die Wahl gilt je Gerät (stores/trackFollow.svelte.js).
// Das Mitrollen selbst hängt an einem Svelte-Effekt und ist im Browser geprüft;
// hier die Entscheidung und das Merken.
import { describe, it, expect } from 'vitest';
import { followsChange, trackFollow } from '../lib/stores/trackFollow.svelte.js';

describe('Zur Stelle dauerhaft', () => {
  it('folgt nur eingeschaltet und nur bei einem anderen Titel', () => {
    expect(followsChange(true, 'a', 'b')).toBe(true);
    expect(followsChange(true, 'b', 'b')).toBe(false);
    expect(followsChange(false, 'a', 'b')).toBe(false);
    expect(followsChange(true, 'a', null)).toBe(false);
  });

  it('merkt sich die Wahl je Gerät', () => {
    const vorher = trackFollow.on;
    expect(trackFollow.toggle()).toBe(!vorher);
    expect(localStorage.getItem('tv_titel_folgen')).toBe(vorher ? '0' : '1');
    trackFollow.toggle();
    expect(localStorage.getItem('tv_titel_folgen')).toBe(vorher ? '1' : '0');
  });
});

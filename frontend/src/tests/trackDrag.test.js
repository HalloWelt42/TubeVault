// Listen-Baukasten: Fracht beim Ziehen, Ablagestelle und Ziel beim Verschieben.
import { describe, expect, it } from 'vitest';
import { TRACKS_MIME, carriesTracks, draggedTracks, dropIndex, moveTarget, setDraggedTracks } from '../lib/utils/trackDrag.js';

function fakeTransfer() {
  const data = {};
  return { data, types: [], setData(type, value) { data[type] = value; this.types.push(type); }, getData: (type) => data[type] || '' };
}

describe('Titel ziehen', () => {
  it('gibt die Titel mit und erkennt die Fracht', () => {
    const dataTransfer = fakeTransfer();
    const tracks = [{ id: 'f0123456789abcde', title: 'Eins', artist: 'Band' }];
    setDraggedTracks({ dataTransfer }, tracks);
    expect(carriesTracks({ dataTransfer })).toBe(true);
    expect(draggedTracks({ dataTransfer })).toEqual(tracks);
    expect(dataTransfer.data['text/plain']).toBe('Band - Eins');
    expect(carriesTracks({ dataTransfer: { types: ['Files'] } })).toBe(false);
    expect(TRACKS_MIME).toMatch(/^application\//);
  });

  it('legt in der oberen Hälfte davor ab, in der unteren dahinter', () => {
    const row = { getBoundingClientRect: () => ({ top: 100, height: 40 }) };
    expect(dropIndex({ currentTarget: row, clientY: 110 }, 3)).toBe(3);
    expect(dropIndex({ currentTarget: row, clientY: 130 }, 3)).toBe(4);
  });

  it('rechnet beim Verschieben nach unten die eigene Lücke heraus', () => {
    expect(moveTarget(0, 3)).toBe(2);
    expect(moveTarget(3, 0)).toBe(0);
    expect(moveTarget(2, 2)).toBe(2);
  });
});

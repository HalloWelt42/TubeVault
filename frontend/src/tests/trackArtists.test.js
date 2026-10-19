// Die Genannten eines Musiktitels: jeder für sich ein Verweis, die Angabe
// bleibt, wie sie im Tag steht (utils/trackArtists.js).
import { describe, it, expect } from 'vitest';
import { artistRefs, artistSegments } from '../lib/utils/trackArtists.js';

const ref = (name) => ({ name, source: `artist:${name.toLowerCase()}` });

describe('Genannte eines Titels', () => {
  it('zerlegt die Angabe in Verweise und den Text dazwischen', () => {
    const track = { artist: '50 Cent, Nate Dogg', artists: [ref('50 Cent'), ref('Nate Dogg')] };
    expect(artistSegments(track)).toEqual([
      { text: '50 Cent', source: 'artist:50 cent' }, { text: ', ' }, { text: 'Nate Dogg', source: 'artist:nate dogg' }]);
  });

  it('behält feat. und eine ganze Band, wie sie dastehen', () => {
    const track = { artist: 'Earth, Wind & Fire feat. The Emotions', artists: [ref('Earth, Wind & Fire'), ref('The Emotions')] };
    expect(artistSegments(track).map((s) => s.text).join('')).toBe(track.artist);
    expect(artistSegments(track).filter((s) => s.source).map((s) => s.text)).toEqual(['Earth, Wind & Fire', 'The Emotions']);
  });

  it('kennt Titel aus einer älteren gemerkten Warteschlange (nur artist_source)', () => {
    const old = { artist: 'ABBA', artist_source: 'artist:abba' };
    expect(artistRefs(old)).toEqual([{ name: 'ABBA', source: 'artist:abba' }]);
    expect(artistSegments({ artist: 'ABBA' })).toEqual([{ text: 'ABBA' }]);
  });

  it('nennt alle Genannten, auch wenn einer nicht in der Angabe steht', () => {
    const track = { artist: 'Irgendwas', artists: [ref('A'), ref('B')] };
    expect(artistSegments(track)).toEqual([{ text: 'A', source: 'artist:a' }, { text: ', ' }, { text: 'B', source: 'artist:b' }]);
  });
});

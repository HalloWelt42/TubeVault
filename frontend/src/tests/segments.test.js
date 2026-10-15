import { describe, expect, it } from 'vitest';
import { nextSegmentStart, previousSegmentStart, segmentIndexAt, toSegments } from '../lib/utils/segments.js';

// Echte Titelliste eines Mixes (Anfang), Länge gekürzt
const KAPITEL = [
  { start_time: 270, title: 'David Moleon - Soma [Unrilis]' },
  { start_time: 0, title: "Jack's Trip - Tool Bag [Unrilis]" },
  { start_time: 397, title: 'MX - Let Me Tell You' },
  { start_time: 600, title: 'Erik Yahnkovf - Number One' },
];

describe('Segmente eines Musiktitels', () => {
  const segments = toSegments(KAPITEL, 720);

  it('ordnet die Kapitel und schließt jedes am nächsten ab', () => {
    expect(segments.map((s) => [s.start, s.end])).toEqual([[0, 270], [270, 397], [397, 600], [600, 720]]);
    expect(segments[0].title).toBe("Jack's Trip - Tool Bag [Unrilis]");
  });

  it('ein einzelnes Kapitel ist kein Segment', () => {
    expect(toSegments([{ start_time: 0, title: 'Intro' }], 300)).toEqual([]);
    expect(toSegments([], 300)).toEqual([]);
  });

  it('findet das laufende Segment', () => {
    expect(segmentIndexAt(segments, 0)).toBe(0);
    expect(segmentIndexAt(segments, 269.9)).toBe(1);   // knapp davor zählt schon (Sprungziel)
    expect(segmentIndexAt(segments, 500)).toBe(2);
  });

  it('Weiter springt zum nächsten Segment, nach dem letzten kommt der nächste Titel', () => {
    expect(nextSegmentStart(segments, 10)).toBe(270);
    expect(nextSegmentStart(segments, 610)).toBeNull();
  });

  it('Zurück: erst an den Anfang des Segments, kurz danach ins vorige', () => {
    expect(previousSegmentStart(segments, 420)).toBe(397);
    expect(previousSegmentStart(segments, 398)).toBe(270);
    expect(previousSegmentStart(segments, 1)).toBeNull();
  });
});

/**
 * TubeVault – Abschnitte innerhalb eines Musiktitels
 *
 * Hat ein Musikvideo eigene Abschnitte (die Kapitel eines Mixes, also seine
 * Titelliste), sind sie anspringbare Segmente (Wunsch 15.10.2026): Weiter und
 * Zurück gehen zuerst durch die Abschnitte, erst danach beginnt der nächste
 * Titel. Reine Rechnungen; genutzt vom Musikspieler und den Zeitleisten,
 * getestet in tests/segments.test.js.
 */
export const MIN_SEGMENTS = 2;     // ein einzelner Abschnitt ist keiner

/** Kapitel ({ start_time, end_time, title }) zu Segmenten { start, end, title }; [] wenn es keine sind */
export function toSegments(chapters, duration = 0) {
  const sorted = (chapters || [])
    .filter((c) => Number.isFinite(Number(c.start_time)))
    .map((c) => ({ start: Math.max(0, Number(c.start_time)), title: (c.title || '').trim() }))
    .sort((a, b) => a.start - b.start);
  const segments = sorted
    .map((s, i) => ({ ...s, end: i + 1 < sorted.length ? sorted[i + 1].start : (duration || s.start) }))
    .filter((s, i, all) => s.end > s.start || (i === all.length - 1 && !duration));
  return segments.length >= MIN_SEGMENTS ? segments : [];
}

/** Index des Segments, in dem die Stelle liegt; -1 vor dem ersten oder ohne Segmente */
export function segmentIndexAt(segments, time) {
  let found = -1;
  for (let i = 0; i < segments.length; i++) {
    if (time + 0.25 >= segments[i].start) found = i; else break;
  }
  return found;
}

/** Beginn des nächsten Segments oder null (dann folgt der nächste Titel) */
export function nextSegmentStart(segments, time) {
  const next = segments[segmentIndexAt(segments, time) + 1];
  return next ? next.start : null;
}

/** Ziel von "Zurück": Anfang des laufenden Segments, kurz nach dessen Beginn das vorige; null vor dem ersten */
export function previousSegmentStart(segments, time, restartAfter = 3) {
  const index = segmentIndexAt(segments, time);
  if (index < 0) return null;
  if (time - segments[index].start > restartAfter) return segments[index].start;
  return index > 0 ? segments[index - 1].start : null;
}

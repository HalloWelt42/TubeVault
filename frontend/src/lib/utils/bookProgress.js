// Hörbücher: Gesamtstand über alle Teile und welches Buch "Weiterhören" zeigt.

const sum = (values) => values.reduce((total, value) => total + value, 0);

/**
 * Stand über alle Teile: gehört und gesamt in Sekunden Ton, Rest in echter
 * Hörzeit (beim Tempo 1,5 dauert eine Stunde Ton 40 Minuten), Anteil 0..1.
 *   parts  Teile in Reihenfolge ({ duration } in Sekunden)
 *   index  laufender Teil, time  Stelle darin
 */
export function bookProgress(parts, index, time, rate = 1) {
  const durations = (parts || []).map((part) => Math.max(0, part?.duration || 0));
  const total = sum(durations);
  const heard = Math.min(total, sum(durations.slice(0, Math.max(0, index))) + Math.max(0, time || 0));
  return { heard, total, left: (total - heard) / (rate > 0 ? rate : 1), fraction: total ? heard / total : 0 };
}

/** Das zuletzt gehörte, nicht fertige Hörbuch (die Liste kommt zuletzt gehörte zuerst), sonst null */
export function bookToResume(books) {
  return (books || []).find((book) => book.current_part && !book.finished) || null;
}

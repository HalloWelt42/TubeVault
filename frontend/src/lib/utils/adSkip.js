// Werbestellen eines Videos: ein Ort für alle Abspieler (Wiedergabe, Mobil,
// Mini-Player) und die Untertitel-Anzeigen. Welche Abschnitte als Werbung
// gelten, entscheidet das Backend (skip_ranges, zusammengefasst und sortiert);
// beim Abruf gleicht es die Marken vorher ab, wenn es Zeit ist.
import { api } from '../api/client.js';

// Kurz vor dem Ende einer Werbestelle nicht mehr springen - sonst springt
// der Abspieler wegen Rundung an dieselbe Stelle immer wieder
const END_TOLERANCE_S = 0.3;

/** Werbestellen [[start, ende], ...] eines Videos; ohne Antwort keine. */
export async function loadSkipRanges(videoId) {
  try {
    const res = await api.getAdMarkers(videoId);
    return res.skip_ranges || [];
  } catch {
    return [];
  }
}

/** Wohin gesprungen werden muss, wenn t in einer Werbestelle liegt (sonst null).
 *  Reicht eine Stelle bis ans Ende (typisch für den Abspann), endet sie am
 *  Videoende - sonst spränge der Abspieler dort immer wieder hin. */
export function skipTarget(t, ranges, duration = Infinity) {
  const videoEnd = Number.isFinite(duration) && duration > 0 ? duration : Infinity;
  for (const [start, end] of ranges) {
    const stop = Math.min(end, videoEnd);
    if (t >= start && t < stop - END_TOLERANCE_S) return stop;
  }
  return null;
}

/** Untertitel ohne die, deren Mitte in einer Werbestelle liegt (wie im Backend). */
export function withoutAds(cues, ranges) {
  if (!ranges.length) return cues;
  return cues.filter(cue => {
    const middle = (cue.start + cue.end) / 2;
    return !ranges.some(([start, end]) => middle >= start && middle < end);
  });
}

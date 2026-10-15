// Tempo der Wiedergabe (Hörbücher): die wählbaren Stufen und ihre Anzeige.

export const PLAYBACK_RATES = [0.75, 1, 1.25, 1.5, 1.75, 2];

const MIN_RATE = 0.5;
const MAX_RATE = 3;

/** Gültiges Tempo (auf Hundertstel), sonst 1 */
export function normalizeRate(value) {
  const rate = Number(value);
  if (!Number.isFinite(rate) || rate < MIN_RATE || rate > MAX_RATE) return 1;
  return Math.round(rate * 100) / 100;
}

/** "1,0", "1,25", "0,75" */
export const formatRate = (rate) =>
  normalizeRate(rate).toLocaleString('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 2 });

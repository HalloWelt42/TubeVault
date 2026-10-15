// Schlaf-Zeitgeber des Musikspielers: hält nach dem laufenden Titel (bei
// Hörbüchern: Teil) oder nach einigen Minuten Hörzeit an. Hier stehen nur
// die Rechnungen; den Zustand hält der Spieler (stores/musicPlayer.svelte.js).
//
// Zustand: null (aus) | { kind: 'track' } | { kind: 'minutes', minutes, left, endsAt }
//   left    verbleibende Millisekunden, solange die Wiedergabe ruht
//   endsAt  Zeitpunkt (ms) des Anhaltens, solange sie läuft, sonst null
// Minuten zählen nur, solange etwas läuft: eine Pause hält die Uhr an.

export const SLEEP_MINUTES = [15, 30, 45, 60];

export const afterTrack = () => ({ kind: 'track' });

export function afterMinutes(minutes, now, running) {
  const left = minutes * 60000;
  return { kind: 'minutes', minutes, left, endsAt: running ? now + left : null };
}

/** Millisekunden bis zum Anhalten; null, wenn nicht nach Minuten gezählt wird */
export function remainingMs(timer, now) {
  if (timer?.kind !== 'minutes') return null;
  return Math.max(0, timer.endsAt === null ? timer.left : timer.endsAt - now);
}

/** Wiedergabe ruht: die Uhr anhalten */
export function frozen(timer, now) {
  if (timer?.kind !== 'minutes' || timer.endsAt === null) return timer;
  return { ...timer, left: remainingMs(timer, now), endsAt: null };
}

/** Wiedergabe läuft: die Uhr weiterlaufen lassen */
export function running(timer, now) {
  if (timer?.kind !== 'minutes' || timer.endsAt !== null) return timer;
  return { ...timer, endsAt: now + timer.left };
}

export const isDue = (timer, now) => timer?.kind === 'minutes' && remainingMs(timer, now) === 0;

/** Anzeige am Knopf: "Einschlafen", "Aus nach Teil 7", "Aus nach diesem Titel", "Aus in 12 Min." */
export function sleepLabel(timer, leftMs, part = null) {
  if (!timer) return 'Einschlafen';
  if (timer.kind === 'track') return part ? `Aus nach Teil ${part}` : 'Aus nach diesem Titel';
  const ms = Math.max(0, leftMs ?? timer.left ?? 0);
  if (ms < 60000) return `Aus in ${Math.ceil(ms / 1000)} s`;
  return `Aus in ${Math.ceil(ms / 60000)} Min.`;
}

/**
 * TubeVault – Änderungen an der Musik melden
 *
 * Wer Titel herausnimmt oder zurückholt (Spieler, Menü, Bereich
 * "Ausgeblendet"), meldet es hier; Musikseite am Rechner und am Handy
 * frischen sich daraufhin auf, gleich wo die Änderung geschah.
 *
 *   emitMusicChange(change)            change hat eine oder mehrere Angaben:
 *     removed: ['f0123...']            diese Titel sofort aus allen Listen nehmen
 *     removedAlbums: ['album:...']     ebenso alle Titel dieser Alben
 *     reload: true                     Zahlen und Gruppen beim Server neu holen
 *     restored: true                   etwas kam zurück: auch einfache Listen neu holen
 *   onMusicChange((change) => ...)     gibt die Abmeldung zurück
 *   isRemoved(change)(track)           trifft ein Titel die Meldung?
 */
const EVENT = 'tubevault:musik-geaendert';

export function emitMusicChange(change) {
  window.dispatchEvent(new CustomEvent(EVENT, { detail: change }));
}

export const isRemoved = (change) => (track) =>
  !!change.removed?.includes(track.id) || (!!track.album_source && !!change.removedAlbums?.includes(track.album_source));

export function onMusicChange(handler) {
  const wrapped = (e) => handler(e.detail);
  window.addEventListener(EVENT, wrapped);
  return () => window.removeEventListener(EVENT, wrapped);
}

/**
 * TubeVault – Musiktitel ziehen und ablegen
 *
 * Die Titelquelle des Listen-Baukastens gibt beim Ziehen die Titel mit,
 * die Liste nimmt sie an. Während des Ziehens verrät der Browser nur die
 * Art der Fracht (types), erst beim Ablegen den Inhalt.
 */
export const TRACKS_MIME = 'application/x-tubevault-titel';

export function setDraggedTracks(event, tracks) {
  event.dataTransfer.setData(TRACKS_MIME, JSON.stringify(tracks));
  event.dataTransfer.setData('text/plain', tracks.map((t) => `${t.artist} - ${t.title}`).join('\n'));
  event.dataTransfer.effectAllowed = 'copy';
}

export const carriesTracks = (event) => !!event.dataTransfer?.types?.includes(TRACKS_MIME);

export function draggedTracks(event) {
  try { return JSON.parse(event.dataTransfer.getData(TRACKS_MIME) || '[]'); } catch { return []; }
}

/** Ablagestelle über einer Zeile: obere Hälfte davor, untere dahinter */
export function dropIndex(event, index) {
  const box = event.currentTarget.getBoundingClientRect();
  return event.clientY < box.top + box.height / 2 ? index : index + 1;
}

/** Ziel nach dem Herausnehmen von from (beim Verschieben innerhalb der Liste) */
export const moveTarget = (from, at) => (from < at ? at - 1 : at);

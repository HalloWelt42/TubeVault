/**
 * TubeVault – Aus der Musik herausnehmen und zurückholen
 *
 * Eine Stelle für Rechner und Handy: Titel der Sammlung ausblenden, ganze
 * Alben ausschließen, beides im Bereich "Ausgeblendet" zurückholen (einzeln
 * oder mehrere). Was herausfällt, verlässt auch die Warteschlange; alle
 * Listen erfahren es über utils/musicChanges.js.
 */
import { api } from '../api/client.js';
import { musicPlayer } from '../stores/musicPlayer.svelte.js';
import { emitMusicChange } from './musicChanges.js';

/** Titel der eigenen Sammlung ausblenden (die Datei bleibt unberührt) */
export async function hideTrack(track) {
  await api.musicFileHidden(track.id, true);
  musicPlayer.dropWhere((t) => t.id === track.id);
  emitMusicChange({ removed: [track.id], reload: true });
}

/** Ganzes Album ausschließen, auch was später dazukommt; liefert den Eintrag ({ source, name, ... }) */
export async function excludeAlbum(source) {
  const entry = await api.musicExclude(source);
  musicPlayer.dropWhere((t) => t.album_source === source);
  emitMusicChange({ removedAlbums: [source], reload: true });
  return entry;
}

/** Ausgeblendete Titel (Kennungen) und ausgeschlossene Alben (Gruppen) zurückholen */
export async function restoreHidden({ tracks = [], albums = [] }) {
  const result = await api.musicRestoreHidden({ tracks, albums });
  emitMusicChange({ restored: true, reload: true });
  return result;
}

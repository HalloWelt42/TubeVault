/**
 * TubeVault – Aus der Musik herausnehmen und zurückholen
 *
 * Eine Stelle für Rechner und Handy: Titel ausblenden (Minus-Knopf, Menü;
 * Dateien wie Videos), ganze Alben ausschließen, beides im Bereich
 * "Ausgeblendet" zurückholen (einzeln oder mehrere). Gelöscht wird nichts.
 * Was herausfällt, verlässt auch die Warteschlange; alle Listen erfahren es
 * über utils/musicChanges.js, der Server lässt es überall weg.
 */
import { api } from '../api/client.js';
import { musicPlayer, UNDO_MS } from '../stores/musicPlayer.svelte.js';
import { toast } from '../stores/notifications.js';
import { setHidden } from './musicTrack.js';
import { emitMusicChange } from './musicChanges.js';

/** Titel aus der ganzen Musik nehmen. Er verlässt sofort die Warteschlange
 *  (läuft er, geht es weiter); kurz lässt er sich zurückholen, dann auch
 *  wieder an seine Stelle in der Warteschlange. Liefert dieses Rückgängig
 *  (z.B. für die Fernbedienung, die es von einem anderen Gerät auslöst). */
export async function hideTrack(track) {
  await setHidden(track, true);
  const putBack = musicPlayer.takeOut(track);
  emitMusicChange({ removed: [track.id], reload: true });
  const undo = () => undoHide(track, putBack);
  toast.undo(`Ausgeblendet: ${track.title}`, undo, UNDO_MS);
  return undo;
}

async function undoHide(track, putBack) {
  try {
    await restoreHidden({ tracks: [track.id] });
    putBack();
  } catch (e) { toast.error(e.message); }
}

/** Ganzes Album ausschließen, auch was später dazukommt; liefert den Eintrag ({ source, name, ... }) */
export async function excludeAlbum(source) {
  const entry = await api.musicExclude(source);
  musicPlayer.dropWhere((t) => t.album_source === source);
  emitMusicChange({ removedAlbums: [source], reload: true });
  return entry;
}

/** Ausgeblendete Titel (Kennungen von Dateien und Videos) und ausgeschlossene Alben (Gruppen) zurückholen */
export async function restoreHidden({ tracks = [], albums = [] }) {
  const result = await api.musicRestoreHidden({ tracks, albums });
  emitMusicChange({ restored: true, reload: true });
  return result;
}

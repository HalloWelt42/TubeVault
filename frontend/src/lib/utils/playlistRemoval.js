// TubeVault – Das laufende Video aus seiner Playlist nehmen
//
// Minus der Fernbedienung bei einem Video aus einer Playlist (Wunsch
// 19.10.2026): nur die Playlist verliert es, das Video bleibt in der
// Bibliothek, die Wiedergabe springt zum nächsten. Kurz rückgängig zu
// machen; dann steht es wieder genau an seiner Stelle. Rechner (Watch) und
// Handy (Video) nutzen diese eine Stelle.
import { api } from '../api/client.js';
import { UNDO_MS } from '../stores/musicPlayer.svelte.js';
import { toast } from '../stores/notifications.js';

/** Herausnehmen, weiter (next), Hinweis mit Rückgängig; liefert das Rückgängig */
export async function removeFromPlaylist(listId, video, next) {
  const { ids: before } = await api.playlistEntries(listId);
  await api.removeFromPlaylist(listId, video.id);
  next();
  const undo = async () => {
    try {
      await api.addToPlaylist(listId, video.id);
      await api.reorderPlaylist(listId, before);
    } catch (e) { toast.error(e.message); }
  };
  toast.undo(`Aus der Playlist genommen: ${video.title}`, undo, UNDO_MS);
  return undo;
}

/** Kennung der Playlist einer Quelle wie "playlist:12"; andere Sammlungen (Favoriten, Kategorien) haben keine */
export const playlistIdOf = (source) => (source?.startsWith('playlist:') ? source.slice('playlist:'.length) : null);

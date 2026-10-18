// TubeVault – Wiedergabeliste umbenennen
//
// Eine Stelle für Rechner (Listen-Baukasten) und Handy (Playlist): Namen
// prüfen, beim Server speichern und melden. Listenübersichten frischen sich
// daraufhin auf (onPlaylistRenamed), die Musik über utils/musicChanges.js.
import { api } from '../api/client.js';
import { emitMusicChange } from './musicChanges.js';

const EVENT = 'tubevault:liste-umbenannt';
export const EMPTY_NAME = 'Der Name darf nicht leer sein';

/** Neuer Name ohne Ränder; leer: Fehler mit Hinweis (gespeichert wird dann nichts) */
export async function renamePlaylist(id, name) {
  const clean = (name || '').trim();
  if (!clean) throw new Error(EMPTY_NAME);
  await api.updatePlaylist(id, { name: clean });
  window.dispatchEvent(new CustomEvent(EVENT, { detail: { id: String(id), name: clean } }));
  emitMusicChange({ reload: true });
  return clean;
}

/** handler({ id, name }) nach jedem Umbenennen; gibt die Abmeldung zurück */
export function onPlaylistRenamed(handler) {
  const wrapped = (e) => handler(e.detail);
  window.addEventListener(EVENT, wrapped);
  return () => window.removeEventListener(EVENT, wrapped);
}

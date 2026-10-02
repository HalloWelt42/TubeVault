/**
 * TubeVault – Abspielfolge einer Playlist (Mobil)
 * Lädt die Playlist einmal und liefert die Reihenfolge, in der gespielt wird:
 * wie gespeichert oder gemischt. Die gemischte Folge bleibt für die Dauer
 * der Sitzung gleich, damit "weiter" und "zurück" verlässlich sind.
 */
import { api } from '../lib/api/client.js';

const cache = new Map();   // "id|zufall" -> { id, name, videos }

function shuffled(items) {
  const result = [...items];
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}

/** Abspielfolge holen: { id, name, videos: [{ id, title, channel_name, duration }] } */
export async function loadQueue(listId, shuffle = false) {
  const key = `${listId}|${shuffle ? 1 : 0}`;
  if (!cache.has(key)) {
    const playlist = await api.getPlaylist(listId);
    const playable = (playlist.videos || []).filter(v => v.status === 'ready');
    cache.set(key, { id: playlist.id, name: playlist.name, videos: shuffle ? shuffled(playable) : playable });
  }
  return cache.get(key);
}

/** Eine neue gemischte Folge erzwingen (beim Start von "Zufällig"). */
export function forgetQueue(listId) {
  cache.delete(`${listId}|1`);
}

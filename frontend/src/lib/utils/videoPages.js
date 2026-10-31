/**
 * TubeVault – Seiten der Videoliste für den Listen-Lader (listLoader).
 *
 * Die eine Stelle, die /api/videos seitenweise abfragt: die erste Seite (oder
 * ein Sprung) über page, jede weitere über den Cursor der vorigen (after), den
 * die Schnittstelle als next_cursor liefert. Ob danach noch etwas kommt, sagt
 * allein der Cursor, nicht ein Vergleich mit total (der sich beim Archivieren
 * ändert).
 *
 *   const list = createListLoader((page, after) => videoPage({ ...filter }, page, after));
 *
 * Liefert { items, total, hasMore, next, result } - result ist die ganze
 * Antwort (für Gesamtgröße, Sprachzähler usw.).
 */
import { api } from '../api/client.js';

export async function videoPage(params, page, after) {
  const result = await api.getVideos({ ...params, page, ...(after ? { after } : {}) });
  return {
    items: result.videos || [],
    total: result.total || 0,
    hasMore: !!result.next_cursor,
    next: result.next_cursor || null,
    result,
  };
}

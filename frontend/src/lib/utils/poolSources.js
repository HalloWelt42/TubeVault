// TubeVault – Quellen der Titelquelle im Listen-Baukasten
//
// Links im Baukasten (TrackPool) wählt man, woraus die Titel kommen
// (Wunsch 19.10.2026: gezielt aus Alben, Interpreten und anderen Listen):
//   paged   alle Titel bzw. die Lieblingssongs, seitenweise vom Server
//           (/api/music/tracks), mit Suche, Herkunft und Sortierung
//   groups  erst die Gruppen (Alben, Interpreten, Wiedergabelisten), eine
//           geöffnete Gruppe zeigt ihre Titel (/api/music/play)
//   fixed   eine feste Liste (Verlauf, /api/music/play)
// Hier stehen die Quellen und was beim Übernehmen in die Liste gilt.
import { api } from '../api/client.js';

export const POOL_SOURCES = [
  { id: 'titel', label: 'Alle Titel', icon: 'fa-music', paged: true },
  { id: 'alben', label: 'Alben', icon: 'fa-compact-disc', groups: () => api.musicAlbums(), search: 'Album suchen' },
  { id: 'interpreten', label: 'Interpreten', icon: 'fa-microphone', groups: () => api.musicArtists(), search: 'Interpret suchen' },
  { id: 'lieblingssongs', label: 'Lieblingssongs', icon: 'fa-heart', paged: true, favorites: true },
  { id: 'listen', label: 'Wiedergabelisten', icon: 'fa-list-ul', groups: () => api.musicPlaylists(), search: 'Liste suchen' },
  { id: 'verlauf', label: 'Verlauf', icon: 'fa-clock-rotate-left', fixed: 'recent' },
];

export const sourceById = (id) => POOL_SOURCES.find((s) => s.id === id) || POOL_SOURCES[0];

const words = (query) => (query || '').toLocaleLowerCase('de').split(/\s+/).filter(Boolean);

/** Titel, deren Titel, Interpret oder Album alle Suchwörter enthält */
export function filterTracks(tracks, query) {
  const wanted = words(query);
  if (!wanted.length) return tracks;
  return tracks.filter((t) => {
    const text = `${t.title} ${t.artist} ${t.album || ''}`.toLocaleLowerCase('de');
    return wanted.every((w) => text.includes(w));
  });
}

/** Gruppen, deren Name oder Unterzeile alle Suchwörter enthält */
export function filterGroups(groups, query) {
  const wanted = words(query);
  if (!wanted.length) return groups;
  return groups.filter((g) => {
    const text = `${g.name} ${g.subtitle || ''}`.toLocaleLowerCase('de');
    return wanted.every((w) => text.includes(w));
  });
}

/** Was von tracks in die Liste kommt: in ihrer Reihenfolge, ohne was schon
 *  darin steht (inList: Kennungen) und ohne Doppel; skipped zählt den Rest. */
export function planAdd(tracks, inList) {
  const seen = new Set(inList);
  const fresh = [];
  for (const track of tracks) {
    if (seen.has(track.id)) continue;
    seen.add(track.id);
    fresh.push(track);
  }
  return { fresh, skipped: tracks.length - fresh.length };
}

/** Hinweis nach "Alle hinzufügen" */
export function addedText({ fresh, skipped }) {
  if (!fresh.length) return skipped === 1 ? 'Steht schon in der Liste' : 'Alle stehen schon in der Liste';
  const added = `${fresh.length.toLocaleString('de-DE')} Titel hinzugefügt`;
  if (!skipped) return added;
  return `${added}, ${skipped.toLocaleString('de-DE')} ${skipped === 1 ? 'stand' : 'standen'} schon drin`;
}

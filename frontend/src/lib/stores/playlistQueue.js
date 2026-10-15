/**
 * TubeVault - Warteschlange der Videowiedergabe
 * Eine Reihe von Videos, die nacheinander laufen (Playlist, Favoriten, Feed,
 * Kanal ...). Die Quelle (z.B. "playlist:59", "favorites:Standard") erlaubt
 * es, die Warteschlange nach dem Neuladen der Seite wiederherzustellen;
 * ohne Quelle gilt sie nur bis dahin.
 * © HalloWelt42 – Private Nutzung
 */
import { writable, get } from 'svelte/store';

const EMPTY = {
  active: false,
  source: null,         // Sammlung, aus der die Reihe stammt (oder null)
  playlistId: null,     // Kennung, wenn die Quelle eine Playlist ist
  playlistName: '',     // Anzeigename der Reihe
  videos: [],           // [{ id, title, channel_name, duration, ... }]
  currentIndex: 0,
  resume: false,        // an der gemerkten Stelle fortsetzen statt von vorn
  repeat: false,        // nach dem letzten Video wieder von vorn
};

export const playlistQueue = writable({ ...EMPTY });

/** Quelle vereinheitlichen: eine Zahl ist eine Playlist (ältere Aufrufe und Adressen). */
export function queueSource(source) {
  if (source === null || source === undefined || source === '') return null;
  return /^\d+$/.test(String(source)) ? `playlist:${source}` : String(source);
}

/**
 * Warteschlange starten.
 *   source   Quelle (siehe queueSource) oder null
 *   options  { resume, repeat }
 */
export function startQueue(source, name, videos, startIndex = 0, { resume = false, repeat = false } = {}) {
  const normalized = queueSource(source);
  playlistQueue.set({
    active: true,
    source: normalized,
    playlistId: normalized?.startsWith('playlist:') ? Number(normalized.slice(9)) : null,
    playlistName: name,
    videos,
    currentIndex: Math.max(0, Math.min(startIndex, videos.length - 1)),
    resume,
    repeat,
  });
}

export function stopQueue() {
  playlistQueue.set({ ...EMPTY });
}

/** Nächstes Video (bei "Wiederholen" nach dem letzten wieder das erste); null am Ende. */
export function nextInQueue() {
  const q = get(playlistQueue);
  if (!q.active || !q.videos.length) return null;
  let nextIdx = q.currentIndex + 1;
  if (nextIdx >= q.videos.length) {
    if (!q.repeat) return null;
    nextIdx = 0;
  }
  playlistQueue.update(s => ({ ...s, currentIndex: nextIdx }));
  return q.videos[nextIdx]?.id || null;
}

export function prevInQueue() {
  const q = get(playlistQueue);
  if (!q.active || q.currentIndex <= 0) return null;
  const prevIdx = q.currentIndex - 1;
  playlistQueue.update(s => ({ ...s, currentIndex: prevIdx }));
  return q.videos[prevIdx]?.id || null;
}

export function playAtIndex(index) {
  const q = get(playlistQueue);
  if (!q.active || index < 0 || index >= q.videos.length) return null;
  playlistQueue.update(s => ({ ...s, currentIndex: index }));
  return q.videos[index]?.id || null;
}

export function hasNext() {
  const q = get(playlistQueue);
  return q.active && q.videos.length > 0 && (q.repeat || q.currentIndex < q.videos.length - 1);
}

export function hasPrev() {
  const q = get(playlistQueue);
  return q.active && q.currentIndex > 0;
}

/** Video direkt nach dem laufenden einreihen (nur bei aktiver Warteschlange). */
export function queueNext(video) {
  playlistQueue.update(s => {
    if (!s.active) return s;
    const videos = s.videos.filter((v, i) => v.id !== video.id || i === s.currentIndex);
    const current = videos.findIndex(v => v.id === s.videos[s.currentIndex]?.id);
    videos.splice(current + 1, 0, video);
    return { ...s, videos, currentIndex: current };
  });
}

/** Video ans Ende der Warteschlange stellen (nur bei aktiver Warteschlange). */
export function queueAppend(video) {
  playlistQueue.update(s => {
    if (!s.active || s.videos.some(v => v.id === video.id)) return s;
    return { ...s, videos: [...s.videos, video] };
  });
}

export function setRepeat(repeat) {
  playlistQueue.update(s => ({ ...s, repeat }));
}

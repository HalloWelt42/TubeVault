/**
 * TubeVault -  Playlist Queue Store v1.5.91
 * Verwaltet die aktuelle Wiedergabe-Queue (Playlist → Autoplay nächstes Video).
 * © HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
 * SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
 */
import { writable, get } from 'svelte/store';

// Queue-State
export const playlistQueue = writable({
  active: false,        // Queue aktiv?
  playlistId: null,     // Playlist-ID
  playlistName: '',     // Playlist-Name
  videos: [],           // Video-Liste [{ id, title, channel_name, duration, ... }]
  currentIndex: 0,      // Aktueller Index in der Liste
});

/**
 * Queue starten: Playlist laden und erstes (oder gewähltes) Video abspielen.
 */
export function startQueue(playlistId, playlistName, videos, startIndex = 0) {
  playlistQueue.set({
    active: true,
    playlistId,
    playlistName,
    videos,
    currentIndex: Math.max(0, Math.min(startIndex, videos.length - 1)),
  });
}

/**
 * Queue stoppen.
 */
export function stopQueue() {
  playlistQueue.set({ active: false, playlistId: null, playlistName: '', videos: [], currentIndex: 0 });
}

/**
 * Nächstes Video in der Queue. Gibt video_id zurück oder null wenn am Ende.
 */
export function nextInQueue() {
  const q = get(playlistQueue);
  if (!q.active || q.currentIndex >= q.videos.length - 1) return null;
  const nextIdx = q.currentIndex + 1;
  playlistQueue.update(s => ({ ...s, currentIndex: nextIdx }));
  return q.videos[nextIdx]?.id || null;
}

/**
 * Vorheriges Video in der Queue.
 */
export function prevInQueue() {
  const q = get(playlistQueue);
  if (!q.active || q.currentIndex <= 0) return null;
  const prevIdx = q.currentIndex - 1;
  playlistQueue.update(s => ({ ...s, currentIndex: prevIdx }));
  return q.videos[prevIdx]?.id || null;
}

/**
 * Video an bestimmtem Index abspielen.
 */
export function playAtIndex(index) {
  const q = get(playlistQueue);
  if (!q.active || index < 0 || index >= q.videos.length) return null;
  playlistQueue.update(s => ({ ...s, currentIndex: index }));
  return q.videos[index]?.id || null;
}

/**
 * Prüfen ob es ein nächstes Video gibt.
 */
export function hasNext() {
  const q = get(playlistQueue);
  return q.active && q.currentIndex < q.videos.length - 1;
}

export function hasPrev() {
  const q = get(playlistQueue);
  return q.active && q.currentIndex > 0;
}

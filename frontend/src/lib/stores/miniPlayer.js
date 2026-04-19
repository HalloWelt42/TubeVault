/**
 * TubeVault – Mini-Player Store v1.8.72
 * Persistente Wiedergabe: Video läuft weiter wenn Watch-Seite verlassen wird.
 * © HalloWelt42 – Private Nutzung
 */
import { writable, get } from 'svelte/store';

export const miniPlayer = writable({
  active: false,
  videoId: null,
  title: '',
  channelName: '',
  currentTime: 0,
  duration: 0,
  volume: 0.8,
  isPlaying: false,
  audioOnly: false,
  thumbnailUrl: null,
});

/**
 * Mini-Player aktivieren: beim Verlassen der Watch-Seite.
 */
export function activateMiniPlayer({ videoId, title, channelName, currentTime, duration, volume, isPlaying, audioOnly, thumbnailUrl }) {
  miniPlayer.set({
    active: true,
    videoId,
    title: title || videoId,
    channelName: channelName || '',
    currentTime: currentTime || 0,
    duration: duration || 0,
    volume: volume ?? 0.8,
    isPlaying: isPlaying ?? true,
    audioOnly: audioOnly ?? false,
    thumbnailUrl: thumbnailUrl || null,
  });
}

/**
 * Mini-Player deaktivieren (z.B. wenn zurück zu Watch navigiert wird).
 */
export function deactivateMiniPlayer() {
  miniPlayer.set({
    active: false,
    videoId: null,
    title: '',
    channelName: '',
    currentTime: 0,
    duration: 0,
    volume: 0.8,
    isPlaying: false,
    audioOnly: false,
    thumbnailUrl: null,
  });
}

/**
 * Aktuellen Zustand lesen (für Watch.svelte beim Zurückkehren).
 */
export function getMiniPlayerState() {
  return get(miniPlayer);
}

/**
 * Time-Update vom MiniPlayer-Video-Element.
 */
export function updateMiniPlayerTime(currentTime) {
  miniPlayer.update(s => ({ ...s, currentTime }));
}

/**
 * TubeVault – Quick Playlist Store v1.6.0
 * Speichert die "gepinnte" Playlist für One-Click-Hinzufügen.
 * © HalloWelt42 – Private Nutzung
 */
import { writable, get } from 'svelte/store';

const STORAGE_KEY = 'tv_quick_playlist';

function loadQuickPlaylist() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch { /* */ }
  return null; // { id: number, name: string }
}

export const quickPlaylist = writable(loadQuickPlaylist());

// Persist on change
quickPlaylist.subscribe(val => {
  if (val) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(val));
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
});

export function pinPlaylist(id, name) {
  quickPlaylist.set({ id, name });
}

export function unpinPlaylist() {
  quickPlaylist.set(null);
}

export function getQuickPlaylist() {
  return get(quickPlaylist);
}

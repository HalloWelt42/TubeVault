/**
 * TubeVault – Video-Mutations-Event-Bus
 *
 * Zentrale Utility: Komponenten wie Watch.svelte senden nach Archive/Delete/Upgrade
 * ein Event `tubevault:video-mutated`. Listen-Komponenten (Library, Archives,
 * Dashboard, Favorites, History, ChannelDetail) können sich anmelden und
 * sich beim Navigieren-zurück frisch halten.
 *
 * Verwendung:
 *   // In einer Listen-Komponente:
 *   onVideoMutation(() => loadVideos(true));  // gibt cleanup-Fn zurück
 *
 *   // Mutations-Emitter:
 *   emitVideoMutation(id, 'archived' | 'unarchived' | 'deleted' | 'upgraded');
 */

const EVENT = 'tubevault:video-mutated';

export function emitVideoMutation(id, action, extra = {}) {
  window.dispatchEvent(new CustomEvent(EVENT, { detail: { id, action, ...extra } }));
}

/**
 * Registriert einen Listener. Gibt eine Cleanup-Funktion zurück, die den
 * Listener wieder entfernt — passt perfekt in Svelte 5 $effect-Returns.
 *
 * @param {(detail: {id: string, action: string}) => void} handler
 * @returns {() => void}
 */
export function onVideoMutation(handler) {
  const wrapped = (e) => handler(e.detail);
  window.addEventListener(EVENT, wrapped);
  return () => window.removeEventListener(EVENT, wrapped);
}

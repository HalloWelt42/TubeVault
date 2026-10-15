/**
 * TubeVault – Notifications Store v1.5.52
 * Toast-Benachrichtigungen (keine Browser-Popups!)
 * © HalloWelt42
 */

import { writable } from 'svelte/store';

function createNotificationStore() {
  const { subscribe, update } = writable([]);
  let nextId = 0;

  // action: { label, run } - ein Knopf in der Meldung, z.B. "Rückgängig"
  function add(message, type = 'info', duration = 4000, action = null) {
    const id = nextId++;
    update(n => [...n, { id, message, type, duration, action }]);
    if (duration > 0) {
      setTimeout(() => remove(id), duration);
    }
    return id;
  }

  function remove(id) {
    update(n => n.filter(t => t.id !== id));
  }

  return {
    subscribe,
    success: (msg, dur) => add(msg, 'success', dur),
    error: (msg, dur) => add(msg, 'error', dur || 6000),
    warning: (msg, dur) => add(msg, 'warning', dur),
    info: (msg, dur) => add(msg, 'info', dur),
    // Meldung mit "Rückgängig"; run macht die Aktion ungeschehen
    undo: (msg, run, dur = 7000) => add(msg, 'info', dur, { label: 'Rückgängig', run }),
    remove,
  };
}

export const toast = createNotificationStore();

/**
 * TubeVault -  Notifications Store v1.5.52
 * Toast-Benachrichtigungen (keine Browser-Popups!)
 * © HalloWelt42
 */

import { writable } from 'svelte/store';

function createNotificationStore() {
  const { subscribe, update } = writable([]);
  let nextId = 0;

  function add(message, type = 'info', duration = 4000) {
    const id = nextId++;
    update(n => [...n, { id, message, type, duration }]);
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
    remove,
  };
}

export const toast = createNotificationStore();

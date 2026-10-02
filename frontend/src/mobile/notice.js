/** Kurze Rückmeldung am unteren Rand (eine Zeile, verschwindet von selbst). */
import { writable } from 'svelte/store';

export const notice = writable(null);
let timer = null;

export function say(text, kind = 'info') {
  clearTimeout(timer);
  notice.set({ text, kind });
  timer = setTimeout(() => notice.set(null), 3200);
}

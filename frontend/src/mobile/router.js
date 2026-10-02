/**
 * TubeVault – Mobil-Router
 * Wenige feste Adressen unter /m. Die Adresse ist die Wahrheit; Zurück des
 * Telefons funktioniert wie erwartet.
 *
 *   /m/            Start
 *   /m/videos      Bibliothek und Archiv
 *   /m/suche       Suche (?q=)
 *   /m/neu         Neues aus den Abos
 *   /m/video/:id   Wiedergabe
 */
import { writable } from 'svelte/store';

export const BASE = '/m';
export const TABS = ['start', 'videos', 'suche', 'neu'];

function parse() {
  const rest = window.location.pathname.slice(BASE.length).split('/').filter(Boolean);
  const params = Object.fromEntries(new URLSearchParams(window.location.search));
  if (rest[0] === 'video' && rest[1]) return { view: 'video', id: rest[1], params };
  if (TABS.includes(rest[0])) return { view: rest[0], id: null, params };
  return { view: 'start', id: null, params };
}

export const route = writable(parse());

/** Zu einer Mobil-Adresse wechseln, z.B. go('/video/abc') oder go('/suche', { q: 'teig' }). */
export function go(path, params = {}, { replace = false } = {}) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => value !== null && value !== undefined && value !== '')
  ).toString();
  const url = BASE + path + (query ? `?${query}` : '');
  if (replace) history.replaceState(null, '', url);
  else history.pushState(null, '', url);
  route.set(parse());
}

export function back() {
  if (history.length > 1) history.back();
  else go('/', {}, { replace: true });
}

window.addEventListener('popstate', () => route.set(parse()));

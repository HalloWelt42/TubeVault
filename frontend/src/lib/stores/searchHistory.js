/**
 * TubeVault - Suchverlauf dieses Browsers (zuletzt gesucht)
 * Für die Aufklappliste im Kopf, die Suche-Seite und das Handy.
 */
import { writable } from 'svelte/store';

const KEY = 'tv_search_history';
const MAX = 20;

function load() {
  try {
    const list = JSON.parse(localStorage.getItem(KEY) || '[]');
    return Array.isArray(list) ? list.filter((entry) => entry?.query) : [];
  } catch {
    return [];
  }
}

export const searchHistory = writable(typeof localStorage === 'undefined' ? [] : load());

function save(list) {
  try { localStorage.setItem(KEY, JSON.stringify(list)); } catch { /* Speicher gesperrt */ }
  searchHistory.set(list);
}

export function rememberSearch(query) {
  const text = (query || '').trim();
  if (!text) return;
  save([{ query: text, date: new Date().toISOString() }, ...load().filter((entry) => entry.query !== text)].slice(0, MAX));
}

export function forgetSearch(query) {
  save(load().filter((entry) => entry.query !== query));
}

export function clearSearchHistory() {
  save([]);
}

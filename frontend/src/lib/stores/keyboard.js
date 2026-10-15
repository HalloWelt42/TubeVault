/**
 * TubeVault – Keyboard Shortcuts v1.6.29
 * © HalloWelt42 – Private Nutzung
 */

import { navigate } from '../router/router.js';

const shortcuts = {
  'd': '/',
  'b': '/library',
  'h': '/history',
  'p': '/playlists',
  'f': '/favorites',
  'k': '/categories',
  'o': '/downloads',
  't': '/stats',
  'e': '/settings',
};

let enabled = true;
// Das Suchfeld im Kopf (layout/SearchBox.svelte)
export const SEARCH_FIELD = '[data-suchfeld]';

export function initKeyboard() {
  window.addEventListener('keydown', handleKey);
}

function handleKey(e) {
  if (!enabled) return;

  // Ignore wenn in Input/Textarea/Select
  const tag = e.target?.tagName?.toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
  if (e.target?.isContentEditable) return;

  // Ctrl/Cmd + K, S oder / → Suchfeld im Kopf
  if (((e.ctrlKey || e.metaKey) && e.key === 'k') || (!e.altKey && !e.ctrlKey && !e.metaKey && ['s', 'S', '/'].includes(e.key))) {
    e.preventDefault();
    document.querySelector(SEARCH_FIELD)?.focus();
    return;
  }

  // ? → Show shortcuts help
  if (e.key === '?') {
    window.dispatchEvent(new CustomEvent('tubevault:show-shortcuts'));
    return;
  }

  // Alt + Key → Navigation
  if (e.altKey && shortcuts[e.key]) {
    e.preventDefault();
    navigate(shortcuts[e.key]);
    return;
  }

  // Escape → Suchfeld verlassen
  if (e.key === 'Escape') {
    document.querySelector(SEARCH_FIELD)?.blur();
    return;
  }
}

export function disableKeyboard() { enabled = false; }
export function enableKeyboard() { enabled = true; }
export { shortcuts };

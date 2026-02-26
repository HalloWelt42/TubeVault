/**
 * TubeVault -  Keyboard Shortcuts v1.6.29
 * © HalloWelt42 -  Private Nutzung
 */

import { navigate } from '../router/router.js';
import { searchQuery } from './app.js';

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

export function initKeyboard() {
  window.addEventListener('keydown', handleKey);
}

function handleKey(e) {
  if (!enabled) return;

  // Ignore wenn in Input/Textarea/Select
  const tag = e.target?.tagName?.toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
  if (e.target?.isContentEditable) return;

  // Ctrl/Cmd + K oder S → Focus search
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    const searchEl = document.querySelector('.sd-input');
    if (searchEl) searchEl.focus();
    return;
  }

  // S → Focus search (wie Ctrl+K, aber ohne Modifier)
  if (e.key === 's' || e.key === 'S') {
    e.preventDefault();
    const searchEl = document.querySelector('.sd-input');
    if (searchEl) searchEl.focus();
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

  // Escape → Clear search, back to dashboard
  if (e.key === 'Escape') {
    searchQuery.set('');
    const searchEl = document.querySelector('.search-input');
    if (searchEl) searchEl.blur();
    return;
  }
}

export function disableKeyboard() { enabled = false; }
export function enableKeyboard() { enabled = true; }
export { shortcuts };

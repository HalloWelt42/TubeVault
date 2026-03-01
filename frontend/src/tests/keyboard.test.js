/**
 * TubeVault -  Keyboard Shortcuts Tests v1.5.2
 * © HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
 * SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { get } from 'svelte/store';
import { currentRoute, searchQuery } from '../lib/stores/app.js';
import { initKeyboard, disableKeyboard, enableKeyboard, shortcuts } from '../lib/stores/keyboard.js';

describe('Keyboard Shortcuts', () => {
  beforeEach(() => {
    currentRoute.set('dashboard');
    searchQuery.set('');
    enableKeyboard();
    initKeyboard();
  });

  afterEach(() => {
    // Remove event listeners by re-adding (not ideal, but functional)
  });

  function pressKey(key, opts = {}) {
    const event = new KeyboardEvent('keydown', {
      key,
      altKey: opts.altKey || false,
      ctrlKey: opts.ctrlKey || false,
      metaKey: opts.metaKey || false,
      bubbles: true,
    });
    // Simuliere target als body (kein input)
    Object.defineProperty(event, 'target', {
      value: { tagName: 'BODY', isContentEditable: false },
    });
    window.dispatchEvent(event);
  }

  describe('Shortcut Mapping', () => {
    it('enthält alle erwarteten Shortcuts', () => {
      expect(shortcuts).toEqual({
        'd': 'dashboard',
        'b': 'library',
        // 's' fokussiert SearchDropdown (kein Route-Wechsel)
        'h': 'history',
        'p': 'playlists',
        'f': 'favorites',
        'k': 'categories',
        'o': 'downloads',
        't': 'stats',
        'e': 'settings',
      });
    });

    it('10 Shortcuts definiert', () => {
      expect(Object.keys(shortcuts)).toHaveLength(10);
    });
  });

  describe('Alt + Key Navigation', () => {
    it('Alt+D → dashboard', () => {
      currentRoute.set('library');
      pressKey('d', { altKey: true });
      expect(get(currentRoute)).toBe('dashboard');
    });

    it('Alt+B → library', () => {
      pressKey('b', { altKey: true });
      expect(get(currentRoute)).toBe('library');
    });

    it('Alt+S → search', () => {
      pressKey('s', { altKey: true });
      expect(get(currentRoute)).toBe('search');
    });

    it('Alt+O → downloads', () => {
      pressKey('o', { altKey: true });
      expect(get(currentRoute)).toBe('downloads');
    });
  });

  describe('Escape', () => {
    it('setzt searchQuery zurück', () => {
      searchQuery.set('test query');
      pressKey('Escape');
      expect(get(searchQuery)).toBe('');
    });
  });

  describe('Input-Felder ignorieren', () => {
    it('ignoriert Tasten in Input-Feldern', () => {
      currentRoute.set('dashboard');
      const event = new KeyboardEvent('keydown', {
        key: 'b',
        altKey: true,
        bubbles: true,
      });
      Object.defineProperty(event, 'target', {
        value: { tagName: 'INPUT', isContentEditable: false },
      });
      window.dispatchEvent(event);
      expect(get(currentRoute)).toBe('dashboard'); // unverändert
    });

    it('ignoriert Tasten in Textareas', () => {
      currentRoute.set('dashboard');
      const event = new KeyboardEvent('keydown', {
        key: 'b',
        altKey: true,
        bubbles: true,
      });
      Object.defineProperty(event, 'target', {
        value: { tagName: 'TEXTAREA', isContentEditable: false },
      });
      window.dispatchEvent(event);
      expect(get(currentRoute)).toBe('dashboard');
    });
  });

  describe('Keyboard Enable/Disable', () => {
    it('disableKeyboard verhindert Navigation', () => {
      disableKeyboard();
      pressKey('b', { altKey: true });
      expect(get(currentRoute)).toBe('dashboard');
    });

    it('enableKeyboard reaktiviert Navigation', () => {
      disableKeyboard();
      enableKeyboard();
      pressKey('b', { altKey: true });
      expect(get(currentRoute)).toBe('library');
    });
  });
});

/**
 * TubeVault – Store Tests v1.5.2
 * © HalloWelt42
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { currentRoute, currentVideoId, currentChannelId, sidebarOpen, searchQuery } from '../lib/stores/app.js';
import { toast } from '../lib/stores/notifications.js';

// ============================================================
// App Store
// ============================================================
describe('App Store', () => {
  beforeEach(() => {
    currentRoute.set('dashboard');
    currentVideoId.set(null);
    currentChannelId.set(null);
    sidebarOpen.set(true);
    searchQuery.set('');
  });

  describe('currentRoute', () => {
    it('Startwert ist dashboard', () => {
      expect(get(currentRoute)).toBe('dashboard');
    });

    it('Route wechseln', () => {
      currentRoute.set('library');
      expect(get(currentRoute)).toBe('library');
    });

    it('alle Routen sind setzbar', () => {
      const routes = [
        'dashboard', 'library', 'watch', 'downloads', 'favorites',
        'categories', 'settings', 'subscriptions', 'feed', 'channel',
        'archives', 'history', 'playlists', 'stats', 'import',
      ];
      routes.forEach(route => {
        currentRoute.set(route);
        expect(get(currentRoute)).toBe(route);
      });
    });

    it('subscribe benachrichtigt bei Änderung', () => {
      const values = [];
      const unsub = currentRoute.subscribe(v => values.push(v));
      currentRoute.set('library');
      currentRoute.set('downloads');
      unsub();
      expect(values).toEqual(['dashboard', 'library', 'downloads']);
    });
  });

  describe('currentVideoId', () => {
    it('Startwert ist null', () => {
      expect(get(currentVideoId)).toBe(null);
    });

    it('Video-ID setzen und zurücksetzen', () => {
      currentVideoId.set(42);
      expect(get(currentVideoId)).toBe(42);
      currentVideoId.set(null);
      expect(get(currentVideoId)).toBe(null);
    });
  });

  describe('currentChannelId', () => {
    it('Startwert ist null', () => {
      expect(get(currentChannelId)).toBe(null);
    });

    it('Channel-ID setzen', () => {
      currentChannelId.set('UCxxxxxx');
      expect(get(currentChannelId)).toBe('UCxxxxxx');
    });
  });

  describe('sidebarOpen', () => {
    it('Startwert ist true', () => {
      expect(get(sidebarOpen)).toBe(true);
    });

    it('Sidebar toggle', () => {
      sidebarOpen.set(false);
      expect(get(sidebarOpen)).toBe(false);
      sidebarOpen.set(true);
      expect(get(sidebarOpen)).toBe(true);
    });
  });

  describe('searchQuery', () => {
    it('Startwert ist leer', () => {
      expect(get(searchQuery)).toBe('');
    });

    it('Suchtext setzen', () => {
      searchQuery.set('python tutorial');
      expect(get(searchQuery)).toBe('python tutorial');
    });
  });
});

// ============================================================
// Notifications Store (Toast)
// ============================================================
describe('Notifications Store', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Clear all toasts
    const current = get(toast);
    current.forEach(t => toast.remove(t.id));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('startet leer', () => {
    expect(get(toast)).toEqual([]);
  });

  it('toast.success erstellt success-Benachrichtigung', () => {
    toast.success('Gespeichert');
    const toasts = get(toast);
    expect(toasts).toHaveLength(1);
    expect(toasts[0].message).toBe('Gespeichert');
    expect(toasts[0].type).toBe('success');
  });

  it('toast.error erstellt error-Benachrichtigung', () => {
    toast.error('Fehler aufgetreten');
    const toasts = get(toast);
    expect(toasts).toHaveLength(1);
    expect(toasts[0].message).toBe('Fehler aufgetreten');
    expect(toasts[0].type).toBe('error');
  });

  it('toast.warning erstellt warning-Benachrichtigung', () => {
    toast.warning('Achtung');
    const toasts = get(toast);
    expect(toasts).toHaveLength(1);
    expect(toasts[0].type).toBe('warning');
  });

  it('toast.info erstellt info-Benachrichtigung', () => {
    toast.info('Hinweis');
    const toasts = get(toast);
    expect(toasts).toHaveLength(1);
    expect(toasts[0].type).toBe('info');
  });

  it('mehrere Toasts gleichzeitig', () => {
    toast.success('Eins');
    toast.error('Zwei');
    toast.info('Drei');
    expect(get(toast)).toHaveLength(3);
  });

  it('jeder Toast hat eindeutige ID', () => {
    toast.success('A');
    toast.success('B');
    toast.success('C');
    const ids = get(toast).map(t => t.id);
    expect(new Set(ids).size).toBe(3);
  });

  it('toast.remove entfernt spezifischen Toast', () => {
    const id = toast.success('Temporär');
    toast.remove(id);
    expect(get(toast)).toHaveLength(0);
  });

  it('Toast verschwindet automatisch nach Duration', () => {
    toast.success('Auto-Remove', 2000);
    expect(get(toast)).toHaveLength(1);
    vi.advanceTimersByTime(2000);
    expect(get(toast)).toHaveLength(0);
  });

  it('Error-Toast hat längere Default-Duration (6s)', () => {
    toast.error('Langlebiger Fehler');
    expect(get(toast)).toHaveLength(1);
    vi.advanceTimersByTime(4000);
    expect(get(toast)).toHaveLength(1); // noch da
    vi.advanceTimersByTime(2000);
    expect(get(toast)).toHaveLength(0); // nach 6s weg
  });

  it('Standard-Duration ist 4s', () => {
    toast.info('Standard');
    vi.advanceTimersByTime(3999);
    expect(get(toast)).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(get(toast)).toHaveLength(0);
  });
});

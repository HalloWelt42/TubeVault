/**
 * TubeVault -  Theme Store v1.5.52
 * 27 CSS Variablen, Dark/Light + Custom
 * © HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
 * SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
 */

import { writable } from 'svelte/store';

export const themes = {
  dark: {
    '--bg-primary': '#0f0f14',
    '--bg-secondary': '#1a1a24',
    '--bg-tertiary': '#232334',
    '--bg-hover': '#2a2a3d',
    '--bg-active': '#33334d',
    '--text-primary': '#eeeef0',
    '--text-secondary': '#a0a0b8',
    '--text-tertiary': '#6b6b80',
    '--text-inverse': '#0f0f14',
    '--border-primary': '#2e2e42',
    '--border-secondary': '#3d3d55',
    '--accent-primary': '#6366f1',
    '--accent-hover': '#7c7ff7',
    '--accent-muted': '#6366f133',
    '--accent-complement': '#f1c866',
    '--status-success': '#22c55e',
    '--status-warning': '#eab308',
    '--status-error': '#ef4444',
    '--status-info': '#3b82f6',
    '--status-success-bg': '#22c55e18',
    '--status-warning-bg': '#eab30818',
    '--status-error-bg': '#ef444418',
    '--status-info-bg': '#3b82f618',
    '--status-pending': '#a78bfa',
    '--code-bg': '#1e1e2e',
    '--code-text': '#cdd6f4',
    '--scrollbar-track': '#1a1a24',
    '--scrollbar-thumb': '#3d3d55',
    '--scrollbar-hover': '#4d4d66',
  },
  light: {
    '--bg-primary': '#f8f8fc',
    '--bg-secondary': '#ffffff',
    '--bg-tertiary': '#f0f0f6',
    '--bg-hover': '#e8e8f0',
    '--bg-active': '#dddde8',
    '--text-primary': '#1a1a2e',
    '--text-secondary': '#5a5a72',
    '--text-tertiary': '#8888a0',
    '--text-inverse': '#f8f8fc',
    '--border-primary': '#dddde8',
    '--border-secondary': '#c8c8d8',
    '--accent-primary': '#6366f1',
    '--accent-hover': '#4f46e5',
    '--accent-muted': '#6366f120',
    '--accent-complement': '#e5a600',
    '--status-success': '#16a34a',
    '--status-warning': '#ca8a04',
    '--status-error': '#dc2626',
    '--status-info': '#2563eb',
    '--status-success-bg': '#16a34a15',
    '--status-warning-bg': '#ca8a0415',
    '--status-error-bg': '#dc262615',
    '--status-info-bg': '#2563eb15',
    '--status-pending': '#7c3aed',
    '--code-bg': '#f0f0f6',
    '--code-text': '#1a1a2e',
    '--scrollbar-track': '#f0f0f6',
    '--scrollbar-thumb': '#c8c8d8',
    '--scrollbar-hover': '#aaaabc',
  },
};

function createThemeStore() {
  const stored = typeof localStorage !== 'undefined' ? localStorage.getItem('tubevault-theme') : null;
  const { subscribe, set, update } = writable(stored || 'dark');

  function applyTheme(name) {
    const vars = themes[name];
    if (!vars) return;
    const root = document.documentElement;
    root.setAttribute('data-theme', name);
    Object.entries(vars).forEach(([k, v]) => root.style.setProperty(k, v));
  }

  // Initial
  if (typeof document !== 'undefined') {
    applyTheme(stored || 'dark');
  }

  return {
    subscribe,
    set(name) {
      set(name);
      applyTheme(name);
      localStorage.setItem('tubevault-theme', name);
    },
    toggle() {
      update(current => {
        const next = current === 'dark' ? 'light' : 'dark';
        applyTheme(next);
        localStorage.setItem('tubevault-theme', next);
        return next;
      });
    },
  };
}

export const theme = createThemeStore();

/**
 * TubeVault – Settings Store v1.5.75
 * Lädt Einstellungen aus dem Backend und stellt sie reaktiv bereit.
 * © HalloWelt42
 */

import { writable, get } from 'svelte/store';
import { api } from '../api/client.js';

// Default-Werte (Fallback wenn API nicht erreichbar)
const DEFAULTS = {
  'player.volume': '80',
  'player.autoplay': 'false',
  'player.speed': '1.0',
  'player.save_position': 'true',
  'general.videos_per_page': '24',
  'download.quality': '720p',
  'download.format': 'mp4',
};

export const settings = writable({...DEFAULTS});
let _loaded = false;

/**
 * Einstellungen vom Backend laden (einmalig, cached).
 * Wird beim App-Start aufgerufen.
 */
export async function loadSettings() {
  if (_loaded) return;
  try {
    const groups = await api.getSettings();
    const flat = {};
    if (Array.isArray(groups)) {
      for (const group of groups) {
        // Format: [{ category, settings: [{ key, value, ... }] }]
        if (group.settings && Array.isArray(group.settings)) {
          for (const item of group.settings) {
            flat[item.key] = item.value;
          }
        }
        // Fallback: flaches Array [{ key, value }]
        else if (group.key) {
          flat[group.key] = group.value;
        }
      }
    }
    settings.update(s => ({ ...s, ...flat }));
    _loaded = true;
  } catch (e) {
    console.warn('Settings laden fehlgeschlagen:', e);
  }
}

/**
 * Einzelne Einstellung lesen.
 */
export function getSetting(key, fallback = '') {
  const s = get(settings);
  return s[key] ?? DEFAULTS[key] ?? fallback;
}

/**
 * Einstellung als Boolean.
 */
export function getSettingBool(key, fallback = false) {
  const val = getSetting(key, fallback ? 'true' : 'false');
  return val === 'true' || val === true;
}

/**
 * Einstellung als Zahl.
 */
export function getSettingNum(key, fallback = 0) {
  const val = getSetting(key, String(fallback));
  const n = Number(val);
  return isNaN(n) ? fallback : n;
}

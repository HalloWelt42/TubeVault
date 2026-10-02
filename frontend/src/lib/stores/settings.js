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
let _loading = null;

/**
 * Einstellungen vom Backend laden. Die App wartet beim Start darauf, bevor
 * sie Seiten zeigt - sonst lesen Seiten beim ersten Aufruf die Ersatzwerte
 * (Videos pro Seite, Qualität) statt der gespeicherten Einstellungen.
 * Mehrfache Aufrufe teilen sich denselben Ladevorgang; ein Fehlschlag wird
 * beim nächsten Aufruf erneut versucht.
 */
export function loadSettings() {
  if (!_loading) {
    _loading = fetchSettings().then(ok => { if (!ok) _loading = null; });
  }
  return _loading;
}

/** Einstellungen erneut laden (nach Zurücksetzen oder Wiederherstellen). */
export function reloadSettings() {
  _loading = null;
  return loadSettings();
}

async function fetchSettings() {
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
    settings.set({ ...DEFAULTS, ...flat });
    return true;
  } catch (e) {
    console.warn('Settings laden fehlgeschlagen:', e);
    return false;
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

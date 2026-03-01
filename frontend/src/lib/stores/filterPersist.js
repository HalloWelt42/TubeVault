/**
 * TubeVault -  Filter Persistence v1.7.4
 * Speichert Filter-/Sortier-States pro Seite in localStorage.
 * © HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
 * SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
 */

const PREFIX = 'tv_filters_';

/**
 * Filter-State speichern.
 * @param {string} route - Route-Name (z.B. 'library', 'feed')
 * @param {object} state - Key/Value Paare die gespeichert werden sollen
 */
export function saveFilters(route, state) {
  try {
    const existing = loadFilters(route);
    const merged = { ...existing, ...state };
    localStorage.setItem(PREFIX + route, JSON.stringify(merged));
  } catch { /* localStorage voll oder blockiert */ }
}

/**
 * Filter-State laden.
 * @param {string} route - Route-Name
 * @returns {object} Gespeicherte Filter oder leeres Objekt
 */
export function loadFilters(route) {
  try {
    const raw = localStorage.getItem(PREFIX + route);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

/**
 * Einzelnen Wert laden mit Fallback.
 * @param {string} route
 * @param {string} key
 * @param {*} fallback
 */
export function getFilter(route, key, fallback) {
  const filters = loadFilters(route);
  return key in filters ? filters[key] : fallback;
}

/**
 * Filter-State einer Route löschen.
 */
export function clearFilters(route) {
  try { localStorage.removeItem(PREFIX + route); } catch {}
}

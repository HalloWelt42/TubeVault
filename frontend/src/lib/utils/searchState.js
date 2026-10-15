/**
 * TubeVault - Zustand der Suche in der Adresse und für die API
 *
 * Adresse (deutsch, teilbar):  q, bereich, sprache, laenge, zeitraum, ort, stand, ordnung, genau
 * API (services/search):        q, language, length, period, location, state, order, precision
 * Leere Werte und die Standardordnung stehen nirgends.
 */
import { parseLanguageList } from './language.js';

// Adresse -> API, je Filter
const FILTERS = [
  ['laenge', 'length'], ['zeitraum', 'period'], ['ort', 'location'],
  ['stand', 'state'], ['ordnung', 'order'], ['genau', 'precision'],
];
export const DEFAULT_ORDER = 'passend';

export function emptyFilters() {
  return { sprache: [], laenge: null, zeitraum: null, ort: null, stand: null, ordnung: DEFAULT_ORDER, genau: null };
}

/** Zustand aus den Adressparametern */
export function readSearch(params = {}) {
  const filters = emptyFilters();
  filters.sprache = parseLanguageList(params.sprache);
  for (const [key] of FILTERS) {
    if (params[key]) filters[key] = params[key];
  }
  return { q: params.q || '', section: params.bereich || null, filters };
}

/** Adressparameter (null entfernt einen Wert, siehe router.updateParams) */
export function addressParams({ q, section, filters }) {
  const params = { q: q || null, bereich: section || null, sprache: filters.sprache.length ? filters.sprache.join(',') : null };
  for (const [key] of FILTERS) {
    params[key] = filters[key] && !(key === 'ordnung' && filters[key] === DEFAULT_ORDER) ? filters[key] : null;
  }
  return params;
}

/** Filter für die API (ohne leere Werte) */
export function apiParams(filters) {
  const params = {};
  if (filters.sprache?.length) params.language = filters.sprache.join(',');
  for (const [key, apiKey] of FILTERS) {
    if (filters[key] && !(key === 'ordnung' && filters[key] === DEFAULT_ORDER)) params[apiKey] = filters[key];
  }
  return params;
}

/** Filter aus einer gemerkten Suche (API-Namen, wie das Backend sie speichert) */
export function filtersFromSaved(saved = {}) {
  const filters = emptyFilters();
  filters.sprache = [...(saved.languages || [])];
  for (const [key, apiKey] of FILTERS) {
    if (saved[apiKey]) filters[key] = saved[apiKey];
  }
  return filters;
}

/** Filter zum Merken (API-Namen) */
export function filtersToSaved(filters) {
  const saved = { languages: [...filters.sprache] };
  for (const [key, apiKey] of FILTERS) {
    if (filters[key]) saved[apiKey] = filters[key];
  }
  return saved;
}

/** Wie viele Filter weichen vom Standard ab (für "Filter aufheben") */
export function activeFilterCount(filters) {
  return (filters.sprache.length ? 1 : 0)
    + FILTERS.filter(([key]) => filters[key] && !(key === 'ordnung' && filters[key] === DEFAULT_ORDER) && key !== 'genau').length;
}

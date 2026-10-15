/**
 * TubeVault - Sprache anzeigen (Labels, Filter, Tooltips)
 *
 * Namen, Flaggen und Herkünfte kommen aus dem Backend (GET /api/languages,
 * services/language.py) - hier wird nichts davon doppelt gepflegt. Der
 * Katalog wird einmal geladen und von allen Labels und Filtern geteilt.
 *
 * Regeln für Labels:
 *   - Sprache gleich der Hauptsprache (Einstellung language.main): kein Label,
 *     sonst stünde auf fast jeder Kachel dieselbe Flagge.
 *   - Unbekannte Sprache: kein Label.
 *   - Kanal mit mehreren Sprachen ("mul"): Label "gemischt".
 */
import { writable } from 'svelte/store';
import { api } from '../api/client.js';

export const MAIN_LANGUAGE_KEY = 'language.main';
export const DEFAULT_MAIN_LANGUAGE = 'de';
export const UNKNOWN = 'und';
export const MIXED = 'mul';

/** Katalog { languages, sources, unknown, mixed } oder null, solange er lädt. */
export const languageCatalog = writable(null);
let _loading = null;

/** Katalog laden (einmal; ein Fehlschlag wird beim nächsten Aufruf wiederholt). */
export function loadLanguages() {
  if (!_loading) {
    _loading = api.getLanguages()
      .then((catalog) => { languageCatalog.set(catalog); return catalog; })
      .catch(() => { _loading = null; return null; });
  }
  return _loading;
}

/** Hauptsprache aus den Einstellungen (Werte des settings-Stores). */
export function mainLanguage(settingValues) {
  return settingValues?.[MAIN_LANGUAGE_KEY] || DEFAULT_MAIN_LANGUAGE;
}

/** { code, name, flag } einer Sprache; Unbekanntes mit dem Kürzel als Namen. */
export function languageInfo(catalog, code) {
  if (!code || code === UNKNOWN) return catalog?.unknown || { code: UNKNOWN, name: 'Unbekannt', flag: null };
  if (code === MIXED) return catalog?.mixed || { code: MIXED, name: 'Gemischt', flag: null };
  const known = catalog?.languages?.find((lang) => lang.code === code);
  return known || { code, name: code.toUpperCase(), flag: null };
}

/** So heißt eine Herkunft ("Angabe beim Laden"), oder null. */
export function sourceLabel(catalog, source) {
  return catalog?.sources?.find((s) => s.key === source)?.label || null;
}

/**
 * Label für eine Sprachangabe oder null, wenn keins erscheinen soll.
 * main: Hauptsprache (ihr Label entfällt); null zeigt jede bekannte Sprache.
 * channel: Sprache eines Kanals (Mehrheit seiner Videos) statt eines Videos.
 * Ergebnis: { code, short, flag, title, mixed }
 */
export function languageLabel(catalog, code, source = null, main = DEFAULT_MAIN_LANGUAGE, channel = false) {
  if (!code || code === UNKNOWN || (main && code === main)) return null;
  const info = languageInfo(catalog, code);
  if (code === MIXED) {
    return { code, short: 'gemischt', flag: null, mixed: true,
             title: 'Gemischt: Videos in mehreren Sprachen' };
  }
  const origin = sourceLabel(catalog, source);
  const title = channel ? `${info.name}: Sprache der meisten Videos`
    : origin ? `${info.name} (Quelle: ${origin})` : info.name;
  return { code, short: code.toUpperCase(), flag: info.flag, mixed: false, title };
}

/**
 * Auswahl für den Sprachfilter aus den Zählern des Backends
 * ([{ code, count }]): mit Namen und Flagge, Reihenfolge wie geliefert
 * (häufigste zuerst, ohne Sprache zuletzt). Gewählte Sprachen ohne Treffer
 * bleiben sichtbar (Zähler 0), damit man sie abwählen kann.
 */
export function languageChoices(catalog, counts = [], selected = []) {
  const list = (counts || []).map((item) => ({ ...languageInfo(catalog, item.code), code: item.code, count: item.count }));
  for (const code of selected) {
    if (!list.some((item) => item.code === code)) list.push({ ...languageInfo(catalog, code), code, count: 0 });
  }
  return list;
}

/** Filterwerte als Liste aus "en,fr" (oder leer). */
export function parseLanguageList(value) {
  return value ? String(value).split(',').map((v) => v.trim()).filter(Boolean) : [];
}

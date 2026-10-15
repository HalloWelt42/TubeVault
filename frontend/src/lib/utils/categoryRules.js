// Kategorien: Regelarten, Anzeigetexte, Sortierung und Vorschau - reine
// Funktionen für die Seite und ihre Tests. Ausgewertet werden die Regeln
// allein im Backend (category_rules).
import { totalTime } from './collection.js';

/** Regelarten in der Reihenfolge der Auswahl. */
export const RULE_KINDS = [
  { kind: 'channel', label: 'Kanal ist', icon: 'fa-tv', placeholder: 'Kanal suchen',
    hint: 'Alle Videos dieses Kanals, auch künftige' },
  { kind: 'tag', label: 'Schlagwort enthält', icon: 'fa-tag', placeholder: 'z.B. Konzert',
    hint: 'Videos mit einem Schlagwort, das dieses Wort enthält (Groß und klein egal)' },
  { kind: 'semantic', label: 'Inhaltlich wie', icon: 'fa-wand-magic-sparkles', placeholder: 'z.B. Kochen und Backen: Rezepte, Brot, Pizza',
    hint: 'Videos mit ähnlichem Inhalt (Bedeutungssuche der lokalen KI); Thema und Stichwörter treffen am besten' },
];

export const kindOf = (kind) => RULE_KINDS.find((k) => k.kind === kind) || RULE_KINDS[0];

/** Text eines Regel-Chips: Kanalname, Wort bzw. "inhaltlich wie: ...". */
export function ruleText(rule) {
  if (rule.kind === 'semantic') return `inhaltlich wie: ${rule.value}`;
  return rule.kind === 'channel' ? (rule.label || rule.value) : rule.value;
}

/** Warum ein Video in der Kategorie ist (Feld reason der Sammlung). */
export const REASON_LABELS = { hand: 'von Hand', channel: 'Regel: Kanal', tag: 'Regel: Schlagwort', semantic: 'inhaltlich wie' };

export const OVERVIEW_SORTS = [
  { key: 'groesse', label: 'Größe', title: 'Die meisten Videos zuerst' },
  { key: 'name', label: 'Name' },
  { key: 'gefuellt', label: 'Zuletzt gefüllt', title: 'Wohin zuletzt ein Video kam' },
];

const byName = (a, b) => a.name.localeCompare(b.name, 'de', { sensitivity: 'base' });
const ORDER = {
  groesse: (a, b) => (b.video_count || 0) - (a.video_count || 0) || byName(a, b),
  name: byName,
  gefuellt: (a, b) => (b.last_filled_at || b.created_at || '').localeCompare(a.last_filled_at || a.created_at || '') || byName(a, b),
};

/** Kategorien nach Suchwörtern (Name, Beschreibung, Regeln) filtern und sortieren. */
export function arrangeCategories(list, { search = '', sort = 'groesse' } = {}) {
  const words = search.trim().toLocaleLowerCase('de').split(/\s+/).filter(Boolean);
  const text = (c) => [c.name, c.description, ...(c.rules || []).map(ruleText)].join(' ').toLocaleLowerCase('de');
  return list.filter((c) => words.every((w) => text(c).includes(w))).sort(ORDER[sort] || ORDER.groesse);
}

const num = (n) => (n || 0).toLocaleString('de-DE');
const videos = (n) => `${num(n)} ${n === 1 ? 'Video' : 'Videos'}`;

/** Kennzahlen einer Kategorie: "214 Videos · 3:03 Std. · 12 gesehen". */
export function categoryInfo(card) {
  return [videos(card.video_count), card.duration ? totalTime(card.duration) : null,
    card.finished_count ? `${num(card.finished_count)} gesehen` : null].filter(Boolean).join(' · ');
}

/** Kopf der Übersicht: "3 Kategorien · 255 Videos eingeordnet · 32.268 ohne Kategorie". */
export function overviewInfo(data) {
  if (!data) return null;
  const count = data.categories.length;
  return `${num(count)} ${count === 1 ? 'Kategorie' : 'Kategorien'} · ${videos(data.assigned)} eingeordnet · ${num(data.unassigned)} ohne Kategorie`;
}

/** Regeln eines Entwurfs, wie das Backend sie nimmt (leere fallen weg). */
export function rulesForSave(drafts) {
  return drafts.filter((r) => String(r.value || '').trim())
    .map((r) => ({ kind: r.kind, value: String(r.value).trim(), ...(r.kind === 'semantic' ? { precision: r.precision || null } : {}) }));
}

/** Beschriftung des Speicherknopfs im Seitenblatt. */
export function saveLabel(preview) {
  if (preview?.new) return `Speichern und ${num(preview.new)} einordnen`;
  return 'Speichern';
}

/** Farben für eine neue Kategorie: zuerst die noch freien. */
export function freeColors(palette, used, count = 6) {
  const taken = new Set(used);
  return [...palette.filter((c) => !taken.has(c)), ...palette.filter((c) => taken.has(c))].slice(0, count);
}

// Sammlungen (Favoriten, Playlists, Verlauf): Filtern, Sortieren, Umordnen
// und Gruppieren - reine Funktionen, die Seiten und Tests gemeinsam nutzen.
// Den Stand je Video (new | started | finished) liefert der Server.
import { parseServerTime } from './format.js';

export const STATE_LABELS = { new: 'Neu', started: 'Angefangen', finished: 'Gesehen' };

/** Chips für den Stand mit Anzahl: Alle, Neu, Angefangen, Gesehen. */
export function stateChips(counts, total) {
  return [{ key: '', label: 'Alle', count: total },
    ...Object.entries(STATE_LABELS).map(([key, label]) => ({ key, label, count: counts?.[key] ?? 0 }))];
}

/** Nach Suchwörtern (Titel, Kanal) und Stand filtern. */
export function filterItems(items, { search = '', state = '' } = {}) {
  const words = search.trim().toLocaleLowerCase('de').split(/\s+/).filter(Boolean);
  return items.filter((item) => (!state || item.state === state)
    && words.every((w) => `${item.title} ${item.channel_name || ''}`.toLocaleLowerCase('de').includes(w)));
}

const text = (key) => (a, b) => (a[key] || '').localeCompare(b[key] || '', 'de', { sensitivity: 'base' });
const SORTERS = {
  eigene: null,                                                        // Reihenfolge der Sammlung
  hinzugefuegt: (a, b) => (b.added_at || '').localeCompare(a.added_at || ''),
  neueste: (a, b) => (b.upload_date || '').localeCompare(a.upload_date || ''),   // nach Erscheinen
  titel: text('title'),
  dauer: (a, b) => (a.duration || 0) - (b.duration || 0),
  kanal: (a, b) => text('channel_name')(a, b) || text('title')(a, b),
};

/** Sortierte Kopie; 'eigene' lässt die Reihenfolge der Sammlung. */
export function sortItems(items, sort = 'eigene') {
  const by = SORTERS[sort];
  return by ? [...items].sort(by) : items;
}

/** Gesamtdauer kurz: "37 Min." bzw. "21:37 Std.". */
export function totalTime(seconds) {
  const minutes = Math.round((seconds || 0) / 60);
  if (minutes < 60) return `${minutes} Min.`;
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')} Std.`;
}

/** Womit "Weiterschauen" beginnt: das erste angefangene, sonst das erste neue Video. */
export function continueIndex(items) {
  const started = items.findIndex((i) => i.state === 'started');
  return started >= 0 ? started : items.findIndex((i) => i.state === 'new');
}

/** Ein Element an eine andere Stelle verschieben (neue Liste). */
export function moveItem(list, from, to) {
  if (from === to || from < 0 || to < 0 || from >= list.length) return list;
  const result = [...list];
  const [moved] = result.splice(from, 1);
  result.splice(from < to ? to - 1 : to, 0, moved);
  return result;
}

/** Zufällige Reihenfolge (Fisher-Yates), optional mit einem Element vorn. */
export function shuffled(list, firstId = null) {
  const result = [...list];
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  if (firstId) result.sort((a, b) => (a.id === firstId ? -1 : b.id === firstId ? 1 : 0));
  return result;
}

const WEEKDAYS = ['Sonntag', 'Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag'];
const dayStart = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());

/** Überschrift eines Tages: "Heute, 15.10.", "Gestern, 14.10.", "Montag, 13.10.", älter "06.10.2025". */
export function dayLabel(date, now = new Date()) {
  const days = Math.round((dayStart(now) - dayStart(date)) / 86400000);
  const two = (n) => String(n).padStart(2, '0');
  const short = `${two(date.getDate())}.${two(date.getMonth() + 1)}.`;
  if (days === 0) return `Heute, ${short}`;
  if (days === 1) return `Gestern, ${short}`;
  if (days < 7) return `${WEEKDAYS[date.getDay()]}, ${short}`;
  if (date.getFullYear() === now.getFullYear()) return short;
  return `${short}${date.getFullYear()}`;
}

/** Einträge nach Kalendertag (Ortszeit) gruppieren, Reihenfolge bleibt. */
export function groupByDay(items, timeOf, now = new Date()) {
  const groups = [];
  for (const item of items) {
    const label = dayLabel(parseServerTime(timeOf(item)), now);
    const last = groups[groups.length - 1];
    if (last?.label === label) last.items.push(item);
    else groups.push({ label, items: [item] });
  }
  return groups;
}

/** Beginn eines Zeitraums als Serverzeit (UTC, 'YYYY-MM-DD HH:MM:SS'): today | 7 | 30 Tage. */
export function sinceOf(period, now = new Date()) {
  if (!period) return null;
  const start = dayStart(now);
  if (period !== 'heute') start.setDate(start.getDate() - (Number(period) - 1));
  return start.toISOString().slice(0, 19).replace('T', ' ');
}

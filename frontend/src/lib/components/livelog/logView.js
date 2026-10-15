// Live-Log: Bereiche, Stufen, Reiter und Filter - reine Tabellen und
// Funktionen für das Fenster (Entwurf mockups/werkzeuge.html).

/** Bereich je Kategorie des Backends: ganzes Wort und Farbe (keine Kürzel). */
export const AREAS = {
  backend: { label: 'Server', color: '#9fb3be' },
  system: { label: 'System', color: '#9fb3be' },
  api: { label: 'Abfrage', color: '#c084fc' },
  frontend: { label: 'Browser', color: '#34d399' },
  download: { label: 'Download', color: '#58b8f0' },
  rss: { label: 'Kanalprüfung', color: '#ffb03a' },
  queue: { label: 'Warteschlange', color: '#c38bea' },
  rate: { label: 'Drosselung', color: '#ff7b7b' },
  scan: { label: 'Kanalscan', color: '#26c6da' },
  meta: { label: 'Metadaten', color: '#9fb3be' },
  lyrics: { label: 'Liedtexte', color: '#ce93d8' },
  import: { label: 'Import', color: '#9fb3be' },
  stream: { label: 'Wiedergabe', color: '#4db6ac' },
  playlist: { label: 'Playlist', color: '#66bb6a' },
};
export const areaOf = (cat) => AREAS[cat] || { label: cat || 'Server', color: '#9fb3be' };

/** Stufen: Rang, Name, Zeichen. DEBUG sind vor allem die laufenden Abfragen der Oberfläche. */
export const LEVELS = {
  DEBUG: { rank: 0, label: 'Detail', cls: 'detail', icon: '' },
  INFO: { rank: 1, label: 'Info', cls: '', icon: '' },
  WARNING: { rank: 2, label: 'Warnung', cls: 'warnung', icon: 'fa-triangle-exclamation' },
  ERROR: { rank: 3, label: 'Fehler', cls: 'fehler', icon: 'fa-circle-xmark' },
  CRITICAL: { rank: 3, label: 'Fehler', cls: 'fehler', icon: 'fa-circle-xmark' },
};
export const levelOf = (level) => LEVELS[level] || LEVELS.INFO;
export const isError = (entry) => levelOf(entry.level).rank >= 3;

/** Wahl "ab welcher Stufe" (Standard: ab Info, Details auf Wunsch). */
export const THRESHOLDS = [
  { value: 0, label: 'Auch Details' },
  { value: 1, label: 'Ab Info' },
  { value: 2, label: 'Ab Warnung' },
  { value: 3, label: 'Nur Fehler' },
];

const SERVER_CATS = ['backend', 'system', 'meta', 'scan', 'download', 'rss', 'queue', 'rate', 'lyrics', 'import', 'stream', 'playlist'];

/** Reiter: cats = Kategorien des Reiters (null = alle); jobs = Aufträge statt Meldungen. */
export const TABS = [
  { id: 'alle', label: 'Alle', icon: 'fa-layer-group', cats: null },
  { id: 'server', label: 'Server', icon: 'fa-server', cats: SERVER_CATS },
  { id: 'abfragen', label: 'Abfragen', icon: 'fa-right-left', cats: ['api'] },
  { id: 'browser', label: 'Browser', icon: 'fa-display', cats: ['frontend'] },
  { id: 'auftraege', label: 'Aufträge', icon: 'fa-gears', jobs: true },
];

/** Prüft die Suche einmal: Text (ohne Groß/Klein) oder Muster (regulärer Ausdruck). */
export function matcher(query, pattern) {
  const text = query.trim();
  if (!text) return () => true;
  if (pattern) {
    let expression;
    try { expression = new RegExp(text, 'i'); } catch { return () => false; }
    return (entry) => expression.test(entry.msg) || expression.test(entry.name || '');
  }
  const needle = text.toLowerCase();
  return (entry) => String(entry.msg).toLowerCase().includes(needle) || String(entry.name || '').toLowerCase().includes(needle);
}

/** Einträge eines Reiters ab einer Stufe, passend zur Suche. */
export function filterEntries(entries, { tab, threshold, query, pattern }) {
  const cats = TABS.find((t) => t.id === tab)?.cats;
  const matches = matcher(query, pattern);
  return entries.filter((entry) => levelOf(entry.level).rank >= threshold
    && (!cats || cats.includes(entry.cat)) && matches(entry));
}

/** Text zum Speichern, eine Zeile je Meldung, Verlauf darunter. */
export function exportText(entries) {
  return entries.map((entry) => {
    const line = `${entry.ts} [${levelOf(entry.level).label}] [${areaOf(entry.cat).label}] ${entry.name}: ${entry.msg}`;
    return entry.trace ? `${line}\n${entry.trace}` : line;
  }).join('\n');
}

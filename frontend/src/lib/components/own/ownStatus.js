// Eigene Videos: Befunde, Gründe und Entscheidungen - Beschriftung und Farbe
// an einer Stelle (Werte kommen aus app/models/own_files.py).

/** Befunde in der Reihenfolge der Filter. farbe = Marke aus marken.css */
export const FINDINGS = [
  { id: 'duplicate', label: 'Schon vorhanden', kurz: 'doppelt', farbe: 'var(--tv-gefahr)', zustand: 'fehler' },
  { id: 'certain', label: 'Sicher erkannt', kurz: 'sicher', farbe: 'var(--tv-erfolg)', zustand: 'fertig' },
  { id: 'probable', label: 'Vermutlich', kurz: 'vermutlich', farbe: 'var(--tv-warnung)', zustand: 'warnung' },
  { id: 'unknown', label: 'Unbekannt', kurz: 'unbekannt', farbe: 'var(--tv-text-3)', zustand: '' },
  { id: 'pending', label: 'Wird geprüft', kurz: 'wird geprüft', farbe: 'var(--tv-info)', zustand: 'wartet' },
];
export const FINDING = Object.fromEntries(FINDINGS.map(f => [f.id, f]));

/** Woran ein Treffer erkannt wurde - als Satz für die Vergleichsansicht */
export function reasonText(file) {
  const m = file.match;
  switch (file.reason) {
    case 'source_id': return 'Die Kennung im Dateinamen gehört zu diesem Video.';
    case 'same_file': return 'Gleiche Dauer und gleiche Größe: die alte Datei wird nicht gebraucht.';
    case 'title_duration': return m?.in_library
      ? 'Gleicher Titel und gleiche Dauer: dasselbe Video liegt schon in der Bibliothek.'
      : 'Gleicher Titel und gleiche Dauer wie ein bekanntes Video des Kanals.';
    case 'title': return 'Gleicher Titel, die Dauer lässt sich nicht vergleichen.';
    case 'similar_title': return `Ähnlicher Titel im Kanal ${m?.channel_name || ''}.`.replace(' .', '.');
    default: return '';
  }
}

export const DECISIONS = {
  deleted: 'gelöscht', adopted: 'übernommen', own: 'eigenem Kanal zugeordnet',
  replaced: 'hat die Bibliotheksdatei ersetzt', skipped: 'übersprungen',
};

/** Was die Datei mit dem Treffer verbindet, kurz für die Liste */
export function matchSummary(file) {
  if (file.finding === 'pending') return 'wird geprüft';
  const m = file.match;
  if (!m) return file.channel_hint ? `kein Treffer, Ordner ${file.channel_hint}` : 'kein Treffer';
  const wo = m.in_library ? 'in der Bibliothek' : 'bei der Quelle bekannt';
  return `${m.channel_name ? m.channel_name + ', ' : ''}${wo}`;
}

/**
 * TubeVault - Auswahl der Suche: Bereiche, Filter, Fundorte
 *
 * Die Kennungen sind die Werte des Backends (services/search: filters,
 * models); hier stehen nur die Namen für die Oberfläche. Eine Stelle für
 * Seite, Aufklappliste und Handy.
 */

export const SECTIONS = [
  { id: 'videos', label: 'Videos', icon: 'fa-film', hint: 'Wort in Titel, Kanal, Beschreibung, Kapiteln, Schlagwörtern, Notizen oder Liedtext' },
  { id: 'gesagt', label: 'Im Gesagten', icon: 'fa-comment-dots', hint: 'Textstellen aus Transkripten und Untertiteln, mit Sprung an die Stelle' },
  { id: 'kapitel', label: 'Kapitel', icon: 'fa-list-ol', hint: 'Kapitelüberschriften, mit Sprung an den Anfang des Kapitels' },
  { id: 'abos', label: 'Bei Abos', icon: 'fa-rss', hint: 'Neue Videos deiner Abos, die noch nicht geladen sind' },
  { id: 'kanaele', label: 'Kanäle', icon: 'fa-tv', hint: 'Kanäle nach Name, Beschreibung und Schlagwörtern' },
  { id: 'playlists', label: 'Playlists', icon: 'fa-list', hint: 'Eigene Playlists nach Name und Beschreibung' },
  { id: 'musik', label: 'Musik', icon: 'fa-music', hint: 'Eigene Musiksammlung: Titel, Künstler, Album, Genre, Liedtext' },
  { id: 'sinngemaess', label: 'Sinngemäß', icon: 'fa-wand-magic-sparkles', hint: 'Inhaltlich verwandt, ohne dass das Wort vorkommt' },
];
export const SOURCE_SECTION = { id: 'quelle', label: 'Bei der Quelle', icon: 'fa-globe', hint: 'Fragt die Quelle nur auf Wunsch und schont so die Abrufgrenze' };

export const LENGTHS = [
  { id: 'kurz', label: 'Kurz', hint: 'unter 4 Minuten' },
  { id: 'mittel', label: 'Mittel', hint: '4 bis 20 Minuten' },
  { id: 'lang', label: 'Lang', hint: '20 bis 60 Minuten' },
  { id: 'sehr_lang', label: 'Sehr lang', hint: 'über eine Stunde' },
];
export const PERIODS = [
  { id: 'woche', label: 'Letzte Woche' },
  { id: 'monat', label: 'Letzter Monat' },
  { id: 'jahr', label: 'Letztes Jahr' },
];
export const LOCATIONS = [
  { id: 'bibliothek', label: 'Bibliothek' },
  { id: 'archiv', label: 'Archiv' },
  { id: 'eigene', label: 'Eigene Videos' },
];
export const STATES = [
  { id: 'new', label: 'Ungesehen' },
  { id: 'started', label: 'Angefangen' },
  { id: 'finished', label: 'Gesehen' },
];
export const ORDERS = [
  { id: 'passend', label: 'Passendste', hint: 'Titel vor Kapitel vor Beschreibung, ganze Wörter vor Wortanfängen' },
  { id: 'neu', label: 'Neueste' },
  { id: 'alt', label: 'Älteste' },
  { id: 'lang', label: 'Längste' },
  { id: 'kurz', label: 'Kürzeste' },
  { id: 'aufrufe', label: 'Meiste Aufrufe' },
];
export const PRECISIONS = [
  { id: 'aus', label: 'Aus', hint: 'Nur nach Wörtern suchen' },
  { id: 'weit', label: 'Weit', hint: 'Auch lose Verwandtes - mehr Treffer' },
  { id: 'ausgewogen', label: 'Ausgewogen', hint: 'Verwandtes, ohne Beliebiges' },
  { id: 'genau', label: 'Genau', hint: 'Nur eng Verwandtes' },
  { id: 'sehr_genau', label: 'Sehr genau', hint: 'Nur sehr eng Passendes - wenige Treffer' },
];

/** Wo ein Video getroffen wurde: Name und Zeichen der Marke am Treffer */
export const FOUND = {
  titel: { label: 'Titel', icon: 'fa-heading' },
  kanal: { label: 'Kanal', icon: 'fa-tv' },
  kapitel: { label: 'Kapitel', icon: 'fa-list-ol' },
  schlagwort: { label: 'Schlagwort', icon: 'fa-tag' },
  notiz: { label: 'Notiz', icon: 'fa-note-sticky' },
  liedtext: { label: 'Liedtext', icon: 'fa-music' },
  beschreibung: { label: 'Beschreibung', icon: 'fa-align-left' },
  teilwort: { label: 'Teilwort', icon: 'fa-i-cursor' },
  gesagt: { label: 'Gesagtes', icon: 'fa-comment-dots' },
};
export const MUSIC_FOUND = { titel: 'Titel', kuenstler: 'Künstler', album: 'Album', genre: 'Genre', liedtext: 'Liedtext' };

/** Herkunft einer Textstelle im Gesagten (transcripts.KIND_LABELS) */
export const ORIGINS = {
  manual: 'Untertitel vom Autor',
  auto: 'Untertitel der Quelle',
  ai: 'KI-Transkript',
};

/** Suchsprache, wie sie auf der Seite erklärt wird (backend: services/search/query.py) */
export const SEARCH_RULES = [
  { code: '"Wortfolge"', text: 'genau diese Wörter hintereinander' },
  { code: '-Wort', text: 'Treffer mit diesem Wort weglassen' },
  { code: 'A oder B', text: 'eins von beiden reicht' },
  { code: 'kanal:Lesch', text: 'nur Kanäle mit diesem Namen' },
  { code: 'sprache:en', text: 'nur diese Sprache (auch sprache:englisch)' },
  { code: 'länge:>20', text: 'länger als 20 Minuten (auch <10, 10-30)' },
  { code: 'jahr:2024', text: 'hochgeladen in dem Jahr (auch 2020-2024)' },
  { code: 'in:archiv', text: 'nur Archiv (auch in:bibliothek, in:eigene)' },
];
export const SEARCHED = ['Titel', 'Kanal', 'Beschreibung', 'Schlagwörter', 'Notizen', 'Kapitel', 'Gesagtes', 'Liedtexte',
  'Abos und Feed', 'Kanäle', 'Playlists', 'Musik', 'Eigene Videos', 'Archiv'];

export const choiceLabel = (list, id) => list.find((c) => c.id === id)?.label || null;

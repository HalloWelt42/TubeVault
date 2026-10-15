// Kanäle (Abos): Medaillen, Merkmale, Filter, Sortierung und Zeitangaben -
// reine Funktionen und Tabellen für die Seite "Kanäle" und ihr Seitenblatt.
// Die Medaille selbst rechnet das Backend (services/channel_coverage.py):
// gezählt werden nur normale Videos, Live und Shorts nie.
import { formatDate, parseServerTime } from '../../utils/format.js';
import { VIDEO_QUALITIES } from '../../constants/qualities.js';

export const DEFAULT_DRIP = 3;                     // Vorgabe der Spalte drip_count im Backend
export const DRIP_CHOICES = [1, 3, 5, 10];          // Wahl im Seitenblatt (Entwurf)
export const QUICK_QUALITIES = ['', '720p', '1080p', 'best'];   // Wahl im Seitenblatt, '' = Standard

/** Medaillen: Name und Farben (Entwurf mockups/kanaele.html). */
export const MEDALS = {
  gold: { label: 'Gold', farbe: '#ffd54f', grund: 'rgba(255, 202, 40, 0.16)' },
  silver: { label: 'Silber', farbe: '#cfd8dc', grund: 'rgba(207, 216, 220, 0.16)' },
  bronze: { label: 'Bronze', farbe: '#e0a070', grund: 'rgba(215, 136, 80, 0.18)' },
};

// Schwellen wie im Backend (channel_coverage: BRONZE_SHARE, SILVER_SHARE, MIN_WANTED)
const MEDAL_STEPS = [['bronze', 0.8], ['silver', 0.95], ['gold', 1]];
const MIN_WANTED = 3;

/** Zahl deutsch mit Tausenderpunkt. */
export const num = (value) => Number(value || 0).toLocaleString('de-DE');

export const channelName = (sub) => sub.channel_name || sub.channel_id;
export const dripCount = (sub) => sub.drip_count || DEFAULT_DRIP;
export const qualityShort = (value) => (!value ? 'Standard' : value === 'best' ? 'Beste' : value);
export const isScanned = (sub) => sub.medal !== 'never-scanned';
export const medalOf = (sub) => MEDALS[sub.medal] || null;

/** Einträge fürs Aufklappmenü: Standard und alle Qualitäten, die aktuelle markiert. */
export function qualityItems(current, apply) {
  return [{ value: '', label: 'Standard aus den Einstellungen' }, ...VIDEO_QUALITIES].map((q) => ({
    icon: q.value ? 'fa-film' : 'fa-gear', label: q.label, hint: q.value === current ? 'gewählt' : '', run: () => apply(q.value),
  }));
}

/** Farben der Medaille als CSS-Variablen (leer ohne Medaille). */
export function medalStyle(sub) {
  const medal = medalOf(sub);
  return medal ? `--medaille: ${medal.farbe}; --medaille-grund: ${medal.grund}` : '';
}

// ── Abdeckung ──

/** Anteil der geladenen normalen Videos, 0 bis 1. */
export const coverageShare = (sub) => (sub.wanted_count ? sub.have_count / sub.wanted_count : 0);
/** Prozent abgerundet, damit nur Lückenloses 100 % zeigt. */
export const coveragePercent = (sub) => Math.floor(coverageShare(sub) * 100);
export const missingCount = (sub) => Math.max(0, (sub.wanted_count || 0) - (sub.have_count || 0));

/** Erklärung zum Überfahren der Abdeckung. */
export function coverageTitle(sub) {
  if (!sub.wanted_count) return 'Keine normalen Videos bekannt';
  const base = `${num(sub.have_count)} von ${num(sub.wanted_count)} normalen Videos geladen (${coveragePercent(sub)} %)`;
  const missing = missingCount(sub);
  const scan = isScanned(sub) ? '' : '. Noch nicht ganz gescannt: bekannt sind nur die neuesten Videos';
  return `${base}${missing ? `, ${num(missing)} ${missing === 1 ? 'fehlt' : 'fehlen'}` : ''}${scan}. Live und Shorts zählen nicht.`;
}

/** Nächste Medaille und wie viele Videos bis dorthin fehlen (null bei Gold). */
export function nextMedal(sub) {
  const { have_count: have, wanted_count: wanted } = sub;
  const step = MEDAL_STEPS.find(([, share]) => have / wanted < share);
  if (!step) return null;
  let need = 0;
  while ((have + need) / wanted < step[1]) need++;   // genau wie das Backend vergleicht
  return { label: MEDALS[step[0]].label, need };
}

const MEDAL_RULE = MEDAL_STEPS
  .map(([key, share]) => (share < 1 ? `${MEDALS[key].label} ab ${Math.round(share * 100)} %` : `${MEDALS[key].label} bei allen`))
  .join(', ');

/** Satz unter der Abdeckung im Seitenblatt: Regel und Weg zur nächsten Medaille. */
export function coverageNote(sub) {
  if (!isScanned(sub)) return 'Noch nicht ganz gescannt: bekannt sind nur die neuesten Videos. Eine Medaille gibt es nach dem Scan.';
  if (!sub.wanted_count) return 'Keine normalen Videos bekannt.';
  if (sub.wanted_count < MIN_WANTED) return 'Zu wenige Videos für eine Medaille.';
  const next = nextMedal(sub);
  if (!next) return `Lückenlos: alle ${num(sub.wanted_count)} Videos geladen.`;
  return `${MEDAL_RULE}. Noch ${num(next.need)} ${next.need === 1 ? 'Video' : 'Videos'} bis ${next.label}.`;
}

// ── Merkmale auf der Kachel: nur Eingeschaltetes und Auffälliges ──

/** [{ key, cls?, icon?, count?, text, title }] */
export function channelBadges(sub) {
  return [
    sub.new_videos > 0 && { key: 'neu', cls: 'neu', count: sub.new_videos, text: 'neu', title: 'Neue Videos bei den Abos, noch nicht geladen' },
    sub.auto_download && { key: 'auto', icon: 'fa-bolt', text: 'Auto', title: 'Neue Videos werden automatisch geladen' },
    sub.drip_enabled && (sub.drip_completed_at
      ? { key: 'drip', icon: 'fa-check', text: 'Drip fertig', title: 'Drip hat alle Videos geladen' }
      : { key: 'drip', icon: 'fa-droplet', count: dripCount(sub), text: 'am Tag', title: 'Lädt den Bestand nach und nach, nachts' }),
    sub.music_channel && { key: 'musik', cls: 'musik', icon: 'fa-music', text: 'Musik', title: 'Musikkanal: alle Videos zählen als Musik' },
    sub.download_quality && !sub.audio_only && { key: 'qualitaet', text: qualityShort(sub.download_quality), title: 'Eigene Qualität für die Downloads dieses Kanals' },
    sub.audio_only && { key: 'ton', icon: 'fa-headphones', text: 'Nur Ton', title: 'Lädt nur den Ton' },
    !sub.enabled && { key: 'aus', text: 'abgeschaltet', title: 'Wird nicht geprüft und lädt nichts' },
    sub.enabled && !sub.last_checked && { key: 'ungeprueft', cls: 'wartet', icon: 'fa-clock', text: 'noch nie geprüft', title: 'Wartet auf die erste Prüfung' },
    sub.error_count > 0 && { key: 'fehler', cls: 'fehler', icon: 'fa-triangle-exclamation', count: sub.error_count, text: 'Prüffehler', title: sub.last_error || 'Die Prüfung schlug fehl' },
  ].filter(Boolean);
}

// ── Filter ──

/** Filter der Steuerleiste; optional = nur zeigen, wenn es Treffer gibt. */
export const FILTERS = [
  { key: '', label: 'Alle', test: () => true },
  { key: 'auto', label: 'Auto-Download', icon: 'fa-bolt', test: (s) => s.auto_download, title: 'Kanäle, deren neue Videos automatisch geladen werden' },
  { key: 'drip', label: 'Drip', icon: 'fa-droplet', test: (s) => s.drip_enabled, title: 'Kanäle, die ihren Bestand nach und nach laden' },
  { key: 'musik', label: 'Musik', icon: 'fa-music', test: (s) => s.music_channel, title: 'Musikkanäle: alle Videos gelten als Musik' },
  { key: 'ohne-musik', label: 'Ohne Musik', test: (s) => !s.music_channel, noCount: true, title: 'Alle Kanäle außer den Musikkanälen' },
  { key: 'nie-gescannt', label: 'Nie gescannt', test: (s) => !isScanned(s), title: 'Noch nie ganz gescannt: bekannt sind nur die neuesten Videos, eine Medaille gibt es erst danach' },
  { key: 'aus', label: 'Abgeschaltet', test: (s) => !s.enabled, title: 'Werden nicht geprüft und laden nichts' },
  { key: 'ungeprueft', label: 'Noch nie geprüft', icon: 'fa-clock', optional: true, test: (s) => !s.last_checked, title: 'Warten auf ihre erste Prüfung auf neue Videos' },
  { key: 'fehler', label: 'Prüffehler', icon: 'fa-triangle-exclamation', optional: true, test: (s) => s.error_count > 0, title: 'Die letzte Prüfung auf neue Videos schlug fehl' },
  { key: 'probleme', label: 'Problem-Videos', icon: 'fa-circle-exclamation', optional: true, test: (s) => s.problem_count > 0, title: 'Kanäle mit Videos, die sich dauerhaft nicht laden ließen' },
];

export const MEDAL_FILTERS = Object.entries(MEDALS).map(([key, medal]) => ({
  key, label: medal.label, icon: 'fa-medal', style: `--medaille: ${medal.farbe}`, test: (s) => s.medal === key,
  title: `Kanäle mit der Medaille ${medal.label}. ${MEDAL_RULE}; gezählt werden nur normale Videos.`,
}));

const ALL_FILTERS = [...FILTERS, ...MEDAL_FILTERS];

/** Anzahl je Filter: { key: count }. */
export const filterCounts = (subs) => Object.fromEntries(ALL_FILTERS.map((f) => [f.key, subs.filter(f.test).length]));

/** Nach Filter und Suchwörtern (Name oder Kanal-ID) auswählen. */
export function filterChannels(subs, { filter = '', search = '' } = {}) {
  const test = ALL_FILTERS.find((f) => f.key === filter)?.test || (() => true);
  const words = search.trim().toLocaleLowerCase('de').split(/\s+/).filter(Boolean);
  return subs.filter((s) => test(s)
    && words.every((w) => `${s.channel_name || ''} ${s.channel_id}`.toLocaleLowerCase('de').includes(w)));
}

// ── Sortierung ──

export const SORTS = [
  { key: 'name', label: 'Name', title: 'Alphabetisch nach Kanalname' },
  { key: 'neu', label: 'Neue Videos', title: 'Kanäle mit den meisten neuen Videos zuerst' },
  { key: 'abdeckung', label: 'Abdeckung', title: 'Am vollständigsten geladene Kanäle zuerst, nie gescannte zuletzt' },
  { key: 'hochgeladen', label: 'Zuletzt hochgeladen', title: 'Kanäle mit dem neuesten Video zuerst' },
];

const byName = (a, b) => channelName(a).localeCompare(channelName(b), 'de', { sensitivity: 'base' });
const ORDER = {
  name: byName,
  neu: (a, b) => (b.new_videos || 0) - (a.new_videos || 0),
  abdeckung: (a, b) => (isScanned(b) - isScanned(a)) || (coverageShare(b) - coverageShare(a)),
  hochgeladen: (a, b) => (b.last_video_date || '').localeCompare(a.last_video_date || ''),
};

/** Sortierte Kopie, bei Gleichstand nach Name. */
export function sortChannels(subs, key = 'name') {
  const by = ORDER[key] || byName;
  return [...subs].sort((a, b) => by(a, b) || byName(a, b));
}

// ── Zeitangaben ──

/** Tag "03.06.2026", leer ohne Angabe. */
export const dayText = (value) => (value ? formatDate(value) : '');

/** Zeitpunkt kurz "14.10. 08:17" oder "noch nie". */
export function momentText(value) {
  if (!value) return 'noch nie';
  const date = parseServerTime(value);
  return `${date.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })} ${date.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}`;
}

/** Wochentag und Uhrzeit "Do., 03:12" für den nächsten Drip-Lauf. */
export const runText = (value) => (value
  ? parseServerTime(value).toLocaleString('de-DE', { weekday: 'short', hour: '2-digit', minute: '2-digit' }) : '');

/** Prüfabstand "30 Min.", "6 Std." oder "3 Tage". */
export function intervalText(seconds) {
  if (!seconds) return '';
  if (seconds < 3600) return `${Math.round(seconds / 60)} Min.`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} Std.`;
  const days = Math.round(seconds / 86400);
  return `${days} ${days === 1 ? 'Tag' : 'Tage'}`;
}

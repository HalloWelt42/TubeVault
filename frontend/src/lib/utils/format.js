/**
 * TubeVault -  Format Utilities v1.5.52
 * Zentrale Formatierungsfunktionen -  keine lokalen Duplikate mehr nötig
 * © HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
 * SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
 */

/**
 * Dauer als kompaktes Zeitformat: 1:23:45 oder 3:45
 */
export function formatDuration(seconds) {
  if (!seconds || seconds < 0) return '0:00';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

/**
 * Dauer als lesbarer Text: "2 Std 15 Min" oder "45 Min"
 */
export function formatDurationLong(seconds) {
  if (!seconds) return '–';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h} Std ${m} Min`;
  return `${m} Min`;
}

/**
 * Bytes als lesbare Größe: 1.5 GB, 320 MB, 4.2 KB
 */
export function formatSize(bytes) {
  if (!bytes || bytes < 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  let size = bytes;
  while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
  return `${size.toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
}

/**
 * Stream-Größe: Kompakteres Format für Stream-Dialoge (nur MB/GB)
 */
export function formatStreamSize(bytes) {
  if (!bytes) return '?';
  if (bytes > 1073741824) return (bytes / 1073741824).toFixed(1) + ' GB';
  return (bytes / 1048576).toFixed(0) + ' MB';
}

/**
 * Datum als deutsches Format: 15.03.2026
 */
export function formatDate(dateStr) {
  if (!dateStr) return '–';
  const d = new Date(dateStr);
  return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

/**
 * Relatives Datum: "vor 5 Min.", "vor 3 Tagen", etc.
 */
export function formatDateRelative(dateStr) {
  if (!dateStr) return '–';
  const d = new Date(dateStr);
  const now = new Date();
  const diff = Math.floor((now - d) / 1000);
  if (diff < 60) return 'gerade eben';
  if (diff < 3600) return `vor ${Math.floor(diff / 60)} Min.`;
  if (diff < 86400) return `vor ${Math.floor(diff / 3600)} Std.`;
  if (diff < 604800) return `vor ${Math.floor(diff / 86400)} Tagen`;
  return formatDate(dateStr);
}

/**
 * Aufrufzahlen: 1.2 Mio., 5.3K, etc.
 */
export function formatViews(count) {
  if (!count) return '–';
  if (count >= 1_000_000_000) return `${(count / 1_000_000_000).toFixed(1)} Mrd.`;
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)} Mio.`;
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)}K`;
  return String(count);
}

/**
 * Text kürzen mit Ellipsis
 */
export function truncate(text, maxLen = 100) {
  if (!text || text.length <= maxLen) return text || '';
  return text.slice(0, maxLen) + '…';
}

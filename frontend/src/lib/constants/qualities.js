/**
 * TubeVault – Video-Qualitäten (zentral)
 *
 * Einheitliche Liste für alle Qualitäts-Dropdowns (Dashboard, Subscriptions,
 * Downloads-Seite etc.). Bei Änderung nur hier bearbeiten.
 *
 * Werte (value) werden 1:1 an das Backend übergeben und dort vom
 * download_service._pick_progressive / _pick_adaptive_video ausgewertet.
 */

/** Standard-Qualitäten für Video-Downloads. */
export const VIDEO_QUALITIES = [
  { value: 'best',  label: 'Beste verfügbar' },
  { value: '2160p', label: '2160p (4K)' },
  { value: '1440p', label: '1440p (2K)' },
  { value: '1080p', label: '1080p (Full HD)' },
  { value: '720p',  label: '720p (HD)' },
  { value: '480p',  label: '480p' },
  { value: '360p',  label: '360p' },
  { value: '240p',  label: '240p' },
  { value: '144p',  label: '144p' },
];

/** Default für neue Downloads, wenn der Nutzer nichts explizit wählt. */
export const DEFAULT_QUALITY = 'best';

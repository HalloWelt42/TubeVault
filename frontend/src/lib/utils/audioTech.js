// Technische Angaben zum Ton eines Titels, kurz und deutsch. Verlustfreie
// Dateien nennen ihre Bittiefe ("FLAC · 16 Bit · 44,1 kHz"), alles andere
// die Bitrate ("OPUS · 160 kbit/s · 48 kHz"). Eine Stelle für die
// Abspielleiste am Rechner und den Spieler am Handy.
import { isFile } from './musicTrack.js';

/** Format in Großbuchstaben (FLAC, OPUS ...), sonst null */
export const codecName = (info) => (info?.codec ? String(info.codec).toUpperCase() : null);

/** Angaben ohne Format: Bittiefe (verlustfrei) oder Bitrate, dazu die Abtastrate */
export function audioDetails(info) {
  if (!info) return [];
  const parts = [];
  if (info.bit_depth) parts.push(`${info.bit_depth} Bit`);
  else if (info.bitrate) parts.push(`${Math.round(info.bitrate / 1000)} kbit/s`);
  if (info.sample_rate) parts.push(`${(info.sample_rate / 1000).toLocaleString('de-DE')} kHz`);
  return parts;
}

/** "FLAC · 16 Bit · 44,1 kHz" - was die Datei hergibt, ohne Format leer */
export function audioQuality(info) {
  const codec = codecName(info);
  return codec ? [codec, ...audioDetails(info)].join(' · ') : '';
}

/** Herkunft eines Titels: Datei der eigenen Sammlung oder Video */
export function trackOrigin(track) {
  return isFile(track) ? { label: 'Sammlung', icon: 'fa-hard-drive' } : { label: 'Video', icon: 'fa-film' };
}

/** Kurzform für Listen: Format der Datei (FLAC, MP3 ...), bei Videos "Video" */
export function trackFormat(track) {
  if (!isFile(track)) return 'Video';
  return codecName(track) || 'Sammlung';
}

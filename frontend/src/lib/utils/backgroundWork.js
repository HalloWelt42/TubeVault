/**
 * TubeVault - Hintergrundarbeiten (/api/system/background): Fortschritt und
 * Schalter. Genutzt von der Anzeige in der Statusleiste und der Übersicht.
 */
import { api } from '../api/client.js';

/** Fortschritt in ganzen Prozent oder null, wenn die Arbeit keinen kennt */
export function workPercent(item) {
  return item.progress === null || item.progress === undefined ? null : Math.round(item.progress * 100);
}

/** Angehaltene Arbeit fortsetzen, laufende anhalten (nur mit switch_key) */
export function switchWork(item) {
  return api.updateSetting(item.switch_key, item.paused ? 'true' : 'false');
}

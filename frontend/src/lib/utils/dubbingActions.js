/**
 * TubeVault – Nachvertonung vormerken (gemeinsame Aktion)
 * Für Einzelvideo, Bibliothek und Archiv dieselbe Rückmeldung: wie viele
 * vorgemerkt wurden und warum etwas übersprungen wurde.
 */
import { get } from 'svelte/store';
import { api } from '../api/client.js';
import { settings } from '../stores/settings.js';
import { toast } from '../stores/notifications.js';

/** Ist die Erweiterung eingeschaltet? (reaktiv nutzbar über $settings) */
export const dubbingEnabled = (current = get(settings)) => current['dub.enabled'] === 'true';

export async function enqueueForDubbing(videoIds) {
  try {
    const result = await api.enqueueDubbing(videoIds);
    const queued = result.queued.length;
    const reasons = Object.values(result.skipped);
    if (queued > 0) {
      toast.success(queued === 1 ? 'Zur Nachvertonung vorgemerkt' : `${queued} Videos zur Nachvertonung vorgemerkt`);
    }
    if (reasons.length === 1 && videoIds.length === 1) {
      toast.info(`Nicht vorgemerkt: ${reasons[0]}`);
    } else if (reasons.length > 0) {
      // Häufigsten Grund nennen, statt jede Zeile einzeln zu melden
      const tally = {};
      reasons.forEach(r => { tally[r] = (tally[r] || 0) + 1; });
      const [reason, count] = Object.entries(tally).sort((a, b) => b[1] - a[1])[0];
      toast.info(`${reasons.length} übersprungen (${count}x: ${reason})`);
    }
    return result;
  } catch (e) {
    toast.error(e.message);
    return null;
  }
}

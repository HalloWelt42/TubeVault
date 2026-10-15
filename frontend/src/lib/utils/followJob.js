// Einem Hintergrundauftrag folgen, bis er fertig, gescheitert oder
// abgebrochen ist. Nur der Auftrag weiß, wie es ausging - geraten wird nicht.
// Gibt die Abmeldung zurück (beim Verlassen der Seite aufrufen).
import { api } from '../api/client.js';

const POLL_MS = 2000;
const GONE_AFTER = 5;      // so oft hintereinander nicht lesbar: Auftrag gilt als beendet (aufgeräumt)

/**
 * @param {number} jobId
 * @param {{ onUpdate?: (job) => void, onEnd: (job|null) => void }} handlers
 *   onEnd bekommt den beendeten Auftrag, null wenn er nicht mehr lesbar ist
 */
export function followJob(jobId, { onUpdate = () => {}, onEnd }) {
  let stopped = false;
  let misses = 0;
  const stop = () => { stopped = true; clearInterval(timer); };
  const timer = setInterval(async () => {
    let job;
    try { job = await api.getJob(jobId); misses = 0; }
    catch { if (++misses >= GONE_AFTER && !stopped) { stop(); onEnd(null); } return; }
    if (stopped) return;
    if (['queued', 'active'].includes(job.status)) { onUpdate(job); return; }
    stop();
    onEnd(job);
  }, POLL_MS);
  return stop;
}

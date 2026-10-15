<!--
  Systemauftrag in der Warteschlange (Kanalprüfung, Kanal-Scan, Import ...).
  Kanal-Scans zeigen ihre Phasen und eine geschätzte Restzeit.
-->
<script module>
  // Restzeit eines Kanal-Scans aus dem bisherigen Tempo (über alle Zeilen hinweg gemerkt)
  const scanTracker = {};
  function scanEta(jobId, foundTotal, estTotal) {
    if (!estTotal || estTotal <= 0 || foundTotal <= 0) return null;
    if (!scanTracker[jobId]) scanTracker[jobId] = { start: Date.now(), startCount: foundTotal };
    const t = scanTracker[jobId];
    const elapsed = (Date.now() - t.start) / 1000;
    const processed = foundTotal - t.startCount;
    if (processed <= 5 || elapsed < 3) return null;
    const seconds = Math.ceil(Math.max(0, estTotal - foundTotal) / (processed / elapsed));
    if (seconds > 7200) return null;
    const min = Math.floor(seconds / 60);
    return min > 0 ? `noch ${min} Min ${seconds % 60} s` : `noch ${seconds} s`;
  }

  const TYPES = {
    channel_scan: ['fa-satellite-dish', 'Kanal-Scan'],
    rss_cycle: ['fa-rss', 'Kanalprüfung'],
    rss_poll: ['fa-rss', 'Kanalprüfung'],
    import: ['fa-file-import', 'Import'],
    avatar_fetch: ['fa-image', 'Kanalbild'],
    archive_scan: ['fa-box-archive', 'Archiv-Scan'],
    cleanup: ['fa-broom', 'Aufräumen'],
    deep_scan: ['fa-magnifying-glass', 'Tiefen-Scan'],
    enrich: ['fa-wand-magic-sparkles', 'Anreichern'],
  };
  const PHASES = {
    connecting: 'Verbinde', metadata: 'Metadaten', precount: 'Vorschau', videos: 'Videos',
    shorts: 'Shorts', live: 'Livestreams', saving: 'Speichern',
  };
</script>

<script>
  import { formatDateRelative } from '../../utils/format.js';
  import { statusOf } from './jobStatus.js';

  let { job, onCancel = () => {} } = $props();

  let meta = $derived(job.metadata || {});
  let type = $derived(TYPES[job.type] || ['fa-circle', job.type]);
  let status = $derived(statusOf(job.status));
  let cancellable = $derived(job.status === 'active' || job.status === 'queued');

  // Fortschritt eines Kanal-Scans: Speichern zählt Einträge, sonst Fundstücke gegen die Schätzung
  let scan = $derived.by(() => {
    if (job.type !== 'channel_scan' || job.status !== 'active') return null;
    const found = (meta.video_count || 0) + (meta.short_count || 0) + (meta.live_count || 0);
    const est = meta.estimated_total || 0;
    const phase = meta.phase || '';
    const showEst = est > 0 && est >= found && !meta.precount_exceeded;
    const pct = phase === 'saving' && meta.save_total > 0 ? (meta.save_current / meta.save_total) * 100
      : phase === 'precount' ? Math.min(((meta.precount_running || 0) / Math.max((meta.precount_running || 0) + 100, 500)) * 100, 90)
      : showEst ? Math.min((found / est) * 100, 99) : job.progress * 100;
    const parts = [];
    if (phase === 'saving' && meta.save_total > 0) parts.push(`Speichere ${meta.save_current} von ${meta.save_total}`);
    else if (phase === 'precount') parts.push(`Zähle Videos ${meta.precount_running || ''}`);
    else if (phase === 'connecting' || phase === 'metadata') parts.push(job.description || 'Verbinde');
    else {
      if (meta.video_count) parts.push(`${meta.video_count} Videos`);
      if (meta.short_count) parts.push(`${meta.short_count} Shorts`);
      if (meta.live_count) parts.push(`${meta.live_count} Live`);
      if (meta.precount_exceeded) parts.push(`${meta.precount_extra} mehr als erwartet`);
      else if (showEst) parts.push(`von etwa ${est}`);
      if (meta.batch_saved) parts.push(`${meta.batch_saved} gesichert`);
    }
    const eta = ['videos', 'shorts', 'live'].includes(phase) ? scanEta(job.id, found, est) : null;
    return { pct, text: parts.join(', '), phase: PHASES[phase] || phase, eta };
  });
</script>

<div class="auftrag">
  <div class="vorschau"><i class="fa-solid {type[0]}"></i></div>
  <div class="text">
    <div class="titel"><span class="art">{type[1]}</span> {job.title || ''}</div>
    <div class="zeile2">
      <span class="tv-zustand {status.css}"><i class="fa-solid {job.status === 'active' ? 'fa-gear fa-spin' : status.icon}"></i> {status.label}</span>
      {#if scan}
        <span>{scan.text}</span>{#if scan.phase}<span>{scan.phase}</span>{/if}{#if scan.eta}<span class="zahl">{scan.eta}</span>{/if}
      {:else if job.description && job.status !== 'queued'}
        <span>{job.description}</span>
      {/if}
      {#if job.completed_at}<span>{formatDateRelative(job.completed_at)}</span>{/if}
    </div>
    {#if scan}
      <div class="balken"><b style:width="{scan.pct.toFixed(1)}%"></b></div>
    {:else if job.status === 'active' && job.progress > 0}
      <div class="balken"><b style:width="{(job.progress * 100).toFixed(1)}%"></b></div>
    {/if}
  </div>
  <div class="knoepfe">
    {#if cancellable}
      <button class="tv-knopf ohne symbol klein" onclick={() => onCancel(job.id)} title="Abbrechen"><i class="fa-solid fa-xmark"></i></button>
    {/if}
  </div>
</div>

<style>
  .auftrag { display: grid; grid-template-columns: 128px minmax(0, 1fr) auto; gap: var(--tv-a3); align-items: center; padding: var(--tv-a3); border-radius: var(--tv-ecke); }
  .auftrag + :global(.auftrag) { margin-top: 2px; }
  .auftrag:hover { background: var(--tv-flaeche); }
  .vorschau { aspect-ratio: 16 / 9; display: grid; place-items: center; background: var(--tv-mulde); border-radius: var(--tv-ecke-klein); color: var(--tv-text-3); font-size: 22px; }
  .text { min-width: 0; display: flex; flex-direction: column; gap: 6px; }
  .titel { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .titel .art { color: var(--tv-text-3); font-weight: 500; }
  .zeile2 { display: flex; gap: var(--tv-a3); align-items: center; flex-wrap: wrap; font-size: var(--tv-gr-klein); color: var(--tv-text-2); }
  .balken { height: 6px; background: var(--tv-mulde); border-radius: 1px; overflow: hidden; }
  .balken b { display: block; height: 100%; background: var(--tv-info); }
</style>

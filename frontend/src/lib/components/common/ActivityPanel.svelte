<!--
  TubeVault -  ActivityPanel v1.8.65
  Unified Bar (ersetzt Footer + altes ActivityPanel)
  Detail-Panel mit Phasen-Fortschritt, Pause/Resume, Cleanup
  © HalloWelt42 -  Private Nutzung
-->
<script>
  import { api, createActivitySocket, FE_VERSION } from '../../api/client.js';
  import { formatDateRelative } from '../../utils/format.js';
  import { feedVersion } from '../../stores/app.js';
  import { toast } from '../../stores/notifications.js';
  import DownloadProgress from './DownloadProgress.svelte';
  import MiniProgress from './MiniProgress.svelte';

  // Zustand
  let jobs = $state([]);
  let stats = $state({ active: 0, queued: 0, done: 0, errors: 0, paused: false, pause_reason: '' });
  let expanded = $state(false);
  let activitySocket = $state(null);
  // Live WS-Status -  EXAKT wie liveStatus in Downloads.svelte
  let liveStatus = $state({});

  // Scan-ETA Tracking
  const scanTracker = {};
  function getScanEta(jobId, foundTotal, estTotal) {
    if (!estTotal || estTotal <= 0 || foundTotal <= 0) return null;
    if (!scanTracker[jobId]) scanTracker[jobId] = { start: Date.now(), startCount: foundTotal };
    const t = scanTracker[jobId];
    const elapsed = (Date.now() - t.start) / 1000;
    const processed = foundTotal - t.startCount;
    if (processed <= 5 || elapsed < 3) return null; // Zu früh für sinnvolle Schätzung
    const rate = processed / elapsed;
    const remaining = Math.max(0, estTotal - foundTotal);
    const etaSec = Math.ceil(remaining / rate);
    if (etaSec > 7200) return null; // >2h = unsinnig
    const min = Math.floor(etaSec / 60);
    const sec = etaSec % 60;
    return min > 0 ? `~${min}m ${sec}s` : `~${sec}s`;
  }

  // System-Status (Service-LEDs)
  let backendVersion = $state('…');
  let dbVersion = $state('?');
  let backendOk = $state(false);
  let rssRunning = $state(false);
  let rateWarning = $state(false);
  let rateLimiterDisabled = $state(false);
  let ytOk = $state(true);
  let ytBlockCount = $state(0);
  let rydOk = $state(false);

  // Cooldown-Timer
  let cooldownState = $state({ active: false, remaining: 0, cooldown: 30, base: 30 });
  let cooldownRemaining = $state(0);

  // hh:mm:ss Formatter
  function fmtTime(secs) {
    if (secs <= 0) return '';
    const s = Math.round(secs);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
    if (m > 0) return `${m}:${String(sec).padStart(2, '0')}`;
    return `0:${String(sec).padStart(2, '0')}`;
  }

  // Cooldown-Countdown lokal heruntertakten
  $effect(() => {
    if (cooldownRemaining > 0) {
      const iv = setInterval(() => {
        cooldownRemaining = Math.max(0, cooldownRemaining - 1);
      }, 1000);
      return () => clearInterval(iv);
    }
  });

  // Icon-Map für Job-Typen
  const typeIcons = {
    download: 'fa-download', channel_scan: 'fa-satellite-dish',
    rss_cycle: 'fa-satellite-dish', rss_poll: 'fa-satellite-dish',
    playlist_fetch: 'fa-list-ul', playlist_videos: 'fa-list-ol', playlist_import: 'fa-file-import',
    import: 'fa-file-import', avatar_fetch: 'fa-image',
    archive_scan: 'fa-box-archive', cleanup: 'fa-broom',
  };

  // Emoji-Strip (Lucide Icons statt Emojis)
  function strip(text) {
    if (!text) return '';
    return text.replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{FE0E}-\u{FE0F}\u{200D}\u{2B05}-\u{2B55}\u{231A}-\u{231B}\u{23E9}-\u{23FA}\u{2328}\u{2764}\u{2714}-\u{2716}\u{274C}-\u{274E}]/gu, '').trim();
  }

  // Titel-Anzeige: Titel wenn vorhanden, sonst YouTube-ID
  function displayTitle(job) {
    const title = strip(job.title);
    if (title && title !== job.metadata?.video_id) return title;
    return job.metadata?.video_id || title || `Job #${job.id}`;
  }

  function isIdOnly(job) {
    const title = strip(job.title);
    return !title || title === job.metadata?.video_id;
  }

  // YouTube-ID für Tooltip
  function videoId(job) {
    return job.metadata?.video_id || '';
  }

  // ─── Daten laden ──────────────────────────────────

  async function loadJobs() {
    try {
      const [jobList, jobStats] = await Promise.all([
        api.getJobs({ limit: 50 }),
        api.getJobStats(),
      ]);
      // Immer neues Array zuweisen (wie queue = await api.getQueue() in Downloads.svelte)
      jobs = Array.isArray(jobList) ? jobList : [];
      const sKey = s => `${s.active}:${s.queued}:${s.done}:${s.errors}:${s.parked}:${s.paused}`;
      if (sKey(stats) !== sKey(jobStats)) stats = jobStats;
    } catch {}
  }

  async function pollSystemStatus() {
    try {
      const s = await api.getStatus();
      backendVersion = s.version || '?';
      dbVersion = s.db_version || '?';
      backendOk = true;
      rssRunning = s.services?.rss?.running ?? s.rss?.worker_running ?? false;
      rateWarning = s.rate_limiter_warning ?? false;
      rateLimiterDisabled = s.rate_limiter_disabled ?? false;
      ytOk = s.services?.youtube?.ok ?? true;
      ytBlockCount = s.services?.youtube?.block_count ?? 0;
      rydOk = s.services?.ryd?.ok ?? false;
      // Cooldown-State aus Status (Fallback wenn WS nicht verbunden)
      if (s.cooldown) {
        cooldownState = {
          active: s.cooldown.cooldown_active ?? false,
          remaining: s.cooldown.cooldown_remaining ?? 0,
          cooldown: s.cooldown.cooldown ?? 30,
          base: s.cooldown.cooldown_base ?? 30,
        };
        if (s.cooldown.cooldown_active && s.cooldown.cooldown_remaining > 0) {
          cooldownRemaining = s.cooldown.cooldown_remaining;
        }
      }
    } catch {
      backendOk = false;
      backendVersion = '?';
    }
  }

  // ─── WebSocket-Handler ────────────────────────────

  function handleProgressMessage(msg) {
    const id = msg.job_id || msg.queue_id;
    if (!id) return;
    // Svelte 5: Proxy-Mutation reicht für Property-Tracking
    liveStatus[id] = msg;
    // ZUSÄTZLICH jobs-Referenz erneuern → activeJobs recalculated
    // → each-Block re-evaluiert → const live liest neuen liveStatus
    jobs = [...jobs];
  }

  function handleJobUpdate(msg) {
    if (!msg?.type) return;
    // Feed-Update
    if (msg.type === 'feed_updated') {
      feedVersion.update(v => v + 1);
      if (msg.new_videos > 0) toast(`${msg.new_videos} neue Videos im Feed`, 'success');
      return;
    }
    // Cleanup → alles neu laden
    if (msg.type === 'cleanup' || msg.job?.type === 'cleanup') { loadJobs(); return; }
    // Pause/Resume Events
    if (msg.type === 'queue_paused') {
      stats = { ...stats, paused: true, pause_reason: msg.reason || 'user' };
      return;
    }
    if (msg.type === 'queue_resumed') {
      stats = { ...stats, paused: false, pause_reason: '' };
      return;
    }
    if (msg.type !== 'job_update' || !msg.job) return;

    const updated = msg.job;
    const idx = jobs.findIndex(j => j.id === updated.id);
    if (idx >= 0) {
      jobs[idx] = updated;
      jobs = [...jobs];
    } else {
      jobs = [updated, ...jobs];
    }

    // Queue aktualisieren wenn done/error (wie Downloads.svelte)
    if (['done', 'error', 'cancelled'].includes(updated.status)) {
      setTimeout(loadJobs, 500);
    }
  }

  // ─── Aktionen ─────────────────────────────────────

  async function cancelJob(id) {
    try {
      await api.cancelJob(id);
      const i = jobs.findIndex(j => j.id === id);
      if (i >= 0) { jobs[i] = { ...jobs[i], status: 'cancelled' }; jobs = [...jobs]; }
      // Stats sofort aktualisieren
      setTimeout(loadJobs, 500);
    } catch {}
  }

  async function unparkJob(id) {
    try {
      await api.unparkJob(id);
      const i = jobs.findIndex(j => j.id === id);
      if (i >= 0) { jobs[i] = { ...jobs[i], status: 'queued' }; jobs = [...jobs]; }
      toast('Zurück in Queue', 'success');
      setTimeout(loadJobs, 500);
    } catch {}
  }

  async function cleanupDone() {
    try {
      await api.cleanupAllJobs();
      toast('Queue aufgeräumt', 'success');
      await loadJobs();
    } catch {}
  }

  async function togglePause() {
    try {
      if (stats.paused) {
        await api.resumeQueue();
        stats = { ...stats, paused: false, pause_reason: '' };
        toast('Queue fortgesetzt', 'success');
      } else {
        await api.pauseQueue('user');
        stats = { ...stats, paused: true, pause_reason: 'user' };
        toast('Queue pausiert', 'info');
      }
    } catch {}
  }

  async function resetRateLimit() {
    try {
      await api.resetRateLimit();
      rateWarning = false;
      if (stats.paused && stats.pause_reason === 'rate_limit') {
        stats = { ...stats, paused: false, pause_reason: '' };
      }
      toast('Rate-Limit zurückgesetzt', 'success');
      await pollSystemStatus();
    } catch {}
  }

  async function toggleRateLimit() {
    try {
      const res = await api.toggleRateLimit();
      rateLimiterDisabled = res.disabled;
      toast(res.disabled ? 'Rate-Limiter deaktiviert' : 'Rate-Limiter aktiviert', 'info');
      await pollSystemStatus();
    } catch {}
  }

  // ─── Abgeleitete Listen ───────────────────────────

  let activeJobs = $derived(jobs.filter(j => j.status === 'active'));

  // Live-Status Lookup -  EXAKT wie in Downloads.svelte
  function getLive(jobId) {
    return liveStatus[jobId] || null;
  }
  let queuedJobs = $derived(jobs.filter(j => j.status === 'queued').slice(0, 10));
  let moreQueued = $derived(Math.max(0, (stats.queued || 0) - queuedJobs.length));
  let doneJobs = $derived(
    jobs.filter(j => ['done', 'error', 'cancelled', 'parked'].includes(j.status))
      .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || '')).slice(0, 10)
  );
  let hasCleanable = $derived(stats.done > 0 || stats.errors > 0 || stats.parked > 0);

  function getQueuePositions() {
    const positions = {};
    let pos = activeJobs.length + 1;
    for (const j of queuedJobs) { positions[j.id] = pos++; }
    return positions;
  }

  // ─── Lifecycle ────────────────────────────────────

  let stackEl = $state(null);

  // ActivityPanel-Höhe als CSS-Variable auf :root setzen (für playlist-sidebar bottom)
  $effect(() => {
    if (!stackEl) return;
    const ro = new ResizeObserver(([entry]) => {
      const h = Math.round(entry.contentRect.height);
      document.documentElement.style.setProperty('--activity-panel-height', h + 'px');
    });
    ro.observe(stackEl);
    return () => ro.disconnect();
  });

  $effect(() => {
    loadJobs();
    pollSystemStatus();
    const jobIv = setInterval(loadJobs, 2000);
    const sysIv = setInterval(pollSystemStatus, 10000);
    activitySocket = createActivitySocket((msg) => {
      // Cooldown-Timer (von download_service._broadcast_cooldown)
      if (msg.type === 'cooldown') {
        cooldownState = {
          active: msg.cooldown_active,
          remaining: msg.cooldown_remaining,
          cooldown: msg.cooldown,
          base: msg.cooldown_base,
        };
        cooldownRemaining = msg.cooldown_remaining;
        return;
      }
      // Download-Progress (einheitlich mit type-Feld)
      if (msg.type === 'download_progress' || (msg.job_id && msg.stage)) {
        handleProgressMessage(msg);
      }
      // Job-Updates (von job_service.notify)
      handleJobUpdate(msg);
    });
    return () => {
      clearInterval(jobIv);
      clearInterval(sysIv);
      activitySocket?.close();
    };
  });
</script>

<!-- ═══ Bottom Stack: Detail Panel + Unified Bar ═══ -->
<div class="bottom-stack" class:paused={stats.paused} bind:this={stackEl}>

  <!-- Detail Panel (aufklappbar) -->
  {#if expanded}
    <div class="detail">
      <div class="detail-inner">

        <!-- Pause-Banner -->
        {#if stats.paused}
          <div class="pause-banner">
            <i class="fa-solid {stats.pause_reason === 'rate_limit' ? 'fa-shield-halved' : 'fa-pause-circle'}"></i>
            <div class="pause-info">
              <div class="pause-title">
                Queue pausiert{stats.pause_reason === 'rate_limit' ? ' -  YouTube Rate-Limit' : ''}
              </div>
              <div class="pause-detail">
                {stats.pause_reason === 'rate_limit'
                  ? 'Automatisch pausiert · Laufende Jobs werden fertig'
                  : 'Keine neuen Jobs · Laufende Jobs werden fertig'}
              </div>
            </div>
            <button class="pause-resume" onclick={togglePause}>
              <i class="fa-solid fa-play"></i> Fortsetzen
            </button>
          </div>
        {/if}

        <!-- Cooldown-Banner -->
        {#if cooldownRemaining > 0 && !stats.paused}
          <div class="cooldown-banner">
            <i class="fa-solid fa-hourglass-half"></i>
            <div class="cooldown-info">
              <span class="cooldown-timer">{fmtTime(cooldownRemaining)}</span>
              <span class="cooldown-label">bis zum nächsten Job</span>
            </div>
            {#if cooldownState.cooldown > cooldownState.base}
              <span class="cooldown-multi">×{Math.round(cooldownState.cooldown / cooldownState.base)}</span>
            {/if}
          </div>
        {/if}

        <!-- Aktive Jobs: voller Phasen-Fortschritt -->
        {#each activeJobs as job (job.id)}
          {@const live = getLive(job.id)}
          {@const progress = live?.progress ?? job.progress ?? 0}
          {@const stage = live?.stage || 'resolving'}
          {@const stageLabel = live?.stage_label || ''}
          {@const phases = live?.phases || null}
          <div class="ji-active" class:fading={stats.paused}>
            <div class="ji-active-top">
              <i class="fa-solid {typeIcons[job.type] || 'fa-circle'}" style="color:var(--status-info)"></i>
              <span class="ji-active-title" class:is-id={isIdOnly(job)} title={videoId(job)}>
                {displayTitle(job)}
              </span>
              <button class="ji-cancel" onclick={() => cancelJob(job.id)} title="Abbrechen">
                <i class="fa-solid fa-xmark"></i>
              </button>
            </div>
            {#if job.type === 'download'}
              <div class="ji-active-dl">
                <DownloadProgress data={{
                  progress,
                  stage,
                  stage_label: stageLabel,
                  phases,
                }} />
              </div>
            {:else if job.type === 'channel_scan'}
              <!-- Kanalscan: X/Y Fortschritt mit Phasen -->
              {@const meta = job.metadata || {}}
              {@const videoCount = meta.video_count || 0}
              {@const shortCount = meta.short_count || 0}
              {@const liveCount = meta.live_count || 0}
              {@const foundTotal = videoCount + shortCount + liveCount}
              {@const estTotal = meta.estimated_total || 0}
              {@const precount = meta.precount || 0}
              {@const precountRunning = meta.precount_running || 0}
              {@const precountExceeded = meta.precount_exceeded || false}
              {@const precountExtra = meta.precount_extra || 0}
              {@const batchSaved = meta.batch_saved || 0}
              {@const saveCurrent = meta.save_current || 0}
              {@const saveTotal = meta.save_total || 0}
              {@const phase = meta.phase || ''}
              {@const showEst = estTotal > 0 && estTotal >= foundTotal && !precountExceeded}
              {@const scanPct = phase === 'saving' && saveTotal > 0
                ? (saveCurrent / saveTotal) * 100
                : phase === 'precount'
                  ? Math.min((precountRunning / Math.max(precountRunning + 100, 500)) * 100, 90)
                  : showEst
                    ? Math.min((foundTotal / estTotal) * 100, 99)
                    : (job.progress * 100)}
              {@const eta = (phase === 'videos' || phase === 'shorts' || phase === 'live') ? getScanEta(job.id, foundTotal, estTotal) : null}
              <div class="ji-scan-wrap">
                <div class="ji-prog-wrap">
                  <div class="ji-prog-fill scan" style="width:{scanPct.toFixed(1)}%"></div>
                </div>
                <div class="ji-scan-info">
                  <span class="ji-scan-counts">
                    {#if phase === 'saving' && saveTotal > 0}
                      <i class="fa-solid fa-database"></i> Speichere {saveCurrent} / {saveTotal}
                    {:else if phase === 'connecting' || phase === 'metadata'}
                      {strip(job.description) || 'Verbinde…'}
                    {:else if phase === 'precount'}
                      <i class="fa-solid fa-magnifying-glass"></i> Zähle Videos… {precountRunning > 0 ? precountRunning : ''}
                    {:else}
                      {#if videoCount > 0}{videoCount} Videos{/if}
                      {#if shortCount > 0}{videoCount > 0 ? ' · ' : ''}{shortCount} Shorts{/if}
                      {#if liveCount > 0}{(videoCount + shortCount) > 0 ? ' · ' : ''}{liveCount} Live{/if}
                      {#if precountExceeded}
                        <span class="ji-scan-est"> -  +{precountExtra} weitere gefunden</span>
                      {:else if showEst && phase !== 'saving'}
                        <span class="ji-scan-est"> / ~{estTotal} erwartet</span>
                      {/if}
                      {#if batchSaved > 0}
                        <span class="ji-scan-saved"> · {batchSaved} gesichert</span>
                      {/if}
                    {/if}
                  </span>
                  <span class="ji-scan-phase">
                    {phase === 'connecting' ? 'Verbinde…' :
                     phase === 'metadata' ? 'Metadaten' :
                     phase === 'precount' ? 'Vorschau' :
                     phase === 'videos' ? 'Videos laden' :
                     phase === 'shorts' ? 'Shorts laden' :
                     phase === 'live' ? 'Livestreams' :
                     phase === 'saving' ? 'Speichern' : phase || '…'}
                    {#if eta}<span class="ji-scan-eta"> · {eta}</span>{/if}
                  </span>
                </div>
              </div>
            {:else if job.progress > 0 && job.type !== 'download'}
              <div class="ji-prog-wrap">
                <div class="ji-prog-fill" style="width:{(job.progress * 100).toFixed(1)}%"></div>
              </div>
              <div class="ji-prog-info">
                <span>{strip(job.description) || ''}</span>
              </div>
            {:else if job.description && job.type !== 'download'}
              <div class="ji-active-desc">{strip(job.description)}</div>
            {/if}
          </div>
        {/each}

        <!-- Wartende Jobs: kompakte Einzeiler -->
        {#each queuedJobs as job (job.id)}
          {@const positions = getQueuePositions()}
          {@const pos = positions[job.id]}
          <div class="ji-compact queued" class:is-paused={stats.paused}>
            <span class="ji-c-icon" style="color:var(--status-pending)">
              {#if stats.paused}
                <i class="fa-solid fa-pause"></i>
              {:else}
                <i class="fa-solid fa-clock"></i>
              {/if}
            </span>
            <span class="ji-c-title" class:is-id={isIdOnly(job)} title={videoId(job)}>
              {displayTitle(job)}
            </span>
            <span class="ji-c-right">
              {#if stats.paused}
                <span class="ji-badge paused">pausiert</span>
              {:else if pos}
                <span class="ji-badge pos">#{pos}</span>
              {/if}
              <button class="ji-c-cancel" onclick={() => cancelJob(job.id)} title="Abbrechen">
                <i class="fa-solid fa-xmark"></i>
              </button>
            </span>
          </div>
        {/each}
        {#if moreQueued > 0}
          <div class="ji-more">+ {moreQueued} weitere in Warteschlange</div>
        {/if}

        <!-- Fertige/Fehler Jobs: kompakte Einzeiler -->
        {#each doneJobs as job (job.id)}
          <div class="ji-compact {job.status}">
            <span class="ji-c-icon">
              {#if job.status === 'done'}
                <i class="fa-solid fa-circle-check"></i>
              {:else if job.status === 'error'}
                <i class="fa-solid fa-circle-xmark"></i>
              {:else if job.status === 'parked'}
                <i class="fa-solid fa-circle-pause"></i>
              {:else}
                <i class="fa-solid fa-ban"></i>
              {/if}
            </span>
            <span class="ji-c-title" class:is-id={isIdOnly(job)} title={videoId(job)}>
              {displayTitle(job)}
            </span>
            <span class="ji-c-right">
              {#if job.status === 'parked'}
                <button class="ji-c-unpark" onclick={() => unparkJob(job.id)} title="Zurück in Queue"><i class="fa-solid fa-rotate-left"></i></button>
              {/if}
              <span class="ji-c-time">{formatDateRelative(job.completed_at || job.created_at)}</span>
            </span>
          </div>
        {/each}

        <!-- Leer-Zustand -->
        {#if activeJobs.length === 0 && queuedJobs.length === 0 && doneJobs.length === 0}
          <div class="ji-empty">Keine Aktivitäten</div>
        {/if}
      </div>
    </div>
  {/if}

  <!-- ═══ Unified Bar ═══ -->
  <div class="ubar">
    <div class="ubar-left">
      <button class="ubar-toggle" onclick={() => expanded = !expanded}>
        <i class="fa-solid {expanded ? 'fa-chevron-down' : 'fa-chevron-up'} ubar-chev"></i>
        <span>Aktivitäten</span>
      </button>

      <span class="ubar-led" class:lit={stats.active > 0} style="--c:var(--status-info)">
        <i class="fa-solid fa-play"></i> {stats.active}
      </span>
      {#if stats.paused}
        <span class="ubar-led lit" style="--c:var(--status-warning)">
          <i class="fa-solid fa-pause"></i> {stats.queued}
        </span>
      {:else}
        <span class="ubar-led" class:lit={stats.queued > 0} style="--c:var(--status-pending)">
          <i class="fa-solid fa-clock"></i> {stats.queued}
        </span>
      {/if}
      <span class="ubar-led" class:lit={stats.done > 0} style="--c:var(--status-success)">
        <i class="fa-solid fa-check"></i> {stats.done}
      </span>
      <span class="ubar-led" class:lit={stats.errors > 0} style="--c:var(--status-error)">
        <i class="fa-solid fa-xmark"></i> {stats.errors}
      </span>
      {#if stats.parked > 0}
        <span class="ubar-led lit" style="--c:var(--status-warning)">
          <i class="fa-solid fa-circle-pause"></i> {stats.parked}
        </span>
      {/if}

      <span class="ubar-sep"></span>

      <!-- Pause/Play Toggle -->
      <button
        class="ubar-btn"
        class:play={stats.paused}
        class:pause={!stats.paused}
        onclick={togglePause}
        title={stats.paused ? 'Queue fortsetzen' : 'Queue pausieren'}
      >
        <i class="fa-solid {stats.paused ? 'fa-play' : 'fa-pause'}"></i>
      </button>

      <!-- Cleanup -->
      <button
        class="ubar-btn danger"
        class:disabled={!hasCleanable}
        onclick={hasCleanable ? cleanupDone : undefined}
        title="Fertige/Fehler löschen"
      >
        <i class="fa-solid fa-trash-can"></i>
      </button>

      <!-- Cooldown-Timer -->
      {#if cooldownRemaining > 0}
        <span class="ubar-sep"></span>
        <span class="ubar-cooldown" title="Cooldown bis zum nächsten Job ({cooldownState.cooldown}s, Basis: {cooldownState.base}s)">
          <i class="fa-solid fa-hourglass-half"></i>
          <span class="ubar-timer">{fmtTime(cooldownRemaining)}</span>
          {#if cooldownState.cooldown > cooldownState.base}
            <span class="ubar-cd-warn">×{Math.round(cooldownState.cooldown / cooldownState.base)}</span>
          {/if}
        </span>
      {/if}

      <!-- Aktive Jobs (zugeklappt: alle sichtbar, max 3) -->
      {#if !expanded && activeJobs.length > 0}
        {#each activeJobs.slice(0, 3) as aj (aj.id)}
          {@const live = getLive(aj.id)}
          {@const progress = live?.progress ?? aj.progress ?? 0}
          {@const stage = live?.stage || 'resolving'}
          {@const phases = live?.phases || null}
          <span class="ubar-sep"></span>
          <span class="ubar-job-group">
            <span class="ubar-job-title" title={displayTitle(aj)}>
              <i class="fa-solid {typeIcons[aj.type] || 'fa-circle'}"></i>
              {displayTitle(aj)}
            </span>
            <span class="ubar-job-bar">
              {#if aj.type === 'download'}
                <MiniProgress
                  progress={progress}
                  stage={stage}
                  phases={phases}
                  status={aj.status}
                />
                <span class="ubar-pct">{(progress * 100).toFixed(0)}%</span>
              {:else}
                <div class="ubar-mini-generic" title="{((aj.progress || 0) * 100).toFixed(0)}%">
                  <div class="ubar-mini-fill" style="width:{(aj.progress || 0) * 100}%; background:var(--accent-primary)"></div>
                </div>
                <span class="ubar-pct">{((aj.progress || 0) * 100).toFixed(0)}%</span>
              {/if}
            </span>
          </span>
        {/each}
      {/if}
    </div>

    <div class="ubar-right">
      <span class="ubar-sys"><span class="led led-ok"></span> Frontend {FE_VERSION}</span>
      <span class="ubar-sys"><span class="led" class:led-ok={backendOk} class:led-err={!backendOk}></span> Backend {backendVersion}</span>
      <span class="ubar-sep"></span>
      <span class="ubar-sys"><span class="led" class:led-ok={ytOk && !rateWarning && cooldownState.cooldown <= cooldownState.base} class:led-warn={!ytOk || rateWarning || cooldownState.cooldown > cooldownState.base}></span> YouTube</span>
      <span class="ubar-sys"><span class="led" class:led-ok={rssRunning} class:led-off={!rssRunning}></span> RSS</span>
      <span class="ubar-sys"><span class="led" class:led-ok={rydOk} class:led-off={!rydOk}></span> RYD</span>

      {#if rateWarning || rateLimiterDisabled || !ytOk || (stats.paused && stats.pause_reason === 'rate_limit')}
        <span class="ubar-sep"></span>
        {#if rateLimiterDisabled}
          <span class="ubar-led lit" style="--c:var(--status-info)">
            <i class="fa-solid fa-shield-halved"></i> Limiter AUS
          </span>
        {:else if !ytOk}
          <span class="ubar-led lit" style="--c:var(--status-error)">
            <i class="fa-solid fa-ban"></i> YouTube blockiert{ytBlockCount > 0 ? ` (${ytBlockCount}×)` : ''}
          </span>
        {:else if rateWarning}
          <span class="ubar-led lit" style="--c:var(--status-warning)">
            <i class="fa-solid fa-gauge-high"></i> Backoff aktiv
          </span>
        {/if}
        <button class="ubar-btn" onclick={resetRateLimit} title="Rate-Limit zurücksetzen">
          <i class="fa-solid fa-rotate-right"></i>
        </button>
        <button class="ubar-btn" onclick={toggleRateLimit} title={rateLimiterDisabled ? 'Rate-Limiter einschalten' : 'Rate-Limiter ausschalten'}>
          <i class="fa-solid {rateLimiterDisabled ? 'fa-toggle-off' : 'fa-toggle-on'}"></i>
        </button>
      {:else}
        <button class="ubar-btn" onclick={toggleRateLimit} title="Rate-Limiter ausschalten" style="opacity:0.5">
          <i class="fa-solid fa-shield-halved"></i>
        </button>
      {/if}
    </div>
  </div>
</div>

<style>
  /* ═══ Bottom Stack ═══ */
  .bottom-stack {
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    max-height: 50vh;
    position: relative;
    z-index: 10;
  }
  .bottom-stack.paused .ubar {
    border-top-color: rgba(234, 179, 8, 0.3);
  }

  /* ═══ Detail Panel ═══ */
  .detail {
    background: var(--bg-secondary);
    border-top: 1px solid var(--border-primary);
    overflow: hidden;
    flex-shrink: 1;
    min-height: 0;
  }
  .detail-inner {
    padding: 6px 12px 4px;
    max-height: 260px;
    overflow-y: auto;
  }

  /* ─── Pause-Banner ─── */
  .pause-banner {
    display: flex; align-items: center; gap: 8px;
    padding: 6px 10px; margin-bottom: 6px;
    background: rgba(234, 179, 8, 0.08);
    border: 1px solid rgba(234, 179, 8, 0.25);
    border-radius: 6px; font-size: 0.78rem; color: var(--status-warning);
  }
  .pause-banner > i { font-size: 0.9rem; flex-shrink: 0; color: inherit; }
  .pause-info { flex: 1; }
  .pause-title { font-weight: 600; }
  .pause-detail { font-size: 0.68rem; opacity: 0.8; }
  .pause-resume {
    background: var(--status-warning); color: var(--bg-primary);
    border: none; border-radius: 5px; padding: 3px 10px;
    font-size: 0.72rem; font-weight: 700; cursor: pointer;
    display: flex; align-items: center; gap: 4px; flex-shrink: 0;
  }
  .pause-resume:hover { filter: brightness(1.15); }
  .pause-resume i { color: inherit; }

  /* Cooldown-Banner */
  .cooldown-banner {
    display: flex; align-items: center; gap: 8px;
    padding: 5px 10px; margin-bottom: 4px;
    border-radius: 6px;
    background: rgba(234, 179, 8, 0.08);
    border: 1px solid rgba(234, 179, 8, 0.2);
    color: var(--status-warning);
    font-size: 0.72rem;
  }
  .cooldown-banner > i { font-size: 0.72rem; flex-shrink: 0; color: inherit; }
  .cooldown-info { display: flex; align-items: baseline; gap: 6px; }
  .cooldown-timer {
    font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 0.82rem; font-weight: 700;
    font-variant-numeric: tabular-nums;
  }
  .cooldown-label { font-size: 0.66rem; opacity: 0.8; }
  .cooldown-multi {
    margin-left: auto; font-size: 0.62rem; font-weight: 700;
    color: var(--status-error); background: rgba(239, 68, 68, 0.1);
    border-radius: 3px; padding: 1px 5px;
  }

  /* ─── Aktives Item (komplex, mit Phasen-Balken) ─── */
  .ji-active {
    padding: 6px 8px; border-radius: 6px;
    background: var(--bg-tertiary); margin-bottom: 4px;
    border: 1px solid var(--border-secondary);
    contain: layout style; position: relative;
  }
  .ji-active.fading { opacity: 0.7; }
  .ji-active-top {
    display: flex; align-items: center; gap: 6px;
  }
  .ji-active-top > i { font-size: 0.8rem; flex-shrink: 0; color: inherit; }
  .ji-active-title {
    font-size: 0.78rem; font-weight: 600; color: var(--text-primary);
    flex: 1; min-width: 0; cursor: default;
    overflow-wrap: break-word; word-break: break-word;
  }
  .ji-active-title.is-id {
    font-family: monospace; font-size: 0.72rem; color: var(--text-tertiary);
  }
  .ji-active-pct {
    font-size: 0.72rem; font-weight: 700; color: var(--accent-primary);
    font-variant-numeric: tabular-nums; flex-shrink: 0;
  }
  .ji-cancel {
    position: absolute; top: 4px; right: 4px; z-index: 2;
    background: var(--bg-tertiary); border: 1px solid var(--border-primary);
    color: var(--text-tertiary); cursor: pointer; border-radius: 4px;
    width: 22px; height: 22px; display: flex; align-items: center;
    justify-content: center; font-size: 0.6rem; flex-shrink: 0;
    opacity: 0; transition: all 0.15s;
  }
  .ji-active:hover .ji-cancel { opacity: 1; }
  .ji-cancel:hover { border-color: var(--status-error); color: var(--status-error); }
  .ji-cancel i { color: inherit; }
  .ji-active-dl { margin: 2px 0; }
  .ji-active-desc {
    font-size: 0.72rem; color: var(--text-secondary); margin-top: 2px;
    overflow-wrap: break-word; word-break: break-word;
  }
  .ji-prog-wrap {
    height: 5px; border-radius: 3px; overflow: hidden; margin: 4px 0 2px;
    position: relative;
    background: color-mix(in srgb, var(--accent-primary) 18%, transparent);
  }
  .ji-prog-wrap:has(.scan) {
    background: color-mix(in srgb, #00BCD4 18%, transparent);
  }
  .ji-prog-fill {
    position: absolute; top: 0; left: 0; bottom: 0;
    background: var(--accent-primary);
    border-radius: 3px; transition: width 0.5s ease;
  }
  .ji-prog-info {
    display: flex; justify-content: space-between;
    font-size: 0.65rem; color: var(--text-secondary);
  }
  .ji-pct { color: var(--accent-primary); font-weight: 600; font-variant-numeric: tabular-nums; }

  /* ─── Kanalscan-Fortschritt ─── */
  .ji-scan-wrap { margin-top: 4px; }
  .ji-prog-fill.scan { background: #00BCD4; }
  .ji-scan-info {
    display: flex; justify-content: space-between; align-items: center;
    font-size: 0.65rem; color: var(--text-secondary); margin-top: 2px;
  }
  .ji-scan-info i { font-size: 0.5rem; margin-right: 3px; color: inherit; }
  .ji-scan-counts { display: inline-flex; align-items: center; gap: 0; }
  .ji-scan-est { color: var(--text-tertiary); font-size: 0.6rem; }
  .ji-scan-saved { color: var(--status-success); font-size: 0.6rem; opacity: 0.7; }
  .ji-scan-phase {
    font-size: 0.58rem; font-weight: 600; text-transform: uppercase;
    color: #00BCD4; letter-spacing: 0.04em; flex-shrink: 0;
  }
  .ji-scan-eta { color: var(--text-tertiary); font-weight: 400; text-transform: none; letter-spacing: 0; }

  /* ─── Kompakte Items ─── */
  .ji-compact {
    display: flex; align-items: flex-start; gap: 5px;
    padding: 3px 6px; border-radius: 4px; font-size: 0.72rem;
    margin-bottom: 1px; border-left: 3px solid transparent;
    position: relative;
  }
  .ji-compact:hover { background: var(--bg-tertiary); }

  .ji-compact.queued { border-left-color: var(--status-pending); color: var(--text-secondary); }
  .ji-compact.queued.is-paused { border-left-color: var(--status-warning); opacity: 0.5; }
  .ji-compact.done { border-left-color: var(--status-success); color: var(--text-tertiary); }
  .ji-compact.error { border-left-color: var(--status-error); color: var(--text-tertiary); }
  .ji-compact.parked { border-left-color: var(--status-warning); color: var(--text-tertiary); }
  .ji-compact.parked .ji-c-icon { color: var(--status-warning); }
  .ji-compact.cancelled { border-left-color: var(--text-tertiary); color: var(--text-tertiary); opacity: 0.5; }

  .ji-c-icon { width: 14px; text-align: center; font-size: 0.62rem; flex-shrink: 0; margin-top: 2px; }
  .ji-c-icon i { color: inherit; }
  .ji-compact.done .ji-c-icon { color: var(--status-success); }
  .ji-compact.error .ji-c-icon { color: var(--status-error); }

  .ji-c-title {
    flex: 1; min-width: 0;
    overflow-wrap: break-word; word-break: break-word; cursor: default;
  }
  .ji-c-title.is-id {
    font-family: monospace; font-size: 0.68rem; color: var(--text-tertiary);
  }

  .ji-c-right {
    display: flex; align-items: center; gap: 4px; flex-shrink: 0;
    font-size: 0.62rem;
  }
  .ji-c-time { color: var(--text-tertiary); }
  .ji-badge {
    padding: 0 4px; border-radius: 3px; font-weight: 700;
    font-size: 0.55rem;
  }
  .ji-badge.pos { background: rgba(167, 139, 250, 0.12); color: var(--status-pending); }
  .ji-badge.paused { color: var(--status-warning); font-weight: 600; font-size: 0.6rem; }
  .ji-c-cancel {
    position: absolute; top: 2px; right: 2px; z-index: 2;
    background: var(--bg-tertiary); border: none; color: var(--text-tertiary);
    cursor: pointer; font-size: 0.55rem; padding: 2px 4px; border-radius: 3px;
    opacity: 0; transition: opacity 0.12s;
  }
  .ji-compact:hover .ji-c-cancel { opacity: 1; }
  .ji-c-cancel:hover { color: var(--status-error); }
  .ji-c-cancel i { color: inherit; }
  .ji-c-unpark {
    background: none; border: none; padding: 0 2px; cursor: pointer;
    font-size: 0.62rem; color: var(--status-warning); opacity: 0.6;
  }
  .ji-c-unpark:hover { opacity: 1; color: var(--accent-primary); }

  .ji-more {
    text-align: center; font-size: 0.68rem; color: var(--text-tertiary);
    padding: 4px 6px; border-left: 3px solid var(--border-secondary);
    margin: 2px 0; font-style: italic;
  }

  .ji-empty {
    padding: 12px; text-align: center;
    font-size: 0.75rem; color: var(--text-tertiary);
  }

  /* ═══ Unified Bar ═══ */
  .ubar {
    display: flex; align-items: center; height: 34px;
    padding: 0 14px; gap: 6px;
    background: var(--bg-secondary);
    border-top: 1px solid var(--border-primary);
    font-size: 0.72rem; color: var(--text-tertiary);
    flex-shrink: 0; user-select: none;
  }

  .ubar-left {
    flex: 1; display: flex; align-items: center; gap: 6px;
    min-width: 0; overflow: hidden;
  }

  .ubar-right {
    display: flex; align-items: center; gap: 8px; flex-shrink: 0;
  }

  .ubar-toggle {
    display: flex; align-items: center; gap: 4px;
    background: none; border: none; color: var(--text-secondary);
    cursor: pointer; font-size: 0.72rem; font-weight: 600;
    padding: 2px 6px; border-radius: 4px;
  }
  .ubar-toggle:hover { background: var(--bg-tertiary); color: var(--text-primary); }
  .ubar-chev { font-size: 0.5rem; }

  .ubar-led {
    display: inline-flex; align-items: center; gap: 3px;
    font-size: 0.68rem; font-weight: 600; color: var(--text-tertiary);
    flex-shrink: 0; white-space: nowrap;
  }
  .ubar-led i { font-size: 0.48rem; color: inherit; }
  .ubar-led.lit { color: var(--c); }

  .ubar-sep { width: 1px; height: 12px; background: var(--border-primary); flex-shrink: 0; }

  .ubar-btn {
    background: none; border: none; color: var(--text-tertiary);
    cursor: pointer; font-size: 0.72rem; padding: 2px 5px; border-radius: 4px;
  }
  .ubar-btn i { color: inherit; }
  .ubar-btn:hover { color: var(--text-primary); background: var(--bg-tertiary); }
  .ubar-btn.play { color: var(--status-success); }
  .ubar-btn.play:hover { background: rgba(34, 197, 94, 0.1); }
  .ubar-btn.pause:hover { color: var(--status-warning); background: rgba(234, 179, 8, 0.1); }
  .ubar-btn.danger:hover { color: var(--status-error); background: rgba(239, 68, 68, 0.08); }
  .ubar-btn.disabled { opacity: 0.3; cursor: default; pointer-events: none; }

  /* Cooldown-Timer */
  .ubar-cooldown {
    display: inline-flex; align-items: center; gap: 3px;
    font-size: 0.68rem; font-weight: 600;
    color: var(--status-warning);
  }
  .ubar-cooldown i { font-size: 0.52rem; color: inherit; }
  .ubar-timer {
    font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.02em;
  }
  .ubar-cd-warn {
    font-size: 0.58rem; color: var(--status-error);
    background: rgba(239, 68, 68, 0.1); border-radius: 3px;
    padding: 0 3px; font-weight: 700;
  }

  /* Aktiver Job-Titel + Mini-Fortschritt (zugeklappt) */
  .ubar-job-group {
    display: flex; align-items: center; gap: 6px;
    flex: 1 1 0; min-width: 80px; overflow: hidden;
  }
  .ubar-job-title {
    font-size: 0.68rem; color: var(--text-secondary);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    display: inline-flex; align-items: center; gap: 4px;
    flex: 1 1 auto; min-width: 40px;
  }
  .ubar-job-title i { font-size: 0.52rem; color: var(--status-info); flex-shrink: 0; }
  .ubar-job-bar {
    display: flex; align-items: center; gap: 4px;
    flex-shrink: 0; width: 140px;
  }
  .ubar-pct {
    font-size: 0.6rem; color: var(--text-tertiary); font-variant-numeric: tabular-nums;
    flex-shrink: 0; width: 28px; text-align: right;
  }
  .ubar-mini-generic {
    flex: 1; min-width: 40px; height: 4px; border-radius: 2px;
    background: color-mix(in srgb, var(--accent-primary) 20%, transparent);
    overflow: hidden; position: relative;
  }
  .ubar-mini-fill {
    position: absolute; top: 0; left: 0; bottom: 0;
    border-radius: 2px; transition: width 0.6s ease;
  }

  .ubar-sys {
    display: flex; align-items: center; gap: 3px; white-space: nowrap;
  }
  .led {
    width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
  }
  .led-ok { background: var(--status-success); box-shadow: 0 0 4px var(--status-success); }
  .led-warn { background: var(--status-warning); box-shadow: 0 0 4px var(--status-warning); }
  .led-err { background: var(--status-error); box-shadow: 0 0 4px var(--status-error); }
  .led-off { background: var(--text-tertiary); opacity: 0.4; }

  /* ═══ Responsive ═══ */
  @media (max-width: 768px) {
    .ubar-right { gap: 5px; }
    .ubar-led { font-size: 0.6rem; }
    .ubar-left { gap: 4px; }
    .ji-active-top > i { display: none; }
    .ubar-job-group { max-width: 200px; }
  }
  @media (max-width: 480px) {
    .ubar-right .ubar-sys { font-size: 0; gap: 0; }
    .ubar-right .ubar-sys .led { margin: 0 1px; }
    .ubar-job-group { display: none; }
  }
</style>

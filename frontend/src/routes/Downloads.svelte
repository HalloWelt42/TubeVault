<!--
  TubeVault
  © HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
  SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
-->
<script>
  import { api, createActivitySocket } from '../lib/api/client.js';
  import { toast } from '../lib/stores/notifications.js';
  import { pendingDownloadUrl } from '../lib/stores/app.js';
  import { formatDuration, formatSize } from '../lib/utils/format.js';
  import { formatDateRelative } from '../lib/utils/format.js';
  import DownloadProgress from '../lib/components/common/DownloadProgress.svelte';

  let queue = $state({ queue: [], active_count: 0, queued_count: 0, completed_count: 0, error_count: 0, cancelled_count: 0, retry_wait_count: 0, failed_count: 0 });
  let urlInput = $state('');
  let batchInput = $state('');
  let showBatch = $state(false);
  let resolving = $state(false);
  let videoInfo = $state(null);
  let playlistInfo = $state(null);
  let channelInfo = $state(null);
  let selectedQuality = $state('best');
  let selectedPriority = $state(0);
  let socket = $state(null);
  let plDownloading = $state(new Set());

  // Worker Health
  let workerDead = $state(false);
  let restartingWorker = $state(false);

  // Live-Status aus WebSocket (ergänzt Queue-Daten)
  let liveStatus = $state({});

  // System-Jobs (nicht-Download: Scans, RSS, AI, etc.)
  let systemJobs = $state([]);
  let jobsTab = $state('all'); // all, active, done, error

  // Scan-ETA Tracking
  const scanTracker = {};
  function getScanEta(jobId, foundTotal, estTotal) {
    if (!estTotal || estTotal <= 0 || foundTotal <= 0) return null;
    if (!scanTracker[jobId]) scanTracker[jobId] = { start: Date.now(), startCount: foundTotal };
    const t = scanTracker[jobId];
    const elapsed = (Date.now() - t.start) / 1000;
    const processed = foundTotal - t.startCount;
    if (processed <= 5 || elapsed < 3) return null;
    const rate = processed / elapsed;
    const remaining = Math.max(0, estTotal - foundTotal);
    const etaSec = Math.ceil(remaining / rate);
    if (etaSec > 7200) return null;
    const min = Math.floor(etaSec / 60);
    const sec = etaSec % 60;
    return min > 0 ? `~${min}m ${sec}s` : `~${sec}s`;
  }

  async function loadQueue() {
    try {
      queue = await api.getQueue();
      // Worker-Health prüfen wenn es wartende Downloads gibt aber keine aktiven
      if (queue.queued_count > 0 && queue.active_count === 0) {
        try {
          const health = await api.workerHealth();
          workerDead = !health.alive;
        } catch { workerDead = false; }
      } else {
        workerDead = false;
      }
    } catch {}
  }

  async function restartWorker() {
    restartingWorker = true;
    try {
      await api.restartWorker();
      toast.success('Download-Worker neu gestartet');
      workerDead = false;
      setTimeout(loadQueue, 2000);
    } catch (e) {
      toast.error('Worker-Restart fehlgeschlagen: ' + e.message);
    }
    restartingWorker = false;
  }

  function handleWsMessage(msg) {
    const id = msg.job_id || msg.queue_id;
    if (id) {
      liveStatus[id] = msg;
      liveStatus = { ...liveStatus };
    }
    // Queue aktualisieren wenn done/error
    if (msg.status === 'done' || msg.status === 'error' || msg.status === 'cancelled') {
      setTimeout(loadQueue, 500);
    }
  }

  // URL auflösen (Step 1) — erkennt Video, Playlist, Kanal
  async function resolveVideo() {
    if (!urlInput.trim()) return;
    resolving = true;
    videoInfo = null;
    playlistInfo = null;
    channelInfo = null;
    try {
      const result = await api.resolveUrl(urlInput.trim());
      if (result.type === 'video') {
        videoInfo = result.data;
      } else if (result.type === 'playlist') {
        playlistInfo = result.data;
      } else if (result.type === 'channel') {
        channelInfo = result.data;
      }
    } catch (e) {
      toast.error(e.message);
    }
    finally { resolving = false; }
  }

  // Playlist: Einzelnes Video laden
  async function plDownloadOne(videoId) {
    plDownloading = new Set([...plDownloading, videoId]);
    try {
      await api.addDownload({ url: `https://www.youtube.com/watch?v=${videoId}`, quality: 'best', priority: selectedPriority });
      toast.success('Download gestartet');
      loadQueue();
    } catch (e) { toast.error(e.message); }
    plDownloading = new Set([...plDownloading].filter(id => id !== videoId));
  }

  // Playlist: Alle fehlenden laden
  async function plDownloadAll() {
    if (!playlistInfo) return;
    const missing = playlistInfo.videos.filter(v => !v.already_downloaded);
    toast.info(`${missing.length} Downloads werden gestartet…`);
    let ok = 0;
    for (const v of missing) {
      try {
        await api.addDownload({ url: `https://www.youtube.com/watch?v=${v.id}`, quality: 'best', priority: selectedPriority });
        ok++;
      } catch {}
    }
    toast.success(`${ok}/${missing.length} Downloads gestartet`);
    loadQueue();
  }

  // Kanal abonnieren
  async function subscribeChannel() {
    if (!channelInfo) return;
    try {
      await api.addSubscription({ channel_id: channelInfo.channel_id });
      channelInfo = { ...channelInfo, already_subscribed: true };
      toast.success(`${channelInfo.channel_name} abonniert`);
    } catch (e) { toast.error(e.message); }
  }

  // Download starten (Step 2)
  async function startDownload() {
    if (!urlInput.trim()) return;
    try {
      await api.addDownload({
        url: urlInput.trim(),
        quality: selectedQuality,
        download_thumbnail: true,
        priority: selectedPriority,
      });
      toast.success('Download gestartet');
      urlInput = '';
      videoInfo = null;
      playlistInfo = null;
      channelInfo = null;
      loadQueue();
    } catch (e) { toast.error(e.message); }
  }

  // URL-Typ erkennen (Playlist, Kanal, oder normales Video?)
  function isPlaylistOrChannelUrl(url) {
    return /[?&]list=/.test(url) || /\/playlist\?/.test(url) ||
           /\/@[a-zA-Z0-9_.-]+/.test(url) || /\/channel\//.test(url) || /\/c\//.test(url);
  }

  // Direkt-Download (ohne Resolve) — erkennt Playlists/Kanäle automatisch
  async function quickDownload() {
    if (!urlInput.trim()) return;
    // Playlist/Kanal-URLs zum Resolver umleiten
    if (isPlaylistOrChannelUrl(urlInput.trim())) {
      return resolveVideo();
    }
    try {
      await api.addDownload({ url: urlInput.trim(), quality: 'best', priority: selectedPriority });
      toast.success('Download gestartet (beste Qualität)');
      urlInput = '';
      videoInfo = null;
      playlistInfo = null;
      channelInfo = null;
      loadQueue();
    } catch (e) { toast.error(e.message); }
  }

  async function addBatch() {
    const urls = batchInput.split('\n').map(l => l.trim()).filter(l => l);
    if (!urls.length) return;
    try {
      const result = await api.addBatchDownload({ urls });
      const ok = result.results?.filter(r => r.status !== 'error').length || 0;
      toast.success(`${ok} Downloads gestartet`);
      batchInput = '';
      showBatch = false;
      loadQueue();
    } catch (e) { toast.error(e.message); }
  }

  async function cancelItem(id) {
    await api.cancelDownload(id);
    loadQueue();
  }
  async function retryItem(id) {
    await api.retryDownload(id);
    loadQueue();
  }
  async function retryAllFailed() {
    try {
      const res = await api.retryAllFailed();
      toast.success(`${res.retried} Downloads erneut in Queue`);
      loadQueue();
    } catch (e) { toast.error(e.message); }
  }
  async function retryDelayed(id, minutes) {
    try {
      await api.retryWithDelay(id, minutes);
      toast.success(`Retry in ${minutes} Minuten`);
      loadQueue();
    } catch (e) { toast.error(e.message); }
  }
  async function clearDone() {
    try {
      await api.clearCompleted();
      toast.success('Fertige Downloads entfernt');
      loadQueue();
    } catch (e) { toast.error('Fehler: ' + (e.message || 'Unbekannt')); }
  }
  async function fixStale() {
    try {
      const res = await api.fixStaleDownloads();
      toast.success(`${res.fixed} stale Downloads entfernt`);
      loadQueue();
    } catch (e) { toast.error('Fehler: ' + (e.message || 'Unbekannt')); }
  }
  async function clearAll() {
    try {
      const res = await api.clearAllDownloads();
      toast.success(`${res.cleared} Downloads bereinigt`);
      loadQueue();
    } catch (e) { toast.error('Fehler: ' + (e.message || 'Unbekannt')); }
  }

  function getLive(queueId) {
    return liveStatus[queueId] || null;
  }

  // System-Jobs laden (nicht-Download)
  async function loadSystemJobs() {
    try {
      const all = await api.getJobs({ limit: 50 });
      systemJobs = (Array.isArray(all) ? all : []).filter(j => j.type !== 'download');
    } catch {}
  }

  const JOB_TYPE_ICONS = {
    channel_scan: 'fa-satellite-dish',
    rss_cycle: 'fa-rss',
    rss_poll: 'fa-rss',
    import: 'fa-file-import',
    avatar_fetch: 'fa-image',
    archive_scan: 'fa-box-archive',
    cleanup: 'fa-broom',
    deep_scan: 'fa-magnifying-glass',
    enrich: 'fa-wand-magic-sparkles',
  };

  const JOB_TYPE_LABELS = {
    channel_scan: 'Kanal-Scan',
    rss_cycle: 'RSS-Zyklus',
    rss_poll: 'RSS-Poll',
    import: 'Import',
    avatar_fetch: 'Avatar-Download',
    archive_scan: 'Archiv-Scan',
    cleanup: 'Cleanup',
    deep_scan: 'Deep-Scan',
    enrich: 'Anreicherung',
  };

  let filteredJobs = $derived.by(() => {
    if (jobsTab === 'all') return systemJobs;
    if (jobsTab === 'active') return systemJobs.filter(j => j.status === 'active' || j.status === 'queued');
    if (jobsTab === 'done') return systemJobs.filter(j => j.status === 'done' || j.status === 'cancelled');
    if (jobsTab === 'error') return systemJobs.filter(j => j.status === 'error');
    return systemJobs;
  });

  let jobCounts = $derived({
    all: systemJobs.length,
    active: systemJobs.filter(j => j.status === 'active' || j.status === 'queued').length,
    done: systemJobs.filter(j => j.status === 'done' || j.status === 'cancelled').length,
    error: systemJobs.filter(j => j.status === 'error').length,
  });

  async function cancelSystemJob(id) {
    try {
      await api.cancelJob(id);
      setTimeout(loadSystemJobs, 500);
    } catch {}
  }

  function stageIcon(stage) {
    const icons = {
      queued: '<i class="fa-solid fa-clock"></i>',
      resolving: '<i class="fa-solid fa-magnifying-glass"></i>',
      resolved: '<i class="fa-solid fa-list-check"></i>',
      downloading_video: '<i class="fa-solid fa-download"></i>',
      downloading_audio: '<i class="fa-solid fa-music"></i>',
      merging: '<i class="fa-solid fa-wrench"></i>',
      finalizing: '<i class="fa-solid fa-floppy-disk"></i>',
      done: '<i class="fa-solid fa-circle-check"></i>',
      error: '<i class="fa-solid fa-circle-xmark"></i>',
      cancelled: '<i class="fa-solid fa-ban"></i>',
      retry_wait: '<i class="fa-solid fa-hourglass-half"></i>',
    };
    return icons[stage] || '<i class="fa-solid fa-clock"></i>';
  }

  function retryCountdown(retryAfter) {
    if (!retryAfter) return '';
    const diff = Math.max(0, Math.floor((new Date(retryAfter) - Date.now()) / 1000));
    if (diff <= 0) return 'gleich…';
    const m = Math.floor(diff / 60);
    const s = diff % 60;
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  }

  // Progressive streams (Video+Audio kombiniert) herausfiltern
  let progressiveStreams = $derived(
    videoInfo?.streams?.filter(s => s.is_progressive && s.type === 'video')
      .sort((a, b) => (parseInt(b.quality) || 0) - (parseInt(a.quality) || 0)) || []
  );
  let adaptiveVideo = $derived(
    videoInfo?.streams?.filter(s => s.is_adaptive && s.type === 'video')
      .sort((a, b) => (parseInt(b.quality) || 0) - (parseInt(a.quality) || 0)) || []
  );

  $effect(() => {
    loadQueue();
    loadSystemJobs();
    const iv = setInterval(loadQueue, 5000);
    const jiv = setInterval(loadSystemJobs, 5000);
    socket = createActivitySocket(handleWsMessage);
    return () => { clearInterval(iv); clearInterval(jiv); if (socket) socket.close(); };
  });

  // Pending URL von SearchDropdown übernehmen
  $effect(() => {
    const pending = $pendingDownloadUrl;
    if (pending) {
      urlInput = pending;
      $pendingDownloadUrl = null;
      // Auto-Resolve nach kurzer Verzögerung
      setTimeout(() => resolveVideo(), 50);
    }
  });
</script>

<div class="page">
  <div class="page-header">
    <h1 class="title"><i class="fa-solid fa-bolt"></i> Jobs</h1>
    <div class="queue-stats">
      <span class="qs active">{queue.active_count} aktiv</span>
      <span class="qs queued">{queue.queued_count} wartend</span>
      <span class="qs done">{queue.completed_count} fertig</span>
      {#if queue.error_count > 0}<span class="qs error">{queue.error_count} Fehler</span>{/if}
      {#if queue.cancelled_count > 0}<span class="qs cancelled">{queue.cancelled_count} abgebrochen</span>{/if}
      {#if queue.retry_wait_count > 0}<span class="qs retry-wait">{queue.retry_wait_count} warten</span>{/if}
    </div>
  </div>

  <!-- Worker Warning -->
  {#if workerDead}
    <div class="worker-warning">
      <i class="fa-solid fa-triangle-exclamation"></i>
      <span><strong>Download-Worker gestoppt</strong> — Downloads werden nicht verarbeitet.</span>
      <button class="btn-sm accent" onclick={restartWorker} disabled={restartingWorker}>
        {#if restartingWorker}<i class="fa-solid fa-spinner fa-spin"></i>{:else}<i class="fa-solid fa-rotate"></i>{/if}
        Worker neu starten
      </button>
    </div>
  {/if}

  <!-- Download Input -->
  <div class="input-section">
    <div class="url-row">
      <input type="text" class="input" placeholder="YouTube-URL einfügen…"
        bind:value={urlInput}
        onkeydown={(e) => e.key === 'Enter' && resolveVideo()} />
      <button class="btn-secondary" onclick={resolveVideo} disabled={resolving || !urlInput.trim()}>
        {#if resolving}<i class="fa-solid fa-spinner fa-spin"></i> Wird aufgelöst…{:else}<i class="fa-solid fa-magnifying-glass"></i> Auflösen{/if}
      </button>
      <button class="btn-primary" onclick={quickDownload} disabled={!urlInput.trim()}>
        <i class="fa-solid fa-download"></i> Schnell-DL
      </button>
    </div>
    <div class="input-sub">
      <div class="priority-row">
        <span class="priority-label">Priorität:</span>
        {#each [[0, 'Normal'], [5, 'Hoch'], [10, 'Sofort']] as [val, label]}
          <button class="priority-btn" class:active={selectedPriority === val}
                  onclick={() => selectedPriority = val}>{label}</button>
        {/each}
      </div>
      <button class="link-btn" onclick={() => showBatch = !showBatch}>
        {showBatch ? 'Schließen' : 'Batch Download (mehrere URLs)'}
      </button>
    </div>

    {#if showBatch}
      <div class="batch-area">
        <textarea class="textarea" bind:value={batchInput} rows="4"
          placeholder="Eine URL pro Zeile…"></textarea>
        <button class="btn-primary" onclick={addBatch}
          disabled={!batchInput.trim()}>
          {batchInput.split('\n').filter(l=>l.trim()).length} Downloads starten
        </button>
      </div>
    {/if}
  </div>

  <!-- Resolved Video Info -->
  {#if videoInfo}
    <div class="resolved-panel">
      <div class="resolved-header">
        {#if videoInfo.id}
          <img class="resolved-thumb" src={api.rssThumbUrl(videoInfo.id)} alt="" />
        {/if}
        <div class="resolved-info">
          <h3>{videoInfo.title}</h3>
          <span class="resolved-meta">
            {videoInfo.channel_name} · {formatDuration(videoInfo.duration)}
            {#if videoInfo.already_downloaded}
              <span class="already-badge">Bereits heruntergeladen</span>
            {/if}
          </span>
        </div>
      </div>

      <div class="stream-section">
        <h4>Verfügbare Streams</h4>

        {#if progressiveStreams.length > 0}
          <div class="stream-group">
            <span class="stream-label">Progressive (Video+Audio)</span>
            {#each progressiveStreams as s}
              <label class="stream-option" class:selected={selectedQuality === s.quality}>
                <input type="radio" name="quality" value={s.quality}
                  bind:group={selectedQuality} />
                <span class="sq">{s.quality}</span>
                <span class="sf">{formatSize(s.file_size)}</span>
                <span class="sc">{s.codec}</span>
              </label>
            {/each}
          </div>
        {/if}

        {#if adaptiveVideo.length > 0}
          <div class="stream-group">
            <span class="stream-label">Adaptive (Video only, wird mit Audio gemerged)</span>
            {#each adaptiveVideo.slice(0, 5) as s}
              <label class="stream-option" class:selected={selectedQuality === `adaptive_${s.quality}`}>
                <input type="radio" name="quality" value={`adaptive_${s.quality}`}
                  onclick={() => selectedQuality = s.quality} />
                <span class="sq">{s.quality}{s.fps ? ` ${s.fps}fps` : ''}</span>
                <span class="sf">{formatSize(s.file_size)} + Audio</span>
                <span class="sc">{s.codec}</span>
              </label>
            {/each}
          </div>
        {/if}
      </div>

      <div class="resolved-actions">
        <button class="btn-primary btn-lg" onclick={startDownload}>
          <i class="fa-solid fa-download"></i> Download starten ({selectedQuality})
        </button>
        <button class="btn-ghost" onclick={() => videoInfo = null}>Abbrechen</button>
      </div>
    </div>
  {/if}

  <!-- Resolved: Playlist -->
  {#if playlistInfo}
    <div class="resolved-panel pl-panel">
      <div class="pl-panel-header">
        <div class="pl-panel-info">
          <span class="pl-type-badge"><i class="fa-solid fa-list-ul"></i> Playlist</span>
          <h3>{playlistInfo.title}</h3>
          <span class="resolved-meta">
            {playlistInfo.owner || 'Unbekannt'} · {playlistInfo.videos.length} Videos
            {#if playlistInfo.videos.filter(v => v.already_downloaded).length > 0}
              · <span class="already-badge">{playlistInfo.videos.filter(v => v.already_downloaded).length} bereits vorhanden</span>
            {/if}
          </span>
        </div>
        <div class="pl-panel-actions">
          <button class="btn-primary" onclick={plDownloadAll}
            disabled={playlistInfo.videos.every(v => v.already_downloaded)}>
            <i class="fa-solid fa-download"></i>
            {playlistInfo.videos.filter(v => !v.already_downloaded).length} fehlende laden
          </button>
          <button class="btn-ghost" onclick={() => playlistInfo = null}>Schließen</button>
        </div>
      </div>
      <div class="pl-video-list">
        {#each playlistInfo.videos as v, idx (v.id)}
          <div class="pl-video-row" class:downloaded={v.already_downloaded}>
            <span class="pl-video-idx">{idx + 1}</span>
            {#if v.id}
              <img class="pl-video-thumb" src={api.rssThumbUrl(v.id)} alt="" loading="lazy" />
            {:else}
              <div class="pl-video-thumb placeholder"><i class="fa-solid fa-film"></i></div>
            {/if}
            <div class="pl-video-info">
              <span class="pl-video-title">{v.title}</span>
              <span class="pl-video-meta">
                {v.channel_name || ''}
                {#if v.duration} · {formatDuration(v.duration)}{/if}
              </span>
            </div>
            <div class="pl-video-status">
              {#if v.already_downloaded}
                <span class="status-ok"><i class="fa-solid fa-check"></i></span>
              {:else if plDownloading.has(v.id)}
                <i class="fa-solid fa-spinner fa-spin"></i>
              {:else}
                <button class="btn-icon-sm" onclick={() => plDownloadOne(v.id)} title="Herunterladen">
                  <i class="fa-solid fa-download"></i>
                </button>
              {/if}
            </div>
          </div>
        {/each}
      </div>
    </div>
  {/if}

  <!-- Resolved: Channel -->
  {#if channelInfo}
    <div class="resolved-panel ch-panel">
      <div class="ch-panel-header">
        <span class="pl-type-badge"><i class="fa-solid fa-user"></i> Kanal</span>
        <h3>{channelInfo.channel_name}</h3>
        <span class="resolved-meta">{channelInfo.channel_id}</span>
      </div>
      <div class="resolved-actions">
        {#if channelInfo.already_subscribed}
          <button class="btn-secondary" disabled><i class="fa-solid fa-check"></i> Bereits abonniert</button>
        {:else}
          <button class="btn-primary" onclick={subscribeChannel}><i class="fa-solid fa-rss"></i> Kanal abonnieren</button>
        {/if}
        <button class="btn-ghost" onclick={() => channelInfo = null}>Schließen</button>
      </div>
    </div>
  {/if}

  <!-- Queue -->
  {#if queue.queue.length > 0 || systemJobs.length > 0}
    <div class="queue-section">
      <div class="queue-header">
        <h2>Warteschlange</h2>
        <div class="queue-actions">
          {#if systemJobs.length > 0}
            <div class="jobs-tabs">
              {#each [['all','Alle'],['active','Aktiv'],['done','Fertig'],['error','Fehler']] as [id, label]}
                <button class="jobs-tab" class:active={jobsTab === id} onclick={() => jobsTab = id}>
                  {label}
                  {#if jobCounts[id] > 0}<span class="jobs-tab-count">{jobCounts[id]}</span>{/if}
                </button>
              {/each}
            </div>
          {/if}
          {#if queue.failed_count > 0}
            <button class="link-btn link-retry" onclick={retryAllFailed}>
              <i class="fa-solid fa-rotate-right"></i> Alle erneut ({queue.failed_count})
            </button>
          {/if}
          <button class="link-btn" onclick={fixStale}>Stale fixen</button>
          <button class="link-btn" onclick={clearDone}>Fertige entfernen</button>
          <button class="link-btn link-danger" onclick={clearAll}>Alle bereinigen</button>
        </div>
      </div>

      {#each queue.queue as item (item.id)}
        {@const live = getLive(item.id)}
        {@const stage = live?.stage || item.status}
        {@const progress = live?.progress ?? item.progress ?? 0}
        {@const label = live?.stage_label || ''}

        <div class="queue-item" class:item-active={item.status === 'active'}
             class:item-done={item.status === 'done'}
             class:item-error={item.status === 'error'}
             class:item-cancelled={item.status === 'cancelled'}
             class:item-retry-wait={item.status === 'retry_wait'}>

          <div class="qi-icon">{@html stageIcon(stage)}</div>

          <div class="qi-body">
            <div class="qi-top">
              <span class="qi-vid">{item.title || item.video_id}</span>
              {#if item.priority > 0}
                <span class="qi-priority" class:high={item.priority >= 5}>P{item.priority}</span>
              {/if}
            </div>

            {#if item.status === 'active' && progress > 0}
              <DownloadProgress data={{
                progress,
                stage,
                stage_label: label,
                phases: live?.phases || null,
              }} />
            {:else if item.status === 'done'}
              <DownloadProgress data={{
                progress: 1.0,
                stage: 'done',
                stage_label: 'Abgeschlossen',
                phases: (live?.phases || []).map(p => ({ ...p, status: 'done' })),
              }} />
            {:else if item.status === 'error'}
              <DownloadProgress data={{
                progress: progress || 0,
                stage: 'error',
                stage_label: item.error_message || 'Fehler',
                phases: live?.phases || null,
              }} />
            {:else if item.status === 'active'}
              <span class="qi-stage-text">{label || stage}</span>
            {/if}

            <!-- error_message wird bereits in DownloadProgress stage_label angezeigt -->
          </div>

          <div class="qi-actions">
            {#if item.status === 'queued' || item.status === 'active'}
              <button class="qi-btn" onclick={() => cancelItem(item.id)} title="Abbrechen"><i class="fa-solid fa-xmark"></i></button>
            {/if}
            {#if item.status === 'retry_wait'}
              <button class="qi-btn retry" onclick={() => retryItem(item.id)} title="Sofort starten"><i class="fa-solid fa-play"></i></button>
              <button class="qi-btn" onclick={() => cancelItem(item.id)} title="Abbrechen"><i class="fa-solid fa-xmark"></i></button>
            {/if}
            {#if item.status === 'error' || item.status === 'cancelled'}
              <button class="qi-btn retry" onclick={() => retryItem(item.id)} title="Sofort erneut"><i class="fa-solid fa-rotate-right"></i></button>
              <button class="qi-btn retry-delay" onclick={() => retryDelayed(item.id, 5)} title="In 5 Min erneut"><i class="fa-solid fa-clock"></i> 5m</button>
              <button class="qi-btn retry-delay" onclick={() => retryDelayed(item.id, 30)} title="In 30 Min erneut"><i class="fa-solid fa-clock"></i> 30m</button>
            {/if}
          </div>
        </div>
      {/each}

      <!-- System-Jobs (Scans, RSS, etc.) inline in Queue -->
      {#each filteredJobs as job (job.id)}
        {@const meta = job.metadata || {}}
        <div class="queue-item"
             class:item-active={job.status === 'active'}
             class:item-done={job.status === 'done'}
             class:item-error={job.status === 'error'}
             class:item-cancelled={job.status === 'cancelled'}
             class:item-retry-wait={job.status === 'queued'}>

          <div class="qi-icon">
            <i class="fa-solid {JOB_TYPE_ICONS[job.type] || 'fa-circle'}"></i>
          </div>

          <div class="qi-body">
            <div class="qi-top">
              <span class="qi-type-tag">{JOB_TYPE_LABELS[job.type] || job.type}</span>
              <span class="qi-vid">{job.title || ''}</span>
              {#if job.priority > 0}
                <span class="qi-priority" class:high={job.priority >= 5}>P{job.priority}</span>
              {/if}
            </div>

            <!-- Kanalscan: spezielle Anzeige -->
            {#if job.type === 'channel_scan' && job.status === 'active'}
              {@const videoCount = meta.video_count || 0}
              {@const shortCount = meta.short_count || 0}
              {@const liveCount = meta.live_count || 0}
              {@const foundTotal = videoCount + shortCount + liveCount}
              {@const estTotal = meta.estimated_total || 0}
              {@const precountRunning = meta.precount_running || 0}
              {@const precountExceeded = meta.precount_exceeded || false}
              {@const precountExtra = meta.precount_extra || 0}
              {@const batchSaved = meta.batch_saved || 0}
              {@const saveCurrent = meta.save_current || 0}
              {@const saveTotal = meta.save_total || 0}
              {@const phase = meta.phase || ''}
              {@const showEst = estTotal > 0 && estTotal >= foundTotal && !precountExceeded}
              {@const pct = phase === 'saving' && saveTotal > 0
                ? (saveCurrent / saveTotal) * 100
                : phase === 'precount'
                  ? Math.min((precountRunning / Math.max(precountRunning + 100, 500)) * 100, 90)
                  : showEst
                    ? Math.min((foundTotal / estTotal) * 100, 99)
                    : (job.progress * 100)}
              <div class="job-scan-progress">
                <div class="job-prog-bar">
                  <div class="job-prog-fill" style="width:{pct.toFixed(1)}%"></div>
                </div>
                <div class="job-scan-detail">
                  <span>
                    {#if phase === 'saving' && saveTotal > 0}
                      Speichere {saveCurrent} / {saveTotal}
                    {:else if phase === 'connecting' || phase === 'metadata'}
                      {job.description || 'Verbinde…'}
                    {:else if phase === 'precount'}
                      Zähle Videos… {precountRunning > 0 ? precountRunning : ''}
                    {:else}
                      {#if videoCount > 0}{videoCount} Videos{/if}
                      {#if shortCount > 0}{videoCount > 0 ? ', ' : ''}{shortCount} Shorts{/if}
                      {#if liveCount > 0}{(videoCount + shortCount) > 0 ? ', ' : ''}{liveCount} Live{/if}
                      {#if precountExceeded}
                        <span class="scan-exceeded"> -  +{precountExtra} weitere gefunden</span>
                      {:else if showEst}
                        / ~{estTotal} erwartet
                      {/if}
                      {#if batchSaved > 0}
                        <span class="scan-saved"> · {batchSaved} gesichert</span>
                      {/if}
                    {/if}
                  </span>
                  <span class="job-phase">
                    {phase === 'connecting' ? 'Verbinde…' :
                     phase === 'metadata' ? 'Metadaten' :
                     phase === 'precount' ? 'Vorschau' :
                     phase === 'videos' ? 'Videos laden' :
                     phase === 'shorts' ? 'Shorts laden' :
                     phase === 'live' ? 'Livestreams' :
                     phase === 'saving' ? 'Speichern' : phase || ''}
                    {#if (phase === 'videos' || phase === 'shorts' || phase === 'live')}{@const eta = getScanEta(job.id, foundTotal, estTotal)}{#if eta}<span class="scan-eta"> · {eta}</span>{/if}{/if}
                  </span>
                </div>
              </div>
            {:else if job.status === 'active' && job.progress > 0}
              <div class="job-scan-progress">
                <div class="job-prog-bar">
                  <div class="job-prog-fill" style="width:{(job.progress * 100).toFixed(1)}%"></div>
                </div>
                <div class="job-scan-detail">
                  <span>{job.description || ''}</span>
                  <span>{(job.progress * 100).toFixed(0)}%</span>
                </div>
              </div>
            {:else if job.description && job.status !== 'queued'}
              <div class="qi-stage-text">{job.description}</div>
            {/if}

            {#if job.completed_at}
              <div class="qi-time">{formatDateRelative(job.completed_at)}</div>
            {/if}
          </div>

          <div class="qi-actions">
            {#if job.status === 'active' || job.status === 'queued'}
              <button class="qi-btn" onclick={() => cancelSystemJob(job.id)} title="Abbrechen">
                <i class="fa-solid fa-xmark"></i>
              </button>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .page { padding: 24px; padding-bottom: 60px; max-width: 900px; }
  .page-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:16px; flex-wrap:wrap; gap:8px; }
  .title { font-size:1.5rem; font-weight:700; color:var(--text-primary); margin:0; }

  .queue-stats { display:flex; gap:10px; }
  .qs { font-size:0.78rem; font-weight:600; padding:3px 10px; border-radius:12px; }
  .qs.active { background:var(--status-info-bg); color:var(--status-info); }
  .qs.queued { background:var(--status-pending-bg, var(--bg-tertiary)); color:var(--status-pending); }
  .qs.done { background:var(--status-success-bg); color:var(--status-success); }
  .qs.error { background:var(--status-error-bg); color:var(--status-error); }
  .qs.cancelled { background:rgba(245,158,11,0.15); color:var(--status-warning, #f59e0b); }
  .qs.retry-wait { background:rgba(139,92,246,0.15); color:#8b5cf6; }

  .input-section { background:var(--bg-secondary); border:1px solid var(--border-primary); border-radius:12px; padding:16px; margin-bottom:20px; }
  .url-row { display:flex; gap:8px; flex-wrap:wrap; }
  .input { flex:1; min-width:200px; padding:9px 14px; background:var(--bg-tertiary); border:1px solid var(--border-primary); border-radius:8px; color:var(--text-primary); font-size:0.88rem; outline:none; box-sizing:border-box; }
  .input:focus { border-color:var(--accent-primary); }
  .textarea { width:100%; padding:9px 14px; background:var(--bg-tertiary); border:1px solid var(--border-primary); border-radius:8px; color:var(--text-primary); font-family:monospace; font-size:0.82rem; outline:none; resize:vertical; box-sizing:border-box; }
  .input-sub { margin-top:8px; display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:8px; }
  .priority-row { display:flex; align-items:center; gap:6px; }
  .priority-label { font-size:0.78rem; color:var(--text-tertiary); }
  .priority-btn { padding:3px 10px; background:var(--bg-tertiary); border:1px solid var(--border-primary); border-radius:6px; font-size:0.76rem; cursor:pointer; color:var(--text-secondary); transition:all 0.12s; }
  .priority-btn.active { background:var(--accent-primary); color:#fff; border-color:var(--accent-primary); }
  .priority-btn:hover:not(.active) { border-color:var(--accent-primary); }
  .link-btn { background:none; border:none; color:var(--accent-primary); font-size:0.82rem; cursor:pointer; padding:0; }
  .link-btn:hover { text-decoration:underline; }
  .batch-area { margin-top:10px; display:flex; flex-direction:column; gap:8px; }
  .btn-secondary:disabled { opacity:0.5; }

  /* Resolved Panel */
  .resolved-panel { background:var(--bg-secondary); border:1px solid var(--accent-primary); border-radius:12px; padding:20px; margin-bottom:20px; }
  .resolved-header { display:flex; gap:16px; align-items:flex-start; margin-bottom:16px; }
  .resolved-thumb { width:200px; border-radius:8px; aspect-ratio:16/9; object-fit:cover; }
  .resolved-info { flex:1; }
  .resolved-info h3 { margin:0 0 6px; font-size:1rem; color:var(--text-primary); line-height:1.3; }
  .resolved-meta { font-size:0.82rem; color:var(--text-secondary); }
  .already-badge { background:var(--status-warning-bg); color:var(--status-warning); padding:2px 8px; border-radius:6px; font-size:0.72rem; font-weight:700; margin-left:8px; }
  .stream-group { margin-bottom:12px; }
  .stream-label { font-size:0.75rem; color:var(--text-tertiary); display:block; margin-bottom:6px; }
  .sq { font-weight:600; color:var(--text-primary); min-width:60px; }
  .sf { color:var(--text-secondary); min-width:80px; }
  .sc { color:var(--text-tertiary); font-size:0.75rem; }

  .resolved-actions { display:flex; gap:8px; align-items:center; }

  /* Queue */
  .queue-section { margin-top:8px; }
  .queue-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:10px; }
  .queue-header h2 { font-size:1.1rem; color:var(--text-primary); margin:0; }
  .queue-actions { display:flex; gap:12px; }
  .link-danger { color:var(--status-error); }
  .link-danger:hover { color:var(--status-error); }
  .link-retry { color:var(--status-info, #3b82f6); font-weight:600; }
  .link-retry:hover { color:var(--accent-primary); }

  .queue-item { display:flex; align-items:flex-start; gap:10px; padding:10px 14px; border-radius:10px; margin-bottom:6px; background:var(--bg-secondary); border:1px solid var(--border-primary); transition:border-color 0.15s; position:relative; }
  .item-active { border-left:3px solid var(--status-info); background:var(--status-info-bg); }
  .item-done { opacity:0.75; }
  .item-done :global(.dp-wrap) { opacity: 0.85; }
  .item-error { border-left:3px solid var(--status-error); }
  .item-cancelled { border-left:3px solid var(--status-warning, #f59e0b); opacity:0.75; }
  .item-retry-wait { border-left:3px solid #8b5cf6; background:rgba(139,92,246,0.05); }

  .qi-icon { font-size:1.1rem; margin-top:2px; }
  .qi-body { flex:1; min-width:0; }
  .qi-top { display:flex; justify-content:space-between; align-items:center; gap:8px; }
  .qi-vid { font-size:0.82rem; font-weight:600; color:var(--text-primary); font-family:monospace; }
  .qi-stage-text { font-size:0.72rem; color:var(--text-secondary); margin-top:4px; display:block; }
  
  .qi-priority { font-size:0.65rem; padding:1px 5px; border-radius:4px; background:var(--bg-tertiary); color:var(--text-tertiary); font-weight:700; }
  .qi-priority.high { background:var(--status-warning-bg, #fef3c7); color:var(--status-warning); }

  /* Alter Progress-Balken entfernt -  siehe DownloadProgress.svelte */

  .qi-error { font-size:0.75rem; color:var(--status-error); margin-top:4px; word-break:break-word; }

  .qi-actions { position:absolute; top:6px; right:6px; z-index:2; display:flex; gap:4px; }
  .qi-btn { width:28px; height:28px; display:flex; align-items:center; justify-content:center; background:var(--bg-tertiary); border:1px solid var(--border-primary); border-radius:6px; cursor:pointer; font-size:0.82rem; }
  .qi-btn:hover { border-color:var(--status-error); color:var(--status-error); }
  .qi-btn.retry:hover { border-color:var(--status-info); color:var(--status-info); }
  .qi-btn.retry-delay { font-size:0.68rem; gap:2px; }
  .qi-btn.retry-delay:hover { border-color:#8b5cf6; color:#8b5cf6; }

  .worker-warning {
    display: flex; align-items: center; gap: 10px; padding: 10px 14px;
    background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.3);
    border-radius: 8px; margin-bottom: 14px; font-size: 0.85rem; color: var(--text-primary);
  }
  .worker-warning > i { color: #ef4444; font-size: 1.1rem; flex-shrink: 0; }
  .worker-warning > span { flex: 1; }

  /* Playlist Panel */
  .pl-panel { border-color: var(--accent-secondary, var(--accent-primary)); }
  .pl-panel-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 14px; flex-wrap: wrap; }
  .pl-panel-info { flex: 1; min-width: 0; }
  .pl-panel-info h3 { margin: 4px 0 4px; font-size: 1rem; color: var(--text-primary); }
  .pl-panel-actions { display: flex; gap: 8px; align-items: center; flex-shrink: 0; }
  .pl-type-badge {
    display: inline-flex; align-items: center; gap: 4px;
    font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
    color: var(--accent-primary); letter-spacing: 0.04em;
  }
  .pl-video-list {
    max-height: 420px; overflow-y: auto; border: 1px solid var(--border-primary);
    border-radius: 8px; scrollbar-width: thin; scrollbar-color: var(--border-primary) transparent;
  }
  .pl-video-row {
    display: flex; align-items: center; gap: 8px; padding: 6px 10px;
    border-bottom: 1px solid var(--border-primary);
  }
  .pl-video-row:last-child { border-bottom: none; }
  .pl-video-row.downloaded { opacity: 0.55; }
  .pl-video-idx { width: 24px; text-align: center; font-size: 0.72rem; color: var(--text-tertiary); flex-shrink: 0; }
  .pl-video-thumb { width: 80px; height: 45px; border-radius: 4px; object-fit: cover; flex-shrink: 0; background: var(--bg-tertiary); }
  .pl-video-thumb.placeholder { display: flex; align-items: center; justify-content: center; color: var(--text-tertiary); font-size: 0.9rem; }
  .pl-video-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  .pl-video-title { font-size: 0.8rem; font-weight: 500; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .pl-video-meta { font-size: 0.68rem; color: var(--text-tertiary); }
  .pl-video-status { flex-shrink: 0; width: 32px; display: flex; align-items: center; justify-content: center; }
  .status-ok { color: var(--status-success); font-size: 0.8rem; }
  .btn-icon-sm { width: 28px; height: 28px; border-radius: 6px; border: 1px solid var(--border-primary); background: var(--bg-primary); color: var(--text-secondary); cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 0.72rem; }
  .btn-icon-sm:hover { border-color: var(--accent-primary); color: var(--accent-primary); }

  /* Channel Panel */
  .ch-panel-header { margin-bottom: 12px; }
  .ch-panel-header h3 { margin: 4px 0 2px; font-size: 1.1rem; color: var(--text-primary); }

  /* ═══ Job Filter Tabs ═══ */
  .jobs-tabs { display: flex; gap: 2px; }
  .jobs-tab {
    padding: 4px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-primary);
    border-radius: 6px; font-size: 0.75rem; cursor: pointer; color: var(--text-secondary);
    display: flex; align-items: center; gap: 4px; transition: all 0.12s;
  }
  .jobs-tab:hover { border-color: var(--accent-primary); }
  .jobs-tab.active { background: var(--accent-primary); color: #fff; border-color: var(--accent-primary); }
  .jobs-tab-count {
    font-size: 0.65rem; font-weight: 700; background: rgba(255,255,255,0.2);
    padding: 0 4px; border-radius: 4px;
  }
  .jobs-tab.active .jobs-tab-count { background: rgba(255,255,255,0.25); }

  .qi-type-tag {
    font-size: 0.62rem; font-weight: 700; text-transform: uppercase;
    color: var(--accent-primary); letter-spacing: 0.03em;
    padding: 1px 6px; border-radius: 3px;
    background: rgba(99,102,241,0.1); flex-shrink: 0;
  }
  .qi-time { font-size: 0.65rem; color: var(--text-tertiary); margin-top: 3px; }

  /* Scan-Progress (Kanalscan etc.) */
  .job-scan-progress { margin-top: 6px; }
  .job-prog-bar { height: 5px; background: var(--bg-primary); border-radius: 3px; overflow: hidden; }
  .job-prog-fill { height: 100%; background: #00BCD4; border-radius: 3px; transition: width 0.5s ease; }
  .job-scan-detail {
    display: flex; justify-content: space-between; align-items: center;
    font-size: 0.68rem; color: var(--text-secondary); margin-top: 2px;
  }
  .job-phase { font-size: 0.62rem; font-weight: 600; text-transform: uppercase; color: #00BCD4; }
  .scan-exceeded { color: var(--text-tertiary); font-size: 0.72rem; font-style: italic; }
  .scan-saved { color: var(--status-success); font-size: 0.68rem; opacity: 0.7; }
  .scan-eta { color: var(--text-tertiary); font-weight: 400; text-transform: none; }
</style>

<script>
  import { api, createActivitySocket } from '../lib/api/client.js';
  import { toast } from '../lib/stores/notifications.js';
  import { pendingDownloadUrl } from '../lib/stores/app.js';
  import { formatDuration, formatSize } from '../lib/utils/format.js';
  import { formatDateRelative } from '../lib/utils/format.js';
  import DownloadProgress from '../lib/components/common/DownloadProgress.svelte';
  import ConfirmDialog from '../lib/components/common/ConfirmDialog.svelte';
  let confirmRef;

  let queue = $state({ queue: [], active_count: 0, queued_count: 0, completed_count: 0, error_count: 0, cancelled_count: 0, retry_wait_count: 0, failed_count: 0 });
  let urlInput = $state('');

  // Live-Throttling + Cooldown-Einstellungen
  const THROTTLE_DEFAULT = 0;
  const COOLDOWN_DEFAULT = 30;
  let throttleKbps = $state(0);
  let throttleRealtime = $state(false);  // dynamisch: filesize/duration pro Video
  let cooldownSec = $state(30);
  let settingsSaving = $state(false);

  async function loadDownloadSettings() {
    try {
      const [t, r, c] = await Promise.all([
        api.getSetting('download.throttle_kbps').catch(() => ({ value: 0 })),
        api.getSetting('download.throttle_realtime').catch(() => ({ value: 'false' })),
        api.getSetting('download.cooldown_base_s').catch(() => ({ value: 30 })),
      ]);
      throttleKbps = parseInt(t?.value || 0) || 0;
      throttleRealtime = String(r?.value).toLowerCase() === 'true';
      cooldownSec = parseInt(c?.value || 30) || 30;
    } catch {}
  }
  async function saveThrottle() {
    settingsSaving = true;
    try {
      await api.setDownloadThrottle(throttleKbps, throttleRealtime);
      if (throttleRealtime) toast.success('Drosselung: dynamisch (nach Videolänge)');
      else if (throttleKbps > 0) toast.success(`Drosselung: ${throttleKbps} KB/s`);
      else toast.success('Drosselung ausgeschaltet');
    } catch (e) { toast.error(e.message); }
    settingsSaving = false;
  }
  async function toggleRealtime() {
    throttleRealtime = !throttleRealtime;
    await saveThrottle();
  }
  async function saveCooldown(v) {
    // Validierung: leere/ungültige Eingaben nicht übernehmen
    const num = parseInt(v);
    if (isNaN(num) || num < 0 || num > 3600) {
      // zurücksetzen auf letzten gültigen Wert
      cooldownSec = cooldownSec > 0 ? cooldownSec : 30;
      return;
    }
    settingsSaving = true;
    try {
      await api.setDownloadCooldown(num);
      cooldownSec = num;
      toast.success(`Wartezeit: ${num}s zwischen Downloads`);
    } catch (e) { toast.error(e.message); }
    settingsSaving = false;
  }
  function resetDefaults() {
    throttleKbps = THROTTLE_DEFAULT;
    throttleRealtime = false;
    saveThrottle();
    saveCooldown(COOLDOWN_DEFAULT);
  }
  let batchInput = $state('');
  let showBatch = $state(false);
  let resolving = $state(false);
  let videoInfo = $state(null);
  let playlistInfo = $state(null);
  let channelInfo = $state(null);
  // leer = nichts gewählt: Kanal bzw. Standard-Qualität aus den Einstellungen
  let selectedQuality = $state('');
  let selectedPriority = $state(0);
  let socket = $state(null);
  let plDownloading = $state(new Set());

  // Worker Health
  let workerDead = $state(false);
  let restartingWorker = $state(false);

  // Live-Status aus WebSocket (ergänzt Queue-Daten)
  let liveStatus = $state({});
  // Pro-Job Pro-Phase-Füllstand (0..1): jede Download-Phase (v.a. Video ↓ / Audio ↓)
  // merkt sich ihren EIGENEN Fortschritt aus ihren eigenen asynchronen Events,
  // damit beide Balken-Abschnitte sich unabhängig füllen (kein springender Gesamtwert).
  let phaseFills = $state({});

  // System-Jobs (nicht-Download: Scans, RSS, AI, etc.)
  let systemJobs = $state([]);
  let jobsTab = $state('all'); // all, active, done, error
  let selectedId = $state(null); // Klick auf Download-Zeile → Detail-Panel rechts

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

  let currentThrottleLive = $state(0); // Live-Wert aus dem cooldown-Broadcast

  // Stage-Reihenfolge für den Monotonie-Schutz (siehe unten)
  const STAGE_RANK = { resolving: 0, resolved: 1, downloading_video: 2, downloading_audio: 3, merging: 4, finalizing: 5, done: 6 };

  function handleWsMessage(msg) {
    // Live-Throttle aus cooldown-Broadcast aufnehmen
    if (msg.type === 'cooldown' && typeof msg.current_throttle_kbps === 'number') {
      currentThrottleLive = msg.current_throttle_kbps;
    }
    const id = msg.job_id || msg.queue_id;
    if (id) {
      // Monotonie-Schutz: verwirft veraltete/parallele Rückwärts-Updates innerhalb
      // eines laufenden Downloads. Ohne das toggelt die Anzeige zwischen Phasen
      // (z.B. Video 26% ↔ Audio 85%), wenn zwei Progress-Quellen fürs selbe Video
      // durcheinanderfunken. Ein echter Neustart setzt Status auf queued/retry_wait
      // (nicht 'active') und hebt die Sperre damit auf.
      const prev = liveStatus[id];
      if (prev && prev.status === 'active' && msg.status === 'active') {
        const pr = STAGE_RANK[prev.stage] ?? -1;
        const nr = STAGE_RANK[msg.stage] ?? -1;
        if (nr < pr) return;                                             // Stage-Rückschritt
        if (nr === pr && (msg.progress ?? 0) < (prev.progress ?? 0) - 0.02) return; // Progress-Rückschritt
      }
      liveStatus[id] = msg;
      liveStatus = { ...liveStatus };

      // Pro-Phase-Füllstand pflegen: aktive Download-Phase aus ihren eigenen Bytes,
      // fertige Phasen (Backend-phases[].status==='done') voll, bei Neustart/Terminal
      // leeren. So füllen sich Video ↓ und Audio ↓ unabhängig aus ihren Events.
      if (msg.status && msg.status !== 'active') {
        if (phaseFills[id]) { delete phaseFills[id]; phaseFills = { ...phaseFills }; }
      } else {
        let next = { ...(phaseFills[id] || {}) };
        let changed = false;
        if (typeof msg.stage === 'string' && msg.stage.startsWith('downloading_') && (msg.bytes_total || 0) > 0) {
          const frac = Math.max(0, Math.min(1, (msg.bytes_done || 0) / msg.bytes_total));
          if (frac > (next[msg.stage] ?? 0)) { next[msg.stage] = frac; changed = true; }
        }
        if (Array.isArray(msg.phases)) {
          for (const p of msg.phases) {
            if (p.status === 'done' && next[p.id] !== 1) { next[p.id] = 1; changed = true; }
          }
        }
        if (changed) { phaseFills[id] = next; phaseFills = { ...phaseFills }; }
      }
    }
    // Queue aktualisieren wenn Terminal-Status (inkl. 'parked')
    const terminal = ['done', 'error', 'cancelled', 'parked'];
    if (terminal.includes(msg.status) || terminal.includes(msg.stage)) {
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

  // Playlist: Einzelnes Video laden (Quality aus Settings, nicht hardcoded)
  async function plDownloadOne(videoId) {
    plDownloading = new Set([...plDownloading, videoId]);
    try {
      await api.addDownload({ url: `https://www.youtube.com/watch?v=${videoId}`, priority: selectedPriority });
      toast.success('Download gestartet');
      loadQueue();
    } catch (e) { toast.error(e.message); }
    plDownloading = new Set([...plDownloading].filter(id => id !== videoId));
  }

  // Playlist: Alle fehlenden laden (Quality aus Settings)
  async function plDownloadAll() {
    if (!playlistInfo) return;
    const missing = playlistInfo.videos.filter(v => !v.already_downloaded);
    toast.info(`${missing.length} Downloads werden gestartet…`);
    let ok = 0;
    for (const v of missing) {
      try {
        await api.addDownload({ url: `https://www.youtube.com/watch?v=${v.id}`, priority: selectedPriority });
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
        quality: selectedQuality || undefined,
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
      // Keine quality mitgeben → Backend nimmt die Settings-Default
      // (vorher hardcoded 'best', ignorierte User-Einstellung)
      await api.addDownload({ url: urlInput.trim(), priority: selectedPriority });
      toast.success('Download gestartet');
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
  async function ignoreVideoPermanent(item) {
    const name = item.title || item.video_id;
    if (!await confirmRef.ask(`„${name.slice(0, 40)}…" ausschließen?`, 'Wird beim Kanal als nicht-ladbar markiert.', { confirmLabel: 'Ausschließen' })) return;
    try {
      await api.ignoreVideo(item.video_id || item.id, item.channel_id || null,
                            item.error_message || 'Manuell ausgeschlossen');
      // Aus Queue entfernen
      await api.cancelDownload(item.id);
      toast.success(`„${name}" dauerhaft ausgeschlossen`);
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

  // Priorität eines Queue-Items zyklisch ändern: 0 → 5 → 10 → 0
  const PRIORITY_CYCLE = [0, 5, 10];
  const PRIORITY_LABELS = { 0: 'Normal', 5: 'Hoch', 10: 'Sofort' };
  async function cyclePriority(id, currentPrio, e) {
    e?.stopPropagation?.();
    const idx = PRIORITY_CYCLE.indexOf(currentPrio);
    const next = PRIORITY_CYCLE[(idx + 1) % PRIORITY_CYCLE.length];
    try {
      await api.setDownloadPriority(id, next);
      toast.success(`Priorität → ${PRIORITY_LABELS[next]}`);
      loadQueue();
    } catch (e) { toast.error('Priorität: ' + e.message); }
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

  // Einheitlicher Filter – wirkt auf Downloads UND System-Jobs
  function matchesTab(item, tab) {
    if (tab === 'all') return true;
    if (tab === 'active') return item.status === 'active';
    if (tab === 'wait') return item.status === 'queued' || item.status === 'retry_wait';
    if (tab === 'done') return item.status === 'done';
    if (tab === 'error') return item.status === 'error' || item.status === 'parked';
    if (tab === 'cancelled') return item.status === 'cancelled';
    return true;
  }

  let filteredQueue = $derived(queue.queue.filter(q => matchesTab(q, jobsTab)));
  // Ausgewählter Download für das Detail-Panel (immer live aus der Queue gezogen)
  let selected = $derived(selectedId != null ? (queue.queue.find(q => q.id === selectedId) || null) : null);
  function selectItem(id) { selectedId = (selectedId === id) ? null : id; }
  // Esc + Klick außerhalb schließen das Panel
  $effect(() => {
    if (selectedId == null) return;
    const onKey = (e) => { if (e.key === 'Escape') selectedId = null; };
    const onClick = (e) => {
      if (e.target.closest && (e.target.closest('.job') || e.target.closest('.detail-panel'))) return;
      selectedId = null;
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('click', onClick);
    return () => { document.removeEventListener('keydown', onKey); document.removeEventListener('click', onClick); };
  });
  let filteredJobs  = $derived(systemJobs.filter(j => matchesTab(j, jobsTab)));

  // Counts über Downloads + System-Jobs gesamt
  function countAll(tab) {
    const dl = queue.queue.filter(q => matchesTab(q, tab)).length;
    const sj = systemJobs.filter(j => matchesTab(j, tab)).length;
    return dl + sj;
  }
  let jobCounts = $derived({
    all: countAll('all'),
    active: countAll('active'),
    wait: countAll('wait'),
    done: countAll('done'),
    error: countAll('error'),
    cancelled: countAll('cancelled'),
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
    loadDownloadSettings();
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
  <!-- ── Command-Bar ── -->
  <header class="dtop">
    <div class="dbrand">
      <div class="dbrand-mark"><i class="fa-solid fa-bolt"></i></div>
      <div>
        <h1 class="dtitle">Downloads</h1>
        <p class="dtsub">Warteschlange &amp; Jobs</p>
      </div>
    </div>
    <div class="dtop-right">
      {#if workerDead}
        <span class="wchip dead"><span class="wdot"></span> Worker gestoppt</span>
      {:else}
        <span class="wchip ok"><span class="wdot"></span> Verarbeitung läuft</span>
      {/if}
      <button class="diconbtn" onclick={restartWorker} disabled={restartingWorker} title="Download-Worker neu starten">
        {#if restartingWorker}<i class="fa-solid fa-spinner fa-spin"></i>{:else}<i class="fa-solid fa-rotate"></i>{/if}
      </button>
    </div>
  </header>

  {#if workerDead}
    <div class="dbanner">
      <i class="fa-solid fa-triangle-exclamation"></i>
      <span><strong>Download-Worker gestoppt</strong> — Downloads werden nicht verarbeitet.</span>
      <button class="dbtn primary sm" onclick={restartWorker} disabled={restartingWorker}>
        {#if restartingWorker}<i class="fa-solid fa-spinner fa-spin"></i>{:else}<i class="fa-solid fa-rotate"></i>{/if}
        Worker neu starten
      </button>
    </div>
  {/if}

  <!-- ── Stat-Kacheln ── -->
  <div class="dstats">
    <div class="dstat act"><span><span class="k num">{jobCounts.active}</span><span class="l">aktiv</span></span></div>
    <div class="dstat wait"><span><span class="k num">{jobCounts.wait}</span><span class="l">wartend</span></span></div>
    <div class="dstat done"><span><span class="k num">{jobCounts.done}</span><span class="l">fertig</span></span></div>
    {#if jobCounts.error > 0}
      <div class="dstat err"><span><span class="k num">{jobCounts.error}</span><span class="l">Fehler</span></span></div>
    {/if}
    {#if jobCounts.cancelled > 0}
      <div class="dstat canc"><span><span class="k num">{jobCounts.cancelled}</span><span class="l">abgebrochen</span></span></div>
    {/if}
  </div>

  <!-- ── Aufgelöste Panels (volle Breite, wenn vorhanden) ── -->
  {#if videoInfo}
    <div class="panel resolved-panel">
      <div class="resolved-header">
        {#if videoInfo.id}
          <img class="resolved-thumb" src={api.rssThumbUrl(videoInfo.id)} alt="" />
        {/if}
        <div class="resolved-info">
          <h3>{videoInfo.title}</h3>
          <span class="resolved-meta">
            {videoInfo.channel_name} · {formatDuration(videoInfo.duration)}
            {#if videoInfo.already_downloaded}<span class="already-badge">Bereits heruntergeladen</span>{/if}
          </span>
        </div>
      </div>
      <div class="stream-section">
        <h4>Verfügbare Streams</h4>
        {#if progressiveStreams.length > 0}
          <div class="stream-group">
            <span class="stream-label">Progressive (Video+Audio)</span>
            <div class="opts">
              {#each progressiveStreams as s}
                <label class="opt" class:sel={selectedQuality === s.quality}>
                  <input type="radio" name="quality" value={s.quality} bind:group={selectedQuality} hidden />
                  <span class="rd"></span><span class="q">{s.quality}</span><span class="sz">{formatSize(s.file_size)}</span><span class="cd">{s.codec}</span>
                </label>
              {/each}
            </div>
          </div>
        {/if}
        {#if adaptiveVideo.length > 0}
          <div class="stream-group">
            <span class="stream-label">Adaptive (Video only, wird mit Audio gemerged)</span>
            <div class="opts">
              {#each adaptiveVideo.slice(0, 5) as s}
                <label class="opt" class:sel={selectedQuality === `adaptive_${s.quality}`}>
                  <input type="radio" name="quality" value={`adaptive_${s.quality}`} onclick={() => selectedQuality = s.quality} hidden />
                  <span class="rd"></span><span class="q">{s.quality}{s.fps ? ` ${s.fps}fps` : ''}</span><span class="sz">{formatSize(s.file_size)} + Audio</span><span class="cd">{s.codec}</span>
                </label>
              {/each}
            </div>
          </div>
        {/if}
      </div>
      <div class="resolved-actions">
        <button class="dbtn primary lg" onclick={startDownload}><i class="fa-solid fa-download"></i> Download starten ({selectedQuality || 'Standard-Qualität'})</button>
        <button class="dbtn ghost" onclick={() => videoInfo = null}>Abbrechen</button>
      </div>
    </div>
  {/if}

  {#if playlistInfo}
    <div class="panel resolved-panel">
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
          <button class="dbtn primary" onclick={plDownloadAll} disabled={playlistInfo.videos.every(v => v.already_downloaded)}>
            <i class="fa-solid fa-download"></i> {playlistInfo.videos.filter(v => !v.already_downloaded).length} fehlende laden
          </button>
          <button class="dbtn ghost" onclick={() => playlistInfo = null}>Schließen</button>
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
              <span class="pl-video-meta">{v.channel_name || ''}{#if v.duration} · {formatDuration(v.duration)}{/if}</span>
            </div>
            <div class="pl-video-status">
              {#if v.already_downloaded}
                <span class="status-ok"><i class="fa-solid fa-check"></i></span>
              {:else if plDownloading.has(v.id)}
                <i class="fa-solid fa-spinner fa-spin"></i>
              {:else}
                <button class="btn-icon-sm" onclick={() => plDownloadOne(v.id)} title="Herunterladen"><i class="fa-solid fa-download"></i></button>
              {/if}
            </div>
          </div>
        {/each}
      </div>
    </div>
  {/if}

  {#if channelInfo}
    <div class="panel resolved-panel">
      <div class="ch-panel-header">
        <span class="pl-type-badge"><i class="fa-solid fa-user"></i> Kanal</span>
        <h3>{channelInfo.channel_name}</h3>
        <span class="resolved-meta">{channelInfo.channel_id}</span>
      </div>
      <div class="resolved-actions">
        {#if channelInfo.already_subscribed}
          <button class="dbtn" disabled><i class="fa-solid fa-check"></i> Bereits abonniert</button>
        {:else}
          <button class="dbtn primary" onclick={subscribeChannel}><i class="fa-solid fa-rss"></i> Kanal abonnieren</button>
        {/if}
        <button class="dbtn ghost" onclick={() => channelInfo = null}>Schließen</button>
      </div>
    </div>
  {/if}

  <!-- ── Zwei-Spalten: Queue (Haupt) + Add/Einstellungen (Seite) ── -->
  <div class="dgrid">
    <!-- Haupt: Warteschlange -->
    <main class="panel dmain">
      <div class="panel-h">
        <h2>Warteschlange</h2>
        <span class="panel-sub">· {filteredQueue.length + filteredJobs.length} sichtbar</span>
        <div class="panel-spacer"></div>
        <div class="q-actions">
          {#if jobCounts.error > 0}
            <button class="link link-retry" onclick={retryAllFailed}><i class="fa-solid fa-rotate-right"></i> Alle erneut ({jobCounts.error})</button>
          {/if}
          <button class="link muted" onclick={fixStale} title="Festhängende Downloads zurück in die Warteschlange">Festhänger befreien</button>
          <button class="link muted" onclick={clearDone}>Fertige entfernen</button>
          <button class="link danger" onclick={clearAll}>Alle bereinigen</button>
        </div>
      </div>

      <div class="tabs">
        {#each [['all','Alle'],['active','Läuft'],['wait','Wartet'],['done','Fertig'],['error','Fehler'],['cancelled','Abgebrochen']] as [id, label]}
          <button class="tab" class:on={jobsTab === id} onclick={() => jobsTab = id}>
            {label}{#if jobCounts[id] > 0}<span class="c num">{jobCounts[id]}</span>{/if}
          </button>
        {/each}
      </div>

      <div class="jobs">
        {#each filteredQueue as item (item.id)}
          {@const live = getLive(item.id)}
          {@const stage = live?.stage || item.status}
          {@const progress = live?.progress ?? item.progress ?? 0}
          {@const label = live?.stage_label || ''}
          {@const canRetry = item.status === 'retry_wait' || item.status === 'error' || item.status === 'cancelled' || item.status === 'parked'}
          {@const canDelay = item.status === 'error' || item.status === 'cancelled' || item.status === 'parked'}
          {@const canCancel = item.status === 'queued' || item.status === 'active' || item.status === 'retry_wait'}
          <article class="job job-clickable"
                   class:s-active={item.status === 'active'}
                   class:s-queued={item.status === 'queued'}
                   class:s-wait={item.status === 'retry_wait'}
                   class:s-error={item.status === 'error' || item.status === 'parked'}
                   class:s-cancelled={item.status === 'cancelled'}
                   class:s-done={item.status === 'done'}
                   class:sel={selectedId === item.id}
                   role="button" tabindex="0"
                   onclick={(e) => { if (!e.target.closest('.job-act')) selectItem(item.id); }}
                   onkeydown={(e) => { if (e.key === 'Enter' && !e.target.closest('.job-act')) selectItem(item.id); }}>
            <div class="job-thumb">
              {#if item.video_id}
                <img src={api.rssThumbUrl(item.video_id)} alt="" loading="lazy" onerror={(e) => e.target.style.visibility='hidden'} />
              {/if}
              <i class="fa-solid fa-play thumb-ph"></i>
            </div>
            <div class="job-body">
              <div class="job-top">
                <span class="job-title">{item.title || item.video_id}</span>
                <span class="job-status">
                  <span class="job-prio-slot">
                    {#if item.status === 'queued' || item.status === 'retry_wait'}
                      <button class="prio" class:high={item.priority >= 5} class:now={item.priority >= 10}
                              onclick={(e) => cyclePriority(item.id, item.priority || 0, e)}
                              title="Klick: Priorität wechseln (Normal → Hoch → Sofort → Normal)">
                        {PRIORITY_LABELS[item.priority] || `Prio ${item.priority}`}
                      </button>
                    {:else if item.priority > 0}
                      <span class="prio" class:high={item.priority >= 5} title="Priorität">Prio {item.priority}</span>
                    {/if}
                  </span>
                  <span class="job-chip-slot">
                    {#if item.status === 'active'}<span class="chip active"><i class="fa-solid fa-download"></i> Lädt</span>
                    {:else if item.status === 'queued'}<span class="chip queued"><i class="fa-solid fa-clock"></i> Wartet</span>
                    {:else if item.status === 'retry_wait'}<span class="chip wait"><i class="fa-solid fa-hourglass-half"></i> Retry</span>
                    {:else if item.status === 'error'}<span class="chip error"><i class="fa-solid fa-triangle-exclamation"></i> Fehler</span>
                    {:else if item.status === 'parked'}<span class="chip offline"><i class="fa-solid fa-box-archive"></i> Geparkt</span>
                    {:else if item.status === 'cancelled'}<span class="chip canc"><i class="fa-solid fa-ban"></i> Abgebrochen</span>
                    {:else if item.status === 'done'}<span class="chip done"><i class="fa-solid fa-check"></i> Fertig</span>{/if}
                  </span>
                </span>
              </div>

              {#if item.status === 'active' && progress > 0}
                <DownloadProgress data={{ progress, stage, stage_label: label, phases: live?.phases || null, phaseFills: phaseFills[item.id] || null }} />
              {:else if item.status === 'done'}
                <DownloadProgress data={{ progress: 1.0, stage: 'done', stage_label: 'Abgeschlossen', phases: (live?.phases || []).map(p => ({ ...p, status: 'done' })) }} />
              {:else if item.status === 'error'}
                <DownloadProgress data={{ progress: progress || 0, stage: 'error', stage_label: item.error_message || 'Fehler', phases: live?.phases || null }} />
              {:else if item.status === 'active'}
                <span class="stage-txt">{label || stage}</span>
              {/if}

              {#if (item.status === 'error' || item.status === 'retry_wait' || item.status === 'parked') && item.error_message}
                <div class="err-msg"><i class="fa-solid fa-triangle-exclamation"></i> <span>{item.error_message}</span></div>
              {/if}
            </div>

            <div class="job-act">
              <button class="qb pri" class:off={!canRetry} disabled={!canRetry} onclick={() => retryItem(item.id)} title="Neu in Queue"><i class="fa-solid fa-rotate-right"></i></button>
              <button class="qb" class:off={!canDelay} disabled={!canDelay} onclick={() => retryDelayed(item.id, 5)} title="In 5 Min erneut"><i class="fa-solid fa-clock"></i> 5m</button>
              <button class="qb" class:off={!canDelay} disabled={!canDelay} onclick={() => retryDelayed(item.id, 30)} title="In 30 Min erneut"><i class="fa-solid fa-clock"></i> 30m</button>
              <button class="qb" class:off={!canRetry} disabled={!canRetry} onclick={() => ignoreVideoPermanent(item)} title="Dauerhaft ausschließen"><i class="fa-solid fa-ban"></i></button>
              <button class="qb danger" class:off={!canCancel} disabled={!canCancel} onclick={() => cancelItem(item.id)} title="Abbrechen"><i class="fa-solid fa-xmark"></i></button>
            </div>
          </article>
        {/each}

        {#each filteredJobs as job (job.id)}
          {@const meta = job.metadata || {}}
          <article class="job s-scan"
                   class:s-active={job.status === 'active'}
                   class:s-done={job.status === 'done'}
                   class:s-error={job.status === 'error'}
                   class:s-cancelled={job.status === 'cancelled'}>
            <div class="job-thumb job-thumb-sys"><i class="fa-solid {JOB_TYPE_ICONS[job.type] || 'fa-circle'}"></i></div>
            <div class="job-body">
              <div class="job-top">
                <span class="job-type">{JOB_TYPE_LABELS[job.type] || job.type}</span>
                <span class="job-title">{job.title || ''}</span>
                <span class="job-status">
                  <span class="job-prio-slot">
                    {#if job.priority > 0}<span class="prio" class:high={job.priority >= 5} title="Priorität">Prio {job.priority}</span>{/if}
                  </span>
                  <span class="job-chip-slot">
                    {#if job.status === 'active'}<span class="chip scan"><i class="fa-solid fa-gear fa-spin"></i> Läuft</span>
                    {:else if job.status === 'done'}<span class="chip done"><i class="fa-solid fa-check"></i> Fertig</span>
                    {:else if job.status === 'error'}<span class="chip error"><i class="fa-solid fa-triangle-exclamation"></i> Fehler</span>
                    {:else if job.status === 'queued'}<span class="chip queued"><i class="fa-solid fa-clock"></i> Wartet</span>{/if}
                  </span>
                </span>
              </div>

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
                <div class="bar scan"><i style="width:{pct.toFixed(1)}%"></i></div>
                <div class="prog-meta">
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
                      {#if precountExceeded}<span class="scan-exceeded"> – +{precountExtra} weitere gefunden</span>
                      {:else if showEst} / ~{estTotal} erwartet{/if}
                      {#if batchSaved > 0}<span class="scan-saved"> · {batchSaved} gesichert</span>{/if}
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
              {:else if job.status === 'active' && job.progress > 0}
                <div class="bar scan"><i style="width:{(job.progress * 100).toFixed(1)}%"></i></div>
                <div class="prog-meta"><span>{job.description || ''}</span><span class="num">{(job.progress * 100).toFixed(0)}%</span></div>
              {:else if job.description && job.status !== 'queued'}
                <div class="stage-txt">{job.description}</div>
              {/if}

              {#if job.completed_at}<div class="job-meta">{formatDateRelative(job.completed_at)}</div>{/if}
            </div>

            <div class="job-act">
              <button class="qb off" disabled><i class="fa-solid fa-rotate-right"></i></button>
              <button class="qb off" disabled><i class="fa-solid fa-clock"></i> 5m</button>
              <button class="qb off" disabled><i class="fa-solid fa-clock"></i> 30m</button>
              <button class="qb off" disabled><i class="fa-solid fa-ban"></i></button>
              <button class="qb danger" class:off={!(job.status === 'active' || job.status === 'queued')} disabled={!(job.status === 'active' || job.status === 'queued')} onclick={() => cancelSystemJob(job.id)} title="Abbrechen"><i class="fa-solid fa-xmark"></i></button>
            </div>
          </article>
        {/each}

        {#if filteredQueue.length === 0 && filteredJobs.length === 0}
          <div class="jobs-empty"><i class="fa-solid fa-inbox"></i> Keine Einträge in diesem Filter.</div>
        {/if}
      </div>
    </main>

    <!-- Seite: Detail (bei Auswahl) + Neuer Download + Einstellungen -->
    <aside class="daside">
      {#if selected}
        {@const dl = getLive(selected.id)}
        {@const dstage = dl?.stage || selected.status}
        {@const dprog = dl?.progress ?? selected.progress ?? 0}
        {@const canRetry = selected.status === 'retry_wait' || selected.status === 'error' || selected.status === 'cancelled' || selected.status === 'parked'}
        {@const canDelay = selected.status === 'error' || selected.status === 'cancelled' || selected.status === 'parked'}
        {@const canCancel = selected.status === 'queued' || selected.status === 'active' || selected.status === 'retry_wait'}
        <section class="panel detail-panel">
          <div class="panel-h">
            <h2>Details</h2>
            <div class="panel-spacer"></div>
            <button class="diconbtn" onclick={() => selectedId = null} title="Schließen (Esc)"><i class="fa-solid fa-xmark"></i></button>
          </div>
          <div class="detail-body">
            <div class="detail-thumb">
              {#if selected.video_id}
                <img src={api.rssThumbUrl(selected.video_id)} alt="" onerror={(e) => e.target.style.visibility='hidden'} />
              {/if}
              <i class="fa-solid fa-play thumb-ph"></i>
            </div>
            <h3 class="detail-title">{selected.title || selected.video_id}</h3>
            <div class="detail-rows">
              <div class="drow"><span class="dk">Status</span><span class="dv">
                {#if selected.status === 'active'}<span class="chip active"><i class="fa-solid fa-download"></i> Lädt</span>
                {:else if selected.status === 'queued'}<span class="chip queued"><i class="fa-solid fa-clock"></i> Wartet</span>
                {:else if selected.status === 'retry_wait'}<span class="chip wait"><i class="fa-solid fa-hourglass-half"></i> Retry</span>
                {:else if selected.status === 'error'}<span class="chip error"><i class="fa-solid fa-triangle-exclamation"></i> Fehler</span>
                {:else if selected.status === 'parked'}<span class="chip offline"><i class="fa-solid fa-box-archive"></i> Geparkt</span>
                {:else if selected.status === 'cancelled'}<span class="chip canc"><i class="fa-solid fa-ban"></i> Abgebrochen</span>
                {:else if selected.status === 'done'}<span class="chip done"><i class="fa-solid fa-check"></i> Fertig</span>{/if}
              </span></div>
              {#if selected.video_id}<div class="drow"><span class="dk">Video-ID</span><span class="dv mono">{selected.video_id}</span></div>{/if}
              {#if selected.priority > 0}<div class="drow"><span class="dk">Priorität</span><span class="dv">{PRIORITY_LABELS[selected.priority] || `Prio ${selected.priority}`}</span></div>{/if}
              {#if dstage}<div class="drow"><span class="dk">Phase</span><span class="dv">{dl?.stage_label || dstage}</span></div>{/if}
            </div>

            {#if selected.status === 'active' && dprog > 0}
              <DownloadProgress data={{ progress: dprog, stage: dstage, stage_label: dl?.stage_label || '', phases: dl?.phases || null, phaseFills: phaseFills[selected.id] || null }} />
            {:else if selected.status === 'done'}
              <DownloadProgress data={{ progress: 1.0, stage: 'done', stage_label: 'Abgeschlossen', phases: (dl?.phases || []).map(p => ({ ...p, status: 'done' })) }} />
            {/if}

            {#if selected.error_message}
              <div class="err-msg"><i class="fa-solid fa-triangle-exclamation"></i> <span>{selected.error_message}</span></div>
            {/if}

            <div class="detail-actions">
              {#if canCancel}<button class="dbtn danger" onclick={() => cancelItem(selected.id)}><i class="fa-solid fa-xmark"></i> Abbrechen</button>{/if}
              {#if canRetry}<button class="dbtn primary" onclick={() => retryItem(selected.id)}><i class="fa-solid fa-rotate-right"></i> Neu in Queue</button>{/if}
              {#if canDelay}<button class="dbtn" onclick={() => retryDelayed(selected.id, 5)}><i class="fa-solid fa-clock"></i> 5m</button>
              <button class="dbtn" onclick={() => retryDelayed(selected.id, 30)}><i class="fa-solid fa-clock"></i> 30m</button>{/if}
              {#if canRetry}<button class="dbtn" onclick={() => ignoreVideoPermanent(selected)}><i class="fa-solid fa-ban"></i> Ausschließen</button>{/if}
            </div>
          </div>
        </section>
      {/if}

      <section class="panel">
        <div class="panel-h"><h2>Neuer Download</h2></div>
        <div class="add">
          <div class="add-field">
            <i class="fa-solid fa-magnifying-glass"></i>
            <input type="text" placeholder="YouTube-URL einfügen…" bind:value={urlInput}
                   onkeydown={(e) => e.key === 'Enter' && resolveVideo()} />
          </div>
          <div class="add-row">
            <button class="dbtn" onclick={resolveVideo} disabled={resolving || !urlInput.trim()}>
              {#if resolving}<i class="fa-solid fa-spinner fa-spin"></i> Wird aufgelöst…{:else}<i class="fa-solid fa-magnifying-glass"></i> Auflösen{/if}
            </button>
            <button class="dbtn primary add-quick" onclick={quickDownload} disabled={!urlInput.trim()}>
              <i class="fa-solid fa-bolt"></i> Schnell laden
            </button>
          </div>
          <div class="seg">
            <span class="seg-lbl">Priorität</span>
            {#each [[0, 'Normal'], [5, 'Hoch'], [10, 'Sofort']] as [val, plabel]}
              <button class:on={selectedPriority === val} onclick={() => selectedPriority = val}>{plabel}</button>
            {/each}
          </div>
          <button class="link" onclick={() => showBatch = !showBatch}>
            <i class="fa-solid fa-list"></i> {showBatch ? 'Mehrfach-Eingabe schließen' : 'Mehrere Adressen auf einmal'}
          </button>
          {#if showBatch}
            <div class="batch-area">
              <textarea class="textarea" bind:value={batchInput} rows="4" placeholder="Eine URL pro Zeile…"></textarea>
              <button class="dbtn primary" onclick={addBatch} disabled={!batchInput.trim()}>
                {batchInput.split('\n').filter(l=>l.trim()).length} Downloads starten
              </button>
            </div>
          {/if}
        </div>
      </section>

      <section class="panel">
        <div class="panel-h"><h2>Einstellungen</h2><span class="panel-sub">live</span></div>
        <div class="ctrls">
          <div class="ctrl">
            <div class="ctrl-top"><i class="fa-solid fa-gauge-high"></i><span class="ctrl-title">Drosselung</span></div>
            <div class="ctrl-hint">
              {#if throttleRealtime}
                {#if currentThrottleLive > 0}aktiv: {currentThrottleLive.toLocaleString('de-DE')} KB/s (aus Video-Länge){:else}wartet auf Download…{/if}
              {:else if throttleKbps > 0}{throttleKbps} KB/s{:else}aus{/if}
            </div>
            <div class="ctrl-row">
              <label class="chk">
                <input type="checkbox" checked={throttleRealtime} onchange={toggleRealtime} disabled={settingsSaving} />
                <span class="sw"></span>Dynamisch
              </label>
              <div class="num-field" class:ro={throttleRealtime}>
                <input type="number" min="0" max="100000" step="100"
                       value={throttleRealtime ? (currentThrottleLive || '') : throttleKbps}
                       placeholder={throttleRealtime ? '—' : '0'}
                       disabled={settingsSaving || throttleRealtime}
                       oninput={(e) => { throttleKbps = parseInt(e.target.value) || 0; }}
                       onblur={() => !throttleRealtime && saveThrottle()}
                       onkeydown={(e) => e.key === 'Enter' && !throttleRealtime && saveThrottle()} />
                <span class="u">KB/s</span>
              </div>
            </div>
          </div>

          <div class="ctrl">
            <div class="ctrl-top"><i class="fa-solid fa-hourglass-half"></i><span class="ctrl-title">Wartezeit</span></div>
            <div class="ctrl-hint">{cooldownSec}s zwischen Downloads (min. 30 empfohlen)</div>
            <div class="ctrl-row">
              <div class="num-field">
                <input type="number" min="0" max="3600" step="5" bind:value={cooldownSec} disabled={settingsSaving}
                       onblur={() => saveCooldown(cooldownSec)} onkeydown={(e) => e.key === 'Enter' && saveCooldown(cooldownSec)} />
                <span class="u">s</span>
              </div>
              <button class="dbtn sm ghost" onclick={resetDefaults} title="Drosselung aus, Wartezeit 30 s"><i class="fa-solid fa-rotate-left"></i> Default</button>
            </div>
          </div>
        </div>
      </section>
    </aside>
  </div>
</div>

<ConfirmDialog bind:this={confirmRef} />

<style>
  .page { padding: 20px 24px 72px; max-width: none; }

  /* Command-Bar */
  .dtop { display:flex; align-items:center; gap:16px; flex-wrap:wrap; padding-bottom:16px; margin-bottom:18px; border-bottom:1px solid var(--border-primary); }
  .dbrand { display:flex; align-items:center; gap:12px; }
  .dbrand-mark { width:38px; height:38px; border-radius:11px; display:grid; place-items:center; background:linear-gradient(140deg, var(--accent-primary), #8b5cf6); color:#fff; font-size:17px; }
  .dtitle { margin:0; font-size:20px; font-weight:700; letter-spacing:-0.01em; color:var(--text-primary); }
  .dtsub { margin:1px 0 0; font-size:12px; color:var(--text-tertiary); }
  .dtop-right { margin-left:auto; display:flex; align-items:center; gap:10px; }
  .wchip { display:inline-flex; align-items:center; gap:8px; padding:7px 12px; border-radius:999px; font-size:12px; font-weight:600; }
  .wchip.ok { background:var(--status-success-bg); color:var(--status-success); }
  .wchip.dead { background:var(--status-error-bg); color:var(--status-error); }
  .wdot { width:7px; height:7px; border-radius:50%; background:currentColor; box-shadow:0 0 0 3px color-mix(in srgb, currentColor 22%, transparent); }
  .diconbtn { width:34px; height:34px; border-radius:9px; border:1px solid var(--border-primary); background:var(--bg-secondary); color:var(--text-secondary); cursor:pointer; display:grid; place-items:center; font-size:14px; transition:.15s; }
  .diconbtn:hover { color:var(--text-primary); border-color:var(--border-secondary); }
  .diconbtn:disabled { opacity:.5; }

  .dbanner { display:flex; align-items:center; gap:10px; padding:11px 14px; margin-bottom:16px; border-radius:10px; background:var(--status-error-bg); border:1px solid color-mix(in srgb, var(--status-error) 30%, transparent); font-size:0.86rem; color:var(--text-primary); }
  .dbanner > i { color:var(--status-error); font-size:1.1rem; }
  .dbanner > span { flex:1; }

  /* Stat-Kacheln */
  .dstats { display:flex; gap:10px; flex-wrap:wrap; margin-bottom:18px; }
  .dstat { display:flex; align-items:center; gap:10px; padding:10px 14px; min-width:112px; background:var(--bg-secondary); border:1px solid var(--border-primary); border-radius:12px; }
  .dstat .k { font-size:22px; font-weight:700; letter-spacing:-0.02em; line-height:1; display:block; }
  .dstat .l { font-size:11px; color:var(--text-tertiary); font-weight:600; text-transform:uppercase; letter-spacing:.04em; }
  .dstat.act .k { color:var(--accent-primary); }
  .dstat.done .k { color:var(--status-success); }
  .dstat.err .k { color:var(--status-error); }
  .dstat.wait .k { color:var(--text-secondary); }
  .dstat.canc .k { color:var(--text-tertiary); }
  .num { font-variant-numeric: tabular-nums; }

  /* Panels */
  .panel { background:var(--bg-secondary); border:1px solid var(--border-primary); border-radius:14px; }
  .panel-h { display:flex; align-items:center; gap:10px; padding:14px 16px; border-bottom:1px solid var(--border-primary); }
  .panel-h h2 { margin:0; font-size:14px; font-weight:700; color:var(--text-primary); }
  .panel-sub { font-size:12px; color:var(--text-tertiary); }
  .panel-spacer { margin-left:auto; }

  /* Buttons */
  .dbtn { display:inline-flex; align-items:center; gap:7px; padding:9px 14px; border-radius:10px; font-size:13px; font-weight:600; cursor:pointer; border:1px solid var(--border-primary); background:var(--bg-tertiary); color:var(--text-primary); white-space:nowrap; transition:.15s; }
  .dbtn:hover:not(:disabled) { border-color:var(--border-secondary); background:var(--bg-hover); }
  .dbtn:disabled { opacity:.5; cursor:default; }
  .dbtn.primary { background:var(--accent-primary); border-color:var(--accent-primary); color:#fff; }
  .dbtn.primary:hover:not(:disabled) { background:var(--accent-hover); }
  .dbtn.ghost { background:none; }
  .dbtn.sm { padding:6px 10px; font-size:12px; border-radius:8px; }
  .dbtn.lg { padding:11px 18px; font-size:14px; }
  .dbtn.danger { border-color:color-mix(in srgb, var(--status-error) 35%, transparent); color:var(--status-error); }
  .dbtn.danger:hover:not(:disabled) { background:var(--status-error-bg); border-color:var(--status-error); }
  .link { background:none; border:none; color:var(--accent-primary); font-size:12.5px; font-weight:600; cursor:pointer; padding:4px 2px; display:inline-flex; align-items:center; gap:6px; }
  .link:hover { text-decoration:underline; }
  .link.muted { color:var(--text-tertiary); } .link.danger { color:var(--status-error); }
  .link-retry { color:var(--status-info); }

  /* Grid */
  /* Goldener Schnitt: Warteschlange (Haupt) : Seitenpanel ≈ 1.618 : 1.
     Seitenpanel min 280px (Innenelemente brechen sonst); wird's insgesamt zu
     eng, klappt das Seitenpanel über die Warteschlange (order:-1). */
  .dgrid { display:grid; grid-template-columns: minmax(0,1.618fr) minmax(280px,1fr); gap:24px; align-items:start; margin-top:2px; }
  @media (max-width: 1024px) { .dgrid { grid-template-columns:1fr; } .daside { order:-1; } }
  /* Sehr schmal: Job-Aktionen klappen unter den Inhalt statt zu überlaufen */
  @media (max-width: 560px) {
    .job { grid-template-columns:72px minmax(0,1fr); padding-left:14px; }
    .job-act { grid-column:1 / -1; justify-content:flex-end; padding:0 12px 12px; }
    .job-thumb { width:72px; }
    /* eng: Slots auf Inhalt schrumpfen, damit nichts überläuft */
    .job-prio-slot, .job-chip-slot { width:auto; }
    .job-status { gap:6px; }
  }
  .daside { display:flex; flex-direction:column; gap:18px; }

  /* Add */
  .add { padding:16px; display:flex; flex-direction:column; gap:14px; }
  .add-field { display:flex; align-items:center; gap:9px; padding:0 12px; background:var(--bg-tertiary); border:1px solid var(--border-primary); border-radius:10px; transition:.15s; }
  .add-field:focus-within { border-color:var(--accent-primary); box-shadow:0 0 0 3px var(--accent-muted); }
  .add-field i { color:var(--text-tertiary); font-size:13px; }
  .add-field input { flex:1; background:none; border:none; outline:none; padding:11px 0; font-size:13.5px; color:var(--text-primary); }
  .add-row { display:flex; gap:8px; }
  .add-quick { flex:1; justify-content:center; }
  .seg { display:inline-flex; align-items:center; background:var(--bg-primary); border:1px solid var(--border-primary); border-radius:9px; padding:3px; gap:2px; align-self:flex-start; flex-wrap:wrap; }
  .seg-lbl { font-size:11px; color:var(--text-tertiary); font-weight:600; padding:0 8px; text-transform:uppercase; letter-spacing:.03em; }
  .seg button { border:none; background:none; color:var(--text-secondary); font-size:12.5px; font-weight:600; padding:6px 12px; border-radius:7px; cursor:pointer; transition:.12s; }
  .seg button.on { background:var(--accent-primary); color:#fff; }
  .batch-area { display:flex; flex-direction:column; gap:8px; }
  .textarea { width:100%; padding:9px 12px; background:var(--bg-tertiary); border:1px solid var(--border-primary); border-radius:8px; color:var(--text-primary); font-family:ui-monospace, monospace; font-size:0.82rem; outline:none; resize:vertical; box-sizing:border-box; }
  .textarea:focus { border-color:var(--accent-primary); }

  /* Einstellungen */
  .ctrls { display:flex; flex-direction:column; gap:12px; padding:16px; }
  .ctrl { background:var(--bg-primary); border:1px solid var(--border-primary); border-radius:12px; padding:14px 16px; }
  .ctrl-top { display:flex; align-items:center; gap:9px; margin-bottom:5px; }
  .ctrl-top i { color:var(--accent-primary); font-size:14px; }
  .ctrl-title { font-size:13px; font-weight:700; color:var(--text-primary); }
  .ctrl-hint { font-size:11.5px; color:var(--text-tertiary); margin-bottom:13px; min-height:15px; line-height:1.4; }
  .ctrl-row { display:flex; align-items:center; gap:12px; flex-wrap:wrap; row-gap:10px; }
  .ctrl-row .chk { margin-right:auto; flex:none; }
  .ctrl-row .num-field { flex:none; }
  .ctrl-row .dbtn { flex:none; }
  .chk { display:inline-flex; align-items:center; gap:7px; font-size:12.5px; color:var(--text-secondary); cursor:pointer; user-select:none; }
  .chk input { display:none; }
  .sw { width:34px; height:19px; border-radius:999px; background:var(--border-secondary); position:relative; transition:.18s; flex:none; }
  .sw::after { content:""; position:absolute; top:2px; left:2px; width:15px; height:15px; border-radius:50%; background:#fff; transition:.18s; }
  .chk input:checked + .sw { background:var(--accent-primary); }
  .chk input:checked + .sw::after { transform:translateX(15px); }
  .num-field { display:inline-flex; align-items:center; background:var(--bg-tertiary); border:1px solid var(--border-primary); border-radius:9px; overflow:hidden; }
  .num-field input { width:62px; border:none; background:none; outline:none; padding:8px 10px; font-size:13px; text-align:right; color:var(--text-primary); font-variant-numeric:tabular-nums; }
  .num-field input::-webkit-outer-spin-button, .num-field input::-webkit-inner-spin-button { -webkit-appearance:none; margin:0; }
  .num-field .u { padding:0 10px 0 2px; font-size:11.5px; color:var(--text-tertiary); }
  .num-field.ro { opacity:.55; }

  /* Resolved */
  .resolved-panel { padding:18px; margin-bottom:18px; border-color:color-mix(in srgb, var(--accent-primary) 40%, var(--border-primary)); }
  .resolved-header { display:flex; gap:14px; align-items:flex-start; }
  .resolved-thumb { width:180px; border-radius:10px; aspect-ratio:16/9; object-fit:cover; background:var(--bg-tertiary); flex:none; }
  .resolved-info { flex:1; min-width:0; }
  .resolved-info h3 { margin:0 0 5px; font-size:1rem; color:var(--text-primary); line-height:1.3; }
  .resolved-meta { font-size:0.82rem; color:var(--text-secondary); }
  .already-badge { background:var(--status-warning-bg); color:var(--status-warning); padding:2px 8px; border-radius:999px; font-size:0.7rem; font-weight:700; margin-left:8px; }
  .stream-section { margin-top:14px; }
  .stream-section h4 { margin:0 0 4px; font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:var(--text-tertiary); }
  .stream-group { margin-top:10px; }
  .stream-label { font-size:11.5px; color:var(--text-tertiary); display:block; margin-bottom:6px; }
  .opts { display:flex; flex-wrap:wrap; gap:7px; }
  .opt { display:flex; align-items:center; gap:8px; padding:8px 11px; border-radius:9px; border:1px solid var(--border-primary); background:var(--bg-tertiary); cursor:pointer; font-size:12.5px; transition:.12s; }
  .opt:hover { border-color:var(--border-secondary); }
  .opt.sel { border-color:var(--accent-primary); background:var(--accent-muted); }
  .opt .rd { width:14px; height:14px; border-radius:50%; border:2px solid var(--border-secondary); position:relative; flex:none; }
  .opt.sel .rd { border-color:var(--accent-primary); } .opt.sel .rd::after { content:""; position:absolute; inset:2px; border-radius:50%; background:var(--accent-primary); }
  .opt .q { font-weight:700; color:var(--text-primary); } .opt .sz { color:var(--text-secondary); } .opt .cd { color:var(--text-tertiary); font-size:11px; }
  .resolved-actions { display:flex; gap:10px; align-items:center; margin-top:16px; flex-wrap:wrap; }

  .pl-panel-header { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; margin-bottom:14px; flex-wrap:wrap; }
  .pl-panel-info { flex:1; min-width:0; }
  .pl-panel-info h3 { margin:4px 0; font-size:1rem; color:var(--text-primary); }
  .pl-panel-actions { display:flex; gap:8px; align-items:center; flex-shrink:0; }
  .pl-type-badge { display:inline-flex; align-items:center; gap:5px; font-size:0.7rem; font-weight:700; text-transform:uppercase; color:var(--accent-primary); letter-spacing:.04em; }
  .pl-video-list { max-height:420px; overflow-y:auto; border:1px solid var(--border-primary); border-radius:10px; scrollbar-width:thin; }
  .pl-video-row { display:flex; align-items:center; gap:10px; padding:7px 10px; border-bottom:1px solid var(--border-primary); }
  .pl-video-row:last-child { border-bottom:none; }
  .pl-video-row.downloaded { opacity:.55; }
  .pl-video-idx { width:22px; text-align:center; font-size:0.72rem; color:var(--text-tertiary); flex:none; font-variant-numeric:tabular-nums; }
  .pl-video-thumb { width:84px; height:47px; border-radius:6px; object-fit:cover; flex:none; background:var(--bg-tertiary); }
  .pl-video-thumb.placeholder { display:flex; align-items:center; justify-content:center; color:var(--text-tertiary); }
  .pl-video-info { flex:1; min-width:0; display:flex; flex-direction:column; gap:1px; }
  .pl-video-title { font-size:0.82rem; font-weight:500; color:var(--text-primary); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .pl-video-meta { font-size:0.7rem; color:var(--text-tertiary); }
  .pl-video-status { flex:none; width:34px; display:flex; align-items:center; justify-content:center; }
  .status-ok { color:var(--status-success); }
  .btn-icon-sm { width:30px; height:30px; border-radius:8px; border:1px solid var(--border-primary); background:var(--bg-tertiary); color:var(--text-secondary); cursor:pointer; display:flex; align-items:center; justify-content:center; font-size:0.75rem; }
  .btn-icon-sm:hover { border-color:var(--accent-primary); color:var(--accent-primary); }
  .ch-panel-header { margin-bottom:12px; }
  .ch-panel-header h3 { margin:4px 0 2px; font-size:1.1rem; color:var(--text-primary); }

  /* Queue-Tabs */
  .tabs { display:flex; gap:3px; padding:10px 12px; border-bottom:1px solid var(--border-primary); flex-wrap:wrap; }
  .tab { display:inline-flex; align-items:center; gap:7px; padding:7px 13px; border-radius:999px; border:1px solid transparent; background:none; color:var(--text-secondary); font-size:12.5px; font-weight:600; cursor:pointer; transition:.12s; }
  .tab:hover { background:var(--bg-hover); color:var(--text-primary); }
  .tab.on { background:var(--accent-muted); color:var(--accent-primary); border-color:color-mix(in srgb, var(--accent-primary) 35%, transparent); }
  .tab .c { font-size:11px; padding:0 6px; border-radius:999px; background:var(--bg-primary); color:var(--text-secondary); font-weight:700; min-width:18px; text-align:center; }
  .tab.on .c { background:var(--accent-primary); color:#fff; }
  .q-actions { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }

  /* Job-Karten */
  .jobs { display:flex; flex-direction:column; }
  .job { display:grid; grid-template-columns:88px minmax(0,1fr) 250px; gap:0 16px; align-items:stretch; padding-left:18px; border-bottom:1px solid var(--border-primary); position:relative; }
  .job:last-child { border-bottom:none; }
  .job:hover { background:color-mix(in srgb, var(--accent-primary) 3%, transparent); }
  .job.s-done { opacity:.8; }
  .job.s-cancelled { opacity:.7; }

  .job-thumb { align-self:center; margin:14px 0; position:relative; width:88px; aspect-ratio:16/9; border-radius:8px; overflow:hidden; background:linear-gradient(135deg,#2a2440,#1c2740); display:grid; place-items:center; }
  .job-thumb img { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }
  .job-thumb .thumb-ph { color:#ffffff55; font-size:16px; }
  .job-thumb-sys { background:#14b8a61e; color:#2dd4bf; font-size:18px; }
  .job-thumb-sys i { position:relative; }

  .job-body { padding:15px 4px 15px 0; min-width:0; display:flex; flex-direction:column; gap:10px; }
  .job-top { display:flex; align-items:center; gap:12px; flex-wrap:nowrap; }
  .job-title { flex:1; min-width:0; font-size:13.5px; font-weight:650; color:var(--text-primary); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  /* Status/Labels an fester Position rechts (feste Slot-Breiten) → tabellarisch,
     unabhaengig von der Titellaenge. */
  .job-status { flex:none; display:flex; align-items:center; justify-content:flex-end; gap:10px; margin-left:auto; }
  .job-prio-slot { width:58px; display:flex; justify-content:flex-end; flex:none; }
  .job-chip-slot { width:116px; display:flex; justify-content:flex-start; flex:none; }
  .job-type { font-size:10.5px; font-weight:700; text-transform:uppercase; letter-spacing:.04em; color:#2dd4bf; background:#14b8a61e; padding:2px 8px; border-radius:6px; }
  .job-meta { font-size:11.5px; color:var(--text-tertiary); }

  .chip { display:inline-flex; align-items:center; gap:5px; font-size:11px; font-weight:700; padding:2px 9px; border-radius:999px; white-space:nowrap; }
  .chip i { font-size:10px; }
  .chip.active { background:var(--accent-muted); color:var(--accent-primary); }
  .chip.queued { background:var(--bg-primary); color:var(--text-secondary); }
  .chip.wait { background:var(--status-warning-bg); color:var(--status-warning); }
  .chip.error { background:var(--status-error-bg); color:var(--status-error); }
  .chip.offline { background:var(--status-info-bg); color:var(--status-info); }
  .chip.done { background:var(--status-success-bg); color:var(--status-success); }
  .chip.canc { background:var(--bg-primary); color:var(--text-tertiary); }
  .chip.scan { background:#14b8a61e; color:#2dd4bf; }

  .prio { font-size:10.5px; font-weight:700; padding:2px 8px; border-radius:6px; background:var(--bg-primary); color:var(--text-tertiary); cursor:pointer; border:1px solid var(--border-primary); white-space:nowrap; }
  .prio.high { color:var(--status-warning); border-color:color-mix(in srgb, var(--status-warning) 30%, transparent); }
  .prio.now { color:#fff; background:var(--accent-primary); border-color:var(--accent-primary); }

  .stage-txt { font-size:12px; color:var(--text-secondary); }
  .err-msg { font-size:12px; color:var(--status-error); background:var(--status-error-bg); border-radius:8px; padding:7px 10px; display:flex; align-items:flex-start; gap:8px; line-height:1.4; word-break:break-word; }
  .err-msg i { margin-top:2px; flex:none; }

  .bar { height:6px; border-radius:4px; background:var(--bg-primary); overflow:hidden; }
  .bar i { display:block; height:100%; border-radius:4px; background:var(--accent-primary); transition:width .5s ease; }
  .bar.scan i { background:linear-gradient(90deg,#14b8a6,#2dd4bf); }
  .prog-meta { display:flex; align-items:center; justify-content:space-between; gap:10px; font-size:11.5px; color:var(--text-secondary); }
  .job-phase { font-size:10.5px; font-weight:700; text-transform:uppercase; color:#2dd4bf; letter-spacing:.03em; }
  .scan-exceeded { color:var(--text-tertiary); font-style:italic; }
  .scan-saved { color:var(--status-success); opacity:.75; }
  .scan-eta { color:var(--text-tertiary); font-weight:400; text-transform:none; }

  /* Feste Aktions-Spalte (Platz fürs größte Button-Set reserviert) → rechte Kante
     bleibt zeilenübergreifend konsistent, egal wie viele Buttons eine Zeile hat. */
  .job-act { display:flex; align-items:center; justify-content:flex-end; gap:6px; padding:13px 14px 13px 0; align-self:center; }
  .qb { height:32px; min-width:32px; padding:0 9px; border-radius:8px; border:1px solid var(--border-primary); background:var(--bg-secondary); color:var(--text-secondary); cursor:pointer; display:inline-flex; align-items:center; gap:5px; font-size:12px; font-weight:600; transition:.12s; }
  .qb:hover { color:var(--text-primary); border-color:var(--border-secondary); background:var(--bg-hover); }
  /* Reservierte, nicht-anwendbare Aktionen: blass & inaktiv – halten die Reihenfolge/Spalten */
  .qb.off, .qb:disabled { opacity:.26; pointer-events:none; }

  /* Klickbare Zeile + Auswahl-Highlight (Detail-Panel) */
  .job-clickable { cursor:pointer; }
  .job.sel { background:var(--accent-muted); }
  .job.sel:hover { background:var(--accent-muted); }

  /* Detail-Panel (rechts, bei Klick auf eine Download-Zeile) */
  .detail-panel { border-color:color-mix(in srgb, var(--accent-primary) 45%, var(--border-primary)); }
  .detail-body { padding:16px; display:flex; flex-direction:column; gap:14px; }
  .detail-thumb { position:relative; width:100%; aspect-ratio:16/9; border-radius:10px; overflow:hidden; background:linear-gradient(135deg,#2a2440,#1c2740); display:grid; place-items:center; }
  .detail-thumb img { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }
  .detail-thumb .thumb-ph { color:#ffffff55; font-size:30px; position:relative; }
  .detail-title { margin:0; font-size:15px; font-weight:650; line-height:1.35; color:var(--text-primary); }
  .detail-rows { display:flex; flex-direction:column; gap:9px; }
  .drow { display:flex; align-items:center; gap:12px; font-size:12.5px; }
  .dk { width:80px; flex:none; color:var(--text-tertiary); font-weight:600; text-transform:uppercase; letter-spacing:.03em; font-size:11px; }
  .dv { color:var(--text-secondary); min-width:0; overflow:hidden; text-overflow:ellipsis; }
  .detail-actions { display:flex; flex-wrap:wrap; gap:8px; }
  .qb.pri:hover { border-color:var(--accent-primary); color:var(--accent-primary); }
  .qb.danger:hover { border-color:var(--status-error); color:var(--status-error); }

  .jobs-empty { text-align:center; color:var(--text-tertiary); font-size:0.85rem; padding:40px 16px; display:flex; flex-direction:column; align-items:center; gap:8px; }
  .jobs-empty i { font-size:1.6rem; opacity:.5; }
</style>

<!--
  TubeVault – Downloads (Gestaltung nach mockups/downloads.html)
  Fester Kopf mit Kennzahlen, Eingabe für neue Downloads und Reitern;
  darunter zwei Spalten, die jede für sich rollen: links die Warteschlange,
  rechts Gefundenes, gewählter Auftrag und Einstellungen zum Laden.
  © HalloWelt42 – Private Nutzung
-->
<script>
  import { api, createActivitySocket } from '../lib/api/client.js';
  import { toast } from '../lib/stores/notifications.js';
  import { pendingDownloadUrl } from '../lib/stores/app.js';
  import ConfirmDialog from '../lib/components/common/ConfirmDialog.svelte';
  import DownloadRow from '../lib/components/downloads/DownloadRow.svelte';
  import SystemJobRow from '../lib/components/downloads/SystemJobRow.svelte';
  import DownloadDetail from '../lib/components/downloads/DownloadDetail.svelte';
  import ResolvedResult from '../lib/components/downloads/ResolvedResult.svelte';
  import DownloadSettings from '../lib/components/downloads/DownloadSettings.svelte';
  import { TABS, GROUPS, matchesTab, nextPriority, PRIORITY_LABELS } from '../lib/components/downloads/jobStatus.js';

  let confirmRef;

  // ─── Warteschlange und Systemaufträge ───
  let queue = $state({ queue: [], queued_count: 0, active_count: 0 });
  let systemJobs = $state([]);
  let jobsTab = $state('all');
  let selectedId = $state(null);
  let workerDead = $state(false);
  let restartingWorker = $state(false);

  async function loadQueue() {
    try {
      queue = await api.getQueue();
      // Wartet etwas, läuft aber nichts: ist die Verarbeitung noch da?
      if (queue.queued_count > 0 && queue.active_count === 0) {
        try { workerDead = !(await api.workerHealth()).alive; } catch { workerDead = false; }
      } else {
        workerDead = false;
      }
    } catch {}
  }

  async function loadSystemJobs() {
    try {
      const all = await api.getJobs({ limit: 50 });
      systemJobs = (Array.isArray(all) ? all : []).filter(j => j.type !== 'download');
    } catch {}
  }

  async function restartWorker() {
    restartingWorker = true;
    try {
      await api.restartWorker();
      toast.success('Verarbeitung neu gestartet');
      workerDead = false;
      setTimeout(loadQueue, 2000);
    } catch (e) { toast.error('Neustart fehlgeschlagen: ' + e.message); }
    restartingWorker = false;
  }

  // ─── Live-Stand aus dem Aktivitätskanal ───
  let liveStatus = $state({});
  let phaseFills = $state({});     // je Auftrag: Füllstand jeder Phase (Video und Ton füllen sich getrennt)
  let currentThrottleLive = $state(0);
  // Reihenfolge der Schritte: ältere Meldungen dürfen einen Auftrag nicht zurückwerfen
  const STAGE_RANK = { resolving: 0, resolved: 1, downloading_video: 2, downloading_audio: 3, merging: 4, finalizing: 5, done: 6 };

  function handleWsMessage(msg) {
    if (msg.type === 'cooldown' && typeof msg.current_throttle_kbps === 'number') {
      currentThrottleLive = msg.current_throttle_kbps;
    }
    const id = msg.job_id || msg.queue_id;
    if (id) {
      const prev = liveStatus[id];
      if (prev && prev.status === 'active' && msg.status === 'active') {
        const pr = STAGE_RANK[prev.stage] ?? -1;
        const nr = STAGE_RANK[msg.stage] ?? -1;
        if (nr < pr) return;
        if (nr === pr && (msg.progress ?? 0) < (prev.progress ?? 0) - 0.02) return;
      }
      liveStatus = { ...liveStatus, [id]: msg };

      if (msg.status && msg.status !== 'active') {
        if (phaseFills[id]) { const { [id]: _, ...rest } = phaseFills; phaseFills = rest; }
      } else {
        const next = { ...(phaseFills[id] || {}) };
        let changed = false;
        if (typeof msg.stage === 'string' && msg.stage.startsWith('downloading_') && (msg.bytes_total || 0) > 0) {
          const frac = Math.max(0, Math.min(1, (msg.bytes_done || 0) / msg.bytes_total));
          if (frac > (next[msg.stage] ?? 0)) { next[msg.stage] = frac; changed = true; }
        }
        for (const p of msg.phases || []) {
          if (p.status === 'done' && next[p.id] !== 1) { next[p.id] = 1; changed = true; }
        }
        if (changed) phaseFills = { ...phaseFills, [id]: next };
      }
    }
    const terminal = ['done', 'error', 'cancelled', 'parked'];
    if (terminal.includes(msg.status) || terminal.includes(msg.stage)) setTimeout(loadQueue, 500);
  }

  $effect(() => {
    loadQueue();
    loadSystemJobs();
    const iv = setInterval(loadQueue, 5000);
    const jiv = setInterval(loadSystemJobs, 5000);
    const socket = createActivitySocket(handleWsMessage);
    return () => { clearInterval(iv); clearInterval(jiv); socket?.close(); };
  });

  // ─── Neuer Download ───
  let urlInput = $state('');
  let batchInput = $state('');
  let showBatch = $state(false);
  let resolving = $state(false);
  let videoInfo = $state(null);
  let playlistInfo = $state(null);
  let channelInfo = $state(null);
  let selectedQuality = $state('');     // leer = Kanal bzw. Standard-Qualität
  let selectedPriority = $state(0);
  let plDownloading = $state(new Set());

  function clearResolved() { videoInfo = null; playlistInfo = null; channelInfo = null; }

  async function resolveVideo() {
    if (!urlInput.trim()) return;
    resolving = true;
    clearResolved();
    try {
      const result = await api.resolveUrl(urlInput.trim());
      if (result.type === 'video') videoInfo = result.data;
      else if (result.type === 'playlist') playlistInfo = result.data;
      else if (result.type === 'channel') channelInfo = result.data;
    } catch (e) { toast.error(e.message); }
    finally { resolving = false; }
  }

  // Playlists und Kanäle werden erst geprüft; ein einzelnes Video lädt sofort
  const isPlaylistOrChannel = (url) =>
    /[?&]list=/.test(url) || /\/playlist\?/.test(url) || /\/@[a-zA-Z0-9_.-]+/.test(url) || /\/channel\//.test(url) || /\/c\//.test(url);

  async function addOne(url, quality) {
    await api.addDownload({ url, quality: quality || undefined, priority: selectedPriority });
  }

  async function quickDownload() {
    const url = urlInput.trim();
    if (!url) return;
    if (isPlaylistOrChannel(url)) return resolveVideo();
    try {
      await addOne(url);
      toast.success('Download gestartet');
      urlInput = '';
      clearResolved();
      loadQueue();
    } catch (e) { toast.error(e.message); }
  }

  async function startResolved() {
    try {
      await addOne(urlInput.trim(), selectedQuality);
      toast.success('Download gestartet');
      urlInput = '';
      clearResolved();
      loadQueue();
    } catch (e) { toast.error(e.message); }
  }

  async function plDownloadOne(videoId) {
    plDownloading = new Set([...plDownloading, videoId]);
    try {
      await addOne(`https://www.youtube.com/watch?v=${videoId}`);
      toast.success('Download gestartet');
      loadQueue();
    } catch (e) { toast.error(e.message); }
    plDownloading = new Set([...plDownloading].filter(id => id !== videoId));
  }

  async function plDownloadAll() {
    const missing = playlistInfo.videos.filter(v => !v.already_downloaded);
    let ok = 0;
    for (const v of missing) {
      try { await addOne(`https://www.youtube.com/watch?v=${v.id}`); ok++; } catch {}
    }
    toast.success(`${ok} von ${missing.length} Downloads gestartet`);
    loadQueue();
  }

  async function subscribeChannel() {
    try {
      await api.addSubscription({ channel_id: channelInfo.channel_id });
      channelInfo = { ...channelInfo, already_subscribed: true };
      toast.success(`${channelInfo.channel_name} abonniert`);
    } catch (e) { toast.error(e.message); }
  }

  async function addBatch() {
    const urls = batchInput.split('\n').map(l => l.trim()).filter(Boolean);
    if (!urls.length) return;
    try {
      const result = await api.addBatchDownload({ urls });
      toast.success(`${result.results?.filter(r => r.status !== 'error').length || 0} Downloads gestartet`);
      batchInput = '';
      showBatch = false;
      loadQueue();
    } catch (e) { toast.error(e.message); }
  }

  // Adresse aus der Suche übernehmen und gleich prüfen
  $effect(() => {
    const pending = $pendingDownloadUrl;
    if (pending) {
      urlInput = pending;
      $pendingDownloadUrl = null;
      setTimeout(resolveVideo, 50);
    }
  });

  // ─── Aktionen an Aufträgen ───
  const reloadAfter = (fn) => async (...args) => {
    try { await fn(...args); } catch (e) { toast.error(e.message); }
    loadQueue();
  };
  const cancelItem = reloadAfter((id) => api.cancelDownload(id));
  const retryItem = reloadAfter((id) => api.retryDownload(id));
  const retryDelayed = reloadAfter(async (id, minutes) => {
    await api.retryWithDelay(id, minutes);
    toast.success(`Neuer Versuch in ${minutes} Minuten`);
  });
  const setPriority = reloadAfter(async (item) => {
    const next = nextPriority(item.priority);
    await api.setDownloadPriority(item.id, next);
    toast.success(`Priorität: ${PRIORITY_LABELS[next]}`);
  });
  const retryAllFailed = reloadAfter(async () => toast.success(`${(await api.retryAllFailed()).retried} Downloads erneut eingereiht`));
  const clearDone = reloadAfter(async () => { await api.clearCompleted(); toast.success('Fertige entfernt'); });
  const fixStale = reloadAfter(async () => toast.success(`${(await api.fixStaleDownloads()).fixed} hängende Downloads gelöst`));
  const clearAll = reloadAfter(async () => toast.success(`${(await api.clearAllDownloads()).cleared} Einträge entfernt`));

  async function ignoreVideoPermanent(item) {
    const name = item.title || item.video_id;
    if (!await confirmRef.ask(`"${name.slice(0, 50)}" dauerhaft ausschließen?`, 'Das Video wird beim Kanal als nicht ladbar vermerkt und taucht nicht wieder auf.', { confirmLabel: 'Ausschließen' })) return;
    try {
      await api.ignoreVideo(item.video_id || item.id, item.channel_id || null, item.error_message || 'Von Hand ausgeschlossen');
      await api.cancelDownload(item.id);
      toast.success(`"${name}" ausgeschlossen`);
    } catch (e) { toast.error(e.message); }
    loadQueue();
  }

  async function cancelSystemJob(id) {
    try { await api.cancelJob(id); } catch {}
    setTimeout(loadSystemJobs, 500);
  }

  // ─── Anzeige ───
  let filteredQueue = $derived(queue.queue.filter(q => matchesTab(q, jobsTab)));
  let filteredJobs = $derived(systemJobs.filter(j => matchesTab(j, jobsTab)));
  // Im Reiter "Alle" nach Zustand gruppiert, in fester Reihenfolge
  let groups = $derived(jobsTab !== 'all' ? null : GROUPS
    .map(tab => ({ tab, items: queue.queue.filter(q => matchesTab(q, tab)) }))
    .filter(g => g.items.length));
  let counts = $derived(Object.fromEntries(TABS.map(t =>
    [t.id, queue.queue.filter(q => matchesTab(q, t.id)).length + systemJobs.filter(j => matchesTab(j, t.id)).length])));
  const GROUP_LABELS = { active: 'Läuft', wait: 'Wartet', error: 'Fehler', cancelled: 'Abgebrochen', done: 'Fertig' };

  let selected = $derived(selectedId != null ? queue.queue.find(q => q.id === selectedId) || null : null);
  function selectItem(id) { selectedId = selectedId === id ? null : id; }
  // Esc oder Klick neben Liste und Karte schließt die Auswahl
  $effect(() => {
    if (selectedId == null) return;
    const onKey = (e) => { if (e.key === 'Escape') selectedId = null; };
    const onClick = (e) => { if (!e.target.closest?.('.auftrag, .detail-panel')) selectedId = null; };
    document.addEventListener('keydown', onKey);
    document.addEventListener('click', onClick);
    return () => { document.removeEventListener('keydown', onKey); document.removeEventListener('click', onClick); };
  });
</script>

{#snippet row(item)}
  <DownloadRow {item} live={liveStatus[item.id] || null} phaseFill={phaseFills[item.id] || null}
               selected={selectedId === item.id}
               onSelect={() => selectItem(item.id)}
               onRetry={() => retryItem(item.id)}
               onDelay={(m) => retryDelayed(item.id, m)}
               onIgnore={() => ignoreVideoPermanent(item)}
               onCancel={() => cancelItem(item.id)}
               onPriority={() => setPriority(item)} />
{/snippet}

<div class="tv-seite">
  <div class="tv-seitenkopf">
    <div class="kopfzeile">
      <h1>Downloads</h1>
      <div class="rechts">
        {#if workerDead}
          <span class="tv-zustand fehler"><i class="fa-solid fa-circle-stop"></i> Verarbeitung steht</span>
        {:else}
          <span class="tv-zustand laeuft"><i class="fa-solid fa-circle-play"></i> Verarbeitung läuft</span>
        {/if}
        <button class="tv-knopf" class:haupt={workerDead} onclick={restartWorker} disabled={restartingWorker} title="Verarbeitung der Downloads neu starten">
          <i class="fa-solid fa-rotate" class:fa-spin={restartingWorker}></i> Neu starten
        </button>
      </div>
    </div>

    <div class="tv-kennzahlen">
      <div class="tv-kennzahl laeuft"><b>{counts.active}</b><span>Läuft</span></div>
      <div class="tv-kennzahl"><b>{counts.wait}</b><span>Wartet</span></div>
      <div class="tv-kennzahl"><b>{counts.done}</b><span>Fertig</span></div>
      {#if counts.error}<div class="tv-kennzahl fehler"><b>{counts.error}</b><span>Fehler</span></div>{/if}
      {#if counts.cancelled}<div class="tv-kennzahl"><b>{counts.cancelled}</b><span>Abgebrochen</span></div>{/if}
    </div>

    <div class="neu">
      {#if showBatch}
        <textarea class="tv-eingabe mehrere" bind:value={batchInput} rows="3" placeholder="Eine Adresse je Zeile"></textarea>
        <button class="tv-knopf haupt" onclick={addBatch} disabled={!batchInput.trim()}>
          <i class="fa-solid fa-download"></i> {batchInput.split('\n').filter(l => l.trim()).length} laden
        </button>
      {:else}
        <input class="tv-eingabe" bind:value={urlInput} placeholder="Adresse eines Videos, einer Playlist oder eines Kanals einfügen"
               onkeydown={(e) => e.key === 'Enter' && resolveVideo()} />
        <select class="tv-eingabe prioritaet" bind:value={selectedPriority} title="Priorität für neue Downloads">
          {#each Object.entries(PRIORITY_LABELS) as [value, label]}<option value={Number(value)}>{label}</option>{/each}
        </select>
        <button class="tv-knopf" onclick={resolveVideo} disabled={resolving || !urlInput.trim()}>
          <i class="fa-solid {resolving ? 'fa-spinner fa-spin' : 'fa-magnifying-glass'}"></i> Prüfen
        </button>
        <button class="tv-knopf haupt" onclick={quickDownload} disabled={!urlInput.trim()}><i class="fa-solid fa-download"></i> Laden</button>
      {/if}
      <button class="tv-knopf ohne" onclick={() => showBatch = !showBatch} title="Mehrere Adressen auf einmal">
        <i class="fa-solid {showBatch ? 'fa-xmark' : 'fa-list'}"></i> {showBatch ? 'Eine Adresse' : 'Mehrere'}
      </button>
    </div>

    <div class="reiterleiste">
      <div class="tv-reiter">
        {#each TABS as tab}
          <button class:aktiv={jobsTab === tab.id} onclick={() => jobsTab = tab.id}>
            <i class="fa-solid {tab.icon}"></i> {tab.label}{#if counts[tab.id]}<span class="tv-zaehler">{counts[tab.id]}</span>{/if}
          </button>
        {/each}
      </div>
      <div class="aktionen">
        {#if counts.error > 0}<button class="tv-knopf ohne klein" onclick={retryAllFailed}><i class="fa-solid fa-rotate-right"></i> Alle erneut</button>{/if}
        <button class="tv-knopf ohne klein" onclick={fixStale} title="Hängende Downloads zurück in die Warteschlange">Hängende lösen</button>
        <button class="tv-knopf ohne klein" onclick={clearDone}>Fertige entfernen</button>
        <button class="tv-knopf ohne klein gefahr" onclick={clearAll}>Alle entfernen</button>
      </div>
    </div>
  </div>

  <div class="tv-spalten">
    <div class="tv-rollfeld" data-scroll-root>
      {#if groups}
        {#each groups as group}
          <div class="tv-etikett gruppe">{GROUP_LABELS[group.tab]} <span class="zahl">{group.items.length}</span></div>
          {#each group.items as item (item.id)}{@render row(item)}{/each}
        {/each}
      {:else}
        {#each filteredQueue as item (item.id)}{@render row(item)}{/each}
      {/if}

      {#if filteredJobs.length}
        <div class="tv-etikett gruppe">Systemaufträge <span class="zahl">{filteredJobs.length}</span></div>
        {#each filteredJobs as job (job.id)}<SystemJobRow {job} onCancel={cancelSystemJob} />{/each}
      {/if}

      {#if filteredQueue.length === 0 && filteredJobs.length === 0}
        <div class="tv-leer"><i class="fa-solid fa-inbox"></i> Nichts in diesem Reiter.</div>
      {/if}
    </div>

    <div class="tv-rollfeld">
      {#if videoInfo || playlistInfo || channelInfo}
        <ResolvedResult video={videoInfo} playlist={playlistInfo} channel={channelInfo}
                        bind:quality={selectedQuality} loadingIds={plDownloading}
                        onStart={startResolved} onPlaylistOne={plDownloadOne} onPlaylistAll={plDownloadAll}
                        onSubscribe={subscribeChannel} onClose={clearResolved} />
      {/if}
      {#if selected}
        <DownloadDetail item={selected} live={liveStatus[selected.id] || null} phaseFill={phaseFills[selected.id] || null}
                        onClose={() => selectedId = null}
                        onRetry={() => retryItem(selected.id)}
                        onDelay={(m) => retryDelayed(selected.id, m)}
                        onIgnore={() => ignoreVideoPermanent(selected)}
                        onCancel={() => cancelItem(selected.id)} />
      {/if}
      <DownloadSettings {currentThrottleLive} />
    </div>
  </div>
</div>

<ConfirmDialog bind:this={confirmRef} />

<style>
  .kopfzeile { display: flex; align-items: center; gap: var(--tv-a4); margin-bottom: var(--tv-a4); }
  .kopfzeile h1 { margin: 0; font-size: var(--tv-gr-seite); }
  .kopfzeile .rechts { margin-left: auto; display: flex; gap: var(--tv-a2); align-items: center; }
  .neu { display: flex; gap: var(--tv-a2); margin-top: var(--tv-a4); align-items: flex-start; }
  .neu .tv-eingabe { flex: 1; }
  .neu .prioritaet { flex: none; width: 120px; }
  .neu .mehrere { height: auto; padding: var(--tv-a2) var(--tv-a3); resize: vertical; font-family: inherit; }
  .reiterleiste { display: flex; align-items: center; gap: var(--tv-a2); margin-top: var(--tv-a4); flex-wrap: wrap; }
  .reiterleiste .aktionen { margin-left: auto; display: flex; gap: var(--tv-a1); flex-wrap: wrap; }
  .gruppe { display: block; margin: var(--tv-a4) 0 var(--tv-a2); }
  .gruppe:first-child { margin-top: 0; }
</style>

<script>
  /**
   * TubeVault – Feed v1.5.54
   * Feed-Tabs (Aktiv/Spaeter/Archiv/Ausgeblendet), Schnellaktionen, Infinite Scroll
   * © HalloWelt42 – Private Nutzung
   */
  import { api } from '../lib/api/client.js';
  import { toast } from '../lib/stores/notifications.js';
  import { route, navigate, updateParams } from '../lib/router/router.js';
  import { feedVersion } from '../lib/stores/app.js';
  import { formatDateRelative, formatStreamSize } from '../lib/utils/format.js';
  import { getFilter, saveFilters } from '../lib/stores/filterPersist.js';
  import { getSettingNum } from '../lib/stores/settings.js';
  import { startQueue } from '../lib/stores/playlistQueue.js';
  import { onMount, onDestroy } from 'svelte';
  import MultiFilter from '../lib/components/common/MultiFilter.svelte';
  import StreamDialog from '../lib/components/common/StreamDialog.svelte';

  // Feed State
  let entries = $state([]);
  let loading = $state(false);
  let loadingMore = $state(false);
  let page = $state(1);
  let hasMore = $state(false);
  let total = $state(0);
  let typeCounts = $state({ video: 0, short: 0, live: 0 });
  let tabCounts = $state({ active: 0, later: 0, dismissed: 0, archived: 0 });
  let downloading = $state(new Set());

  // Feed-Tab State (persistent)
  let feedTab = $state(getFilter('feed', 'feedTab', 'active'));

  // Multi-Filter State
  let feedFilter = $state({ types: null, channels: null, keywords: null, durationMin: null, durationMax: null });

  // Batch-Auswahl
  let selectedIds = $state(new Set());
  let selectMode = $state(false);

  // Scheduler State
  let scheduler = $state(null);
  let schedulerInterval = null;

  // Stream-Auswahl Dialog
  let streamDialog = $state(null);

  const PER_PAGE = getSettingNum('general.videos_per_page', 24);

  // Sentinel-Element fuer IntersectionObserver
  let sentinelEl = $state(null);
  let observer = null;

  const FEED_TABS = [
    { id: 'active', label: 'Aktiv', icon: 'fa-solid fa-inbox' },
    { id: 'later', label: 'Spaeter', icon: 'fa-solid fa-bookmark' },
    { id: 'archived', label: 'Archiv', icon: 'fa-solid fa-box-archive' },
    { id: 'dismissed', label: 'Ausgeblendet', icon: 'fa-solid fa-eye-slash' },
  ];

  // Datum-Gruppierung (Heute/Gestern/Älter)
  function getDateGroup(published) {
    if (!published) return 'older';
    const now = new Date();
    const pub = new Date(published);
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterdayStart = new Date(todayStart);
    yesterdayStart.setDate(yesterdayStart.getDate() - 1);
    if (pub >= todayStart) return 'today';
    if (pub >= yesterdayStart) return 'yesterday';
    return 'older';
  }

  const DATE_GROUP_LABELS = {
    today: { label: 'Heute', icon: 'fa-solid fa-calendar-day', cls: 'today' },
    yesterday: { label: 'Gestern', icon: 'fa-solid fa-calendar-minus', cls: 'yesterday' },
    older: { label: 'Älter', icon: 'fa-solid fa-calendar', cls: 'older' },
  };

  // Gruppierte Entries (nur im aktiven Tab sinnvoll)
  let groupedEntries = $derived.by(() => {
    if (feedTab !== 'active' || entries.length === 0) return null;
    const groups = { today: [], yesterday: [], older: [] };
    for (const e of entries) {
      groups[getDateGroup(e.published)].push(e);
    }
    // Nur Gruppen mit Einträgen zurückgeben
    return Object.entries(groups)
      .filter(([, items]) => items.length > 0)
      .map(([key, items]) => ({ key, ...DATE_GROUP_LABELS[key], items }));
  });

  async function loadFeed(reset = true) {
    if (reset) {
      page = 1;
      entries = [];
      loading = true;
    } else {
      loadingMore = true;
    }
    try {
      const params = { feedTab, page, perPage: PER_PAGE };
      if (feedFilter.types) params.videoTypes = feedFilter.types;
      if (feedFilter.channels) params.channelIds = feedFilter.channels;
      if (feedFilter.keywords) params.keywords = feedFilter.keywords;
      if (feedFilter.durationMin != null) params.durationMin = feedFilter.durationMin;
      if (feedFilter.durationMax != null) params.durationMax = feedFilter.durationMax;
      const data = await api.getFeedVideos(params);
      if (reset) {
        entries = data.entries || [];
      } else {
        entries = [...entries, ...(data.entries || [])];
      }
      total = data.total || 0;
      hasMore = data.has_more || false;
      typeCounts = data.type_counts || { video: 0, short: 0, live: 0 };
      tabCounts = data.tab_counts || tabCounts;
    } catch (e) { toast.error(e.message); }
    finally { loading = false; loadingMore = false; }
  }

  async function loadMore() {
    if (loadingMore || !hasMore) return;
    page += 1;
    await loadFeed(false);
  }

  function switchTab(tab) {
    feedTab = tab;
    saveFilters('feed', { feedTab: tab });
    updateParams({ tab: tab !== 'active' ? tab : null });
    loadFeed(true);
  }

  function onFeedFilterChange(f) {
    feedFilter = f;
    updateParams({ types: f.types || null, channels: f.channels || null });
    loadFeed(true);
  }

  // ─── Schnellaktionen ─────────────────────────────────
  async function setStatus(entry, status) {
    try {
      await api.setFeedEntryStatus(entry.id, status);
      entries = entries.filter(e => e.id !== entry.id);
      total = Math.max(0, total - 1);
      // Tab-Counts lokal updaten
      const fromTab = feedTab;
      if (tabCounts[fromTab] > 0) tabCounts[fromTab]--;
      tabCounts[status] = (tabCounts[status] || 0) + 1;
      tabCounts = { ...tabCounts };
      const labels = { later: 'Spaeter', archived: 'Archiv', dismissed: 'Ausgeblendet', active: 'Aktiv' };
      toast.success(`${labels[status]}: ${(entry.title || '').slice(0, 40)}`);
    } catch (e) { toast.error(e.message); }
  }

  async function restoreEntry(entry) {
    await setStatus(entry, 'active');
  }

  // Typ-Badge klicken: video → short → live → video
  async function cycleType(entry) {
    const current = entry.video_type_safe || entry.video_type || 'video';
    const order = ['video', 'short', 'live'];
    const next = order[(order.indexOf(current) + 1) % order.length];
    try {
      await api.setFeedEntryType(entry.id, next);
      entry.video_type = next;
      entry.video_type_safe = next;
      entries = [...entries]; // Reaktivitaet triggern
      const labels = { video: 'Video', short: 'Short', live: 'Live' };
      toast.success(`Typ: ${labels[next]}`);
    } catch (e) { toast.error(e.message); }
  }

  $effect(() => {
    if (sentinelEl) {
      observer?.disconnect();
      const currentHasMore = hasMore;
      const currentLoadingMore = loadingMore;
      const currentLoading = loading;
      observer = new IntersectionObserver((es) => {
        if (es[0].isIntersecting && hasMore && !loadingMore && !loading) {
          loadMore();
        }
      }, { rootMargin: '200px' });
      observer.observe(sentinelEl);
    }
  });

  // Scheduler-Status alle 5s aktualisieren
  async function loadScheduler() {
    try { scheduler = await api.getSchedulerStatus(); } catch {}
  }

  function timeAgo(isoStr) {
    if (!isoStr) return '';
    const diff = (Date.now() - new Date(isoStr).getTime()) / 1000;
    if (diff < 60) return 'gerade eben';
    if (diff < 3600) return `vor ${Math.floor(diff / 60)} Min`;
    if (diff < 86400) return `vor ${Math.floor(diff / 3600)} Std`;
    return `vor ${Math.floor(diff / 86400)} Tagen`;
  }

  let pollTriggering = $state(false);
  async function triggerPollNow() {
    if (pollTriggering) return;
    pollTriggering = true;
    try {
      const result = await api.triggerRSSPoll();
      toast.success(`RSS-Check: ${result.feed_count || 0} Feeds werden geprüft`);
      // Nach 3s Status neu laden
      setTimeout(loadScheduler, 3000);
    } catch (e) {
      toast.error(`RSS-Trigger: ${e.message}`);
    } finally {
      pollTriggering = false;
    }
  }

  let unsubFeed = null;

  onMount(() => {
    // URL-Params lesen
    const p = $route?.params || {};
    if (p.tab && ['active','later','archived','dismissed'].includes(p.tab)) feedTab = p.tab;
    if (p.types) feedFilter = { ...feedFilter, types: p.types };
    if (p.channels) feedFilter = { ...feedFilter, channels: p.channels };
    loadFeed(true);
    loadScheduler();
    schedulerInterval = setInterval(loadScheduler, 5000);

    // Auto-Reload wenn Backend neue Videos meldet (via WebSocket → feedVersion Store)
    unsubFeed = feedVersion.subscribe(v => {
      if (v > 0) loadFeed(true);
    });
  });

  onDestroy(() => {
    if (schedulerInterval) clearInterval(schedulerInterval);
    if (unsubFeed) unsubFeed();
    observer?.disconnect();
  });

  // ─── Stream-Dialog ──────────────────────────────────
  async function openStreamDialog(entry) {
    streamDialog = { entry, streams: [], captions: [], loading: true, selectedVideoItag: null, selectedAudioItag: null, mergeAudio: true };
    try {
      const info = await api.getVideoInfo(`https://www.youtube.com/watch?v=${entry.video_id}`);
      // Streams sortieren: Video absteigend nach Auflösung, Audio separat
      const videoStreams = (info.streams || [])
        .filter(s => s.type === 'video')
        .sort((a, b) => {
          const ra = parseInt(a.quality) || 0;
          const rb = parseInt(b.quality) || 0;
          return rb - ra;
        });
      const audioStreams = (info.streams || [])
        .filter(s => s.type === 'audio')
        .sort((a, b) => {
          const ra = parseInt(a.quality) || 0;
          const rb = parseInt(b.quality) || 0;
          return rb - ra;
        });
      streamDialog = {
        ...streamDialog,
        streams: info.streams || [],
        videoStreams, audioStreams,
        captions: info.captions || [],
        title: info.title,
        loading: false,
        mergeAudio: true,
        alreadyDownloaded: info.already_downloaded,
        selectedVideoItag: entry.audio_only ? null : (videoStreams[0]?.itag || null),
        selectedAudioItag: entry.audio_only
          ? (audioStreams[0]?.itag || null)
          : (videoStreams[0]?.is_progressive ? null : (audioStreams[0]?.itag || null)),
      };
    } catch (e) {
      toast.error(`Stream-Info Fehler: ${e.message}`);
      streamDialog = null;
    }
  }

  async function startDownload(entry, { itag = null, audioItag = null, mergeAudio = true, audioOnly = false, priority = 0 } = {}) {
    // Kanal-Einstellung: audio_only überschreibt immer
    const isAudioOnly = audioOnly || !!entry.audio_only;
    downloading.add(entry.video_id);
    downloading = new Set(downloading);
    try {
      await api.addDownload({
        url: `https://www.youtube.com/watch?v=${entry.video_id}`,
        quality: isAudioOnly ? 'audio_only' : (entry.download_quality || 'best'),
        itag: isAudioOnly ? null : itag,
        audio_itag: audioItag,
        merge_audio: isAudioOnly ? false : mergeAudio,
        audio_only: isAudioOnly,
        priority,
      });
      const label = priority >= 10 ? 'Sofort-Download' : 'In Queue gelegt';
      toast.success(`${label}: ${entry.title || entry.video_id}`);
      streamDialog = null;
      // Eintrag nicht sofort entfernen – bleibt bis Benutzer dismissed
    } catch (e) { toast.error(e.message); }
    finally {
      downloading.delete(entry.video_id);
      downloading = new Set(downloading);
    }
  }

  async function quickDownload(entry) {
    await startDownload(entry, { audioOnly: !!entry.audio_only, priority: 0 });
  }

  function openVideo(entry) {
    // Queue aus sichtbaren Feed-Einträgen bauen → Skip/Autoplay im MiniPlayer
    const queueVideos = entries.map(e => ({
      id: e.video_id,
      title: e.title || e.video_id,
      channel_name: e.channel_name || '',
      duration: e.duration || 0,
    }));
    const idx = queueVideos.findIndex(v => v.id === entry.video_id);
    if (queueVideos.length > 1) {
      startQueue(null, 'Feed', queueVideos, idx >= 0 ? idx : 0);
    }
    navigate(`/watch/${entry.video_id}`);
  }

  function openChannel(entry) {
    navigate(`/channel/${entry.channel_id}`);
  }

  async function dismissEntry(entry) {
    await setStatus(entry, 'dismissed');
  }

  async function dismissAll() {
    await api.dismissAllFeed();
    entries = [];
    total = 0;
    tabCounts.active = 0;
    tabCounts = { ...tabCounts };
    toast.info('Alle als gelesen markiert');
  }

  async function restoreAll() {
    await api.moveAllFeedStatus(feedTab, 'active');
    entries = [];
    total = 0;
    const count = tabCounts[feedTab] || 0;
    tabCounts[feedTab] = 0;
    tabCounts.active = (tabCounts.active || 0) + count;
    tabCounts = { ...tabCounts };
    toast.info('Alle wiederhergestellt');
  }

  // ─── Batch-Auswahl ────────────────────────────────────
  function toggleSelect(id) {
    if (selectedIds.has(id)) { selectedIds.delete(id); }
    else { selectedIds.add(id); }
    selectedIds = new Set(selectedIds);
  }

  function selectAll() {
    entries.forEach(e => selectedIds.add(e.id));
    selectedIds = new Set(selectedIds);
  }

  function deselectAll() {
    selectedIds = new Set();
  }

  function toggleSelectMode() {
    selectMode = !selectMode;
    if (!selectMode) selectedIds = new Set();
  }

  let selectedCount = $derived(selectedIds.size);

  async function bulkSetType(newType) {
    if (selectedIds.size === 0) return;
    const ids = [...selectedIds];
    try {
      await api.setFeedBulkType(ids, newType);
      // Lokal updaten
      for (const entry of entries) {
        if (selectedIds.has(entry.id)) {
          entry.video_type = newType;
          entry.video_type_safe = newType;
        }
      }
      entries = [...entries];
      const labels = { video: 'Video', short: 'Short', live: 'Live' };
      toast.success(`${ids.length}× als ${labels[newType]} markiert`);
      selectedIds = new Set();
    } catch (e) { toast.error(e.message); }
  }

  let totalAll = $derived(typeCounts.video + typeCounts.short + typeCounts.live);
</script>

<div class="page">
  <!-- Scheduler-Status -->
  {#if scheduler}
    <div class="scheduler-bar">
      <span class="sched-icon"><i class="fa-solid fa-satellite-dish"></i></span>
      <span class="sched-label">RSS</span>
      {#if scheduler.rss_enabled}
        {#if scheduler.last_cron_job?.status === 'active'}
          <span class="sched-info sched-active"><i class="fa-solid fa-spinner fa-spin"></i> {scheduler.last_cron_job.description}</span>
        {:else if scheduler.feeds_pending > 0}
          <span class="sched-info">{scheduler.feeds_pending} Feeds fällig</span>
        {:else}
          <span class="sched-info sched-idle"><i class="fa-solid fa-circle-check"></i> Alle aktuell</span>
        {/if}
        {#if scheduler.last_checked_channel}
          <span class="sched-detail">Zuletzt: {scheduler.last_checked_channel}
            {#if scheduler.last_checked_at}
              <span class="sched-time">({timeAgo(scheduler.last_checked_at)})</span>
            {/if}
          </span>
        {/if}
        {#if scheduler.last_cron_job?.status === 'done' && scheduler.last_cron_job.result}
          <span class="sched-result" title={scheduler.last_cron_job.result}>
            <i class="fa-solid fa-check"></i> {scheduler.last_cron_job.result}
          </span>
        {/if}
      {:else}
        <span class="sched-info sched-off"><i class="fa-solid fa-pause"></i> RSS deaktiviert</span>
      {/if}
      <span class="sched-count">{scheduler.feeds_checked_total || 0} geprüft</span>
      <button class="sched-trigger" title="RSS-Feeds jetzt prüfen" onclick={triggerPollNow}>
        <i class="fa-solid fa-rotate"></i>
      </button>
    </div>
  {/if}

  <div class="page-header">
    <div>
      <h1 class="title">Feed</h1>
      <span class="subtitle">{total} {feedTab === 'active' ? 'neue' : feedTab === 'later' ? 'gemerkte' : feedTab === 'dismissed' ? 'ausgeblendete' : feedTab === 'archived' ? 'archivierte' : ''} Videos</span>
    </div>
    <div class="actions">
      <button class="btn-ghost" onclick={() => navigate('/subscriptions')}><i class="fa-solid fa-tv"></i> Kanäle</button>
      <button class="btn-ghost" class:active={selectMode} onclick={toggleSelectMode} title="Auswahl-Modus">
        <i class="fa-solid fa-check-double"></i> {selectMode ? 'Auswahl beenden' : 'Auswählen'}
      </button>
      {#if feedTab === 'active'}
        <button class="btn-ghost" onclick={dismissAll} disabled={!entries.length}><i class="fa-solid fa-check-double"></i> Alle gelesen</button>
      {:else if feedTab !== 'active' && entries.length > 0}
        <button class="btn-ghost" onclick={restoreAll}><i class="fa-solid fa-rotate-left"></i> Alle wiederherstellen</button>
      {/if}
    </div>
  </div>

  <!-- Feed-Tabs -->
  <div class="feed-tabs">
    {#each FEED_TABS as tab}
      <button class="feed-tab" class:active={feedTab === tab.id} onclick={() => switchTab(tab.id)}>
        <i class={tab.icon}></i>
        <span>{tab.label}</span>
        {#if tabCounts[tab.id] > 0}
          <span class="tab-badge">{tabCounts[tab.id]}</span>
        {/if}
      </button>
    {/each}
  </div>

  <!-- Multi-Filter: Typ + Kanal -->
  <MultiFilter
    showTypes={true}
    showChannels={true}
    showCategories={false}
    showTags={true}
    showDuration={true}
    {feedTab}
    onchange={onFeedFilterChange}
  />

  <!-- Batch-Aktionsleiste -->
  {#if selectMode}
    <div class="batch-bar">
      <div class="batch-left">
        <button class="btn-sm" onclick={selectAll}><i class="fa-solid fa-check-double"></i> Alle ({entries.length})</button>
        {#if selectedCount > 0}
          <button class="btn-sm" onclick={deselectAll}><i class="fa-solid fa-xmark"></i> Keine</button>
        {/if}
        <span class="batch-count">{selectedCount} ausgewählt</span>
      </div>
      {#if selectedCount > 0}
        <div class="batch-actions">
          <span class="batch-label">Typ ändern:</span>
          <button class="batch-type badge-video" onclick={() => bulkSetType('video')}>
            <i class="fa-solid fa-play"></i> Video
          </button>
          <button class="batch-type badge-short" onclick={() => bulkSetType('short')}>
            <i class="fa-solid fa-bolt"></i> Short
          </button>
          <button class="batch-type badge-live" onclick={() => bulkSetType('live')}>
            <i class="fa-solid fa-tower-broadcast"></i> Live
          </button>
        </div>
      {/if}
    </div>
  {/if}

  {#if loading}
    <div class="loading-state">Feed wird geladen…</div>
  {:else if entries.length > 0}
    <div class="feed-grid">
      {#each entries as entry, idx (entry.id)}
        <!-- Datum-Gruppenheader (nur im aktiven Tab) -->
        {#if feedTab === 'active'}
          {@const grp = getDateGroup(entry.published)}
          {@const prevGrp = idx > 0 ? getDateGroup(entries[idx - 1].published) : null}
          {#if idx === 0 || grp !== prevGrp}
            {@const gInfo = DATE_GROUP_LABELS[grp]}
            <div class="feed-date-header {gInfo.cls}">
              <i class={gInfo.icon}></i>
              <span class="fdh-label">{gInfo.label}</span>
              <span class="fdh-count">
                {entries.filter(e => getDateGroup(e.published) === grp).length} Videos
              </span>
              <span class="fdh-line"></span>
            </div>
          {/if}
        {/if}
        <div class="video-card"
             class:queued={entry.status === 'queued'}
             class:downloaded={entry.video_status === 'ready'}
             class:is-short={entry.video_type_safe === 'short' || entry.video_type === 'short'}
             class:is-live={entry.video_type_safe === 'live' || entry.video_type === 'live'}
             class:is-selected={selectMode && selectedIds.has(entry.id)}>
          <div class="thumb-wrap" onclick={() => selectMode ? toggleSelect(entry.id) : openVideo(entry)} onkeydown={(e) => e.key === "Enter" && (selectMode ? toggleSelect(entry.id) : openVideo(entry))} role="button" tabindex="0" style="cursor:pointer">
            {#if selectMode}
              <div class="select-checkbox" class:checked={selectedIds.has(entry.id)}>
                {#if selectedIds.has(entry.id)}
                  <i class="fa-solid fa-check"></i>
                {/if}
              </div>
            {/if}
            {#if entry.video_id}
              <img class="thumb" src={api.rssThumbUrl(entry.video_id)} alt="" loading="lazy"
                onerror={(e) => { e.target.style.display='none'; if(e.target.nextElementSibling) e.target.nextElementSibling.style.display='flex'; }} />
              <div class="thumb-empty" style="display:none"><i class="fa-solid fa-play"></i></div>
            {:else}
              <div class="thumb-empty"><i class="fa-solid fa-play"></i></div>
            {/if}

            <!-- Typ-Badge -->
            {#if entry.audio_only}
              <span class="type-badge badge-audio" title="Audio-Only Kanal">Audio</span>
            {:else}
              <button class="type-badge badge-{entry.video_type_safe || entry.video_type || 'video'}"
                onclick={(e) => { e.stopPropagation(); cycleType(entry); }}
                title="Typ aendern">
                {(entry.video_type_safe || entry.video_type) === 'short' ? 'Short' : (entry.video_type_safe || entry.video_type) === 'live' ? 'Live' : 'Video'}
              </button>
            {/if}

            {#if entry.video_status === 'ready'}
              <span class="play-badge"><i class="fa-solid fa-play"></i> Abspielen</span>
            {/if}

            <!-- Overlay -->
            <div class="thumb-overlay">
              {#if entry.video_status === 'ready'}
                <button class="overlay-btn play-btn" onclick={(e) => { e.stopPropagation(); openVideo(entry); }} title="Abspielen">
                  <i class="fa-solid fa-play"></i>
                </button>
              {:else}
                <button class="overlay-btn dl-btn" onclick={(e) => { e.stopPropagation(); openStreamDialog(entry); }}
                  disabled={downloading.has(entry.video_id)} title={entry.audio_only ? 'Audio-Stream wählen' : 'Stream waehlen & laden'}>
                  <i class="fa-solid {entry.audio_only ? 'fa-podcast' : 'fa-download'}"></i>
                </button>
                <button class="overlay-btn queue-btn" onclick={(e) => { e.stopPropagation(); quickDownload(entry); }}
                  disabled={downloading.has(entry.video_id)} title={entry.audio_only ? 'Audio laden' : 'Schnell-Download'}>
                  <i class="fa-solid fa-bolt"></i>
                </button>
              {/if}
              <!-- Schnellaktionen je nach Tab -->
              {#if feedTab === 'active'}
                <button class="overlay-btn later-btn" onclick={(e) => { e.stopPropagation(); setStatus(entry, 'later'); }} title="Spaeter anschauen">
                  <i class="fa-solid fa-bookmark"></i>
                </button>
                <button class="overlay-btn archive-btn" onclick={(e) => { e.stopPropagation(); setStatus(entry, 'archived'); }} title="Archivieren">
                  <i class="fa-solid fa-box-archive"></i>
                </button>
                <button class="overlay-btn dismiss-btn" onclick={(e) => { e.stopPropagation(); dismissEntry(entry); }} title="Ausblenden">
                  <i class="fa-solid fa-xmark"></i>
                </button>
              {:else}
                <button class="overlay-btn restore-btn" onclick={(e) => { e.stopPropagation(); restoreEntry(entry); }} title="Wiederherstellen">
                  <i class="fa-solid fa-rotate-left"></i>
                </button>
              {/if}
            </div>
          </div>

          <div class="card-body">
            <button class="channel-avatar-small" onclick={() => openChannel(entry)}>
              <img src={api.channelAvatarUrl(entry.channel_id)} alt=""
                onerror={(e) => { e.target.style.display='none'; e.target.nextElementSibling.style.display='flex'; }} />
              <div class="avatar-mini-fb" style="display:none">
                {(entry.channel_name || '?')[0].toUpperCase()}
              </div>
            </button>
            <div class="card-text">
              <button class="card-title-btn" onclick={() => openVideo(entry)}>
                <h3 class="card-title">{entry.title || entry.video_id}</h3>
              </button>
              <div class="card-meta">
                <button class="channel-link" onclick={() => openChannel(entry)}>{entry.channel_name || entry.channel_id}</button>
                {#if entry.audio_only}
                  <span class="audio-only-badge" title="Audio-Only Kanal"><i class="fa-solid fa-podcast"></i></span>
                {/if}
                <span class="meta-dot">·</span>
                <span>{formatDateRelative(entry.published)}</span>
              </div>
            </div>
          </div>
        </div>
      {/each}
    </div>

    <!-- Sentinel für IntersectionObserver -->
    <div bind:this={sentinelEl} class="scroll-sentinel"></div>

    {#if loadingMore}
      <div class="loading-more">Lade weitere Videos…</div>
    {/if}

    {#if hasMore && !loadingMore}
      <div class="load-more-wrap">
        <button class="btn-load-more" onclick={loadMore}>
          Weitere Videos laden ({entries.length} von {total})
        </button>
      </div>
    {/if}

    {#if !hasMore && entries.length > 0}
      <div class="end-marker">Alle {total} Videos geladen</div>
    {/if}

  {:else}
    <div class="empty">
      {#if feedTab === 'active'}
        <i class="fa-solid fa-tv empty-icon"></i>
        <h3>Keine neuen Videos</h3>
        <p>Sobald deine abonnierten Kanaele neue Videos veroeffentlichen, erscheinen sie hier.</p>
        <button class="btn-ghost" onclick={() => navigate('/subscriptions')}>Abonnements verwalten</button>
      {:else if feedTab === 'later'}
        <i class="fa-solid fa-bookmark empty-icon"></i>
        <h3>Nichts fuer spaeter gemerkt</h3>
        <p>Markiere Videos mit <i class="fa-solid fa-bookmark"></i> um sie hier zu sammeln.</p>
      {:else if feedTab === 'archived'}
        <i class="fa-solid fa-box-archive empty-icon"></i>
        <h3>Kein Archiv</h3>
        <p>Archivierte Videos ohne Download landen hier.</p>
      {:else if feedTab === 'dismissed'}
        <i class="fa-solid fa-eye-slash empty-icon"></i>
        <h3>Nichts ausgeblendet</h3>
        <p>Ausgeblendete Videos koennen hier wiederhergestellt werden.</p>
      {/if}
    </div>
  {/if}
</div>

<!-- Stream-Auswahl Dialog -->
<StreamDialog
  dialog={streamDialog}
  showAudioOnly={true}
  forceAudioOnly={!!streamDialog?.entry?.audio_only}
  ondownload={({ itag, audioItag, mergeAudio, audioOnly, priority }) => {
    startDownload(streamDialog.entry, { itag, audioItag, mergeAudio, audioOnly, priority });
  }}
  onclose={() => streamDialog = null}
/>

<style>
  .page { padding: 24px; max-width: 1200px; }

  /* Scheduler Bar */
  .scheduler-bar {
    display: flex; align-items: center; gap: 10px; padding: 8px 16px;
    background: var(--bg-tertiary); border-radius: 10px; margin-bottom: 16px;
    font-size: 0.78rem; color: var(--text-secondary); flex-wrap: wrap;
  }
  .sched-icon { font-size: 1rem; }
  .sched-label { font-weight: 700; color: var(--text-primary); }
  .sched-info { color: var(--accent-primary); font-weight: 600; display: flex; align-items: center; gap: 4px; }
  .sched-active { color: var(--status-warning); }
  .sched-idle { color: var(--status-success); }
  .sched-off { color: var(--status-error); }
  .sched-detail { color: var(--text-tertiary); }
  .sched-time { font-size: 0.68rem; opacity: 0.7; }
  .sched-result { color: var(--status-success); font-size: 0.72rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 280px; }
  .sched-count { margin-left: auto; color: var(--text-tertiary); font-size: 0.72rem; }
  .sched-trigger {
    width: 28px; height: 28px; display: flex; align-items: center; justify-content: center;
    background: none; border: 1px solid var(--border-primary); border-radius: 6px;
    color: var(--text-tertiary); cursor: pointer; font-size: 0.78rem; flex-shrink: 0;
  }
  .sched-trigger:hover { border-color: var(--accent-primary); color: var(--accent-primary); }

  /* Header */
  .page-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; flex-wrap:wrap; gap:12px; }
  .title { font-size:1.5rem; font-weight:700; color:var(--text-primary); margin:0; }
  .subtitle { font-size:0.82rem; color:var(--text-tertiary); }
  .actions { display:flex; gap:8px; flex-wrap:wrap; }

  /* Feed-Tabs (Aktiv/Spaeter/Archiv/Ausgeblendet) */
  .feed-tabs {
    display: flex; gap: 4px; margin-bottom: 16px;
    border-bottom: 1px solid var(--border-primary); padding-bottom: 0;
  }
  .feed-tab {
    display: flex; align-items: center; gap: 6px;
    padding: 10px 16px; background: none; border: none;
    border-bottom: 2px solid transparent;
    color: var(--text-tertiary); font-size: 0.82rem; font-weight: 600;
    cursor: pointer; transition: all 0.15s;
  }
  .feed-tab:hover { color: var(--text-primary); }
  .feed-tab.active { color: var(--accent-primary); border-bottom-color: var(--accent-primary); }
  .feed-tab .tab-badge {
    font-size: 0.68rem; background: var(--bg-tertiary); padding: 1px 6px;
    border-radius: 8px; color: var(--text-secondary); font-weight: 700;
  }
  .feed-tab.active .tab-badge {
    background: var(--accent-primary); color: var(--bg-primary);
  }

  /* Typ-Tabs */
  .type-tabs {
    display: flex; gap: 4px; margin-bottom: 20px;
    border-bottom: 1px solid var(--border-primary); padding-bottom: 0;
  }
  .tab {
    padding: 8px 16px; background: none; border: none; border-bottom: 2px solid transparent;
    color: var(--text-tertiary); font-size: 0.85rem; font-weight: 600; cursor: pointer;
    transition: all 0.15s;
  }
  .tab:hover { color: var(--text-primary); }
  .tab.active { color: var(--accent-primary); border-bottom-color: var(--accent-primary); }
  .tab-count {
    font-size: 0.72rem; background: var(--bg-tertiary); padding: 1px 6px;
    border-radius: 8px; margin-left: 4px;
  }
  .tab.active .tab-count { background: var(--accent-muted); color: var(--accent-primary); }

  /* Grid */
  .feed-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(290px, 1fr)); gap:20px; }

  /* Datum-Gruppenheader */
  .feed-date-header {
    grid-column: 1 / -1;
    display: flex; align-items: center; gap: 8px;
    padding: 4px 2px; margin-top: 4px;
  }
  .feed-date-header:first-child { margin-top: 0; }
  .feed-date-header i { font-size: 0.72rem; }
  .fdh-label { font-size: 0.78rem; font-weight: 700; }
  .fdh-count { font-size: 0.68rem; color: var(--text-tertiary); }
  .fdh-line { flex: 1; height: 1px; background: var(--border-primary); }
  .feed-date-header.today { color: var(--status-success); }
  .feed-date-header.today .fdh-label { color: var(--status-success); }
  .feed-date-header.yesterday { color: var(--accent-primary); }
  .feed-date-header.yesterday .fdh-label { color: var(--accent-primary); }
  .feed-date-header.older { color: var(--text-tertiary); }
  .feed-date-header.older .fdh-label { color: var(--text-tertiary); }

  .video-card { display:flex; flex-direction:column; border-radius:12px; overflow:hidden; transition:transform 0.2s; }
  .video-card:hover { transform:translateY(-2px); }

  .thumb-wrap { position:relative; aspect-ratio:16/9; background:var(--bg-tertiary); border-radius:12px; overflow:hidden; }
  .thumb { width:100%; height:100%; object-fit:cover; display:block; }
  .thumb-empty { width:100%; height:100%; display:flex; align-items:center; justify-content:center; color:var(--text-tertiary); font-size:2rem; }

  .type-badge { position:absolute; top:8px; right:8px; font-size:0.62rem; font-weight:700; padding:2px 8px; border-radius:4px; text-transform:uppercase; cursor:pointer; border:none; transition:transform 0.15s, opacity 0.15s; z-index:2; }
  .type-badge:hover { transform:scale(1.1); opacity:0.9; }
  .badge-video { background:rgba(255,255,255,0.2); color:#fff; backdrop-filter:blur(4px); }
  .badge-short { background:#AB47BC; color:#fff; }
  .badge-live { background:#EF5350; color:#fff; }
  .badge-audio { background:#2196F3; color:#fff; cursor:default; }

  .thumb-overlay { position:absolute; inset:0; background:rgba(0,0,0,0.5); display:flex; align-items:center; justify-content:center; gap:10px; opacity:0; transition:opacity 0.2s; }
  .video-card:hover .thumb-overlay { opacity:1; }

  .overlay-btn { width:42px; height:42px; border-radius:50%; border:none; display:flex; align-items:center; justify-content:center; cursor:pointer; font-size:1.1rem; transition:transform 0.15s; }
  .overlay-btn:hover { transform:scale(1.1); }
  .overlay-btn:disabled { opacity:0.5; }
  .dl-btn { background:var(--accent-primary); color:#fff; }
  .queue-btn { background:rgba(255,255,255,0.2); color:#fff; }
  .queue-btn:hover { background:rgba(255,200,0,0.5); }
  .dismiss-btn { background:rgba(255,255,255,0.15); color:#fff; }
  .dismiss-btn:hover { background:rgba(255,80,80,0.6); }
  .later-btn { background:rgba(255,255,255,0.15); color:#fff; }
  .later-btn:hover { background:rgba(59,130,246,0.6); }
  .archive-btn { background:rgba(255,255,255,0.15); color:#fff; }
  .archive-btn:hover { background:rgba(245,158,11,0.6); }
  .restore-btn { background:rgba(255,255,255,0.15); color:#fff; }
  .restore-btn:hover { background:rgba(34,197,94,0.6); }
  .play-btn { background:var(--status-success); color:#fff; }
  .play-badge { position:absolute; bottom:8px; left:8px; background:rgba(0,0,0,0.8); color:var(--status-success); font-size:0.68rem; font-weight:700; padding:2px 8px; border-radius:4px; }


  .video-card.queued .thumb-wrap { border:2px solid var(--status-info); }
  .video-card.downloaded .thumb-wrap { border:2px solid var(--status-success); }

  /* Card Body */
  .card-body { display:flex; gap:12px; padding:10px 2px; }
  .channel-avatar-small { width:36px; height:36px; border-radius:50%; overflow:hidden; flex-shrink:0; margin-top:2px; cursor:pointer; border:none; background:none; padding:0; }
  .channel-avatar-small img { width:36px; height:36px; object-fit:cover; border-radius:50%; }
  .avatar-mini-fb { width:36px; height:36px; border-radius:50%; background:var(--accent-muted); color:var(--accent-primary); display:flex; align-items:center; justify-content:center; font-size:0.9rem; font-weight:700; }
  .card-text { flex:1; min-width:0; }
  .card-title { font-size:0.9rem; font-weight:600; color:var(--text-primary); margin:0; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; line-height:1.3; }
  .card-title-btn { background:none; border:none; padding:0; cursor:pointer; text-align:left; width:100%; }
  .card-title-btn:hover .card-title { color:var(--accent-primary); }
  .card-meta { display:flex; align-items:center; gap:5px; margin-top:4px; font-size:0.78rem; color:var(--text-tertiary); }
  .channel-link { background:none; border:none; padding:0; cursor:pointer; color:var(--text-secondary); font-size:0.78rem; }
  .channel-link:hover { color:var(--accent-primary); }
  .meta-dot { color:var(--text-tertiary); }
  .audio-only-badge { color: #63b3ed; font-size: 0.7rem; }

  /* Scroll / Load More */
  .scroll-sentinel { height:1px; }
  .loading-more { text-align:center; padding:20px; color:var(--text-tertiary); font-size:0.85rem; }
  .load-more-wrap { text-align:center; padding:24px; }
  .btn-load-more { padding:10px 28px; background:var(--bg-tertiary); border:1px solid var(--border-primary); border-radius:10px; color:var(--text-primary); font-size:0.88rem; font-weight:600; cursor:pointer; }
  .btn-load-more:hover { border-color:var(--accent-primary); background:var(--accent-muted); }
  .end-marker { text-align:center; padding:20px; color:var(--text-tertiary); font-size:0.8rem; }

  /* Empty / Loading */
  .loading-state { padding:60px; text-align:center; color:var(--text-tertiary); }
  .empty { display:flex; flex-direction:column; align-items:center; padding:60px 20px; text-align:center; color:var(--text-tertiary); }
  .empty-icon { font-size: 3.5rem; color: var(--text-tertiary); }
  .empty h3 { margin:16px 0 8px; color:var(--text-secondary); }
  .empty p { margin-bottom:16px; font-size:0.88rem; max-width:380px; }

  /* Batch-Auswahl */
  .btn-ghost.active { background:var(--accent-primary); color:#fff; border-color:var(--accent-primary); }
  .batch-bar {
    display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px;
    padding:10px 14px; background:var(--accent-muted); border:1px solid var(--accent-primary);
    border-radius:10px; margin-bottom:14px;
  }
  .batch-left { display:flex; align-items:center; gap:8px; }
  .btn-sm {
    padding:4px 10px; border:1px solid var(--border-primary); border-radius:6px;
    background:var(--bg-primary); color:var(--text-secondary); font-size:0.76rem; cursor:pointer;
  }
  .btn-sm:hover { border-color:var(--accent-primary); color:var(--text-primary); }
  .batch-count { font-size:0.8rem; font-weight:600; color:var(--accent-primary); }
  .batch-actions { display:flex; align-items:center; gap:6px; }
  .batch-label { font-size:0.72rem; color:var(--text-tertiary); font-weight:600; text-transform:uppercase; }
  .batch-type {
    display:flex; align-items:center; gap:4px; padding:5px 12px;
    border:none; border-radius:6px; font-size:0.78rem; font-weight:600; cursor:pointer;
    transition:all 0.12s;
  }
  .batch-type i { font-size:0.7rem; }
  .batch-type.badge-video { background:var(--accent-primary); color:#fff; }
  .batch-type.badge-short { background:#f59e0b; color:#fff; }
  .batch-type.badge-live { background:#ef4444; color:#fff; }
  .batch-type:hover { opacity:0.85; transform:scale(1.03); }

  .video-card.is-selected { outline:2px solid var(--accent-primary); outline-offset:-2px; border-radius:12px; }
  .select-checkbox {
    position:absolute; top:8px; left:8px; z-index:5;
    width:24px; height:24px; border-radius:6px;
    background:rgba(0,0,0,0.6); border:2px solid rgba(255,255,255,0.7);
    display:flex; align-items:center; justify-content:center;
    color:#fff; font-size:0.72rem; transition:all 0.12s;
  }
  .select-checkbox.checked { background:var(--accent-primary); border-color:var(--accent-primary); }
</style>

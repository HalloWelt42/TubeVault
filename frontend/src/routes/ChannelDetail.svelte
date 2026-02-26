<!--
  TubeVault -  Channel Detail v1.5.52
  © HalloWelt42 -  Private Nutzung

  Kanal-Übersicht mit Banner, Tabs (Videos/Shorts/Live),
  Sortierung, Debug-Panel, erweiterte Statistiken.
-->
<script>
  import { api } from '../lib/api/client.js';
  import { toast } from '../lib/stores/notifications.js';
  import { route, navigate } from '../lib/router/router.js';
  import { getFilter, saveFilters } from '../lib/stores/filterPersist.js';
  import { startQueue } from '../lib/stores/playlistQueue.js';
  import { formatDateRelative, formatDuration, formatDurationLong, formatSize, formatViews } from '../lib/utils/format.js';
  import QuickPlaylistBtn from '../lib/components/common/QuickPlaylistBtn.svelte';
  import Pagination from '../lib/components/common/Pagination.svelte';
  import { marked } from 'marked';
  marked.setOptions({ breaks: true, gfm: true });

  let channel = $state(null);
  let videos = $state([]);
  let channelPlaylists = $state([]);
  let localPlaylists = $state([]);
  let loadingPlaylists = $state(false);
  let fetchingPlaylistVideos = $state(null);
  let totalVideos = $state(0);
  let page = $state(1);
  let source = $state('all');
  let videoType = $state('all');
  let sortBy = $state(getFilter('channelDetail', 'sortBy', 'newest'));
  let subscribingNow = $state(false);
  let loading = $state(true);
  let scanning = $state(false);
  let downloading = $state({});
  let showDescription = $state(false);
  let showDebug = $state(false);

  // Batch Download
  let batchLoading = $state(false);
  let missingCount = $state(0);
  let sourceCounts = $state({ all: 0, rss: 0, downloaded: 0 });

  // Meta / Filesystem
  let fsData = $state(null);
  let fsLoading = $state(false);
  let fsVideoExpanded = $state(null);
  let debugData = $state(null);
  let debugLoading = $state(false);
  let searchQuery = $state('');

  // Suggest-Exclude
  async function toggleChannelSuggest() {
    if (!channel?.id) return;
    const newVal = channel.suggest_exclude ? 0 : 1;
    try {
      await api.updateSubscription(channel.id, { suggest_exclude: newVal });
      channel.suggest_exclude = newVal;
      if (newVal === 0) {
        // Beim Re-Includen alle Video-Overrides löschen
        await api.resetSuggestOverrides(channel.id);
        videos = videos.map(v => ({ ...v, suggest_override: null }));
      }
      toast.success(newVal ? 'Kanal aus Zufallsvorschlägen entfernt' : 'Kanal in Zufallsvorschlägen');
    } catch (e) { toast.error('Fehler: ' + e.message); }
  }

  async function toggleVideoSuggest(video) {
    const vid = video.video_id;
    if (!vid || !video.is_downloaded) return;
    // Zyklus: null → 'exclude' → 'include' → null
    let next;
    if (!video.suggest_override) next = 'exclude';
    else if (video.suggest_override === 'exclude') next = 'include';
    else next = 'reset';
    try {
      await api.updateVideoSuggest(vid, next);
      video.suggest_override = next === 'reset' ? null : next;
      videos = [...videos]; // Reaktivität
    } catch (e) { toast.error('Fehler: ' + e.message); }
  }

  async function loadChannel() {
    const cid = $route.id;
    if (!cid) { navigate('/subscriptions'); return; }
    loading = true;
    try {
      channel = await api.getChannelDetail(cid);
      await loadVideos();
      loadPlaylists();
      loadMissingCount();
    } catch (e) {
      toast.error(e.message);
      navigate('/subscriptions');
    } finally {
      loading = false;
    }
  }

  async function loadVideos() {
    const cid = $route.id;
    if (!cid) return;
    try {
      const result = await api.getChannelVideos(cid, source, page, videoType, sortBy);
      videos = result.videos || [];
      totalVideos = result.total || 0;
      if (result.source_counts) sourceCounts = result.source_counts;
    } catch (e) { toast.error(e.message); }
  }

  async function scanChannel() {
    const cid = $route.id;
    if (!cid || scanning) return;
    scanning = true;
    try {
      await api.fetchAllChannelVideos(cid);
      toast.success('Kanal-Scan gestartet -  Fortschritt in der Aktivitätenleiste');
      pollScanStatus(cid);
    } catch (e) {
      toast.error(e.message);
      scanning = false;
    }
  }

  function pollScanStatus(cid) {
    let attempts = 0;
    const iv = setInterval(async () => {
      attempts++;
      try {
        const detail = await api.getChannelDetail(cid);
        if (detail.last_scanned && detail.last_scanned !== channel?.last_scanned) {
          clearInterval(iv);
          scanning = false;
          channel = detail;
          page = 1;
          await loadVideos();
          const tc = detail.type_counts || {};
          const parts = [];
          if (tc.video) parts.push(`${tc.video} Videos`);
          if (tc.short) parts.push(`${tc.short} Shorts`);
          if (tc.live) parts.push(`${tc.live} Live`);
          toast.success(`Scan abgeschlossen -  ${parts.join(', ') || (detail.rss_entry_count || 0) + ' Einträge'}`);
        }
      } catch {}
      if (attempts > 60) {
        clearInterval(iv);
        scanning = false;
        toast.info('Scan läuft noch im Hintergrund');
      }
    }, 5000);
  }

  async function loadDebug() {
    const cid = $route.id;
    if (!cid) return;
    debugLoading = true;
    try {
      debugData = await api.getChannelDebug(cid);
    } catch (e) { toast.error(e.message); }
    finally { debugLoading = false; }
  }

  function toggleDebug() {
    showDebug = !showDebug;
    if (showDebug && !debugData) loadDebug();
  }

  async function downloadVideo(video) {
    if (downloading[video.video_id]) return;
    downloading[video.video_id] = true;
    downloading = { ...downloading };
    try {
      await api.addDownload({
        url: `https://www.youtube.com/watch?v=${video.video_id}`,
        quality: channel?.download_quality || 'best',
        audio_only: channel?.audio_only || false,
      });
      toast.success(`"${video.title?.substring(0, 40)}…" zur Queue`);
    } catch (e) { toast.error(e.message); }
    finally {
      downloading[video.video_id] = false;
      downloading = { ...downloading };
    }
  }

  function openVideoDetail(video) {
    // Queue aus gefilterten Kanal-Videos → Skip/Autoplay im MiniPlayer
    const queueVideos = filteredVideos.map(v => ({
      id: v.video_id,
      title: v.title || v.video_id,
      channel_name: channel?.name || '',
      duration: v.duration || 0,
    }));
    const idx = queueVideos.findIndex(v => v.id === video.video_id);
    if (queueVideos.length > 1) {
      startQueue(null, channel?.name || 'Kanal', queueVideos, idx >= 0 ? idx : 0);
    }
    navigate(`/watch/${video.video_id}`);
  }

  // Typ-Badge klicken: video → short → live → video
  async function cycleType(video) {
    const current = video.video_type || 'video';
    const order = ['video', 'short', 'live'];
    const next = order[(order.indexOf(current) + 1) % order.length];
    try {
      await api.setVideoType(video.video_id, next);
      video.video_type = next;
      videos = [...videos]; // Reaktivität triggern
      const labels = { video: 'Video', short: 'Short', live: 'Live' };
      toast.success(`Typ → ${labels[next]}`);
    } catch (e) { toast.error(e.message); }
  }

  function goBack() { navigate('/subscriptions'); }

  async function subscribeChannel() {
    if (!channel || subscribingNow) return;
    subscribingNow = true;
    try {
      await api.addSubscription({ channel_id: channel.channel_id, channel_name: channel.channel_name });
      channel.subscribed = true;
      toast.success(`"${channel.channel_name}" abonniert`);
      await loadChannel();
    } catch (e) {
      if (e.message?.includes('UNIQUE') || e.message?.includes('bereits')) {
        channel.subscribed = true;
        toast.info('Bereits abonniert');
      } else {
        toast.error(e.message);
      }
    }
    subscribingNow = false;
  }

  function changeSource(s) { source = s; page = 1; loadVideos(); }
  function changeType(t) {
    videoType = t;
    if (t === 'playlists') {
      loadPlaylists();
    } else if (t === 'meta') {
      loadFilesystem();
    } else {
      page = 1; loadVideos(); loadMissingCount();
    }
  }

  async function loadPlaylists() {
    const cid = $route.id;
    if (!cid) return;
    try {
      const res = await api.getChannelPlaylists(cid);
      channelPlaylists = res.playlists || [];
      localPlaylists = res.local_playlists || [];
    } catch { channelPlaylists = []; localPlaylists = []; }
  }

  async function fetchPlaylists() {
    const cid = $route.id;
    if (!cid) return;
    loadingPlaylists = true;
    try {
      const res = await api.fetchChannelPlaylists(cid);
      toast.success('Playlists werden geladen… (siehe Aktivitäten)');
      setTimeout(async () => { await loadPlaylists(); loadingPlaylists = false; }, 3000);
      setTimeout(async () => { await loadPlaylists(); }, 10000);
    } catch (e) { toast.error(e.message); loadingPlaylists = false; }
  }

  async function fetchPlaylistVids(playlistId) {
    fetchingPlaylistVideos = playlistId;
    try {
      const res = await api.fetchPlaylistVideos(playlistId);
      toast.success(`Video-IDs werden geladen… (Job #${res.job_id})`);
      const poll = setInterval(async () => {
        await loadPlaylists();
        const pl = channelPlaylists.find(p => p.playlist_id === playlistId);
        if (pl && Array.isArray(pl.video_ids) && pl.video_ids.length > 0) {
          fetchingPlaylistVideos = null;
          clearInterval(poll);
          toast.success(`${pl.video_ids.length} Video-IDs geladen für „${pl.title}"`);
        }
      }, 3000);
      setTimeout(() => {
        clearInterval(poll);
        if (fetchingPlaylistVideos === playlistId) {
          fetchingPlaylistVideos = null;
          toast.warning('Timeout -  prüfe Aktivitäten für Status');
        }
      }, 120000);
    } catch (e) { toast.error(e.message); fetchingPlaylistVideos = null; }
  }

  async function importPlaylist(playlistId) {
    try {
      const res = await api.importPlaylistToLocal(playlistId);
      toast.success(`Import gestartet: „${res.title}" (${res.total_videos} Videos)`);
      // Nach Import Playlists neu laden
      setTimeout(async () => { await loadPlaylists(); }, 3000);
      setTimeout(async () => { await loadPlaylists(); }, 8000);
    } catch (e) { toast.error(e.message); }
  }

  async function toggleVisibility(localPl) {
    const newVis = localPl.visibility === 'channel' ? 'global' : 'channel';
    try {
      await api.togglePlaylistVisibility(localPl.id, newVis);
      toast.success(newVis === 'global' ? 'Playlist global sichtbar' : 'Playlist nur auf Kanal-Seite');
      await loadPlaylists();
    } catch (e) { toast.error(e.message); }
  }

  const BATCH_SIZE = 20;
  let batchQueueing = $state(false);

  async function queueMissingFromPlaylist(pl) {
    const videoIds = pl.video_ids || [];
    if (!videoIds.length) { toast.info('Keine Video-IDs geladen'); return; }

    batchQueueing = true;
    try {
      // Prüfe aktuelle Queue-Größe
      const queue = await api.getQueue();
      const pendingCount = (queue.jobs || []).filter(j => j.status === 'queued' || j.status === 'active').length;

      if (pendingCount >= BATCH_SIZE) {
        toast.warning(`Bereits ${pendingCount} Downloads in Warteschlange -  warte bis Platz frei ist`);
        batchQueueing = false;
        return;
      }

      const slotsLeft = BATCH_SIZE - pendingCount;

      // Sammle nur fehlende Video-URLs (nicht-heruntergeladene)
      const urls = videoIds
        .map(vid => `https://www.youtube.com/watch?v=${vid}`)
        .slice(0, slotsLeft);

      const res = await api.addBatchDownload({ urls, audio_only: channel?.audio_only || false });
      const queued = (res.results || []).filter(r => r.status !== 'error').length;
      const errors = (res.results || []).filter(r => r.status === 'error').length;

      if (queued > 0) {
        const remaining = (pl.video_count - pl.have_count) - queued;
        toast.success(`${queued} Videos in Warteschlange${remaining > 0 ? ` · ${remaining} weitere verfügbar` : ''}`);
      } else if (errors > 0) {
        toast.info(`Keine neuen Videos -  ${errors} bereits geladen/in Queue`);
      } else {
        toast.info('Keine neuen Videos zum Laden');
      }

      await loadPlaylists();
    } catch (e) {
      toast.error(`Batch-Queue Fehler: ${e.message}`);
    }
    batchQueueing = false;
  }
  function changeSort(s) { sortBy = s; page = 1; saveFilters('channelDetail', { sortBy: s }); loadVideos(); }
  function changePage(p) { page = p; loadVideos(); }

  async function batchDownload(count) {
    const cid = $route.id;
    if (!cid || batchLoading) return;
    batchLoading = true;
    try {
      const res = await api.getMissingVideos(cid, count, videoType);
      if (!res.video_ids?.length) {
        toast.info('Keine fehlenden Videos zum Herunterladen');
        missingCount = 0;
        batchLoading = false;
        return;
      }
      const urls = res.video_ids.map(id => `https://www.youtube.com/watch?v=${id}`);
      const result = await api.addBatchDownload({ urls, audio_only: channel?.audio_only || false });
      const queued = result.results?.filter(r => r.status === 'queued').length || urls.length;
      missingCount = Math.max(0, res.total_missing - queued);
      const typeLabel = videoType === 'short' ? 'Shorts' : videoType === 'live' ? 'Live' : 'Videos';
      toast.success(`${queued} ${typeLabel} in Warteschlange · ${missingCount} weitere verfügbar`);
      await loadVideos();
    } catch (e) { toast.error(e.message); }
    batchLoading = false;
  }

  async function loadMissingCount() {
    try {
      const res = await api.getMissingVideos($route.id, 1, videoType);
      missingCount = res.total_missing || 0;
    } catch { missingCount = 0; }
  }

  async function loadFilesystem() {
    fsLoading = true;
    try {
      fsData = await api.getChannelFilesystem($route.id);
    } catch (e) { toast.error('Filesystem-Audit: ' + e.message); }
    fsLoading = false;
  }

  async function resetChannelError() {
    try {
      const res = await api.resetChannelError($route.id);
      toast.success(`${res.channel} entsperrt`);
      channel.error_count = 0;
      channel.last_error = null;
      channel.enabled = true;
    } catch (e) { toast.error(e.message); }
  }

  function fmtSize(bytes) {
    if (!bytes) return '–';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
    return (bytes / 1073741824).toFixed(2) + ' GB';
  }

  let filteredVideos = $derived(
    searchQuery.trim()
      ? videos.filter(v => (v.title || '').toLowerCase().includes(searchQuery.toLowerCase()))
      : videos
  );

  $effect(() => { loadChannel(); });
</script>

<div class="page">
  {#if loading}
    <div class="loading">Lade Kanal…</div>
  {:else if channel}

    <!-- Banner -->
    {#if channel.banner_url}
      <div class="channel-banner">
        <img src={api.bannerUrl($route.id)} alt="Kanalbanner"
             onerror={(e) => e.target.parentElement.style.display='none'} />
      </div>
    {/if}

    <!-- Header -->
    <div class="channel-header">
      <button class="back-btn" onclick={goBack}>
        <i class="fa-solid fa-arrow-left"></i>
      </button>
      <div class="avatar-wrap">
        {#if channel.avatar_path}
          <img class="avatar" src={api.channelAvatarUrl(channel.channel_id)} alt="" />
        {:else}
          <div class="avatar-fb">{(channel.channel_name||'?')[0].toUpperCase()}</div>
        {/if}
      </div>
      <div class="channel-info">
        <h1 class="channel-name">{channel.channel_name || channel.channel_id}</h1>
        <div class="channel-meta">
          {#if !channel.subscribed}
            <button class="btn-subscribe" onclick={subscribeChannel} disabled={subscribingNow}>
              <i class="fa-solid fa-rss"></i> Abonnieren
            </button>
            <a class="yt-link-small" href="https://www.youtube.com/channel/{channel.channel_id}" target="_blank" rel="noopener">
              <i class="fa-solid fa-arrow-up-right-from-square"></i> YouTube
            </a>
          {/if}
          {#if channel.subscriber_count}
            <span class="meta-item">{formatViews(channel.subscriber_count)} Abonnenten</span>
          {/if}
          <span class="meta-item">
            {channel.video_count || 0} Videos
            {#if channel.shorts_count > 0} · {channel.shorts_count} Shorts{/if}
            {#if channel.live_count > 0} · {channel.live_count} Live{/if}
          </span>
          {#if channel.last_scanned}
            <span class="meta-item">Scan: {formatDateRelative(channel.last_scanned)}</span>
          {/if}
          {#if channel.subscribed}
            <button class="meta-btn-suggest" class:excluded={channel.suggest_exclude}
              onclick={(e) => { e.stopPropagation(); toggleChannelSuggest(); }}
              title={channel.suggest_exclude ? 'Aus Zufallsvorschlägen ausgeschlossen -  Klick zum Einschließen' : 'In Zufallsvorschlägen -  Klick zum Ausschließen'}>
              <i class="fa-solid fa-dice"></i>
            </button>
          {/if}
        </div>
        <!-- Channel Tags -->
        {#if channel.channel_tags_parsed?.length > 0}
          <div class="channel-tags">
            {#each channel.channel_tags_parsed.slice(0, 12) as tag}
              <span class="tag-chip">{tag}</span>
            {/each}
            {#if channel.channel_tags_parsed.length > 12}
              <span class="tag-more">+{channel.channel_tags_parsed.length - 12}</span>
            {/if}
          </div>
        {/if}
      </div>
    </div>

    <!-- Channel Description -->
    {#if channel.channel_description}
      <div class="channel-desc-wrap">
        <button class="desc-toggle" onclick={() => showDescription = !showDescription}>
          {#if showDescription}<i class="fa-solid fa-chevron-down"></i> Beschreibung ausblenden{:else}<i class="fa-solid fa-chevron-right"></i> Kanalbeschreibung anzeigen{/if}
        </button>
        {#if showDescription}
          <div class="channel-desc md-content">{@html marked.parse(channel.channel_description)}</div>
        {/if}
      </div>
    {/if}

    <!-- Stats -->
    <div class="stats-row">
      <div class="stat-box">
        <span class="stat-val">{channel.rss_entry_count || 0}</span>
        <span class="stat-lbl">Katalog</span>
      </div>
      <div class="stat-box">
        <span class="stat-val">{channel.downloaded_count || 0}</span>
        <span class="stat-lbl">Lokal</span>
      </div>
      {#if (channel.rss_entry_count || 0) > 0 && channel.last_scanned}
        {@const rss = channel.rss_entry_count || 0}
        {@const dl = channel.downloaded_count || 0}
        {@const missing = rss - dl}
        {#if missing <= 0}
          <div class="stat-box medal-box medal-gold"><span class="stat-val">🥇</span><span class="stat-lbl">Vollständig</span></div>
        {:else if missing <= 5}
          <div class="stat-box medal-box medal-silver"><span class="stat-val">🥈</span><span class="stat-lbl">{missing} fehlen</span></div>
        {:else if channel.drip_completed_at}
          <div class="stat-box medal-box medal-bronze"><span class="stat-val">🥉</span><span class="stat-lbl">{missing} fehlen</span></div>
        {/if}
      {/if}
      {#if channel.type_counts}
        {#if channel.type_counts.video > 0}
          <div class="stat-box">
            <span class="stat-val"><i class="fa-solid fa-video"></i> {channel.type_counts.video}</span>
            <span class="stat-lbl">Videos</span>
          </div>
        {/if}
        {#if channel.type_counts.short > 0}
          <div class="stat-box">
            <span class="stat-val"><i class="fa-solid fa-mobile-screen"></i> {channel.type_counts.short}</span>
            <span class="stat-lbl">Shorts</span>
          </div>
        {/if}
        {#if channel.type_counts.live > 0}
          <div class="stat-box">
            <span class="stat-val"><i class="fa-solid fa-tower-broadcast"></i> {channel.type_counts.live}</span>
            <span class="stat-lbl">Live</span>
          </div>
        {/if}
      {/if}
      {#if channel.total_downloaded_size > 0}
        <div class="stat-box">
          <span class="stat-val">{formatSize(channel.total_downloaded_size)}</span>
          <span class="stat-lbl">Belegt</span>
        </div>
      {/if}
      {#if channel.total_known_duration > 0}
        <div class="stat-box">
          <span class="stat-val">{formatDurationLong(channel.total_known_duration)}</span>
          <span class="stat-lbl">Gesamtlänge</span>
        </div>
      {/if}
      {#if channel.total_views > 0}
        <div class="stat-box">
          <span class="stat-val">{formatViews(channel.total_views)}</span>
          <span class="stat-lbl">Aufrufe</span>
        </div>
      {/if}
    </div>

    <!-- Scan-Bar -->
    <div class="scan-bar">
      <button class="btn-scan" onclick={scanChannel} disabled={scanning}>
        {#if scanning}
          <i class="fa-solid fa-spinner fa-spin"></i> Scanne…
        {:else}
          <i class="fa-solid fa-satellite-dish"></i> Kanal scannen
        {/if}
      </button>
      {#if channel.needs_scan}
        <span class="scan-hint">Noch nicht gescannt -  klicke um alle Inhalte zu laden</span>
      {:else if channel.last_scanned}
        <span class="scan-hint">Letzter Scan: {formatDateRelative(channel.last_scanned)}</span>
      {/if}
      {#if channel.download_quality && channel.download_quality !== '720p'}
        <span class="quality-tag">Qualität: {channel.download_quality}</span>
      {/if}
      {#if channel.audio_only}
        <span class="audio-tag"><i class="fa-solid fa-music"></i> Nur Audio</span>
      {/if}
      <button class="btn-debug" onclick={toggleDebug} title="Debug-Infos"><i class="fa-solid fa-bug"></i></button>
    </div>

    <!-- Error Banner -->
    {#if channel.error_count > 0 || !channel.enabled}
      <div class="error-banner">
        <div class="error-info">
          <i class="fa-solid fa-triangle-exclamation"></i>
          <div>
            <strong>{!channel.enabled ? 'Kanal deaktiviert' : `${channel.error_count} Fehler`}</strong>
            {#if channel.last_error}
              <span class="error-detail">{channel.last_error}</span>
            {/if}
          </div>
        </div>
        <button class="btn-sm btn-unlock" onclick={resetChannelError}>
          <i class="fa-solid fa-lock-open"></i> Entsperren
        </button>
      </div>
    {/if}

    <!-- Type Tabs -->
    <div class="type-tabs">
      {#each [
        ['all', 'Alle', channel.rss_entry_count || 0],
        ['video', 'Videos', channel.type_counts?.video || 0],
        ['short', 'Shorts', channel.type_counts?.short || 0],
        ['live', 'Live', channel.type_counts?.live || 0],
        ['playlists', 'Playlists', channelPlaylists.length + localPlaylists.length],
        ['meta', 'Meta', 0]
      ] as [key, label, count]}
        {#if key === 'all' || key === 'playlists' || key === 'meta' || count > 0}
          <button class="type-tab" class:active={videoType === key} onclick={() => changeType(key)}>
            {label} {#if count > 0}<span class="tab-count">{count}</span>{/if}
          </button>
        {/if}
      {/each}
    </div>

    {#if videoType === 'playlists'}
    <!-- Playlists View -->
    <div class="playlists-section">
      <div class="pl-toolbar">
        <button class="btn-sm btn-primary" onclick={fetchPlaylists} disabled={loadingPlaylists}>
          <i class="fa-solid fa-rotate"></i> {loadingPlaylists ? 'Lade…' : 'Playlist-Liste abrufen'}
        </button>
        <span class="pl-hint">Holt die Playlist-Namen und Beschreibungen von YouTube (kein Download, keine Video-Inhalte)</span>
      </div>

      {#if channelPlaylists.length === 0}
        <div class="empty">
          <i class="fa-solid fa-list-ul" style="font-size:2.5rem; color:var(--text-tertiary)"></i>
          <p>Keine Playlists gespeichert.</p>
          <p class="empty-hint">Klicke „Playlist-Liste abrufen" um die öffentlichen Playlists dieses Kanals zu sehen.</p>
        </div>
      {:else}
        <div class="pl-grid">
          {#each channelPlaylists as pl}
            <div class="pl-card">
              <div class="pl-header">
                <div class="pl-icon"><i class="fa-solid fa-list-ul"></i></div>
                <div class="pl-info">
                  <h3 class="pl-title">{pl.title}</h3>
                  <div class="pl-meta">
                    <span>{pl.video_count} Videos</span>
                    {#if pl.video_ids?.length > 0}
                      <span class="pl-have">· {pl.have_count} lokal</span>
                      {#if pl.video_count - pl.have_count > 0}
                        <span class="pl-missing">· {pl.video_count - pl.have_count} fehlen</span>
                      {/if}
                    {/if}
                  </div>
                  {#if pl.description}
                    <p class="pl-desc">{pl.description.substring(0, 120)}{pl.description.length > 120 ? '…' : ''}</p>
                  {/if}
                </div>
              </div>
              {#if pl.video_ids?.length > 0}
                <div class="pl-bar">
                  <div class="pl-bar-fill" style="width: {Math.round(pl.have_count / pl.video_count * 100)}%"></div>
                </div>
              {/if}
              <div class="pl-actions">
                <!-- Schritt 1: Playlist-Inhalt abrufen -->
                <button class="btn-sm" onclick={() => fetchPlaylistVids(pl.playlist_id)}
                  disabled={fetchingPlaylistVideos === pl.playlist_id}
                  title="Ruft ab, welche Videos in dieser Playlist sind (Reihenfolge + IDs). Kein Download!">
                  <i class="fa-solid fa-list-check"></i> {fetchingPlaylistVideos === pl.playlist_id ? 'Lade…' : 'Inhalt abrufen'}
                </button>
                {#if pl.video_ids?.length > 0}
                  <!-- Schritt 2: Lokal speichern / Aktualisieren -->
                  <button class="btn-sm" onclick={() => importPlaylist(pl.playlist_id)}
                    title={pl.local_playlist_id ? 'Playlist aktualisieren (neue Videos, Reihenfolge)' : 'Erstellt eine lokale Playlist -  bereits heruntergeladene Videos werden verknüpft'}>
                    {#if pl.local_playlist_id}
                      <i class="fa-solid fa-arrows-rotate"></i> Aktualisieren
                    {:else}
                      <i class="fa-solid fa-bookmark"></i> Lokal speichern
                    {/if}
                  </button>
                  <!-- Play wenn lokal gespeichert + Videos vorhanden -->
                  {#if pl.local_playlist_id && pl.have_count > 0}
                    <button class="btn-sm btn-play" onclick={() => navigate(`/playlists?open=${pl.local_playlist_id}&play=1`)}
                      title="Playlist abspielen ({pl.have_count} lokale Videos)">
                      <i class="fa-solid fa-play"></i> Abspielen
                    </button>
                  {/if}
                  <!-- Schritt 3: Fehlende Videos in 20er-Paketen -->
                  {#if pl.video_count - pl.have_count > 0}
                    <button class="btn-sm btn-accent" onclick={() => queueMissingFromPlaylist(pl)}
                      disabled={batchQueueing}
                      title="Nächste {BATCH_SIZE} fehlende Videos in die Download-Warteschlange stellen">
                      <i class="fa-solid fa-cloud-arrow-down"></i>
                      {batchQueueing ? 'Queued…' : `${Math.min(pl.video_count - pl.have_count, BATCH_SIZE)} von ${pl.video_count - pl.have_count} laden`}
                    </button>
                  {/if}
                {/if}
              </div>
              <!-- Status-Zeile -->
              {#if pl.local_playlist_id}
                <div class="pl-imported-badge">
                  <i class="fa-solid fa-check-circle"></i> Lokal gespeichert
                </div>
              {:else if !pl.video_ids?.length}
                <div class="pl-workflow-hint">
                  <i class="fa-solid fa-circle-info"></i>
                  „Inhalt abrufen" holt die Video-Liste dieser Playlist von YouTube
                </div>
              {/if}
            </div>
          {/each}
        </div>
      {/if}

      <!-- Lokale Playlists dieses Kanals -->
      {#if localPlaylists.length > 0}
        <h4 class="pl-section-title">Lokale Playlists</h4>
        <div class="pl-grid">
          {#each localPlaylists as lp}
            <div class="pl-card pl-card-local">
              <div class="pl-header">
                <div class="pl-icon"><i class="fa-solid fa-music"></i></div>
                <div class="pl-info">
                  <h3 class="pl-title">{lp.name}</h3>
                  <div class="pl-meta">
                    <span>{lp.ready_count || 0} von {lp.actual_count || 0} Videos lokal</span>
                    {#if lp.source === 'youtube'}
                      <span class="pl-yt-badge">YouTube</span>
                    {/if}
                  </div>
                </div>
              </div>
              {#if lp.actual_count > 0}
                <div class="pl-bar">
                  <div class="pl-bar-fill" style="width: {Math.round((lp.ready_count || 0) / lp.actual_count * 100)}%"></div>
                </div>
              {/if}
              <div class="pl-actions">
                {#if lp.ready_count > 0}
                  <button class="btn-sm btn-play" onclick={() => navigate(`/playlists?open=${lp.id}&play=1`)}
                    title="Playlist abspielen">
                    <i class="fa-solid fa-play"></i> Abspielen
                  </button>
                {/if}
                <button class="btn-sm" onclick={() => navigate(`/playlists?open=${lp.id}`)}
                  title="Playlist öffnen">
                  <i class="fa-solid fa-external-link"></i> Öffnen
                </button>
                <button class="btn-sm" onclick={() => toggleVisibility(lp)}
                  title={lp.visibility === 'channel' ? 'Nur auf Kanal-Seite sichtbar -  klick für global' : 'Global sichtbar -  klick für nur Kanal'}>
                  {#if lp.visibility === 'channel'}
                    <i class="fa-solid fa-eye-slash"></i> Kanal
                  {:else}
                    <i class="fa-solid fa-eye"></i> Global
                  {/if}
                </button>
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </div>

    {:else if videoType === 'meta'}
    <!-- Meta / Filesystem Audit -->
    <div class="meta-section">
      {#if fsLoading}
        <div class="meta-loading"><i class="fa-solid fa-spinner fa-spin"></i> Filesystem-Audit läuft…</div>
      {:else if fsData}

        <!-- Kanal-Dateien -->
        <div class="meta-group">
          <h4 class="meta-group-title"><i class="fa-solid fa-user-circle"></i> Kanal-Dateien</h4>
          <div class="meta-file-grid">
            {#each Object.entries(fsData.channel_files) as [key, f]}
              <div class="meta-file-row" class:meta-exists={f.exists} class:meta-missing={!f.exists}>
                <span class="meta-file-icon">{f.exists ? '✓' : '✗'}</span>
                <span class="meta-file-label">{key}</span>
                <code class="meta-path" title={f.host}>{f.docker}</code>
                {#if f.exists && f.size}
                  <span class="meta-file-size">{fmtSize(f.size)}</span>
                {/if}
              </div>
            {/each}
          </div>
        </div>

        <!-- DB-Only Kanal-Daten -->
        <div class="meta-group">
          <h4 class="meta-group-title"><i class="fa-solid fa-database"></i> Nur in DB (kein Datei-Backup)</h4>
          <div class="meta-file-grid">
            {#each Object.entries(fsData.channel_db_only) as [key, info]}
              <div class="meta-file-row meta-db-only">
                <span class="meta-file-icon">⚠</span>
                <span class="meta-file-label">{key}</span>
                {#if info.count !== undefined}
                  <span class="meta-db-count">{info.count} Einträge</span>
                {/if}
                <span class="meta-db-badge">nur DB</span>
              </div>
            {/each}
          </div>
        </div>

        <!-- Geplante Struktur -->
        <div class="meta-group">
          <h4 class="meta-group-title"><i class="fa-solid fa-folder-tree"></i> Geplante Dateistruktur</h4>
          <div class="meta-file-grid">
            {#each Object.entries(fsData.planned_structure) as [key, f]}
              <div class="meta-file-row" class:meta-exists={f.exists} class:meta-planned={!f.exists}>
                <span class="meta-file-icon">{f.exists ? '✓' : '○'}</span>
                <span class="meta-file-label">{key.replace(/_/g, '.')}</span>
                <code class="meta-path" title={f.host}>{f.docker}</code>
              </div>
            {/each}
          </div>
        </div>

        <!-- Basispfade -->
        <div class="meta-group">
          <h4 class="meta-group-title"><i class="fa-solid fa-hard-drive"></i> Basispfade</h4>
          <div class="meta-file-grid">
            <div class="meta-file-row meta-path-row">
              <span class="meta-file-label">Docker</span>
              <code class="meta-path">{fsData.paths.data_dir.docker}</code>
            </div>
            <div class="meta-file-row meta-path-row">
              <span class="meta-file-label">Host</span>
              <code class="meta-path">{fsData.paths.data_dir.host}</code>
            </div>
          </div>
          <div class="meta-dir-grid">
            {#each Object.entries(fsData.paths).filter(([k]) => k !== 'data_dir') as [key, dir]}
              <div class="meta-dir-chip" class:meta-exists={dir.exists}>
                <span>{key.replace('_dir','')}</span>
                {#if dir.file_count !== undefined}<span class="meta-dir-count">{dir.file_count}</span>{/if}
              </div>
            {/each}
          </div>
        </div>

        <!-- Video-Übersicht -->
        <div class="meta-group">
          <h4 class="meta-group-title">
            <i class="fa-solid fa-film"></i> Videos ({fsData.video_totals.total_videos})
          </h4>
          <div class="meta-totals">
            <div class="meta-total-chip" class:meta-complete={fsData.video_totals.video === fsData.video_totals.total_videos}>
              <i class="fa-solid fa-video"></i> Video {fsData.video_totals.video}/{fsData.video_totals.total_videos}
            </div>
            <div class="meta-total-chip" class:meta-complete={fsData.video_totals.thumb === fsData.video_totals.total_videos}>
              <i class="fa-solid fa-image"></i> Thumbs {fsData.video_totals.thumb}/{fsData.video_totals.total_videos}
            </div>
            <div class="meta-total-chip">
              <i class="fa-solid fa-closed-captioning"></i> Subs {fsData.video_totals.subs}
            </div>
            <div class="meta-total-chip">
              <i class="fa-solid fa-music"></i> Lyrics {fsData.video_totals.lyrics}
            </div>
            <div class="meta-total-chip">
              <i class="fa-solid fa-list-ol"></i> Chapters {fsData.video_totals.chapters}
            </div>
            <div class="meta-total-chip" class:meta-none={fsData.video_totals.meta_json === 0}>
              <i class="fa-solid fa-file-code"></i> meta.json {fsData.video_totals.meta_json}/{fsData.video_totals.total_videos}
            </div>
          </div>

          <!-- Video-Liste (klappbar) -->
          <div class="meta-video-list">
            {#each fsData.videos as v}
              <div class="meta-video-row">
                <button class="meta-video-toggle" onclick={() => fsVideoExpanded = fsVideoExpanded === v.id ? null : v.id}>
                  <span class="meta-video-indicators">
                    <span class="mi" class:ok={v.files.video?.exists} title="Video">V</span>
                    <span class="mi" class:ok={v.files.thumbnail?.exists} title="Thumb">T</span>
                    <span class="mi" class:ok={v.files.subtitles?.file_count > 0} title="Subs">S</span>
                    <span class="mi" class:ok={v.files.lyrics?.file_count > 0} title="Lyrics">L</span>
                    <span class="mi" class:ok={v.db_chapters > 0} title="Chapters">C</span>
                    <span class="mi" class:ok={v.files.meta_json?.exists} title="meta.json">M</span>
                  </span>
                  <span class="meta-video-title">{v.title}</span>
                  <span class="meta-video-type">{v.type}</span>
                </button>

                {#if fsVideoExpanded === v.id}
                  <div class="meta-video-detail">
                    {#each Object.entries(v.files) as [fkey, f]}
                      <div class="meta-detail-row" class:meta-exists={f.exists} class:meta-missing={!f.exists}>
                        <span class="meta-file-icon">{f.exists ? '✓' : '✗'}</span>
                        <span class="meta-file-label">{fkey}</span>
                        <code class="meta-path" title={f.host}>{f.docker}</code>
                        {#if f.size}<span class="meta-file-size">{fmtSize(f.size)}</span>{/if}
                        {#if f.file_count !== undefined}<span class="meta-file-size">{f.file_count} Dateien</span>{/if}
                      </div>
                    {/each}
                    {#if v.db_only}
                      <div class="meta-detail-dbonly">
                        <span class="meta-db-badge">DB-Only:</span>
                        {#each Object.entries(v.db_only).filter(([,val]) => val) as [k, val]}
                          <span class="meta-db-tag">{k}: {typeof val === 'boolean' ? '✓' : val}</span>
                        {/each}
                      </div>
                    {/if}
                  </div>
                {/if}
              </div>
            {/each}
          </div>
        </div>

      {:else}
        <div class="meta-loading">Klicke auf „Meta" um den Filesystem-Audit zu laden.</div>
      {/if}
    </div>

    {:else}
    <!-- Filter + Sort Row -->
    <div class="filter-sort-row">
      <div class="filter-bar">
        {#each [['all','Alle'],['rss','Katalog'],['downloaded','Lokal']] as [key, label]}
          <button class="filter-chip" class:active={source===key} onclick={() => changeSource(key)}>
            {label} <span class="chip-count">{sourceCounts[key] ?? ''}</span>
          </button>
        {/each}
      </div>
      <div class="sort-wrap">
        <select class="sort-select" value={sortBy} onchange={(e) => changeSort(e.target.value)}>
          <option value="newest">Neueste</option>
          <option value="oldest">Älteste</option>
          <option value="popular">Beliebteste</option>
          <option value="longest">Längste</option>
          <option value="shortest">Kürzeste</option>
        </select>
      </div>
      <div class="search-wrap">
        <input type="text" class="search-input" placeholder="Videos filtern…" bind:value={searchQuery} />
        {#if searchQuery}
          <button class="search-clear" onclick={() => searchQuery = ''} title="Suche leeren"><i class="fa-solid fa-xmark"></i></button>
        {/if}
      </div>
    </div>

    <!-- Batch Download Bar -->
    {#if missingCount > 0}
      <div class="batch-bar">
        <span class="batch-label">
          <i class="fa-solid fa-cloud-arrow-down"></i>
          {missingCount} {videoType === 'short' ? 'Shorts' : videoType === 'live' ? 'Live' : videoType === 'video' ? 'Videos' : 'Videos/Shorts/Live'} nicht lokal
        </span>
        <div class="batch-btns">
          {#each [5, 10, 20, 50] as n}
            {#if missingCount >= n || n === 5}
              <button class="btn-sm btn-accent" onclick={() => batchDownload(n)}
                disabled={batchLoading}
                title="{n} fehlende Videos in die Warteschlange">
                {batchLoading ? '…' : n}
              </button>
            {/if}
          {/each}
        </div>
      </div>
    {/if}

    <!-- Debug Panel -->
    {#if showDebug}
      <div class="debug-panel">
        <h3><i class="fa-solid fa-bug"></i> Debug-Info</h3>
        {#if debugLoading}
          <p class="debug-loading">Lade Debug-Daten…</p>
        {:else if debugData}
          <div class="debug-grid">
            <div class="debug-section">
              <h4>Typ-Verteilung</h4>
              <div class="debug-kv">
                <span>Videos:</span><span>{debugData.type_distribution?.video || 0}</span>
                <span>Shorts:</span><span>{debugData.type_distribution?.short || 0}</span>
                <span>Live:</span><span>{debugData.type_distribution?.live || 0}</span>
                <span>Unbekannt:</span><span>{debugData.type_distribution?.unknown || 0}</span>
                <span>Gesamt:</span><span><strong>{debugData.total_entries || 0}</strong></span>
              </div>
            </div>
            <div class="debug-section">
              <h4>Fehlende Daten</h4>
              <div class="debug-kv">
                <span>Ohne Duration:</span><span>{debugData.missing_data?.no_duration || 0}</span>
                <span>Ohne Views:</span><span>{debugData.missing_data?.no_views || 0}</span>
                <span>Ohne Thumbnail:</span><span>{debugData.missing_data?.no_thumbnail || 0}</span>
                <span>Ohne Beschreibung:</span><span>{debugData.missing_data?.no_description || 0}</span>
                <span>Ohne Titel:</span><span>{debugData.missing_data?.no_title || 0}</span>
                <span>Mit Keywords:</span><span>{debugData.keywords_count || 0}</span>
              </div>
            </div>
            {#if debugData.duration_stats}
              <div class="debug-section debug-full">
                <h4>Duration-Statistiken</h4>
                {#each Object.entries(debugData.duration_stats) as [type, stats]}
                  <div class="debug-dur-row">
                    <strong>{type} {type}:</strong>
                    {stats.count}× · Min {formatDuration(stats.min)} · Max {formatDuration(stats.max)} · Ø {formatDuration(Math.round(stats.avg))} · Σ {formatDurationLong(stats.total)}
                  </div>
                {/each}
              </div>
            {/if}
            <div class="debug-section">
              <h4>Abo-Details</h4>
              <div class="debug-kv">
                <span>Channel ID:</span><span class="debug-mono">{debugData.subscription?.channel_id}</span>
                <span>Banner:</span><span>{debugData.subscription?.banner_url ? 'Vorhanden' : 'Fehlt'}</span>
                <span>Tags:</span><span>{debugData.subscription?.channel_tags_parsed?.length || 0} Tags</span>
                <span>Avatar:</span><span>{debugData.subscription?.avatar_path ? 'Ja' : 'Nein'}</span>
              </div>
            </div>
            {#if debugData.recent_jobs?.length > 0}
              <div class="debug-section debug-full">
                <h4>Letzte Scan-Jobs</h4>
                {#each debugData.recent_jobs as job}
                  <div class="debug-job">
                    <span class="debug-job-status" class:ok={job.status === 'completed'} class:err={job.status === 'failed'}>
                      {#if job.status === 'completed'}<i class="fa-solid fa-check"></i>{:else if job.status === 'failed'}<i class="fa-solid fa-xmark"></i>{:else}<i class="fa-solid fa-ellipsis"></i>{/if} {job.status}
                    </span>
                    <span class="debug-job-time">{formatDateRelative(job.created_at)}</span>
                    {#if job.result}
                      <span class="debug-job-result">{job.result}</span>
                    {/if}
                    {#if job.error_message}
                      <span class="debug-job-error">{job.error_message}</span>
                    {/if}
                  </div>
                {/each}
              </div>
            {/if}
          </div>
          <button class="btn-refresh-debug" onclick={loadDebug}><i class="fa-solid fa-rotate-right"></i> Aktualisieren</button>
        {:else}
          <p>Keine Debug-Daten verfügbar.</p>
        {/if}
      </div>
    {/if}

    <!-- Video-Liste -->
    {#if filteredVideos.length > 0}
      <div class="video-list">
        {#each filteredVideos as video (video.video_id)}
          <div class="video-row" onclick={() => openVideoDetail(video)}>
            <div class="thumb-wrap">
              {#if video.is_downloaded && video.thumbnail_path}
                <img class="thumb" src={api.thumbnailUrl(video.video_id)} alt="" loading="lazy"
                     onerror={(e) => { e.target.src = api.rssThumbUrl(video.video_id); }} />
              {:else if video.video_id}
                <img class="thumb" src={api.rssThumbUrl(video.video_id)} alt="" loading="lazy"
                     onerror={(e) => e.target.style.display='none'} />
              {:else}
                <div class="thumb-placeholder"><i class="fa-solid fa-film"></i></div>
              {/if}
              {#if video.duration}
                <span class="duration">{formatDuration(video.duration)}</span>
              {/if}
              {#if video.is_downloaded}
                <span class="dl-indicator"><i class="fa-solid fa-circle-check"></i></span>
              {/if}
              {#if video.video_type === 'short'}
                <span class="type-indicator type-short">S</span>
              {:else if video.video_type === 'live'}
                <span class="type-indicator type-live">L</span>
              {/if}
            </div>
            <div class="video-info">
              <span class="video-title">{video.title || video.video_id}</span>
              <div class="video-meta">
                {#if video.published}
                  <span>{formatDateRelative(video.published)}</span>
                {/if}
                {#if video.view_count}
                  <span>{formatViews(video.view_count)} Aufrufe</span>
                {/if}
                {#if video.file_size}
                  <span>{formatSize(video.file_size)}</span>
                {/if}
              </div>
              <div class="video-badges">
                {#if video.is_downloaded}
                  <span class="badge badge-ok">Lokal</span>
                {:else if video.is_in_queue}
                  <span class="badge badge-queue"><i class="fa-solid fa-download"></i> Queue</span>
                {:else if video.rss_status === 'new'}
                  <span class="badge badge-new">Neu</span>
                {/if}
                {#if channel?.audio_only}
                  <span class="type-badge badge-audio" title="Audio-Only Kanal">
                    <i class="fa-solid fa-podcast"></i> Audio
                  </span>
                {:else}
                  <button class="type-badge badge-{video.video_type || 'video'}"
                    onclick={(e) => { e.stopPropagation(); cycleType(video); }}
                    title="Klick: Typ ändern (Video → Short → Live)">
                    {#if video.video_type === 'short'}
                      <i class="fa-solid fa-bolt"></i> Short
                    {:else if video.video_type === 'live'}
                      <i class="fa-solid fa-tower-broadcast"></i> Live
                    {:else}
                      <i class="fa-solid fa-film"></i> Video
                    {/if}
                  </button>
                {/if}
              </div>
            </div>
            <div class="video-actions" onclick={(e) => e.stopPropagation()}>
              {#if video.is_downloaded}
                <button class="btn-sm btn-suggest"
                  class:sg-exclude={video.suggest_override === 'exclude'}
                  class:sg-include={video.suggest_override === 'include'}
                  onclick={() => toggleVideoSuggest(video)}
                  title={video.suggest_override === 'exclude' ? 'Aus Vorschlägen ausgeschlossen' : video.suggest_override === 'include' ? 'Explizit eingeschlossen' : 'Kanal-Standard'}>
                  <i class="fa-solid fa-dice"></i>
                </button>
              {/if}
              <QuickPlaylistBtn videoId={video.video_id} title={video.title} channelName={channel?.channel_name} channelId={video.channel_id || channel?.channel_id} size="sm" />
              {#if video.is_downloaded}
                <button class="btn-sm btn-play" onclick={() => openVideoDetail(video)} title="Abspielen"><i class="fa-solid fa-play"></i></button>
              {:else if video.is_in_queue}
                <span class="btn-sm btn-wait"><i class="fa-solid fa-clock"></i></span>
              {:else}
                <button class="btn-sm btn-dl"
                  onclick={() => downloadVideo(video)}
                  disabled={downloading[video.video_id]}
                  title="Herunterladen">
                  <i class="fa-solid fa-download"></i>
                </button>
              {/if}
            </div>
          </div>
        {/each}
      </div>

      <Pagination {page} totalPages={Math.ceil(totalVideos / 50)} onchange={changePage} />
    {:else if !scanning}
      <div class="empty">
        {#if channel.needs_scan}
          <i class="fa-solid fa-satellite-dish" style="font-size:3rem; color:var(--text-tertiary)"></i>
          <h3>Kanal noch nicht gescannt</h3>
          <p>Klicke "Kanal scannen" um alle Videos, Shorts und Livestreams zu entdecken.</p>
        {:else if searchQuery}
          <p>Keine Videos für "{searchQuery}" gefunden.</p>
        {:else}
          <p>Keine Videos in dieser Ansicht.</p>
        {/if}
      </div>
    {/if}
    {/if}
  {/if}
</div>

<style>
  .page { padding: 24px; max-width: 960px; }
  .loading { text-align: center; padding: 60px; color: var(--text-tertiary); }

  .channel-banner {
    width: 100%; height: 160px; border-radius: 12px; overflow: hidden;
    margin-bottom: 16px; background: var(--bg-tertiary);
  }
  .channel-banner img { width: 100%; height: 100%; object-fit: cover; }

  .channel-header {
    display: flex; align-items: flex-start; gap: 16px;
    margin-bottom: 16px; padding-bottom: 16px;
    border-bottom: 1px solid var(--border-primary);
  }
  .back-btn {
    background: none; border: 1px solid var(--border-primary); border-radius: 8px;
    padding: 8px; cursor: pointer; color: var(--text-secondary); display: flex; flex-shrink: 0;
    margin-top: 4px;
  }
  .back-btn:hover { border-color: var(--accent-primary); color: var(--text-primary); }

  .avatar-wrap { flex-shrink: 0; }
  .avatar { width: 64px; height: 64px; border-radius: 50%; object-fit: cover; border: 2px solid var(--border-secondary); }
  .avatar-fb {
    width: 64px; height: 64px; border-radius: 50%; background: var(--accent-muted);
    color: var(--accent-primary); display: flex; align-items: center; justify-content: center;
    font-size: 1.8rem; font-weight: 700;
  }

  .channel-info { flex: 1; min-width: 0; }
  .channel-name { font-size: 1.3rem; font-weight: 700; color: var(--text-primary); margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .btn-subscribe {
    display: inline-flex; align-items: center; gap: 6px; padding: 5px 14px;
    background: var(--accent-primary); color: #fff; border: none; border-radius: 6px;
    font-size: 0.78rem; font-weight: 600; cursor: pointer;
  }
  .btn-subscribe:hover { background: var(--accent-hover); }
  .btn-subscribe:disabled { opacity: 0.5; }
  .yt-link-small {
    display: inline-flex; align-items: center; gap: 4px; padding: 5px 12px;
    background: var(--bg-tertiary); border: 1px solid var(--border-primary); border-radius: 6px;
    color: var(--text-secondary); font-size: 0.76rem; text-decoration: none;
  }
  .yt-link-small:hover { border-color: var(--accent-primary); color: var(--accent-primary); }
  .channel-meta { display: flex; gap: 14px; margin-top: 4px; flex-wrap: wrap; }
  .meta-item { font-size: 0.78rem; color: var(--text-tertiary); }

  .channel-tags { display: flex; gap: 4px; margin-top: 6px; flex-wrap: wrap; }
  .tag-chip {
    padding: 1px 8px; border-radius: 10px; font-size: 0.66rem; font-weight: 500;
    background: var(--bg-tertiary); color: var(--text-secondary); border: 1px solid var(--border-primary);
  }
  .tag-more { font-size: 0.66rem; color: var(--text-tertiary); padding: 1px 4px; }

  .channel-desc-wrap { margin-bottom: 16px; }
  .desc-toggle {
    background: none; border: none; color: var(--accent-primary); cursor: pointer;
    font-size: 0.82rem; padding: 0; margin-bottom: 6px;
  }
  .desc-toggle:hover { text-decoration: underline; }
  .channel-desc {
    font-size: 0.82rem; color: var(--text-secondary); line-height: 1.5;
    max-height: 200px; overflow-y: auto;
    padding: 10px 14px; background: var(--bg-secondary); border-radius: 8px;
    border: 1px solid var(--border-primary); margin: 0;
  }

  .stats-row { display: flex; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
  .stat-box {
    flex: 1; min-width: 80px; padding: 10px 14px; background: var(--bg-secondary);
    border: 1px solid var(--border-primary); border-radius: 10px; text-align: center;
  }
  .stat-val { display: block; font-size: 1rem; font-weight: 700; color: var(--text-primary); }
  .stat-lbl { font-size: 0.65rem; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.3px; }

  .scan-bar {
    display: flex; align-items: center; gap: 12px; margin-bottom: 16px;
    padding: 10px 14px; background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 10px; flex-wrap: wrap;
  }
  .btn-scan {
    padding: 7px 16px; background: var(--accent-primary); color: #fff; border: none;
    border-radius: 8px; font-size: 0.82rem; font-weight: 600; cursor: pointer; white-space: nowrap;
  }
  .btn-scan:hover:not(:disabled) { opacity: 0.9; }
  .btn-scan:disabled { opacity: 0.5; cursor: not-allowed; }
  .scan-hint { font-size: 0.78rem; color: var(--text-tertiary); }

  .error-banner {
    display: flex; align-items: center; justify-content: space-between; gap: 12px;
    padding: 10px 14px; margin-bottom: 4px;
    background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.25);
    border-radius: 8px;
  }
  .error-info {
    display: flex; align-items: flex-start; gap: 10px; color: var(--status-error);
    font-size: 0.78rem; flex: 1; min-width: 0;
  }
  .error-info i { margin-top: 2px; flex-shrink: 0; }
  .error-info strong { display: block; }
  .error-detail {
    display: block; font-size: 0.7rem; color: var(--text-tertiary);
    margin-top: 2px; word-break: break-word;
  }
  .btn-unlock {
    background: rgba(34,197,94,0.15); color: var(--status-success);
    border: 1px solid rgba(34,197,94,0.3); white-space: nowrap;
  }
  .btn-unlock:hover { background: rgba(34,197,94,0.25); }
  .quality-tag { font-size: 0.72rem; padding: 2px 8px; background: var(--accent-muted); color: var(--accent-primary); border-radius: 4px; font-weight: 600; }
  .audio-tag { font-size: 0.72rem; padding: 2px 8px; background: rgba(139,92,246,0.15); color: #8b5cf6; border-radius: 4px; font-weight: 600; }
  .btn-debug {
    background: none; border: 1px solid var(--border-primary); border-radius: 8px;
    padding: 4px 8px; cursor: pointer; font-size: 0.85rem; margin-left: auto;
  }
  .btn-debug:hover { border-color: var(--accent-primary); }
  .spin-icon { animation: spin 1s linear infinite; display: inline-block; }
  @keyframes spin { to { transform: rotate(360deg); } }

  .type-tabs {
    display: flex; gap: 2px; margin-bottom: 12px;
    border-bottom: 2px solid var(--border-primary); padding-bottom: 0;
  }
  .type-tab {
    padding: 8px 16px; background: none; border: none; border-bottom: 2px solid transparent;
    margin-bottom: -2px; cursor: pointer; font-size: 0.82rem; font-weight: 600;
    color: var(--text-tertiary); transition: all 0.15s;
  }
  .type-tab:hover { color: var(--text-primary); }
  .type-tab.active { color: var(--accent-primary); border-bottom-color: var(--accent-primary); }
  .tab-count { font-weight: 400; opacity: 0.7; font-size: 0.75rem; }

  .filter-sort-row {
    display: flex; gap: 10px; margin-bottom: 14px; align-items: center; flex-wrap: wrap;
  }
  .filter-bar { display: flex; gap: 4px; }
  .filter-chip {
    padding: 4px 12px; background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 20px; font-size: 0.75rem; color: var(--text-secondary); cursor: pointer;
  }
  .filter-chip:hover { border-color: var(--accent-primary); }
  .filter-chip.active { border-color: var(--accent-primary); background: var(--accent-muted); color: var(--accent-primary); }
  .chip-count { font-size: 0.65rem; opacity: 0.7; margin-left: 2px; }

  .sort-wrap { margin-left: auto; }
  .sort-select {
    padding: 5px 10px; background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 8px; font-size: 0.75rem; color: var(--text-secondary);
    cursor: pointer; outline: none;
  }
  .sort-select:focus { border-color: var(--accent-primary); }

  .search-wrap { position: relative; }
  .search-input {
    padding: 5px 28px 5px 10px; background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 8px; font-size: 0.75rem; color: var(--text-primary); width: 160px; outline: none;
  }
  .search-input:focus { border-color: var(--accent-primary); width: 200px; }
  .search-clear {
    position: absolute; right: 4px; top: 50%; transform: translateY(-50%);
    background: none; border: none; cursor: pointer; font-size: 0.7rem; color: var(--text-tertiary);
    padding: 2px 4px;
  }

  .batch-bar {
    display: flex; align-items: center; gap: 12px; padding: 8px 12px;
    background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 8px; margin-bottom: 12px;
  }
  .batch-label {
    font-size: 0.75rem; color: var(--text-secondary);
    display: flex; align-items: center; gap: 6px; white-space: nowrap;
  }
  .batch-btns { display: flex; gap: 6px; }
  .batch-btns .btn-sm {
    min-width: 36px; padding: 3px 8px; font-size: 0.72rem; font-weight: 600;
  }

  /* ─── Meta / Filesystem Audit ─── */
  .meta-section { display: flex; flex-direction: column; gap: 16px; }
  .meta-loading { text-align: center; padding: 40px; color: var(--text-tertiary); font-size: 0.8rem; }
  .meta-group {
    background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 10px; padding: 14px;
  }
  .meta-group-title {
    font-size: 0.78rem; font-weight: 600; color: var(--text-secondary);
    margin: 0 0 10px; display: flex; align-items: center; gap: 6px;
  }
  .meta-file-grid { display: flex; flex-direction: column; gap: 4px; }
  .meta-file-row {
    display: flex; align-items: center; gap: 8px; padding: 5px 8px;
    border-radius: 6px; font-size: 0.72rem;
  }
  .meta-file-row.meta-exists { background: rgba(34,197,94,0.06); }
  .meta-file-row.meta-missing { background: rgba(239,68,68,0.06); }
  .meta-file-row.meta-db-only { background: rgba(234,179,8,0.08); }
  .meta-file-row.meta-planned { background: rgba(100,116,139,0.08); }
  .meta-file-row.meta-path-row { background: var(--bg-tertiary); }
  .meta-file-icon { font-size: 0.7rem; width: 16px; text-align: center; flex-shrink: 0; }
  .meta-exists .meta-file-icon { color: var(--status-success); }
  .meta-missing .meta-file-icon { color: var(--status-error); }
  .meta-db-only .meta-file-icon { color: var(--status-warning); }
  .meta-planned .meta-file-icon { color: var(--text-quaternary, #64748b); }
  .meta-file-label { font-weight: 500; color: var(--text-secondary); min-width: 100px; }
  .meta-path {
    font-size: 0.65rem; color: var(--text-tertiary); background: var(--bg-tertiary);
    padding: 1px 6px; border-radius: 3px; overflow: hidden; text-overflow: ellipsis;
    white-space: nowrap; flex: 1; min-width: 0; cursor: help;
  }
  .meta-file-size { font-size: 0.65rem; color: var(--text-tertiary); white-space: nowrap; }
  .meta-db-count { font-size: 0.68rem; color: var(--text-tertiary); }
  .meta-db-badge {
    font-size: 0.6rem; background: rgba(234,179,8,0.2); color: #ca8a04;
    padding: 1px 6px; border-radius: 3px; white-space: nowrap;
  }

  .meta-dir-grid {
    display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px;
  }
  .meta-dir-chip {
    font-size: 0.65rem; padding: 3px 8px; border-radius: 5px;
    background: rgba(239,68,68,0.08); color: var(--text-tertiary);
    display: flex; align-items: center; gap: 4px;
  }
  .meta-dir-chip.meta-exists {
    background: rgba(34,197,94,0.08); color: var(--text-secondary);
  }
  .meta-dir-count {
    font-size: 0.6rem; background: var(--bg-tertiary); padding: 0 4px; border-radius: 3px;
  }

  .meta-totals { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
  .meta-total-chip {
    font-size: 0.7rem; padding: 4px 10px; border-radius: 6px;
    background: rgba(234,179,8,0.1); color: var(--text-secondary);
    display: flex; align-items: center; gap: 4px;
  }
  .meta-total-chip.meta-complete { background: rgba(34,197,94,0.1); color: var(--status-success); }
  .meta-total-chip.meta-none { background: rgba(239,68,68,0.08); color: var(--status-error); }

  .meta-video-list { display: flex; flex-direction: column; gap: 2px; }
  .meta-video-row {
    border-radius: 6px; overflow: hidden;
  }
  .meta-video-toggle {
    display: flex; align-items: center; gap: 8px; width: 100%; padding: 5px 8px;
    background: var(--bg-tertiary); border: none; cursor: pointer; text-align: left;
    color: var(--text-primary); font-size: 0.72rem;
  }
  .meta-video-toggle:hover { background: var(--bg-quaternary, rgba(255,255,255,0.06)); }
  .meta-video-indicators { display: flex; gap: 2px; flex-shrink: 0; }
  .mi {
    width: 16px; height: 16px; display: flex; align-items: center; justify-content: center;
    font-size: 0.55rem; font-weight: 700; border-radius: 3px;
    background: rgba(239,68,68,0.15); color: var(--status-error);
  }
  .mi.ok { background: rgba(34,197,94,0.15); color: var(--status-success); }
  .meta-video-title {
    flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .meta-video-type { font-size: 0.6rem; color: var(--text-quaternary, #64748b); }

  .meta-video-detail {
    padding: 6px 8px 8px 36px; background: var(--bg-secondary);
    border-top: 1px solid var(--border-secondary);
    display: flex; flex-direction: column; gap: 3px;
  }
  .meta-detail-row {
    display: flex; align-items: center; gap: 6px; font-size: 0.68rem; padding: 2px 6px;
    border-radius: 4px;
  }
  .meta-detail-row.meta-exists { background: rgba(34,197,94,0.05); }
  .meta-detail-row.meta-missing { background: rgba(239,68,68,0.05); }
  .meta-detail-dbonly {
    display: flex; flex-wrap: wrap; gap: 4px; align-items: center;
    padding: 4px 6px; margin-top: 4px;
  }
  .meta-db-tag {
    font-size: 0.6rem; background: var(--bg-tertiary); padding: 1px 5px;
    border-radius: 3px; color: var(--text-tertiary);
  }

  .debug-panel {
    background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 10px; padding: 16px; margin-bottom: 16px;
  }
  .debug-panel h3 { margin: 0 0 12px; font-size: 0.95rem; color: var(--text-primary); }
  .debug-panel h4 { margin: 0 0 6px; font-size: 0.78rem; color: var(--accent-primary); }
  .debug-loading { font-size: 0.82rem; color: var(--text-tertiary); }

  .debug-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  .debug-full { grid-column: 1 / -1; }
  .debug-section { background: var(--bg-tertiary); border-radius: 8px; padding: 10px 12px; }

  .debug-kv { display: grid; grid-template-columns: auto 1fr; gap: 2px 10px; font-size: 0.75rem; }
  .debug-kv span:nth-child(odd) { color: var(--text-tertiary); }
  .debug-kv span:nth-child(even) { color: var(--text-primary); }
  .debug-mono { font-family: monospace; font-size: 0.7rem; word-break: break-all; }

  .debug-dur-row { font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 4px; }

  .debug-job {
    display: flex; gap: 8px; align-items: center; font-size: 0.72rem;
    padding: 4px 0; border-bottom: 1px solid var(--border-primary); flex-wrap: wrap;
  }
  .debug-job:last-child { border-bottom: none; }
  .debug-job-status.ok { color: var(--status-success); }
  .debug-job-status.err { color: var(--status-error); }
  .debug-job-time { color: var(--text-tertiary); }
  .debug-job-result { color: var(--text-secondary); flex: 1; }
  .debug-job-error { color: var(--status-error); font-size: 0.68rem; width: 100%; }

  .btn-refresh-debug {
    margin-top: 10px; padding: 4px 12px; background: var(--bg-tertiary);
    border: 1px solid var(--border-primary); border-radius: 6px;
    font-size: 0.75rem; cursor: pointer; color: var(--text-secondary);
  }
  .btn-refresh-debug:hover { border-color: var(--accent-primary); }

  .video-list { display: flex; flex-direction: column; gap: 2px; }
  .video-row {
    display: flex; align-items: center; gap: 14px; padding: 8px 10px;
    border-radius: 10px; cursor: pointer; transition: background 0.15s;
  }
  .video-row:hover { background: var(--bg-secondary); }
  .video-row:hover .video-title { color: var(--accent-primary); }

  .thumb-wrap { position: relative; width: 160px; height: 90px; flex-shrink: 0; border-radius: 8px; overflow: hidden; background: var(--bg-tertiary); }
  .thumb { width: 100%; height: 100%; object-fit: cover; }
  .thumb-placeholder { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 1.6rem; }
  .duration { position: absolute; bottom: 4px; right: 4px; background: rgba(0,0,0,0.8); color: #fff; font-size: 0.68rem; padding: 1px 5px; border-radius: 4px; font-family: monospace; }
  .dl-indicator { position: absolute; top: 4px; left: 4px; font-size: 0.65rem; }
  .type-indicator { position: absolute; top: 4px; right: 4px; font-size: 0.7rem; }
  .type-short { background: rgba(0,0,0,0.6); border-radius: 4px; padding: 1px 3px; }
  .type-live { background: rgba(220,38,38,0.8); border-radius: 4px; padding: 1px 3px; }

  .video-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .video-title { font-size: 0.86rem; font-weight: 600; color: var(--text-primary); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; line-height: 1.3; transition: color 0.15s; }
  .video-meta { display: flex; gap: 10px; font-size: 0.72rem; color: var(--text-tertiary); }
  .video-badges { display: flex; gap: 4px; margin-top: 2px; }
  .badge { padding: 1px 7px; border-radius: 4px; font-size: 0.66rem; font-weight: 600; }
  .badge-ok { background: rgba(34,197,94,0.15); color: var(--status-success); }
  .badge-queue { background: var(--accent-muted); color: var(--accent-primary); }
  .badge-new { background: rgba(239,68,68,0.15); color: var(--status-error); }
  .badge-short { background: rgba(171,71,188,0.15); color: #AB47BC; }
  .badge-live { background: rgba(244,67,54,0.15); color: #EF5350; }
  .type-badge {
    padding: 1px 7px; border-radius: 4px; font-size: 0.66rem; font-weight: 600;
    border: 1px solid transparent; cursor: pointer; transition: all 0.15s;
    display: inline-flex; align-items: center; gap: 3px; line-height: 1.3;
  }
  .type-badge:hover { filter: brightness(1.3); border-color: currentColor; }
  .type-badge.badge-video { background: rgba(33,150,243,0.12); color: #42A5F5; }
  .type-badge.badge-short { background: rgba(171,71,188,0.15); color: #AB47BC; }
  .type-badge.badge-live { background: rgba(244,67,54,0.15); color: #EF5350; }
  .type-badge.badge-audio { background: rgba(33,150,243,0.15); color: #2196F3; cursor: default; }
  .type-badge.badge-audio:hover { filter: none; }

  .video-actions { flex-shrink: 0; }
  .btn-sm {
    width: 36px; height: 36px; border-radius: 8px; border: 1px solid var(--border-primary);
    background: var(--bg-secondary); cursor: pointer; font-size: 1rem;
    display: flex; align-items: center; justify-content: center;
  }
  .btn-sm:hover:not(:disabled) { border-color: var(--accent-primary); }
  .btn-sm:disabled { opacity: 0.4; cursor: not-allowed; }
  .btn-play { color: var(--status-success); }
  .btn-dl { color: var(--accent-primary); }
  .btn-wait { color: var(--text-tertiary); cursor: default; opacity: 0.5; border: 1px solid var(--border-primary); }


  .empty { display: flex; flex-direction: column; align-items: center; text-align: center; padding: 40px 20px; color: var(--text-tertiary); }
  .empty h3 { margin: 12px 0 6px; color: var(--text-secondary); }
  .empty p { font-size: 0.88rem; max-width: 360px; }

  /* Playlists */
  :global(.channel-desc a) { color: var(--accent-primary); text-decoration: none; }
  :global(.channel-desc a:hover) { text-decoration: underline; }
  :global(.channel-desc p) { margin: 0 0 6px; }
  :global(.channel-desc p:last-child) { margin: 0; }
  .playlists-section { margin-top: 16px; }
  .pl-toolbar { display: flex; gap: 8px; margin-bottom: 16px; align-items: center; flex-wrap: wrap; }
  .pl-hint { font-size: 0.7rem; color: var(--text-tertiary); font-style: italic; }
  .pl-workflow-hint {
    font-size: 0.7rem; color: var(--text-tertiary); padding: 8px 10px;
    display: flex; align-items: center; gap: 6px;
  }
  .pl-imported-badge {
    font-size: 0.7rem; color: var(--status-success); padding: 8px 10px;
    display: flex; align-items: center; gap: 6px;
  }
  .pl-section-title {
    margin: 28px 0 14px; font-size: 0.85rem; color: var(--text-secondary);
    border-top: 1px solid var(--border-primary); padding-top: 18px;
  }
  .pl-card-local { border-color: var(--accent-primary); border-style: solid; }
  .pl-card-local .pl-icon { background: var(--accent-muted, rgba(34,197,94,0.1)); color: var(--status-success); }
  .pl-yt-badge {
    font-size: 0.62rem; background: rgba(255,0,0,0.15); color: #f44; padding: 1px 5px;
    border-radius: 3px; font-weight: 600;
  }
  .pl-grid { display: flex; flex-direction: column; gap: 14px; }
  .pl-card { background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 10px; padding: 14px; }
  .pl-header { display: flex; gap: 12px; align-items: flex-start; }
  .pl-icon { width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; border-radius: 8px; background: var(--accent-muted, rgba(59,130,246,0.1)); color: var(--accent-primary); font-size: 1rem; flex-shrink: 0; }
  .pl-info { flex: 1; min-width: 0; }
  .pl-title { font-size: 0.92rem; font-weight: 600; margin: 0; color: var(--text-primary); }
  .pl-meta { font-size: 0.76rem; color: var(--text-tertiary); margin-top: 2px; display: flex; gap: 4px; flex-wrap: wrap; }
  .pl-have { color: var(--status-success, #22c55e); }
  .pl-missing { color: var(--status-warning, #f59e0b); }
  .pl-desc { font-size: 0.78rem; color: var(--text-secondary); margin: 4px 0 0; line-height: 1.4; }
  .pl-bar { height: 4px; background: var(--bg-tertiary); border-radius: 2px; margin: 10px 0 8px; overflow: hidden; }
  .pl-bar-fill { height: 100%; background: var(--accent-primary); border-radius: 2px; transition: width 0.3s; }
  .pl-actions { display: flex; gap: 6px; flex-wrap: wrap; }

  /* Text-Buttons für Playlist-Section (überschreibt Icon-only btn-sm) */
  .pl-toolbar .btn-sm,
  .pl-actions .btn-sm {
    width: auto; height: auto;
    padding: 7px 14px; font-size: 0.8rem; font-weight: 500;
    display: inline-flex; align-items: center; gap: 6px;
    color: var(--text-secondary);
  }
  .pl-toolbar .btn-primary,
  .pl-actions .btn-primary {
    background: var(--accent-primary); color: #fff; border-color: var(--accent-primary);
  }
  .pl-toolbar .btn-primary:hover:not(:disabled) { background: var(--accent-hover, var(--accent-primary)); border-color: var(--accent-hover, var(--accent-primary)); color: #fff; }
  .btn-accent { background: var(--accent-primary) !important; color: #fff !important; border-color: var(--accent-primary) !important; }
  .btn-accent:hover { opacity: 0.9; }
  /* ─── Suggest Toggle ─── */
  .meta-btn-suggest { background: none; border: 1px solid var(--border-primary); color: var(--text-secondary); padding: 2px 8px; border-radius: 6px; cursor: pointer; font-size: 0.75rem; transition: all 0.2s; }
  .meta-btn-suggest:hover { border-color: var(--accent-primary); color: var(--text-primary); }
  .meta-btn-suggest.excluded { text-decoration: line-through; opacity: 0.5; border-color: var(--status-warning); color: var(--status-warning); }
  .btn-suggest { background: none; border: 1px solid transparent; color: var(--text-muted); padding: 2px 4px; border-radius: 4px; cursor: pointer; font-size: 0.65rem; opacity: 0.4; transition: all 0.2s; }
  .btn-suggest:hover { opacity: 1; color: var(--text-secondary); }
  .btn-suggest.sg-exclude { opacity: 0.7; text-decoration: line-through; color: var(--status-warning); }
  .btn-suggest.sg-include { opacity: 0.9; color: var(--status-success); }

  /* ─── Medals ─── */
  .medal-box { text-align: center; }
  .medal-box .stat-val { font-size: 1.4rem; }
  .medal-gold { border-color: #fbbf24 !important; }
  .medal-silver { border-color: #9ca3af !important; }
  .medal-bronze { border-color: #d97706 !important; }
</style>

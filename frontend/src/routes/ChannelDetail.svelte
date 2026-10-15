<!--
  TubeVault - Kanalseite (Entwurf mockups/kanal.html, Freigabe 16.10.2026)
  Fester Kopf: Kanal mit Medaille und Aktionen, Reiter (Alle, Videos,
  Shorts, Live, Playlists, Diagnose), bei Listen die Filter Alle, Lokal und
  Nicht geladen, Sortierung, Titelfilter über den ganzen Kanal und das Laden
  fehlender Videos in Paketen. Darunter rollen Banner, Beschreibung,
  Kennzahlen und die gewählte Ansicht. "Einstellungen" öffnet dasselbe
  Seitenblatt wie die Kanalübersicht, über dieselben Aktionen (channelActions).
-->
<script>
  import { onDestroy, untrack } from 'svelte';
  import { api } from '../lib/api/client.js';
  import { settings } from '../lib/stores/settings.js';
  import { toast } from '../lib/stores/notifications.js';
  import { route, navigate } from '../lib/router/router.js';
  import { getFilter, saveFilters } from '../lib/stores/filterPersist.js';
  import { startQueue } from '../lib/stores/playlistQueue.js';
  import { infiniteScroll } from '../lib/utils/infiniteScroll.js';
  import { createListLoader } from '../lib/utils/listLoader.svelte.js';
  import { followJob } from '../lib/utils/followJob.js';
  import ActionMenu from '../lib/components/common/ActionMenu.svelte';
  import ConfirmDialog from '../lib/components/common/ConfirmDialog.svelte';
  import ChannelHead from '../lib/components/channel/ChannelHead.svelte';
  import ChannelOverview from '../lib/components/channel/ChannelOverview.svelte';
  import ChannelVideoRow from '../lib/components/channel/ChannelVideoRow.svelte';
  import ChannelPlaylists from '../lib/components/channel/ChannelPlaylists.svelte';
  import ChannelDiagnosis from '../lib/components/channel/ChannelDiagnosis.svelte';
  import ChannelSettingsSheet from '../lib/components/channel/ChannelSettingsSheet.svelte';
  import { createChannelActions } from '../lib/components/channel/channelActions.js';
  import { channelName, num } from '../lib/components/channel/channelView.js';

  const SORTS = [['newest', 'Neueste zuerst'], ['oldest', 'Älteste zuerst'], ['popular', 'Meiste Aufrufe'],
                 ['longest', 'Längste'], ['shortest', 'Kürzeste']];
  const SOURCES = [['all', 'Alle'], ['downloaded', 'Lokal'], ['missing', 'Nicht geladen']];
  const LOAD_STEPS = [5, 10, 20, 50];
  const LOAD_ALL_UP_TO = 50;           // bis dahin gibt es "Alle N laden"
  const FILTER_DELAY_MS = 300;
  const watchUrl = (id) => `https://www.youtube.com/watch?v=${id}`;

  let channel = $state(null);
  let loading = $state(true);
  let tab = $state('all');             // all | video | short | live | playlists | diagnose
  let source = $state('all');
  let sortBy = $state(getFilter('channelDetail', 'sortBy', 'newest'));
  let query = $state('');
  let sourceCounts = $state({ all: 0, downloaded: 0, missing: 0 });
  let loadable = $state(0);            // fehlende Videos des Reiters, die sich laden lassen
  let queueing = $state(false);
  let downloading = $state({});
  let playlists = $state({ playlists: [], local_playlists: [] });
  let scan = $state({ running: false, label: '', jobId: null });
  let sheetOpen = $state(false);
  let subscribing = $state(false);
  let checking = $state({});
  let menu, confirmRef, filterTimer, stopScan;

  let channelId = $derived($route.id);
  let videoType = $derived(['video', 'short', 'live'].includes(tab) ? tab : 'all');
  let listView = $derived(tab !== 'playlists' && tab !== 'diagnose');
  let playlistCount = $derived(playlists.playlists.length + playlists.local_playlists
    .filter((lp) => !playlists.playlists.some((pl) => pl.local_playlist_id === lp.id)).length);
  let tabs = $derived.by(() => {
    if (!channel) return [];
    const types = channel.type_counts || {};
    const shown = [['all', 'Alle', channel.rss_entry_count, 'fa-layer-group']];
    if (types.video) shown.push(['video', 'Videos', types.video, 'fa-video']);
    if (types.short && $settings['shorts.exclude'] !== 'true') shown.push(['short', 'Shorts', types.short, 'fa-mobile-screen']);
    if (types.live) shown.push(['live', 'Live', types.live, 'fa-tower-broadcast']);
    shown.push(['playlists', 'Playlists', playlistCount, 'fa-list-ul']);
    if (channel.subscribed) shown.push(['diagnose', 'Diagnose', null, 'fa-stethoscope']);
    return shown;
  });
  let loadSteps = $derived(LOAD_STEPS.filter((n) => n < loadable));

  const list = createListLoader(async (page) => {
    try {
      const result = await api.getChannelVideos(channelId, source, page, videoType, sortBy, query.trim());
      if (result.source_counts) sourceCounts = result.source_counts;
      return { items: result.videos || [], total: result.total || 0 };
    } catch (e) { toast.error(e.message); return { items: [], total: 0 }; }
  }, { keyOf: (video) => video.video_id });

  // Gemeinsame Aktionen mit der Kanalübersicht; "Ganz scannen" verfolgt diese Seite selbst
  const actions = createChannelActions({
    patch: (sub, changes) => { channel = { ...channel, ...changes }; },
    reload: () => refresh(),
    confirm: (...args) => confirmRef.ask(...args),
    removed: () => navigate('/subscriptions'),
    checking,
  });
  const sheetActions = { ...actions, scanFully: () => startScan() };

  // ── Laden ──

  async function open(id) {
    stopScan?.();
    scan = { running: false, label: '', jobId: null };
    tab = 'all'; source = 'all'; query = ''; sheetOpen = false;
    loading = true;
    try {
      channel = await api.getChannelDetail(id);
    } catch (e) {
      toast.error(e.message);
      navigate('/subscriptions');
      return;
    }
    loading = false;
    list.load(true);
    loadPlaylists();
    loadLoadable();
  }

  /** Nach Änderungen: Kanal, Liste und Lücke neu, ohne die Ansicht zu wechseln. */
  async function refresh() {
    try { channel = await api.getChannelDetail(channelId); } catch { /* bleibt beim alten Stand */ }
    if (listView) { list.load(true); loadLoadable(); }
    loadPlaylists();
  }

  async function loadPlaylists() {
    try {
      const result = await api.getChannelPlaylists(channelId);
      playlists = { playlists: result.playlists || [], local_playlists: result.local_playlists || [] };
    } catch { playlists = { playlists: [], local_playlists: [] }; }
  }

  async function loadLoadable() {
    try { loadable = (await api.getMissingVideos(channelId, 1, videoType)).total_missing || 0; }
    catch { loadable = 0; }
  }

  // Nur der Kanal (Adresse) löst das Laden aus - nie Filter oder Zustand, den open() selbst schreibt
  $effect(() => {
    const id = channelId;
    if (id) untrack(() => open(id));
  });
  onDestroy(() => { stopScan?.(); actions.dispose(); clearTimeout(filterTimer); });

  // ── Ansicht ──

  function changeTab(next) {
    if (tab === next) return;
    tab = next;
    if (listView) { list.load(true); loadLoadable(); }
  }
  function changeSource(next) { source = next; list.load(true); }
  function changeSort(next) { sortBy = next; saveFilters('channelDetail', { sortBy: next }); list.load(true); }
  function changeQuery(next) {
    query = next;
    clearTimeout(filterTimer);
    filterTimer = setTimeout(() => list.load(true), FILTER_DELAY_MS);
  }

  // ── Videos ──

  function play(video) {
    // Warteschlange aus den geladenen lokalen Videos der Liste (Weiter/Zurück im Spieler)
    const queue = list.items.filter((v) => v.is_downloaded)
      .map((v) => ({ id: v.video_id, title: v.title || v.video_id, channel_name: channelName(channel), duration: v.duration || 0 }));
    const index = queue.findIndex((v) => v.id === video.video_id);
    if (queue.length > 1) startQueue(null, channelName(channel), queue, Math.max(0, index));
    navigate(`/watch/${video.video_id}`);
  }

  async function download(video) {
    if (downloading[video.video_id]) return;
    downloading[video.video_id] = true;
    try {
      await api.addDownload({ url: watchUrl(video.video_id) });   // Qualität: Kanal bzw. Einstellungen
      list.items = list.items.map((v) => (v.video_id === video.video_id ? { ...v, is_in_queue: 1 } : v));
      loadable = Math.max(0, loadable - 1);
      toast.success(`"${video.title || video.video_id}" in die Warteschlange`);
    } catch (e) { toast.error(e.message); }
    delete downloading[video.video_id];
  }

  async function queueMissing(count) {
    queueing = true;
    const queued = await actions.queueMissing(channel, count, videoType);
    queueing = false;
    if (queued) { list.load(true); loadLoadable(); }
  }

  async function setSuggest(video, override) {
    try {
      await api.updateVideoSuggest(video.video_id, override);
      const value = override === 'reset' ? null : override;
      list.items = list.items.map((v) => (v.video_id === video.video_id ? { ...v, suggest_override: value } : v));
    } catch (e) { toast.error(e.message); }
  }

  function videoMenu(event, video) {
    const current = video.suggest_override || 'reset';
    const suggest = [['reset', 'Wie der Kanal'], ['exclude', 'Nie vorschlagen'], ['include', 'Immer vorschlagen']]
      .map(([value, label]) => ({ icon: 'fa-dice', label, hint: value === current ? 'gewählt' : '', run: () => setSuggest(video, value) }));
    menu.open(event, video.title || video.video_id, [
      ...(video.is_downloaded ? [{ icon: 'fa-dice', label: 'Zufallsvorschläge', items: suggest }] : []),
      ...(!video.is_downloaded && !video.is_in_queue ? [{ icon: 'fa-download', label: 'Herunterladen', run: () => download(video) }] : []),
      { icon: 'fa-arrow-up-right-from-square', label: 'Bei der Quelle öffnen', run: () => window.open(watchUrl(video.video_id), '_blank', 'noopener') },
    ]);
  }

  // ── Kanal ──

  async function startScan() {
    if (scan.running) return;
    scan = { running: true, label: 'Wartet auf freien Platz', jobId: null };
    try {
      const { job_id: jobId } = await api.fetchAllChannelVideos(channelId);
      scan.jobId = jobId;
      stopScan = followJob(jobId, {
        onUpdate: (job) => { scan.label = job.status === 'queued' ? 'Wartet auf freien Platz' : (job.description || 'Scannt'); },
        onEnd: (job) => {
          scan = { running: false, label: '', jobId: null };
          refresh();
          if (job?.status === 'done') toast.success(`Scan abgeschlossen${job.result ? `: ${job.result}` : ''}`);
          else if (job?.status === 'cancelled') toast.info(job.result || 'Scan abgebrochen');
          else if (job) toast.error(job.error_message || 'Scan fehlgeschlagen');
        },
      });
    } catch (e) {
      toast.error(e.message);
      scan = { running: false, label: '', jobId: null };
    }
  }

  async function cancelScan() {
    if (!scan.jobId) return;
    try { await api.cancelJob(scan.jobId); scan.label = 'Wird abgebrochen'; }
    catch (e) { toast.error(e.message); }
  }

  async function unlock() {
    try {
      await api.resetChannelError(channelId);
      channel = { ...channel, error_count: 0, last_error: null, enabled: 1 };
      toast.success(`${channelName(channel)}: Prüfung wieder an`);
    } catch (e) { toast.error(e.message); }
  }

  async function subscribe() {
    subscribing = true;
    try {
      await api.addSubscription({ channel_id: channel.channel_id, channel_name: channel.channel_name });
      toast.success(`"${channelName(channel)}" abonniert`);
      await open(channelId);
    } catch (e) { toast.error(e.message); }
    subscribing = false;
  }
</script>

<div class="tv-seite kanalseite">
  {#if loading}
    <div class="tv-rollfeld" data-scroll-root><div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt Kanal ...</div></div>
  {:else if channel}
    <div class="tv-seitenkopf">
      <ChannelHead {channel} {scan} {subscribing} onscan={startScan} oncancel={cancelScan}
                   onsettings={() => sheetOpen = true} onsubscribe={subscribe} onunlock={unlock} />
      <div class="tv-reiter reiter">
        {#each tabs as [key, label, count, icon] (key)}
          <button class:aktiv={tab === key} onclick={() => changeTab(key)}>
            <i class="fa-solid {icon}"></i> {label}{#if count != null} <span class="tv-zaehler">{num(count)}</span>{/if}</button>
        {/each}
      </div>
      {#if listView}
        <div class="steuer">
          {#each SOURCES as [key, label] (key)}
            <button class="tv-chip" class:aktiv={source === key} onclick={() => changeSource(key)}>
              {label} <span class="tv-zaehler">{num(sourceCounts[key])}</span></button>
          {/each}
          <div class="rechts">
            <select class="tv-eingabe" value={sortBy} onchange={(e) => changeSort(e.currentTarget.value)} aria-label="Sortierung">
              {#each SORTS as [key, label] (key)}<option value={key}>{label}</option>{/each}
            </select>
            <span class="filterfeld">
              <input class="tv-eingabe" placeholder="In diesem Kanal filtern" value={query}
                     oninput={(e) => changeQuery(e.currentTarget.value)} aria-label="Titel filtern" />
              {#if query}<button class="tv-knopf ohne symbol klein leeren" onclick={() => changeQuery('')} title="Filter leeren" aria-label="Filter leeren">
                <i class="fa-solid fa-xmark"></i></button>{/if}
            </span>
          </div>
        </div>
        {#if loadable > 0}
          <div class="luecke">
            <i class="fa-solid fa-cloud-arrow-down"></i>
            <span><span class="zahl">{num(loadable)}</span> {loadable === 1 ? 'Video lässt' : 'Videos lassen'} sich noch laden</span>
            <div class="rechts">Laden:
              {#each loadSteps as n (n)}
                <button class="tv-knopf klein" onclick={() => queueMissing(n)} disabled={queueing} title="Die nächsten {n} in die Warteschlange">{n}</button>
              {/each}
              {#if loadable <= LOAD_ALL_UP_TO}
                <button class="tv-knopf klein" onclick={() => queueMissing(loadable)} disabled={queueing}>Alle {num(loadable)}</button>
              {/if}
            </div>
          </div>
        {/if}
      {/if}
    </div>

    <div class="tv-rollfeld" data-scroll-root>
      {#if tab === 'playlists'}
        <ChannelPlaylists {channelId} playlists={playlists.playlists} localPlaylists={playlists.local_playlists} onreload={loadPlaylists} />
      {:else if tab === 'diagnose'}
        <ChannelDiagnosis {channelId} />
      {:else}
        <ChannelOverview {channel} {playlistCount} />
        {#if list.items.length}
          <div class="zeilen">
            {#each list.items as video (video.video_id)}
              <ChannelVideoRow {video} {channel} loading={!!downloading[video.video_id]}
                               onplay={play} onload={download} onmore={videoMenu} />
            {/each}
          </div>
          <div use:infiniteScroll={{ onLoadMore: list.loadMore, canLoad: list.canLoad }}></div>
          {#if list.loadingMore}<div class="tv-leer klein"><i class="fa-solid fa-spinner fa-spin"></i> Lädt weitere ...</div>{/if}
        {:else if list.loading}
          <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt Videos ...</div>
        {:else if channel.needs_scan && channel.subscribed && !query}
          <div class="tv-leer">
            <p>Dieser Kanal ist noch nicht ganz gescannt: bekannt sind nur die neuesten Videos.</p>
            <button class="tv-knopf haupt" onclick={startScan} disabled={scan.running}><i class="fa-solid fa-satellite-dish"></i> Ganz scannen</button>
          </div>
        {:else}
          <div class="tv-leer">{query ? `Kein Titel mit "${query}" in dieser Ansicht.` : 'Keine Videos in dieser Ansicht.'}</div>
        {/if}
      {/if}
    </div>

    {#if sheetOpen && channel.subscribed}
      <ChannelSettingsSheet sub={channel} actions={sheetActions} checking={!!checking[channel.id]} onClose={() => sheetOpen = false} />
    {/if}
  {/if}
</div>

<ActionMenu bind:this={menu} />
<ConfirmDialog bind:this={confirmRef} />

<style>
  .kanalseite { position: relative; }   /* Bezug für das Seitenblatt */
  .reiter { margin-bottom: var(--tv-a3); }
  .steuer { display: flex; flex-wrap: wrap; align-items: center; gap: var(--tv-a2); }
  .steuer .rechts { margin-left: auto; display: flex; flex-wrap: wrap; gap: var(--tv-a2); align-items: center; }
  .steuer select { width: 180px; }
  .filterfeld { position: relative; display: inline-flex; }
  .filterfeld .tv-eingabe { width: 260px; padding-right: 40px; }
  .filterfeld .leeren { position: absolute; right: 3px; top: 3px; }
  .luecke { display: flex; flex-wrap: wrap; align-items: center; gap: var(--tv-a3); margin-top: var(--tv-a3);
            padding: var(--tv-a2) var(--tv-a2) var(--tv-a2) var(--tv-a4); border-radius: var(--tv-ecke);
            background: var(--tv-flaeche); font-size: var(--tv-gr-klein); color: var(--tv-text-2); }
  .luecke > i { color: var(--tv-text-3); }
  .luecke .zahl { color: var(--tv-text); font-weight: 600; }
  .luecke .rechts { margin-left: auto; display: flex; flex-wrap: wrap; gap: var(--tv-a2); align-items: center; }
  .zeilen { display: flex; flex-direction: column; gap: 2px; }
  .tv-leer.klein { padding: var(--tv-a4); }
  .tv-leer p { margin: 0 0 var(--tv-a3); }

  @media (max-width: 700px) {
    .steuer .rechts, .filterfeld, .filterfeld .tv-eingabe { width: 100%; }
    .steuer select { flex: 1; }
  }
</style>

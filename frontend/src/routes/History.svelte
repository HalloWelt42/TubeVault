<!--
  Verlauf (Entwurf mockups/verlauf.html): im festen Kopf Pausieren, Verlauf
  leeren (mit Bestätigung auf der Seite) und Weiterschauen, Steuerleiste mit
  Suche, Stand, Zeitraum sowie Art und Kanal. Im Rollfeld die angefangenen
  Videos als Kartenreihe, darunter die Einträge nach Tagen mit Uhrzeit und
  Stand, seitenweise nachgeladen. Menü je Eintrag, Auswahl mit
  Stapelaktionen, Entfernen mit Rückgängig.
-->
<script>
  import { onMount } from 'svelte';
  import { get } from 'svelte/store';
  import { api } from '../lib/api/client.js';
  import { route, navigate, updateParams } from '../lib/router/router.js';
  import { toast } from '../lib/stores/notifications.js';
  import { playlistQueue } from '../lib/stores/playlistQueue.js';
  import { getSettingBool, getSettingNum, reloadSettings } from '../lib/stores/settings.js';
  import { formatDuration, parseServerTime } from '../lib/utils/format.js';
  import { groupByDay, sinceOf } from '../lib/utils/collection.js';
  import { playCollection, playAfterCurrent } from '../lib/utils/collectionPlay.js';
  import { onVideoMutation } from '../lib/utils/videoMutations.js';
  import { infiniteScroll } from '../lib/utils/infiniteScroll.js';
  import { createListLoader } from '../lib/utils/listLoader.svelte.js';
  import PageHeader from '../lib/components/common/PageHeader.svelte';
  import BatchToolbar from '../lib/components/common/BatchToolbar.svelte';
  import ActionMenu from '../lib/components/common/ActionMenu.svelte';
  import { musicMenuItem } from '../lib/utils/videoMusic.js';
  import MultiFilter from '../lib/components/common/MultiFilter.svelte';
  import CollectionBar from '../lib/components/collection/CollectionBar.svelte';
  import VideoRow from '../lib/components/collection/VideoRow.svelte';

  const TITLE = 'Verlauf';
  const PAUSED_KEY = 'history.paused';
  const SERVER_PAGE_MAX = 100;        // mehr liefert der Server je Seite nicht
  const CONTINUE_CARDS = 4;           // Karten in der Reihe "Weiterschauen"
  const SEARCH_DELAY_MS = 300;
  const CLEAR_OLDER_DAYS = 30;
  const PERIODS = [
    { key: 'heute', label: 'Heute' }, { key: '7', label: '7 Tage' },
    { key: '30', label: '30 Tage' }, { key: '', label: 'Alles' },
  ];

  // Filter (Art und Kanal kommen aus MultiFilter als kommagetrennte Listen).
  // Art, Kanal und Suche stehen auch in der Adresse und gelten beim Öffnen.
  const startParams = get(route).params || {};
  let search = $state(startParams.search || '');
  let stateFilter = $state('');       // '' | 'started' | 'finished'
  let period = $state('');            // '' | 'heute' | '7' | '30'
  let types = $state(startParams.types || null);
  let channels = $state(startParams.channels || null);
  let moreFilters = $state(!!(startParams.types || startParams.channels));   // Zeile für Art und Kanal offen

  // Gesamtstand ohne Filter: Kennzahlen im Kopf und die Reihe "Weiterschauen"
  let overview = $state(null);        // { total, started, cards }
  let paused = $state(getSettingBool(PAUSED_KEY));
  let pausing = $state(false);
  let asking = $state(false);         // Bestätigung "Verlauf leeren" sichtbar
  let clearing = $state(false);
  let selecting = $state(false);
  let selected = $state(new Set());
  let playlists = null;
  let menu;
  let searchTimer;

  // Seitenweise laden; die Seitenzahl hält der Loader bewusst nicht reaktiv
  const list = createListLoader(async (page) => {
    try {
      const res = await api.getHistory(historyParams(page));
      return { items: res.videos || [], total: res.total || 0 };
    } catch (e) {
      toast.error(`Verlauf konnte nicht geladen werden: ${e.message}`);
      return { items: [], total: 0 };
    }
  });

  let extraCount = $derived(countOf(types) + countOf(channels));
  let filtered = $derived(!!(search.trim() || stateFilter || period || extraCount));
  let groups = $derived(groupByDay(list.items, (item) => item.last_watched));
  let queueActive = $derived($playlistQueue.active);
  let showContinue = $derived(!filtered && !selecting && overview?.cards.length > 0);
  let hasHistory = $derived(overview === null || overview.total > 0);
  let showBar = $derived(hasHistory || filtered);
  let states = $derived([
    { key: '', label: 'Alle' },
    { key: 'started', label: 'Angefangen', count: overview?.started ?? 0 },
    { key: 'finished', label: 'Zu Ende gesehen' },
  ]);
  let info = $derived(overview ? [
    filtered && !list.loading ? `${number(list.total)} von ${videos(overview.total)}` : videos(overview.total),
    overview.started ? `${number(overview.started)} angefangen` : null,
  ].filter(Boolean).join(' · ') : null);
  let selectedItems = $derived(list.items.filter((item) => selected.has(item.id)));
  let selectedIds = $derived(selectedItems.map((item) => item.id));

  // ── Hilfen ──
  function countOf(csv) { return csv ? csv.split(',').filter(Boolean).length : 0; }
  function number(n) { return (n || 0).toLocaleString('de-DE'); }
  function videos(n) { return `${number(n)} ${n === 1 ? 'Video' : 'Videos'}`; }
  function clock(value) {
    return parseServerTime(value).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
  }
  function shortTitle(item) { return item.title?.length > 50 ? `${item.title.slice(0, 50)} ...` : item.title; }

  function historyParams(page) {
    const params = { page, per_page: Math.min(SERVER_PAGE_MAX, getSettingNum('general.videos_per_page', 24)) };
    if (search.trim()) params.search = search.trim();
    if (stateFilter) params.state = stateFilter;
    if (period) params.since = sinceOf(period);
    if (types) params.video_types = types;
    if (channels) params.channel_ids = channels;
    return params;
  }

  // ── Laden ──
  async function loadOverview() {
    try {
      const [all, started] = await Promise.all([
        api.getHistory({ page: 1, per_page: 1 }),
        api.getHistory({ page: 1, per_page: CONTINUE_CARDS, state: 'started' }),
      ]);
      overview = { total: all.total || 0, started: started.total || 0, cards: started.videos || [] };
    } catch { /* Kopf behält den letzten Stand; die Liste meldet den Fehler */ }
  }

  function refresh() {
    list.load(true);
    loadOverview();
  }

  // Ein Filterwechsel lädt ausdrücklich neu und merkt Art, Kanal und Suche in der Adresse
  function applyFilters() {
    clearTimeout(searchTimer);
    updateParams({ types, channels, search: search.trim() || null });
    list.load(true);
  }

  function setSearch(value) {
    search = value;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(applyFilters, SEARCH_DELAY_MS);
  }
  function setState(value) { stateFilter = value; applyFilters(); }
  function choosePeriod(key) { period = key; applyFilters(); }
  function onExtraFilter(f) { types = f.types; channels = f.channels; applyFilters(); }

  // ── Abspielen ──
  const play = (item, resume) => playCollection(null, TITLE, [item], 0, { resume });
  const playItem = (item) => play(item, item.state === 'started');
  const playFromStart = (item) => play(item, false);
  const playCard = (index) => playCollection(null, 'Weiterschauen', overview.cards, index, { resume: true });

  // Alle angefangenen als Reihe, jedes an seiner gemerkten Stelle
  async function continueWatching() {
    try {
      const res = await api.getHistory({ page: 1, per_page: SERVER_PAGE_MAX, state: 'started' });
      playCollection(null, 'Weiterschauen', res.videos || [], 0, { resume: true });
    } catch (e) { toast.error(e.message); }
  }

  // ── Ändern ──
  async function removeItems(items) {
    const undo = [];
    for (const item of items) {
      try {
        const res = await api.removeFromHistory(item.id);
        undo.push({ id: item.id, entries: res.entries || [] });
      } catch (e) { toast.error(e.message); }
    }
    if (!undo.length) return;
    const gone = new Set(undo.map((u) => u.id));
    list.items = list.items.filter((item) => !gone.has(item.id));
    list.total = Math.max(0, list.total - gone.size);
    selected = new Set();
    loadOverview();
    toast.undo(undo.length === 1 ? `"${shortTitle(items[0])}" aus dem Verlauf entfernt` : `${undo.length} Videos aus dem Verlauf entfernt`,
      async () => {
        for (const u of undo) await api.restoreHistory(u.id, u.entries).catch(() => {});
        refresh();
      });
  }

  // Stand am Platz anpassen wie der Server (Stelle ans Ende bzw. auf den
  // Anfang), damit die nachgeladenen Seiten und die Rollstelle bleiben
  async function setWatched(ids, watched) {
    try { await api.setWatched(ids, watched); } catch (e) { toast.error(e.message); return; }
    const changed = new Set(ids);
    const updated = list.items.map((item) => (changed.has(item.id)
      ? { ...item, position: watched ? item.duration || 0 : 0, progress: watched ? 1 : 0, state: watched ? 'finished' : 'new' }
      : item));
    const kept = stateFilter ? updated.filter((item) => item.state === stateFilter) : updated;
    list.total = Math.max(0, list.total - (updated.length - kept.length));
    list.items = kept;
    selected = new Set();
    loadOverview();
  }

  async function addFavorite(item) {
    try {
      await api.addFavorite({ video_id: item.id, list_name: 'Standard' });
      toast.success('Zu den Favoriten hinzugefügt');
    } catch (e) { toast.error(e.message); }
  }

  async function addToPlaylist(ids, pl) {
    let added = 0;
    for (const id of ids) {
      try { await api.addToPlaylist(pl.id, id); added++; } catch { /* schon drin */ }
    }
    toast.success(`${added} zu "${pl.name}" hinzugefügt`);
  }

  async function clearHistory(olderThanDays = null) {
    clearing = true;
    try {
      const res = await api.clearHistory(olderThanDays);
      if (!olderThanDays) toast.success('Verlauf geleert');
      else if (res.removed) toast.success(`Einträge älter als ${olderThanDays} Tage entfernt`);
      else toast.info(`Keine Einträge älter als ${olderThanDays} Tage`);
      asking = false;
      refresh();
    } catch (e) { toast.error(e.message); }
    finally { clearing = false; }
  }

  async function togglePaused() {
    pausing = true;
    try {
      await api.updateSetting(PAUSED_KEY, paused ? 'false' : 'true');
      await reloadSettings();
      paused = getSettingBool(PAUSED_KEY);
      toast.info(paused ? 'Verlauf pausiert - Angesehenes wird nicht mitgeschrieben' : 'Verlauf wird wieder mitgeschrieben');
    } catch (e) { toast.error(e.message); }
    finally { pausing = false; }
  }

  // ── Menüs ──
  async function playlistItems(ids) {
    playlists ??= await api.getPlaylists().catch(() => []);
    return playlists.map((pl) => ({ icon: 'fa-list-ul', label: pl.name, hint: String(pl.video_count ?? ''), run: () => addToPlaylist(ids, pl) }));
  }

  async function openMenu(event, item) {
    const ids = [item.id];
    const started = item.state === 'started';
    menu.open(event, item.title, [
      started
        ? { icon: 'fa-play', label: `Weiterschauen bei ${formatDuration(item.position)}`, run: () => play(item, true) }
        : { icon: 'fa-rotate-right', label: 'Nochmal ansehen', run: () => playFromStart(item) },
      ...(started ? [{ icon: 'fa-backward-step', label: 'Von vorn', run: () => playFromStart(item) }] : []),
      ...(queueActive ? [{ icon: 'fa-forward', label: 'Als Nächstes', run: () => playAfterCurrent(item) }] : []),
      { icon: 'fa-heart', label: 'Zu den Favoriten', run: () => addFavorite(item) },
      { icon: 'fa-list-ul', label: 'Zur Playlist hinzufügen', items: await playlistItems(ids) },
      ...(item.channel_id ? [{ icon: 'fa-tv', label: 'Zum Kanal', run: () => navigate(`/channel/${item.channel_id}`) }] : []),
      { trenner: true },
      ...(item.state !== 'finished' ? [{ icon: 'fa-check', label: 'Als gesehen markieren', run: () => setWatched(ids, true) }] : []),
      ...(started ? [{ icon: 'fa-eraser', label: 'Gemerkte Stelle vergessen', run: () => setWatched(ids, false) }] : []),
      ...(item.state === 'finished' ? [{ icon: 'fa-eye-slash', label: 'Als neu markieren', run: () => setWatched(ids, false) }] : []),
      musicMenuItem(item, (isMusic) => { item.is_music = isMusic; }),
      { icon: 'fa-xmark', label: 'Aus dem Verlauf entfernen', danger: true, run: () => removeItems([item]) },
    ]);
  }

  // ── Auswahl ──
  function toggle(item) {
    const next = new Set(selected);
    next.has(item.id) ? next.delete(item.id) : next.add(item.id);
    selected = next;
  }
  function startSelecting() { selecting = true; asking = false; }
  function stopSelecting() { selecting = false; selected = new Set(); }

  // Laden nur beim Öffnen und ausdrücklich bei Filterwechsel - ein $effect
  // würde sich über den Zustand, den der Loader schreibt, selbst neu auslösen
  onMount(() => {
    refresh();
    const stopListening = onVideoMutation(() => refresh());
    return () => { stopListening(); clearTimeout(searchTimer); };
  });
</script>

<div class="tv-seite">
  <div class="tv-seitenkopf">
    <PageHeader title={TITLE} icon="fa-solid fa-clock-rotate-left" {info}>
      <button class="tv-knopf" class:aktiv={paused} onclick={togglePaused} disabled={pausing}
              title={paused ? 'Der Verlauf wird gerade nicht mitgeschrieben - antippen zum Fortsetzen' : 'Verlauf vorübergehend nicht mitschreiben'}>
        <i class="fa-solid fa-pause"></i> {paused ? 'Pausiert' : 'Pausieren'}</button>
      {#if overview?.total}
        <button class="tv-knopf ohne gefahr" onclick={() => { asking = true; stopSelecting(); }}>
          <i class="fa-solid fa-trash-can"></i> Verlauf leeren</button>
      {/if}
      {#if overview?.started}
        <button class="tv-knopf haupt" onclick={continueWatching} title="Die angefangenen Videos nacheinander, jedes an der gemerkten Stelle">
          <i class="fa-solid fa-rotate-left"></i> Weiterschauen</button>
      {/if}
    </PageHeader>

    {#if selecting}
      <BatchToolbar selectedCount={selectedIds.length} totalCount={list.items.length}
                    onSelectAll={() => selected = new Set(list.items.map((item) => item.id))} onDone={stopSelecting}>
        <button class="tv-knopf klein" onclick={async (e) => menu.open(e, 'Zur Playlist', await playlistItems(selectedIds))}>
          <i class="fa-solid fa-list-ul"></i> Zur Playlist</button>
        <button class="tv-knopf klein" onclick={() => setWatched(selectedIds, true)}><i class="fa-solid fa-check"></i> Als gesehen</button>
        <button class="tv-knopf klein" onclick={() => setWatched(selectedIds, false)}><i class="fa-solid fa-eye-slash"></i> Als neu</button>
        <button class="tv-knopf klein gefahr" onclick={() => removeItems(selectedItems)}><i class="fa-solid fa-xmark"></i> Aus dem Verlauf entfernen</button>
      </BatchToolbar>
    {:else if showBar}
      <CollectionBar bind:search={() => search, setSearch} placeholder="Im Verlauf suchen"
                     {states} bind:state={() => stateFilter, setState} onSelect={startSelecting}>
        <span class="tv-trenner"></span>
        <span class="tv-etikett">Zeitraum</span>
        {#each PERIODS as option (option.key)}
          <button class="tv-chip" class:aktiv={period === option.key} onclick={() => choosePeriod(option.key)}>{option.label}</button>
        {/each}
        {#snippet rechts()}
          <button class="tv-knopf klein" class:aktiv={moreFilters || extraCount > 0} onclick={() => moreFilters = !moreFilters}
                  title="Nach Art (Videos, Live) und Kanal filtern">
            <i class="fa-solid fa-filter"></i> Art und Kanal
            {#if extraCount}<span class="tv-zaehler akzent">{extraCount}</span>{/if}
          </button>
        {/snippet}
      </CollectionBar>
    {/if}
    <!-- Bleibt eingehängt und wird nur verborgen: die gewählten Werte stecken in MultiFilter -->
    {#if showBar}
      <div class="mehr-filter" hidden={selecting || !moreFilters}>
        <MultiFilter showSearch={false} showTypes={true} showChannels={true} showCategories={false}
                     initial={{ types, channels }} onchange={onExtraFilter} />
      </div>
    {/if}

    {#if asking}
      <div class="bestaetigen" role="alertdialog" aria-label="Verlauf leeren">
        <i class="fa-solid fa-triangle-exclamation"></i>
        <span>Den ganzen Verlauf (<span class="zahl">{number(overview?.total)}</span> Einträge) leeren? Gemerkte Stellen zum Weiterschauen bleiben erhalten.</span>
        <div class="rechts">
          <button class="tv-knopf klein" disabled={clearing} onclick={() => clearHistory(CLEAR_OLDER_DAYS)}>Nur älter als {CLEAR_OLDER_DAYS} Tage</button>
          <button class="tv-knopf klein voll" disabled={clearing} onclick={() => clearHistory()}>Alles leeren</button>
          <button class="tv-knopf klein ohne" onclick={() => asking = false}>Abbrechen</button>
        </div>
      </div>
    {/if}
  </div>

  <div class="tv-rollfeld" data-scroll-root>
    {#if list.loading && !list.items.length}
      <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt ...</div>
    {:else if !list.items.length && !filtered}
      <div class="leer-gross">
        <i class="fa-solid fa-clock-rotate-left"></i>
        <h2>Der Verlauf ist leer</h2>
        <p>Was du ansiehst, erscheint hier nach Tagen geordnet - mit der Stelle, an der du aufgehört hast.</p>
      </div>
    {:else if !list.items.length}
      <div class="tv-leer">Nichts gefunden.</div>
    {:else}
      {#if showContinue}
        <div class="tag-kopf">
          <h2>Weiterschauen</h2><span class="zahl">{number(overview.started)} angefangen</span>
          {#if overview.started > overview.cards.length}
            <button class="tv-knopf klein ohne alle" onclick={() => setState('started')}>
              Alle <span class="zahl">{number(overview.started)}</span> zeigen</button>
          {/if}
        </div>
        <div class="weiter-reihe">
          {#each overview.cards as card, index (card.id)}
            <button class="weiter-karte" onclick={() => playCard(index)} title="An der gemerkten Stelle weiterschauen">
              <span class="vbild">
                <img src={api.thumbnailUrl(card.id)} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
                <span class="fort"><b style:width="{Math.min(100, card.progress * 100)}%"></b></span>
                <span class="rest zahl">noch {formatDuration(Math.max(0, (card.duration || 0) - (card.position || 0)))}</span>
                <span class="los"><i class="fa-solid fa-circle-play"></i></span>
              </span>
              <span class="vtitel">{card.title}</span>
              <span class="vmeta">{card.channel_name || ''}</span>
            </button>
          {/each}
        </div>
      {/if}

      {#each groups as group (group.label)}
        <div class="tag-kopf">
          <h2>{group.label}</h2><span class="zahl">{videos(group.items.length)}</span>
        </div>
        <div class="zeilen" role="list">
          {#each group.items as item (item.id)}
            <VideoRow {item} time={clock(item.last_watched)} showPosition
                      mode={selecting ? 'auswahl' : null} selected={selected.has(item.id)}
                      onPlay={playItem} onNext={queueActive ? playAfterCurrent : null}
                      onRemove={(row) => removeItems([row])} removeTitle="Aus dem Verlauf entfernen"
                      onMenu={openMenu} onToggle={toggle} />
          {/each}
        </div>
      {/each}

      <div class="nachlade-marke" use:infiniteScroll={{ onLoadMore: list.loadMore, canLoad: list.canLoad }}></div>
      {#if list.loadingMore}<div class="tv-leer nachladen"><i class="fa-solid fa-spinner fa-spin"></i> Lädt weitere ...</div>{/if}
    {/if}
  </div>
</div>

<ActionMenu bind:this={menu} />

<style>
  .mehr-filter { margin-top: var(--tv-a3); }
  .mehr-filter :global(.multi-filter) { margin-bottom: var(--tv-a2); }

  /* Bestätigung "Verlauf leeren" direkt auf der Seite */
  .bestaetigen { display: flex; align-items: center; gap: var(--tv-a3); flex-wrap: wrap; margin-top: var(--tv-a3);
                 padding: var(--tv-a3) var(--tv-a4); background: rgba(var(--tv-gefahr-rgb), 0.08);
                 border: 1px solid rgba(var(--tv-gefahr-rgb), 0.4); border-radius: var(--tv-ecke); }
  .bestaetigen > i { color: var(--tv-gefahr); }
  .bestaetigen > span { flex: 1 1 320px; min-width: 0; }
  .bestaetigen .rechts { margin-left: auto; display: flex; gap: var(--tv-a2); flex-wrap: wrap; }
  .tv-knopf.voll { background: var(--tv-gefahr); color: var(--tv-akzent-text); border-color: transparent; }
  .tv-knopf.voll:hover:not(:disabled) { background: var(--tv-gefahr); opacity: 0.88; }

  /* Abschnitte im Rollfeld: Weiterschauen und je Tag */
  .tag-kopf { display: flex; align-items: baseline; gap: var(--tv-a3); margin: var(--tv-a5) 0 var(--tv-a2); }
  .tag-kopf:first-child { margin-top: var(--tv-a2); }
  .tag-kopf h2 { margin: 0; font-size: var(--tv-gr-titel); }
  .tag-kopf > .zahl { color: var(--tv-text-3); font-size: var(--tv-gr-klein); }
  .tag-kopf .alle { margin-left: auto; align-self: center; }
  .zeilen { display: flex; flex-direction: column; gap: 2px; }

  /* Weiterschauen: eine Reihe Karten, nie seitlich rollend */
  .weiter-reihe { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--tv-a4); }
  .weiter-karte { display: block; min-width: 0; padding: 0; border: 0; background: none; color: var(--tv-text);
                  font: inherit; text-align: left; cursor: pointer; }
  .weiter-karte .vbild { position: relative; display: block; aspect-ratio: 16 / 9; border-radius: var(--tv-ecke); overflow: hidden;
                         background: var(--tv-mulde); }
  .weiter-karte img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .weiter-karte .fort { position: absolute; left: 0; right: 0; bottom: 0; height: 5px; background: var(--tv-schleier); }
  .weiter-karte .fort b { display: block; height: 100%; background: var(--tv-akzent); }
  .weiter-karte .rest { position: absolute; right: var(--tv-a2); bottom: var(--tv-a3); height: 24px; padding: 0 var(--tv-a2);
                        display: grid; place-items: center; background: var(--tv-schleier); border-radius: var(--tv-ecke-klein);
                        font-size: var(--tv-gr-marke); font-weight: 700; }
  .weiter-karte .los { position: absolute; inset: 0; display: grid; place-items: center; opacity: 0; transition: opacity var(--tv-schnell);
                       background: var(--tv-schleier); font-size: 34px; color: var(--tv-akzent); }
  .weiter-karte:hover .los, .weiter-karte:focus-visible .los { opacity: 1; }
  .weiter-karte .vtitel { display: block; margin-top: var(--tv-a2); font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .weiter-karte:hover .vtitel { color: var(--tv-akzent); }
  .weiter-karte .vmeta { display: block; font-size: var(--tv-gr-klein); color: var(--tv-text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  @media (max-width: 900px) {
    .weiter-reihe { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }

  .nachlade-marke { height: 1px; }
  .nachladen { padding: var(--tv-a4); }

  /* Leerer Zustand */
  .leer-gross { padding: 72px var(--tv-a5); text-align: center; color: var(--tv-text-2); }
  .leer-gross i { font-size: 44px; color: var(--tv-text-3); margin-bottom: var(--tv-a4); }
  .leer-gross h2 { margin: 0 0 var(--tv-a2); color: var(--tv-text); }
  .leer-gross p { margin: 0 auto; max-width: 520px; }
</style>

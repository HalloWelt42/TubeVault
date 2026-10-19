<!--
  Playlists (Entwurf mockups/playlists.html)
  Übersicht: Kacheln mit Bild aus den ersten Videos, Fortschritt, Abspielen,
  Zufällig und Menü; Suche, Sortierung, Stand; Serien erkennen, neu anlegen.
  Playlist: Weiter mit der nächsten Folge, Zufällig, Von vorn, Menü
  (Umbenennen, Quick-Playlist, Wiederholen, Ton, ZIP, Kopie, Löschen),
  Steuerleiste, Umordnen per Ziehen, Auswahl, Videos aus der Bibliothek
  hinzufügen. Geöffnet wird über ?open=<id> (&play=1 spielt gleich ab).
-->
<script>
  import { onMount, untrack } from 'svelte';
  import { api } from '../lib/api/client.js';
  import { route, updateParams } from '../lib/router/router.js';
  import { toast } from '../lib/stores/notifications.js';
  import { playlistQueue } from '../lib/stores/playlistQueue.js';
  import { musicPlayer } from '../lib/stores/musicPlayer.svelte.js';
  import { quickPlaylist, pinPlaylist, unpinPlaylist } from '../lib/stores/quickPlaylist.js';
  import { formatDuration, parseServerTime } from '../lib/utils/format.js';
  import { onVideoMutation } from '../lib/utils/videoMutations.js';
  import { stateChips, filterItems, sortItems, moveItem, continueIndex, totalTime } from '../lib/utils/collection.js';
  import { playCollection, continueCollection, listenCollection, playAfterCurrent } from '../lib/utils/collectionPlay.js';
  import PageHeader from '../lib/components/common/PageHeader.svelte';
  import BatchToolbar from '../lib/components/common/BatchToolbar.svelte';
  import ActionMenu from '../lib/components/common/ActionMenu.svelte';
  import { musicMenuItem } from '../lib/utils/videoMusic.js';
  import SeriesProposals from '../lib/components/common/SeriesProposals.svelte';
  import CollectionBar from '../lib/components/collection/CollectionBar.svelte';
  import VideoRow from '../lib/components/collection/VideoRow.svelte';

  const OVERVIEW_SORTS = [
    { key: 'zuletzt', label: 'Zuletzt gespielt' }, { key: 'neu', label: 'Neu angelegt' },
    { key: 'name', label: 'Name' }, { key: 'groesse', label: 'Größe' },
  ];
  const DETAIL_SORTS = [
    { key: 'eigene', label: 'Eigene Reihenfolge', title: 'Wie angeordnet - per Ziehen änderbar' },
    { key: 'titel', label: 'Titel' }, { key: 'dauer', label: 'Dauer' }, { key: 'kanal', label: 'Kanal' },
  ];
  const OVERVIEW_ORDER = {
    zuletzt: (a, b) => (b.last_played || '').localeCompare(a.last_played || '') || (b.created_at || '').localeCompare(a.created_at || ''),
    neu: (a, b) => (b.created_at || '').localeCompare(a.created_at || ''),
    name: (a, b) => a.name.localeCompare(b.name, 'de', { sensitivity: 'base' }),
    groesse: (a, b) => (b.video_count || 0) - (a.video_count || 0),
  };
  // Fehlende Videos nach und nach laden: so viele je Tag (wie im Backend drip.PLAYLIST_DRIP_COUNTS)
  const DRIP_COUNTS = [1, 3, 5, 10, 20, 50];
  const progressOf = (pl) => {
    const count = pl.video_count || 0, done = pl.finished_count || 0, started = pl.started_count || 0;
    return { count, done, started, key: !count ? '' : done >= count ? 'fertig' : done || started ? 'angefangen' : 'ungesehen' };
  };

  // ── Übersicht ──
  let playlists = $state([]);
  let loading = $state(true);
  let overSearch = $state('');
  let overSort = $state('zuletzt');
  let overState = $state('');
  let showSeries = $state(false);
  let creating = $state(false);
  let newName = $state('');
  let newDesc = $state('');

  // ── Playlist ──
  let openId = $state(null);
  let detail = $state(null);           // Sammlung playlist:<id>
  let meta = $state(null);             // Eintrag aus der Übersicht (Beschreibung ...)
  let search = $state('');
  let stateFilter = $state('');
  let sort = $state('eigene');
  let repeat = $state(false);
  let selecting = $state(false);
  let selected = $state(new Set());
  let editing = $state(null);          // { name, description }
  let adding = $state(false);
  let addQuery = $state('');
  let addResults = $state([]);
  let addTimer = null;
  let dragFrom = $state(null);
  let dropAt = $state(null);
  let menu;

  let overview = $derived(playlists
    .filter(pl => (!overSearch.trim() || `${pl.name} ${pl.description || ''}`.toLocaleLowerCase('de').includes(overSearch.trim().toLocaleLowerCase('de')))
      && (!overState || progressOf(pl).key === overState))
    .sort(OVERVIEW_ORDER[overSort]));
  let overCounts = $derived(playlists.reduce((acc, pl) => { const k = progressOf(pl).key; if (k) acc[k] = (acc[k] || 0) + 1; return acc; }, {}));
  let overInfo = $derived(`${playlists.length} Playlists · ${playlists.reduce((s, pl) => s + (pl.video_count || 0), 0).toLocaleString('de-DE')} Videos`);

  let source = $derived(openId ? `playlist:${openId}` : null);
  let items = $derived(detail?.items || []);
  let shown = $derived(sortItems(filterItems(items, { search, state: stateFilter }), sort));
  let canOrder = $derived(sort === 'eigene' && !search && !stateFilter && !selecting);
  let selectedIds = $derived(shown.filter(i => selected.has(i.id)).map(i => i.id));
  // "Weiter mit Folge N": nur Geladenes zählt, die Nummer ist die Stelle in der ganzen Playlist
  let loadedItems = $derived(items.filter(i => i.loaded !== false));
  let nextIndex = $derived.by(() => {
    const index = continueIndex(loadedItems);
    return index < 0 ? -1 : items.indexOf(loadedItems[index]);
  });
  let pendingCount = $derived(detail?.counts.pending || 0);
  let nextRun = $derived(meta?.drip_enabled && meta.drip_next_run
    ? parseServerTime(meta.drip_next_run).toLocaleString('de-DE', { weekday: 'short', hour: '2-digit', minute: '2-digit' }) : null);
  let queueActive = $derived($playlistQueue.active);
  let detailInfo = $derived(detail ? [
    `${loadedItems.length} ${loadedItems.length === 1 ? 'Video' : 'Videos'}`,
    detail.duration ? totalTime(detail.duration) : null,
    detail.counts.finished ? `${detail.counts.finished} gesehen` : null,
    detail.counts.pending ? `${detail.counts.pending} noch nicht geladen` : null,
  ].filter(Boolean).join(' · ') : null);

  async function loadPlaylists() {
    try { playlists = await api.getPlaylists(); } catch { toast.error('Playlists laden fehlgeschlagen'); }
    loading = false;
    if (openId) meta = playlists.find(pl => pl.id === openId) || meta;
  }

  async function loadDetail() {
    if (!openId) return;
    try { detail = await api.getCollection(`playlist:${openId}`); }
    catch (e) { toast.error(e.message); close(); }
  }

  async function openPlaylist(id, { play = false } = {}) {
    if (openId !== Number(id)) {
      openId = Number(id);
      detail = null;
      search = ''; stateFilter = ''; sort = 'eigene'; selecting = false; selected = new Set(); adding = false; editing = null;
    }
    meta = playlists.find(pl => pl.id === Number(id)) || null;
    await loadDetail();
    if (play && items.length) playCollection(source, detail.title, items);
  }

  function open(pl) { updateParams({ open: pl.id, play: null }); }
  function close() { updateParams({ open: null, play: null }); }

  // ── Abspielen ──
  const playAt = (item) => playCollection(source, detail.title, shown, shown.indexOf(item), { resume: item.state === 'started', repeat });
  const playFromStart = () => playCollection(source, detail.title, shown, 0, { repeat });
  const playShuffled = () => playCollection(source, detail.title, shown, 0, { shuffle: true, repeat });
  const playNext = () => continueCollection(source, detail.title, items, { repeat });

  async function quickPlay(pl, how) {
    const collection = await api.getCollection(`playlist:${pl.id}`).catch((e) => { toast.error(e.message); return null; });
    if (!collection) return;
    if (!collection.items.length) { toast.info('Die Playlist ist leer'); return; }
    const src = `playlist:${pl.id}`;
    if (how === 'zufall') playCollection(src, collection.title, collection.items, 0, { shuffle: true });
    else if (how === 'weiter') continueCollection(src, collection.title, collection.items);
    else playCollection(src, collection.title, collection.items);
  }

  function download(url) {
    const link = document.createElement('a');
    link.href = url;
    link.download = '';
    link.click();
  }

  // ── Playlists verwalten ──
  async function createPlaylist() {
    const name = newName.trim();
    if (!name) return;
    try {
      const created = await api.createPlaylist({ name, description: newDesc.trim() || undefined });
      newName = ''; newDesc = ''; creating = false;
      await loadPlaylists();
      open({ id: created.id });
    } catch (e) { toast.error(e.message); }
  }

  async function saveEdit() {
    if (!editing?.name.trim()) return;
    try {
      await api.updatePlaylist(openId, { name: editing.name.trim(), description: editing.description.trim() || null });
      editing = null;
      await loadPlaylists();
      await loadDetail();
    } catch (e) { toast.error(e.message); }
  }

  function togglePin(pl) {
    if ($quickPlaylist?.id === pl.id) { unpinPlaylist(); toast.info(`"${pl.name}" ist nicht mehr Quick-Playlist`); }
    else { pinPlaylist(pl.id, pl.name); toast.success(`"${pl.name}" ist jetzt Quick-Playlist`); }
  }

  async function copyPlaylist(pl) {
    try {
      const copy = await api.copyPlaylist(pl.id);
      toast.success(`"${copy.name}" angelegt`);
      await loadPlaylists();
    } catch (e) { toast.error(e.message); }
  }

  // Löschen mit Rückgängig: die Playlist entsteht mit Namen und Reihenfolge neu
  async function deletePlaylist(pl) {
    const content = await api.getCollection(`playlist:${pl.id}`).catch(() => null);
    try {
      await api.deletePlaylist(pl.id);
      if ($quickPlaylist?.id === pl.id) unpinPlaylist();
      if (openId === pl.id) close();
      await loadPlaylists();
    } catch (e) { toast.error(e.message); return; }
    toast.undo(`"${pl.name}" gelöscht`, async () => {
      const created = await api.createPlaylist({ name: pl.name, description: pl.description || undefined });
      for (const item of content?.items || []) await api.addToPlaylist(created.id, item.id).catch(() => {});
      await loadPlaylists();
    });
  }

  // ── Videos der Playlist ──
  async function saveOrder(ids) {
    detail = { ...detail, items: ids.map(id => items.find(i => i.id === id)) };
    try { await api.reorderPlaylist(openId, ids); } catch { toast.error('Reihenfolge speichern fehlgeschlagen'); loadDetail(); }
  }

  async function removeItems(ids) {
    const before = items.map(i => i.id);
    const plId = openId;
    try { for (const id of ids) await api.removeFromPlaylist(plId, id); } catch (e) { toast.error(e.message); }
    selected = new Set();
    await Promise.all([loadDetail(), loadPlaylists()]);
    toast.undo(ids.length === 1 ? 'Video aus der Playlist entfernt' : `${ids.length} Videos aus der Playlist entfernt`, async () => {
      for (const id of ids) await api.addToPlaylist(plId, id).catch(() => {});
      await api.reorderPlaylist(plId, before);
      await Promise.all([loadDetail(), loadPlaylists()]);
    });
  }

  async function setDrip(enabled, count = null) {
    try {
      await api.updatePlaylist(openId, { drip_enabled: enabled, ...(count ? { drip_count: count } : {}) });
      toast.success(enabled ? `Lädt ab heute Nacht ${count ?? meta?.drip_count} am Tag` : 'Lädt nicht mehr nach und nach');
      await loadPlaylists();
    } catch (e) { toast.error(e.message); }
  }

  async function loadPending(limit = null) {
    try {
      const { queued } = await api.loadPlaylistPending(openId, limit);
      toast.success(`${queued} ${queued === 1 ? 'Video' : 'Videos'} in die Warteschlange`);
      await loadPlaylists();
    } catch (e) { toast.error(e.message); }
  }

  async function loadOne(item) {
    try {
      await api.addDownload({ url: `https://www.youtube.com/watch?v=${item.id}` });
      toast.success('In die Warteschlange');
    } catch (e) { toast.error(e.message); }
  }

  async function setWatched(ids, watched) {
    try { await api.setWatched(ids, watched); } catch (e) { toast.error(e.message); }
    selected = new Set();
    await Promise.all([loadDetail(), loadPlaylists()]);
  }

  async function addToOther(ids, pl) {
    let added = 0;
    for (const id of ids) { try { await api.addToPlaylist(pl.id, id); added++; } catch { /* schon drin */ } }
    toast.success(`${added} zu "${pl.name}" hinzugefügt`);
    loadPlaylists();
  }

  async function addFavorites(ids) {
    for (const id of ids) await api.addFavorite({ video_id: id, list_name: 'Standard' }).catch(() => {});
    toast.success(ids.length === 1 ? 'Zu den Favoriten' : `${ids.length} Videos zu den Favoriten`);
  }

  const otherPlaylists = (ids) => playlists.filter(pl => pl.id !== openId)
    .map(pl => ({ icon: 'fa-list-ul', label: pl.name, hint: String(pl.video_count ?? ''), run: () => addToOther(ids, pl) }));

  // ── Hinzufügen aus der Bibliothek ──
  function onAddInput() {
    clearTimeout(addTimer);
    if (!addQuery.trim()) { addResults = []; return; }
    addTimer = setTimeout(async () => {
      try {
        const res = await api.searchSection('videos', addQuery, { per_page: 30 });
        const present = new Set(items.map(i => i.id));
        addResults = res.items.filter(v => !present.has(v.id));
      } catch { addResults = []; }
    }, 300);
  }

  async function addVideo(video) {
    try {
      await api.addToPlaylist(openId, video.id);
      addResults = addResults.filter(v => v.id !== video.id);
      await Promise.all([loadDetail(), loadPlaylists()]);
    } catch (e) { toast.error(e.message?.includes('bereits') ? 'Schon in der Playlist' : e.message); }
  }

  // ── Menüs ──
  function playlistMenu(event, pl) {
    const pinned = $quickPlaylist?.id === pl.id;
    menu.open(event, pl.name, [
      { icon: 'fa-folder-open', label: 'Öffnen', run: () => open(pl) },
      { icon: 'fa-play', label: 'Von vorn abspielen', run: () => quickPlay(pl, 'vorn') },
      { icon: 'fa-rotate-left', label: 'Weiterschauen', run: () => quickPlay(pl, 'weiter') },
      { icon: 'fa-shuffle', label: 'Zufällig', run: () => quickPlay(pl, 'zufall') },
      { icon: 'fa-headphones', label: 'Als Ton hören', run: () => listenCollection(`playlist:${pl.id}`) },
      { icon: 'fa-file-zipper', label: 'Ton als ZIP herunterladen', run: () => download(api.musicZipUrl(`playlist:${pl.id}`)) },
      { trenner: true },
      { icon: 'fa-thumbtack', label: pinned ? 'Nicht mehr Quick-Playlist' : 'Als Quick-Playlist anheften', run: () => togglePin(pl) },
      { icon: 'fa-copy', label: 'Kopie anlegen', run: () => copyPlaylist(pl) },
      { trenner: true },
      { icon: 'fa-trash-can', label: 'Playlist löschen', danger: true, run: () => deletePlaylist(pl) },
    ]);
  }

  function detailMenu(event) {
    const pl = meta || { id: openId, name: detail.title };
    const pinned = $quickPlaylist?.id === openId;
    menu.open(event, detail.title, [
      { icon: 'fa-pen', label: 'Umbenennen und beschreiben', run: () => { editing = { name: detail.title, description: meta?.description || '' }; } },
      { icon: 'fa-thumbtack', label: pinned ? 'Nicht mehr Quick-Playlist' : 'Als Quick-Playlist anheften', run: () => togglePin(pl) },
      { icon: 'fa-repeat', label: 'Endlos wiederholen', hint: repeat ? 'an' : 'aus', run: () => { repeat = !repeat; } },
      { icon: 'fa-headphones', label: 'Als Ton hören', run: () => listenCollection(source) },
      { icon: 'fa-file-zipper', label: 'Ton als ZIP herunterladen', run: () => download(api.musicZipUrl(source)) },
      { icon: 'fa-copy', label: 'Kopie anlegen', run: () => copyPlaylist(pl) },
      { trenner: true },
      { icon: 'fa-eye-slash', label: 'Alles als ungesehen', run: () => setWatched(items.map(i => i.id), false) },
      { icon: 'fa-trash-can', label: 'Playlist löschen', danger: true, run: () => deletePlaylist(pl) },
    ]);
  }

  function itemMenu(event, item) {
    const ids = [item.id];
    const index = items.indexOf(item);
    menu.open(event, item.title, [
      { icon: item.state === 'started' ? 'fa-rotate-left' : 'fa-play', label: item.state === 'started' ? 'Weiterschauen' : 'Abspielen', run: () => playAt(item) },
      ...(queueActive ? [{ icon: 'fa-forward', label: 'Als Nächstes', run: () => playAfterCurrent(item) }] : []),
      { icon: 'fa-headphones', label: 'Ab hier als Ton hören', run: () => musicPlayer.playSource(`sammlung:${source}`, { start: item.id }) },
      { trenner: true },
      { icon: 'fa-list-ul', label: 'Zu anderer Playlist', items: otherPlaylists(ids) },
      { icon: 'fa-heart', label: 'Zu den Favoriten', run: () => addFavorites(ids) },
      ...(canOrder && index > 0 ? [{ icon: 'fa-arrow-up', label: 'Ganz nach oben', run: () => saveOrder(moveItem(items.map(i => i.id), index, 0)) }] : []),
      ...(canOrder && index < items.length - 1 ? [{ icon: 'fa-arrow-down', label: 'Ganz nach unten', run: () => saveOrder(moveItem(items.map(i => i.id), index, items.length)) }] : []),
      item.state === 'finished'
        ? { icon: 'fa-eye-slash', label: 'Als neu markieren', run: () => setWatched(ids, false) }
        : { icon: 'fa-check', label: 'Als gesehen markieren', run: () => setWatched(ids, true) },
      musicMenuItem(item, (isMusic) => { item.is_music = isMusic; }),
      { trenner: true },
      { icon: 'fa-xmark', label: 'Aus der Playlist entfernen', danger: true, run: () => removeItems(ids) },
    ]);
  }

  function toggle(item) {
    const next = new Set(selected);
    next.has(item.id) ? next.delete(item.id) : next.add(item.id);
    selected = next;
  }

  function onDrop(index) {
    if (dragFrom !== null && dragFrom !== index) saveOrder(moveItem(items.map(i => i.id), dragFrom, index));
    dragFrom = null; dropAt = null;
  }

  // Geöffnete Playlist folgt der Adresse (?open=<id>&play=1)
  $effect(() => {
    const id = $route.params.open;
    const play = $route.params.play === '1';
    untrack(() => {
      if (id) openPlaylist(id, { play });
      else { openId = null; detail = null; }
    });
  });

  onMount(() => {
    loadPlaylists();
    return onVideoMutation(() => { loadPlaylists(); loadDetail(); });
  });
</script>

<div class="tv-seite">
  {#if openId}
    <!-- ═══ Eine Playlist ═══ -->
    <div class="tv-seitenkopf">
      <PageHeader title={detail?.title || meta?.name || 'Playlist'} info={detailInfo} onBack={close}>
        {#if items.length}
          {#if nextIndex > 0}
            <button class="tv-knopf" onclick={playNext} title="An der gemerkten Stelle bzw. mit dem ersten ungesehenen Video">
              <i class="fa-solid fa-rotate-left"></i> Weiter mit Folge <span class="zahl">{nextIndex + 1}</span></button>
          {/if}
          <button class="tv-knopf" onclick={playShuffled}><i class="fa-solid fa-shuffle"></i> Zufällig</button>
          <button class="tv-knopf haupt" onclick={playFromStart}><i class="fa-solid fa-play"></i> {nextIndex > 0 ? 'Von vorn' : 'Abspielen'}</button>
        {/if}
        {#if detail}
          <button class="tv-knopf symbol" class:aktiv={repeat} onclick={detailMenu}
                  title="Mehr: Umbenennen, Quick-Playlist, Wiederholen, Ton, Kopie, Löschen">
            <i class="fa-solid fa-ellipsis"></i></button>
        {/if}
      </PageHeader>

      {#if editing}
        <form class="tv-filter bearbeiten" onsubmit={(e) => { e.preventDefault(); saveEdit(); }}>
          <input class="tv-eingabe name" bind:value={editing.name} placeholder="Name" maxlength="120" />
          <input class="tv-eingabe beschreibung" bind:value={editing.description} placeholder="Beschreibung (optional)" />
          <button class="tv-knopf klein haupt" disabled={!editing.name.trim()}>Speichern</button>
          <button type="button" class="tv-knopf klein ohne" onclick={() => editing = null}>Abbrechen</button>
        </form>
      {:else if meta?.description}
        <p class="beschreibung">{meta.description}</p>
      {/if}

      {#if detail && (pendingCount || meta?.drip_enabled)}
        <div class="tv-filter nachladen">
          <i class="fa-solid fa-hourglass-half"></i>
          {#if pendingCount}<span><span class="zahl">{pendingCount}</span> noch nicht geladen</span>{:else}<span>Alles geladen</span>{/if}
          <span class="tv-trenner"></span>
          <span class="tv-etikett">Nach und nach laden</span>
          <button class="tv-chip" class:aktiv={!meta?.drip_enabled} onclick={() => setDrip(false)}>aus</button>
          {#each DRIP_COUNTS as n (n)}
            <button class="tv-chip" class:aktiv={meta?.drip_enabled && meta.drip_count === n} onclick={() => setDrip(true, n)}>
              <span class="zahl">{n}</span> am Tag</button>
          {/each}
          {#if nextRun}<span class="tv-leise tv-klein">nächster Lauf {nextRun}</span>{/if}
          {#if pendingCount}
            <div class="rechts">
              {#if pendingCount > 10}<button class="tv-knopf klein" onclick={() => loadPending(10)}>Nächste <span class="zahl">10</span> jetzt</button>{/if}
              <button class="tv-knopf klein" onclick={() => loadPending()}>Alle <span class="zahl">{pendingCount}</span> jetzt laden</button>
            </div>
          {/if}
        </div>
      {/if}

      {#if selecting}
        <BatchToolbar selectedCount={selectedIds.length} totalCount={shown.length}
                      onSelectAll={() => selected = new Set(shown.map(i => i.id))} onDone={() => { selecting = false; selected = new Set(); }}>
          <button class="tv-knopf klein" onclick={() => playCollection(source, detail.title, shown.filter(i => selected.has(i.id)))}>
            <i class="fa-solid fa-play"></i> Abspielen</button>
          <button class="tv-knopf klein" onclick={(e) => menu.open(e, 'Zu anderer Playlist', otherPlaylists(selectedIds))}>
            <i class="fa-solid fa-list-ul"></i> Zu anderer Playlist</button>
          <button class="tv-knopf klein" onclick={() => setWatched(selectedIds, true)}><i class="fa-solid fa-check"></i> Als gesehen</button>
          <button class="tv-knopf klein" onclick={() => setWatched(selectedIds, false)}><i class="fa-solid fa-eye-slash"></i> Als neu</button>
          <button class="tv-knopf klein gefahr" onclick={() => removeItems(selectedIds)}><i class="fa-solid fa-xmark"></i> Aus der Playlist</button>
        </BatchToolbar>
      {:else if detail}
        <CollectionBar bind:search placeholder="In der Playlist suchen"
                       states={stateChips(detail.counts, items.length)} bind:state={stateFilter}
                       sorts={DETAIL_SORTS} bind:sort onSelect={items.length ? () => { selecting = true; adding = false; } : null}>
          {#snippet rechts()}
            <button class="tv-knopf klein" class:aktiv={adding} onclick={() => { adding = !adding; addQuery = ''; addResults = []; }}>
              <i class="fa-solid fa-plus"></i> Videos hinzufügen</button>
          {/snippet}
        </CollectionBar>
      {/if}
    </div>

    <div class="inhalt" class:tv-spalten={adding}>
      <div class="tv-rollfeld" data-scroll-root>
        {#if !detail}
          <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt ...</div>
        {:else if !items.length}
          <div class="leer-gross">
            <i class="fa-solid fa-list-ul"></i>
            <h2>Noch keine Videos</h2>
            <p>Über "Videos hinzufügen" in der Bibliothek suchen und mit + anfügen.</p>
            {#if !adding}<button class="tv-knopf" onclick={() => adding = true}><i class="fa-solid fa-plus"></i> Videos hinzufügen</button>{/if}
          </div>
        {:else if !shown.length}
          <div class="tv-leer">Nichts gefunden.</div>
        {:else}
          <div class="zeilen" role="list">
            {#each shown as item, i (item.id)}
              {#if dropAt === i && dragFrom !== null && dragFrom !== i && dragFrom !== i - 1}<div class="einfuegen"></div>{/if}
              <VideoRow {item} nr={i + 1} mode={selecting ? 'auswahl' : canOrder ? 'ordnen' : null}
                        selected={selected.has(item.id)} lifted={dragFrom === i}
                        playing={queueActive && $playlistQueue.source === source && $playlistQueue.videos[$playlistQueue.currentIndex]?.id === item.id}
                        onPlay={playAt} onNext={queueActive ? playAfterCurrent : null} onMenu={itemMenu} onToggle={toggle}
                        onLoad={loadOne} onRemove={item.loaded === false ? (it) => removeItems([it.id]) : null}
                        removeTitle="Aus der Playlist entfernen"
                        draggable={canOrder}
                        ondragstart={() => dragFrom = i}
                        ondragover={(e) => { if (dragFrom !== null) { e.preventDefault(); dropAt = i; } }}
                        ondrop={() => onDrop(i)}
                        ondragend={() => { dragFrom = null; dropAt = null; }} />
            {/each}
            {#if canOrder}
              <div class="ende" role="presentation"
                   ondragover={(e) => { if (dragFrom !== null) { e.preventDefault(); dropAt = shown.length; } }}
                   ondrop={() => onDrop(shown.length)}>
                {#if dropAt === shown.length && dragFrom !== null}<div class="einfuegen"></div>{/if}
              </div>
            {/if}
          </div>
        {/if}
      </div>

      {#if adding}
        <div class="tv-rollfeld hinzu" data-scroll-root>
          <div class="tv-etikett">Aus der Bibliothek hinzufügen</div>
          <!-- svelte-ignore a11y_autofocus -->
          <input class="tv-eingabe" type="search" bind:value={addQuery} oninput={onAddInput} placeholder="Titel oder Kanal suchen" autofocus />
          {#each addResults as video (video.id)}
            <div class="treffer">
              <img src={api.thumbnailUrl(video.id)} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
              <div class="text">
                <div class="t">{video.title}</div>
                <div class="tv-leise tv-klein">{video.channel_name || ''}{#if video.duration} · <span class="zahl">{formatDuration(video.duration)}</span>{/if}</div>
              </div>
              <button class="tv-knopf klein haupt symbol" onclick={() => addVideo(video)} title="Hinten anfügen"><i class="fa-solid fa-plus"></i></button>
            </div>
          {:else}
            <p class="tv-schwach tv-klein">{addQuery.trim() ? 'Keine weiteren Treffer.' : 'Gefundene Videos lassen sich mit + hinten anfügen.'}</p>
          {/each}
        </div>
      {/if}
    </div>

  {:else}
    <!-- ═══ Übersicht ═══ -->
    <div class="tv-seitenkopf">
      <PageHeader title="Playlists" icon="fa-solid fa-list-ul" info={loading ? null : overInfo}>
        <button class="tv-knopf" class:aktiv={showSeries} onclick={() => showSeries = !showSeries}
                title="Nummerierte Folgen in den Titeln finden und als Playlists anlegen">
          <i class="fa-solid fa-layer-group"></i> Serien erkennen</button>
        <button class="tv-knopf haupt" onclick={() => { creating = !creating; newName = ''; newDesc = ''; }}>
          <i class="fa-solid fa-plus"></i> Neue Playlist</button>
      </PageHeader>

      {#if creating}
        <form class="tv-filter bearbeiten" onsubmit={(e) => { e.preventDefault(); createPlaylist(); }}>
          <!-- svelte-ignore a11y_autofocus -->
          <input class="tv-eingabe name" bind:value={newName} placeholder="Name der Playlist" maxlength="120" autofocus />
          <input class="tv-eingabe beschreibung" bind:value={newDesc} placeholder="Beschreibung (optional)" />
          <button class="tv-knopf klein haupt" disabled={!newName.trim()}>Anlegen</button>
          <button type="button" class="tv-knopf klein ohne" onclick={() => creating = false}>Abbrechen</button>
        </form>
      {:else if playlists.length}
        <CollectionBar bind:search={overSearch} placeholder="Playlists suchen"
                       states={[{ key: '', label: 'Alle', count: playlists.length },
                                { key: 'angefangen', label: 'Angefangen', count: overCounts.angefangen || 0 },
                                { key: 'ungesehen', label: 'Ungesehen', count: overCounts.ungesehen || 0 },
                                { key: 'fertig', label: 'Alles gesehen', count: overCounts.fertig || 0 }]}
                       bind:state={overState} sorts={OVERVIEW_SORTS} bind:sort={overSort} />
      {/if}
    </div>

    <div class="tv-rollfeld" data-scroll-root>
      {#if showSeries}<div class="serien"><SeriesProposals onchange={loadPlaylists} /></div>{/if}

      {#if loading}
        <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt ...</div>
      {:else if !playlists.length}
        <div class="leer-gross">
          <i class="fa-solid fa-list-ul"></i>
          <h2>Noch keine Playlists</h2>
          <p>Eine neue Playlist anlegen oder Serien in den Titeln erkennen lassen.</p>
        </div>
      {:else if !overview.length}
        <div class="tv-leer">Nichts gefunden.</div>
      {:else}
        <div class="pl-raster">
          {#each overview as pl (pl.id)}
            {@const p = progressOf(pl)}
            <div class="pl-kachel">
              <div class="pl-bild">
                <button class="flaeche" onclick={() => open(pl)} aria-label="{pl.name} öffnen"></button>
                {#each (pl.cover_ids || []).slice(0, 3) as id, i (id)}
                  <img class:gross={i === 0} src={api.thumbnailUrl(id)} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
                {/each}
                {#if !pl.cover_ids?.length}<i class="fa-solid fa-list-ul platzhalter"></i>{/if}
                <div class="menge"><b class="zahl">{p.count}</b><span>Videos</span></div>
                {#if $quickPlaylist?.id === pl.id}<span class="stift" title="Quick-Playlist"><i class="fa-solid fa-thumbtack"></i></span>{/if}
                <button class="mehr" onclick={(e) => playlistMenu(e, pl)} title="Mehr"><i class="fa-solid fa-ellipsis"></i></button>
                {#if p.count}
                  <div class="los">
                    {#if p.key === 'angefangen'}
                      <button class="spielen" onclick={() => quickPlay(pl, 'weiter')}><i class="fa-solid fa-rotate-left"></i> Weiter</button>
                    {:else}
                      <button class="spielen" onclick={() => quickPlay(pl, 'vorn')}><i class="fa-solid fa-play"></i> Abspielen</button>
                    {/if}
                    <button onclick={() => quickPlay(pl, 'zufall')} title="Zufällig"><i class="fa-solid fa-shuffle"></i></button>
                  </div>
                {/if}
              </div>
              <button class="pl-text" onclick={() => open(pl)}>
                <span class="pl-name">{pl.name}</span>
                <span class="pl-meta">
                  {#if pl.total_duration}<span class="zahl">{totalTime(pl.total_duration)}</span>{/if}
                  <span>{p.key === 'fertig' ? 'alles gesehen' : p.done ? `${p.done} von ${p.count} gesehen` : p.started ? `${p.started} angefangen` : p.count ? 'noch nichts gesehen' : pl.pending_count ? '' : 'leer'}</span>
                  {#if pl.pending_count}
                    <span title={pl.drip_enabled ? `Lädt ${pl.drip_count} am Tag` : 'Noch nicht geladen'}>
                      <i class="fa-solid fa-hourglass-half"></i> <span class="zahl">{pl.pending_count}</span> fehlen{pl.drip_enabled ? ` · ${pl.drip_count} am Tag` : ''}</span>
                  {/if}
                </span>
              </button>
              <div class="pl-fort"><b style:width="{p.count ? Math.round(p.done / p.count * 100) : 0}%"></b></div>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  {/if}
</div>

<ActionMenu bind:this={menu} />

<style>
  .bearbeiten { margin-bottom: var(--tv-a3); }
  .nachladen { margin-bottom: var(--tv-a3); }
  .nachladen > i { color: var(--tv-info); }
  .nachladen .rechts { margin-left: auto; display: flex; gap: var(--tv-a2); }
  .bearbeiten .name { width: 320px; }
  .bearbeiten .beschreibung { flex: 1; min-width: 240px; }
  .beschreibung { margin: calc(-1 * var(--tv-a3)) 0 var(--tv-a3); color: var(--tv-text-2); font-size: var(--tv-gr-klein); max-width: 820px; }
  .inhalt { flex: 1; min-height: 0; display: flex; flex-direction: column; }
  .inhalt.tv-spalten { display: grid; }
  .zeilen { display: flex; flex-direction: column; gap: 2px; }
  .einfuegen { height: 3px; margin: 0 0 0 30px; background: var(--tv-akzent); border-radius: 1px; }
  .ende { min-height: 40px; }
  .hinzu { display: flex; flex-direction: column; gap: var(--tv-a2); background: var(--tv-flaeche); border-radius: var(--tv-ecke);
           padding: var(--tv-a3); margin: var(--tv-a2) 0 var(--tv-a4); }
  .treffer { display: grid; grid-template-columns: 112px minmax(0, 1fr) auto; gap: var(--tv-a3); align-items: center; padding: 4px;
             border-radius: var(--tv-ecke); }
  .treffer:hover { background: var(--tv-karte); }
  .treffer img { width: 112px; aspect-ratio: 16 / 9; object-fit: cover; border-radius: var(--tv-ecke-klein); background: var(--tv-mulde); }
  .treffer .t { font-weight: 600; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .serien { margin-bottom: var(--tv-a5); }

  .pl-raster { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--tv-a5) var(--tv-a4); }
  .pl-kachel { position: relative; min-width: 0; }
  .pl-bild { position: relative; aspect-ratio: 16 / 9; border-radius: var(--tv-ecke); overflow: hidden; background: var(--tv-mulde);
             display: grid; grid-template-columns: 2fr 1fr; grid-template-rows: 1fr 1fr; gap: 2px; }
  .pl-bild img { width: 100%; height: 100%; min-height: 0; object-fit: cover; display: block; }
  .pl-bild img.gross { grid-row: 1 / 3; }
  .flaeche { position: absolute; inset: 0; z-index: 1; border: 0; padding: 0; background: none; cursor: pointer; }
  .platzhalter { grid-row: 1 / 3; align-self: center; justify-self: center; font-size: 36px; color: var(--tv-text-3); }
  .menge { position: absolute; right: 0; top: 0; bottom: 0; width: 33.4%; display: flex; flex-direction: column; align-items: center;
           justify-content: center; gap: 2px; background: rgba(8, 13, 16, 0.78); font-weight: 700; pointer-events: none; }
  .menge b { font-size: 24px; }
  .menge span { font-size: var(--tv-gr-marke); color: var(--tv-text-2); letter-spacing: 0.06em; text-transform: uppercase; }
  .stift { position: absolute; left: 8px; top: 8px; z-index: 2; width: 28px; height: 28px; display: grid; place-items: center;
           background: var(--tv-schleier); border-radius: var(--tv-ecke-klein); color: var(--tv-akzent); font-size: 13px; }
  .mehr { position: absolute; right: calc(33.4% + 8px); top: 8px; z-index: 2; width: 34px; height: 34px; border: 0; display: grid;
          place-items: center; background: var(--tv-schleier); border-radius: var(--tv-ecke-klein); color: var(--tv-text); opacity: 0; cursor: pointer; }
  .los { position: absolute; left: 10px; bottom: 10px; z-index: 2; display: flex; gap: 6px; opacity: 0; transform: translateY(6px);
         transition: opacity var(--tv-schnell), transform var(--tv-schnell); }
  .pl-kachel:hover .mehr, .pl-kachel:focus-within .mehr, .pl-kachel:hover .los, .pl-kachel:focus-within .los { opacity: 1; transform: none; }
  .los button { height: 40px; padding: 0 12px; border: 0; border-radius: var(--tv-ecke); cursor: pointer; font: inherit; font-weight: 700;
                background: var(--tv-schleier); color: var(--tv-text); display: inline-flex; align-items: center; gap: 6px; }
  .los button.spielen { background: var(--tv-akzent); color: var(--tv-akzent-text); }
  .pl-text { display: block; width: 100%; margin-top: var(--tv-a2); padding: 0; border: 0; background: none; color: var(--tv-text);
             font: inherit; text-align: left; cursor: pointer; }
  .pl-name { display: block; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .pl-text:hover .pl-name { color: var(--tv-akzent); }
  .pl-meta { display: flex; gap: var(--tv-a3); font-size: var(--tv-gr-klein); color: var(--tv-text-2); }
  .pl-meta .zahl { color: var(--tv-text-3); }
  .pl-fort { margin-top: 6px; height: 4px; background: var(--tv-mulde); border-radius: 1px; overflow: hidden; }
  .pl-fort b { display: block; height: 100%; background: var(--tv-akzent); }

  .leer-gross { padding: 72px var(--tv-a5); text-align: center; color: var(--tv-text-2); }
  .leer-gross i { font-size: 44px; color: var(--tv-text-3); margin-bottom: var(--tv-a4); }
  .leer-gross h2 { margin: 0 0 var(--tv-a2); color: var(--tv-text); }
  .leer-gross p { margin: 0 auto var(--tv-a4); max-width: 520px; }
</style>

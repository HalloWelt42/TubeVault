<!--
  Favoriten (Entwurf mockups/favoriten.html): Listen als Reiter, Abspielen,
  Zufällig, Weiterschauen und Als Ton hören im festen Kopf, Steuerleiste mit
  Stand und Sortierung, Liste oder Kacheln, Umordnen per Ziehen, Auswahl mit
  Stapelaktionen, Menü je Video, Entfernen mit Rückgängig.
-->
<script>
  import { api } from '../lib/api/client.js';
  import { toast } from '../lib/stores/notifications.js';
  import { playlistQueue } from '../lib/stores/playlistQueue.js';
  import { musicPlayer } from '../lib/stores/musicPlayer.svelte.js';
  import { formatDateRelative } from '../lib/utils/format.js';
  import { onVideoMutation } from '../lib/utils/videoMutations.js';
  import { onMount } from 'svelte';
  import { stateChips, filterItems, sortItems, moveItem, totalTime } from '../lib/utils/collection.js';
  import { playCollection, continueCollection, listenCollection, playAfterCurrent } from '../lib/utils/collectionPlay.js';
  import PageHeader from '../lib/components/common/PageHeader.svelte';
  import BatchToolbar from '../lib/components/common/BatchToolbar.svelte';
  import ActionMenu from '../lib/components/common/ActionMenu.svelte';
  import CollectionBar from '../lib/components/collection/CollectionBar.svelte';
  import VideoRow from '../lib/components/collection/VideoRow.svelte';
  import VideoCard from '../lib/components/video/VideoCard.svelte';

  const STANDARD = 'Standard';
  const SORTS = [
    { key: 'eigene', label: 'Eigene Reihenfolge', title: 'Wie du sie angeordnet hast - per Ziehen änderbar' },
    { key: 'hinzugefuegt', label: 'Hinzugefügt' }, { key: 'titel', label: 'Titel' },
    { key: 'dauer', label: 'Dauer' }, { key: 'kanal', label: 'Kanal' },
  ];

  let lists = $state([]);            // [{ name, count }]
  let newLists = $state([]);         // angelegt, aber noch leer
  let activeList = $state(STANDARD);
  let collection = $state(null);
  let loading = $state(true);

  let search = $state('');
  let stateFilter = $state('');
  let sort = $state('eigene');
  let view = $state('liste');
  let selecting = $state(false);
  let selected = $state(new Set());
  let naming = $state(null);         // { ids } beim Anlegen einer neuen Liste
  let newName = $state('');
  let dragFrom = $state(null);
  let dropAt = $state(null);
  let playlists = null;
  let menu;

  let source = $derived(`favorites:${activeList}`);
  let items = $derived(collection?.items || []);
  let shown = $derived(sortItems(filterItems(items, { search, state: stateFilter }), sort));
  let canOrder = $derived(sort === 'eigene' && !search && !stateFilter && !selecting);
  let allLists = $derived([...lists, ...newLists.filter(n => !lists.some(l => l.name === n)).map(name => ({ name, count: 0 }))]);
  let info = $derived(collection ? [
    `${items.length} ${items.length === 1 ? 'Video' : 'Videos'}`,
    collection.duration ? totalTime(collection.duration) : null,
    collection.counts.started ? `${collection.counts.started} angefangen` : null,
  ].filter(Boolean).join(' · ') : null);
  let queueActive = $derived($playlistQueue.active);

  async function loadLists() {
    try { lists = await api.getFavoriteLists(); } catch (e) { toast.error(e.message); }
    if (!allLists.some(l => l.name === activeList)) activeList = lists[0]?.name || STANDARD;
  }

  async function load() {
    loading = !collection;
    try { collection = await api.getCollection(source); }
    catch (e) { toast.error(e.message); }
    finally { loading = false; }
  }

  function chooseList(name) {
    activeList = name;
    collection = null;
    selected = new Set();
    load();
  }

  // ── Abspielen ──
  const playAt = (item) => playCollection(source, collection.title, shown, shown.indexOf(item), { resume: item.state === 'started' });
  const playAll = () => playCollection(source, collection.title, shown);
  const playShuffled = () => playCollection(source, collection.title, shown, 0, { shuffle: true });
  const playContinue = () => continueCollection(source, collection.title, shown);
  const listen = () => listenCollection(source);

  // ── Ändern ──
  async function removeItems(ids) {
    const before = items.map(i => i.id);
    const titles = items.filter(i => ids.includes(i.id)).map(i => i.title);
    try {
      for (const id of ids) await api.removeFavorite(id, activeList);
    } catch (e) { toast.error(e.message); }
    selected = new Set();
    await refresh();
    toast.undo(ids.length === 1 ? `"${titles[0]?.slice(0, 50)}" aus den Favoriten entfernt` : `${ids.length} Videos aus den Favoriten entfernt`,
      async () => {
        for (const id of ids) await api.addFavorite({ video_id: id, list_name: activeList }).catch(() => {});
        await api.reorderFavorites(activeList, before);
        await refresh();
      });
  }

  async function moveTo(ids, target) {
    try {
      await api.moveFavorites(ids, activeList, target);
      newLists = newLists.filter(n => n !== target);
      toast.success(`${ids.length === 1 ? '1 Video' : `${ids.length} Videos`} nach "${target}" verschoben`);
    } catch (e) { toast.error(e.message); }
    selected = new Set();
    await refresh();
  }

  async function setWatched(ids, watched) {
    try { await api.setWatched(ids, watched); } catch (e) { toast.error(e.message); }
    selected = new Set();
    await load();
  }

  async function saveOrder(ids) {
    collection = { ...collection, items: ids.map(id => items.find(i => i.id === id)) };
    try { await api.reorderFavorites(activeList, ids); } catch (e) { toast.error(e.message); load(); }
  }

  async function addToPlaylist(ids, pl) {
    let added = 0;
    for (const id of ids) {
      try { await api.addToPlaylist(pl.id, id); added++; } catch { /* schon drin */ }
    }
    toast.success(`${added} zu "${pl.name}" hinzugefügt`);
  }

  async function refresh() { await Promise.all([loadLists(), load()]); }

  // ── Menüs ──
  async function playlistItems(ids) {
    playlists ??= await api.getPlaylists().catch(() => []);
    return playlists.map(pl => ({ icon: 'fa-list-ul', label: pl.name, hint: String(pl.video_count ?? ''), run: () => addToPlaylist(ids, pl) }));
  }

  function listItems(ids) {
    return [
      ...allLists.filter(l => l.name !== activeList).map(l => ({ icon: 'fa-heart', label: l.name, hint: String(l.count), run: () => moveTo(ids, l.name) })),
      { icon: 'fa-plus', label: 'Neue Liste ...', run: () => { naming = { ids }; newName = ''; } },
    ];
  }

  async function openMenu(event, item) {
    const ids = [item.id];
    const index = items.indexOf(item);
    menu.open(event, item.title, [
      { icon: item.state === 'started' ? 'fa-rotate-left' : 'fa-play', label: item.state === 'started' ? 'Weiterschauen' : 'Abspielen', run: () => playAt(item) },
      ...(queueActive ? [{ icon: 'fa-forward', label: 'Als Nächstes', run: () => playAfterCurrent(item) }] : []),
      { icon: 'fa-headphones', label: 'Ab hier als Ton hören', run: () => musicPlayer.playSource(`sammlung:${source}`, { start: item.id }) },
      { trenner: true },
      { icon: 'fa-list-ul', label: 'Zur Playlist hinzufügen', items: await playlistItems(ids) },
      { icon: 'fa-arrow-right-arrow-left', label: 'In Liste verschieben', items: listItems(ids) },
      ...(canOrder && index > 0 ? [{ icon: 'fa-arrow-up', label: 'Ganz nach oben', run: () => saveOrder(moveItem(items.map(i => i.id), index, 0)) }] : []),
      ...(canOrder && index < items.length - 1 ? [{ icon: 'fa-arrow-down', label: 'Ganz nach unten', run: () => saveOrder(moveItem(items.map(i => i.id), index, items.length)) }] : []),
      item.state === 'finished'
        ? { icon: 'fa-eye-slash', label: 'Als neu markieren', run: () => setWatched(ids, false) }
        : { icon: 'fa-check', label: 'Als gesehen markieren', run: () => setWatched(ids, true) },
      { trenner: true },
      { icon: 'fa-heart-crack', label: 'Aus Favoriten entfernen', danger: true, run: () => removeItems(ids) },
    ]);
  }

  // ── Auswahl ──
  function toggle(item) {
    const next = new Set(selected);
    next.has(item.id) ? next.delete(item.id) : next.add(item.id);
    selected = next;
  }
  function stopSelecting() { selecting = false; selected = new Set(); }
  let selectedIds = $derived(shown.filter(i => selected.has(i.id)).map(i => i.id));

  // ── Ziehen ──
  function onDrop(index) {
    if (dragFrom !== null && dragFrom !== index) saveOrder(moveItem(items.map(i => i.id), dragFrom, index));
    dragFrom = null; dropAt = null;
  }

  function createList() {
    const name = newName.trim();
    if (!name) return;
    if (naming?.ids?.length) moveTo(naming.ids, name);
    else { newLists = [...newLists, name]; chooseList(name); }
    naming = null;
  }

  // Laden nur beim Öffnen und bei Listenwechsel - ein $effect würde sich über
  // das gelesene collection selbst neu auslösen
  onMount(() => {
    refresh();
    return onVideoMutation(() => refresh());
  });
</script>

<div class="tv-seite">
  <div class="tv-seitenkopf">
    <PageHeader title="Favoriten" {info}>
      {#if items.length}
        <button class="tv-knopf" onclick={playContinue} title="Das zuletzt angefangene Video an der gemerkten Stelle">
          <i class="fa-solid fa-rotate-left"></i> Weiterschauen</button>
        <button class="tv-knopf" onclick={listen} title="Alle Videos der Liste nur als Ton im Musikspieler">
          <i class="fa-solid fa-headphones"></i> Als Ton hören</button>
        <button class="tv-knopf" onclick={playShuffled}><i class="fa-solid fa-shuffle"></i> Zufällig</button>
        <button class="tv-knopf haupt" onclick={playAll}><i class="fa-solid fa-play"></i> Alle abspielen</button>
      {/if}
    </PageHeader>

    <div class="tv-reiter">
      {#each allLists as list (list.name)}
        <button class:aktiv={activeList === list.name} onclick={() => chooseList(list.name)}>
          <i class="fa-solid fa-heart"></i> {list.name} <span class="tv-zaehler">{list.count}</span></button>
      {/each}
      {#if naming}
        <form class="neu" onsubmit={(e) => { e.preventDefault(); createList(); }}>
          <!-- svelte-ignore a11y_autofocus -->
          <input class="tv-eingabe" bind:value={newName} placeholder="Name der neuen Liste" maxlength="80" autofocus />
          <button class="tv-knopf klein haupt" disabled={!newName.trim()}>{naming.ids?.length ? 'Anlegen und verschieben' : 'Anlegen'}</button>
          <button type="button" class="tv-knopf klein ohne" onclick={() => naming = null}>Abbrechen</button>
        </form>
      {:else}
        <button onclick={() => { naming = { ids: [] }; newName = ''; }} title="Neue Liste anlegen"><i class="fa-solid fa-plus"></i> Neue Liste</button>
      {/if}
    </div>

    {#if selecting}
      <BatchToolbar selectedCount={selectedIds.length} totalCount={shown.length}
                    onSelectAll={() => selected = new Set(shown.map(i => i.id))} onDone={stopSelecting}>
        <button class="tv-knopf klein" onclick={() => playCollection(source, collection.title, shown.filter(i => selected.has(i.id)))}>
          <i class="fa-solid fa-play"></i> Abspielen</button>
        <button class="tv-knopf klein" onclick={async (e) => menu.open(e, 'Zur Playlist', await playlistItems(selectedIds))}>
          <i class="fa-solid fa-list-ul"></i> Zur Playlist</button>
        <button class="tv-knopf klein" onclick={(e) => menu.open(e, 'In Liste verschieben', listItems(selectedIds))}>
          <i class="fa-solid fa-arrow-right-arrow-left"></i> In Liste verschieben</button>
        <button class="tv-knopf klein" onclick={() => setWatched(selectedIds, true)}><i class="fa-solid fa-check"></i> Als gesehen</button>
        <button class="tv-knopf klein" onclick={() => setWatched(selectedIds, false)}><i class="fa-solid fa-eye-slash"></i> Als neu</button>
        <button class="tv-knopf klein gefahr" onclick={() => removeItems(selectedIds)}><i class="fa-solid fa-heart-crack"></i> Aus Favoriten</button>
      </BatchToolbar>
    {:else if items.length}
      <CollectionBar bind:search placeholder="In den Favoriten suchen"
                     states={stateChips(collection.counts, items.length)} bind:state={stateFilter}
                     sorts={SORTS} bind:sort bind:view onSelect={() => { selecting = true; view = 'liste'; }} />
    {/if}
  </div>

  <div class="tv-rollfeld" data-scroll-root>
    {#if loading}
      <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt ...</div>
    {:else if !items.length}
      <div class="leer-gross">
        <i class="fa-regular fa-heart"></i>
        <h2>Diese Liste ist leer</h2>
        <p>Mit dem Herz an jedem Video landet es hier. Videos aus anderen Listen lassen sich auch hierher verschieben.</p>
      </div>
    {:else if !shown.length}
      <div class="tv-leer">Nichts gefunden.</div>
    {:else if view === 'kacheln'}
      <div class="tv-raster">
        {#each shown as item (item.id)}
          <VideoCard video={{ ...item, last_position: item.position }} showArchiveBtn={false} onPlay={() => playAt(item)} />
        {/each}
      </div>
    {:else}
      <div class="zeilen" role="list">
        {#each shown as item, i (item.id)}
          {#if dropAt === i && dragFrom !== null && dragFrom !== i && dragFrom !== i - 1}<div class="einfuegen"></div>{/if}
          <VideoRow {item} nr={i + 1} meta={item.added_at ? formatDateRelative(item.added_at) : null}
                    mode={selecting ? 'auswahl' : canOrder ? 'ordnen' : null}
                    selected={selected.has(item.id)} lifted={dragFrom === i}
                    playing={queueActive && $playlistQueue.source === source && $playlistQueue.videos[$playlistQueue.currentIndex]?.id === item.id}
                    onPlay={playAt} onNext={queueActive ? playAfterCurrent : null} onMenu={openMenu} onToggle={toggle}
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
</div>

<ActionMenu bind:this={menu} />

<style>
  .tv-reiter { margin: 0 0 var(--tv-a3); align-items: center; }
  .neu { display: flex; gap: var(--tv-a2); align-items: center; }
  .neu .tv-eingabe { width: 240px; }
  .zeilen { display: flex; flex-direction: column; gap: 2px; }
  .einfuegen { height: 3px; margin: 0 0 0 30px; background: var(--tv-akzent); border-radius: 1px; }
  .ende { min-height: 40px; }
  .leer-gross { padding: 72px var(--tv-a5); text-align: center; color: var(--tv-text-2); }
  .leer-gross i { font-size: 44px; color: var(--tv-text-3); margin-bottom: var(--tv-a4); }
  .leer-gross h2 { margin: 0 0 var(--tv-a2); color: var(--tv-text); }
  .leer-gross p { margin: 0 auto; max-width: 520px; }
</style>

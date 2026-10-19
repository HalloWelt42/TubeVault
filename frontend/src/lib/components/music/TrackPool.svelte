<!--
  Titelquelle des Listen-Baukastens. Oben die Quelle (utils/poolSources.js):
  alle Titel, Alben, Interpreten, Lieblingssongs, andere Wiedergabelisten,
  Verlauf. Alle Titel und Lieblingssongs kommen seitenweise vom Server, mit
  Suche, Herkunft (Musikvideos, Sammlung) und Sortierung. Bei Alben,
  Interpreten und Listen steht erst die Liste der Gruppen (durchsuchbar); eine
  geöffnete Gruppe zeigt ihre Titel, mit Zurück und "Alle hinzufügen" (in ihrer
  Reihenfolge, ohne was schon in der Liste steht). Quelle und Gruppe stehen in
  der Adresse (?aus=, ?gruppe=). Übernehmen wie gehabt: ziehen, doppelt klicken
  oder +; Klick wählt aus (Umschalt: von bis), dann wandert die ganze Auswahl
  auf einmal. Klick aufs Cover hört hinein (ab dort läuft die Titelquelle
  weiter, nochmals Klick hält an). Was schon in der Liste steht, ist markiert.
  "Zur Stelle" im Spieler zeigt den laufenden Titel in der offenen Liste, sonst
  unter allen Titeln, und wählt ihn aus (utils/trackSpot.js).
-->
<script>
  import { onMount, tick } from 'svelte';
  import { get } from 'svelte/store';
  import { api } from '../../api/client.js';
  import { route, updateParams } from '../../router/router.js';
  import { formatDuration } from '../../utils/format.js';
  import { coverUrl } from '../../utils/musicTrack.js';
  import { createListLoader } from '../../utils/listLoader.svelte.js';
  import { infiniteScroll } from '../../utils/infiniteScroll.js';
  import { setDraggedTracks } from '../../utils/trackDrag.js';
  import { isRemoved, onMusicChange } from '../../utils/musicChanges.js';
  import { claimTrackSpot, loadAround, prependInPlace, scrollToTrack } from '../../utils/trackSpot.js';
  import { POOL_SOURCES, filterGroups, filterTracks, sourceById } from '../../utils/poolSources.js';
  import { toast } from '../../stores/notifications.js';
  import { musicPlayer as player } from '../../stores/musicPlayer.svelte.js';
  import CoverPlay from './CoverPlay.svelte';

  // inList: Kennungen, die schon in der Liste stehen; target: die Liste rechts (playlist:<id>, fehlt unter
  // den Wiedergabelisten); onAdd(titel, { whole }): ans Ende der Liste, whole = eine ganze Gruppe
  let { inList = new Set(), canAdd = false, target = null, onAdd = () => {} } = $props();

  const PAGE = 100;
  const GROUP_PAGE = 100;            // so viele Gruppen auf einmal, weitere beim Rollen
  const SORTS = [['artist', 'Interpret'], ['title', 'Titel'], ['added', 'Neu']];
  const ORIGINS = [['alle', 'Alles'], ['videos', 'Musikvideos'], ['sammlung', 'Sammlung']];
  const DEBOUNCE_MS = 300;

  const params = get(route).params || {};
  let from = $state(sourceById(params.aus).id);
  let groupKey = $state(sourceById(params.aus).groups ? params.gruppe || null : null);
  let query = $state('');
  let sort = $state('artist');
  let origin = $state('alle');
  let chosen = $state(new Set());
  let anchor = -1;                 // letzter Klick, für Umschalt-Klick
  let timer;
  let loadRun = 0;                 // nur die jüngste Antwort zählt
  let groupScroll = 0;             // Rollstand der Gruppenliste, für den Rückweg
  let box = $state(null);          // Rollbereich

  let groups = $state([]);         // Gruppen der Quelle
  let groupsShown = $state(GROUP_PAGE);
  let fixed = $state(null);        // { title, tracks }: geöffnete Gruppe oder Verlauf
  let busy = $state(false);

  const list = createListLoader(async (page) => {
    const r = await api.musicTracks({ sort, source: origin, q: query.trim(), favorites: !!source.favorites,
                                      offset: (page - 1) * PAGE, limit: PAGE });
    return { items: r.items, total: r.total };
  });

  let source = $derived(sourceById(from));
  let paged = $derived(!!source.paged);
  let showsGroups = $derived(!!source.groups && !groupKey);
  let visibleGroups = $derived(filterGroups(groups.filter((g) => g.key !== target), query));
  let tracks = $derived(paged ? list.items : filterTracks(fixed?.tracks || [], query));
  let picked = $derived(tracks.filter((t) => chosen.has(t.id)));
  let count = $derived(paged ? list.total : showsGroups ? visibleGroups.length : tracks.length);
  let loading = $derived(paged ? list.loading : busy);
  let placeholder = $derived(paged ? 'Titel, Interpret, Album' : showsGroups ? source.search : 'In dieser Liste suchen');

  function clearChoice() {
    chosen = new Set();
    anchor = -1;
  }

  async function load() {
    clearChoice();
    const run = ++loadRun;
    if (paged) return list.load(true).catch((e) => toast.error(e.message));
    busy = true;
    try {
      if (showsGroups) {
        const found = await source.groups();
        if (run === loadRun) { groups = found; groupsShown = GROUP_PAGE; }
      } else {
        const found = await api.musicPlay(groupKey || source.fixed);
        if (run === loadRun) fixed = found;
      }
    } catch (e) { toast.error(e.message); }
    if (run === loadRun) busy = false;
  }

  const remember = () => updateParams({ aus: from === POOL_SOURCES[0].id ? null : from, gruppe: groupKey });

  function chooseSource(id) {
    if (id === from && !groupKey) return;
    from = id;
    groupKey = null;
    groups = [];
    fixed = null;
    query = '';
    remember();
    load();
  }

  function openGroup(key) {
    groupScroll = box?.scrollTop || 0;
    groupKey = key;
    fixed = null;
    query = '';
    remember();
    load();
  }

  // Zurück zur Gruppenliste, an die Stelle, von der aus die Gruppe geöffnet wurde
  async function closeGroup() {
    groupKey = null;
    fixed = null;
    query = '';
    remember();
    clearChoice();
    if (!groups.length) return load();
    await tick();
    if (box) box.scrollTop = groupScroll;
  }

  function onSearch() {
    if (!paged) return;            // Gruppen und feste Listen filtern sofort hier
    clearTimeout(timer);
    timer = setTimeout(load, DEBOUNCE_MS);
  }

  function chooseSort(value) {
    sort = value;
    load();
  }

  function chooseOrigin(value) {
    origin = value;
    load();
  }

  function click(e, index) {
    const id = tracks[index].id;
    const next = new Set(chosen);
    if (e.shiftKey && anchor >= 0) {
      const [first, last] = anchor < index ? [anchor, index] : [index, anchor];
      for (const track of tracks.slice(first, last + 1)) next.add(track.id);
    } else if (!next.delete(id)) {
      next.add(id);
    }
    anchor = index;
    chosen = next;
  }

  // Gewählte Zeile: die ganze Auswahl, sonst nur diese
  const cargo = (track) => (chosen.has(track.id) ? picked : [track]);

  // Hineinhören, ohne die Auswahl zu ändern; Weiter springt zum nächsten Titel der Quelle
  const listen = (index) => player.playTracks(tracks, index, 'Listen-Baukasten');

  // Zur Stelle: steht der Titel in der offenen Liste, dorthin; sonst unter allen Titeln
  // (bzw. den Lieblingssongs, wenn er einer ist und sie offen sind): Seite laden, hinrollen, auswählen
  async function reveal(track) {
    const index = tracks.findIndex((t) => t.id === track.id);
    if (index >= 0) {
      chosen = new Set([track.id]);
      anchor = index;
      await scrollToTrack(box, track.id);
      return;
    }
    if (!(paged && (!source.favorites || track.favorite))) {
      from = POOL_SOURCES[0].id;
      groupKey = null;
      query = '';
      remember();
    }
    try {
      const found = await loadAround({
        list, pageSize: PAGE,
        locate: async () => (await api.musicTrackPosition(track.id, { sort, source: origin, q: query.trim(),
                                                                       favorites: !!source.favorites })).position,
        clearFilters: () => {
          if (!query.trim() && origin === 'alle') return false;
          query = '';
          origin = 'alle';
          return true;
        },
      });
      if (!found) return toast.info('Der Titel steht nicht unter den Titeln der Musik');
      chosen = new Set([track.id]);
      anchor = list.items.findIndex((t) => t.id === track.id);
      await scrollToTrack(box, track.id);
    } catch (e) { toast.error(e.message); }
  }

  function add(items) {
    if (!canAdd) return toast.info('Rechts erst eine Liste wählen oder anlegen');
    onAdd(items);
    clearChoice();
  }

  // Die ganze geöffnete Gruppe, in ihrer Reihenfolge (die Suche hier grenzt nur die Anzeige ein)
  function addAll() {
    if (!canAdd) return toast.info('Rechts erst eine Liste wählen oder anlegen');
    onAdd(fixed?.tracks || [], { whole: true });
    clearChoice();
  }

  onMount(() => {
    load();
    const unclaim = claimTrackSpot({ accepts: () => true, reveal });
    const unlisten = onMusicChange((change) => {
      const gone = isRemoved(change);
      list.items = list.items.filter((t) => !gone(t));
      if (fixed) fixed = { ...fixed, tracks: fixed.tracks.filter((t) => !gone(t)) };
      if (change.restored) load();
    });
    return () => { unclaim(); unlisten(); };
  });
</script>

<section class="quelle">
  <div class="kopf">
    <div class="quellen" role="tablist" aria-label="Woraus die Titel kommen">
      {#each POOL_SOURCES as s (s.id)}
        <button class="tv-chip" role="tab" aria-selected={from === s.id} class:aktiv={from === s.id} onclick={() => chooseSource(s.id)}>
          <i class="fa-solid {s.icon}"></i> {s.label}{#if from === s.id && !groupKey && !loading}<span class="zahl anzahl">{count.toLocaleString('de-DE')}</span>{/if}</button>
      {/each}
    </div>

    {#if groupKey}
      <div class="gruppenkopf">
        <button class="tv-knopf ohne klein" onclick={closeGroup} title="Zurück zu den {source.label}">
          <i class="fa-solid fa-arrow-left"></i> {source.label}</button>
        <button class="tv-knopf haupt klein" onclick={addAll} disabled={!fixed?.tracks.length}
                title="Alle Titel dieser Gruppe ans Ende der Liste rechts, ohne die, die schon darin stehen">
          <i class="fa-solid fa-plus"></i> Alle hinzufügen</button>
      </div>
      <h2 class="gruppenname" title={fixed?.title || ''}>{fixed?.title || ''}
        {#if fixed}<span class="zahl tv-schwach">{fixed.tracks.length} Titel</span>{/if}</h2>
    {/if}

    <input class="tv-eingabe" bind:value={query} oninput={onSearch} {placeholder} />
    {#if paged}
      <div class="leiste">
        {#each ORIGINS as [value, label]}
          <button class="tv-chip" class:aktiv={origin === value} onclick={() => chooseOrigin(value)}>{label}</button>
        {/each}
        <span class="tv-trenner"></span>
        {#each SORTS as [value, label]}
          <button class="tv-chip" class:aktiv={sort === value} onclick={() => chooseSort(value)}>{label}</button>
        {/each}
      </div>
    {/if}
    {#if !showsGroups}
      <div class="leiste auswahl">
        {#if chosen.size}
          <button class="tv-knopf haupt klein" onclick={() => add(picked)} disabled={!canAdd}>
            <i class="fa-solid fa-plus"></i> <span class="zahl">{chosen.size}</span> hinzufügen</button>
          <button class="tv-knopf ohne klein" onclick={clearChoice}>Auswahl aufheben</button>
        {:else}
          <span class="tv-schwach tv-klein hinweis">Ziehen, Doppelklick oder +; Klick wählt aus, Umschalt-Klick von bis</span>
        {/if}
      </div>
    {/if}
  </div>

  <div class="titel" data-scroll-root bind:this={box}>
    {#if loading}
      <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt ...</div>
    {:else if showsGroups}
      {#each visibleGroups.slice(0, groupsShown) as group (group.key)}
        <button class="gruppe" onclick={() => openGroup(group.key)} title="{group.name}: Titel zeigen">
          <span class="bild">
            {#if group.covers?.length}<img src={coverUrl(group.covers[0])} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
            {:else}<i class="fa-solid {source.icon}"></i>{/if}
          </span>
          <span class="text"><span class="t">{group.name}</span>
            <span class="w zahl">{group.subtitle ? `${group.subtitle} · ` : ''}{group.count} Titel</span></span>
          <i class="fa-solid fa-chevron-right weiter"></i>
        </button>
      {:else}
        <div class="tv-leer">{query.trim() ? 'Nichts gefunden.' : 'Hier ist noch nichts.'}</div>
      {/each}
      <div use:infiniteScroll={{ onLoadMore: () => { groupsShown += GROUP_PAGE; }, canLoad: () => groupsShown < visibleGroups.length }}></div>
    {:else}
      {#if paged && list.hasEarlier}
        <button class="tv-knopf ohne klein frueher" onclick={() => prependInPlace(box, list.loadEarlier)} disabled={list.loadingMore}>
          <i class="fa-solid fa-angles-up"></i> Frühere Titel</button>
      {/if}
      {#each tracks as track, i (track.id)}
        <div class="zeile" data-titel={track.id} class:gewaehlt={chosen.has(track.id)} class:drin={inList.has(track.id)}
             class:laeuft={player.current?.id === track.id} role="button" tabindex="0"
             draggable="true" ondragstart={(e) => setDraggedTracks(e, cargo(track))}
             onclick={(e) => click(e, i)} ondblclick={() => add([track])}
             onkeydown={(e) => { if (e.key === 'Enter') add(cargo(track)); else if (e.key === ' ') { e.preventDefault(); click(e, i); } }}
             title={inList.has(track.id) ? 'Schon in der Liste' : 'Ziehen oder doppelt klicken: in die Liste'}>
          <CoverPlay {track} onplay={() => listen(i)} />
          <span class="text"><span class="t">{#if track.kind === 'datei'}<i class="fa-solid fa-compact-disc sammlung" title="Aus der eigenen Sammlung"></i> {/if}{track.title}</span>
            <span class="w">{track.artist}{#if track.album}{' · '}{track.album}{/if}</span></span>
          <span class="zahl dauer">{formatDuration(track.duration || 0)}</span>
          {#if inList.has(track.id)}
            <i class="fa-solid fa-check drin-zeichen" title="Schon in der Liste"></i>
          {:else}
            <button class="plus" onclick={(e) => { e.stopPropagation(); add(cargo(track)); }} title="In die Liste"><i class="fa-solid fa-plus"></i></button>
          {/if}
        </div>
      {:else}
        <div class="tv-leer">{source.favorites && !query.trim() ? 'Noch keine Lieblingssongs.' : 'Keine Titel gefunden.'}</div>
      {/each}
      {#if paged}<div use:infiniteScroll={{ onLoadMore: list.loadMore, canLoad: list.canLoad }}></div>{/if}
    {/if}
  </div>
</section>

<style>
  .quelle { min-height: 0; display: flex; flex-direction: column; container-type: inline-size; }
  .kopf { flex: none; display: flex; flex-direction: column; gap: var(--tv-a2); padding-bottom: var(--tv-a2); }
  .quellen { display: flex; flex-wrap: wrap; gap: 6px; }
  .anzahl { color: var(--tv-text-3); font-size: var(--tv-gr-marke); }
  h2 { margin: 0; font-size: var(--tv-gr-titel); }
  .gruppenkopf { display: flex; align-items: center; justify-content: space-between; gap: var(--tv-a2); }
  .gruppenname { display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .gruppenname .zahl { font-size: var(--tv-gr-klein); font-weight: 500; margin-left: var(--tv-a2); }
  .leiste { display: flex; align-items: center; gap: var(--tv-a2); flex-wrap: wrap; min-height: 34px; }
  .titel { flex: 1; min-height: 0; overflow-y: auto; }
  .frueher { width: 100%; justify-content: center; }
  .zeile { display: grid; grid-template-columns: 40px minmax(0, 1fr) auto 32px; gap: var(--tv-a2); align-items: center;
           padding: 4px 6px; border-radius: var(--tv-ecke); cursor: grab; user-select: none; }
  .zeile:hover { background: var(--tv-flaeche); }
  .zeile.gewaehlt { background: rgba(var(--tv-akzent-rgb), 0.14); }
  .zeile.drin .t { color: var(--tv-text-2); }
  .zeile:focus-visible { outline: 2px solid var(--tv-akzent); outline-offset: -2px; }
  .zeile.laeuft .t { color: var(--tv-akzent); }
  .text { min-width: 0; display: flex; flex-direction: column; }
  .text > span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .t { font-weight: 600; }
  .w { font-size: var(--tv-gr-klein); color: var(--tv-text-2); }
  .sammlung { color: var(--tv-text-3); font-size: 13px; }
  .dauer { font-size: var(--tv-gr-klein); color: var(--tv-text-3); }
  .plus { width: 32px; height: 32px; border: 0; border-radius: var(--tv-ecke-klein); background: none; color: var(--tv-text-3);
          cursor: pointer; opacity: 0; }
  .zeile:hover .plus, .zeile.gewaehlt .plus, .plus:focus-visible { opacity: 1; }
  .plus:hover { color: var(--tv-akzent-text); background: var(--tv-akzent); }
  .drin-zeichen { justify-self: center; color: var(--tv-akzent); }
  .gruppe { display: grid; grid-template-columns: 40px minmax(0, 1fr) 24px; gap: var(--tv-a2); align-items: center; width: 100%;
            padding: 4px 6px; border: 0; border-radius: var(--tv-ecke); background: none; color: var(--tv-text); font: inherit;
            text-align: left; cursor: pointer; }
  .gruppe:hover { background: var(--tv-flaeche); }
  .gruppe:focus-visible { outline: 2px solid var(--tv-akzent); outline-offset: -2px; }
  .bild { width: 40px; height: 40px; border-radius: var(--tv-ecke-klein); overflow: hidden; background: var(--tv-mulde);
          display: grid; place-items: center; color: var(--tv-art-musik); }
  .bild img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .weiter { color: var(--tv-text-3); justify-self: center; }
  /* Schmale Spalte (Baukasten um 1000 px): Quellen ohne Zeichen, der Hinweis steht an jeder Zeile (title) */
  @container (max-width: 440px) {
    .quellen { gap: 4px; }
    .quellen .tv-chip { padding: 0 8px; }
    .quellen i { display: none; }
    .auswahl:has(.hinweis) { display: none; }
  }
</style>

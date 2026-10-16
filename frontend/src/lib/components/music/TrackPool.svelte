<!--
  Titelquelle des Listen-Baukastens: alle Titel aus Musikvideos und eigener
  Sammlung (eigene Wahl, unabhängig von der Quelle der Musikseite),
  durchsuchbar und seitenweise. Schnell in die Liste rechts:
  ziehen, doppelt klicken oder +. Klick wählt aus (Umschalt: von bis), dann
  wandert die ganze Auswahl auf einmal. Was schon in der Liste steht, ist
  markiert.
-->
<script>
  import { onMount } from 'svelte';
  import { api } from '../../api/client.js';
  import { coverUrl } from '../../utils/musicTrack.js';
  import { formatDuration } from '../../utils/format.js';
  import { createListLoader } from '../../utils/listLoader.svelte.js';
  import { infiniteScroll } from '../../utils/infiniteScroll.js';
  import { setDraggedTracks } from '../../utils/trackDrag.js';
  import { isRemoved, onMusicChange } from '../../utils/musicChanges.js';
  import { toast } from '../../stores/notifications.js';

  // inList: Kennungen, die schon in der Liste stehen; onAdd(titel): ans Ende der Liste
  let { inList = new Set(), canAdd = false, onAdd = () => {} } = $props();

  const PAGE = 100;
  const SORTS = [['artist', 'Interpret'], ['title', 'Titel'], ['added', 'Neu']];
  const SOURCES = [['alle', 'Alles'], ['videos', 'Musikvideos'], ['sammlung', 'Sammlung']];
  const DEBOUNCE_MS = 300;

  let query = $state('');
  let sort = $state('artist');
  let source = $state('alle');
  let chosen = $state(new Set());
  let anchor = -1;                 // letzter Klick, für Umschalt-Klick
  let timer;

  const list = createListLoader(async (page) => {
    const r = await api.musicTracks({ sort, source, q: query.trim(), offset: (page - 1) * PAGE, limit: PAGE });
    return { items: r.items, total: r.total };
  });

  let picked = $derived(list.items.filter((t) => chosen.has(t.id)));

  function reload() {
    chosen = new Set();
    anchor = -1;
    list.load(true).catch((e) => toast.error(e.message));
  }

  function onSearch() {
    clearTimeout(timer);
    timer = setTimeout(reload, DEBOUNCE_MS);
  }

  function chooseSort(value) {
    sort = value;
    reload();
  }

  function chooseSource(value) {
    source = value;
    reload();
  }

  function click(e, index) {
    const id = list.items[index].id;
    const next = new Set(chosen);
    if (e.shiftKey && anchor >= 0) {
      const [from, to] = anchor < index ? [anchor, index] : [index, anchor];
      for (const track of list.items.slice(from, to + 1)) next.add(track.id);
    } else if (!next.delete(id)) {
      next.add(id);
    }
    anchor = index;
    chosen = next;
  }

  // Gewählte Zeile: die ganze Auswahl, sonst nur diese
  const cargo = (track) => (chosen.has(track.id) ? picked : [track]);

  function add(tracks) {
    if (!canAdd) return toast.info('Rechts erst eine Liste wählen oder anlegen');
    onAdd(tracks);
    chosen = new Set();
  }

  onMount(() => {
    list.load(true).catch((e) => toast.error(e.message));
    return onMusicChange((change) => {
      const gone = isRemoved(change);
      list.items = list.items.filter((t) => !gone(t));
      if (change.restored) reload();
    });
  });
</script>

<section class="quelle">
  <div class="kopf">
    <h2>Alle Titel <span class="zahl tv-schwach">{list.total.toLocaleString('de-DE')}</span></h2>
    <input class="tv-eingabe" bind:value={query} oninput={onSearch} placeholder="Titel, Interpret, Album" />
    <div class="leiste">
      {#each SOURCES as [value, label]}
        <button class="tv-chip" class:aktiv={source === value} onclick={() => chooseSource(value)}>{label}</button>
      {/each}
      <span class="tv-trenner"></span>
      {#each SORTS as [value, label]}
        <button class="tv-chip" class:aktiv={sort === value} onclick={() => chooseSort(value)}>{label}</button>
      {/each}
    </div>
    <div class="leiste">
      {#if chosen.size}
        <button class="tv-knopf haupt klein" onclick={() => add(picked)} disabled={!canAdd}>
          <i class="fa-solid fa-plus"></i> <span class="zahl">{chosen.size}</span> hinzufügen</button>
        <button class="tv-knopf ohne klein" onclick={() => { chosen = new Set(); anchor = -1; }}>Auswahl aufheben</button>
      {:else}
        <span class="tv-schwach tv-klein">Ziehen, Doppelklick oder +; Klick wählt aus, Umschalt-Klick von bis</span>
      {/if}
    </div>
  </div>

  <div class="titel" data-scroll-root>
    {#if list.loading}
      <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt ...</div>
    {:else}
      {#each list.items as track, i (track.id)}
        <div class="zeile" class:gewaehlt={chosen.has(track.id)} class:drin={inList.has(track.id)} role="button" tabindex="0"
             draggable="true" ondragstart={(e) => setDraggedTracks(e, cargo(track))}
             onclick={(e) => click(e, i)} ondblclick={() => add([track])}
             onkeydown={(e) => { if (e.key === 'Enter') add(cargo(track)); else if (e.key === ' ') { e.preventDefault(); click(e, i); } }}
             title={inList.has(track.id) ? 'Schon in der Liste' : 'Ziehen oder doppelt klicken: in die Liste'}>
          <img src={coverUrl(track)} alt="" loading="lazy" draggable="false" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
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
        <div class="tv-leer">Keine Titel gefunden.</div>
      {/each}
      <div use:infiniteScroll={{ onLoadMore: list.loadMore, canLoad: list.canLoad }}></div>
    {/if}
  </div>
</section>

<style>
  .quelle { min-height: 0; display: flex; flex-direction: column; }
  .kopf { flex: none; display: flex; flex-direction: column; gap: var(--tv-a2); padding-bottom: var(--tv-a2); }
  h2 { margin: 0; font-size: var(--tv-gr-titel); }
  .leiste { display: flex; align-items: center; gap: var(--tv-a2); flex-wrap: wrap; min-height: 34px; }
  .titel { flex: 1; min-height: 0; overflow-y: auto; }
  .zeile { display: grid; grid-template-columns: 40px minmax(0, 1fr) auto 32px; gap: var(--tv-a2); align-items: center;
           padding: 4px 6px; border-radius: var(--tv-ecke); cursor: grab; user-select: none; }
  .zeile:hover { background: var(--tv-flaeche); }
  .zeile.gewaehlt { background: rgba(var(--tv-akzent-rgb), 0.14); }
  .zeile.drin .t { color: var(--tv-text-2); }
  .zeile:focus-visible { outline: 2px solid var(--tv-akzent); outline-offset: -2px; }
  img { width: 40px; height: 40px; object-fit: cover; border-radius: var(--tv-ecke-klein); background: var(--tv-mulde); }
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
</style>

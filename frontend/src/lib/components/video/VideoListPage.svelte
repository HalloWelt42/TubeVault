<!--
  TubeVault - Videoliste als Seite (Bibliothek, Archiv; HELF-71)

  Eine Komponente für alle Seiten, die die Videos des Bestands mit Filtern,
  Sortierung, Schlagwörtern, Auswahl und Nachladen beim Rollen zeigen. Was eine
  Seite ausmacht, kommt als Parameter: welcher Teil des Bestands (archived),
  Titel, Filterleiste und die Aktionen für die Auswahl. Darstellung, Laden und
  Verhalten gibt es damit nur einmal.

  Nachgeladen wird ab dem letzten Eintrag (Cursor, videoPage), nicht ab einem
  Versatz: archiviert man beim Rollen Kacheln, fehlt dahinter nichts.

  Parameter:
    routeKey      Schlüssel für gespeicherte Filter ('library', 'archives')
    title, icon   Kopf der Seite
    archived      false: Bibliothek, true: Archiv
    showMusic     Musikfilter in der Filterleiste
    emptyText     Text, wenn der Teil des Bestands leer ist
    batch         Snippet mit den Knöpfen für die Auswahl; bekommt
                  { ids, done } - done() leert die Auswahl und lädt neu
-->
<script>
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';
  import { getSettingNum } from '../../stores/settings.js';
  import { onVideoMutation } from '../../utils/videoMutations.js';
  import { infiniteScroll } from '../../utils/infiniteScroll.js';
  import { createListLoader } from '../../utils/listLoader.svelte.js';
  import { createVideoListFilters } from '../../utils/videoListFilters.svelte.js';
  import { videoPage } from '../../utils/videoPages.js';
  import VideoCard from './VideoCard.svelte';
  import MultiFilter from '../common/MultiFilter.svelte';
  import PageHeader from '../common/PageHeader.svelte';
  import TagFilterBar from '../common/TagFilterBar.svelte';
  import BatchToolbar from '../common/BatchToolbar.svelte';

  let { routeKey, title, icon = '', archived = false, showMusic = false, emptyText = '', batch = null } = $props();

  const SORTS = [['created_at', 'Geladen'], ['upload_date', 'Hochgeladen'], ['is_favorite', 'Favoriten'], ['title', 'Titel'],
                 ['duration', 'Dauer'], ['file_size', 'Größe'], ['rating', 'Bewertung'], ['play_count', 'Abgespielt']];

  // Sortierung, Schlagwörter und Mehrfachfilter: eine Wahrheit (URL > gespeicherte Auswahl)
  // svelte-ignore state_referenced_locally
  const filters = createVideoListFilters(routeKey);

  let selectMode = $state(false);
  let selected = $state(new Set());
  let filterRef;
  let allTags = $state([]);
  let totalBytes = $state(0);          // Größe aller Treffer (vom Backend)
  let languageCounts = $state([]);     // Zähler je Sprache für den Filter (mit allen übrigen Filtern)
  let loadTimer = null;

  async function loadTags() {
    // Schlagwörter wie die gefilterte Liste, nicht alle des Bestands
    try { allTags = (await api.getAllTags({ archived, ...filters.tagParams() })) || []; } catch {}
  }

  const list = createListLoader(async (page, after) => {
    const params = {
      per_page: getSettingNum('general.videos_per_page', 24),
      is_archived: archived, ...filters.apiParams(),
      ...(!after ? { with_language_counts: true } : {}),
    };
    try {
      const seite = await videoPage(params, page, after);
      if (!after) {
        totalBytes = seite.result.total_bytes || 0;
        languageCounts = seite.result.language_counts || [];
      }
      return seite;
    } catch (e) {
      toast.error('Fehler: ' + e.message);
      if (after) throw e;            // Nachladen: die Liste bleibt, der nächste Anstoß versucht es noch einmal
      return { items: [], total: 0 };
    }
  });

  // Mehrere Filteränderungen kurz hintereinander: nur einmal laden
  function loadDebounced() {
    clearTimeout(loadTimer);
    loadTimer = setTimeout(() => list.load(true), 80);
  }

  function clearFilters() {
    filters.clearTags();
    filterRef?.reset();   // leert die Leiste und meldet den leeren Filter zurück
  }

  function toggleSelect(id) {
    const s = new Set(selected);
    if (s.has(id)) s.delete(id); else s.add(id);
    selected = s;
  }

  function toggleSelectMode() {
    selectMode = !selectMode;
    selected = new Set();
  }

  // Nach einer Aktion auf der Auswahl: Auswahl leeren, neu laden
  function done() {
    selected = new Set();
    selectMode = false;
    list.load(true);
    loadTags();
  }

  // Eine Kachel hat sich selbst aus diesem Teil des Bestands genommen (archiviert, dearchiviert)
  function removed(id) {
    list.items = list.items.filter((v) => v.id !== id);
    list.total = Math.max(0, list.total - 1);
    if (selected.has(id)) toggleSelect(id);
  }

  // Änderungen aus anderen Ansichten (Wiedergabe: archivieren, löschen) - beim Zurückkehren frisch
  $effect(() => onVideoMutation(() => { list.load(true); loadTags(); }));

  // Jede Filteränderung: Auswahl sichern (Speicher + URL), Liste und Schlagwörter neu laden
  $effect(() => {
    filters.signature;
    filters.persist();
    loadDebounced();
    loadTags();
  });
</script>

<div class="tv-seite">
 <div class="tv-seitenkopf">
  <PageHeader {title} {icon} count={list.loading && !list.total ? null : list.total} bytes={totalBytes}
              hasFilter={filters.hasActive} onClearFilter={clearFilters}>
    <button class="tv-knopf" class:aktiv={selectMode} onclick={toggleSelectMode}>
      <i class="fa-{selectMode ? 'solid fa-xmark' : 'regular fa-square-check'}"></i>
      {selectMode ? 'Abbrechen' : 'Auswählen'}
    </button>
  </PageHeader>

  {#if selectMode}
    <BatchToolbar selectedCount={selected.size} totalCount={list.items.length}
                  onSelectAll={() => selected = new Set(list.items.map((v) => v.id))}>
      {@render batch?.({ ids: [...selected], done })}
    </BatchToolbar>
  {/if}

  <MultiFilter bind:this={filterRef} showSearch={true} showTypes={true} showChannels={true} showCategories={true}
               {showMusic} showLanguages={true} {languageCounts}
               initial={filters.multi} onchange={filters.setMulti} />

  <div class="tv-filter">
    <span class="tv-etikett">Sortieren</span>
    {#each SORTS as [field, label]}
      <button class="tv-chip" class:aktiv={filters.sortBy === field} onclick={() => filters.changeSort(field)}>
        {label}
        {#if filters.sortBy === field}
          <i class="fa-solid {filters.sortOrder === 'desc' ? 'fa-arrow-down-long' : 'fa-arrow-up-long'}"
             title={filters.sortOrder === 'desc' ? 'absteigend' : 'aufsteigend'}></i>
        {/if}
      </button>
    {/each}
  </div>

  <!-- Die Leiste zeigt nur die häufigsten Schlagwörter (zwei Zeilen), der Rest über die Suche -->
  <TagFilterBar {allTags} activeTags={filters.activeTags} onToggle={filters.toggleTag} />
 </div>

 <!-- Nur die Liste rollt -->
 <div class="tv-rollfeld" data-scroll-root>
  {#if list.loading}
    <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt ...</div>
  {:else if list.items.length > 0}
    <div class="tv-raster">
      {#each list.items as video (video.id)}
        <div class="auswahl" class:gewaehlt={selected.has(video.id)}>
          {#if selectMode}
            <button class="auswahl-haken" onclick={() => toggleSelect(video.id)}
                    title={selected.has(video.id) ? 'Abwählen' : 'Auswählen'}>
              <i class="fa-{selected.has(video.id) ? 'solid fa-square-check' : 'regular fa-square'}"></i>
            </button>
          {/if}
          <VideoCard {video} {archived} onUpdate={removed} />
        </div>
      {/each}
    </div>
    <div class="nachlade-marke" use:infiniteScroll={{ onLoadMore: list.loadMore, canLoad: list.canLoad }}></div>
    {#if list.loadingMore}
      <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt weitere ...</div>
    {/if}
  {:else}
    <div class="tv-leer">
      {#if filters.hasActive}
        <p>Keine Videos für diesen Filter.</p>
        <button class="tv-knopf" style="margin-top: var(--tv-a3)" onclick={clearFilters}>Filter zurücksetzen</button>
      {:else}
        <p>{emptyText}</p>
      {/if}
    </div>
  {/if}
 </div>
</div>

<style>
  /* Gestaltung nach mockups/bibliothek.html */
  .tv-raster { margin-top: var(--tv-a3); }
  .nachlade-marke { height: 1px; }

  /* Auswahl: Haken oben rechts auf dem Bild, gewählte Kachel umrandet */
  .auswahl { position: relative; }
  .auswahl-haken {
    position: absolute; top: 8px; right: 8px; z-index: 4;
    width: 34px; height: 34px; display: grid; place-items: center;
    background: var(--tv-schleier); border: none; border-radius: var(--tv-ecke);
    color: var(--tv-text); font-size: 18px; cursor: pointer;
  }
  .auswahl.gewaehlt .auswahl-haken { color: var(--tv-akzent); }
  .auswahl.gewaehlt :global(.bild) { outline: 2px solid var(--tv-akzent); outline-offset: -2px; }
</style>

<!--
  TubeVault – Archive v1.5.91
  Archivierte Videos: Gleiche Such-/Filter-Logik wie Bibliothek.
  Videos hier sind aus der Bibliothek ausgeblendet.
  © HalloWelt42 – Private Nutzung
-->
<script>
  import { api } from '../lib/api/client.js';
  import { searchQuery } from '../lib/stores/app.js';
  import { toast } from '../lib/stores/notifications.js';
  import { getSettingNum } from '../lib/stores/settings.js';
  import { getFilter, saveFilters } from '../lib/stores/filterPersist.js';
  import { onVideoMutation } from '../lib/utils/videoMutations.js';
  import VideoCard from '../lib/components/video/VideoCard.svelte';
  import MultiFilter from '../lib/components/common/MultiFilter.svelte';
  import { infiniteScroll } from '../lib/utils/infiniteScroll.js';
  import { createListLoader } from '../lib/utils/listLoader.svelte.js';
  import PageHeader from '../lib/components/common/PageHeader.svelte';
  import TagFilterBar from '../lib/components/common/TagFilterBar.svelte';
  import BatchToolbar from '../lib/components/common/BatchToolbar.svelte';

  let sortBy = $state(getFilter('archives', 'sortBy', 'upload_date'));
  let sortOrder = $state(getFilter('archives', 'sortOrder', 'desc'));
  let selectMode = $state(false);
  let selected = $state(new Set());

  let activeTags = $state(getFilter('archives', 'activeTags', []));
  let allTags = $state([]);
  let multiFilter = $state(getFilter('archives', 'multiFilter', { types: null, channels: null, categories: null }));

  async function loadTags() {
    // Tags nur für die im Archiv gefilterten Videos — nicht global.
    try {
      const filters = {
        archived: true,
        video_types: multiFilter.types || undefined,
        channel_ids: multiFilter.channels || undefined,
        category_ids: multiFilter.categories || undefined,
      };
      allTags = (await api.getAllTags(filters)) || [];
    } catch {}
  }

  // Zentraler List-Loader: page ist darin bewusst nicht-reaktiv,
  // dadurch kann der Filter-$effect das Nachladen nicht mehr zurücksetzen.
  const list = createListLoader(async (page) => {
    const params = { page, per_page: getSettingNum('general.videos_per_page', 24), sort_by: sortBy, sort_order: sortOrder, is_archived: true };
    const q = $searchQuery;
    if (q) params.search = q;
    if (activeTags.length > 0) params.tags = activeTags.join(',');
    if (multiFilter.types) params.video_types = multiFilter.types;
    if (multiFilter.channels) params.channel_ids = multiFilter.channels;
    if (multiFilter.categories) params.category_ids = multiFilter.categories;
    try {
      const result = await api.getVideos(params);
      return { items: result.videos || [], total: result.total || 0 };
    } catch (e) { toast.error('Fehler: ' + e.message); return { items: [], total: 0 }; }
  });

  function toggleTag(tag) { activeTags = activeTags.includes(tag) ? activeTags.filter(t => t !== tag) : [...activeTags, tag]; }
  function clearFilters() { activeTags = []; multiFilter = { types: null, channels: null, categories: null }; }
  function onFilterChange(f) {
    multiFilter = f;
    loadTags();
  }
  function changeSort(field) {
    if (sortBy === field) sortOrder = sortOrder === 'desc' ? 'asc' : 'desc';
    else { sortBy = field; sortOrder = 'desc'; }
  }

  // ─── Dearchivieren ───
  async function unarchiveVideo(id) {
    try {
      await api.unarchiveVideo(id);
      list.items = list.items.filter(v => v.id !== id);
      list.total -= 1;
      toast.success('Dearchiviert');
    } catch (e) { toast.error(e.message); }
  }

  async function unarchiveSelected() {
    if (selected.size === 0) return;
    try {
      await api.archiveBatch([...selected], true);
      toast.success(`${selected.size} Video(s) dearchiviert`);
      selected = new Set();
      selectMode = false;
      list.load(true);
    } catch (e) { toast.error(e.message); }
  }

  function toggleSelect(id) {
    const s = new Set(selected);
    if (s.has(id)) s.delete(id); else s.add(id);
    selected = s;
  }

  $effect(() => { loadTags(); });
  $effect(() => {
    // Filter-Änderungen → Liste von vorne laden. list.load() liest intern
    // kein reaktives page mehr — Nachladen kann den Effect nicht triggern.
    $searchQuery; sortBy; sortOrder; activeTags;
    multiFilter.types; multiFilter.channels; multiFilter.categories;
    // Alle Filter persistieren (User-Wunsch: Auswahl bleibt erhalten)
    saveFilters('archives', {
      sortBy, sortOrder,
      activeTags: [...activeTags],
      multiFilter: { ...multiFilter },
    });
    list.load(true);
  });
  // Reagiere auf Video-Mutationen aus anderen Views (z.B. Watch → Dearchive)
  $effect(() => onVideoMutation(() => { list.load(true); loadTags(); }));

  let hasActiveFilter = $derived(activeTags.length > 0 || multiFilter.types || multiFilter.channels || multiFilter.categories);
</script>

<div class="library">
  <PageHeader title="Archiv" icon="fa-solid fa-box-archive" count={list.total} hasFilter={!!hasActiveFilter} onClearFilter={clearFilters}>
    <button class="btn-select" class:active={selectMode} onclick={() => { selectMode = !selectMode; selected = new Set(); }}>
      <i class="fa-solid {selectMode ? 'fa-xmark' : 'fa-check-double'}"></i>
      {selectMode ? 'Abbrechen' : 'Auswählen'}
    </button>
  </PageHeader>

  {#if selectMode}
    <BatchToolbar selectedCount={selected.size} totalCount={list.items.length}
                  onSelectAll={() => selected = new Set(list.items.map(v => v.id))}>
      <button class="bulk-btn" onclick={unarchiveSelected}><i class="fa-solid fa-box-open"></i> Dearchivieren</button>
    </BatchToolbar>
  {/if}

  <MultiFilter showTypes={true} showChannels={true} showCategories={true} onchange={onFilterChange} />

  <TagFilterBar {allTags} {activeTags} onToggle={toggleTag} />

  <div class="toolbar">
    <div class="sort-group">
      <span class="toolbar-label">Sortieren:</span>
      {#each [['created_at', 'Datum'], ['upload_date', 'Upload'], ['is_favorite', 'Favoriten'], ['title', 'Titel'], ['duration', 'Dauer'], ['file_size', 'Größe'], ['rating', 'Bewertung'], ['play_count', 'Abgespielt']] as [field, label]}
        <button class="sort-btn" class:active={sortBy === field} onclick={() => changeSort(field)}>
          {label}
          {#if sortBy === field}<span class="sort-arrow">{sortOrder === 'desc' ? '↓' : '↑'}</span>{/if}
        </button>
      {/each}
    </div>
  </div>

  {#if list.loading}
    <div class="loading"><i class="fa-solid fa-spinner fa-spin"></i> Laden…</div>
  {:else if list.items.length > 0}
    <div class="video-grid">
      {#each list.items as video (video.id)}
        <div class="archive-card-wrap" class:selected={selected.has(video.id)}>
          {#if selectMode}
            <button class="select-check" onclick={() => toggleSelect(video.id)}>
              {#if selected.has(video.id)}
                <i class="fa-solid fa-square-check"></i>
              {:else}
                <i class="fa-regular fa-square"></i>
              {/if}
            </button>
          {/if}
          <VideoCard {video} showArchiveBtn={false} onUpdate={() => list.load(true)} />
          <button class="btn-unarchive" onclick={() => unarchiveVideo(video.id)} title="Dearchivieren">
            <i class="fa-solid fa-box-open"></i>
          </button>
        </div>
      {/each}
    </div>
    <div class="scroll-sentinel" use:infiniteScroll={{ onLoadMore: list.loadMore, canLoad: list.canLoad }}></div>
    {#if list.loadingMore}<div class="loading-more"><i class="fa-solid fa-spinner fa-spin"></i> Lade mehr…</div>{/if}
  {:else}
    <div class="empty">
      {#if hasActiveFilter}
        <p>Keine archivierten Videos für diesen Filter.</p>
        <button class="btn-reset" onclick={clearFilters}>Filter zurücksetzen</button>
      {:else}
        <i class="fa-solid fa-box-open empty-icon"></i>
        <p>Keine archivierten Videos.</p>
        <p class="empty-hint">Videos über das Kontextmenü oder den Player archivieren.</p>
      {/if}
    </div>
  {/if}
</div>

<style>
  .library { padding: 24px; max-width: none; }
  .btn-select { padding: 5px 12px; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 6px; color: var(--text-secondary); font-size: 0.78rem; cursor: pointer; display: flex; align-items: center; gap: 5px; }
  .btn-select.active { border-color: var(--accent-primary); color: var(--accent-primary); }

  .toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }
  .toolbar-label { font-size: 0.8rem; color: var(--text-tertiary); }
  .sort-group { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
  .sort-btn { display: flex; align-items: center; gap: 4px; padding: 5px 12px; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 6px; color: var(--text-secondary); font-size: 0.8rem; cursor: pointer; transition: all 0.15s; }
  .sort-btn:hover { border-color: var(--accent-primary); color: var(--text-primary); }
  .sort-btn.active { background: var(--accent-muted); color: var(--accent-primary); border-color: var(--accent-primary); }
  .sort-arrow { font-size: 0.7rem; }

  .video-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }

  /* Archive Card Wrapper */
  .archive-card-wrap { position: relative; }
  .archive-card-wrap.selected { outline: 2px solid var(--accent-primary); border-radius: 12px; }
  .select-check { position: absolute; top: 8px; left: 8px; z-index: 3; background: rgba(0,0,0,0.6); border: none; border-radius: 4px; color: #fff; font-size: 1.1rem; cursor: pointer; padding: 2px 4px; }
  .btn-unarchive { position: absolute; top: 8px; right: 8px; z-index: 3; width: 30px; height: 30px; border-radius: 50%; background: rgba(0,0,0,0.7); color: #fff; border: none; cursor: pointer; font-size: 0.75rem; display: flex; align-items: center; justify-content: center; opacity: 0; transition: opacity 0.15s; }
  .archive-card-wrap:hover .btn-unarchive { opacity: 1; }
  .btn-unarchive:hover { background: var(--accent-primary); }

  .loading, .empty { padding: 60px 20px; text-align: center; color: var(--text-tertiary); }
  .empty-icon { font-size: 2.5rem; display: block; margin-bottom: 12px; }
  .empty-hint { font-size: 0.8rem; margin-top: 4px; }
  .btn-reset { margin-top: 12px; padding: 7px 18px; background: var(--accent-primary); color: #fff; border: none; border-radius: 8px; font-size: 0.82rem; cursor: pointer; }
</style>

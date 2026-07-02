<script>
  import { api } from '../lib/api/client.js';
  import { route, updateParams } from '../lib/router/router.js';
  import { searchQuery } from '../lib/stores/app.js';
  import { toast } from '../lib/stores/notifications.js';
  import { getSettingNum } from '../lib/stores/settings.js';
  import { onVideoMutation } from '../lib/utils/videoMutations.js';
  import { getFilter, saveFilters } from '../lib/stores/filterPersist.js';
  import { infiniteScroll } from '../lib/utils/infiniteScroll.js';
  import { createListLoader } from '../lib/utils/listLoader.svelte.js';
  import VideoCard from '../lib/components/video/VideoCard.svelte';
  import MultiFilter from '../lib/components/common/MultiFilter.svelte';
  import ConfirmDialog from '../lib/components/common/ConfirmDialog.svelte';
  import AddToPlaylistDialog from '../lib/components/common/AddToPlaylistDialog.svelte';
  import PageHeader from '../lib/components/common/PageHeader.svelte';
  import TagFilterBar from '../lib/components/common/TagFilterBar.svelte';
  import BatchToolbar from '../lib/components/common/BatchToolbar.svelte';

  let sortBy = $state(getFilter('library', 'sortBy', 'upload_date'));
  let sortOrder = $state(getFilter('library', 'sortOrder', 'desc'));

  let selectMode = $state(false);
  let selected = $state(new Set());
  let confirmRef;
  let addToPlaylistVideoId = $state(null);

  let activeTags = $state(getFilter('library', 'activeTags', []));
  let allTags = $state([]);
  let multiFilter = $state(getFilter('library', 'multiFilter', { types: null, channels: null, categories: null }));
  let _loadTimer = null;

  const PER_PAGE = getSettingNum('general.videos_per_page', 24);

  async function loadTags() {
    // Tags werden gefiltert wie die aktuelle Video-Liste, damit nicht global
    // 64k Tags angezeigt werden, wenn nur 20 Videos gefiltert sind.
    try {
      const filters = {
        archived: false,
        video_types: multiFilter.types || undefined,
        channel_ids: multiFilter.channels || undefined,
        category_ids: multiFilter.categories || undefined,
      };
      allTags = (await api.getAllTags(filters)) || [];
    } catch {}
  }

  // Zentraler List-Loader (page darin nicht-reaktiv, Stale-Guard inklusive)
  const list = createListLoader(async (page) => {
    const params = { page, per_page: PER_PAGE, sort_by: sortBy, sort_order: sortOrder, is_archived: false };
    const q = $searchQuery;
    if (q) params.search = q;
    if (activeTags.length > 0) params.tags = activeTags.join(',');
    if (multiFilter.types) params.video_types = multiFilter.types;
    if (multiFilter.channels) params.channel_ids = multiFilter.channels;
    if (multiFilter.categories) params.category_ids = multiFilter.categories;
    if (multiFilter.is_music) params.is_music = true;
    try {
      const result = await api.getVideos(params);
      return { items: result.videos || [], total: result.total || 0 };
    } catch (e) { toast.error('Fehler: ' + e.message); return { items: [], total: 0 }; }
  });

  // Debounced Reset-Load – verhindert Request-Flut bei schnellen Filter-Änderungen
  function loadDebounced() {
    clearTimeout(_loadTimer);
    _loadTimer = setTimeout(() => list.load(true), 80);
  }

  // ── URL-Sync: Lese Filter aus URL-Params ──
  function syncFromUrl() {
    const p = $route.params;
    if (p.sort && p.sort !== sortBy) sortBy = p.sort;
    if (p.order && p.order !== sortOrder) sortOrder = p.order;
    const urlTags = p.tags ? p.tags.split(',') : [];
    if (JSON.stringify(urlTags) !== JSON.stringify(activeTags)) activeTags = urlTags;
    const newTypes = p.types || null;
    const newChannels = p.channels || null;
    if (newTypes !== multiFilter.types || newChannels !== multiFilter.channels) {
      multiFilter = { ...multiFilter, types: newTypes, channels: newChannels };
    }
  }

  function syncToUrl() {
    updateParams({
      sort: sortBy !== 'upload_date' ? sortBy : null,
      order: sortOrder !== 'desc' ? sortOrder : null,
      tags: activeTags.length > 0 ? activeTags.join(',') : null,
      types: multiFilter.types || null,
      channels: multiFilter.channels || null,
    });
  }

  function toggleTag(tag) {
    activeTags = activeTags.includes(tag) ? activeTags.filter(t => t !== tag) : [...activeTags, tag];
    syncToUrl();
  }

  function clearFilters() {
    activeTags = []; multiFilter = { types: null, channels: null, categories: null };
    syncToUrl();
  }

  function onFilterChange(f) {
    multiFilter = f;
    syncToUrl();
    // Tags an neuen Filter anpassen (z.B. nur Tags der Shorts wenn video_type=short)
    loadTags();
  }

  function changeSort(field) {
    if (sortBy === field) sortOrder = sortOrder === 'desc' ? 'asc' : 'desc';
    else { sortBy = field; sortOrder = 'desc'; }
    syncToUrl();
  }

  // ─── Bulk-Aktionen ───
  function toggleSelect(id) { const s = new Set(selected); if (s.has(id)) s.delete(id); else s.add(id); selected = s; }
  function selectAll() { selected = new Set(list.items.map(v => v.id)); }
  async function archiveSelected() {
    if (selected.size === 0) return;
    try { await api.archiveBatch([...selected], false); toast.success(`${selected.size} Video(s) archiviert`); selected = new Set(); selectMode = false; list.load(true); } catch (e) { toast.error(e.message); }
  }
  async function deleteSelected() {
    if (selected.size === 0) return;
    const ok = await confirmRef.ask(`${selected.size} Videos löschen?`, 'Alle ausgewählten Videos werden unwiderruflich gelöscht.');
    if (!ok) return;
    let deleted = 0; for (const id of selected) { try { await api.deleteVideo(id); deleted++; } catch {} }
    toast.success(`${deleted} Video(s) gelöscht`); selected = new Set(); selectMode = false; list.load(true);
  }
  async function setTypeBulk(videoType) {
    if (selected.size === 0) return;
    const labels = { video: 'Video', short: 'Short', live: 'Live' };
    try { const res = await api.setTypeBatch([...selected], videoType); toast.success(`${res.updated} Video(s) → ${labels[videoType]}`); selected = new Set(); selectMode = false; list.load(true); } catch (e) { toast.error(e.message); }
  }

  // Tag-Filter Event von Watch
  $effect(() => {
    function onTagFilter(e) { const tag = e.detail; if (!activeTags.includes(tag)) { activeTags = [...activeTags, tag]; syncToUrl(); } }
    window.addEventListener('tubevault:tag-filter', onTagFilter);
    return () => window.removeEventListener('tubevault:tag-filter', onTagFilter);
  });

  // Init: URL-Params lesen, dann laden
  $effect(() => { syncFromUrl(); loadTags(); });

  // Auf globale Video-Mutationen (Archive/Delete aus Watch-View) reagieren —
  // Liste neu laden, damit beim Zurück-Navigieren der neue Stand zu sehen ist.
  $effect(() => onVideoMutation(() => { list.load(true); loadTags(); }));

  // Laden bei Filter-Änderung (debounced um Request-Flut zu verhindern)
  // Alle Auswahlen persistieren (User-Wunsch: was ich auswähle bleibt beim Wiederkommen)
  $effect(() => {
    $searchQuery; sortBy; sortOrder; activeTags;
    multiFilter.types; multiFilter.channels; multiFilter.categories;
    saveFilters('library', {
      sortBy, sortOrder,
      activeTags: [...activeTags],
      multiFilter: { ...multiFilter },
    });
    loadDebounced();
  });

  let hasActiveFilter = $derived(activeTags.length > 0 || multiFilter.types || multiFilter.channels || multiFilter.categories || multiFilter.is_music);
</script>

<div class="library">
  <PageHeader title="Bibliothek" count={list.total} hasFilter={!!hasActiveFilter} onClearFilter={clearFilters}>
    <button class="btn-select" class:active={selectMode} onclick={() => { selectMode = !selectMode; selected = new Set(); }}>
      <i class="fa-solid {selectMode ? 'fa-xmark' : 'fa-check-double'}"></i>
      {selectMode ? 'Abbrechen' : 'Auswählen'}
    </button>
  </PageHeader>

  {#if selectMode}
    <BatchToolbar selectedCount={selected.size} totalCount={list.items.length} onSelectAll={selectAll}>
      <button class="bulk-btn bulk-type" onclick={() => setTypeBulk('video')}><i class="fa-solid fa-play"></i> → Video</button>
      <button class="bulk-btn bulk-type" onclick={() => setTypeBulk('short')}><i class="fa-solid fa-mobile-screen"></i> → Short</button>
      <button class="bulk-btn bulk-type" onclick={() => setTypeBulk('live')}><i class="fa-solid fa-tower-broadcast"></i> → Live</button>
      <span class="bulk-sep">|</span>
      <button class="bulk-btn" onclick={archiveSelected}><i class="fa-solid fa-box-archive"></i> Archivieren</button>
      <button class="bulk-btn bulk-danger" onclick={deleteSelected}><i class="fa-regular fa-trash-can"></i> Löschen</button>
    </BatchToolbar>
  {/if}

  <MultiFilter showTypes={true} showChannels={true} showCategories={true} showMusic={true} onchange={onFilterChange} />

  <TagFilterBar {allTags} {activeTags} onToggle={toggleTag} />

  <div class="toolbar">
    <div class="sort-group">
      <span class="toolbar-label">Sortieren:</span>
      {#each [['created_at','Datum'],['upload_date','Upload'],['is_favorite','Favoriten'],['title','Titel'],['duration','Dauer'],['file_size','Größe'],['rating','Bewertung'],['play_count','Abgespielt']] as [field, label]}
        <button class="sort-btn" class:active={sortBy === field} onclick={() => changeSort(field)}>
          {label} {#if sortBy === field}<span class="sort-arrow">{sortOrder === 'desc' ? '↓' : '↑'}</span>{/if}
        </button>
      {/each}
    </div>
  </div>

  {#if list.loading}
    <div class="loading">Laden…</div>
  {:else if list.items.length > 0}
    <div class="video-grid">
      {#each list.items as video (video.id)}
        {#if selectMode}
          <div class="select-card-wrap" class:selected={selected.has(video.id)}>
            <button class="select-check" onclick={() => toggleSelect(video.id)}>
              {#if selected.has(video.id)}<i class="fa-solid fa-square-check"></i>{:else}<i class="fa-regular fa-square"></i>{/if}
            </button>
            <VideoCard {video} onUpdate={() => list.load(true)} />
          </div>
        {:else}
          <VideoCard {video} />
        {/if}
      {/each}
    </div>
    <div class="scroll-sentinel" use:infiniteScroll={{ onLoadMore: list.loadMore, canLoad: list.canLoad }}></div>
    {#if list.loadingMore}
      <div class="loading-more"><i class="fa-solid fa-spinner fa-spin"></i> Lade mehr…</div>
    {/if}
  {:else}
    <div class="empty">
      {#if hasActiveFilter}
        <p>Keine Videos für diesen Filter gefunden.</p>
        <button class="btn-reset" onclick={clearFilters}>Filter zurücksetzen</button>
      {:else}
        <p>Keine Videos gefunden.</p>
      {/if}
    </div>
  {/if}
</div>

<ConfirmDialog bind:this={confirmRef} />
<AddToPlaylistDialog bind:videoId={addToPlaylistVideoId} />

<style>
  .library { padding: 24px; max-width: none; }

  .toolbar { display:flex; align-items:center; gap:12px; margin-bottom:20px; flex-wrap:wrap; }
  .toolbar-label { font-size:0.8rem; color:var(--text-tertiary); }
  .sort-group { display:flex; align-items:center; gap:4px; flex-wrap:wrap; }
  .sort-btn { display:flex; align-items:center; gap:4px; padding:5px 12px; background:var(--bg-secondary); border:1px solid var(--border-primary); border-radius:6px; color:var(--text-secondary); font-size:0.8rem; cursor:pointer; transition:all 0.15s; }
  .sort-btn:hover { border-color:var(--accent-primary); color:var(--text-primary); }
  .sort-btn.active { background:var(--accent-muted); color:var(--accent-primary); border-color:var(--accent-primary); }
  .sort-arrow { font-size:0.7rem; }

  .video-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(260px, 1fr)); gap:16px; }
  .scroll-sentinel { height:1px; }
  .loading-more { text-align:center; padding:16px; color:var(--text-tertiary); font-size:0.82rem; }
  .loading, .empty { padding:60px 20px; text-align:center; color:var(--text-tertiary); }
  .btn-reset { margin-top:12px; padding:7px 18px; background:var(--accent-primary); color:#fff; border:none; border-radius:8px; font-size:0.82rem; cursor:pointer; }

  .btn-select { padding:5px 12px; background:var(--bg-secondary); border:1px solid var(--border-primary); border-radius:6px; color:var(--text-secondary); font-size:0.78rem; cursor:pointer; display:flex; align-items:center; gap:5px; }
  .btn-select.active { border-color:var(--accent-primary); color:var(--accent-primary); }

  .select-card-wrap { position:relative; }
  .select-card-wrap.selected { outline:2px solid var(--accent-primary); border-radius:12px; }
  .select-check { position:absolute; top:8px; left:8px; z-index:4; background:rgba(0,0,0,0.6); border:none; border-radius:4px; color:#fff; font-size:1.1rem; cursor:pointer; padding:2px 4px; }
  .select-card-wrap.selected .select-check { color:var(--accent-primary); }
</style>

<script>
  import { api } from '../lib/api/client.js';
  import { route, updateParams } from '../lib/router/router.js';
  import { searchQuery } from '../lib/stores/app.js';
  import { toast } from '../lib/stores/notifications.js';
  import { getSettingNum } from '../lib/stores/settings.js';
  import { getFilter, saveFilters } from '../lib/stores/filterPersist.js';
  import VideoCard from '../lib/components/video/VideoCard.svelte';
  import MultiFilter from '../lib/components/common/MultiFilter.svelte';
  import ConfirmDialog from '../lib/components/common/ConfirmDialog.svelte';
  import AddToPlaylistDialog from '../lib/components/common/AddToPlaylistDialog.svelte';

  let videos = $state([]);
  let total = $state(0);
  let page = $state(1);
  let hasMore = $state(false);
  let loading = $state(false);
  let loadingMore = $state(false);
  let sortBy = $state(getFilter('library', 'sortBy', 'created_at'));
  let sortOrder = $state(getFilter('library', 'sortOrder', 'desc'));

  let selectMode = $state(false);
  let selected = $state(new Set());
  let confirmRef;
  let addToPlaylistVideoId = $state(null);

  let activeTags = $state([]);
  let allTags = $state([]);
  let showAllTags = $state(false);
  let tagSearch = $state('');
  let multiFilter = $state({ types: null, channels: null, categories: null });
  let _loadTimer = null;

  let sentinelEl = $state(null);
  let observer = null;
  const PER_PAGE = getSettingNum('general.videos_per_page', 24);

  async function loadTags() {
    try { allTags = (await api.getAllTags()) || []; } catch {}
  }

  async function loadVideos(reset = true) {
    if (reset) { page = 1; videos = []; loading = true; }
    else { loadingMore = true; }
    try {
      const params = { page, per_page: PER_PAGE, sort_by: sortBy, sort_order: sortOrder, is_archived: false };
      const q = $searchQuery;
      if (q) params.search = q;
      if (activeTags.length > 0) params.tags = activeTags.join(',');
      if (multiFilter.types) params.video_types = multiFilter.types;
      if (multiFilter.channels) params.channel_ids = multiFilter.channels;
      if (multiFilter.categories) params.category_ids = multiFilter.categories;
      if (multiFilter.is_music) params.is_music = true;
      const result = await api.getVideos(params);
      const newVids = result.videos || [];
      if (reset) { videos = newVids; } else { videos = [...videos, ...newVids]; }
      total = result.total || 0;
      hasMore = videos.length < total;
    } catch (e) { toast.error('Fehler: ' + e.message); }
    finally { loading = false; loadingMore = false; }
  }

  // Debounced loadVideos -  verhindert Request-Flut bei schnellen Filter-Änderungen
  function loadVideosDebounced() {
    clearTimeout(_loadTimer);
    _loadTimer = setTimeout(() => loadVideos(), 80);
  }

  function loadMore() {
    if (loadingMore || !hasMore) return;
    page += 1;
    loadVideos(false);
  }

  // ── URL-Sync: Lese Filter aus URL-Params ──
  let _syncing = false;
  function syncFromUrl() {
    _syncing = true;
    const p = $route.params;
    if (p.sort && p.sort !== sortBy) sortBy = p.sort;
    if (p.order && p.order !== sortOrder) sortOrder = p.order;
    const urlTags = p.tags ? p.tags.split(',') : [];
    if (JSON.stringify(urlTags) !== JSON.stringify(activeTags)) activeTags = urlTags;
    // multiFilter: nur setzen wenn sich tatsächlich was geändert hat
    const newTypes = p.types || null;
    const newChannels = p.channels || null;
    if (newTypes !== multiFilter.types || newChannels !== multiFilter.channels) {
      multiFilter = { ...multiFilter, types: newTypes, channels: newChannels };
    }
    _syncing = false;
  }

  function syncToUrl() {
    updateParams({
      sort: sortBy !== 'created_at' ? sortBy : null,
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

  function onFilterChange(f) { multiFilter = f; syncToUrl(); }

  function changeSort(field) {
    if (sortBy === field) sortOrder = sortOrder === 'desc' ? 'asc' : 'desc';
    else { sortBy = field; sortOrder = 'desc'; }
    syncToUrl();
  }

  // ─── Bulk-Aktionen ───
  function toggleSelect(id) { const s = new Set(selected); if (s.has(id)) s.delete(id); else s.add(id); selected = s; }
  function selectAll() { selected = new Set(videos.map(v => v.id)); }
  async function archiveSelected() {
    if (selected.size === 0) return;
    try { await api.archiveBatch([...selected], false); toast.success(`${selected.size} Video(s) archiviert`); selected = new Set(); selectMode = false; loadVideos(); } catch (e) { toast.error(e.message); }
  }
  async function deleteSelected() {
    if (selected.size === 0) return;
    const ok = await confirmRef.ask(`${selected.size} Videos löschen?`, 'Alle ausgewählten Videos werden unwiderruflich gelöscht.');
    if (!ok) return;
    let deleted = 0; for (const id of selected) { try { await api.deleteVideo(id); deleted++; } catch {} }
    toast.success(`${deleted} Video(s) gelöscht`); selected = new Set(); selectMode = false; loadVideos();
  }
  async function setTypeBulk(videoType) {
    if (selected.size === 0) return;
    const labels = { video: 'Video', short: 'Short', live: 'Live' };
    try { const res = await api.setTypeBatch([...selected], videoType); toast.success(`${res.updated} Video(s) → ${labels[videoType]}`); selected = new Set(); selectMode = false; loadVideos(); } catch (e) { toast.error(e.message); }
  }

  // Tag-Filter Event von Watch
  $effect(() => {
    function onTagFilter(e) { const tag = e.detail; if (!activeTags.includes(tag)) { activeTags = [...activeTags, tag]; syncToUrl(); } }
    window.addEventListener('tubevault:tag-filter', onTagFilter);
    return () => window.removeEventListener('tubevault:tag-filter', onTagFilter);
  });

  // Init: URL-Params lesen, dann laden
  $effect(() => { syncFromUrl(); loadTags(); });

  // Laden bei Filter-Änderung (debounced um Request-Flut zu verhindern)
  $effect(() => {
    $searchQuery; sortBy; sortOrder; activeTags;
    multiFilter.types; multiFilter.channels; multiFilter.categories;
    saveFilters('library', { sortBy, sortOrder });
    loadVideosDebounced();
  });

  // IntersectionObserver für Lazy Loading
  $effect(() => {
    if (sentinelEl) {
      observer?.disconnect();
      observer = new IntersectionObserver((es) => { if (es[0]?.isIntersecting) loadMore(); }, { rootMargin: '400px' });
      observer.observe(sentinelEl);
    }
    return () => observer?.disconnect();
  });

  let filteredTags = $derived(tagSearch ? allTags.filter(t => t.tag.toLowerCase().includes(tagSearch.toLowerCase())) : allTags);
  let visibleTags = $derived(tagSearch ? filteredTags : (showAllTags ? allTags : allTags.slice(0, 15)));
  let hasActiveFilter = $derived(activeTags.length > 0 || multiFilter.types || multiFilter.channels || multiFilter.categories || multiFilter.is_music);
</script>

<div class="library">
  <div class="library-header">
    <h1 class="page-title">Bibliothek</h1>
    <span class="video-count">{total} Video{total !== 1 ? 's' : ''}</span>
    {#if hasActiveFilter}
      <button class="btn-clear-filter" onclick={clearFilters}><i class="fa-solid fa-xmark"></i> Filter zurücksetzen</button>
    {/if}
    <div class="header-actions">
      <button class="btn-select" class:active={selectMode} onclick={() => { selectMode = !selectMode; selected = new Set(); }}>
        <i class="fa-solid {selectMode ? 'fa-xmark' : 'fa-check-double'}"></i>
        {selectMode ? 'Abbrechen' : 'Auswählen'}
      </button>
    </div>
  </div>

  {#if selectMode && selected.size > 0}
    <div class="bulk-bar">
      <span class="bulk-count">{selected.size} ausgewählt</span>
      <button class="bulk-btn" onclick={selectAll}><i class="fa-solid fa-check-double"></i> Alle ({videos.length})</button>
      <span class="bulk-sep">|</span>
      <button class="bulk-btn bulk-type" onclick={() => setTypeBulk('video')}><i class="fa-solid fa-play"></i> → Video</button>
      <button class="bulk-btn bulk-type" onclick={() => setTypeBulk('short')}><i class="fa-solid fa-mobile-screen"></i> → Short</button>
      <button class="bulk-btn bulk-type" onclick={() => setTypeBulk('live')}><i class="fa-solid fa-tower-broadcast"></i> → Live</button>
      <span class="bulk-sep">|</span>
      <button class="bulk-btn" onclick={archiveSelected}><i class="fa-solid fa-box-archive"></i> Archivieren</button>
      <button class="bulk-btn bulk-danger" onclick={deleteSelected}><i class="fa-regular fa-trash-can"></i> Löschen</button>
    </div>
  {/if}

  <MultiFilter showTypes={true} showChannels={true} showCategories={true} showMusic={true} onchange={onFilterChange} />

  {#if allTags.length > 0}
    <div class="tag-bar">
      <span class="tag-label">Tags:</span>
      <div class="tag-search-wrap">
        <i class="fa-solid fa-magnifying-glass tag-search-icon"></i>
        <input type="text" class="tag-search" placeholder="Tag suchen… ({allTags.length})" bind:value={tagSearch} />
        {#if tagSearch}<button class="tag-search-clear" onclick={() => tagSearch = ''}><i class="fa-solid fa-xmark"></i></button>{/if}
      </div>
      <div class="tag-list">
        {#each visibleTags as t}
          <button class="tag-chip" class:active={activeTags.includes(t.tag)} onclick={() => toggleTag(t.tag)}>
            {t.tag} <span class="tag-count">{t.count}</span>
          </button>
        {/each}
        {#if !tagSearch && allTags.length > 15}
          <button class="tag-toggle" onclick={() => showAllTags = !showAllTags}>
            {showAllTags ? 'weniger' : `+${allTags.length - 15} mehr`}
          </button>
        {/if}
        {#if tagSearch && visibleTags.length === 0}<span class="tag-empty">Kein Tag gefunden</span>{/if}
      </div>
    </div>
  {/if}

  {#if activeTags.length > 0}
    <div class="active-filter">
      {#each activeTags as tag}
        <button class="filter-badge" onclick={() => toggleTag(tag)}>
          <i class="fa-solid fa-tag"></i> {tag} <i class="fa-solid fa-xmark"></i>
        </button>
      {/each}
    </div>
  {/if}

  <div class="toolbar">
    <div class="sort-group">
      <span class="toolbar-label">Sortieren:</span>
      {#each [['created_at','Datum'],['title','Titel'],['duration','Dauer'],['file_size','Größe'],['rating','Bewertung'],['play_count','Abgespielt']] as [field, label]}
        <button class="sort-btn" class:active={sortBy === field} onclick={() => changeSort(field)}>
          {label} {#if sortBy === field}<span class="sort-arrow">{sortOrder === 'desc' ? '↓' : '↑'}</span>{/if}
        </button>
      {/each}
    </div>
  </div>

  {#if loading}
    <div class="loading">Laden…</div>
  {:else if videos.length > 0}
    <div class="video-grid">
      {#each videos as video (video.id)}
        {#if selectMode}
          <div class="select-card-wrap" class:selected={selected.has(video.id)}>
            <button class="select-check" onclick={() => toggleSelect(video.id)}>
              {#if selected.has(video.id)}<i class="fa-solid fa-square-check"></i>{:else}<i class="fa-regular fa-square"></i>{/if}
            </button>
            <VideoCard {video} />
          </div>
        {:else}
          <VideoCard {video} />
        {/if}
      {/each}
    </div>
    <div bind:this={sentinelEl} class="scroll-sentinel"></div>
    {#if loadingMore}
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
  .library { padding: 24px; max-width: 1200px; }
  .library-header { display:flex; align-items:baseline; gap:12px; margin-bottom:16px; flex-wrap:wrap; }
  .page-title { font-size:1.6rem; font-weight:700; color:var(--text-primary); margin:0; }
  .video-count { font-size:0.9rem; color:var(--text-tertiary); }
  .btn-clear-filter { margin-left:auto; padding:5px 12px; background:none; border:1px solid var(--border-primary); border-radius:6px; color:var(--text-secondary); font-size:0.78rem; cursor:pointer; }
  .btn-clear-filter:hover { border-color:var(--status-error); color:var(--status-error); }

  .tag-bar { display:flex; align-items:flex-start; gap:8px; margin-bottom:14px; padding:10px 14px; background:var(--bg-secondary); border:1px solid var(--border-primary); border-radius:10px; }
  .tag-label { font-size:0.76rem; color:var(--text-tertiary); font-weight:600; text-transform:uppercase; letter-spacing:0.04em; padding-top:4px; white-space:nowrap; }
  .tag-search-wrap { display:flex; align-items:center; gap:5px; background:var(--bg-primary); border:1px solid var(--border-primary); border-radius:8px; padding:2px 8px; min-width:140px; flex-shrink:0; }
  .tag-search-wrap:focus-within { border-color:var(--accent-primary); }
  .tag-search-icon { font-size:0.68rem; color:var(--text-tertiary); }
  .tag-search { border:none; background:none; color:var(--text-primary); font-size:0.78rem; padding:3px 0; outline:none; width:100%; }
  .tag-search-clear { background:none; border:none; color:var(--text-tertiary); cursor:pointer; font-size:0.68rem; padding:2px; }
  .tag-empty { font-size:0.76rem; color:var(--text-tertiary); padding:2px 6px; }
  .tag-list { display:flex; flex-wrap:wrap; gap:5px; }
  .tag-chip { display:flex; align-items:center; gap:4px; padding:3px 10px; background:var(--bg-primary); border:1px solid var(--border-primary); border-radius:14px; color:var(--text-secondary); font-size:0.76rem; cursor:pointer; transition:all 0.12s; }
  .tag-chip:hover { border-color:var(--accent-primary); color:var(--text-primary); }
  .tag-chip.active { background:var(--accent-primary); color:#fff; border-color:var(--accent-primary); font-weight:600; }
  .tag-chip.active .tag-count { background:rgba(255,255,255,0.25); color:#fff; }
  .tag-count { font-size:0.65rem; background:var(--bg-tertiary); color:var(--text-tertiary); padding:0 5px; border-radius:8px; font-weight:600; }
  .tag-toggle { padding:3px 10px; background:none; border:1px dashed var(--border-primary); border-radius:14px; color:var(--accent-primary); font-size:0.76rem; cursor:pointer; }

  .active-filter { display:flex; gap:6px; margin-bottom:12px; flex-wrap:wrap; }
  .filter-badge { padding:4px 10px; background:var(--accent-muted); color:var(--accent-primary); border:none; border-radius:6px; font-size:0.78rem; font-weight:600; cursor:pointer; }
  .filter-badge:hover { background:var(--accent-primary); color:#fff; }

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

  .header-actions { margin-left:auto; display:flex; gap:6px; }
  .btn-select { padding:5px 12px; background:var(--bg-secondary); border:1px solid var(--border-primary); border-radius:6px; color:var(--text-secondary); font-size:0.78rem; cursor:pointer; display:flex; align-items:center; gap:5px; }
  .btn-select.active { border-color:var(--accent-primary); color:var(--accent-primary); }

  .bulk-bar { display:flex; align-items:center; gap:8px; padding:10px 14px; background:var(--bg-secondary); border:1px solid var(--accent-primary); border-radius:10px; margin-bottom:14px; flex-wrap:wrap; }
  .bulk-count { font-size:0.82rem; font-weight:600; color:var(--accent-primary); margin-right:4px; }
  .bulk-btn { padding:5px 12px; background:var(--bg-tertiary); border:1px solid var(--border-primary); border-radius:6px; color:var(--text-secondary); font-size:0.78rem; cursor:pointer; display:flex; align-items:center; gap:5px; }
  .bulk-btn:hover { border-color:var(--accent-primary); color:var(--text-primary); }
  .bulk-danger:hover { border-color:var(--status-error); color:var(--status-error); }
  .bulk-sep { color:var(--border-primary); font-size:0.9rem; }
  .bulk-type:hover { border-color:#ab47bc; color:#ab47bc; }

  .select-card-wrap { position:relative; }
  .select-card-wrap.selected { outline:2px solid var(--accent-primary); border-radius:12px; }
  .select-check { position:absolute; top:8px; left:8px; z-index:4; background:rgba(0,0,0,0.6); border:none; border-radius:4px; color:#fff; font-size:1.1rem; cursor:pointer; padding:2px 4px; }
  .select-card-wrap.selected .select-check { color:var(--accent-primary); }
</style>

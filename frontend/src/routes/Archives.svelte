<!--
  TubeVault -  Archive v1.5.91
  Archivierte Videos: Gleiche Such-/Filter-Logik wie Bibliothek.
  Videos hier sind aus der Bibliothek ausgeblendet.
  © HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
  SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
-->
<script>
  import { api } from '../lib/api/client.js';
  import { searchQuery } from '../lib/stores/app.js';
  import { toast } from '../lib/stores/notifications.js';
  import { getSettingNum } from '../lib/stores/settings.js';
  import { getFilter, saveFilters } from '../lib/stores/filterPersist.js';
  import VideoCard from '../lib/components/video/VideoCard.svelte';
  import MultiFilter from '../lib/components/common/MultiFilter.svelte';
  import Pagination from '../lib/components/common/Pagination.svelte';

  let videos = $state([]);
  let total = $state(0);
  let page = $state(1);
  let totalPages = $state(1);
  let sortBy = $state(getFilter('archives', 'sortBy', 'created_at'));
  let sortOrder = $state(getFilter('archives', 'sortOrder', 'desc'));
  let loading = $state(false);
  let selectMode = $state(false);
  let selected = $state(new Set());

  let activeTags = $state([]);
  let allTags = $state([]);
  let showAllTags = $state(false);
  let tagSearch = $state('');
  let multiFilter = $state({ types: null, channels: null, categories: null });

  async function loadTags() {
    try { allTags = await api.getAllTags() || []; } catch {}
  }

  async function loadVideos() {
    loading = true;
    try {
      const params = { page, per_page: getSettingNum('general.videos_per_page', 24), sort_by: sortBy, sort_order: sortOrder, is_archived: true };
      const q = $searchQuery;
      if (q) params.search = q;
      if (activeTags.length > 0) params.tags = activeTags.join(',');
      if (multiFilter.types) params.video_types = multiFilter.types;
      if (multiFilter.channels) params.channel_ids = multiFilter.channels;
      if (multiFilter.categories) params.category_ids = multiFilter.categories;
      const result = await api.getVideos(params);
      videos = result.videos;
      total = result.total;
      totalPages = result.total_pages;
    } catch (e) { toast.error('Fehler: ' + e.message); }
    loading = false;
  }

  function toggleTag(tag) { activeTags = activeTags.includes(tag) ? activeTags.filter(t => t !== tag) : [...activeTags, tag]; page = 1; }
  function clearFilters() { activeTags = []; multiFilter = { types: null, channels: null, categories: null }; page = 1; }
  function onFilterChange(f) { multiFilter = f; page = 1; }
  function changeSort(field) {
    if (sortBy === field) sortOrder = sortOrder === 'desc' ? 'asc' : 'desc';
    else { sortBy = field; sortOrder = 'desc'; }
    page = 1;
  }

  // ─── Dearchivieren ───
  async function unarchiveVideo(id) {
    try {
      await api.unarchiveVideo(id);
      videos = videos.filter(v => v.id !== id);
      total--;
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
      loadVideos();
    } catch (e) { toast.error(e.message); }
  }

  function toggleSelect(id) {
    const s = new Set(selected);
    if (s.has(id)) s.delete(id); else s.add(id);
    selected = s;
  }

  $effect(() => { loadTags(); });
  $effect(() => { $searchQuery; sortBy; sortOrder; page; activeTags; multiFilter.types; multiFilter.channels; multiFilter.categories; saveFilters('archives', { sortBy, sortOrder }); loadVideos(); });

  let filteredTags = $derived(tagSearch ? allTags.filter(t => t.tag.toLowerCase().includes(tagSearch.toLowerCase())) : allTags);
  let visibleTags = $derived(tagSearch ? filteredTags : (showAllTags ? allTags : allTags.slice(0, 15)));
  let hasActiveFilter = $derived(activeTags.length > 0 || multiFilter.types || multiFilter.channels || multiFilter.categories);
</script>

<div class="library">
  <div class="library-header">
    <h1 class="page-title"><i class="fa-solid fa-box-archive"></i> Archiv</h1>
    <span class="video-count">{total} Video{total !== 1 ? 's' : ''}</span>
    {#if hasActiveFilter}
      <button class="btn-clear-filter" onclick={clearFilters}><i class="fa-solid fa-xmark"></i> Filter zurücksetzen</button>
    {/if}
    <div class="header-actions">
      <button class="btn-select" class:active={selectMode} onclick={() => { selectMode = !selectMode; selected = new Set(); }}>
        <i class="fa-solid {selectMode ? 'fa-xmark' : 'fa-check-double'}"></i>
        {selectMode ? 'Abbrechen' : 'Auswählen'}
      </button>
      {#if selectMode && selected.size > 0}
        <button class="btn-unarchive-batch" onclick={unarchiveSelected}>
          <i class="fa-solid fa-box-open"></i> {selected.size} dearchivieren
        </button>
      {/if}
    </div>
  </div>

  <MultiFilter showTypes={true} showChannels={true} showCategories={true} onchange={onFilterChange} />

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
          <button class="tag-toggle" onclick={() => showAllTags = !showAllTags}>{showAllTags ? 'weniger' : `+${allTags.length - 15} mehr`}</button>
        {/if}
      </div>
    </div>
  {/if}

  {#if activeTags.length > 0}
    <div class="active-filter">
      {#each activeTags as tag}
        <button class="filter-badge" onclick={() => toggleTag(tag)}><i class="fa-solid fa-tag"></i> {tag} <i class="fa-solid fa-xmark"></i></button>
      {/each}
    </div>
  {/if}

  <div class="toolbar">
    <div class="sort-group">
      <span class="toolbar-label">Sortieren:</span>
      {#each [['created_at', 'Datum'], ['title', 'Titel'], ['duration', 'Dauer'], ['file_size', 'Größe'], ['rating', 'Bewertung'], ['play_count', 'Abgespielt']] as [field, label]}
        <button class="sort-btn" class:active={sortBy === field} onclick={() => changeSort(field)}>
          {label}
          {#if sortBy === field}<span class="sort-arrow">{sortOrder === 'desc' ? '↓' : '↑'}</span>{/if}
        </button>
      {/each}
    </div>
  </div>

  {#if loading}
    <div class="loading"><i class="fa-solid fa-spinner fa-spin"></i> Laden…</div>
  {:else if videos.length > 0}
    <div class="video-grid">
      {#each videos as video (video.id)}
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
          <VideoCard {video} />
          <button class="btn-unarchive" onclick={() => unarchiveVideo(video.id)} title="Dearchivieren">
            <i class="fa-solid fa-box-open"></i>
          </button>
        </div>
      {/each}
    </div>
    <Pagination {page} {totalPages} onchange={(p) => page = p} />
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
  .library { padding: 24px; max-width: 1200px; }
  .library-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
  .page-title { font-size: 1.6rem; font-weight: 700; color: var(--text-primary); margin: 0; display: flex; align-items: center; gap: 10px; }
  .page-title i { color: var(--accent-primary); }
  .video-count { font-size: 0.9rem; color: var(--text-tertiary); }
  .btn-clear-filter { padding: 5px 12px; background: none; border: 1px solid var(--border-primary); border-radius: 6px; color: var(--text-secondary); font-size: 0.78rem; cursor: pointer; }
  .btn-clear-filter:hover { border-color: var(--status-error); color: var(--status-error); }
  .header-actions { margin-left: auto; display: flex; gap: 6px; }
  .btn-select { padding: 5px 12px; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 6px; color: var(--text-secondary); font-size: 0.78rem; cursor: pointer; display: flex; align-items: center; gap: 5px; }
  .btn-select.active { border-color: var(--accent-primary); color: var(--accent-primary); }
  .btn-unarchive-batch { padding: 5px 12px; background: var(--accent-primary); color: #fff; border: none; border-radius: 6px; font-size: 0.78rem; cursor: pointer; display: flex; align-items: center; gap: 5px; }

  .tag-bar { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 14px; padding: 10px 14px; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 10px; }
  .tag-label { font-size: 0.76rem; color: var(--text-tertiary); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; padding-top: 4px; white-space: nowrap; }
  .tag-search-wrap { display: flex; align-items: center; gap: 5px; background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 8px; padding: 2px 8px; min-width: 140px; flex-shrink: 0; }
  .tag-search-wrap:focus-within { border-color: var(--accent-primary); }
  .tag-search-icon { font-size: 0.68rem; color: var(--text-tertiary); }
  .tag-search { border: none; background: none; color: var(--text-primary); font-size: 0.78rem; padding: 3px 0; outline: none; width: 100%; }
  .tag-search-clear { background: none; border: none; color: var(--text-tertiary); cursor: pointer; font-size: 0.68rem; padding: 2px; }
  .tag-list { display: flex; flex-wrap: wrap; gap: 5px; }
  .tag-chip { display: flex; align-items: center; gap: 4px; padding: 3px 10px; background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 14px; color: var(--text-secondary); font-size: 0.76rem; cursor: pointer; transition: all 0.12s; }
  .tag-chip:hover { border-color: var(--accent-primary); color: var(--text-primary); }
  .tag-chip.active { background: var(--accent-primary); color: #fff; border-color: var(--accent-primary); font-weight: 600; }
  .tag-chip.active .tag-count { background: rgba(255,255,255,0.25); color: #fff; }
  .tag-count { font-size: 0.65rem; background: var(--bg-tertiary); color: var(--text-tertiary); padding: 0 5px; border-radius: 8px; font-weight: 600; }
  .tag-toggle { padding: 3px 10px; background: none; border: 1px dashed var(--border-primary); border-radius: 14px; color: var(--accent-primary); font-size: 0.76rem; cursor: pointer; }
  .active-filter { display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; }
  .filter-badge { padding: 4px 10px; background: var(--accent-muted); color: var(--accent-primary); border: none; border-radius: 6px; font-size: 0.78rem; font-weight: 600; cursor: pointer; }
  .filter-badge:hover { background: var(--accent-primary); color: #fff; }

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

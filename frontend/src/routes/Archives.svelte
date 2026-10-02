<!--
  TubeVault – Archive v1.5.91
  Archivierte Videos: Gleiche Such-/Filter-Logik wie Bibliothek.
  Videos hier sind aus der Bibliothek ausgeblendet.
  © HalloWelt42 – Private Nutzung
-->
<script>
  import { api } from '../lib/api/client.js';
  import { toast } from '../lib/stores/notifications.js';
  import { getSettingNum } from '../lib/stores/settings.js';
  import { createVideoListFilters } from '../lib/utils/videoListFilters.svelte.js';
  import { onVideoMutation } from '../lib/utils/videoMutations.js';
  import VideoCard from '../lib/components/video/VideoCard.svelte';
  import MultiFilter from '../lib/components/common/MultiFilter.svelte';
  import { infiniteScroll } from '../lib/utils/infiniteScroll.js';
  import { createListLoader } from '../lib/utils/listLoader.svelte.js';
  import PageHeader from '../lib/components/common/PageHeader.svelte';
  import TagFilterBar from '../lib/components/common/TagFilterBar.svelte';
  import BatchToolbar from '../lib/components/common/BatchToolbar.svelte';
  import { settings } from '../lib/stores/settings.js';
  import { dubbingEnabled, enqueueForDubbing } from '../lib/utils/dubbingActions.js';

  // Sortierung, Tags und Mehrfachfilter: eine Wahrheit (URL > gespeicherte Auswahl)
  const filters = createVideoListFilters('archives');

  let selectMode = $state(false);
  let selected = $state(new Set());
  let filterRef;
  let allTags = $state([]);

  async function loadTags() {
    // Tags nur für die im Archiv gefilterten Videos — nicht global.
    try {
      allTags = (await api.getAllTags({ archived: true, ...filters.tagParams() })) || [];
    } catch {}
  }

  // Zentraler List-Loader: page ist darin bewusst nicht-reaktiv,
  // dadurch kann der Filter-$effect das Nachladen nicht mehr zurücksetzen.
  const list = createListLoader(async (page) => {
    const params = {
      page, per_page: getSettingNum('general.videos_per_page', 24),
      is_archived: true, ...filters.apiParams(),
    };
    try {
      const result = await api.getVideos(params);
      return { items: result.videos || [], total: result.total || 0 };
    } catch (e) { toast.error('Fehler: ' + e.message); return { items: [], total: 0 }; }
  });

  function clearFilters() {
    filters.clearTags();
    filterRef?.reset();   // leert die Leiste und meldet den leeren Filter zurück
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

  async function dubSelected() {
    if (selected.size === 0) return;
    if (await enqueueForDubbing([...selected])) { selected = new Set(); selectMode = false; }
  }

  function toggleSelect(id) {
    const s = new Set(selected);
    if (s.has(id)) s.delete(id); else s.add(id);
    selected = s;
  }

  // Jede Filter-Änderung: Auswahl sichern (Speicher + URL), Liste und Tags neu laden
  $effect(() => {
    filters.signature;
    filters.persist();
    list.load(true);
    loadTags();
  });
  // Reagiere auf Video-Mutationen aus anderen Views (z.B. Watch → Dearchive)
  $effect(() => onVideoMutation(() => { list.load(true); loadTags(); }));
</script>

<div class="library">
  <PageHeader title="Archiv" icon="fa-solid fa-box-archive" count={list.total} hasFilter={filters.hasActive} onClearFilter={clearFilters}>
    <button class="btn-select" class:active={selectMode} onclick={() => { selectMode = !selectMode; selected = new Set(); }}>
      <i class="fa-solid {selectMode ? 'fa-xmark' : 'fa-check-double'}"></i>
      {selectMode ? 'Abbrechen' : 'Auswählen'}
    </button>
  </PageHeader>

  {#if selectMode}
    <BatchToolbar selectedCount={selected.size} totalCount={list.items.length}
                  onSelectAll={() => selected = new Set(list.items.map(v => v.id))}>
      {#if dubbingEnabled($settings)}
        <button class="bulk-btn" onclick={dubSelected} title="Ausgewählte Videos zur Nachvertonung vormerken">
          <i class="fa-solid fa-language"></i> Nachvertonen
        </button>
      {/if}
      <button class="bulk-btn" onclick={unarchiveSelected}><i class="fa-solid fa-box-open"></i> Dearchivieren</button>
    </BatchToolbar>
  {/if}

  <MultiFilter bind:this={filterRef} showSearch={true} showTypes={true} showChannels={true} showCategories={true}
               initial={filters.multi} onchange={filters.setMulti} />

  <TagFilterBar {allTags} activeTags={filters.activeTags} onToggle={filters.toggleTag} />

  <div class="toolbar">
    <div class="sort-group">
      <span class="toolbar-label">Sortieren:</span>
      {#each [['created_at', 'Datum'], ['upload_date', 'Upload'], ['is_favorite', 'Favoriten'], ['title', 'Titel'], ['duration', 'Dauer'], ['file_size', 'Größe'], ['rating', 'Bewertung'], ['play_count', 'Abgespielt']] as [field, label]}
        <button class="sort-btn" class:active={filters.sortBy === field} onclick={() => filters.changeSort(field)}>
          {label}
          {#if filters.sortBy === field}<span class="sort-arrow">{filters.sortOrder === 'desc' ? '↓' : '↑'}</span>{/if}
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
      {#if filters.hasActive}
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

<script>
  import { api } from '../lib/api/client.js';
  import { toast } from '../lib/stores/notifications.js';
  import { getSettingNum } from '../lib/stores/settings.js';
  import { onVideoMutation } from '../lib/utils/videoMutations.js';
  import { infiniteScroll } from '../lib/utils/infiniteScroll.js';
  import { createListLoader } from '../lib/utils/listLoader.svelte.js';
  import { createVideoListFilters } from '../lib/utils/videoListFilters.svelte.js';
  import VideoCard from '../lib/components/video/VideoCard.svelte';
  import MultiFilter from '../lib/components/common/MultiFilter.svelte';
  import ConfirmDialog from '../lib/components/common/ConfirmDialog.svelte';
  import AddToPlaylistDialog from '../lib/components/common/AddToPlaylistDialog.svelte';
  import PageHeader from '../lib/components/common/PageHeader.svelte';
  import TagFilterBar from '../lib/components/common/TagFilterBar.svelte';
  import BatchToolbar from '../lib/components/common/BatchToolbar.svelte';
  import { settings } from '../lib/stores/settings.js';

  // Sortierung, Tags und Mehrfachfilter: eine Wahrheit (URL > gespeicherte Auswahl)
  const filters = createVideoListFilters('library');

  let selectMode = $state(false);
  let selected = $state(new Set());
  let confirmRef;
  let filterRef;
  let addToPlaylistVideoId = $state(null);

  let allTags = $state([]);
  let totalBytes = $state(0);   // Größe aller Treffer (vom Backend)
  let _loadTimer = null;

  async function loadTags() {
    // Tags werden gefiltert wie die aktuelle Video-Liste, damit nicht global
    // 64k Tags angezeigt werden, wenn nur 20 Videos gefiltert sind.
    try {
      allTags = (await api.getAllTags({ archived: false, ...filters.tagParams() })) || [];
    } catch {}
  }

  // Zentraler List-Loader (page darin nicht-reaktiv, Stale-Guard inklusive)
  const list = createListLoader(async (page) => {
    const params = {
      page, per_page: getSettingNum('general.videos_per_page', 24),
      is_archived: false, ...filters.apiParams(),
    };
    try {
      const result = await api.getVideos(params);
      if (page === 1) totalBytes = result.total_bytes || 0;
      return { items: result.videos || [], total: result.total || 0 };
    } catch (e) { toast.error('Fehler: ' + e.message); return { items: [], total: 0 }; }
  });

  // Debounced Reset-Load – verhindert Request-Flut bei schnellen Filter-Änderungen
  function loadDebounced() {
    clearTimeout(_loadTimer);
    _loadTimer = setTimeout(() => list.load(true), 80);
  }

  function clearFilters() {
    filters.clearTags();
    filterRef?.reset();   // leert die Leiste und meldet den leeren Filter zurück
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

  async function setMusicBulk(isMusic) {
    if (selected.size === 0) return;
    try {
      const res = await api.setMusicBatch([...selected], isMusic);
      toast.success(`${res.updated} Video(s) ${isMusic ? 'als Musik' : 'als keine Musik'} festgelegt`);
      selected = new Set(); selectMode = false; list.load(true);
    } catch (e) { toast.error(e.message); }
  }

  async function setAudiobookBulk(isAudiobook) {
    if (selected.size === 0) return;
    try {
      const res = await api.setAudiobookBatch([...selected], isAudiobook);
      toast.success(`${res.updated} Video(s) ${isAudiobook ? 'als Hörbuch' : 'als kein Hörbuch'} festgelegt`);
      selected = new Set(); selectMode = false; list.load(true);
    } catch (e) { toast.error(e.message); }
  }

  // Auf globale Video-Mutationen (Archive/Delete aus Watch-View) reagieren -
  // Liste neu laden, damit beim Zurück-Navigieren der neue Stand zu sehen ist.
  $effect(() => onVideoMutation(() => { list.load(true); loadTags(); }));

  // Jede Filter-Änderung: Auswahl sichern (Speicher + URL), Liste und Tags neu laden
  $effect(() => {
    filters.signature;
    filters.persist();
    loadDebounced();
    loadTags();
  });
</script>

<div class="tv-seite">
 <div class="tv-seitenkopf">
  <PageHeader title="Bibliothek" count={list.loading && !list.total ? null : list.total} bytes={totalBytes}
              hasFilter={filters.hasActive} onClearFilter={clearFilters}>
    <button class="tv-knopf" class:aktiv={selectMode} onclick={() => { selectMode = !selectMode; selected = new Set(); }}>
      <i class="fa-{selectMode ? 'solid fa-xmark' : 'regular fa-square-check'}"></i>
      {selectMode ? 'Abbrechen' : 'Auswählen'}
    </button>
  </PageHeader>

  {#if selectMode}
    <BatchToolbar selectedCount={selected.size} totalCount={list.items.length} onSelectAll={selectAll}>
      <button class="tv-knopf klein" onclick={() => setTypeBulk('video')}><i class="fa-solid fa-play"></i> Als Video</button>
      <button class="tv-knopf klein" onclick={() => setTypeBulk('short')}><i class="fa-solid fa-mobile-screen"></i> Als Short</button>
      <button class="tv-knopf klein" onclick={() => setTypeBulk('live')}><i class="fa-solid fa-tower-broadcast"></i> Als Live</button>
      <span class="tv-trenner"></span>
      <button class="tv-knopf klein" onclick={() => setMusicBulk(true)} title="Von Hand als Musik festlegen - keine Automatik ändert das">
        <i class="fa-solid fa-music"></i> Musik</button>
      <button class="tv-knopf klein" onclick={() => setMusicBulk(false)} title="Von Hand als keine Musik festlegen">
        <i class="fa-solid fa-microphone-slash"></i> Keine Musik</button>
      <button class="tv-knopf klein" onclick={() => setAudiobookBulk(true)} title="Hörbuch oder Hörspiel: nie in der Musik, eigener Bereich in fester Reihenfolge">
        <i class="fa-solid fa-book-open"></i> Hörbuch</button>
      <button class="tv-knopf klein" onclick={() => setAudiobookBulk(false)} title="Kein Hörbuch">
        <i class="fa-solid fa-book"></i> Kein Hörbuch</button>
      <span class="tv-trenner"></span>
      <button class="tv-knopf klein" onclick={archiveSelected}><i class="fa-solid fa-box-archive"></i> Archivieren</button>
      <button class="tv-knopf klein gefahr" onclick={deleteSelected}><i class="fa-regular fa-trash-can"></i> Löschen</button>
    </BatchToolbar>
  {/if}

  <MultiFilter bind:this={filterRef} showSearch={true} showTypes={true} showChannels={true} showCategories={true} showMusic={true}
               initial={filters.multi} onchange={filters.setMulti} />

  <div class="tv-filter">
    <span class="tv-etikett">Sortieren</span>
    {#each [['created_at','Geladen'],['upload_date','Hochgeladen'],['is_favorite','Favoriten'],['title','Titel'],['duration','Dauer'],['file_size','Größe'],['rating','Bewertung'],['play_count','Abgespielt']] as [field, label]}
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
        {#if selectMode}
          <div class="auswahl" class:gewaehlt={selected.has(video.id)}>
            <button class="auswahl-haken" onclick={() => toggleSelect(video.id)}
                    title={selected.has(video.id) ? 'Abwählen' : 'Auswählen'}>
              <i class="fa-{selected.has(video.id) ? 'solid fa-square-check' : 'regular fa-square'}"></i>
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
      <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt weitere ...</div>
    {/if}
  {:else}
    <div class="tv-leer">
      {#if filters.hasActive}
        <p>Keine Videos für diesen Filter.</p>
        <button class="tv-knopf" style="margin-top: var(--tv-a3)" onclick={clearFilters}>Filter zurücksetzen</button>
      {:else}
        <p>Noch keine Videos in der Bibliothek.</p>
      {/if}
    </div>
  {/if}
 </div>
</div>

<ConfirmDialog bind:this={confirmRef} />
<AddToPlaylistDialog bind:videoId={addToPlaylistVideoId} />

<style>
  /* Gestaltung nach mockups/bibliothek.html */
  .tv-raster { margin-top: var(--tv-a3); }
  .scroll-sentinel { height: 1px; }

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

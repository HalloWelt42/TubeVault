<!--
  TubeVault – Categories v1.5.91
  © HalloWelt42 – Private Nutzung
  Material Design Farbpalette statt freier Farbauswahl
-->
<script>
  import { api } from '../lib/api/client.js';
  import { navigate } from '../lib/router/router.js';
  import { toast } from '../lib/stores/notifications.js';
  import { getFilter, saveFilters } from '../lib/stores/filterPersist.js';
  import { formatDuration, formatSize, formatDateRelative } from '../lib/utils/format.js';

  let categories = $state([]);
  let selectedCat = $state(null);
  let catVideos = $state([]);
  let loading = $state(true);
  let catSearch = $state('');
  let catSort = $state(getFilter('categories', 'catSort', 'created_at'));
  let catSortOrder = $state(getFilter('categories', 'catSortOrder', 'desc'));

  // Material Design Farben
  const MD_COLORS = [
    { name: 'Rot',        hex: '#F44336' },
    { name: 'Pink',       hex: '#E91E63' },
    { name: 'Lila',       hex: '#9C27B0' },
    { name: 'Tiefviolett',hex: '#673AB7' },
    { name: 'Indigo',     hex: '#3F51B5' },
    { name: 'Blau',       hex: '#2196F3' },
    { name: 'Hellblau',   hex: '#03A9F4' },
    { name: 'Cyan',       hex: '#00BCD4' },
    { name: 'Teal',       hex: '#009688' },
    { name: 'Grün',       hex: '#4CAF50' },
    { name: 'Hellgrün',   hex: '#8BC34A' },
    { name: 'Lime',       hex: '#CDDC39' },
    { name: 'Gelb',       hex: '#FFEB3B' },
    { name: 'Bernstein',  hex: '#FFC107' },
    { name: 'Orange',     hex: '#FF9800' },
    { name: 'Tiefrot',    hex: '#FF5722' },
    { name: 'Braun',      hex: '#795548' },
    { name: 'Grau',       hex: '#607D8B' },
  ];

  // Create
  let newName = $state('');
  let newColor = $state('#3F51B5');
  let newDesc = $state('');

  // Edit
  let editing = $state(null);
  let editName = $state('');
  let editColor = $state('');
  let editDesc = $state('');
  let autoAssignQuery = $state('');
  let assigning = $state(false);
  let unassignedStats = $state(null);
  let catSearchTimer = null;
  let debugStats = $state(null);
  let lastApiResponse = $state(null); // Debug: letzte Rohtwort der API

  async function load() {
    loading = true;
    try { categories = await api.getCategoriesFlat(); } catch (e) { toast.error(e.message); }
    loading = false;
  }

  async function selectCategory(cat) {
    selectedCat = cat;
    catSearch = '';
    await loadCatVideos();
  }

  async function loadCatVideos() {
    if (!selectedCat) return;
    saveFilters('categories', { catSort, catSortOrder });
    try {
      const raw = await api.getCategoryVideos(selectedCat.id, {
        sort_by: catSort,
        sort_order: catSortOrder,
        search: catSearch || undefined,
      });
      lastApiResponse = { catId: selectedCat.id, catName: selectedCat.name, type: typeof raw, isArray: Array.isArray(raw), length: Array.isArray(raw) ? raw.length : null, keys: raw && typeof raw === 'object' && !Array.isArray(raw) ? Object.keys(raw) : null, raw: JSON.stringify(raw).substring(0, 500) };
      console.log('[Categories] API response:', lastApiResponse);
      catVideos = Array.isArray(raw) ? raw : (raw?.videos || raw?.items || []);
      selectedCat = { ...selectedCat, video_count: catVideos.length };
    } catch (e) {
      lastApiResponse = { error: e.message, catId: selectedCat?.id };
      console.error('[Categories] API error:', e);
      catVideos = [];
    }
  }

  async function addCategory() {
    if (!newName.trim()) return;
    try {
      await api.createCategory({ name: newName.trim(), color: newColor, description: newDesc.trim() || null });
      toast.success(`"${newName}" erstellt`);
      newName = ''; newDesc = '';
      load();
    } catch (e) { toast.error(e.message); }
  }

  function startEdit(cat) {
    editing = cat.id;
    editName = cat.name;
    editColor = cat.color || '#3F51B5';
    editDesc = cat.description || '';
  }

  async function saveEdit() {
    if (!editName.trim() || !editing) return;
    try {
      await api.updateCategory(editing, { name: editName.trim(), color: editColor, description: editDesc.trim() || null });
      toast.success('Kategorie aktualisiert');
      editing = null;
      load();
      if (selectedCat?.id === editing) selectedCat = { ...selectedCat, name: editName, color: editColor, description: editDesc };
    } catch (e) { toast.error(e.message); }
  }

  async function deleteCategory(id, name) {
    try {
      await api.deleteCategory(id);
      toast.info(`"${name}" gelöscht`);
      if (selectedCat?.id === id) { selectedCat = null; catVideos = []; }
      load();
    } catch (e) { toast.error(e.message); }
  }

  function playVideo(id) {
    navigate(`/watch/${id}`);
  }

  function back() { selectedCat = null; catVideos = []; catSearch = ''; }

  async function cleanupOrphans() {
    try {
      const res = await api.cleanupCategoryOrphans();
      if (res.cleaned > 0) {
        toast.success(`${res.cleaned} verwaiste Zuordnungen entfernt`);
        load();
        loadUnassigned();
      } else {
        toast.info('Keine verwaisten Zuordnungen gefunden');
      }
    } catch (e) { toast.error(e.message); }
  }

  async function autoAssign(mode = 'channel') {
    if (!selectedCat || !autoAssignQuery.trim()) return;
    assigning = true;
    try {
      const opts = mode === 'channel'
        ? { channel: autoAssignQuery.trim() }
        : { keyword: autoAssignQuery.trim() };
      const res = await api.autoAssignCategory(selectedCat.id, opts);
      if (res.assigned > 0) {
        toast.success(`${res.assigned} Videos zugeordnet`);
        await loadCatVideos();
        load();
        loadUnassigned();
      } else {
        toast.info('Keine neuen Videos gefunden');
      }
      autoAssignQuery = '';
    } catch (e) { toast.error(e.message); }
    assigning = false;
  }

  async function loadUnassigned() {
    try { unassignedStats = await api.getUnassignedStats(); } catch { }
  }

  async function quickAssignChannel(channelName) {
    try {
      const res = await api.quickChannelAssign(channelName);
      toast.success(`${res.assigned} Videos → „${res.category_name}"`);
      load();
      loadUnassigned();
    } catch (e) { toast.error(e.message); }
  }

  async function quickAssignAll() {
    assigning = true;
    try {
      const res = await api.quickChannelAssignAll();
      if (res.assigned > 0) {
        toast.success(`${res.assigned} Videos in ${res.categories_created} neue Kategorien sortiert`);
      } else {
        toast.info('Keine unkategorisierten Videos gefunden');
      }
      load();
      loadUnassigned();
    } catch (e) { toast.error(e.message); }
    assigning = false;
  }

  async function showDiagnose() {
    try {
      debugStats = await api.getCategoryDebugStats();
    } catch (e) { toast.error(e.message); }
  }

  async function removeFromCategory(videoId) {
    if (!selectedCat) return;
    try {
      const current = await api.getVideoCategories(videoId);
      const remaining = current.filter(c => c.id !== selectedCat.id).map(c => c.id);
      await api.assignVideoCategories(videoId, remaining);
      catVideos = catVideos.filter(v => v.id !== videoId);
      selectedCat = { ...selectedCat, video_count: catVideos.length };
      load(); // Zähler in Hauptliste aktualisieren
      toast.info('Aus Kategorie entfernt');
    } catch (e) { toast.error(e.message); }
  }

  $effect(() => { load(); loadUnassigned(); });
</script>

<div class="categories-page">
  {#if selectedCat}
    <!-- Category Detail -->
    <div class="detail-header">
      <button class="btn-back" onclick={back}><i class="fa-solid fa-arrow-left"></i> Zurück</button>
      <div class="detail-info">
        <div class="detail-title-row">
          <span class="cat-dot-lg" style="background: {selectedCat.color}"></span>
          <h1>{selectedCat.name}</h1>
        </div>
        {#if selectedCat.description}
          <p class="detail-desc">{selectedCat.description}</p>
        {/if}
        <span class="detail-meta">{catVideos.length} Video{catVideos.length !== 1 ? 's' : ''}</span>
      </div>
      <div class="auto-assign-bar">
        <input class="aa-input" type="text" bind:value={autoAssignQuery} placeholder="Kanal oder Stichwort…"
          onkeydown={(e) => e.key === 'Enter' && autoAssign()} />
        <button class="btn-sm" onclick={() => autoAssign('channel')} disabled={!autoAssignQuery.trim() || assigning}>
          <i class="fa-solid fa-user"></i> Kanal zuordnen
        </button>
        <button class="btn-sm" onclick={() => autoAssign('keyword')} disabled={!autoAssignQuery.trim() || assigning}>
          <i class="fa-solid fa-tag"></i> Stichwort zuordnen
        </button>
      </div>
    </div>

    <!-- Such- und Sortierleiste -->
    <div class="cat-toolbar">
      <div class="cat-search-box">
        <i class="fa-solid fa-magnifying-glass"></i>
        <input type="text" placeholder="In Kategorie suchen…" bind:value={catSearch}
          oninput={() => { clearTimeout(catSearchTimer); catSearchTimer = setTimeout(loadCatVideos, 300); }} />
        {#if catSearch}
          <button class="cat-search-clear" onclick={() => { catSearch = ''; loadCatVideos(); }}>
            <i class="fa-solid fa-xmark"></i>
          </button>
        {/if}
      </div>
      <select class="cat-sort-select" bind:value={catSort} onchange={loadCatVideos}>
        <option value="created_at">Hinzugefügt</option>
        <option value="title">Titel</option>
        <option value="channel_name">Kanal</option>
        <option value="rating">Bewertung</option>
        <option value="duration">Dauer</option>
        <option value="file_size">Größe</option>
      </select>
      <button class="cat-sort-dir" onclick={() => { catSortOrder = catSortOrder === 'desc' ? 'asc' : 'desc'; loadCatVideos(); }}
        title={catSortOrder === 'desc' ? 'Absteigend' : 'Aufsteigend'}>
        <i class="fa-solid {catSortOrder === 'desc' ? 'fa-arrow-down-wide-short' : 'fa-arrow-up-short-wide'}"></i>
      </button>
    </div>

    {#if catVideos.length === 0}
      <div class="empty">
        <i class="fa-solid fa-folder-open empty-icon"></i>
        <p>Keine Videos in dieser Kategorie.</p>
        <p class="empty-hint">Videos über den Bearbeiten-Tab im Player zuordnen.</p>
      </div>
      <!-- Debug-Info: API-Antwort anzeigen -->
      {#if lastApiResponse}
        <details class="debug-panel" open>
          <summary><i class="fa-solid fa-bug"></i> Diagnose</summary>
          <pre class="debug-pre">{JSON.stringify(lastApiResponse, null, 2)}</pre>
          <button class="btn-sm" onclick={showDiagnose} style="margin-top: 8px">
            <i class="fa-solid fa-stethoscope"></i> DB-Diagnose laden
          </button>
          {#if debugStats}
            <pre class="debug-pre">{JSON.stringify(debugStats, null, 2)}</pre>
          {/if}
        </details>
      {/if}
    {:else}
      <div class="video-grid">
        {#each catVideos as v}
          <div class="video-card">
            <button class="card-click" onclick={() => playVideo(v.id)}>
              <div class="thumb-wrap">
                <img src={api.thumbnailUrl(v.id)} alt="" loading="lazy" onerror={(e) => e.target.style.display='none'} />
                {#if v.duration}<span class="duration">{formatDuration(v.duration)}</span>{/if}
              </div>
              <div class="video-info">
                <h3 class="video-title">{v.title}</h3>
                <span class="video-channel">{v.channel_name || 'Unbekannt'}</span>
                <div class="video-meta">
                  <span>{formatSize(v.file_size)}</span>
                  <span>·</span>
                  <span>{formatDateRelative(v.download_date)}</span>
                </div>
              </div>
            </button>
            <button class="card-remove" title="Aus Kategorie entfernen" onclick={() => removeFromCategory(v.id)}>
              <i class="fa-solid fa-xmark"></i>
            </button>
          </div>
        {/each}
      </div>
    {/if}

  {:else}
    <!-- Category List -->
    <h1 class="page-title"><i class="fa-solid fa-list-ul"></i> Kategorien</h1>

    {#if unassignedStats && unassignedStats.unassigned > 0}
      <div class="unassigned-info">
        <i class="fa-solid fa-circle-info"></i>
        <span><strong>{unassignedStats.unassigned}</strong> von {unassignedStats.total} Videos ohne Kategorie</span>
        {#if unassignedStats.top_unassigned_channels.length > 0}
          <div class="ua-channels">
            {#each unassignedStats.top_unassigned_channels.slice(0, 5) as ch}
              <button class="ua-channel-btn" onclick={() => quickAssignChannel(ch.name)} title={'Kategorie "' + ch.name + '" erstellen + ' + ch.count + ' Videos zuordnen'}>
                {ch.name} <span class="ua-ch-count">{ch.count}</span>
              </button>
            {/each}
          </div>
        {/if}
        <div class="ua-actions">
          <button class="btn-sm ua-auto" onclick={quickAssignAll} disabled={assigning} title="Alle Videos automatisch nach Kanal sortieren">
            <i class="fa-solid fa-wand-magic-sparkles"></i> {assigning ? 'Läuft…' : 'Alle nach Kanal'}
          </button>
          <button class="btn-sm ua-cleanup" onclick={cleanupOrphans} title="Verwaiste Zuordnungen entfernen">
            <i class="fa-solid fa-broom"></i> Bereinigen
          </button>
          <button class="btn-sm" onclick={showDiagnose} title="Diagnose anzeigen">
            <i class="fa-solid fa-stethoscope"></i> Diagnose
          </button>
        </div>
      </div>
    {/if}

    {#if debugStats}
      <div class="debug-panel">
        <div class="debug-header">
          <strong><i class="fa-solid fa-stethoscope"></i> Kategorie-Diagnose</strong>
          <button class="btn-xs" onclick={() => debugStats = null}><i class="fa-solid fa-xmark"></i></button>
        </div>
        <div class="debug-stats">
          <span>Zuordnungen gesamt: <strong>{debugStats.total_assignments}</strong></span>
          <span>Videos (ready): <strong>{debugStats.total_ready_videos}</strong></span>
          <span>Davon zugeordnet: <strong>{debugStats.assigned_ready_videos}</strong></span>
          <span>Verwaist: <strong>{debugStats.orphan_assignments}</strong></span>
        </div>
        {#if debugStats.per_category?.length > 0}
          <div class="debug-cats">
            {#each debugStats.per_category as dc}
              <span class="debug-cat-item">
                {dc.name}: <strong>{dc.ready}</strong>/{dc.total}
              </span>
            {/each}
          </div>
        {/if}
        {#if debugStats.total_assignments === 0}
          <div class="debug-hint">
            <i class="fa-solid fa-lightbulb"></i> Noch keine Videos zugeordnet. Nutze &bdquo;Kanal zuordnen&ldquo; / &bdquo;Stichwort zuordnen&ldquo; um Videos automatisch zuzuweisen, oder ordne einzelne Videos &#252;ber den Bearbeiten-Tab im Player zu.
          </div>
        {/if}
      </div>
    {/if}

    <!-- Create Form -->
    <div class="add-card">
      <div class="add-top">
        <input type="text" class="input" placeholder="Neue Kategorie…" bind:value={newName}
               onkeydown={(e) => e.key === 'Enter' && addCategory()} />
        <input type="text" class="input desc-input" placeholder="Beschreibung (optional)" bind:value={newDesc} />
        <button class="btn-primary" onclick={addCategory} disabled={!newName.trim()}>
          <i class="fa-solid fa-plus"></i> Erstellen
        </button>
      </div>
      <!-- Color Palette -->
      <div class="color-palette">
        <span class="palette-label">Farbe:</span>
        {#each MD_COLORS as c}
          <button class="color-swatch" class:selected={newColor === c.hex}
                  style="background: {c.hex}" title={c.name}
                  onclick={() => newColor = c.hex}>
            {#if newColor === c.hex}<i class="fa-solid fa-check swatch-check"></i>{/if}
          </button>
        {/each}
      </div>
    </div>

    {#if loading}
      <div class="loading"><i class="fa-solid fa-spinner fa-spin"></i> Laden…</div>
    {:else}
      <div class="cat-list">
        {#each categories as cat (cat.id)}
          {#if editing === cat.id}
            <div class="cat-item editing">
              <div class="edit-top">
                <input type="text" class="edit-input" bind:value={editName} placeholder="Name" />
                <input type="text" class="edit-input desc" placeholder="Beschreibung" bind:value={editDesc} />
                <button class="btn-xs save" title="Speichern" onclick={saveEdit}><i class="fa-solid fa-check"></i></button>
                <button class="btn-xs" title="Abbrechen" onclick={() => editing = null}><i class="fa-solid fa-xmark"></i></button>
              </div>
              <div class="color-palette compact">
                {#each MD_COLORS as c}
                  <button class="color-swatch sm" class:selected={editColor === c.hex}
                          style="background: {c.hex}" title={c.name}
                          onclick={() => editColor = c.hex}>
                    {#if editColor === c.hex}<i class="fa-solid fa-check swatch-check"></i>{/if}
                  </button>
                {/each}
              </div>
            </div>
          {:else}
            <div class="cat-item">
              <button class="cat-body" onclick={() => selectCategory(cat)}>
                <span class="cat-dot" style="background: {cat.color}"></span>
                <div class="cat-info">
                  <span class="cat-name">{cat.name}</span>
                  {#if cat.description}<span class="cat-desc">{cat.description}</span>{/if}
                </div>
                <span class="cat-count">{cat.video_count || 0} Videos</span>
              </button>
              <button class="btn-icon-sm" onclick={() => startEdit(cat)} title="Bearbeiten">
                <i class="fa-solid fa-pen"></i>
              </button>
              <button class="btn-icon-sm" onclick={() => deleteCategory(cat.id, cat.name)} title="Löschen">
                <i class="fa-regular fa-trash-can"></i>
              </button>
            </div>
          {/if}
        {:else}
          <div class="empty">
            <i class="fa-solid fa-folder-open empty-icon"></i>
            <p>Keine Kategorien vorhanden. Erstelle eine oben.</p>
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</div>

<style>
  .categories-page { padding: 24px; max-width: 1000px; }
  .page-title {
    font-size: 1.4rem; font-weight: 700; color: var(--text-primary);
    margin: 0 0 20px; display: flex; align-items: center; gap: 10px;
  }
  .page-title i { color: var(--accent-primary); }

  /* Add Card */
  .add-card {
    background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 12px; padding: 16px; margin-bottom: 24px;
  }
  .add-top { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
  .input {
    flex: 1; min-width: 140px; padding: 8px 14px; background: var(--bg-tertiary);
    border: 1px solid var(--border-primary); border-radius: 8px;
    color: var(--text-primary); font-size: 0.88rem; outline: none;
  }
  .input:focus { border-color: var(--accent-primary); }
  .desc-input { flex: 1.5; }

  /* Color Palette */
  .color-palette {
    display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  }
  .color-palette.compact { margin-top: 10px; }
  .palette-label { font-size: 0.78rem; color: var(--text-tertiary); margin-right: 4px; }
  .color-swatch {
    width: 28px; height: 28px; border-radius: 50%; border: 2px solid transparent;
    cursor: pointer; transition: all 0.15s; display: flex; align-items: center;
    justify-content: center; padding: 0;
  }
  .color-swatch:hover { transform: scale(1.15); }
  .color-swatch.selected { border-color: var(--text-primary); box-shadow: 0 0 0 2px var(--bg-primary); }
  .color-swatch.sm { width: 22px; height: 22px; }
  .swatch-check { color: #fff; font-size: 0.6rem; text-shadow: 0 1px 2px rgba(0,0,0,0.5); }

  /* Category List */
  .cat-list { display: flex; flex-direction: column; gap: 6px; }
  .cat-item {
    display: flex; align-items: center; gap: 8px;
    padding: 4px 8px; background: var(--bg-secondary);
    border: 1px solid var(--border-primary); border-radius: 10px;
    transition: border-color 0.12s;
  }
  .cat-item:hover { border-color: var(--accent-primary); }
  .cat-item.editing { padding: 12px 14px; flex-direction: column; align-items: stretch; }
  .edit-top { display: flex; gap: 6px; align-items: center; }
  .cat-body {
    display: flex; align-items: center; gap: 12px; flex: 1;
    padding: 8px; background: none; border: none; cursor: pointer;
    text-align: left; color: inherit;
  }
  .cat-dot { width: 14px; height: 14px; border-radius: 50%; flex-shrink: 0; }
  .cat-dot-lg { width: 20px; height: 20px; border-radius: 50%; flex-shrink: 0; }
  .cat-info { display: flex; flex-direction: column; flex: 1; min-width: 0; }
  .cat-name { font-weight: 600; color: var(--text-primary); font-size: 0.92rem; }
  .cat-desc { font-size: 0.76rem; color: var(--text-tertiary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .cat-count { font-size: 0.8rem; color: var(--text-tertiary); white-space: nowrap; }
  .btn-icon-sm {
    background: none; border: none; cursor: pointer; font-size: 0.82rem;
    opacity: 0; transition: opacity 0.12s; padding: 6px; color: var(--text-tertiary);
  }
  .cat-item:hover .btn-icon-sm { opacity: 0.7; }
  .btn-icon-sm:hover { opacity: 1; color: var(--text-primary); }

  .edit-input {
    flex: 1; padding: 5px 10px; background: var(--bg-primary);
    border: 1px solid var(--border-primary); border-radius: 6px;
    color: var(--text-primary); font-size: 0.85rem; outline: none;
  }
  .edit-input.desc { flex: 1.5; }
  .edit-input:focus { border-color: var(--accent-primary); }
  .btn-xs {
    padding: 4px 10px; background: none; border: 1px solid var(--border-primary);
    border-radius: 6px; cursor: pointer; font-size: 0.82rem; color: var(--text-secondary);
  }
  .btn-xs.save { color: var(--status-success); border-color: var(--status-success); }
  .btn-xs:hover { background: var(--bg-hover); }

  /* Detail */
  .detail-header { display: flex; align-items: flex-start; gap: 16px; margin-bottom: 20px; }
  .btn-back {
    padding: 6px 14px; background: none; border: 1px solid var(--border-primary);
    border-radius: 8px; color: var(--text-secondary); font-size: 0.82rem; cursor: pointer;
    display: flex; align-items: center; gap: 6px;
  }
  .btn-back:hover { border-color: var(--accent-primary); }
  .detail-info { flex: 1; }
  .detail-title-row { display: flex; align-items: center; gap: 10px; }
  .detail-info h1 { font-size: 1.3rem; font-weight: 700; color: var(--text-primary); margin: 0; }
  .detail-desc { font-size: 0.85rem; color: var(--text-secondary); margin: 4px 0; }
  .detail-meta { font-size: 0.78rem; color: var(--text-tertiary); }
  .auto-assign-bar { display: flex; gap: 8px; align-items: center; margin-top: 12px; flex-wrap: wrap; }
  .aa-input { flex: 1; min-width: 150px; padding: 6px 10px; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 6px; color: var(--text-primary); font-size: 0.82rem; }
  .aa-input:focus { border-color: var(--accent-primary); outline: none; }
  .unassigned-info { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 12px 16px; background: var(--accent-muted, rgba(59,130,246,0.1)); border: 1px solid var(--accent-primary); border-radius: 10px; margin-bottom: 16px; font-size: 0.82rem; color: var(--text-secondary); }
  .unassigned-info > i { color: var(--accent-primary); flex-shrink: 0; }
  .ua-channels { display: flex; flex-wrap: wrap; gap: 4px; margin-left: 4px; }
  .ua-channel-btn {
    display: inline-flex; align-items: center; gap: 4px; padding: 2px 10px;
    background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 14px; color: var(--text-primary); font-size: 0.75rem;
    cursor: pointer; transition: all 0.12s; font-weight: 500;
  }
  .ua-channel-btn:hover { border-color: var(--accent-primary); background: var(--accent-primary); color: #fff; }
  .ua-channel-btn:hover .ua-ch-count { background: rgba(255,255,255,0.25); color: #fff; }
  .ua-ch-count { font-size: 0.65rem; background: var(--bg-tertiary); color: var(--text-tertiary); padding: 0 5px; border-radius: 8px; font-weight: 600; }
  .ua-actions { display: flex; gap: 4px; margin-left: auto; flex-shrink: 0; }
  .ua-auto { background: var(--accent-primary) !important; color: #fff !important; border-color: var(--accent-primary) !important; }
  .ua-auto:hover { filter: brightness(1.1); }
  .ua-cleanup { }

  /* Debug Panel */
  .debug-panel { padding: 12px 14px; background: var(--bg-secondary); border: 1px solid var(--border-secondary); border-radius: 8px; margin-bottom: 16px; font-size: 0.8rem; }
  .debug-pre { background: var(--bg-tertiary); padding: 8px; border-radius: 6px; font-size: 0.72rem; overflow-x: auto; max-height: 200px; white-space: pre-wrap; word-break: break-all; color: var(--text-secondary); margin-top: 6px; }
  .debug-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
  .debug-stats { display: flex; gap: 16px; flex-wrap: wrap; color: var(--text-secondary); }
  .debug-cats { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
  .debug-cat-item { padding: 2px 8px; background: var(--bg-tertiary); border-radius: 4px; font-size: 0.72rem; color: var(--text-secondary); }
  .debug-hint { margin-top: 10px; padding: 8px 10px; background: rgba(245, 158, 11, 0.1); border: 1px solid #f59e0b; border-radius: 6px; color: var(--text-secondary); font-size: 0.78rem; }
  .debug-hint i { color: #f59e0b; margin-right: 4px; }

  /* Search/Sort Toolbar in Detail */
  .cat-toolbar {
    display: flex; gap: 8px; align-items: center; margin-bottom: 16px; flex-wrap: wrap;
  }
  .cat-search-box {
    display: flex; align-items: center; gap: 8px; flex: 1; min-width: 180px;
    background: var(--bg-tertiary); border: 1px solid var(--border-primary);
    border-radius: 8px; padding: 6px 12px; font-size: 0.85rem;
  }
  .cat-search-box:focus-within { border-color: var(--accent-primary); }
  .cat-search-box i { color: var(--text-tertiary); font-size: 0.8rem; flex-shrink: 0; }
  .cat-search-box input {
    flex: 1; background: none; border: none; color: var(--text-primary);
    font-size: 0.85rem; outline: none; min-width: 0;
  }
  .cat-search-box input::placeholder { color: var(--text-tertiary); }
  .cat-search-clear {
    background: none; border: none; color: var(--text-tertiary);
    cursor: pointer; padding: 2px; font-size: 0.75rem;
  }
  .cat-sort-select {
    padding: 6px 10px; border: 1px solid var(--border-primary);
    border-radius: 8px; background: var(--bg-secondary); color: var(--text-primary);
    font-size: 0.82rem; cursor: pointer;
  }
  .cat-sort-dir {
    width: 34px; height: 34px; display: flex; align-items: center; justify-content: center;
    background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 8px; cursor: pointer; color: var(--text-secondary); font-size: 0.85rem;
  }
  .cat-sort-dir:hover { border-color: var(--accent-primary); color: var(--accent-primary); }

  .video-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 14px;
  }
  .video-card {
    display: flex; flex-direction: column; background: var(--bg-secondary);
    border: 1px solid var(--border-primary); border-radius: 10px;
    overflow: hidden; transition: all 0.15s; position: relative;
  }
  .video-card:hover { border-color: var(--accent-primary); transform: translateY(-1px); }
  .card-click { display: flex; flex-direction: column; cursor: pointer; text-align: left; color: inherit; background: none; border: none; }
  .card-remove {
    position: absolute; top: 6px; right: 6px; width: 26px; height: 26px;
    border-radius: 50%; background: rgba(0,0,0,0.7); color: #fff; border: none;
    font-size: 0.7rem; cursor: pointer; opacity: 0; transition: opacity 0.15s;
    display: flex; align-items: center; justify-content: center; z-index: 2;
  }
  .video-card:hover .card-remove { opacity: 1; }
  .card-remove:hover { background: var(--status-error); }
  .thumb-wrap { position: relative; aspect-ratio: 16/9; background: var(--bg-tertiary); overflow: hidden; }
  .thumb-wrap img { width: 100%; height: 100%; object-fit: cover; }
  .duration {
    position: absolute; bottom: 6px; right: 6px; background: rgba(0,0,0,0.8);
    color: #fff; padding: 1px 5px; border-radius: 3px; font-size: 0.72rem; font-family: monospace;
  }
  .video-info { padding: 10px 12px; display: flex; flex-direction: column; gap: 2px; }
  .video-title {
    font-size: 0.85rem; font-weight: 600; color: var(--text-primary); margin: 0;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .video-channel { font-size: 0.76rem; color: var(--text-secondary); }
  .video-meta { display: flex; gap: 4px; font-size: 0.72rem; color: var(--text-tertiary); }

  .loading, .empty { padding: 50px 20px; text-align: center; color: var(--text-tertiary); }
  .empty-icon { font-size: 2.5rem; color: var(--text-tertiary); margin-bottom: 12px; display: block; }
  .empty-hint { font-size: 0.8rem; color: var(--text-tertiary); margin-top: 4px; }
</style>

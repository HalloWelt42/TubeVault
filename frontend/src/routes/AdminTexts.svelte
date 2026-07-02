<!--
  TubeVault – Admin: Textexport v1.1.0
  Schrittweiser Export in Batches, keine Browser-Popups.
-->
<script>
  import { api } from '../lib/api/client.js';
  import { toast } from '../lib/stores/notifications.js';
  import { navigate } from '../lib/router/router.js';
  import DataTable from '../lib/components/admin/DataTable.svelte';

  let overview = $state(null);
  let loading = $state(false);
  let syncing = $state(false);
  let lastBatchStats = $state(null);
  let batchSize = $state(100);
  const BATCH_OPTIONS = [50, 100, 500, 1000, 5000];

  // Einzel-Test
  let videoInput = $state('');
  let singleBusy = $state(false);

  // Chapters-Batch
  let chapSyncing = $state(false);
  let chapBatchSize = $state(100);
  let chapLastStats = $state(null);

  async function syncChaptersBatch() {
    chapSyncing = true;
    try {
      chapLastStats = await api.adminChaptersSyncBatch(chapBatchSize);
      const { written, skipped, remaining_pending } = chapLastStats;
      toast.success(`Kapitel-Batch: ${written} geschrieben, ${skipped} übersprungen · ${remaining_pending} verbleiben`);
      await loadOverview();
    } catch (e) { toast.error(e.message); }
    chapSyncing = false;
  }

  // Gefahrenzone: Backup / FTS-Rebuild / DB-Purge
  let dangerBusy = $state(false);
  let lastBackup = $state(null);    // { filename, rows, bytes }
  let lastRebuild = $state(null);   // { rebuilt, fts_count }
  let lastPurge = $state(null);     // { purged, remaining_in_db }
  let purgePrimed = $state(false);
  let purgeResetTimer = null;

  async function doBackup() {
    dangerBusy = true;
    try {
      lastBackup = await api.adminTextBackupDescriptions();
      toast.success(`Backup erstellt: ${lastBackup.rows.toLocaleString('de-DE')} Zeilen`);
    } catch (e) { toast.error(e.message); }
    dangerBusy = false;
  }

  async function doRebuild() {
    dangerBusy = true;
    try {
      lastRebuild = await api.adminFtsRebuild();
      toast.success(`FTS5 neu aufgebaut: ${lastRebuild.rebuilt.toLocaleString('de-DE')} Videos`);
    } catch (e) { toast.error(e.message); }
    dangerBusy = false;
  }

  function primePurge() {
    purgePrimed = true;
    if (purgeResetTimer) clearTimeout(purgeResetTimer);
    purgeResetTimer = setTimeout(() => { purgePrimed = false; }, 5000);
  }

  async function doPurge() {
    if (!purgePrimed) { primePurge(); return; }
    purgePrimed = false;
    if (purgeResetTimer) clearTimeout(purgeResetTimer);
    dangerBusy = true;
    try {
      lastPurge = await api.adminTextPurgeDbDescriptions();
      toast.success(`DB-Spalte geleert: ${lastPurge.purged.toLocaleString('de-DE')} Zeilen · ${lastPurge.remaining_in_db.toLocaleString('de-DE')} verbleiben`);
      await loadOverview();
    } catch (e) { toast.error(e.message); }
    dangerBusy = false;
  }

  // Modal-Preview (für Klick aufs Auge in der Tabelle)
  let previewModal = $state(null);  // { video_id, content, loading, error }

  async function openPreview(video_id) {
    previewModal = { video_id, content: '', loading: true, error: null };
    try {
      const text = await api.adminTextGetFile(video_id);
      previewModal = { video_id, content: text, loading: false, error: null };
    } catch (e) {
      previewModal = { video_id, content: '', loading: false, error: e.message };
    }
  }
  function closePreview() { previewModal = null; }

  // Two-Click-Confirm für Datei-Löschen
  let deletePrimed = $state(false);
  let deleteResetTimer = null;
  function primeDelete() {
    deletePrimed = true;
    if (deleteResetTimer) clearTimeout(deleteResetTimer);
    deleteResetTimer = setTimeout(() => { deletePrimed = false; }, 3000);
  }

  async function loadOverview() {
    loading = true;
    try { overview = await api.adminTextOverview(); }
    catch (e) { toast.error(e.message); }
    loading = false;
  }

  async function syncBatch() {
    syncing = true;
    try {
      lastBatchStats = await api.adminTextSyncBatch(batchSize);
      const { written, skipped, errors, remaining_pending } = lastBatchStats;
      toast.success(`Batch: ${written} geschrieben, ${skipped} übersprungen · ${remaining_pending} verbleiben`);
      await loadOverview();
    } catch (e) { toast.error(e.message); }
    syncing = false;
  }

  async function syncSingle() {
    if (!videoInput.trim()) return;
    singleBusy = true;
    try {
      const r = await api.adminTextSyncOne(videoInput.trim());
      if (r.skipped) {
        toast.info(`Bereits aktuell (${r.size} B, Hash identisch)`);
      } else {
        toast.success(`Exportiert: ${r.filename} (${r.size} B)`);
      }
      await loadOverview();
      await loadTable();
    } catch (e) {
      toast.error(e.message);
    }
    singleBusy = false;
  }

  async function loadFile() {
    if (!videoInput.trim()) return;
    // Öffnet das Preview-Modal (gleich wie das Auge-Icon in der Tabelle)
    await openPreview(videoInput.trim());
  }

  async function deleteExport() {
    if (!videoInput.trim()) return;
    // Two-Click-Pattern: erst primen, dann wirklich ausführen
    if (!deletePrimed) {
      primeDelete();
      return;
    }
    deletePrimed = false;
    if (deleteResetTimer) clearTimeout(deleteResetTimer);
    singleBusy = true;
    try {
      const r = await api.adminTextDelete(videoInput.trim());
      toast.info(r.deleted ? 'Datei gelöscht' : 'Keine Datei vorhanden');
      await loadOverview();
      await loadTable();
    } catch (e) { toast.error(e.message); }
    singleBusy = false;
  }

  function percent(as_file, in_db) {
    if (!in_db) return 0;
    return Math.round((as_file / in_db) * 100);
  }

  // Tabelle
  let tableItems = $state([]);
  let tableTotal = $state(0);
  let tablePage = $state(1);
  let tablePerPage = $state(50);
  let tableFilter = $state('all');
  let tableSearch = $state('');
  let tableSort = $state('created_at');
  let tableOrder = $state('desc');
  let tableLoading = $state(false);
  let tableSelected = $state(new Set());

  async function loadTable() {
    tableLoading = true;
    try {
      const res = await api.adminTextList({
        status: tableFilter,
        page: tablePage,
        per_page: tablePerPage,
        search: tableSearch.trim(),
        sort: tableSort,
        order: tableOrder,
      });
      tableItems = res.items;
      tableTotal = res.total;
    } catch (e) { toast.error(e.message); }
    tableLoading = false;
  }

  function onTableTab(id) { tableFilter = id; tablePage = 1; tableSelected = new Set(); loadTable(); }
  function onTableSearch(v) { tableSearch = v; tablePage = 1; loadTable(); }
  function onTableSort(key, order) { tableSort = key; tableOrder = order; loadTable(); }
  function onTablePage(p) { tablePage = p; loadTable(); }
  function onTablePerPage(n) { tablePerPage = n; tablePage = 1; loadTable(); }

  async function bulkExport(ids) {
    try {
      const r = await api.adminTextSyncMany(ids);
      toast.success(`Bulk-Export: ${r.written} geschrieben, ${r.skipped} übersprungen`);
      tableSelected = new Set();
      await loadTable();
      await loadOverview();
    } catch (e) { toast.error(e.message); }
  }

  async function bulkDelete(ids) {
    try {
      const r = await api.adminTextDeleteBulk(ids);
      toast.info(`${r.deleted} von ${r.requested} Dateien gelöscht`);
      tableSelected = new Set();
      await loadTable();
      await loadOverview();
    } catch (e) { toast.error(e.message); }
  }

  async function rowExport(vid) {
    try {
      await api.adminTextSyncOne(vid);
      toast.success(`Exportiert: ${vid}`);
      await loadTable();
      await loadOverview();
    } catch (e) { toast.error(e.message); }
  }
  async function rowView(vid) {
    await openPreview(vid);
  }
  function rowOpenVideo(vid) { navigate(`/watch/${vid}`); }

  // Spalten-Config
  const COLUMNS = [
    { key: 'exported', label: 'Status', width: '70px', align: 'center' },
    { key: 'title', label: 'Video', sortable: true },
    { key: 'db_length', label: 'DB-Länge', sortable: true, align: 'right', width: '110px' },
    { key: 'file_size', label: 'Datei', align: 'right', width: '90px' },
    { key: 'exported_at', label: 'Exportiert', sortable: true, width: '150px' },
  ];

  // Tabs mit Live-Counts (aus Overview)
  let tableTabs = $derived([
    { id: 'all', label: 'Alle', count: overview?.description?.in_db },
    { id: 'exported', label: 'Exportiert', count: overview?.description?.as_file },
    { id: 'pending', label: 'Ausstehend', count: overview?.description?.pending },
  ]);

  $effect(() => { loadOverview(); loadTable(); });
</script>

<div class="admin-page">
  <header class="admin-header">
    <h1><i class="fa-solid fa-file-lines"></i> Textexport</h1>
    <p class="subtitle">
      Dokument-artige Daten aus der DB in Dateien auslagern. Jede Datei trägt
      die Video-ID als Ordnername, so dass alle Daten eines Videos beisammen liegen:
      <code>texts/&lt;video_id&gt;/description.txt</code>. Die DB-Inhalte bleiben unberührt.
    </p>
  </header>

  <!-- Übersicht -->
  <section class="panel">
    <div class="panel-head">
      <h2>Übersicht</h2>
      <button class="btn-refresh" onclick={loadOverview} disabled={loading}>
        <i class="fa-solid {loading ? 'fa-spinner fa-spin' : 'fa-arrows-rotate'}"></i>
        Neu laden
      </button>
    </div>
    {#if overview?.texts_root}
      <div class="root-info">
        <i class="fa-solid fa-folder-open"></i>
        <span class="root-label">Root:</span>
        <code class="root-path">{overview.texts_root}/&lt;video_id&gt;/&lt;kind&gt;.&lt;ext&gt;</code>
        <button class="root-copy" onclick={() => navigator.clipboard?.writeText(overview.texts_root)} title="Pfad kopieren">
          <i class="fa-solid fa-copy"></i>
        </button>
      </div>
    {/if}
    {#if overview}
      <table class="overview-table">
        <thead>
          <tr><th>Daten-Typ</th><th>in DB</th><th>als Datei</th><th>ausstehend</th><th>Fortschritt</th></tr>
        </thead>
        <tbody>
          <tr>
            <td><strong>Beschreibungen</strong><br><span class="hint">description.txt</span></td>
            <td class="num">{overview.description.in_db.toLocaleString('de-DE')}</td>
            <td class="num">{overview.description.as_file.toLocaleString('de-DE')}</td>
            <td class="num">{overview.description.pending.toLocaleString('de-DE')}</td>
            <td>
              <div class="bar"><div class="bar-fill" style="width: {percent(overview.description.as_file, overview.description.in_db)}%"></div></div>
              <span class="bar-label">{percent(overview.description.as_file, overview.description.in_db)}%</span>
            </td>
          </tr>
          {#if overview.chapters}
          <tr>
            <td><strong>Kapitel</strong><br><span class="hint">chapters.json</span></td>
            <td class="num">{overview.chapters.in_db.toLocaleString('de-DE')}</td>
            <td class="num">{overview.chapters.as_file.toLocaleString('de-DE')}</td>
            <td class="num">{overview.chapters.pending.toLocaleString('de-DE')}</td>
            <td>
              <div class="bar"><div class="bar-fill" style="width: {percent(overview.chapters.as_file, overview.chapters.in_db)}%"></div></div>
              <span class="bar-label">{percent(overview.chapters.as_file, overview.chapters.in_db)}%</span>
            </td>
          </tr>
          {/if}
        </tbody>
      </table>
    {/if}
  </section>

  <!-- Batch-Export -->
  <section class="panel">
    <div class="panel-head">
      <h2>Batch-Export</h2>
    </div>
    <p class="hint">
      Schrittweiser Export der noch ausstehenden Beschreibungen. Du bestimmst die
      Batch-Größe. Kein Popup, kein Datenverlust-Risiko — nur Dateien werden geschrieben,
      DB wird nur gelesen.
    </p>
    <div class="batch-row">
      <label>Batch-Größe</label>
      <div class="batch-picker">
        {#each BATCH_OPTIONS as n}
          <button class="batch-opt" class:active={batchSize === n} onclick={() => batchSize = n}>
            {n.toLocaleString('de-DE')}
          </button>
        {/each}
      </div>
      <button class="btn-run" onclick={syncBatch}
              disabled={syncing || (overview && overview.description.pending === 0)}>
        {#if syncing}
          <i class="fa-solid fa-spinner fa-spin"></i> Läuft…
        {:else}
          <i class="fa-solid fa-play"></i> Nächste {batchSize.toLocaleString('de-DE')} exportieren
        {/if}
      </button>
    </div>

    {#if lastBatchStats}
      <div class="batch-result">
        <div class="batch-stat written"><strong>{lastBatchStats.written}</strong> geschrieben</div>
        <div class="batch-stat skipped"><strong>{lastBatchStats.skipped}</strong> übersprungen</div>
        {#if lastBatchStats.errors > 0}
          <div class="batch-stat err"><strong>{lastBatchStats.errors}</strong> Fehler</div>
        {/if}
        <div class="batch-stat remaining"><strong>{lastBatchStats.remaining_pending}</strong> verbleiben</div>
      </div>
    {/if}
  </section>

  <!-- Chapters-Batch -->
  <section class="panel">
    <div class="panel-head">
      <h2><i class="fa-solid fa-list-ol"></i> Kapitel-Export</h2>
    </div>
    <p class="hint">
      Export der Chapter-Listen aus der <code>chapters</code>-Tabelle als
      <code>chapters.json</code> pro Video (JSON-Array, sortiert nach start_time).
      Thumbnail-URLs werden nicht persistiert, nur Titel + Zeitstempel.
    </p>
    <div class="batch-row">
      <label>Batch-Größe</label>
      <div class="batch-picker">
        {#each BATCH_OPTIONS as n}
          <button class="batch-opt" class:active={chapBatchSize === n} onclick={() => chapBatchSize = n}>
            {n.toLocaleString('de-DE')}
          </button>
        {/each}
      </div>
      <button class="btn-run" onclick={syncChaptersBatch}
              disabled={chapSyncing || (overview?.chapters && overview.chapters.pending === 0)}>
        {#if chapSyncing}
          <i class="fa-solid fa-spinner fa-spin"></i> Läuft…
        {:else}
          <i class="fa-solid fa-play"></i> Nächste {chapBatchSize.toLocaleString('de-DE')} exportieren
        {/if}
      </button>
    </div>

    {#if chapLastStats}
      <div class="batch-result">
        <div class="batch-stat written"><strong>{chapLastStats.written}</strong> geschrieben</div>
        <div class="batch-stat skipped"><strong>{chapLastStats.skipped}</strong> übersprungen</div>
        {#if chapLastStats.errors > 0}
          <div class="batch-stat err"><strong>{chapLastStats.errors}</strong> Fehler</div>
        {/if}
        <div class="batch-stat remaining"><strong>{chapLastStats.remaining_pending}</strong> verbleiben</div>
      </div>
    {/if}
  </section>

  <!-- Tabelle -->
  <section class="panel">
    <div class="panel-head">
      <h2>Videos</h2>
    </div>

    <DataTable
      columns={COLUMNS}
      rows={tableItems}
      total={tableTotal}
      page={tablePage}
      perPage={tablePerPage}
      sort={tableSort}
      order={tableOrder}
      loading={tableLoading}
      filterTabs={tableTabs}
      activeTab={tableFilter}
      searchValue={tableSearch}
      searchPlaceholder="Suche in Titel oder Video-ID…"
      selectable={true}
      selected={tableSelected}
      onSelectChange={(s) => tableSelected = s}
      bulkActions={[
        { label: 'Markierte exportieren', icon: 'fa-solid fa-file-arrow-up', onClick: bulkExport },
        { label: 'Markierte Dateien löschen', icon: 'fa-solid fa-trash-can', variant: 'danger', onClick: bulkDelete },
      ]}
      onTabChange={onTableTab}
      onSearch={onTableSearch}
      onSort={onTableSort}
      onPage={onTablePage}
      onPerPage={onTablePerPage}
    >
      {#snippet rowCell(col, row)}
        {#if col.key === 'exported'}
          {#if row.exported}
            <span class="status-pill ok" title="exportiert"><i class="fa-solid fa-check"></i></span>
          {:else}
            <span class="status-pill pending" title="ausstehend"><i class="fa-solid fa-hourglass-half"></i></span>
          {/if}
        {:else if col.key === 'title'}
          <div class="video-title">{row.title || '–'}</div>
          <div class="video-sub">
            <span class="vid">{row.id}</span>
            {#if row.channel_name}<span class="vch">· {row.channel_name}</span>{/if}
          </div>
        {:else if col.key === 'db_length'}
          <span class="mono">{(row.db_length || 0).toLocaleString('de-DE')}</span>
        {:else if col.key === 'file_size'}
          <span class="mono dim">{row.file_size ? row.file_size.toLocaleString('de-DE') + ' B' : '–'}</span>
        {:else if col.key === 'exported_at'}
          <span class="mono dim">{row.exported_at || '–'}</span>
        {/if}
      {/snippet}

      {#snippet rowActions(row)}
        {#if !row.exported}
          <button class="mini-btn" onclick={() => rowExport(row.id)} title="Exportieren">
            <i class="fa-solid fa-file-arrow-up"></i>
          </button>
        {/if}
        <button class="mini-btn" onclick={() => rowView(row.id)} title="Datei lesen">
          <i class="fa-solid fa-eye"></i>
        </button>
        <button class="mini-btn" onclick={() => rowOpenVideo(row.id)} title="Video öffnen">
          <i class="fa-solid fa-arrow-up-right-from-square"></i>
        </button>
      {/snippet}
    </DataTable>
  </section>

  <!-- Preview-Modal -->
  {#if previewModal}
    <div class="modal-backdrop" onclick={closePreview} role="presentation">
      <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog">
        <header class="modal-head">
          <div>
            <h3>Datei-Inhalt</h3>
            <code class="modal-path">{overview?.texts_root}/{previewModal.video_id}/description.txt</code>
          </div>
          <button class="modal-close" onclick={closePreview} title="Schließen">
            <i class="fa-solid fa-xmark"></i>
          </button>
        </header>
        <div class="modal-body">
          {#if previewModal.loading}
            <div class="modal-state"><i class="fa-solid fa-spinner fa-spin"></i> Laden…</div>
          {:else if previewModal.error}
            <div class="modal-state err">
              <i class="fa-solid fa-triangle-exclamation"></i>
              {previewModal.error}
              <div class="hint" style="margin-top:8px">Hinweis: Video wurde noch nicht exportiert. Oben „Exportieren" klicken.</div>
            </div>
          {:else}
            <pre class="modal-content">{previewModal.content}</pre>
          {/if}
        </div>
      </div>
    </div>
  {/if}

  <!-- Einzel-Test -->
  <section class="panel">
    <div class="panel-head">
      <h2>Einzelnes Video</h2>
    </div>
    <p class="hint">
      YouTube-Video-ID, dann exportieren oder Datei-Inhalt direkt prüfen.
    </p>
    <div class="single-row">
      <input type="text" placeholder="z.B. dQw4w9WgXcQ" bind:value={videoInput}
             oninput={() => { deletePrimed = false; }} />
      <button class="btn-secondary" onclick={syncSingle} disabled={singleBusy || !videoInput.trim()}>
        <i class="fa-solid fa-file-arrow-up"></i> Exportieren
      </button>
      <button class="btn-secondary" onclick={loadFile} disabled={singleBusy || !videoInput.trim()}>
        <i class="fa-solid fa-eye"></i> Datei lesen
      </button>
      <button class="btn-danger" class:primed={deletePrimed}
              onclick={deleteExport} disabled={singleBusy || !videoInput.trim()}>
        <i class="fa-solid {deletePrimed ? 'fa-triangle-exclamation' : 'fa-trash-can'}"></i>
        {deletePrimed ? 'Nochmal klicken = löschen' : 'Datei löschen'}
      </button>
    </div>

  </section>

  <!-- Gefahrenzone: DB-Spalte leeren -->
  <section class="panel danger-zone">
    <div class="panel-head">
      <h2><i class="fa-solid fa-triangle-exclamation"></i> Gefahrenzone · DB-Spalte leeren</h2>
    </div>
    <p class="hint">
      Wenn alle Dateien sitzen und FTS5 aus dem Resolver neu gebaut ist, kann
      <code>videos.description</code> geleert werden. Ab diesem Moment sind die
      Dateien die Wahrheit, die DB nur noch Index.
      <strong>Nur Zeilen werden geleert, für die eine Datei existiert</strong> –
      ungeschriebene bleiben unberührt.
    </p>

    <div class="danger-steps">
      <div class="step">
        <div class="step-num">1</div>
        <div class="step-body">
          <strong>Backup</strong>
          <div class="step-hint">Dumpt alle DB-Descriptions als JSONL.gz + SQL.gz nach <code>exports/text-backups/</code>.</div>
          <button class="btn-secondary" onclick={doBackup} disabled={dangerBusy}>
            <i class="fa-solid fa-box-archive"></i> Backup erstellen
          </button>
          {#if lastBackup}
            <div class="step-result ok">
              <i class="fa-solid fa-check"></i>
              {lastBackup.rows?.toLocaleString('de-DE')} Zeilen gesichert
              {#if lastBackup.filename}<code class="result-path">{lastBackup.filename}</code>{/if}
            </div>
          {/if}
        </div>
      </div>

      <div class="step">
        <div class="step-num">2</div>
        <div class="step-body">
          <strong>FTS5 neu aufbauen</strong>
          <div class="step-hint">Baut den Volltextindex aus dem Resolver (File-first) neu. So bleibt die Suche funktionsfähig, auch wenn die DB-Spalte leer ist.</div>
          <button class="btn-secondary" onclick={doRebuild} disabled={dangerBusy}>
            <i class="fa-solid fa-magnifying-glass"></i> FTS5 neu indexieren
          </button>
          {#if lastRebuild}
            <div class="step-result ok">
              <i class="fa-solid fa-check"></i>
              {lastRebuild.rebuilt?.toLocaleString('de-DE')} Videos indexiert · {lastRebuild.fts_count?.toLocaleString('de-DE')} Einträge im Index
            </div>
          {/if}
        </div>
      </div>

      <div class="step">
        <div class="step-num">3</div>
        <div class="step-body">
          <strong>DB-Spalte leeren</strong>
          <div class="step-hint">Setzt <code>videos.description = NULL</code> für alle Zeilen, deren Datei existiert. Irreversibel ohne Backup!</div>
          <button class="btn-danger big"
                  class:primed={purgePrimed}
                  onclick={doPurge} disabled={dangerBusy}>
            <i class="fa-solid {purgePrimed ? 'fa-triangle-exclamation' : 'fa-eraser'}"></i>
            {purgePrimed ? 'Nochmal klicken = endgültig leeren' : 'DB-Spalte leeren'}
          </button>
          {#if lastPurge}
            <div class="step-result ok">
              <i class="fa-solid fa-check"></i>
              {lastPurge.purged?.toLocaleString('de-DE')} geleert · {lastPurge.remaining_in_db?.toLocaleString('de-DE')} verbleiben
            </div>
          {/if}
        </div>
      </div>
    </div>
  </section>
</div>

<style>
  .admin-page { padding: 32px 40px; width: 100%; }
  .admin-header h1 {
    display: flex; align-items: center; gap: 12px;
    margin: 0 0 6px; font-size: 1.5rem; color: var(--text-primary);
  }
  .admin-header h1 i { color: var(--accent-primary); }
  .subtitle { color: var(--text-tertiary); font-size: 0.88rem; max-width: 780px; margin: 0 0 28px; line-height: 1.5; }
  .subtitle code { background: var(--bg-tertiary); padding: 1px 6px; border-radius: 4px; font-size: 0.82rem; }

  .panel {
    background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 14px; padding: 20px 24px; margin-bottom: 20px;
  }
  .panel-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
  .panel-head h2 { margin: 0; font-size: 1.05rem; color: var(--text-primary); }
  .hint { font-size: 0.8rem; color: var(--text-tertiary); margin: 0 0 14px; line-height: 1.5; }

  .btn-refresh { display: flex; align-items: center; gap: 6px; background: var(--bg-tertiary); border: 1px solid var(--border-primary); color: var(--text-secondary); padding: 5px 12px; border-radius: 8px; font-size: 0.82rem; cursor: pointer; }
  .btn-refresh:hover:not(:disabled) { border-color: var(--accent-primary); color: var(--accent-primary); }

  /* Overview */
  .overview-table { width: 100%; border-collapse: collapse; }
  .overview-table th { text-align: left; font-size: 0.74rem; text-transform: uppercase; color: var(--text-tertiary); padding: 8px 12px; border-bottom: 1px solid var(--border-primary); font-weight: 600; }
  .overview-table td { padding: 14px 12px; font-size: 0.92rem; color: var(--text-secondary); }
  .overview-table td:first-child { color: var(--text-primary); }
  .overview-table td.num { font-family: monospace; text-align: right; min-width: 110px; }

  .bar { height: 8px; background: var(--bg-tertiary); border-radius: 4px; overflow: hidden; width: 180px; display: inline-block; vertical-align: middle; }
  .bar-fill { height: 100%; background: var(--status-success); transition: width 0.3s; }
  .bar-label { font-family: monospace; font-size: 0.82rem; margin-left: 10px; color: var(--text-tertiary); }

  /* Batch */
  .batch-row { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
  .batch-row label { font-size: 0.85rem; color: var(--text-secondary); font-weight: 600; }
  .batch-picker { display: flex; gap: 2px; }
  .batch-opt { padding: 7px 14px; background: var(--bg-tertiary); border: 1px solid var(--border-primary); color: var(--text-secondary); cursor: pointer; font-size: 0.82rem; font-family: monospace; }
  .batch-opt:first-child { border-radius: 8px 0 0 8px; }
  .batch-opt:last-child { border-radius: 0 8px 8px 0; }
  .batch-opt + .batch-opt { border-left: none; }
  .batch-opt:hover { color: var(--text-primary); }
  .batch-opt.active { background: var(--accent-primary); color: #fff; border-color: var(--accent-primary); }

  .btn-run {
    display: flex; align-items: center; gap: 8px;
    padding: 9px 18px; background: var(--accent-primary); color: #fff;
    border: none; border-radius: 8px; font-size: 0.88rem; font-weight: 600;
    cursor: pointer; transition: filter 0.12s;
  }
  .btn-run:hover:not(:disabled) { filter: brightness(1.1); }
  .btn-run:disabled { opacity: 0.5; cursor: not-allowed; }

  .batch-result { display: flex; gap: 16px; margin-top: 16px; flex-wrap: wrap; }
  .batch-stat {
    padding: 8px 14px; border-radius: 8px; font-size: 0.85rem;
    background: var(--bg-tertiary); color: var(--text-secondary);
  }
  .batch-stat strong { color: var(--text-primary); font-size: 1.05rem; margin-right: 6px; }
  .batch-stat.written { background: rgba(34,197,94,0.1); color: var(--status-success); }
  .batch-stat.err { background: rgba(239,68,68,0.1); color: var(--status-error); }
  .batch-stat.remaining { background: var(--accent-muted); color: var(--accent-primary); }

  /* Single */
  .single-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .single-row input {
    flex: 1 1 280px; padding: 9px 14px; background: var(--bg-tertiary);
    border: 1px solid var(--border-primary); border-radius: 8px;
    color: var(--text-primary); font-family: monospace; font-size: 0.9rem; outline: none;
  }
  .single-row input:focus { border-color: var(--accent-primary); }
  .btn-secondary, .btn-danger {
    display: flex; align-items: center; gap: 6px;
    padding: 9px 14px; background: var(--bg-tertiary);
    border: 1px solid var(--border-primary); border-radius: 8px;
    color: var(--text-secondary); cursor: pointer; font-size: 0.85rem;
    transition: all 0.12s; white-space: nowrap;
  }
  .btn-secondary:hover:not(:disabled) { border-color: var(--accent-primary); color: var(--accent-primary); }
  .btn-danger { border-color: rgba(239,68,68,0.4); color: var(--status-error); }
  .btn-danger:hover:not(:disabled) { background: rgba(239,68,68,0.08); border-color: var(--status-error); }
  .btn-danger.primed { background: var(--status-error); color: #fff; border-color: var(--status-error); animation: pulse 1s infinite; }
  @keyframes pulse { 50% { filter: brightness(1.15); } }
  .btn-secondary:disabled, .btn-danger:disabled { opacity: 0.5; cursor: not-allowed; }

  /* Tabellen-Zell-Styles (von DataTable ausgelagert, pro-Page-spezifisch) */
  .status-pill { display: inline-flex; width: 22px; height: 22px; align-items: center; justify-content: center; border-radius: 50%; font-size: 0.72rem; }
  .status-pill.ok { background: rgba(34,197,94,0.15); color: var(--status-success); }
  .status-pill.pending { background: rgba(245,158,11,0.15); color: var(--status-warning, #f59e0b); }

  .video-title { font-weight: 600; color: var(--text-primary); font-size: 0.88rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 500px; }
  .video-sub { font-size: 0.75rem; color: var(--text-tertiary); font-family: monospace; margin-top: 2px; }
  .vch { color: var(--text-secondary); font-family: inherit; margin-left: 4px; }

  .mono { font-family: monospace; }
  .mono.dim { color: var(--text-tertiary); font-size: 0.82rem; }

  .mini-btn { width: 28px; height: 28px; border-radius: 6px; background: var(--bg-tertiary); border: 1px solid var(--border-primary); color: var(--text-secondary); cursor: pointer; display: inline-flex; align-items: center; justify-content: center; font-size: 0.78rem; margin-left: 3px; }
  .mini-btn:hover { border-color: var(--accent-primary); color: var(--accent-primary); }

  /* Root-Pfad-Anzeige */
  .root-info {
    display: flex; align-items: center; gap: 8px;
    padding: 10px 14px; margin-bottom: 14px;
    background: var(--bg-tertiary); border: 1px solid var(--border-primary);
    border-radius: 8px;
    font-size: 0.82rem;
  }
  .root-info > i { color: var(--accent-primary); }
  .root-label { color: var(--text-tertiary); font-weight: 600; }
  .root-path { flex: 1; font-family: monospace; color: var(--text-primary); background: var(--bg-primary); padding: 3px 10px; border-radius: 5px; font-size: 0.82rem; overflow-x: auto; white-space: nowrap; }
  .root-copy { background: none; border: none; color: var(--text-tertiary); cursor: pointer; padding: 4px 8px; border-radius: 4px; }
  .root-copy:hover { color: var(--accent-primary); background: var(--bg-secondary); }

  /* Modal */
  .modal-backdrop {
    position: fixed; inset: 0; z-index: 100;
    background: rgba(0, 0, 0, 0.7); backdrop-filter: blur(3px);
    display: flex; align-items: center; justify-content: center;
    padding: 20px;
  }
  .modal {
    background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 14px; width: 100%; max-width: 900px; max-height: 90vh;
    display: flex; flex-direction: column;
    box-shadow: 0 20px 40px rgba(0,0,0,0.5);
  }
  .modal-head {
    display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;
    padding: 16px 20px; border-bottom: 1px solid var(--border-primary);
  }
  .modal-head h3 { margin: 0 0 4px; font-size: 1.05rem; color: var(--text-primary); }
  .modal-path { font-family: monospace; font-size: 0.76rem; color: var(--text-tertiary); background: var(--bg-tertiary); padding: 2px 8px; border-radius: 4px; word-break: break-all; }
  .modal-close { background: none; border: none; color: var(--text-tertiary); cursor: pointer; padding: 4px 10px; border-radius: 6px; font-size: 1rem; flex-shrink: 0; }
  .modal-close:hover { color: var(--status-error); background: var(--bg-tertiary); }
  .modal-body { flex: 1; min-height: 0; overflow: hidden; display: flex; }
  .modal-content {
    margin: 0; padding: 16px 20px; flex: 1;
    background: var(--bg-primary); font-size: 0.88rem;
    white-space: pre-wrap; word-break: break-word;
    overflow-y: auto; line-height: 1.5; color: var(--text-secondary);
  }
  .modal-state { padding: 40px; text-align: center; color: var(--text-tertiary); flex: 1; }
  .modal-state.err { color: var(--status-error); }

  /* Gefahrenzone */
  .danger-zone { border-color: rgba(239,68,68,0.35); }
  .danger-zone .panel-head h2 { color: var(--status-error); }
  .danger-zone .panel-head h2 i { margin-right: 6px; }
  .danger-zone code { background: var(--bg-tertiary); padding: 1px 6px; border-radius: 4px; font-size: 0.82rem; font-family: monospace; }

  .danger-steps { display: flex; flex-direction: column; gap: 18px; margin-top: 6px; }
  .step { display: flex; gap: 14px; align-items: flex-start; }
  .step-num {
    flex-shrink: 0;
    width: 28px; height: 28px; border-radius: 50%;
    background: var(--bg-tertiary); color: var(--text-secondary);
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-family: monospace;
  }
  .step-body { flex: 1; display: flex; flex-direction: column; gap: 8px; }
  .step-body > strong { color: var(--text-primary); font-size: 0.95rem; }
  .step-hint { color: var(--text-tertiary); font-size: 0.82rem; line-height: 1.5; }
  .step-result { margin-top: 4px; padding: 6px 10px; border-radius: 6px; font-size: 0.82rem; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .step-result.ok { background: rgba(34,197,94,0.1); color: var(--status-success); }
  .result-path { font-family: monospace; font-size: 0.78rem; background: var(--bg-tertiary); padding: 2px 8px; border-radius: 4px; color: var(--text-secondary); word-break: break-all; }

  .btn-danger.big { padding: 10px 18px; font-size: 0.9rem; }
</style>

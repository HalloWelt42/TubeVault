<!--
  TubeVault – Import-Wizard v1.9.15
  2-Panel: Dateiliste | Detail + Vergleich
  Klare Status-Anzeige, prüfbare Matches, wählbare Kandidaten
  © HalloWelt42 – Private Nutzung
-->
<script>
  import { api } from '../lib/api/client.js';
  import { toast } from '../lib/stores/notifications.js';
  import { formatSize, formatDuration } from '../lib/utils/format.js';
  import { onMount } from 'svelte';
  import { route } from '../lib/router/router.js';
  import { updateParams } from '../lib/router/router.js';

  let phase = $state('sessions');
  let sessions = $state([]);
  let activeSession = $state(null);
  let scanPath = $state('/app/data/scan');
  let youtubeArchive = $state(true);
  let scanJobId = $state(null);
  let scanProgress = $state(0);
  let scanStatus = $state('');
  let scanPaused = $state(false);
  let scanLoading = $state(false);
  let pollTimer = $state(null);
  let results = $state([]);
  let resultsMeta = $state({ total: 0, page: 1, per_page: 50, total_pages: 1, folders: [] });
  let sessionStats = $state(null);
  let matchFilter = $state('undecided');
  let folderFilter = $state('');
  let searchQuery = $state('');
  let currentPage = $state(1);
  let selectedItem = $state(null);
  let selectedIdx = $state(-1);
  let assignChannel = $state('');
  let channels = $state([]);
  let previewPlaying = $state(false);
  let selectedCandidate = $state(null);
  let showBulkPanel = $state(false);

  // YouTube-Suche im Detail-Panel
  let ytSearchQuery = $state('');
  let ytSearchResults = $state([]);
  let ytSearching = $state(false);
  let ytLinking = $state(false);
  let importingOwn = $state(false);
  let defaultCategory = $state('');
  let categories = $state([]);

  let decidedCount = $derived(sessionStats?.decided || 0);
  let totalCount = $derived(sessionStats?.total || 0);
  let openCount = $derived(totalCount - decidedCount);
  let filterPills = $derived([
    { key: 'all', label: 'Alle', count: totalCount },
    { key: 'matched', label: 'Treffer', count: (sessionStats?.exact||0) + (sessionStats?.exact_rss||0) + (sessionStats?.fuzzy||0) },
    { key: 'new', label: 'Neu', count: sessionStats?.unmatched },
    { key: 'duplicate', label: 'Duplikate', count: sessionStats?.duplicates },
    { key: 'undecided', label: 'Offen', count: openCount },
    { key: 'decided', label: 'Erledigt', count: decidedCount },
  ]);

  onMount(async () => {
    await loadSessions();
    await loadChannels();
    await loadCategories();
    // URL-basierte State-Wiederherstellung
    const params = $route.params || {};
    if (params.session) {
      if (params.folder) folderFilter = params.folder;
      if (params.q) searchQuery = params.q;
      if (params.status) matchFilter = params.status;
      const page = params.page ? parseInt(params.page) : 1;
      const sid = parseInt(params.session);
      try {
        const s = await api.request('/api/own-videos/scan-session/' + sid);
        activeSession = s; sessionStats = s?.stats;
        await loadResults(sid, page);
        phase = 'review';
      } catch { /* Session existiert nicht mehr */ }
    }
    return () => { if (pollTimer) clearInterval(pollTimer); };
  });

  async function loadSessions() {
    try { sessions = (await api.request('/api/own-videos/scan-sessions')) || []; } catch(e) { console.error(e); }
  }
  async function loadChannels() {
    try {
      const d = await api.request('/api/subscriptions?per_page=500');
      channels = (d?.subscriptions || []).map(s => ({ id: s.channel_id, name: s.channel_name, videoCount: s.video_count || 0 }));
    } catch(e) { console.error(e); }
  }

  async function startScan() {
    if (scanLoading) return; scanLoading = true;
    try {
      const d = await api.request('/api/own-videos/scan-job', { method: 'POST', body: { path: scanPath, youtube_archive: youtubeArchive } });
      scanJobId = d.job_id; activeSession = { id: d.session_id, status: 'running', total_files: d.total_files };
      phase = 'scanning'; scanProgress = 0; scanStatus = '0/' + d.total_files + ' Dateien...'; startPolling();
      toast.success('Scan gestartet: ' + d.total_files + ' Dateien');
    } catch(e) { toast.error('Scan-Fehler: ' + (e.message || e)); scanLoading = false; }
  }
  function startPolling() { if (pollTimer) clearInterval(pollTimer); pollTimer = setInterval(pollJob, 2000); }
  async function pollJob() {
    if (!scanJobId) return;
    try {
      const j = await api.request('/api/jobs/' + scanJobId); if (!j) return;
      scanProgress = j.progress || 0; scanStatus = j.description || '';
      if (['done','error','cancelled'].includes(j.status)) {
        clearInterval(pollTimer); pollTimer = null; scanLoading = false;
        if (j.status === 'done') { toast.success('Scan fertig!'); if (j.metadata?.session_id) await loadSessionResults(j.metadata.session_id); }
        else { toast.error(j.status === 'error' ? 'Fehler: ' + j.error : 'Abgebrochen'); phase = 'sessions'; }
      }
    } catch(e) { console.error(e); }
  }
  async function pauseScan() { try { await api.request('/api/jobs/' + scanJobId + '/pause', { method: 'POST' }); scanPaused = true; } catch(e) { toast.error(e.message); } }
  async function resumeScan() { try { await api.request('/api/jobs/' + scanJobId + '/resume', { method: 'POST' }); scanPaused = false; } catch(e) { toast.error(e.message); } }
  async function cancelScan() {
    try { await api.request('/api/jobs/' + scanJobId + '/cancel', { method: 'POST' }); clearInterval(pollTimer); pollTimer = null;
      phase = 'sessions'; scanJobId = null; scanPaused = false; scanLoading = false; toast.success('Abgebrochen'); await loadSessions();
    } catch(e) { toast.error(e.message); }
  }

  async function loadSessionResults(sid) {
    try {
      const s = await api.request('/api/own-videos/scan-session/' + sid);
      activeSession = s; sessionStats = s?.stats;
      await loadResults(sid);
      phase = 'review';
      updateParams({ session: sid });
    } catch(e) { toast.error('Session: ' + e.message); phase = 'sessions'; }
  }
  async function loadResults(sid, page = 1) {
    const id = sid || activeSession?.id; if (!id) return;
    try {
      const p = new URLSearchParams({ page, per_page: 50 });
      if (matchFilter && matchFilter !== 'all') p.set('match_filter', matchFilter);
      if (folderFilter) p.set('folder', folderFilter);
      if (searchQuery) p.set('search', searchQuery);
      const d = await api.request('/api/own-videos/scan-results/' + id + '?' + p);
      results = d.results || []; resultsMeta = d; currentPage = page;
      if (results.length > 0 && !selectedItem) selectItem(results[0], 0);
      // URL sync
      updateParams({ session: id, page: page > 1 ? page : null, folder: folderFilter || null, q: searchQuery || null, status: matchFilter !== 'undecided' ? matchFilter : null });
    } catch(e) { toast.error('Laden: ' + e.message); }
  }

  async function skipItem(stgId) {
    try {
      await api.stagingSkip(stgId);
      toast.success('⏭ Übersprungen');
      await refreshStats(); removeAndNext(stgId);
    } catch(e) { toast.error(e.message); }
  }

  async function replaceItem(stgId) {
    try {
      const res = await api.stagingReplace(stgId);
      toast.success('🔄 Datei ersetzt: ' + (res.video_id || ''));
      await refreshStats(); removeAndNext(stgId);
    } catch(e) { toast.error(e.message); }
  }

  // Bulk-Aktionen: nur Skip (kein Datei-Operation nötig)
  async function bulkSkipDuplicates() {
    if (!activeSession?.id) return;
    try {
      const res = await api.request('/api/own-videos/staging/bulk-skip?session_id=' + activeSession.id + '&match_type=duplicate', { method: 'POST' });
      toast.success(`⏭ ${res.skipped} Duplikate übersprungen`);
      await loadResults(activeSession?.id, currentPage);
      await refreshStats();
    } catch (e) { toast.error(e.message); }
  }

  async function bulkSkipFolder() {
    if (!activeSession?.id || !folderFilter) return;
    try {
      const res = await api.request('/api/own-videos/staging/bulk-skip?session_id=' + activeSession.id + '&folder=' + encodeURIComponent(folderFilter), { method: 'POST' });
      toast.success(`⏭ ${res.skipped} Dateien übersprungen`);
      await loadResults(activeSession?.id, currentPage);
      await refreshStats();
    } catch (e) { toast.error(e.message); }
  }
  async function refreshStats() {
    if (!activeSession?.id) return;
    const s = await api.request('/api/own-videos/scan-session/' + activeSession.id); sessionStats = s?.stats;
  }
  async function deleteSession(sid) {
    try { await api.request('/api/own-videos/scan-session/' + sid, { method: 'DELETE' }); toast.success('Gelöscht'); await loadSessions(); }
    catch(e) { toast.error(e.message); }
  }

  function selectItem(item, idx) {
    selectedItem = item; selectedIdx = idx; previewPlaying = false;
    assignChannel = item.decision_channel || item.channel_name || '';
    selectedCandidate = item.match_candidates?.length > 0 ? item.match_candidates[0] : null;
    // YouTube-Suche vorbefüllen
    ytSearchResults = [];
    ytSearchQuery = _cleanTitle(item.title || item.filename || '');
  }

  function _cleanTitle(t) {
    // Dateiendungen, Klammern mit IDs, etc. entfernen
    return t.replace(/\.\w{3,4}$/, '').replace(/\s*[\[\(][a-zA-Z0-9_-]{11}[\]\)]\s*/g, '').replace(/_/g, ' ').trim();
  }

  async function ytSearch() {
    if (!ytSearchQuery.trim()) return;
    ytSearching = true;
    try {
      const res = await api.searchYouTube(ytSearchQuery.trim(), 8);
      ytSearchResults = res.results || [];
    } catch (e) { toast.error('YouTube-Suche fehlgeschlagen: ' + e.message); }
    ytSearching = false;
  }

  async function linkWithYoutube(ytVideo) {
    if (!selectedItem || ytLinking) return;
    ytLinking = true;
    try {
      const catId = defaultCategory ? parseInt(defaultCategory) : null;
      const res = await api.stagingLinkYoutube(selectedItem.id, ytVideo.id, catId);
      if (res.already_existed) {
        toast.success(`⚠ ${res.title} — existiert bereits, Scan-Datei als Duplikat markiert`);
      } else {
        toast.success(`✅ Verknüpft: ${res.title}`);
      }
      const stgId = selectedItem.id;
      await refreshStats(); removeAndNext(stgId);
    } catch (e) { toast.error('Verknüpfung fehlgeschlagen: ' + e.message); }
    ytLinking = false;
  }

  async function importAsOwn() {
    if (!selectedItem || importingOwn) return;
    importingOwn = true;
    try {
      const catId = defaultCategory ? parseInt(defaultCategory) : null;
      const channel = assignChannel || selectedItem.channel_name || selectedItem.folder_name || '';
      const res = await api.stagingImportOwn(selectedItem.id, catId, channel);
      toast.success(`📥 Importiert: ${res.title}`);
      const stgId = selectedItem.id;
      await refreshStats(); removeAndNext(stgId);
    } catch (e) { toast.error('Import fehlgeschlagen: ' + e.message); }
    importingOwn = false;
  }

  function durDiff(a, b) {
    if (!a || !b) return null;
    const diff = Math.abs(a - b);
    if (diff <= 3) return { cls: 'dur-ok', text: `±${diff}s ✅` };
    if (diff <= 15) return { cls: 'dur-close', text: `±${diff}s` };
    return { cls: 'dur-bad', text: `±${diff}s ⚠` };
  }

  async function loadCategories() {
    try {
      const rows = await api.request('/api/categories');
      categories = rows || [];
    } catch { categories = []; }
  }

  async function cleanupMissing() {
    try {
      const res = await api.stagingCleanupMissing();
      toast.success(`🧹 ${res.removed} fehlende Dateien entfernt (${res.checked} geprüft)`);
      await loadResults(activeSession?.id, currentPage);
      await refreshStats();
    } catch (e) { toast.error(e.message); }
  }

  let deleteFolderConfirm = $state(false);
  async function deleteFolder() {
    if (!activeSession?.id || !folderFilter) return;
    if (!deleteFolderConfirm) {
      deleteFolderConfirm = true;
      toast.warning(`⚠ Nochmal klicken um "${folderFilter}" zu löschen`);
      setTimeout(() => deleteFolderConfirm = false, 4000);
      return;
    }
    deleteFolderConfirm = false;
    try {
      const res = await api.stagingDeleteFolder(activeSession.id, folderFilter);
      toast.success(`🗑 ${res.deleted} Dateien gelöscht`);
      if (res.errors?.length) toast.warning(res.errors.length + ' Fehler');
      await loadResults(activeSession?.id, 1);
      await refreshStats();
    } catch (e) { toast.error(e.message); }
  }
  function removeAndNext(stgId) {
    // Item aus Liste entfernen (nur wenn Filter nicht "alle"/"erledigt")
    if (matchFilter !== 'all' && matchFilter !== 'decided') {
      const idx = results.findIndex(r => r.id === stgId);
      if (idx >= 0) {
        results.splice(idx, 1);
        results = [...results];
        // Nächstes offenes Item selektieren
        const nextIdx = Math.min(idx, results.length - 1);
        if (results.length > 0) selectItem(results[nextIdx], nextIdx);
        else selectedItem = null;
        return;
      }
    }
    // Fallback: einfach nächstes offenes suchen
    const u = results.filter(r => !r.decision);
    if (u.length) selectItem(u[0], results.indexOf(u[0]));
    else if (selectedIdx < results.length - 1) selectItem(results[selectedIdx + 1], selectedIdx + 1);
  }
  function handleKeydown(e) {
    if (phase !== 'review' || !selectedItem || ['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName)) return;
    const si = selectedItem;
    if (e.key === '1') { e.preventDefault(); skipItem(si.id); }
    else if (e.key === '2' && si.match_type !== 'duplicate' && si.match_type !== 'exact') {
      e.preventDefault(); importAsOwn();
    }
    else if (e.key === '3' && (si.match_type === 'duplicate' || si.match_type === 'exact')) {
      e.preventDefault(); replaceItem(si.id);
    }
    else if (e.key === 'ArrowDown' && selectedIdx < results.length - 1) { e.preventDefault(); selectItem(results[selectedIdx+1], selectedIdx+1); }
    else if (e.key === 'ArrowUp' && selectedIdx > 0) { e.preventDefault(); selectItem(results[selectedIdx-1], selectedIdx-1); }
  }

  function dotColor(t) { return { exact:'#ef4444', duplicate:'#ef4444', exact_rss:'#3b82f6', fuzzy_hi:'#f59e0b', fuzzy_lo:'#f97316', weak:'#78716c', none:'#6366f1' }[t] || '#64748b'; }
  function dotIcon(t) { return { exact:'●', duplicate:'●', exact_rss:'◆', fuzzy_hi:'▲', fuzzy_lo:'▲', weak:'○', none:'★' }[t] || '?'; }
  function statusText(t) { return { exact:'Bereits vorhanden', duplicate:'Duplikat', exact_rss:'RSS-Treffer', fuzzy_hi:'Wahrscheinlich', fuzzy_lo:'Unsicher', weak:'Schwach', none:'Neues Video' }[t] || t; }
  function decLabel(d) { return { link:'Verknüpft', link_rss:'RSS verknüpft', import_new:'Importiert', skip:'Übersprungen', replace:'Ersetzt', delete:'Gelöscht' }[d] || d; }
  function decIcon(d) { return { link:'🔗', link_rss:'🔗', import_new:'📥', skip:'⏭', replace:'🔄', delete:'🗑' }[d] || ''; }
  function confColor(c) { return c >= 0.9 ? 'var(--status-success)' : c >= 0.7 ? 'var(--status-warning)' : '#f97316'; }
  function previewUrl(fp) { return fp ? '/api/own-videos/preview/stream?path=' + encodeURIComponent(fp) : null; }
  function thumbUrl(tp) { return tp ? '/api/own-videos/preview/thumb?path=' + encodeURIComponent(tp) : null; }
  function fileExists(item) { return item._fileExists !== false; } // wird vom Backend gesetzt
  function durDiffLabel(d1, d2) {
    if (!d1 || !d2) return ''; const diff = Math.abs(d1 - d2);
    if (diff <= 2) return '✅ identisch';
    if (diff <= 5) return '✅ ±' + diff + 's';
    if (diff <= 30) return '⚠️ ±' + diff + 's';
    return '❌ ±' + diff + 's';
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="iw">

{#if phase === 'sessions'}
<div class="sessions">
  <h2>Video-Import</h2>
  <p class="muted">Verzeichnis scannen, Videos identifizieren und in die Bibliothek importieren.</p>
  <div class="scan-form">
    <label class="flabel">Scan-Verzeichnis (Container-Pfad)</label>
    <div class="scan-row">
      <input type="text" bind:value={scanPath} class="inp" />
      <label class="cbl"><input type="checkbox" bind:checked={youtubeArchive} /> YouTube-Archiv</label>
      <button class="btn primary" onclick={startScan} disabled={scanLoading}>{scanLoading ? 'Startet...' : 'Scan starten'}</button>
    </div>
  </div>
  {#if sessions.length > 0}
  <h3>Vorherige Scans</h3>
  {#each sessions as s}
  <div class="scard">
    <div class="sinfo"><div class="spath">{s.scan_path}</div><div class="smeta">{s.staged_count||0} Dateien · {s.decided_count||0} entschieden · {s.status}</div></div>
    <div class="sactions">
      {#if s.status === 'done' || s.status === 'executed'}<button class="btn sm" onclick={() => loadSessionResults(s.id)}>Fortsetzen</button>{/if}
      <button class="btn sm danger" onclick={() => deleteSession(s.id)}>Löschen</button>
    </div>
  </div>
  {/each}
  {/if}
</div>

{:else if phase === 'scanning'}
<div class="scanning">
  <div class="pcard">
    <h2>{scanPaused ? '⏸ Pausiert' : 'Scan läuft...'}</h2>
    <div class="pbar-wrap"><div class="pbar" class:paused={scanPaused} style="width:{(scanProgress*100).toFixed(1)}%"></div></div>
    <p class="pstatus">{scanStatus}</p>
    <p class="ppct">{(scanProgress*100).toFixed(1)}%</p>
    <div class="pactions">
      {#if scanPaused}<button class="btn primary" onclick={resumeScan}>Fortsetzen</button>
      {:else}<button class="btn" onclick={pauseScan}>Pause</button>{/if}
      <button class="btn danger" onclick={cancelScan}>Abbrechen</button>
    </div>
  </div>
</div>

{:else if phase === 'review'}
<!-- ═══ TOOLBAR ═══ -->
<div class="toolbar">
  <button class="btn sm" onclick={() => {phase='sessions';selectedItem=null;updateParams({session:null,page:null,folder:null,q:null});}}>← Zurück</button>
  <span class="tpath">{activeSession?.scan_path}</span>
  <div class="pills">
    {#each filterPills as p}
    <button class="pill" class:active={matchFilter===p.key} onclick={() => {matchFilter=p.key;loadResults(activeSession?.id,1);}}>{p.label} ({p.count ?? 0})</button>
    {/each}
  </div>
  <button class="btn sm" class:active={showBulkPanel} onclick={() => showBulkPanel=!showBulkPanel}>Bulk</button>
</div>

{#if showBulkPanel}
<div class="bulk-bar">
  <span class="blabel">Aktionen:</span>
  <button class="btn xs" onclick={bulkSkipDuplicates}>Duplikate überspringen</button>
  <button class="btn xs" onclick={cleanupMissing}>🧹 Fehlende entfernen</button>
  {#if folderFilter}<span class="bsep">│</span>
  <button class="btn xs" onclick={bulkSkipFolder}>Ordner überspringen</button>
  <button class="btn xs warn" class:danger={deleteFolderConfirm} onclick={deleteFolder}>{deleteFolderConfirm ? '⚠ Bestätigen?' : '🗑 Ordner löschen'}</button>{/if}
</div>
{/if}

<!-- ═══ 2-PANEL ═══ -->
<div class="panels">

  <!-- LEFT: Dateiliste -->
  <div class="pleft">
    <div class="lhdr">
      {#if resultsMeta.folders?.length > 1}
      <select class="inp sm" value={folderFilter} onchange={(e) => {folderFilter=e.target.value;loadResults(activeSession?.id,1);}}>
        <option value="">Alle Ordner ({resultsMeta.folders.length})</option>
        {#each resultsMeta.folders as f}<option value={f.folder_name}>{f.folder_name} ({f.decided}/{f.count})</option>{/each}
      </select>
      {/if}
      <input type="text" bind:value={searchQuery} placeholder="Suchen..." class="inp sm" onkeydown={(e) => e.key==='Enter' && loadResults(activeSession?.id,1)} />
    </div>

    <div class="flist">
      {#each results as item, idx}
      <button class="frow" class:sel={selectedItem?.id===item.id} class:decided={!!item.decision} class:missing={item._fileExists===false} onclick={() => selectItem(item,idx)}>
        <span class="dot" style="background:{dotColor(item.match_type)}" title={statusText(item.match_type)}>{dotIcon(item.match_type)}</span>
        <div class="fmain">
          <div class="ftitle" class:strike={item.decision==='delete'}>{item.title || item.filename}</div>
          <div class="fmeta">
            <span>{formatDuration(item.duration)}</span>
            <span>{formatSize(item.file_size)}</span>
            {#if item._fileExists===false}<span class="fmiss">⚠ fehlt</span>{/if}
            {#if item.folder_name && item.folder_name !== '(Root)'}<span class="ffolder">{item.folder_name}</span>{/if}
            {#if item.match_confidence > 0}<span class="fconf" style="color:{confColor(item.match_confidence)}">{Math.round(item.match_confidence*100)}%</span>{/if}
          </div>
        </div>
        {#if item.decision}<span class="dbadge" class:db-link={item.decision.includes('link')} class:db-import={item.decision==='import_new'} class:db-skip={item.decision==='skip'} class:db-del={item.decision==='delete'} class:db-repl={item.decision==='replace'}>{decIcon(item.decision)} {decLabel(item.decision)}</span>{/if}
      </button>
      {/each}
      {#if results.length === 0}<div class="empty">Keine Dateien</div>{/if}
    </div>

    {#if resultsMeta.total_pages > 1}
    <div class="pagi">
      <button class="btn xs" disabled={currentPage<=1} onclick={() => loadResults(activeSession?.id,currentPage-1)}>←</button>
      <span>{currentPage}/{resultsMeta.total_pages}</span>
      <button class="btn xs" disabled={currentPage>=resultsMeta.total_pages} onclick={() => loadResults(activeSession?.id,currentPage+1)}>→</button>
    </div>
    {/if}
    <div class="kbar"><kbd>1</kbd> Überspringen <kbd>2</kbd> Als Eigenes <kbd>3</kbd> Ersetzen <kbd>↑↓</kbd> Nav</div>
  </div>

  <!-- RIGHT: Detail -->
  <div class="pright">
    {#if selectedItem}

    <!-- Datei-Info -->
    <div class="sec">
      <div class="slabel">Eigene Datei</div>
      <div class="fdetail">
        <div class="fprev">
          {#if !selectedItem.file_path || !fileExists(selectedItem)}
          <div class="pph pmissing"><span class="pp">⚠</span><span class="pd">Datei fehlt</span></div>
          {:else if previewPlaying}<video src={previewUrl(selectedItem.file_path)} controls autoplay class="pvid"></video>
          {:else}
          <button class="pph" onclick={() => previewPlaying=true}
            style={selectedItem.thumbnail_path ? `background-image:url(${thumbUrl(selectedItem.thumbnail_path)});background-size:cover;background-position:center` : ''}>
            <span class="pp">▶</span><span class="pd">{formatDuration(selectedItem.duration)}</span>
          </button>
          {/if}
        </div>
        <div class="fdata">
          <div class="fdtitle">{selectedItem.title || selectedItem.filename}</div>
          <div class="mgrid">
            <span class="ml">Datei</span><span class="mv">{selectedItem.filename}</span>
            <span class="ml">Ordner</span><span class="mv">{selectedItem.folder_name}</span>
            <span class="ml">Dauer</span><span class="mv">{formatDuration(selectedItem.duration)}</span>
            <span class="ml">Größe</span><span class="mv">{formatSize(selectedItem.file_size)}</span>
            {#if selectedItem.resolution}<span class="ml">Auflösung</span><span class="mv">{selectedItem.resolution}</span>{/if}
            {#if selectedItem.youtube_id}<span class="ml">YouTube-ID</span><span class="mv ytid">{selectedItem.youtube_id}</span>{/if}
          </div>
          <div class="badges">
            {#if selectedItem.info_json_found}<span class="badge bi">info.json</span>{/if}
            {#if selectedItem.nfo_found}<span class="badge bi">NFO</span>{/if}
            {#if selectedItem.thumbnail_path}<span class="badge bg">Thumbnail</span>{/if}
            {#if selectedItem.subtitles_found?.length}<span class="badge bg">Untertitel</span>{/if}
            {#if selectedItem.description_text}<span class="badge bg">Beschreibung</span>{/if}
          </div>
        </div>
      </div>
    </div>

    <!-- NEUER WORKFLOW: YouTube-Suche + Sofort-Aktion -->

    {#if selectedItem.decision}
    <div class="done-banner">
      {#if selectedItem.decision === 'skip'}⏭ Übersprungen
      {:else if selectedItem.decision === 'replace'}🔄 Datei ersetzt
      {:else if selectedItem.decision === 'link' || selectedItem.decision === 'link_rss'}🔗 Verknüpft
      {:else if selectedItem.decision === 'import_new'}📥 Importiert
      {:else if selectedItem.decision === 'delete'}🗑 Gelöscht
      {:else}{selectedItem.decision}{/if}
    </div>

    {:else if selectedItem.match_type === 'duplicate' || selectedItem.match_type === 'exact'}
    <!-- Duplikat: existiert schon in Bibliothek -->
    <div class="dup-banner"><i class="fa-solid fa-copy"></i> Dieses Video existiert bereits in deiner Bibliothek</div>
    <div class="acts">
      <div class="abtns">
        <button class="btn abtn" onclick={() => skipItem(selectedItem.id)}>⏭ Überspringen</button>
        <button class="btn abtn warn" onclick={() => replaceItem(selectedItem.id)}>🔄 Datei ersetzen</button>
      </div>
    </div>

    {:else}
    <!-- YouTube-Suche -->
    <div class="sec ytsec">
      <div class="slabel"><i class="fa-brands fa-youtube"></i> Bei YouTube suchen & verknüpfen</div>
      <div class="ytsbar">
        <input class="inp" type="text" bind:value={ytSearchQuery}
          placeholder="Titel eingeben…"
          onkeydown={(e) => e.key === 'Enter' && ytSearch()} />
        <button class="btn primary" onclick={ytSearch} disabled={ytSearching || !ytSearchQuery.trim()}>
          {#if ytSearching}<i class="fa-solid fa-spinner fa-spin"></i>{:else}<i class="fa-solid fa-magnifying-glass"></i>{/if}
          Suchen
        </button>
      </div>

      {#if ytSearchResults.length > 0}
      <div class="ytresults">
        {#each ytSearchResults as yt}
        <div class="ytcard">
          <img src={yt.thumbnail_url} alt="" class="ytthumb" loading="lazy" />
          <div class="ytinfo">
            <div class="yttitle">{yt.title}</div>
            <div class="ytmeta">{yt.channel_name}</div>
            <div class="ytcmp">
              <span class="cmprow">
                <span class="cmpl">Deine Datei:</span>
                <span class="cmpv">{formatDuration(selectedItem.duration)}</span>
              </span>
              <span class="cmprow">
                <span class="cmpl">YouTube:</span>
                <span class="cmpv">{formatDuration(yt.duration)}</span>
              </span>
              {#if durDiff(selectedItem.duration, yt.duration)}
              <span class="cmpdiff {durDiff(selectedItem.duration, yt.duration).cls}">{durDiff(selectedItem.duration, yt.duration).text}</span>
              {/if}
            </div>
          </div>
          <button class="btn primary ytlink" onclick={() => linkWithYoutube(yt)} disabled={ytLinking || yt.already_downloaded}>
            {#if yt.already_downloaded}<i class="fa-solid fa-check"></i> Vorhanden
            {:else if ytLinking}<i class="fa-solid fa-spinner fa-spin"></i>
            {:else}<i class="fa-solid fa-link"></i> Verknüpfen{/if}
          </button>
        </div>
        {/each}
      </div>
      {:else if ytSearching}
      <div class="ytloading"><i class="fa-solid fa-spinner fa-spin"></i> Suche…</div>
      {/if}
    </div>

    <!-- Trennlinie -->
    <div class="sep-or"><span>oder</span></div>

    <!-- Als eigenes Video importieren -->
    <div class="sec ownsec">
      <div class="slabel"><i class="fa-solid fa-file-import"></i> Ohne YouTube importieren</div>
      <div class="own-opts">
        <div class="ownrow">
          <label class="flsm">Kanal:</label>
          <select bind:value={assignChannel} class="inp sm">
            <option value="">— Aus Ordner: {selectedItem.folder_name || '–'} —</option>
            {#each channels as ch}<option value={ch.name}>{ch.name}</option>{/each}
          </select>
        </div>
        {#if categories.length > 0}
        <div class="ownrow">
          <label class="flsm">Kategorie:</label>
          <select bind:value={defaultCategory} class="inp sm">
            <option value="">— Keine —</option>
            {#each categories as cat}<option value={cat.id}>{cat.name}</option>{/each}
          </select>
        </div>
        {/if}
      </div>
      <div class="abtns">
        <button class="btn abtn primary" onclick={importAsOwn} disabled={importingOwn}>
          {#if importingOwn}<i class="fa-solid fa-spinner fa-spin"></i>{:else}📥{/if} Als Eigenes importieren
        </button>
        <button class="btn abtn mact" onclick={() => skipItem(selectedItem.id)}>⏭ Überspringen</button>
      </div>
    </div>
    {/if}

    {:else}
    <div class="nosel"><div class="nsi">📁</div><div>Datei links auswählen</div></div>
    {/if}
  </div>
</div>

{/if}

</div>

<style>
  .iw{display:flex;flex-direction:column;height:100%;background:var(--bg-primary);color:var(--text-primary);font-family:inherit}
  .muted{color:var(--text-muted);font-size:.85rem}

  /* Sessions */
  .sessions{max-width:700px;margin:0 auto;padding:2rem 1.5rem}
  .sessions h2{margin:0 0 .25rem} .sessions h3{font-size:.9rem;color:var(--text-secondary);margin:1.5rem 0 .5rem}
  .scan-form{margin:1.5rem 0;padding:1rem;border-radius:8px;background:var(--bg-secondary);border:1px solid var(--border-primary)}
  .scan-row{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap}
  .flabel{display:block;font-size:.75rem;color:var(--text-secondary);margin-bottom:.4rem;font-weight:600}
  .flsm{font-size:.72rem;color:var(--text-muted);display:block;margin-bottom:.25rem}
  .inp{padding:.4rem .6rem;border-radius:5px;border:1px solid var(--border-primary);background:var(--bg-primary);color:var(--text-primary);font-size:.85rem;flex:1;min-width:120px}
  .inp:focus{outline:none;border-color:var(--accent-primary)} .inp.sm{font-size:.8rem;padding:.3rem .5rem}
  .cbl{display:flex;align-items:center;gap:.3rem;font-size:.8rem;color:var(--text-secondary);white-space:nowrap}
  .btn{padding:.4rem .8rem;border-radius:5px;border:1px solid var(--border-primary);background:var(--bg-secondary);color:var(--text-primary);cursor:pointer;font-size:.8rem;font-weight:600;white-space:nowrap}
  .btn:hover{background:var(--bg-tertiary)} .btn:disabled{opacity:.4;cursor:default}
  .btn.primary{background:var(--accent-primary);color:#fff;border-color:var(--accent-primary)} .btn.primary:hover{filter:brightness(1.1)}
  .btn.danger{color:var(--status-error);border-color:var(--status-error);background:transparent}
  .btn.warn{color:var(--status-warning);border-color:var(--status-warning);background:transparent}
  .btn.danger{color:#fff;background:var(--status-error);border-color:var(--status-error);animation:pulse .5s ease-in-out infinite alternate}
  .btn.sm{font-size:.75rem;padding:.3rem .6rem} .btn.xs{font-size:.7rem;padding:.2rem .5rem}
  .btn.active{background:var(--accent-primary);color:#fff;border-color:var(--accent-primary)}

  .scard{display:flex;align-items:center;gap:1rem;padding:.6rem .8rem;border-radius:6px;background:var(--bg-secondary);border:1px solid var(--border-primary);margin-bottom:.4rem}
  .sinfo{flex:1} .spath{font-weight:600;font-size:.85rem} .smeta{font-size:.75rem;color:var(--text-muted)} .sactions{display:flex;gap:.3rem}

  /* Scanning */
  .scanning{display:flex;align-items:center;justify-content:center;flex:1}
  .pcard{text-align:center;padding:2rem;background:var(--bg-secondary);border-radius:12px;border:1px solid var(--border-primary);min-width:400px}
  .pbar-wrap{width:100%;height:8px;background:var(--bg-tertiary);border-radius:4px;overflow:hidden;margin:1rem 0}
  .pbar{height:100%;background:var(--accent-primary);border-radius:4px;transition:width .3s}
  .pbar.paused{background:var(--status-warning);animation:pulse 1.5s ease-in-out infinite}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
  .pstatus{color:var(--text-secondary);font-size:.85rem;margin:.5rem 0 .25rem} .ppct{font-size:1.5rem;font-weight:700;color:var(--accent-primary)}
  .pactions{display:flex;gap:.5rem;margin-top:1rem;justify-content:center}

  /* Toolbar */
  .toolbar{display:flex;align-items:center;gap:.5rem;padding:.5rem .8rem;border-bottom:1px solid var(--border-primary);background:var(--bg-secondary);flex-wrap:wrap}
  .tpath{font-size:.72rem;color:var(--text-muted);padding:.15rem .5rem;background:var(--bg-tertiary);border-radius:4px}
  .pills{display:flex;gap:.2rem;flex:1;flex-wrap:wrap}
  .pill{padding:.2rem .6rem;border-radius:10px;border:1px solid var(--border-primary);background:transparent;color:var(--text-secondary);cursor:pointer;font-size:.72rem}
  .pill.active{background:var(--accent-primary);color:#fff;border-color:var(--accent-primary)} .pill:hover:not(.active){background:var(--bg-tertiary)}

  .bulk-bar{display:flex;align-items:center;gap:.4rem;padding:.4rem .8rem;background:var(--bg-tertiary);border-bottom:1px solid var(--border-primary);flex-wrap:wrap}
  .blabel{font-size:.72rem;font-weight:600;color:var(--text-secondary)} .bsep{color:var(--border-primary);font-size:.8rem}

  /* 2-Panel */
  .panels{display:flex;flex:1;overflow:hidden}
  .pleft{width:45%;min-width:320px;display:flex;flex-direction:column;border-right:1px solid var(--border-primary)}
  .pright{flex:1;overflow-y:auto;background:var(--bg-secondary)}

  .lhdr{display:flex;gap:.4rem;padding:.4rem .5rem;border-bottom:1px solid var(--border-primary);background:var(--bg-secondary)}
  .lhdr select{width:190px;flex:none} .lhdr input{flex:1;min-width:80px}

  .flist{flex:1;overflow-y:auto}
  .frow{display:flex;align-items:center;gap:.5rem;width:100%;padding:.45rem .6rem;border:none;background:transparent;cursor:pointer;text-align:left;border-left:3px solid transparent;border-bottom:1px solid color-mix(in srgb, var(--border-primary) 40%, transparent);color:var(--text-primary)}
  .frow:hover{background:var(--bg-tertiary)} .frow.sel{background:rgba(107,163,232,.1);border-left-color:var(--accent-primary)}
  .frow.decided:not(.sel){opacity:.55}

  .dot{width:20px;height:20px;border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:.6rem;color:#fff;flex-shrink:0;font-weight:700}
  .fmain{flex:1;min-width:0}
  .ftitle{font-size:.8rem;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;line-height:1.3}
  .ftitle.strike{text-decoration:line-through;color:var(--text-muted)}
  .fmeta{display:flex;gap:.5rem;font-size:.68rem;color:var(--text-muted);margin-top:.1rem;flex-wrap:wrap}
  .ffolder{max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .fconf{font-weight:700}

  .dbadge{font-size:.62rem;padding:.12rem .35rem;border-radius:4px;white-space:nowrap;flex-shrink:0;font-weight:600}
  .db-link{background:rgba(59,130,246,.15);color:#3b82f6} .db-import{background:rgba(34,197,94,.15);color:var(--status-success)}
  .db-skip{background:rgba(120,113,108,.15);color:#78716c} .db-del{background:rgba(239,68,68,.1);color:var(--status-error)}
  .db-repl{background:rgba(245,158,11,.15);color:#f59e0b}

  .empty{text-align:center;padding:2rem;color:var(--text-muted)}
  .pagi{display:flex;align-items:center;justify-content:center;gap:.5rem;padding:.35rem;border-top:1px solid var(--border-primary);font-size:.72rem;color:var(--text-muted)}
  .kbar{display:flex;gap:.6rem;justify-content:center;padding:.35rem;border-top:1px solid var(--border-primary);background:var(--bg-secondary);font-size:.68rem;color:var(--text-muted)}
  .kbar kbd{padding:.08rem .3rem;border-radius:3px;background:var(--bg-tertiary);border:1px solid var(--border-primary);font-family:inherit;font-size:.63rem;font-weight:700}

  /* Right: Detail */
  .sec{padding:.8rem;border-bottom:1px solid var(--border-primary)}
  .slabel{font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--text-muted);margin-bottom:.5rem;display:flex;align-items:center;gap:.5rem}
  .src{font-size:.62rem;padding:.08rem .3rem;border-radius:3px;text-transform:none;letter-spacing:0;font-weight:600}
  .src.rss{background:rgba(59,130,246,.15);color:#3b82f6} .src.lib{background:rgba(34,197,94,.15);color:var(--status-success)}

  .fdetail{display:flex;gap:.8rem}
  .fprev{flex-shrink:0;width:200px}
  .pvid{width:100%;border-radius:6px;background:#000}
  .pph{width:100%;aspect-ratio:16/9;border-radius:6px;background:var(--bg-tertiary);border:1px solid var(--border-primary);cursor:pointer;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:.2rem;color:var(--text-muted)}
  .pph:hover{border-color:var(--accent-primary)} .pp{font-size:1.5rem;opacity:.5} .pd{font-size:.75rem}

  .fdata{flex:1;min-width:0}
  .fdtitle{font-size:.88rem;font-weight:700;margin-bottom:.4rem;line-height:1.3}
  .mgrid{display:grid;grid-template-columns:auto 1fr;gap:.12rem .6rem;font-size:.73rem}
  .ml{color:var(--text-muted)} .mv{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .ytid{color:var(--accent-primary);font-weight:600;font-family:monospace;font-size:.72rem}
  .badges{display:flex;gap:.25rem;margin-top:.4rem;flex-wrap:wrap}
  .badge{font-size:.62rem;padding:.08rem .3rem;border-radius:3px;font-weight:600}
  .bi{background:rgba(99,102,241,.15);color:#6366f1} .bg{background:rgba(34,197,94,.1);color:var(--status-success)}

  .mstatus{display:flex;align-items:center;gap:.5rem;padding:.5rem .8rem;background:color-mix(in srgb, var(--mc) 8%, transparent);border-bottom:1px solid color-mix(in srgb, var(--mc) 20%, transparent)}
  .msi{font-size:.8rem;color:var(--mc)} .msl{font-size:.82rem;font-weight:700;color:var(--mc);flex:1} .msc{font-size:1rem;font-weight:800;color:var(--mc)}

  .msec{background:color-mix(in srgb, var(--accent-primary) 3%, transparent)}
  .mtitle{font-size:.86rem;font-weight:700;margin-bottom:.1rem} .mchan{font-size:.76rem;color:var(--text-muted);margin-bottom:.4rem}

  .durcmp{background:var(--bg-tertiary);border-radius:6px;padding:.5rem;margin:.4rem 0}
  .durrow{display:flex;justify-content:space-between;font-size:.76rem;padding:.08rem 0}
  .durl{color:var(--text-muted)} .durv{font-weight:600;font-family:monospace}
  .durres{font-size:.73rem;margin-top:.25rem;padding-top:.25rem;border-top:1px solid var(--border-primary)}
  .mlink{display:inline-block;margin-top:.4rem;font-size:.76rem;color:var(--accent-primary);text-decoration:none} .mlink:hover{text-decoration:underline}

  .clist{display:flex;flex-direction:column;gap:.2rem}
  .crow{display:flex;align-items:center;gap:.4rem;padding:.4rem .5rem;border-radius:6px;border:1px solid var(--border-primary);background:var(--bg-primary);cursor:pointer;text-align:left;color:var(--text-primary)}
  .crow:hover{background:var(--bg-tertiary)} .crow.cact{border-color:var(--accent-primary);background:rgba(107,163,232,.08)}
  .cradio{font-size:.85rem;color:var(--accent-primary);width:16px;text-align:center}
  .cconf{font-size:.78rem;font-weight:800;width:34px;text-align:right}
  .cinfo{flex:1;min-width:0} .ctitle{font-size:.76rem;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .cmeta{font-size:.68rem;color:var(--text-muted)}

  .acts{padding:.8rem;position:sticky;bottom:0;background:var(--bg-secondary);border-top:1px solid var(--border-primary)}
  .cdec{display:flex;align-items:center;justify-content:space-between;padding:.4rem .6rem;margin-bottom:.5rem;border-radius:6px;background:var(--bg-tertiary);font-size:.76rem}
  .chsel{margin-bottom:.5rem}
  .abtns{display:flex;gap:.4rem;flex-wrap:wrap}
  .abtn{flex:1;min-width:110px;padding:.5rem .6rem;font-size:.76rem;text-align:center;border-radius:6px}
  .abtn.primary{background:var(--accent-primary);color:#fff;border-color:var(--accent-primary)}
  .abtn.warn{color:var(--status-warning);border-color:var(--status-warning)}
  .mact{color:var(--text-muted);border-color:var(--border-primary)}
  .nosel{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:var(--text-muted);gap:.5rem}
  .nsi{font-size:2rem;opacity:.3}

  /* YouTube-Suche */
  .ytsec{padding-bottom:0}
  .ytsbar{display:flex;gap:.4rem;margin:.5rem 0}
  .ytsbar .inp{flex:1;font-size:.82rem}
  .ytresults{display:flex;flex-direction:column;gap:.5rem;max-height:420px;overflow-y:auto;padding:.4rem 0}
  .ytcard{display:flex;gap:.6rem;padding:.5rem;border-radius:8px;background:var(--bg-tertiary);border:1px solid var(--border-primary);align-items:flex-start;transition:border-color .15s}
  .ytcard:hover{border-color:var(--accent-primary)}
  .ytthumb{width:100px;height:56px;object-fit:cover;border-radius:4px;flex-shrink:0}
  .ytinfo{flex:1;min-width:0}
  .yttitle{font-size:.78rem;font-weight:600;line-height:1.2;margin-bottom:.15rem;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  .ytmeta{font-size:.7rem;color:var(--text-muted);margin-bottom:.3rem}
  .ytcmp{display:flex;flex-wrap:wrap;gap:.1rem .8rem;font-size:.7rem}
  .cmprow{display:flex;gap:.3rem} .cmpl{color:var(--text-muted)} .cmpv{font-weight:600}
  .cmpdiff{font-weight:700;padding:.05rem .3rem;border-radius:4px;font-size:.68rem}
  .dur-ok{color:var(--status-success);background:color-mix(in srgb, var(--status-success) 10%, transparent)}
  .dur-close{color:var(--status-warning);background:color-mix(in srgb, var(--status-warning) 10%, transparent)}
  .dur-bad{color:var(--status-error);background:color-mix(in srgb, var(--status-error) 10%, transparent)}
  .ytlink{flex-shrink:0;font-size:.72rem;padding:.4rem .6rem;align-self:center}
  .ytloading{text-align:center;padding:1.5rem;color:var(--text-muted);font-size:.82rem}

  /* Trennlinie */
  .sep-or{display:flex;align-items:center;gap:.8rem;padding:.6rem .8rem;color:var(--text-muted);font-size:.76rem}
  .sep-or::before,.sep-or::after{content:'';flex:1;border-top:1px solid var(--border-primary)}

  /* Eigenes Video importieren */
  .ownsec{padding-bottom:.5rem}
  .own-opts{display:flex;flex-direction:column;gap:.4rem;margin:.5rem 0}
  .ownrow{display:flex;align-items:center;gap:.5rem}
  .ownrow label{font-size:.76rem;color:var(--text-muted);width:65px;flex-shrink:0}
  .ownrow .inp{flex:1}

  /* Erledigt / Duplikat Banner */
  .done-banner{display:flex;align-items:center;gap:.5rem;padding:.8rem;margin:.5rem;border-radius:8px;background:color-mix(in srgb, var(--status-success) 10%, transparent);color:var(--status-success);font-size:.82rem;font-weight:600}
  .dup-banner{display:flex;align-items:center;gap:.5rem;padding:.8rem;margin:.5rem;border-radius:8px;background:color-mix(in srgb, var(--status-warning) 10%, transparent);color:var(--status-warning);font-size:.82rem;font-weight:600}
  .frow.missing{opacity:.45} .frow.missing .ftitle{text-decoration:line-through}
  .fmiss{color:var(--status-error);font-weight:700;font-size:.68rem}
  .pmissing{background:var(--bg-tertiary);cursor:default;justify-content:center}
  .pmissing .pp{font-size:1.2rem;opacity:.6} .pmissing .pd{font-size:.72rem;color:var(--status-error)}
</style>

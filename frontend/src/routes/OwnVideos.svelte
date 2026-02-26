<!--
  TubeVault -  Import-Wizard v1.8.76
  3-Panel: Bibliothek | Aktion | Dateien
  Async Scan-Job, Staging-DB, Duration-Matching
  © HalloWelt42 -  Private Nutzung
-->
<script>
  import { api } from '../lib/api/client.js';
  import { toast } from '../lib/stores/notifications.js';
  import { formatSize, formatDuration } from '../lib/utils/format.js';
  import { onMount } from 'svelte';

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
  let matchFilter = $state('all');
  let folderFilter = $state('');
  let searchQuery = $state('');
  let currentPage = $state(1);
  let selectedItem = $state(null);
  let selectedIdx = $state(-1);
  let assignChannel = $state('');
  let channels = $state([]);
  let selectedChannel = $state(null);
  let channelVideos = $state([]);
  let channelSearch = $state('');
  let previewPlaying = $state(false);

  onMount(() => {
    loadSessions();
    loadChannels();
    return () => { if (pollTimer) clearInterval(pollTimer); };
  });

  async function loadSessions() {
    try { const d = await api.request('/api/own-videos/scan-sessions'); sessions = d || []; }
    catch(e) { console.error(e); }
  }

  async function loadChannels() {
    try {
      const d = await api.request('/api/subscriptions?per_page=500');
      channels = (d?.subscriptions || []).map(s => ({
        id: s.channel_id, name: s.channel_name, videoCount: s.video_count || 0
      }));
    } catch(e) { console.error(e); }
  }

  async function startScan() {
    if (scanLoading) return;
    scanLoading = true;
    try {
      const d = await api.request('/api/own-videos/scan-job', {
        method: 'POST', body: { path: scanPath, youtube_archive: youtubeArchive }
      });
      scanJobId = d.job_id;
      activeSession = { id: d.session_id, status: 'running', total_files: d.total_files };
      phase = 'scanning'; scanProgress = 0;
      scanStatus = '0/' + d.total_files + ' Dateien...';
      startPolling();
      toast.success('Scan gestartet: ' + d.total_files + ' Dateien');
    } catch(e) { toast.error('Scan-Fehler: ' + (e.message || e)); scanLoading = false; }
  }

  function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollJob, 2000);
  }

  async function pollJob() {
    if (!scanJobId) return;
    try {
      const j = await api.request('/api/jobs/' + scanJobId);
      if (!j) return;
      scanProgress = j.progress || 0;
      scanStatus = j.description || '';
      if (j.status === 'done' || j.status === 'error' || j.status === 'cancelled') {
        clearInterval(pollTimer); pollTimer = null; scanLoading = false;
        if (j.status === 'done') {
          toast.success('Scan fertig!');
          if (j.metadata?.session_id) await loadSessionResults(j.metadata.session_id);
        } else {
          toast.error(j.status === 'error' ? 'Fehler: ' + j.error : 'Abgebrochen');
          phase = 'sessions';
        }
      }
    } catch(e) { console.error(e); }
  }

  async function pauseScan() {
    if (!scanJobId) return;
    try {
      await api.request('/api/jobs/' + scanJobId + '/pause', { method: 'POST' });
      scanPaused = true;
    } catch(e) { toast.error('Pause: ' + e.message); }
  }

  async function resumeScan() {
    if (!scanJobId) return;
    try {
      await api.request('/api/jobs/' + scanJobId + '/resume', { method: 'POST' });
      scanPaused = false;
    } catch(e) { toast.error('Resume: ' + e.message); }
  }

  async function cancelScan() {
    if (!scanJobId) return;
    try {
      await api.request('/api/jobs/' + scanJobId + '/cancel', { method: 'POST' });
      clearInterval(pollTimer); pollTimer = null;
      phase = 'sessions'; scanJobId = null; scanPaused = false; scanLoading = false;
      toast.success('Scan abgebrochen');
      await loadSessions();
    } catch(e) { toast.error('Cancel: ' + e.message); }
  }

  async function loadSessionResults(sid) {
    try {
      const s = await api.request('/api/own-videos/scan-session/' + sid);
      activeSession = s; sessionStats = s?.stats;
      await loadResults(sid); phase = 'review';
    } catch(e) { toast.error('Session: ' + e.message); phase = 'sessions'; }
  }

  async function loadResults(sid, page = 1) {
    const id = sid || activeSession?.id;
    if (!id) return;
    try {
      const p = new URLSearchParams({ page, per_page: 50 });
      if (matchFilter && matchFilter !== 'all') p.set('match_filter', matchFilter);
      if (folderFilter) p.set('folder', folderFilter);
      if (searchQuery) p.set('search', searchQuery);
      const d = await api.request('/api/own-videos/scan-results/' + id + '?' + p);
      results = d.results || []; resultsMeta = d; currentPage = page;
      if (results.length > 0 && !selectedItem) selectItem(results[0], 0);
    } catch(e) { toast.error('Laden: ' + e.message); }
  }

  async function setDecision(stgId, decision, channel = null) {
    try {
      await api.request('/api/own-videos/scan-decision/' + stgId, {
        method: 'POST', body: { decision, channel }
      });
      const i = results.findIndex(r => r.id === stgId);
      if (i >= 0) { results[i] = { ...results[i], decision, decision_channel: channel }; results = [...results]; }
      if (activeSession?.id) {
        const s = await api.request('/api/own-videos/scan-session/' + activeSession.id);
        sessionStats = s?.stats;
      }
      selectNext();
    } catch(e) { toast.error('Fehler: ' + e.message); }
  }

  async function setBulkDecision(decision, matchType = null, folder = null) {
    try {
      const r = await api.request('/api/own-videos/scan-bulk-decision/' + activeSession.id, {
        method: 'POST', body: { decision, match_type: matchType, folder_name: folder }
      });
      toast.success((r.affected || 0) + ' Dateien: ' + decision);
      await loadResults(activeSession.id, currentPage);
      const s = await api.request('/api/own-videos/scan-session/' + activeSession.id);
      sessionStats = s?.stats;
    } catch(e) { toast.error('Bulk: ' + e.message); }
  }

  async function executeDecisions() {
    if (!activeSession?.id) return;
    phase = 'executing';
    try {
      const r = await api.request('/api/own-videos/scan-execute/' + activeSession.id, { method: 'POST' });
      toast.success(r.imported + ' importiert, ' + r.linked + ' verknüpft, ' + (r.replaced||0) + ' ersetzt, ' + r.deleted + ' gelöscht, ' + r.skipped + ' übersprungen');
      if (r.errors?.length) toast.warning(r.errors.length + ' Fehler');
      phase = 'sessions'; await loadSessions();
    } catch(e) { toast.error('Execute: ' + e.message); phase = 'review'; }
  }

  async function deleteSession(sid) {
    try {
      await api.request('/api/own-videos/scan-session/' + sid, { method: 'DELETE' });
      toast.success('Geloescht'); await loadSessions();
    } catch(e) { toast.error(e.message); }
  }

  async function loadChannelVideos(chId) {
    try { const d = await api.request('/api/videos?channel_id=' + encodeURIComponent(chId) + '&per_page=50'); channelVideos = d?.videos || []; }
    catch(e) { channelVideos = []; }
  }

  function selectItem(item, idx) {
    selectedItem = item; selectedIdx = idx; previewPlaying = false;
    assignChannel = item.decision_channel || item.channel_name || '';
  }

  function selectNext() {
    const u = results.filter(r => !r.decision && r.match_type !== 'duplicate');
    if (u.length) selectItem(u[0], results.indexOf(u[0]));
    else { selectedItem = null; selectedIdx = -1; }
  }

  function handleKeydown(e) {
    if (phase !== 'review' || !selectedItem || e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
    const si = selectedItem;
    if (e.key === 'j') { e.preventDefault(); setDecision(si.id, si.match_type === 'exact_rss' ? 'link_rss' : si.match_id ? 'link' : 'import_new', assignChannel); }
    else if (e.key === 'k') { e.preventDefault(); setDecision(si.id, 'import_new', assignChannel); }
    else if (e.key === 'd') { e.preventDefault(); setDecision(si.id, 'delete'); }
    else if (e.key === 's') { e.preventDefault(); setDecision(si.id, 'skip'); }
    else if (e.key === 'ArrowDown' && selectedIdx < results.length - 1) { e.preventDefault(); selectItem(results[selectedIdx+1], selectedIdx+1); }
    else if (e.key === 'ArrowUp' && selectedIdx > 0) { e.preventDefault(); selectItem(results[selectedIdx-1], selectedIdx-1); }
  }

  function matchColor(t) {
    const m = {exact:'var(--status-error)',duplicate:'var(--status-error)',exact_rss:'var(--accent-primary)',fuzzy_hi:'var(--status-warning)',fuzzy_lo:'#f97316',weak:'#78716c',none:'var(--text-muted)'};
    return m[t] || 'var(--text-muted)';
  }
  function matchLabel(t) {
    const m = {exact:'Duplikat',duplicate:'Duplikat',exact_rss:'RSS-Match',fuzzy_hi:'Wahrscheinlich',fuzzy_lo:'Unsicher',weak:'Schwach',none:'Neu'};
    return m[t] || t;
  }
  function matchIcon(t) {
    const m = {exact:'!',duplicate:'!',exact_rss:'D',fuzzy_hi:'?',fuzzy_lo:'~',weak:'~',none:'+'};
    return m[t] || '?';
  }
  function decLabel(d) {
    const m = {link:'Verknuepft',link_rss:'RSS-Link',import_new:'Importiert',skip:'Skip',replace:'Ersetzt',delete:'Geloescht'};
    return m[d] || d;
  }
  function previewUrl(fp) { return fp ? '/api/own-videos/preview/stream?path=' + encodeURIComponent(fp) : null; }

  let decidedCount = $derived(sessionStats?.decided || 0);
  let totalCount = $derived(sessionStats?.total || 0);
  let filteredChannels = $derived(channels.filter(c => !channelSearch || c.name.toLowerCase().includes(channelSearch.toLowerCase())));
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="iw">

<!-- ═══ SESSIONS ═══ -->
{#if phase === 'sessions'}
<div class="sessions">
  <h2>Video-Import</h2>
  <p class="muted">Verzeichnis scannen, Videos identifizieren und importieren</p>
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
    <div class="sinfo">
      <div class="spath">{s.scan_path}</div>
      <div class="smeta">{s.staged_count||0} Dateien, {s.decided_count||0} entschieden — {s.status}</div>
    </div>
    <div class="sactions">
      {#if s.status === 'done'}<button class="btn sm" onclick={() => loadSessionResults(s.id)}>Fortsetzen</button>{/if}
      <button class="btn sm danger" onclick={() => deleteSession(s.id)}>X</button>
    </div>
  </div>
  {/each}
  {/if}
</div>

<!-- ═══ SCANNING ═══ -->
{:else if phase === 'scanning'}
<div class="scanning">
  <div class="pcard">
    <h2>{scanPaused ? '⏸ Pausiert' : 'Scan läuft...'}</h2>
    <div class="pbar-wrap"><div class="pbar" class:paused={scanPaused} style="width:{(scanProgress*100).toFixed(1)}%"></div></div>
    <p class="pstatus">{scanStatus}</p>
    <p class="ppct">{(scanProgress*100).toFixed(1)}%</p>
    <div class="pactions">
      {#if scanPaused}
        <button class="btn primary" onclick={resumeScan}>▶ Fortsetzen</button>
      {:else}
        <button class="btn" onclick={pauseScan}>⏸ Pause</button>
      {/if}
      <button class="btn danger" onclick={cancelScan}>✕ Abbrechen</button>
    </div>
  </div>
</div>

<!-- ═══ REVIEW ═══ -->
{:else if phase === 'review'}
<div class="topbar">
  <button class="btn sm" onclick={() => {phase='sessions';selectedItem=null;}}>Zurueck</button>
  <span class="tpath">{activeSession?.scan_path}</span>
  <div class="pills">
    {#each [['all','Alle',null],['matched','Match',(sessionStats?.exact||0)+(sessionStats?.exact_rss||0)+(sessionStats?.fuzzy||0)],['new','Neu',sessionStats?.unmatched],['duplicate','Duplikat',sessionStats?.duplicates],['undecided','Offen',totalCount-decidedCount],['decided','Erledigt',decidedCount]] as [key,label,cnt]}
    <button class="pill" class:active={matchFilter===key} onclick={() => {matchFilter=key;loadResults(activeSession?.id,1);}}>{label}{cnt!=null?' ('+cnt+')':''}</button>
    {/each}
  </div>
  <button class="btn primary" disabled={decidedCount===0} onclick={executeDecisions}>Import ({decidedCount})</button>
</div>

<div class="summary">
  <strong>{totalCount} Dateien</strong>
  {#if sessionStats}
  <span style="color:var(--status-error)">{sessionStats.duplicates||0} Dup</span>
  <span style="color:var(--accent-primary)">{sessionStats.exact_rss||0} RSS</span>
  <span style="color:var(--status-warning)">{sessionStats.fuzzy||0} Fuzzy</span>
  <span style="color:var(--text-muted)">{sessionStats.unmatched||0} Neu</span>
  {/if}
  <span class="sdone">{decidedCount} erledigt</span>
</div>

<div class="panels">
  <!-- LEFT: Channels -->
  <div class="panel pleft">
    <div class="ph">Kanaele</div>
    <div class="chsrch"><input type="text" bind:value={channelSearch} placeholder="Suchen..." class="inp sm" /></div>
    <div class="chlist">
      {#each filteredChannels as ch}
      <button class="chrow" class:active={selectedChannel?.id===ch.id} onclick={() => {selectedChannel=ch;loadChannelVideos(ch.id);}}>
        <span class="chname">{ch.name}</span><span class="chcnt">{ch.videoCount}</span>
      </button>
      {/each}
    </div>
    {#if selectedChannel && channelVideos.length > 0}
    <div class="chvids">
      <div class="chvh">{selectedChannel.name}</div>
      {#each channelVideos.slice(0,20) as v}
      <div class="chvrow"><span class="cvdot" class:ready={v.status==='ready'}></span><span class="cvt">{v.title}</span><span class="cvd">{formatDuration(v.duration)}</span></div>
      {/each}
    </div>
    {/if}
  </div>

  <!-- CENTER: Action -->
  <div class="panel pcenter">
    <div class="ph">Aktion</div>
    {#if selectedItem}
    <div class="preview">
      {#if previewPlaying}
      <video src={previewUrl(selectedItem.file_path)} controls autoplay class="pvid"></video>
      {:else}
      <button class="pph" onclick={() => previewPlaying=true}><span class="pplay">&#9654;</span><span class="pdur">{formatDuration(selectedItem.duration)}</span></button>
      {/if}
    </div>
    <div class="finfo">
      <div class="ftitle">{selectedItem.title||selectedItem.filename}</div>
      <div class="fmeta">
        <span>{formatSize(selectedItem.file_size)}</span>
        <span>{formatDuration(selectedItem.duration)}</span>
        {#if selectedItem.youtube_id}<span class="ytid">ID:{selectedItem.youtube_id}</span>{/if}
      </div>
    </div>
    <div class="mcard" style="--mc:{matchColor(selectedItem.match_type)}">
      {#if selectedItem.match_type === 'duplicate' || selectedItem.match_type === 'exact'}
        <div class="mhdr"><span class="mlbl">Bereits in Bibliothek</span></div>
        <div class="mactions">
          <button class="btn sm" onclick={() => setDecision(selectedItem.id,'skip')}>Skip (S)</button>
          <button class="btn sm warn" onclick={() => setDecision(selectedItem.id,'replace')}>Ersetzen</button>
          <button class="btn sm danger" onclick={() => setDecision(selectedItem.id,'delete')}>Loeschen (D)</button>
        </div>
      {:else if selectedItem.match_type === 'exact_rss'}
        <div class="mhdr"><span class="mlbl">RSS-Match (nicht geladen)</span><span class="mconf">100%</span></div>
        <div class="mtitle">{selectedItem.match_title}</div>
        <div class="mchan">{selectedItem.match_channel}</div>
        {#if selectedItem.duration_boost}<span class="dbadge boost">Duration passt</span>{/if}
        <div class="mactions">
          <button class="btn sm primary" onclick={() => setDecision(selectedItem.id,'link_rss')}>Verknuepfen (J)</button>
          <button class="btn sm" onclick={() => setDecision(selectedItem.id,'import_new',assignChannel)}>Als Neu (K)</button>
          <button class="btn sm danger" onclick={() => setDecision(selectedItem.id,'delete')}>D</button>
        </div>
      {:else if selectedItem.match_type === 'fuzzy_hi' || selectedItem.match_type === 'fuzzy_lo' || selectedItem.match_type === 'weak'}
        <div class="mhdr"><span class="mlbl">{matchLabel(selectedItem.match_type)}</span><span class="mconf">{Math.round(selectedItem.match_confidence*100)}%</span></div>
        <div class="mtitle">{selectedItem.match_title}</div>
        <div class="mchan">{selectedItem.match_channel}</div>
        {#if selectedItem.duration_boost}<span class="dbadge boost">Duration passt</span>{/if}
        {#if selectedItem.duration_penalty}<span class="dbadge penalty">Duration weicht ab</span>{/if}
        {#if selectedItem.match_duration}<div class="dcmp">Datei: {formatDuration(selectedItem.duration)} | Match: {formatDuration(selectedItem.match_duration)}</div>{/if}
        <div class="mactions">
          <button class="btn sm primary" onclick={() => setDecision(selectedItem.id,'link')}>Verknuepfen (J)</button>
          <button class="btn sm" onclick={() => setDecision(selectedItem.id,'import_new',assignChannel)}>Als Neu (K)</button>
          <button class="btn sm danger" onclick={() => setDecision(selectedItem.id,'delete')}>D</button>
        </div>
        {#if selectedItem.match_candidates?.length > 1}
        <details class="cands"><summary>Kandidaten ({selectedItem.match_candidates.length})</summary>
          {#each selectedItem.match_candidates.slice(0,5) as c}
          <div class="crow"><span class="cscore">{Math.round(c.confidence*100)}%</span><span class="ctitle">{c.title}</span></div>
          {/each}
        </details>
        {/if}
      {:else}
        <div class="mhdr"><span class="mlbl">Neues Video</span></div>
        <div class="achsel">
          <label class="flabel-sm">Kanal:</label>
          <select bind:value={assignChannel} class="inp sm">
            <option value="">Ordner: {selectedItem.folder_name}</option>
            {#each channels as ch}<option value={ch.name}>{ch.name}</option>{/each}
          </select>
        </div>
        <div class="mactions">
          <button class="btn sm primary" onclick={() => setDecision(selectedItem.id,'import_new',assignChannel||selectedItem.channel_name)}>Importieren (J)</button>
          <button class="btn sm" onclick={() => setDecision(selectedItem.id,'skip')}>Skip (S)</button>
          <button class="btn sm danger" onclick={() => setDecision(selectedItem.id,'delete')}>D</button>
        </div>
      {/if}
      {#if selectedItem.decision}<div class="dbdg">{decLabel(selectedItem.decision)}</div>{/if}
    </div>
    <div class="kbhints">J=Annehmen K=Neu D=Loeschen S=Skip</div>
    {:else}
    <div class="nosel"><span>Datei rechts auswaehlen</span></div>
    {/if}
  </div>

  <!-- RIGHT: Files -->
  <div class="panel pright">
    <div class="ph">
      <span>Dateien ({resultsMeta.total || 0})</span>
      <div class="ph-controls">
        {#if resultsMeta.folders?.length > 1}
        <select class="inp xs" value={folderFilter} onchange={(e) => {folderFilter=e.target.value;loadResults(activeSession?.id,1);}}>
          <option value="">Alle Ordner ({resultsMeta.folders.length})</option>
          {#each resultsMeta.folders as f}
          <option value={f.folder_name}>{f.folder_name} ({f.decided}/{f.count})</option>
          {/each}
        </select>
        {/if}
        <input type="text" bind:value={searchQuery} placeholder="Suchen..." class="inp xs"
          onkeydown={(e) => e.key==='Enter' && loadResults(activeSession?.id,1)} />
      </div>
    </div>
    {#if folderFilter}
    <div class="bulk">
      <span class="blbl">Ordner: {folderFilter}</span>
      <button class="btn xs" onclick={() => setBulkDecision('import_new',null,folderFilter)}>Alle importieren</button>
      <button class="btn xs" onclick={() => setBulkDecision('skip',null,folderFilter)}>Alle skip</button>
      <button class="btn xs" onclick={() => {folderFilter='';loadResults(activeSession?.id,1);}}>✕</button>
    </div>
    {/if}
    <div class="flist">
      {#each results as item, idx}
      <button class="frow" class:selected={selectedItem?.id===item.id} class:decided={!!item.decision} onclick={() => selectItem(item,idx)}>
        <span class="mind" style="background:{matchColor(item.match_type)}">{#if item.decision}{item.decision==='delete'?'x':'v'}{:else}{matchIcon(item.match_type)}{/if}</span>
        <span class="fname" class:strike={item.decision==='delete'}>{item.title || item.filename}</span>
        <span class="fsize">{formatSize(item.file_size)}</span>
        <span class="fdur">{formatDuration(item.duration)}</span>
        {#if item.duration_boost}<span class="durdot">T</span>{/if}
      </button>
      {/each}
      {#if results.length === 0}<div class="nores">Keine Dateien</div>{/if}
    </div>
    {#if resultsMeta.total_pages > 1}
    <div class="pagi">
      <button class="btn xs" disabled={currentPage<=1} onclick={() => loadResults(activeSession?.id,currentPage-1)}>Prev</button>
      <span>{currentPage}/{resultsMeta.total_pages}</span>
      <button class="btn xs" disabled={currentPage>=resultsMeta.total_pages} onclick={() => loadResults(activeSession?.id,currentPage+1)}>Next</button>
    </div>
    {/if}
  </div>
</div>

<!-- ═══ EXECUTING ═══ -->
{:else if phase === 'executing'}
<div class="scanning"><div class="pcard"><h2>Import läuft...</h2><p class="muted">Dateien werden verschoben, Thumbnails verarbeitet, Scan-Ordner aufgeräumt.</p><p class="muted">Das kann bei vielen Dateien etwas dauern.</p></div></div>
{/if}

</div>

<style>
  .iw { display:flex; flex-direction:column; height:100%; background:var(--bg-primary); color:var(--text-primary); font-family:inherit; }
  .muted { color:var(--text-muted); font-size:0.85rem; }

  .sessions { max-width:700px; margin:0 auto; padding:2rem 1.5rem; }
  .sessions h2 { margin:0 0 0.25rem; }
  .sessions h3 { font-size:0.9rem; color:var(--text-secondary); margin:1.5rem 0 0.5rem; }
  .scan-form { margin:1.5rem 0; padding:1rem; border-radius:8px; background:var(--bg-secondary); border:1px solid var(--border-primary); }
  .scan-row { display:flex; gap:0.5rem; align-items:center; flex-wrap:wrap; }
  .flabel { display:block; font-size:0.75rem; color:var(--text-secondary); margin-bottom:0.4rem; font-weight:600; }
  .flabel-sm { font-size:0.7rem; color:var(--text-muted); display:block; margin-bottom:0.2rem; }
  .inp { padding:0.4rem 0.6rem; border-radius:5px; border:1px solid var(--border-primary); background:var(--bg-primary); color:var(--text-primary); font-size:0.85rem; flex:1; min-width:120px; }
  .inp:focus { outline:none; border-color:var(--accent-primary); }
  .inp.sm { font-size:0.8rem; padding:0.3rem 0.5rem; }
  .inp.xs { font-size:0.75rem; padding:0.2rem 0.4rem; width:110px; flex:none; }
  .cbl { display:flex; align-items:center; gap:0.3rem; font-size:0.8rem; color:var(--text-secondary); white-space:nowrap; }
  .btn { padding:0.4rem 0.8rem; border-radius:5px; border:1px solid var(--border-primary); background:var(--bg-secondary); color:var(--text-primary); cursor:pointer; font-size:0.8rem; font-weight:600; white-space:nowrap; }
  .btn:hover { background:var(--bg-tertiary); }
  .btn:disabled { opacity:0.4; cursor:default; }
  .btn.primary { background:var(--accent-primary); color:#fff; border-color:var(--accent-primary); }
  .btn.danger { color:var(--status-error); border-color:var(--status-error); background:transparent; }
  .btn.warn { color:var(--status-warning); border-color:var(--status-warning); background:transparent; }
  .btn.sm { font-size:0.75rem; padding:0.3rem 0.6rem; }
  .btn.xs { font-size:0.7rem; padding:0.2rem 0.5rem; }

  .scard { display:flex; align-items:center; gap:1rem; padding:0.6rem 0.8rem; border-radius:6px; background:var(--bg-secondary); border:1px solid var(--border-primary); margin-bottom:0.4rem; }
  .sinfo { flex:1; }
  .spath { font-weight:600; font-size:0.85rem; }
  .smeta { font-size:0.75rem; color:var(--text-muted); }
  .sactions { display:flex; gap:0.3rem; }

  .scanning { display:flex; align-items:center; justify-content:center; flex:1; }
  .pcard { text-align:center; padding:2rem; background:var(--bg-secondary); border-radius:12px; border:1px solid var(--border-primary); min-width:400px; }
  .pbar-wrap { width:100%; height:8px; background:var(--bg-tertiary); border-radius:4px; overflow:hidden; margin:1rem 0; }
  .pbar { height:100%; background:var(--accent-primary); border-radius:4px; transition:width 0.3s; }
  .pbar.paused { background:var(--status-warning); animation: pulse-bar 1.5s ease-in-out infinite; }
  @keyframes pulse-bar { 0%,100% { opacity:1; } 50% { opacity:0.5; } }
  .pstatus { color:var(--text-secondary); font-size:0.85rem; margin:0.5rem 0 0.25rem; }
  .pactions { display:flex; gap:0.5rem; margin-top:1rem; justify-content:center; }
  .ppct { font-size:1.5rem; font-weight:700; color:var(--accent-primary); }

  .topbar { display:flex; align-items:center; gap:0.5rem; padding:0.5rem 0.8rem; border-bottom:1px solid var(--border-primary); background:var(--bg-secondary); flex-wrap:wrap; }
  .tpath { font-size:0.75rem; color:var(--text-muted); padding:0.15rem 0.5rem; background:var(--bg-tertiary); border-radius:4px; }
  .pills { display:flex; gap:0.2rem; flex:1; flex-wrap:wrap; }
  .pill { padding:0.2rem 0.5rem; border-radius:10px; border:1px solid var(--border-primary); background:transparent; color:var(--text-muted); cursor:pointer; font-size:0.7rem; }
  .pill.active { background:var(--accent-primary); color:#fff; border-color:var(--accent-primary); }

  .summary { display:flex; align-items:center; gap:0.8rem; padding:0.4rem 0.8rem; background:var(--bg-tertiary); border-bottom:1px solid var(--border-primary); font-size:0.8rem; flex-wrap:wrap; }
  .sdone { margin-left:auto; font-weight:600; color:var(--status-success); }

  .panels { display:flex; flex:1; overflow:hidden; }
  .panel { display:flex; flex-direction:column; overflow:hidden; }
  .pleft { width:220px; border-right:1px solid var(--border-primary); background:var(--bg-secondary); }
  .pcenter { width:300px; border-right:1px solid var(--border-primary); background:var(--bg-secondary); }
  .pright { flex:1; background:var(--bg-primary); }
  .ph { padding:0.4rem 0.6rem; border-bottom:1px solid var(--border-primary); font-size:0.7rem; font-weight:700; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.05em; display:flex; align-items:center; gap:0.5rem; justify-content:space-between; }

  .chsrch { padding:0.3rem; border-bottom:1px solid var(--border-primary); }
  .chlist { flex:1; overflow-y:auto; }
  .chrow { display:flex; align-items:center; gap:0.4rem; width:100%; padding:0.35rem 0.6rem; border:none; background:transparent; cursor:pointer; text-align:left; color:var(--text-primary); font-size:0.78rem; border-left:2px solid transparent; }
  .chrow:hover { background:var(--bg-tertiary); }
  .chrow.active { background:rgba(107,163,232,0.1); border-left-color:var(--accent-primary); }
  .chname { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .chcnt { font-size:0.7rem; color:var(--text-muted); }
  .chvids { border-top:1px solid var(--border-primary); max-height:35%; overflow-y:auto; }
  .chvh { padding:0.3rem 0.6rem; font-size:0.7rem; font-weight:600; color:var(--text-secondary); border-bottom:1px solid var(--border-primary); }
  .chvrow { display:flex; align-items:center; gap:0.3rem; padding:0.2rem 0.6rem; font-size:0.72rem; border-bottom:1px solid var(--bg-tertiary); }
  .cvdot { width:5px; height:5px; border-radius:50%; background:var(--status-warning); flex-shrink:0; }
  .cvdot.ready { background:var(--status-success); }
  .cvt { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .cvd { font-size:0.65rem; color:var(--text-muted); }

  .preview { padding:0.5rem; }
  .pvid { width:100%; border-radius:6px; max-height:180px; background:#000; }
  .pph { width:100%; aspect-ratio:16/9; border-radius:6px; background:var(--bg-tertiary); border:1px solid var(--border-primary); cursor:pointer; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:0.3rem; color:var(--text-muted); }
  .pph:hover { border-color:var(--accent-primary); }
  .pplay { font-size:1.5rem; opacity:0.5; }
  .pdur { font-size:0.75rem; }

  .finfo { padding:0.3rem 0.6rem 0.5rem; border-bottom:1px solid var(--border-primary); }
  .ftitle { font-size:0.85rem; font-weight:700; line-height:1.3; margin-bottom:0.2rem; }
  .fmeta { display:flex; gap:0.6rem; font-size:0.72rem; color:var(--text-muted); flex-wrap:wrap; }
  .ytid { color:var(--status-error); font-weight:600; }

  .mcard { padding:0.6rem; margin:0.5rem; border-radius:8px; border:1px solid color-mix(in srgb, var(--mc) 30%, transparent); background:color-mix(in srgb, var(--mc) 4%, transparent); }
  .mhdr { display:flex; align-items:center; justify-content:space-between; margin-bottom:0.3rem; }
  .mlbl { font-size:0.75rem; font-weight:700; color:var(--mc); text-transform:uppercase; }
  .mconf { font-size:0.85rem; font-weight:700; color:var(--mc); }
  .mtitle { font-size:0.82rem; font-weight:600; margin-bottom:0.1rem; }
  .mchan { font-size:0.72rem; color:var(--text-muted); margin-bottom:0.3rem; }
  .mactions { display:flex; gap:0.3rem; margin-top:0.5rem; }
  .mactions .btn { flex:1; text-align:center; }
  .dbadge { font-size:0.65rem; padding:0.1rem 0.3rem; border-radius:3px; display:inline-block; margin:0.2rem 0.2rem 0.2rem 0; }
  .dbadge.boost { background:rgba(34,197,94,0.15); color:var(--status-success); }
  .dbadge.penalty { background:rgba(239,68,68,0.1); color:var(--status-error); }
  .dcmp { font-size:0.7rem; color:var(--text-muted); }
  .cands { font-size:0.72rem; margin-top:0.5rem; }
  .cands summary { cursor:pointer; color:var(--text-muted); }
  .crow { display:flex; gap:0.4rem; padding:0.15rem 0; border-bottom:1px solid var(--bg-tertiary); }
  .cscore { font-weight:700; width:30px; }
  .ctitle { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .achsel { margin:0.3rem 0; }
  .dbdg { margin-top:0.5rem; padding:0.3rem; border-radius:5px; background:var(--bg-tertiary); text-align:center; font-size:0.75rem; font-weight:600; color:var(--status-success); }
  .kbhints { text-align:center; font-size:0.65rem; color:var(--text-muted); padding:0.3rem; opacity:0.5; }
  .nosel { display:flex; align-items:center; justify-content:center; flex:1; color:var(--border-primary); font-size:0.85rem; }

  .ph-controls { display:flex; gap:0.3rem; align-items:center; }
  .ph-controls select { width:180px; flex:none; }
  .bulk { display:flex; align-items:center; gap:0.3rem; padding:0.25rem 0.5rem; border-bottom:1px solid var(--border-primary); background:var(--bg-tertiary); }
  .blbl { font-size:0.7rem; color:var(--text-muted); }

  .flist { flex:1; overflow-y:auto; }
  .frow { display:flex; align-items:center; gap:0.3rem; width:100%; padding:0.25rem 0.5rem; border:none; background:transparent; cursor:pointer; text-align:left; font-size:0.75rem; border-left:2px solid transparent; color:var(--text-primary); }
  .frow:hover { background:var(--bg-tertiary); }
  .frow.selected { background:rgba(107,163,232,0.1); border-left-color:var(--accent-primary); }
  .frow.decided { opacity:0.35; }
  .mind { width:14px; height:14px; border-radius:3px; display:flex; align-items:center; justify-content:center; font-size:0.55rem; font-weight:700; color:#fff; flex-shrink:0; }
  .fname { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-weight:500; }
  .fname.strike { text-decoration:line-through; color:var(--text-muted); }
  .fsize, .fdur { font-size:0.65rem; color:var(--text-muted); flex-shrink:0; }
  .durdot { font-size:0.6rem; color:var(--status-success); flex-shrink:0; }
  .nores { text-align:center; padding:2rem; color:var(--text-muted); }
  .pagi { display:flex; align-items:center; justify-content:center; gap:0.5rem; padding:0.4rem; border-top:1px solid var(--border-primary); font-size:0.75rem; color:var(--text-muted); }
</style>

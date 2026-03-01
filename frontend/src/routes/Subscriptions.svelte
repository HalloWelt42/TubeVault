<!--
  TubeVault
  © HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
  SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
-->
<script>
  import { api } from '../lib/api/client.js';
  import { toast } from '../lib/stores/notifications.js';
  import { navigate } from '../lib/router/router.js';
  import { formatDateRelative } from '../lib/utils/format.js';

  function fmtInterval(seconds) {
    if (!seconds) return '?';
    if (seconds < 3600) return `${Math.round(seconds / 60)}min`;
    if (seconds < 86400) return `${Math.round(seconds / 3600)}h`;
    return `${Math.round(seconds / 86400)}d`;
  }

  function openChannel(sub) {
    navigate(`/channel/${sub.channel_id}`);
  }

  let subs = $state([]);
  let total = $state(0);
  let rssStats = $state(null);
  let showImport = $state(false);
  let channelInput = $state('');
  let batchInput = $state('');
  let autoDownload = $state(false);
  let defaultQuality = $state('720p');
  let loading = $state(false);
  let importing = $state(false);
  let filterMode = $state('all');
  let searchQuery = $state('');
  let prognosis = $state(null);

  async function loadPrognosis() {
    try { prognosis = await api.getDripPrognosis(); } catch { prognosis = null; }
  }

  async function loadSubs() {
    try {
      const result = await api.getSubscriptions({ page: 1, per_page: 1000 });
      subs = result.subscriptions || [];
      total = result.total || 0;
      rssStats = await api.getRSSStats();
    } catch (e) { toast.error(e.message); }
  }

  function extractChannelId(input) {
    input = input.trim();
    if (!input) return '';
    const m = input.match(/channel\/([a-zA-Z0-9_-]+)/);
    if (m) return m[1];
    if (input.startsWith('UC') && input.length >= 20) return input;
    return input;
  }

  async function addSingle() {
    if (!channelInput.trim()) return;
    loading = true;
    try {
      const input = channelInput.trim();
      // Backend löst Video-URLs, Kanal-URLs und IDs auf
      const cid = extractChannelId(input);
      const isUrl = input.includes('youtu.be/') || input.includes('youtube.com/watch') || input.includes('youtube.com/shorts') || input.includes('youtube.com/@');
      await api.addSubscription({
        channel_id: isUrl ? input : cid,
        auto_download: autoDownload,
        download_quality: defaultQuality,
      });
      toast.success('Abo hinzugefügt -  Avatar wird geladen…');
      channelInput = '';
      setTimeout(loadSubs, 3000);
    } catch (e) { toast.error(e.message); }
    finally { loading = false; }
  }

  async function addBatch() {
    const ids = batchInput.split('\n').map(l => extractChannelId(l)).filter(l => l);
    if (!ids.length) return;
    importing = true;
    try {
      const result = await api.addSubscriptionsBatch({ channel_ids: ids, auto_download: autoDownload });
      toast.success(`${result.added} Abos importiert, ${result.skipped} übersprungen`);
      batchInput = '';
      showImport = false;
      loadSubs();
    } catch (e) { toast.error(e.message); }
    finally { importing = false; }
  }

  async function toggleAutoDownload(sub) {
    await api.updateSubscription(sub.id, { auto_download: !sub.auto_download });
    const i = subs.findIndex(s => s.id === sub.id);
    if (i >= 0) { subs[i] = { ...subs[i], auto_download: !sub.auto_download }; subs = [...subs]; }
  }

  async function updateQuality(sub, quality) {
    await api.updateSubscription(sub.id, { download_quality: quality });
    const i = subs.findIndex(s => s.id === sub.id);
    if (i >= 0) { subs[i] = { ...subs[i], download_quality: quality }; subs = [...subs]; }
    toast.info(`${sub.channel_name}: Qualität: ${quality}`);
  }

  async function toggleAudioOnly(sub) {
    const val = !sub.audio_only;
    await api.updateSubscription(sub.id, { audio_only: val });
    const i = subs.findIndex(s => s.id === sub.id);
    if (i >= 0) { subs[i] = { ...subs[i], audio_only: val }; subs = [...subs]; }
    toast.info(`${sub.channel_name}: ${val ? 'Nur Audio' : 'Video + Audio'}`);
  }

  async function toggleEnabled(sub) {
    await api.updateSubscription(sub.id, { enabled: !sub.enabled });
    const i = subs.findIndex(s => s.id === sub.id);
    if (i >= 0) { subs[i] = { ...subs[i], enabled: !sub.enabled }; subs = [...subs]; }
  }

  async function toggleDrip(sub) {
    const val = !sub.drip_enabled;
    await api.updateSubscription(sub.id, { drip_enabled: val });
    const i = subs.findIndex(s => s.id === sub.id);
    if (i >= 0) {
      subs[i] = { ...subs[i], drip_enabled: val, drip_completed_at: val ? null : subs[i].drip_completed_at };
      subs = [...subs];
    }
    toast.info(`${sub.channel_name}: +${sub.drip_count||3}/day ${val ? 'aktiviert' : 'deaktiviert'}`);
  }

  async function toggleDripArchive(sub) {
    const val = !sub.drip_auto_archive;
    await api.updateSubscription(sub.id, { drip_auto_archive: val });
    const i = subs.findIndex(s => s.id === sub.id);
    if (i >= 0) { subs[i] = { ...subs[i], drip_auto_archive: val }; subs = [...subs]; }
    toast.info(`${sub.channel_name}: Auto-Archiv ${val ? 'an' : 'aus'}`);
  }

  async function toggleSuggestExclude(sub) {
    const val = !sub.suggest_exclude;
    // Wenn Einschluss: Overrides zurücksetzen
    if (!val) {
      try { await api.request(`/api/subscriptions/${sub.id}/reset-suggest-overrides`, { method: 'POST' }); } catch {}
    }
    await api.updateSubscription(sub.id, { suggest_exclude: val });
    const i = subs.findIndex(s => s.id === sub.id);
    if (i >= 0) { subs[i] = { ...subs[i], suggest_exclude: val }; subs = [...subs]; }
    toast.info(`${sub.channel_name}: ${val ? 'Aus Vorschlägen ausgeschlossen' : 'In Vorschlägen eingeschlossen'}`);
  }

  /**
   * Kanal-Vollständigkeits-Siegel:
   * 🥇 Gold:   100% komplett (downloaded >= rss_count, Scan vorhanden)
   * 🥈 Silber: Fehlen nur 1–5 Videos
   * 🥉 Bronze: War mal komplett (drip_completed_at gesetzt), aber jetzt fehlen welche
   */
  function channelMedal(sub) {
    const rss = sub.rss_count || 0;
    const dl = sub.downloaded_count || 0;
    if (rss === 0 || !sub.last_scanned) return null;
    const missing = rss - dl;
    if (missing <= 0) return { icon: '🥇', cls: 'medal-gold', label: 'Vollständig' };
    if (missing <= 5) return { icon: '🥈', cls: 'medal-silver', label: `${missing} fehlen` };
    if (sub.drip_completed_at) return { icon: '🥉', cls: 'medal-bronze', label: `War komplett · ${missing} fehlen` };
    return null;
  }

  function dripTooltip(sub) {
    if (sub.drip_completed_at) return 'Komplett -  alle Videos geladen';
    const missing = (sub.rss_count||0) - (sub.downloaded_count||0);
    const next = sub.drip_next_run ? new Date(sub.drip_next_run).toLocaleTimeString('de-DE', {hour:'2-digit',minute:'2-digit'}) : '?';
    return sub.drip_enabled
      ? `Nächster Run: ${next} · ${missing} fehlen`
      : `+${sub.drip_count||3} Videos/Tag laden · ${missing} fehlen`;
  }

  async function removeSub(sub) {
    await api.removeSubscription(sub.id);
    toast.info(`"${sub.channel_name}" entfernt`);
    subs = subs.filter(s => s.id !== sub.id);
    total--;
  }

  async function pollNow() {
    const result = await api.triggerRSSPoll();
    toast.success(`RSS-Check gestartet (${result.feed_count} Feeds)`);
  }

  async function resetAllIntervals() {
    const result = await api.resetAllIntervals();
    toast.success(`${result.reset} Kanäle auf ${fmtInterval(result.interval)} zurückgesetzt`);
    loadSubs();
  }

  async function halveInterval(sub) {
    const result = await api.halveInterval(sub.id);
    const idx = subs.findIndex(s => s.id === sub.id);
    if (idx >= 0) { subs[idx] = { ...subs[idx], check_interval: result.new_interval }; subs = [...subs]; }
    toast.info(`${sub.channel_name}: ${fmtInterval(result.old_interval)} → ${fmtInterval(result.new_interval)}`);
  }

  async function resetInterval(sub) {
    const result = await api.resetInterval(sub.id);
    const idx = subs.findIndex(s => s.id === sub.id);
    if (idx >= 0) { subs[idx] = { ...subs[idx], check_interval: result.new_interval }; subs = [...subs]; }
    toast.info(`${sub.channel_name}: Reset auf ${fmtInterval(result.new_interval)}`);
  }

  async function resetAllErrors() {
    try {
      const res = await api.resetAllErrors();
      toast.success(`${res.reset} Abos entsperrt`);
      await loadSubs();
    } catch (e) { toast.error(e.message); }
  }

  let uncheckedCount = $derived(subs.filter(s => !s.last_checked).length);
  let disabledCount = $derived(subs.filter(s => !s.enabled).length);

  let filtered = $derived.by(() => {
    let result = filterMode === 'all' ? subs :
      filterMode === 'active' ? subs.filter(s => s.enabled) :
      filterMode === 'auto' ? subs.filter(s => s.auto_download) :
      filterMode === 'errors' ? subs.filter(s => s.error_count > 0) :
      filterMode === 'unchecked' ? subs.filter(s => !s.last_checked) :
      filterMode === 'disabled' ? subs.filter(s => !s.enabled) : subs;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(s =>
        (s.channel_name || '').toLowerCase().includes(q) ||
        (s.channel_id || '').toLowerCase().includes(q)
      );
    }
    return result;
  });

  $effect(() => { loadSubs(); loadPrognosis(); });
</script>

<div class="page">
  <div class="page-header">
    <div>
      <h1 class="title">Kanäle</h1>
      <span class="subtitle">{filtered.length !== subs.length ? `${filtered.length} von ` : ''}{total} Kanäle</span>
    </div>
    <div class="actions">
      <button class="btn-ghost" onclick={() => showImport = !showImport}>
        {showImport ? 'Schließen' : 'Hinzufügen'}
      </button>
      <button class="btn-ghost" onclick={() => navigate('/feed')}>
        <i class="fa-solid fa-rss"></i> Feed{#if rssStats?.new_videos > 0}<span class="badge-red">{rssStats.new_videos}</span>{/if}
      </button>
      <button class="btn-ghost" onclick={resetAllIntervals} title="Alle Intervalle zurücksetzen">
        <i class="fa-solid fa-clock-rotate-left"></i> Reset Checks
      </button>
      <button class="btn-primary" onclick={pollNow}><i class="fa-solid fa-rotate-right"></i> Jetzt prüfen</button>
    </div>
  </div>

  {#if rssStats}
  <div class="filter-bar">
    {#each [['all','Alle',total],['active','Aktiv',rssStats.enabled_subscriptions],['auto','Auto-DL',rssStats.auto_download_subscriptions],['errors','Fehler',subs.filter(s=>s.error_count>0).length]] as [key,label,count]}
      <button class="filter-chip" class:active={filterMode===key} onclick={()=>filterMode=key}>
        <strong>{count}</strong> {label}
      </button>
    {/each}
    {#if uncheckedCount > 0}
      <button class="filter-chip warn" class:active={filterMode==='unchecked'} onclick={()=>filterMode='unchecked'}>
        <strong>{uncheckedCount}</strong> Ungeprüft
      </button>
    {/if}
    {#if disabledCount > 0}
      <button class="filter-chip" class:active={filterMode==='disabled'} onclick={()=>filterMode='disabled'}>
        <strong>{disabledCount}</strong> Deaktiviert
      </button>
    {/if}
    {#if subs.filter(s => s.error_count > 0 || !s.enabled).length > 0}
      <button class="filter-chip reset-chip" onclick={resetAllErrors} title="Alle Fehler + Deaktivierungen zurücksetzen">
        <i class="fa-solid fa-lock-open"></i> Alle entsperren
      </button>
    {/if}
    <button class="filter-chip highlight" onclick={()=>navigate('/feed')}>
      <strong>{rssStats.new_videos}</strong> Neue Videos
    </button>
  </div>

  <!-- Info-Zeile: Scanner-Status -->
  <div class="info-bar">
    <span><i class="fa-solid fa-circle-info"></i>
      {subs.length} von {total} Kanälen geladen.
      {#if uncheckedCount > 0}
        {uncheckedCount} Kanäle warten noch auf den ersten Scan -  der Scheduler arbeitet diese automatisch ab.
      {:else}
        Alle Kanäle wurden mindestens einmal geprüft.
      {/if}
    </span>
  </div>
  {/if}

  {#if showImport}
  <div class="import-panel">
    <div class="import-row">
      <h3>Kanal hinzufügen</h3>
      <div class="input-row">
        <input type="text" class="input" placeholder="Kanal-ID, Kanal-URL, @Handle oder Video-URL…" bind:value={channelInput} onkeydown={(e)=>e.key==='Enter'&&addSingle()} />
        <button class="btn-primary" onclick={addSingle} disabled={loading||!channelInput.trim()}>{loading?'…':'Hinzufügen'}</button>
      </div>
    </div>
    <div class="divider"></div>
    <div class="import-row">
      <h3>Batch Import</h3>
      <p class="hint">FreeTube: Einstellungen : Daten : Abonnements exportieren : Channel-IDs hier einfügen</p>
      <textarea class="textarea" placeholder="Eine Kanal-ID oder URL pro Zeile…" bind:value={batchInput} rows="5"></textarea>
      <div class="import-actions">
        <label class="check"><input type="checkbox" bind:checked={autoDownload}/> Auto-Download</label>
        <select class="quality-select" bind:value={defaultQuality}>
          <option value="best">Beste</option>
          <option value="1080p">1080p</option>
          <option value="720p">720p</option>
          <option value="480p">480p</option>
        </select>
        <button class="btn-primary" onclick={addBatch} disabled={importing||!batchInput.trim()}>
          {importing?'Importiere…':`${batchInput.split('\n').filter(l=>l.trim()).length} importieren`}
        </button>
      </div>
    </div>
  </div>
  {/if}

  <!-- Suche -->
  <div class="search-bar">
    <i class="fa-solid fa-magnifying-glass search-icon" style="font-size:0.85rem"></i>
    <input type="text" class="search-input" placeholder="Abos durchsuchen…"
           bind:value={searchQuery} />
    {#if searchQuery}
      <button class="search-clear" title="Suche leeren" onclick={() => searchQuery = ''}><i class="fa-solid fa-xmark"></i></button>
    {/if}
  </div>

  {#if prognosis && prognosis.drip_channels > 0}
  <div class="prognosis-bar">
    <i class="fa-solid fa-hourglass-half"></i>
    <span>Drip-Feed: <b>{prognosis.drip_channels}</b> Kanäle · ~<b>{prognosis.total_missing.toLocaleString('de')}</b> Videos fehlen</span>
    {#if prognosis.avg_video_size > 0}
      <span>· ~<b>{(prognosis.estimated_bytes / 1073741824).toFixed(0)} GB</b> geschätzt</span>
      <span>· ~<b>{prognosis.days_remaining > 365 ? (prognosis.days_remaining / 365).toFixed(1) + ' Jahre' : prognosis.days_remaining + ' Tage'}</b></span>
    {/if}
    {#if prognosis.disk_free > 0}
      <span class="disk-free" class:disk-warn={prognosis.disk_free < 50 * 1073741824}>
        · {prognosis.disk_free_human || (prognosis.disk_free / 1073741824).toFixed(0) + ' GB'} frei
        {#if prognosis.disk_total > 0}/ {(prognosis.disk_total / 1099511627776).toFixed(1)} TB{/if}
      </span>
    {/if}
    {#if prognosis.unscanned_channels > 0}
      <span class="prognosis-note">· ⚠ {prognosis.unscanned_channels} Kanäle ohne Scan</span>
    {/if}
  </div>
  {/if}

  {#if filtered.length > 0}
  <div class="grid">
    {#each filtered as sub (sub.id)}
    <div class="card" class:off={!sub.enabled}>
      <button class="card-top" onclick={() => openChannel(sub)} title="Kanal öffnen">
        <div class="avatar-wrap">
          {#if sub.avatar_path}
            <img class="avatar" src={api.channelAvatarUrl(sub.channel_id)} alt="" onerror={(e)=>{e.target.style.display='none';e.target.nextElementSibling.style.display='flex'}} />
          {/if}
          <div class="avatar-fb" style={sub.avatar_path?'display:none':'display:flex'}>
            {(sub.channel_name||'?')[0].toUpperCase()}
          </div>
          {#if sub.new_videos > 0}
            <span class="new-dot">{sub.new_videos}</span>
          {/if}
        </div>
        <div class="card-text">
          <span class="card-name" title={sub.channel_name||sub.channel_id}>{sub.channel_name||sub.channel_id}</span>
          <span class="card-sub">
            {#if !sub.last_checked}
              <span class="status-badge unchecked"><i class="fa-solid fa-clock"></i> Noch nicht gescannt</span>
            {:else if sub.video_count > 0}
              {sub.video_count} Videos · {formatDateRelative(sub.last_checked)} · <span class="card-interval" title="Prüfintervall (adaptiv)"><i class="fa-solid fa-rotate"></i> {fmtInterval(sub.check_interval)}</span>
            {:else}
              Keine Videos im Zeitfenster · {formatDateRelative(sub.last_checked)} · <span class="card-interval" title="Prüfintervall (adaptiv)"><i class="fa-solid fa-rotate"></i> {fmtInterval(sub.check_interval)}</span>
            {/if}
          </span>
          {#if sub.error_count > 0}
            <span class="card-err" title={sub.last_error}><i class="fa-solid fa-triangle-exclamation"></i> {sub.error_count}× Fehler</span>
          {/if}
        </div>
      </button>
      {#if sub.rss_count > 0}
      {@const medal = channelMedal(sub)}
      <div class="card-progress">
        <div class="prog-bar"><div class="prog-fill" class:prog-complete={medal?.cls === 'medal-gold'} style="width:{Math.round((sub.downloaded_count||0)/(sub.rss_count)*100)}%"></div></div>
        <span class="prog-text">{sub.downloaded_count||0}/{sub.rss_count}</span>
        {#if medal}
          <span class="medal {medal.cls}" title={medal.label}>{medal.icon}</span>
        {/if}
      </div>
      {/if}
      <div class="card-bottom">
        <button class="tag" class:tag-on={sub.auto_download} onclick={()=>toggleAutoDownload(sub)} title="Auto-Download"><i class="fa-solid fa-download"></i> Auto</button>
        <button class="tag" class:tag-on={sub.drip_enabled} class:tag-done={!!sub.drip_completed_at}
                onclick={()=>toggleDrip(sub)} title={dripTooltip(sub)}>
          {#if sub.drip_completed_at}<i class="fa-solid fa-check"></i> Fertig{:else}<i class="fa-solid fa-hourglass-half"></i> +{sub.drip_count||3}/day{/if}
        </button>
        {#if sub.drip_enabled}
        <button class="tag" class:tag-on={sub.drip_auto_archive}
                onclick={()=>toggleDripArchive(sub)} title="Geladenes direkt archivieren"><i class="fa-solid fa-box-archive"></i></button>
        {/if}
        <button class="tag" class:tag-warn={sub.suggest_exclude}
                onclick={()=>toggleSuggestExclude(sub)} title={sub.suggest_exclude ? 'Aus Vorschlägen ausgeschlossen -  Klick zum Einschließen' : 'In Vorschlägen -  Klick zum Ausschließen'}>
          <i class="fa-solid fa-dice" class:strikethrough={sub.suggest_exclude}></i>
        </button>
        <button class="tag" class:tag-on={sub.enabled} onclick={()=>toggleEnabled(sub)}>{sub.enabled?'An':'Aus'}</button>
        {#if sub.check_interval > 1800}
          <button class="tag tag-interval" onclick={(e)=>{e.stopPropagation();halveInterval(sub)}} title="Intervall halbieren ({fmtInterval(sub.check_interval)} → {fmtInterval(Math.max(1800, Math.floor(sub.check_interval/2)))})">½</button>
          <button class="tag tag-interval" onclick={(e)=>{e.stopPropagation();resetInterval(sub)}} title="Intervall zurücksetzen auf Basis"><i class="fa-solid fa-clock-rotate-left"></i></button>
        {/if}
        <button class="tag tag-del" title="Entfernen" onclick={()=>removeSub(sub)}><i class="fa-solid fa-xmark"></i></button>
      </div>
      {#if sub.auto_download}
        <div class="card-settings">
          {#if !sub.audio_only}
            <select class="quality-select" value={sub.download_quality || '720p'}
                    onchange={(e) => updateQuality(sub, e.target.value)}>
              <option value="best">Beste</option>
              <option value="1080p">1080p</option>
              <option value="720p">720p</option>
              <option value="480p">480p</option>
              <option value="360p">360p</option>
            </select>
          {/if}
          <button class="tag" class:tag-on={sub.audio_only} onclick={() => toggleAudioOnly(sub)}
                  title="Nur Audio herunterladen">
            <i class="fa-solid fa-music"></i> Audio
          </button>
        </div>
      {/if}
    </div>
    {/each}
  </div>
  {:else}
  <div class="empty">
    <i class="fa-solid fa-user-plus" style="font-size:3.5rem; color:var(--text-tertiary)"></i>
    <h3>Noch keine Abonnements</h3>
    <p>Füge YouTube-Kanäle hinzu, um per RSS neue Videos zu erkennen.</p>
    <button class="btn-primary" onclick={()=>showImport=true}>Kanäle hinzufügen</button>
  </div>
  {/if}
</div>

<style>
  .page { padding: 24px; max-width: 1200px; }
  .page-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:14px; flex-wrap:wrap; gap:12px; }
  .title { font-size:1.5rem; font-weight:700; color:var(--text-primary); margin:0; }
  .subtitle { font-size:0.82rem; color:var(--text-tertiary); }
  .actions { display:flex; gap:8px; flex-wrap:wrap; }
  .badge-red { background:var(--status-error); color:#fff; font-size:0.65rem; padding:1px 6px; border-radius:8px; font-weight:700; margin-left:4px; }

  .filter-bar { display:flex; gap:6px; margin-bottom:18px; flex-wrap:wrap; }
  .filter-chip { padding:5px 14px; background:var(--bg-secondary); border:1px solid var(--border-primary); border-radius:20px; font-size:0.78rem; color:var(--text-secondary); cursor:pointer; transition:all 0.15s; }
  .filter-chip:hover { border-color:var(--accent-primary); }
  .filter-chip.active { border-color:var(--accent-primary); background:var(--accent-muted); color:var(--accent-primary); }
  .filter-chip strong { margin-right:3px; }
  .filter-chip.highlight { border-color:var(--accent-primary); }
  .filter-chip.reset-chip { border-color:rgba(34,197,94,0.4); color:var(--status-success); background:rgba(34,197,94,0.08); }
  .filter-chip.reset-chip:hover { background:rgba(34,197,94,0.18); }
  .filter-chip.highlight strong { color:var(--accent-primary); }

  .import-panel { background:var(--bg-secondary); border:1px solid var(--border-primary); border-radius:12px; padding:20px; margin-bottom:22px; }
  .import-row h3 { font-size:0.9rem; color:var(--text-primary); margin:0 0 8px; }
  .hint { font-size:0.78rem; color:var(--text-tertiary); margin:0 0 8px; }
  .input-row { display:flex; gap:8px; }
  .input, .textarea { flex:1; padding:8px 14px; background:var(--bg-tertiary); border:1px solid var(--border-primary); border-radius:8px; color:var(--text-primary); font-size:0.85rem; outline:none; box-sizing:border-box; }
  .textarea { width:100%; font-family:monospace; font-size:0.82rem; resize:vertical; }
  .input:focus, .textarea:focus { border-color:var(--accent-primary); }
  .divider { height:1px; background:var(--border-primary); margin:16px 0; }
  .import-actions { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-top:10px; flex-wrap:wrap; }
  .check { display:flex; align-items:center; gap:6px; font-size:0.82rem; color:var(--text-secondary); cursor:pointer; }

  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:12px; }

  .search-bar {
    position: relative; display: flex; align-items: center; margin-bottom: 16px;
  }
  .search-icon { position: absolute; left: 12px; color: var(--text-tertiary); pointer-events: none; }
  .search-input {
    width: 100%; padding: 9px 36px 9px 36px; background: var(--bg-secondary);
    border: 1px solid var(--border-primary); border-radius: 10px; color: var(--text-primary);
    font-size: 0.85rem; outline: none;
  }
  .search-input:focus { border-color: var(--accent-primary); }
  .search-input::placeholder { color: var(--text-tertiary); }
  .search-clear {
    position: absolute; right: 10px; background: none; border: none; color: var(--text-tertiary);
    cursor: pointer; font-size: 0.85rem; padding: 2px 4px;
  }
  .search-clear:hover { color: var(--text-primary); }

  .card {
    background:var(--bg-secondary); border:1px solid var(--border-primary); border-radius:14px;
    padding:16px; display:flex; flex-direction:column; gap:12px; transition:all 0.2s;
  }
  .card:hover { border-color:var(--accent-primary); transform:translateY(-2px); box-shadow:0 6px 20px rgba(0,0,0,0.1); }
  .card.off { opacity:0.4; }

  .card-top { display:flex; align-items:center; gap:12px; background:none; border:none; padding:0; cursor:pointer; width:100%; text-align:left; color:inherit; }

  .avatar-wrap { position:relative; width:56px; height:56px; flex-shrink:0; }
  .avatar { width:56px; height:56px; border-radius:50%; object-fit:cover; border:2px solid var(--border-secondary); }
  .avatar-fb { width:56px; height:56px; border-radius:50%; background:var(--accent-muted); color:var(--accent-primary); display:flex; align-items:center; justify-content:center; font-size:1.4rem; font-weight:700; border:2px solid var(--border-secondary); }
  .new-dot { position:absolute; top:-3px; right:-3px; background:var(--status-error); color:#fff; font-size:0.6rem; font-weight:700; min-width:16px; height:16px; display:flex; align-items:center; justify-content:center; border-radius:8px; padding:0 3px; }

  .card-text { flex:1; min-width:0; display:flex; flex-direction:column; gap:2px; }
  .card-name { font-size:0.88rem; font-weight:700; color:var(--text-primary); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .card-sub { font-size:0.72rem; color:var(--text-tertiary); }
  .card-interval { color:var(--text-quaternary, #64748b); font-size:0.68rem; }
  .card-interval i { font-size:0.58rem; }
  .tag-interval { background:var(--bg-tertiary); color:var(--text-secondary); font-weight:700; font-size:0.72rem; min-width:24px; text-align:center; }
  .tag-interval:hover { background:var(--accent-primary); color:var(--bg-primary); }
  .card-err { font-size:0.7rem; color:var(--status-warning); }

  .card-bottom { display:flex; gap:4px; flex-wrap:wrap; }
  .card-settings { display:flex; gap:4px; align-items:center; }

  .card-progress { display:flex; align-items:center; gap:6px; padding:2px 8px; }
  .prog-bar { flex:1; height:3px; background:var(--bg-tertiary); border-radius:2px; overflow:hidden; }
  .prog-fill { height:100%; background:var(--accent-primary); border-radius:2px; transition:width 0.3s; }
  .prog-text { font-size:0.62rem; color:var(--text-muted); white-space:nowrap; }

  .tag-done { background:var(--bg-tertiary) !important; color:var(--text-muted) !important; border-color:var(--border-primary) !important; opacity:0.6; }
  .tag-warn { border-color:var(--status-warning) !important; color:var(--status-warning) !important; }
  .strikethrough { text-decoration:line-through; opacity:0.5; }
  .quality-select {
    padding:3px 6px; background:var(--bg-tertiary); border:1px solid var(--border-primary);
    border-radius:6px; font-size:0.72rem; color:var(--text-primary); cursor:pointer; outline:none;
  }
  .quality-select:focus { border-color:var(--accent-primary); }
  .tag { padding:3px 10px; background:var(--bg-tertiary); border:1px solid var(--border-primary); border-radius:6px; font-size:0.72rem; color:var(--text-tertiary); cursor:pointer; transition:all 0.15s; }
  .tag:hover { border-color:var(--accent-primary); color:var(--text-primary); }
  .tag-on { background:var(--accent-muted); color:var(--accent-primary); border-color:var(--accent-primary); }
  .tag-del:hover { border-color:var(--status-error); color:var(--status-error); }

  .empty { display:flex; flex-direction:column; align-items:center; padding:60px 20px; text-align:center; color:var(--text-tertiary); }
  .empty h3 { margin:16px 0 8px; color:var(--text-secondary); }
  .empty p { margin-bottom:16px; font-size:0.88rem; max-width:380px; }

  .info-bar {
    display: flex; align-items: center; gap: 8px; padding: 8px 14px;
    background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 8px; margin-bottom: 16px; font-size: 0.78rem;
    color: var(--text-tertiary); line-height: 1.5;
  }
  .info-bar i { color: var(--accent-primary); flex-shrink: 0; }

  .filter-chip.warn { border-color: var(--status-warning); }
  .filter-chip.warn strong { color: var(--status-warning); }
  .filter-chip.warn.active { background: rgba(245,158,11,0.1); color: var(--status-warning); }

  .status-badge {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 1px 7px; border-radius: 4px; font-size: 0.68rem; font-weight: 600;
  }
  .status-badge.unchecked { background: rgba(245,158,11,0.12); color: #d97706; }
  /* ─── Prognosis Bar ─── */
  .prognosis-bar { display: flex; align-items: center; gap: 6px; padding: 8px 12px; margin-bottom: 12px; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 8px; font-size: 0.75rem; color: var(--text-secondary); flex-wrap: wrap; }
  .prognosis-bar i { color: var(--accent-primary); }
  .prognosis-bar b { color: var(--text-primary); }
  .disk-warn { color: var(--status-warning) !important; font-weight: 600; }
  .disk-warn b { color: var(--status-warning); }
  .prognosis-note { color: var(--text-muted); font-style: italic; font-size: 0.7rem; }

  /* ─── Medals ─── */
  .medal { font-size: 0.85rem; line-height: 1; flex-shrink: 0; cursor: default; }
  .prog-fill.prog-complete { background: var(--status-success); }
</style>

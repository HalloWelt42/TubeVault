<script>
  import { api } from '../lib/api/client.js';
  import { toast } from '../lib/stores/notifications.js';
  import { navigate } from '../lib/router/router.js';
  import { formatDateRelative } from '../lib/utils/format.js';
  import { VIDEO_QUALITIES } from '../lib/constants/qualities.js';

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
  // Problem-Videos-Sektion: pro Abo-ID: { open: bool, loading: bool, videos: [...] }
  let problemState = $state({});

  async function loadPrognosis() {
    try { prognosis = await api.getDripPrognosis(); } catch { prognosis = null; }
  }

  async function toggleProblems(sub) {
    const id = sub.id;
    const cur = problemState[id] || { open: false, loading: false, videos: [] };
    if (cur.open) {
      problemState[id] = { ...cur, open: false };
      return;
    }
    problemState[id] = { ...cur, open: true, loading: true };
    try {
      const res = await api.getChannelProblemVideos(sub.channel_id);
      problemState[id] = { open: true, loading: false, videos: res.videos || [] };
    } catch (e) {
      toast.error(`Problem-Videos laden fehlgeschlagen: ${e.message}`);
      problemState[id] = { open: true, loading: false, videos: [] };
    }
  }

  async function retryProblemVideo(sub, problem) {
    try {
      await api.retryDownload(problem.job_id);
      toast.success(`"${problem.title}" zurück in Warteschlange`);
      // Aus der lokalen Liste entfernen
      const st = problemState[sub.id];
      if (st) {
        problemState[sub.id] = {
          ...st,
          videos: st.videos.filter(v => v.job_id !== problem.job_id),
        };
      }
      // Karte mit aktueller Count neu holen
      setTimeout(loadSubs, 800);
    } catch (e) {
      toast.error(`Zurück-in-Queue fehlgeschlagen: ${e.message}`);
    }
  }

  async function dismissProblemVideo(sub, problem) {
    try {
      await api.cancelDownload(problem.job_id);
      toast.info('Problem-Video entfernt');
      const st = problemState[sub.id];
      if (st) {
        problemState[sub.id] = {
          ...st,
          videos: st.videos.filter(v => v.job_id !== problem.job_id),
        };
      }
      setTimeout(loadSubs, 800);
    } catch (e) {
      toast.error(`Entfernen fehlgeschlagen: ${e.message}`);
    }
  }

  async function retryAllProblems(sub) {
    const st = problemState[sub.id];
    if (!st || !st.videos.length) return;
    const n = st.videos.length;
    try {
      for (const v of st.videos) {
        await api.retryDownload(v.job_id);
      }
      toast.success(`${n} Videos zurück in Warteschlange`);
      problemState[sub.id] = { open: true, loading: false, videos: [] };
      setTimeout(loadSubs, 800);
    } catch (e) {
      toast.error(`Sammel-Retry fehlgeschlagen: ${e.message}`);
    }
  }

  function friendlyError(msg) {
    if (!msg) return 'Unbekannter Fehler';
    const m = msg.toLowerCase();
    if (m.includes('members-only') || m.includes('members only')) return 'Nur für Mitglieder';
    if (m.includes('age-restricted') || m.includes('sign in to confirm your age')) return 'Altersbeschränkt';
    if (m.includes('private')) return 'Privat';
    if (m.includes('removed') || m.includes('terminated')) return 'Entfernt';
    if (m.includes('copyright')) return 'Urheberrecht';
    if (m.includes('unavailable')) return 'Nicht verfügbar';
    if (m.includes('retries') || m.includes('retry')) return 'Retries erschöpft';
    if (m.includes('bot')) return 'Bot-Erkennung';
    return msg.substring(0, 80);
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
      toast.success('Abo hinzugefügt – Avatar wird geladen…');
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
   * Kanal-Vollständigkeits-Siegel (prozentual, skaliert mit Kanal-Größe):
   * 🥇 Gold:   100 % komplett ODER bei ≥100 Videos höchstens 1 fehlend
   * 🥈 Silber: ≥ 90 % geladen
   * 🥉 Bronze: ≥ 70 % geladen ODER Kanal war mal komplett (drip_completed_at)
   * keine Medaille: unter 70 % oder zu wenig Datenbasis (< 3 Videos im Feed).
   */
  function channelMedal(sub) {
    const rss = sub.rss_count || 0;
    const dl = sub.downloaded_count || 0;
    if (rss < 3 || !sub.last_scanned) return null;
    const missing = Math.max(0, rss - dl);
    const pct = Math.round((dl / rss) * 100);

    // Gold: komplett, oder bei großem Feed (≥100) max 1 fehlend
    if (missing === 0) return { icon: '🥇', cls: 'medal-gold', label: 'Vollständig' };
    if (rss >= 100 && missing <= 1) {
      return { icon: '🥇', cls: 'medal-gold', label: `1 fehlt bei ${rss} gesamt — faktisch komplett` };
    }

    // Silber: ≥90 % geladen
    if (pct >= 90) {
      return { icon: '🥈', cls: 'medal-silver', label: `${pct} % geladen · ${missing} fehlen` };
    }

    // Bronze: ≥70 % oder war mal komplett
    if (pct >= 70) {
      return { icon: '🥉', cls: 'medal-bronze', label: `${pct} % geladen · ${missing} fehlen` };
    }
    if (sub.drip_completed_at) {
      return { icon: '🥉', cls: 'medal-bronze', label: `War komplett · ${missing} fehlen wieder` };
    }

    return null;
  }

  function dripTooltip(sub) {
    if (sub.drip_completed_at) return 'Komplett – alle Videos geladen';
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

  // „Komplett" = Gold-Medaille: voll geladen ODER bei ≥100 Videos max 1 fehlend.
  // Logik identisch zu channelMedal(), damit Filter und Medal konsistent sind.
  function isComplete(sub) {
    const rss = sub.rss_count || 0;
    const dl = sub.downloaded_count || 0;
    if (rss < 3 || !sub.last_scanned) return false;
    const missing = Math.max(0, rss - dl);
    if (missing === 0) return true;
    if (rss >= 100 && missing <= 1) return true;
    return false;
  }
  let completeCount = $derived(subs.filter(isComplete).length);

  let filtered = $derived.by(() => {
    let result = filterMode === 'all' ? subs :
      filterMode === 'active' ? subs.filter(s => s.enabled) :
      filterMode === 'auto' ? subs.filter(s => s.auto_download) :
      filterMode === 'errors' ? subs.filter(s => s.error_count > 0) :
      filterMode === 'unchecked' ? subs.filter(s => !s.last_checked) :
      filterMode === 'disabled' ? subs.filter(s => !s.enabled) :
      filterMode === 'complete' ? subs.filter(isComplete) :
      filterMode === 'incomplete' ? subs.filter(s => !isComplete(s) && (s.rss_count || 0) >= 3 && s.last_scanned) :
      subs;
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
    {#if completeCount > 0}
      <button class="filter-chip complete-chip" class:active={filterMode==='complete'}
              onclick={()=>filterMode='complete'}
              title="Kanäle mit Gold-Medaille: komplett geladen oder ≥100 Videos mit höchstens 1 fehlend">
        <strong>{completeCount}</strong> 🥇 Komplett
      </button>
      <button class="filter-chip" class:active={filterMode==='incomplete'}
              onclick={()=>filterMode='incomplete'}
              title="Kanäle die noch nicht komplett sind (Medaille unter Gold)">
        <strong>{total - completeCount - uncheckedCount}</strong> Unvollständig
      </button>
    {/if}
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
        {uncheckedCount} Kanäle warten noch auf den ersten Scan – der Scheduler arbeitet diese automatisch ab.
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
          {#each VIDEO_QUALITIES as q}
            <option value={q.value}>{q.label}</option>
          {/each}
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
          {#if sub.problem_count > 0}
            <span class="problem-dot" title="{sub.problem_count} Problem-Video(s) – klicke unten aufs Dreieck">
              <i class="fa-solid fa-triangle-exclamation"></i>{sub.problem_count}
            </span>
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
                onclick={()=>toggleSuggestExclude(sub)} title={sub.suggest_exclude ? 'Aus Vorschlägen ausgeschlossen – Klick zum Einschließen' : 'In Vorschlägen – Klick zum Ausschließen'}>
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
              {#each VIDEO_QUALITIES as q}
                <option value={q.value}>{q.label}</option>
              {/each}
            </select>
          {/if}
          <button class="tag" class:tag-on={sub.audio_only} onclick={() => toggleAudioOnly(sub)}
                  title="Nur Audio herunterladen">
            <i class="fa-solid fa-music"></i> Audio
          </button>
        </div>
      {/if}

      {#if sub.problem_count > 0}
        {@const ps = problemState[sub.id] || { open: false, loading: false, videos: [] }}
        <div class="problem-section">
          <button class="problem-header" onclick={() => toggleProblems(sub)}
                  title="Videos, die wegen dauerhafter Fehler nicht geladen wurden">
            <i class="fa-solid {ps.open ? 'fa-chevron-down' : 'fa-chevron-right'}"></i>
            <i class="fa-solid fa-triangle-exclamation"></i>
            <span>{sub.problem_count} Problem-Video{sub.problem_count === 1 ? '' : 's'}</span>
            <span class="problem-hint">({ps.open ? 'zuklappen' : 'anzeigen'})</span>
          </button>

          {#if ps.open}
            <div class="problem-body">
              {#if ps.loading}
                <div class="problem-loading">
                  <i class="fa-solid fa-spinner fa-spin"></i> Lade…
                </div>
              {:else if ps.videos.length === 0}
                <div class="problem-empty">Keine Problem-Videos mehr</div>
              {:else}
                <div class="problem-actions">
                  <button class="btn-sm btn-retry-all"
                          onclick={() => retryAllProblems(sub)}
                          title="Alle Problem-Videos erneut versuchen">
                    <i class="fa-solid fa-rotate-right"></i> Alle erneut versuchen
                  </button>
                </div>
                <ul class="problem-list">
                  {#each ps.videos as v (v.job_id)}
                    <li class="problem-item">
                      {#if v.thumbnail_url}
                        <img class="problem-thumb" src={v.thumbnail_url} alt="" loading="lazy" />
                      {:else}
                        <div class="problem-thumb placeholder"></div>
                      {/if}
                      <div class="problem-info">
                        <a class="problem-title" href={v.url} target="_blank" rel="noopener"
                           title={v.title}>{v.title || v.video_id}</a>
                        <span class="problem-reason" title={v.error_message || ''}>
                          <i class="fa-solid fa-circle-info"></i>
                          {friendlyError(v.error_message)}
                        </span>
                      </div>
                      <div class="problem-item-actions">
                        <button class="btn-xs btn-retry"
                                onclick={() => retryProblemVideo(sub, v)}
                                title="Erneut versuchen">
                          <i class="fa-solid fa-rotate-right"></i>
                        </button>
                        <button class="btn-xs btn-dismiss"
                                onclick={() => dismissProblemVideo(sub, v)}
                                title="Aus der Warteschlange entfernen">
                          <i class="fa-solid fa-xmark"></i>
                        </button>
                      </div>
                    </li>
                  {/each}
                </ul>
              {/if}
            </div>
          {/if}
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
  .filter-chip.complete-chip { border-color: rgba(250,204,21,0.6); }
  .filter-chip.complete-chip strong { color: #eab308; }
  .filter-chip.complete-chip.active { background: rgba(234,179,8,0.12); border-color: #eab308; }

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

  /* ─── Problem-Videos-Sektion ─── */
  .problem-dot {
    position: absolute;
    bottom: -3px; right: -3px;
    background: var(--status-warning);
    color: #1a1a1a;
    font-size: 0.6rem;
    font-weight: 700;
    min-width: 16px;
    height: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 2px;
    border-radius: 8px;
    padding: 0 4px;
  }
  .problem-dot i { font-size: 0.55rem; }

  .problem-section {
    margin-top: 6px;
    border-top: 1px solid var(--border-primary);
    padding-top: 6px;
  }
  .problem-header {
    display: flex;
    align-items: center;
    gap: 6px;
    width: 100%;
    background: none;
    border: none;
    padding: 4px 6px;
    font-size: 0.75rem;
    color: var(--status-warning);
    cursor: pointer;
    text-align: left;
    border-radius: 4px;
  }
  .problem-header:hover { background: rgba(255, 152, 0, 0.08); }
  .problem-header i { font-size: 0.7rem; }
  .problem-hint { color: var(--text-quaternary, #64748b); font-size: 0.65rem; margin-left: auto; }

  .problem-body {
    margin-top: 4px;
    padding: 6px;
    background: rgba(255, 152, 0, 0.04);
    border-radius: 6px;
    border-left: 2px solid var(--status-warning);
  }
  .problem-loading, .problem-empty {
    font-size: 0.75rem; color: var(--text-tertiary); padding: 4px; text-align: center;
  }
  .problem-actions { display: flex; justify-content: flex-end; margin-bottom: 6px; }
  .btn-retry-all {
    font-size: 0.7rem;
    padding: 4px 8px;
    border-radius: 4px;
    background: var(--accent-muted, rgba(59,130,246,0.1));
    color: var(--accent-primary);
    border: 1px solid var(--accent-primary);
    cursor: pointer;
  }
  .btn-retry-all:hover { background: var(--accent-primary); color: #fff; }

  .problem-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 4px; }
  .problem-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px;
    border-radius: 4px;
    background: var(--bg-secondary);
  }
  .problem-thumb {
    width: 48px; height: 27px; object-fit: cover; border-radius: 3px; flex-shrink: 0;
    background: var(--bg-primary);
  }
  .problem-thumb.placeholder { background: var(--bg-primary); border: 1px dashed var(--border-primary); }
  .problem-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .problem-title {
    font-size: 0.75rem; color: var(--text-primary); text-decoration: none;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .problem-title:hover { color: var(--accent-primary); text-decoration: underline; }
  .problem-reason {
    font-size: 0.65rem;
    color: var(--status-warning);
    display: inline-flex; gap: 3px; align-items: center;
  }
  .problem-item-actions { display: flex; gap: 3px; flex-shrink: 0; }
  .btn-xs {
    border: none; background: var(--bg-primary); color: var(--text-secondary);
    width: 24px; height: 24px; border-radius: 4px; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.7rem;
  }
  .btn-retry:hover { background: var(--accent-primary); color: #fff; }
  .btn-dismiss:hover { background: var(--status-error); color: #fff; }
</style>

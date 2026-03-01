<!--
  TubeVault
  © HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
  SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
-->
<script>
  import { api } from '../lib/api/client.js';
  import { route, navigate, updateParams } from '../lib/router/router.js';
  import { toast } from '../lib/stores/notifications.js';
  import { getSettingNum } from '../lib/stores/settings.js';
  import { formatDuration, formatDate } from '../lib/utils/format.js';
  import MultiFilter from '../lib/components/common/MultiFilter.svelte';

  let history = $state([]);
  let total = $state(0);
  let page = $state(1);
  let hasMore = $state(false);
  let loading = $state(true);
  let loadingMore = $state(false);
  const PER_PAGE = getSettingNum('general.videos_per_page', 24);

  let histFilter = $state({ types: null, channels: null, search: null });
  let sentinelEl = $state(null);
  let observer = null;

  async function loadHistory(reset = true) {
    if (reset) { page = 1; history = []; loading = true; }
    else { loadingMore = true; }
    try {
      const params = { page, per_page: PER_PAGE };
      if (histFilter.search) params.search = histFilter.search;
      if (histFilter.types) params.video_types = histFilter.types;
      if (histFilter.channels) params.channel_ids = histFilter.channels;
      const res = await api.getHistory(params);
      const newVids = res.videos || [];
      if (reset) history = newVids; else history = [...history, ...newVids];
      total = res.total || 0;
      hasMore = history.length < total;
    } catch { toast.error('Verlauf konnte nicht geladen werden'); }
    finally { loading = false; loadingMore = false; }
  }

  function loadMore() {
    if (loadingMore || !hasMore) return;
    page += 1;
    loadHistory(false);
  }

  function onHistFilterChange(f) {
    histFilter = f;
    updateParams({
      types: f.types || null,
      channels: f.channels || null,
      search: f.search || null,
    });
    loadHistory();
  }

  async function clearAll() {
    try { await api.clearHistory(); history = []; total = 0; toast.success('Verlauf gelöscht'); }
    catch (e) { toast.error(e.message); }
  }

  function playVideo(id) { navigate(`/watch/${id}`); }

  function progressPercent(v) {
    if (!v.duration || v.duration <= 0) return 0;
    return Math.min(100, Math.round(((v.last_position || v.history_position || 0) / v.duration) * 100));
  }
  function isInProgress(v) {
    const pos = v.last_position || v.history_position || 0;
    return pos > 5 && v.duration && pos < v.duration - 10;
  }

  $effect(() => {
    // URL-Params lesen
    const p = $route?.params || {};
    if (p.types) histFilter = { ...histFilter, types: p.types };
    if (p.channels) histFilter = { ...histFilter, channels: p.channels };
    if (p.search) histFilter = { ...histFilter, search: p.search };
    loadHistory();
  });

  // IntersectionObserver
  $effect(() => {
    if (sentinelEl) {
      observer?.disconnect();
      observer = new IntersectionObserver(es => { if (es[0]?.isIntersecting) loadMore(); }, { rootMargin: '400px' });
      observer.observe(sentinelEl);
    }
    return () => observer?.disconnect();
  });
</script>

<div class="history-page">
  <div class="page-header">
    <div class="header-left">
      <h1>Verlauf</h1>
      <span class="count">{total} Video{total !== 1 ? 's' : ''}</span>
    </div>
    {#if history.length > 0}
      <button class="btn-clear" onclick={clearAll}>Verlauf löschen</button>
    {/if}
  </div>

  <MultiFilter showSearch={true} showTypes={true} showChannels={true} showCategories={false} onchange={onHistFilterChange} />

  {#if history.filter(isInProgress).length > 0}
    <section class="continue-section">
      <h2 class="section-title">Weiterschauen</h2>
      <div class="continue-grid">
        {#each history.filter(isInProgress) as v}
          <button class="continue-card" onclick={() => playVideo(v.id)}>
            <div class="continue-thumb">
              <img src={api.thumbnailUrl(v.id)} alt="" loading="lazy" />
              <div class="progress-bar"><div class="progress-fill" style="width:{progressPercent(v)}%"></div></div>
              <div class="resume-time">{formatDuration(v.last_position || v.history_position || 0)} / {formatDuration(v.duration)}</div>
            </div>
            <div class="continue-info">
              <span class="continue-title">{v.title}</span>
              <span class="continue-channel">{v.channel_name || 'Unbekannt'}</span>
            </div>
          </button>
        {/each}
      </div>
    </section>
  {/if}

  {#if loading}
    <div class="loading">Lade Verlauf…</div>
  {:else if history.length === 0}
    <div class="empty">
      <div class="empty-icon"><i class="fa-solid fa-clock-rotate-left"></i></div>
      <p>Noch keine Videos angesehen</p>
    </div>
  {:else}
    <div class="history-list">
      {#each history as v}
        <button class="history-item" onclick={() => playVideo(v.id)}>
          <div class="thumb-wrap">
            <img src={api.thumbnailUrl(v.id)} alt="" loading="lazy" />
            {#if v.duration}<span class="duration">{formatDuration(v.duration)}</span>{/if}
            {#if isInProgress(v)}<div class="thumb-progress"><div class="thumb-progress-fill" style="width:{progressPercent(v)}%"></div></div>{/if}
          </div>
          <div class="item-info">
            <span class="item-title">{v.title}</span>
            <span class="item-channel">{v.channel_name || 'Unbekannt'}</span>
            <div class="item-meta">
              <span>{formatDate(v.last_watched || v.last_played)}</span>
              {#if v.play_count > 1}<span class="dot">·</span><span>{v.play_count}× abgespielt</span>{/if}
              {#if v.completed || (v.last_position === 0 && v.play_count > 0)}
                <span class="badge-done"><i class="fa-solid fa-check"></i> Gesehen</span>
              {:else if isInProgress(v)}
                <span class="badge-progress">{progressPercent(v)}%</span>
              {/if}
            </div>
          </div>
        </button>
      {/each}
    </div>
    <div bind:this={sentinelEl} class="scroll-sentinel"></div>
    {#if loadingMore}<div class="loading-more"><i class="fa-solid fa-spinner fa-spin"></i> Lade mehr…</div>{/if}
  {/if}
</div>

<style>
  .history-page { padding:0 24px 24px; max-width:1100px; }
  .page-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:20px; flex-wrap:wrap; gap:12px; }
  .header-left { display:flex; align-items:baseline; gap:10px; }
  .page-header h1 { font-size:1.4rem; font-weight:700; color:var(--text-primary); margin:0; }
  .count { font-size:0.85rem; color:var(--text-tertiary); }
  .btn-clear { padding:7px 16px; background:none; border:1px solid var(--border-primary); border-radius:8px; color:var(--text-secondary); font-size:0.82rem; cursor:pointer; }
  .btn-clear:hover { border-color:var(--status-error); color:var(--status-error); }

  .continue-section { margin-bottom:28px; }
  .section-title { font-size:1rem; font-weight:600; color:var(--text-primary); margin:0 0 12px; }
  .continue-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:14px; }
  .continue-card { background:var(--bg-secondary); border:1px solid var(--border-primary); border-radius:10px; overflow:hidden; cursor:pointer; text-align:left; transition:all 0.15s; }
  .continue-card:hover { border-color:var(--accent-primary); transform:translateY(-1px); }
  .continue-thumb { position:relative; aspect-ratio:16/9; overflow:hidden; }
  .continue-thumb img { width:100%; height:100%; object-fit:cover; }
  .progress-bar { position:absolute; bottom:0; left:0; right:0; height:4px; background:rgba(255,255,255,0.2); }
  .progress-fill { height:100%; background:var(--accent-primary); border-radius:0 2px 2px 0; }
  .resume-time { position:absolute; bottom:8px; right:8px; background:rgba(0,0,0,0.8); color:#fff; font-size:0.7rem; padding:2px 6px; border-radius:4px; font-weight:500; }
  .continue-info { padding:10px 12px; }
  .continue-title { display:block; font-size:0.85rem; font-weight:600; color:var(--text-primary); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .continue-channel { font-size:0.76rem; color:var(--text-tertiary); }

  .history-list { display:flex; flex-direction:column; gap:2px; }
  .history-item { display:flex; gap:14px; padding:10px 12px; background:none; border:none; cursor:pointer; text-align:left; transition:background 0.12s; }
  .history-item:hover { background:var(--bg-secondary); }
  .thumb-wrap { position:relative; width:168px; min-width:168px; aspect-ratio:16/9; border-radius:8px; overflow:hidden; background:var(--bg-tertiary); }
  .thumb-wrap img { width:100%; height:100%; object-fit:cover; }
  .duration { position:absolute; bottom:6px; right:6px; background:rgba(0,0,0,0.8); color:#fff; font-size:0.7rem; padding:1px 5px; border-radius:3px; font-weight:500; }
  .thumb-progress { position:absolute; bottom:0; left:0; right:0; height:3px; background:rgba(255,255,255,0.2); }
  .thumb-progress-fill { height:100%; background:var(--accent-primary); }
  .item-info { display:flex; flex-direction:column; gap:3px; min-width:0; padding:2px 0; }
  .item-title { font-size:0.9rem; font-weight:600; color:var(--text-primary); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .item-channel { font-size:0.8rem; color:var(--text-secondary); }
  .item-meta { display:flex; align-items:center; gap:6px; font-size:0.76rem; color:var(--text-tertiary); margin-top:2px; }
  .dot { color:var(--text-tertiary); }
  .badge-done { background:var(--status-success); color:#fff; font-size:0.68rem; padding:1px 6px; border-radius:4px; font-weight:600; }
  .badge-progress { background:var(--accent-primary); color:#fff; font-size:0.68rem; padding:1px 6px; border-radius:4px; font-weight:600; }

  .scroll-sentinel { height:1px; }
  .loading-more { text-align:center; padding:16px; color:var(--text-tertiary); font-size:0.82rem; }
  .loading, .empty { display:flex; flex-direction:column; align-items:center; padding:60px 20px; color:var(--text-tertiary); font-size:0.9rem; }
  .empty-icon { font-size:2.5rem; margin-bottom:12px; }
</style>

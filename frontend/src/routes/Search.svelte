<!--
  TubeVault – Search v1.0.0
  Eigene Suchseite mit YouTube-Suche, Paginierung, großen Thumbs,
  Block-Button und lokaler Bibliotheks-Suche.
  © HalloWelt42 – Private Nutzung
-->
<script>
  import { api } from '../lib/api/client.js';
  import { route, navigate, updateParams } from '../lib/router/router.js';
  import { toast } from '../lib/stores/notifications.js';
  import { formatDuration, formatViews } from '../lib/utils/format.js';
  import QuickPlaylistBtn from '../lib/components/common/QuickPlaylistBtn.svelte';
  import HoverActionOverlay from '../lib/components/common/HoverActionOverlay.svelte';
  import HoverActionBtn from '../lib/components/common/HoverActionBtn.svelte';

  let query = $state($route.params.q || '');
  let scope = $state($route.params.scope || 'both'); // 'both' | 'local' | 'youtube'
  let loading = $state(false);
  let loadingMore = $state(false);
  let page = $state(1);
  let perPage = 20;
  let hasMore = $state(false);
  let ytVideos = $state([]);
  let ytShorts = $state([]);
  let ytChannels = $state([]);
  let localVideos = $state([]);
  let subscribedIds = $state(new Set());
  let downloading = $state(new Set());

  async function loadSubs() {
    try {
      const res = await api.getSubscriptions();
      subscribedIds = new Set((res.subscriptions || res || []).map(s => s.channel_id));
    } catch {}
  }

  async function runSearch(reset = true) {
    if (!query.trim()) return;
    if (reset) { page = 1; ytVideos = []; ytShorts = []; ytChannels = []; localVideos = []; loading = true; }
    else { loadingMore = true; }
    updateParams({ q: query, scope: scope !== 'both' ? scope : null });
    try {
      // Lokal
      if (scope !== 'youtube' && reset) {
        try {
          const r = await api.searchLocal(query, { per_page: 12 });
          localVideos = r.videos || [];
        } catch { localVideos = []; }
      }
      // YouTube mit Paginierung
      if (scope !== 'local') {
        const r = await api.searchYouTubePaged(query, page, perPage);
        const newVids = r.videos || [];
        ytVideos = reset ? newVids : [...ytVideos, ...newVids];
        if (reset) {
          ytShorts = r.shorts || [];
          ytChannels = r.channels || [];
        }
        hasMore = r.has_more || newVids.length >= perPage;
      }
    } catch (e) { toast.error(e.message); }
    finally { loading = false; loadingMore = false; }
  }

  function loadMore() {
    if (loadingMore || !hasMore) return;
    page += 1;
    runSearch(false);
  }

  function onSubmit(e) { e.preventDefault(); runSearch(true); }

  async function subscribe(v, e) {
    e.stopPropagation();
    try {
      await api.addSubscription({ channel_id: v.channel_id, channel_name: v.channel_name });
      subscribedIds = new Set([...subscribedIds, v.channel_id]);
      toast.success(`„${v.channel_name}" abonniert`);
    } catch (err) { toast.error(err.message); }
  }

  async function blockCh(v, e) {
    e.stopPropagation();
    if (!confirm(`Kanal „${v.channel_name}" aus YT-Suche ausblenden?`)) return;
    try {
      await api.blockChannel(v.channel_id, v.channel_name);
      ytVideos = ytVideos.filter(r => r.channel_id !== v.channel_id);
      ytShorts = ytShorts.filter(r => r.channel_id !== v.channel_id);
      toast.success(`„${v.channel_name}" blockiert`);
    } catch (err) { toast.error(err.message); }
  }

  async function quickDl(v, e) {
    e.stopPropagation();
    if (downloading.has(v.id)) return;
    downloading = new Set([...downloading, v.id]);
    try {
      await api.addDownload({ url: `https://www.youtube.com/watch?v=${v.id}` });
      v.already_in_queue = true;
      ytVideos = [...ytVideos];
      toast.success('Zur Queue hinzugefügt');
    } catch (err) { toast.error(err.message); }
    downloading = new Set([...downloading].filter(id => id !== v.id));
  }

  function openVideo(id) { navigate(`/watch/${id}`); }
  function openChannel(id) { navigate(`/channel/${id}`); }

  $effect(() => { loadSubs(); });
  $effect(() => {
    const q = $route.params.q;
    if (q && q !== query) { query = q; runSearch(true); }
    else if (q && ytVideos.length === 0 && !loading) { runSearch(true); }
  });
</script>

<div class="search-page">
  <div class="page-header">
    <h1 class="page-title"><i class="fa-solid fa-magnifying-glass"></i> Suche</h1>
  </div>

  <form class="search-form" onsubmit={onSubmit}>
    <div class="search-input-wrap">
      <i class="fa-solid fa-magnifying-glass search-icon"></i>
      <input type="text" class="search-input" placeholder="Bibliothek + YouTube durchsuchen…"
             bind:value={query} autofocus />
      {#if query}<button type="button" class="search-clear" onclick={() => { query = ''; ytVideos = []; localVideos = []; }}><i class="fa-solid fa-xmark"></i></button>{/if}
    </div>
    <div class="search-scope">
      {#each [['both','Beides'],['local','Bibliothek'],['youtube','YouTube']] as [id, label]}
        <button type="button" class="scope-btn" class:active={scope === id}
                onclick={() => { scope = id; runSearch(true); }}>{label}</button>
      {/each}
    </div>
    <button type="submit" class="btn-primary" disabled={!query.trim() || loading}>
      {#if loading}<i class="fa-solid fa-spinner fa-spin"></i>{:else}Suchen{/if}
    </button>
  </form>

  {#if loading && ytVideos.length === 0 && localVideos.length === 0}
    <div class="loading"><i class="fa-solid fa-spinner fa-spin"></i> Suche läuft…</div>
  {:else if query && ytVideos.length === 0 && localVideos.length === 0 && !loading}
    <div class="empty"><i class="fa-solid fa-magnifying-glass"></i><h3>Keine Treffer für „{query}"</h3></div>
  {/if}

  <!-- Lokale Ergebnisse -->
  {#if scope !== 'youtube' && localVideos.length > 0}
    <section class="section">
      <h2 class="section-title"><i class="fa-solid fa-photo-film"></i> Bibliothek ({localVideos.length})</h2>
      <div class="grid">
        {#each localVideos as v (v.id)}
          <div class="card-wrap">
            <div class="video-card" role="button" tabindex="0"
                 onclick={() => openVideo(v.id)}
                 onkeydown={(e) => e.key === 'Enter' && openVideo(v.id)}>
              <div class="thumb-wrap">
                <img src={api.thumbnailUrl(v.id)} alt="" loading="lazy" />
                {#if v.duration}<span class="duration">{formatDuration(v.duration)}</span>{/if}
                <HoverActionOverlay>
                  <HoverActionBtn variant="success" onclick={() => openVideo(v.id)} title="Abspielen">
                    <i class="fa-solid fa-play"></i>
                  </HoverActionBtn>
                </HoverActionOverlay>
              </div>
              <div class="info">
                <h3 class="title">{v.title}</h3>
                <span class="channel">{v.channel_name || '–'}</span>
              </div>
            </div>
          </div>
        {/each}
      </div>
    </section>
  {/if}

  <!-- YouTube-Kanäle -->
  {#if scope !== 'local' && ytChannels.length > 0}
    <section class="section">
      <h2 class="section-title"><i class="fa-solid fa-tv"></i> Kanäle ({ytChannels.length})</h2>
      <div class="ch-grid">
        {#each ytChannels.slice(0, 6) as c (c.id)}
          <button class="ch-card" onclick={() => openChannel(c.id)}>
            {#if c.thumbnail_url}<img src={c.thumbnail_url} alt="" loading="lazy" />{:else}<div class="ch-ph"><i class="fa-solid fa-user"></i></div>{/if}
            <span class="ch-name">{c.name}</span>
            {#if c.subscriber_count}<span class="ch-subs">{formatViews(c.subscriber_count)} Abos</span>{/if}
          </button>
        {/each}
      </div>
    </section>
  {/if}

  <!-- YouTube-Videos -->
  {#if scope !== 'local' && ytVideos.length > 0}
    <section class="section">
      <h2 class="section-title"><i class="fa-brands fa-youtube"></i> YouTube ({ytVideos.length}{hasMore ? '+' : ''})</h2>
      <div class="grid">
        {#each ytVideos as v (v.id)}
          <div class="card-wrap" class:already={v.already_downloaded} class:queued={v.already_in_queue}>
            <div class="video-card" role="button" tabindex="0"
                 onclick={() => openVideo(v.id)}
                 onkeydown={(e) => e.key === 'Enter' && openVideo(v.id)}>
              <div class="thumb-wrap">
                <img src={v.already_downloaded ? api.thumbnailUrl(v.id) : api.rssThumbUrl(v.id)} alt="" loading="lazy" />
                {#if v.duration}<span class="duration">{formatDuration(v.duration)}</span>{/if}
                {#if v.already_downloaded}<span class="badge ok">Lokal</span>
                {:else if v.already_in_queue}<span class="badge queue">In Queue</span>{/if}
                <HoverActionOverlay>
                  {#if v.already_downloaded}
                    <HoverActionBtn variant="success" onclick={() => openVideo(v.id)} title="Abspielen">
                      <i class="fa-solid fa-play"></i>
                    </HoverActionBtn>
                  {:else if v.already_in_queue}
                    <HoverActionBtn variant="accent" disabled title="Bereits in Warteschlange">
                      <i class="fa-solid fa-clock"></i>
                    </HoverActionBtn>
                  {:else}
                    <HoverActionBtn variant="accent" onclick={(e) => quickDl(v, e)}
                                    disabled={downloading.has(v.id)} title="Herunterladen">
                      <i class="fa-solid fa-download"></i>
                    </HoverActionBtn>
                  {/if}
                  <QuickPlaylistBtn videoId={v.id} title={v.title} channelName={v.channel_name} channelId={v.channel_id} size="sm" />
                  <HoverActionBtn variant="danger" onclick={(e) => blockCh(v, e)} title="Kanal blockieren">
                    <i class="fa-solid fa-ban"></i>
                  </HoverActionBtn>
                </HoverActionOverlay>
              </div>
              <div class="info">
                <h3 class="title">{v.title}</h3>
                <div class="ch-row">
                  <button class="channel-btn" onclick={(e) => { e.stopPropagation(); openChannel(v.channel_id); }}>{v.channel_name || '–'}</button>
                  {#if v.channel_id && !subscribedIds.has(v.channel_id)}
                    <button class="sub-btn" onclick={(e) => subscribe(v, e)} title="Abonnieren">
                      <i class="fa-solid fa-rss"></i>
                    </button>
                  {:else if subscribedIds.has(v.channel_id)}
                    <span class="sub-ok" title="Abonniert"><i class="fa-solid fa-check"></i></span>
                  {/if}
                </div>
                {#if v.view_count}<span class="meta">{formatViews(v.view_count)} Aufrufe</span>{/if}
              </div>
            </div>
          </div>
        {/each}
      </div>
      {#if hasMore}
        <button class="load-more" onclick={loadMore} disabled={loadingMore}>
          {#if loadingMore}<i class="fa-solid fa-spinner fa-spin"></i> Lade…{:else}Weitere Treffer (Seite {page + 1}){/if}
        </button>
      {/if}
    </section>
  {/if}
</div>

<style>
  .search-page { padding: 24px; max-width: 1400px; }
  .search-form { display: flex; gap: 10px; align-items: center; margin-bottom: 20px; flex-wrap: wrap; }
  .search-input-wrap { flex: 1; min-width: 280px; position: relative; display: flex; align-items: center; }
  .search-icon { position: absolute; left: 14px; color: var(--text-tertiary); font-size: 0.9rem; pointer-events: none; }
  .search-input { flex: 1; padding: 10px 36px 10px 38px; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 10px; color: var(--text-primary); font-size: 0.95rem; outline: none; }
  .search-input:focus { border-color: var(--accent-primary); }
  .search-clear { position: absolute; right: 10px; background: none; border: none; color: var(--text-tertiary); cursor: pointer; padding: 4px; }
  .search-clear:hover { color: var(--status-error); }

  .search-scope { display: flex; gap: 4px; }
  .scope-btn { padding: 8px 14px; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 8px; color: var(--text-secondary); font-size: 0.82rem; cursor: pointer; }
  .scope-btn.active { background: var(--accent-primary); color: #fff; border-color: var(--accent-primary); }

  .loading, .empty { display: flex; flex-direction: column; align-items: center; padding: 60px 20px; color: var(--text-tertiary); }
  .empty i { font-size: 2.5rem; opacity: 0.4; margin-bottom: 12px; }

  .section { margin-bottom: 32px; }
  .section-title { font-size: 1rem; font-weight: 700; color: var(--text-primary); margin: 0 0 12px; display: flex; align-items: center; gap: 8px; }

  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
  .card-wrap { position: relative; }
  .video-card { display: flex; flex-direction: column; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 12px; overflow: hidden; cursor: pointer; transition: all 0.15s; text-align: left; color: inherit; }
  .video-card:hover { border-color: var(--accent-primary); transform: translateY(-2px); }
  .card-wrap.queued .video-card { border-color: var(--status-warning, #f59e0b); }
  .card-wrap.already .video-card { border-color: var(--status-success); }

  .thumb-wrap { position: relative; aspect-ratio: 16/9; background: var(--bg-tertiary); overflow: hidden; }
  .thumb-wrap img { width: 100%; height: 100%; object-fit: cover; }
  .duration { position: absolute; bottom: 8px; right: 8px; background: rgba(0,0,0,0.8); color: #fff; padding: 2px 6px; border-radius: 4px; font-size: 0.72rem; font-family: monospace; }
  .badge { position: absolute; top: 8px; left: 8px; padding: 3px 8px; border-radius: 4px; font-size: 0.68rem; font-weight: 700; text-transform: uppercase; }
  .badge.ok { background: var(--status-success); color: #fff; }
  .badge.queue { background: var(--status-warning, #f59e0b); color: #fff; }

  .info { padding: 12px; display: flex; flex-direction: column; gap: 4px; }
  .title { font-size: 0.9rem; font-weight: 600; color: var(--text-primary); margin: 0; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; line-height: 1.3; }
  .ch-row { display: flex; align-items: center; gap: 6px; }
  .channel-btn { background: none; border: none; padding: 0; color: var(--text-secondary); font-size: 0.8rem; cursor: pointer; text-align: left; }
  .channel-btn:hover { color: var(--accent-primary); text-decoration: underline; }
  .sub-btn { background: none; border: 1px solid var(--border-primary); color: var(--text-tertiary); padding: 2px 6px; border-radius: 5px; cursor: pointer; font-size: 0.7rem; }
  .sub-btn:hover { border-color: var(--accent-primary); color: var(--accent-primary); }
  .sub-ok { color: var(--status-success); font-size: 0.72rem; }
  .meta { font-size: 0.75rem; color: var(--text-tertiary); }

  .ch-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; }
  .ch-card { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 12px; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 10px; cursor: pointer; }
  .ch-card:hover { border-color: var(--accent-primary); }
  .ch-card img, .ch-ph { width: 56px; height: 56px; border-radius: 50%; object-fit: cover; background: var(--bg-tertiary); display: flex; align-items: center; justify-content: center; color: var(--text-tertiary); }
  .ch-name { font-size: 0.8rem; font-weight: 600; color: var(--text-primary); text-align: center; }
  .ch-subs { font-size: 0.68rem; color: var(--text-tertiary); }

  .load-more { display: block; margin: 16px auto; padding: 10px 24px; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 8px; color: var(--text-secondary); cursor: pointer; font-size: 0.85rem; }
  .load-more:hover { border-color: var(--accent-primary); color: var(--text-primary); }
</style>

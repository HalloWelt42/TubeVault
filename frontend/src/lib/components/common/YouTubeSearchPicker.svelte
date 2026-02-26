<!--
  TubeVault – YouTubeSearchPicker v1.5.64
  Wiederverwendbare YT-Such-Komponente für Link-Dialoge.
  © HalloWelt42 – Private Nutzung
-->
<script>
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';
  import { formatDuration } from '../../utils/format.js';

  let { initialQuery = '', onSelect = () => {} } = $props();

  let query = $state('');
  let results = $state([]);
  let loading = $state(false);
  let searched = $state(false);

  $effect(() => {
    if (initialQuery && !searched) {
      query = initialQuery;
      search();
    }
  });

  async function search() {
    if (!query.trim()) return;
    loading = true;
    searched = true;
    try {
      const res = await api.searchYouTube(query.trim(), 12);
      results = res.results || res || [];
    } catch (e) {
      toast.error('YT-Suche fehlgeschlagen: ' + e.message);
    }
    loading = false;
  }

  function select(v) {
    onSelect({
      id: v.id, title: v.title, channel_name: v.channel_name,
      channel_id: v.channel_id, duration: v.duration,
      thumbnail_url: v.thumbnail_url, already_downloaded: v.already_downloaded,
    });
  }
</script>

<div class="ytp">
  <div class="ytp-bar">
    <input class="ytp-input" type="text" bind:value={query}
      placeholder="YouTube durchsuchen…"
      onkeydown={(e) => e.key === 'Enter' && search()}>
    <button class="ytp-btn" onclick={search} disabled={loading || !query.trim()}>
      {#if loading}<i class="fa-solid fa-spinner fa-spin"></i>{:else}<i class="fa-solid fa-magnifying-glass"></i> Suchen{/if}
    </button>
  </div>

  <div class="ytp-list">
    {#if loading}
      <p class="ytp-msg"><i class="fa-solid fa-spinner fa-spin"></i> Suche auf YouTube…</p>
    {:else if results.length > 0}
      {#each results as v (v.id)}
        <div class="ytp-row" class:ytp-exists={v.already_downloaded}>
          <div class="ytp-thumb">
            {#if v.id}<img src={api.rssThumbUrl(v.id)} alt="" loading="lazy">
            {:else}<i class="fa-solid fa-film ytp-ph"></i>{/if}
            {#if v.duration}<span class="ytp-dur">{formatDuration(v.duration)}</span>{/if}
          </div>
          <div class="ytp-info">
            <div class="ytp-title">{v.title}</div>
            <div class="ytp-meta">
              <span class="ytp-ch"><i class="fa-solid fa-user"></i> {v.channel_name || 'Unbekannt'}</span>
              <span class="ytp-id">{v.id}</span>
            </div>
            {#if v.already_downloaded}<span class="ytp-tag-local"><i class="fa-solid fa-check"></i> Im Vault</span>{/if}
          </div>
          <button class="ytp-select" onclick={() => select(v)} disabled={v.already_downloaded}>
            {v.already_downloaded ? '✓' : 'Übernehmen'}
          </button>
        </div>
      {/each}
    {:else if searched}
      <p class="ytp-msg"><i class="fa-solid fa-inbox"></i> Keine Ergebnisse.</p>
    {:else}
      <p class="ytp-msg"><i class="fa-brands fa-youtube"></i> YouTube-Suche — Suchbegriff eingeben.</p>
    {/if}
  </div>
</div>

<style>
  .ytp { display: flex; flex-direction: column; }
  .ytp-bar { display: flex; gap: 8px; padding: 10px 0; }
  .ytp-input { flex: 1; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 6px; padding: 7px 12px; color: var(--text-primary); font-size: 0.85rem; }
  .ytp-input:focus { outline: none; border-color: var(--accent-primary); }
  .ytp-btn { padding: 7px 14px; background: var(--accent-primary); color: #fff; border: none; border-radius: 6px; font-size: 0.82rem; font-weight: 600; cursor: pointer; white-space: nowrap; display: inline-flex; align-items: center; gap: 5px; }
  .ytp-btn:hover { background: var(--accent-hover); }
  .ytp-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .ytp-list { overflow-y: auto; max-height: 400px; }
  .ytp-msg { text-align: center; color: var(--text-tertiary); font-size: 0.82rem; padding: 24px 0; display: flex; align-items: center; justify-content: center; gap: 8px; }
  .ytp-row { display: flex; align-items: center; gap: 10px; padding: 8px 4px; border-bottom: 1px solid var(--border-secondary); transition: background 0.1s; }
  .ytp-row:hover { background: var(--bg-hover); } .ytp-row:last-child { border-bottom: none; }
  .ytp-exists { opacity: 0.45; }
  .ytp-thumb { width: 96px; height: 54px; background: var(--bg-tertiary); border-radius: 4px; flex-shrink: 0; overflow: hidden; position: relative; display: flex; align-items: center; justify-content: center; }
  .ytp-thumb img { width: 100%; height: 100%; object-fit: cover; }
  .ytp-ph { font-size: 1rem; color: var(--text-tertiary); }
  .ytp-dur { position: absolute; bottom: 2px; right: 3px; background: rgba(0,0,0,0.85); color: #fff; font-size: 0.6rem; padding: 0 4px; border-radius: 2px; }
  .ytp-info { flex: 1; min-width: 0; }
  .ytp-title { font-size: 0.82rem; font-weight: 600; color: var(--text-primary); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .ytp-meta { display: flex; gap: 8px; margin-top: 2px; font-size: 0.7rem; color: var(--text-tertiary); }
  .ytp-ch { color: var(--text-secondary); display: flex; align-items: center; gap: 3px; }
  .ytp-id { font-family: monospace; }
  .ytp-tag-local { font-size: 0.68rem; color: var(--status-success); font-weight: 600; display: flex; align-items: center; gap: 3px; }
  .ytp-select { padding: 5px 12px; background: rgba(34,197,94,0.1); color: var(--status-success); border: 1px solid rgba(34,197,94,0.25); border-radius: 6px; font-size: 0.78rem; font-weight: 600; cursor: pointer; white-space: nowrap; flex-shrink: 0; }
  .ytp-select:hover { background: rgba(34,197,94,0.2); }
  .ytp-select:disabled { opacity: 0.4; cursor: not-allowed; }
</style>

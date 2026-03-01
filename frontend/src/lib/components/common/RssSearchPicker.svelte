<!--
  TubeVault -  RssSearchPicker v1.5.64
  Durchsucht lokale RSS-Feeds nach Videos.
  © HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
  SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
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
      const res = await api.searchRss(query.trim());
      results = res.results || [];
    } catch (e) {
      toast.error('RSS-Suche fehlgeschlagen: ' + e.message);
    }
    loading = false;
  }

  function select(r) {
    onSelect({
      id: r.video_id, title: r.title,
      channel_name: r.channel_name, channel_id: r.channel_id,
      duration: r.duration,
    });
  }
</script>

<div class="rsp">
  <div class="rsp-bar">
    <input class="rsp-input" type="text" bind:value={query}
      placeholder="In RSS-Feeds suchen (Titel, Kanal, ID)…"
      onkeydown={(e) => e.key === 'Enter' && search()}>
    <button class="rsp-btn" onclick={search} disabled={loading || !query.trim()}>
      {#if loading}<i class="fa-solid fa-spinner fa-spin"></i>{:else}<i class="fa-solid fa-magnifying-glass"></i>{/if}
    </button>
  </div>

  <div class="rsp-list">
    {#if loading}
      <p class="rsp-msg"><i class="fa-solid fa-spinner fa-spin"></i> Suche in RSS-Feeds…</p>
    {:else if results.length > 0}
      {#each results as r}
        <div class="rsp-row" class:rsp-exists={r.in_library}>
          <div class="rsp-info">
            <div class="rsp-title">{r.title}</div>
            <div class="rsp-meta">
              <span class="rsp-ch"><i class="fa-solid fa-tv"></i> {r.channel_name || '—'}</span>
              <span class="rsp-id">{r.video_id}</span>
              {#if r.duration}<span><i class="fa-solid fa-clock"></i> {formatDuration(r.duration)}</span>{/if}
              {#if r.published}<span>{r.published.slice(0, 10)}</span>{/if}
            </div>
            {#if r.in_library}<span class="rsp-tag"><i class="fa-solid fa-check"></i> Im Vault</span>{/if}
          </div>
          <button class="rsp-select" onclick={() => select(r)} disabled={r.in_library}>
            {r.in_library ? '✓' : 'Übernehmen'}
          </button>
        </div>
      {/each}
    {:else if searched}
      <p class="rsp-msg"><i class="fa-solid fa-inbox"></i> Keine RSS-Treffer. Wechsle zu YouTube-Suche.</p>
    {:else}
      <p class="rsp-msg"><i class="fa-solid fa-rss"></i> Durchsucht abonnierte RSS-Feeds (lokal, schnell).</p>
    {/if}
  </div>
</div>

<style>
  .rsp { display: flex; flex-direction: column; }
  .rsp-bar { display: flex; gap: 8px; padding: 10px 0; }
  .rsp-input { flex: 1; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 6px; padding: 7px 12px; color: var(--text-primary); font-size: 0.85rem; }
  .rsp-input:focus { outline: none; border-color: var(--accent-primary); }
  .rsp-btn { padding: 7px 14px; background: var(--accent-primary); color: #fff; border: none; border-radius: 6px; font-size: 0.82rem; font-weight: 600; cursor: pointer; }
  .rsp-btn:hover { background: var(--accent-hover); }
  .rsp-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .rsp-list { overflow-y: auto; max-height: 400px; }
  .rsp-msg { text-align: center; color: var(--text-tertiary); font-size: 0.82rem; padding: 24px 0; display: flex; align-items: center; justify-content: center; gap: 8px; }
  .rsp-row { display: flex; align-items: center; gap: 10px; padding: 8px 4px; border-bottom: 1px solid var(--border-secondary); }
  .rsp-row:hover { background: var(--bg-hover); } .rsp-row:last-child { border-bottom: none; }
  .rsp-exists { opacity: 0.45; }
  .rsp-info { flex: 1; min-width: 0; }
  .rsp-title { font-size: 0.82rem; font-weight: 600; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .rsp-meta { display: flex; gap: 8px; margin-top: 2px; font-size: 0.7rem; color: var(--text-tertiary); flex-wrap: wrap; }
  .rsp-ch { color: var(--accent-primary); display: flex; align-items: center; gap: 3px; }
  .rsp-id { font-family: monospace; }
  .rsp-tag { font-size: 0.68rem; color: var(--status-success); font-weight: 600; display: flex; align-items: center; gap: 3px; }
  .rsp-select { padding: 5px 12px; background: rgba(34,197,94,0.1); color: var(--status-success); border: 1px solid rgba(34,197,94,0.25); border-radius: 6px; font-size: 0.78rem; font-weight: 600; cursor: pointer; white-space: nowrap; flex-shrink: 0; }
  .rsp-select:hover { background: rgba(34,197,94,0.2); }
  .rsp-select:disabled { opacity: 0.4; cursor: not-allowed; }
</style>

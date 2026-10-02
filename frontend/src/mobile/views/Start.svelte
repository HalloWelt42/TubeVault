<!-- Start: angefangene Videos fortsetzen, zuletzt Geladenes ansehen. -->
<script>
  import { api, FE_VERSION } from '../../lib/api/client.js';
  import { go } from '../router.js';
  import VideoRow from '../parts/VideoRow.svelte';

  const DESKTOP_FLAG = 'tv_volle_ansicht';
  const MIN_STARTED_S = 30;
  const NEAR_END_S = 20;

  let started = $state([]);
  let latest = $state([]);
  let loading = $state(true);
  let failed = $state(false);

  function inProgress(v) {
    const pos = v.history_position ?? v.last_position ?? 0;
    return v.duration > 0 && pos > MIN_STARTED_S && pos < v.duration - NEAR_END_S;
  }

  async function load() {
    loading = true; failed = false;
    try {
      const [history, newest] = await Promise.all([
        api.getHistory({ per_page: 20 }),
        api.getVideos({ per_page: 12, sort_by: 'created_at', sort_order: 'desc' }),
      ]);
      started = (history.videos || []).filter(inProgress).slice(0, 8);
      latest = newest.videos || [];
    } catch { failed = true; }
    loading = false;
  }

  function fullView() {
    try { localStorage.setItem(DESKTOP_FLAG, '1'); } catch {}
    window.location.href = '/';
  }

  load();
</script>

<div class="m-view">
<header class="top">
  <h1 class="m-h1">TubeVault</h1>
</header>

{#if loading}
  <div class="m-spin"><i class="fa-solid fa-spinner fa-spin"></i></div>
{:else if failed}
  <div class="m-note">
    <p>Der Server ist gerade nicht erreichbar.</p>
    <button class="m-btn" onclick={load}><i class="fa-solid fa-rotate"></i> Erneut versuchen</button>
  </div>
{:else}
  {#if started.length > 0}
    <h2 class="m-h2">Weiter ansehen</h2>
    {#each started as v (v.id)}
      <VideoRow title={v.title} channel={v.channel_name} duration={v.duration}
                thumb={api.thumbnailUrl(v.id)} archived={!!v.is_archived}
                progress={(v.history_position ?? v.last_position ?? 0) / v.duration}
                onopen={() => go(`/video/${v.id}`)} />
    {/each}
  {/if}

  <h2 class="m-h2">Zuletzt geladen</h2>
  {#each latest as v (v.id)}
    <VideoRow title={v.title} channel={v.channel_name} duration={v.duration}
              thumb={api.thumbnailUrl(v.id)} archived={!!v.is_archived}
              onopen={() => go(`/video/${v.id}`)} />
  {:else}
    <div class="m-note">Noch keine Videos geladen.</div>
  {/each}

  <footer class="foot">
    <button class="m-btn" onclick={fullView}><i class="fa-solid fa-display"></i> Volle Ansicht öffnen</button>
    <span class="version">TubeVault {FE_VERSION}</span>
  </footer>
{/if}
</div>

<style>
  .top { padding: calc(var(--m-safe-top) + 18px) 16px 4px; }
  .foot { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 28px 16px 32px; }
  .version { color: var(--m-faint); font-size: 0.78rem; }
</style>

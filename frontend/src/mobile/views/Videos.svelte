<!-- Videos: Bibliothek oder Archiv, neueste zuerst, endlos nachladend. -->
<script>
  import { api } from '../../lib/api/client.js';
  import { getSettingNum } from '../../lib/stores/settings.js';
  import { createListLoader } from '../../lib/utils/listLoader.svelte.js';
  import { go } from '../router.js';
  import VideoRow from '../parts/VideoRow.svelte';
  import { nearEnd } from '../parts/nearEnd.js';

  let scroller;

  const AREA_KEY = 'tv_mobil_bereich';
  const areas = [
    { id: 'library', label: 'Bibliothek', archived: false },
    { id: 'archive', label: 'Archiv', archived: true },
  ];

  let area = $state(readArea());

  function readArea() {
    try { return localStorage.getItem(AREA_KEY) === 'archive' ? 'archive' : 'library'; } catch { return 'library'; }
  }

  const list = createListLoader(async (page) => {
    const result = await api.getVideos({
      page, per_page: getSettingNum('general.videos_per_page', 24),
      sort_by: 'upload_date', sort_order: 'desc',
      is_archived: area === 'archive',
    });
    return { items: result.videos || [], total: result.total || 0 };
  });

  let failed = $state(false);

  async function reload() {
    failed = false;
    try { await list.load(true); } catch { failed = true; }
  }

  function choose(id) {
    if (id === area) return;
    area = id;
    try { localStorage.setItem(AREA_KEY, id); } catch {}
    scroller?.scrollTo({ top: 0 });
    reload();
  }

  reload();
</script>

<div class="m-view" bind:this={scroller} use:nearEnd={{ onNearEnd: list.loadMore, canLoad: list.canLoad }}>
<header class="top">
  <h1 class="m-h1">Videos</h1>
  <div class="seg" role="tablist">
    {#each areas as a (a.id)}
      <button role="tab" aria-selected={area === a.id} class:on={area === a.id} onclick={() => choose(a.id)}>
        {a.label}
      </button>
    {/each}
  </div>
  {#if !list.loading && !failed}<p class="count">{list.total} Videos</p>{/if}
</header>

{#if list.loading}
  <div class="m-spin"><i class="fa-solid fa-spinner fa-spin"></i></div>
{:else if failed}
  <div class="m-note">
    <p>Die Liste konnte nicht geladen werden.</p>
    <button class="m-btn" onclick={reload}><i class="fa-solid fa-rotate"></i> Erneut versuchen</button>
  </div>
{:else}
  {#each list.items as v (v.id)}
    <VideoRow title={v.title} channel={v.channel_name} duration={v.duration}
              thumb={api.thumbnailUrl(v.id)} onopen={() => go(`/video/${v.id}`)} />
  {:else}
    <div class="m-note">Hier liegen noch keine Videos.</div>
  {/each}
  {#if list.loadingMore}<div class="m-spin"><i class="fa-solid fa-spinner fa-spin"></i></div>{/if}
{/if}
</div>

<style>
  .top { padding: calc(var(--m-safe-top) + 18px) 16px 10px; border-bottom: 1px solid var(--m-line); }
  .seg {
    display: flex; margin-top: 12px; padding: 3px; gap: 3px;
    background: var(--m-surface-2); border-radius: var(--m-radius);
  }
  .seg button { flex: 1; min-height: 44px; border-radius: 9px; color: var(--m-dim); font-weight: 600; }
  .seg button.on { background: var(--m-bg); color: var(--m-text); }
  .count { margin-top: 10px; color: var(--m-faint); font-size: 0.82rem; }
</style>

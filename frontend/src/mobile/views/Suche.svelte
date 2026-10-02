<!-- Suche: ein Feld, Treffer aus Bibliothek und Archiv. -->
<script>
  import { api } from '../../lib/api/client.js';
  import { createListLoader } from '../../lib/utils/listLoader.svelte.js';
  import { route, go } from '../router.js';
  import VideoRow from '../parts/VideoRow.svelte';
  import { nearEnd } from '../parts/nearEnd.js';

  const PER_PAGE = 20;
  const DEBOUNCE_MS = 280;
  const MIN_CHARS = 2;

  let query = $state($route.params.q || '');
  let searched = $state('');
  let failed = $state(false);
  let timer = null;
  let scroller;

  const list = createListLoader(async (page) => {
    const result = await api.searchLocal(searched, { page, per_page: PER_PAGE });
    return { items: result.videos || [], total: result.total || 0 };
  });

  async function run() {
    const q = query.trim();
    if (q.length < MIN_CHARS) { searched = ''; list.items = []; list.total = 0; return; }
    searched = q;
    failed = false;
    go('/suche', { q }, { replace: true });
    try { await list.load(true); } catch { failed = true; }
  }

  function onInput() {
    clearTimeout(timer);
    timer = setTimeout(run, DEBOUNCE_MS);
  }

  function clear() {
    query = '';
    run();
    go('/suche', {}, { replace: true });
  }

  if ($route.params.q) run();
</script>

<div class="m-view" bind:this={scroller} use:nearEnd={{ onNearEnd: list.loadMore, canLoad: list.canLoad }}>
<header class="top">
  <form class="field" role="search" onsubmit={(e) => { e.preventDefault(); clearTimeout(timer); run(); e.target.querySelector('input').blur(); }}>
    <i class="fa-solid fa-magnifying-glass"></i>
    <input type="search" placeholder="Titel, Kanal, Stichwort" autocomplete="off" autocapitalize="off"
           enterkeyhint="search" bind:value={query} oninput={onInput} />
    {#if query}
      <button type="button" class="clear" aria-label="Eingabe löschen" onclick={clear}><i class="fa-solid fa-xmark"></i></button>
    {/if}
  </form>
  {#if searched && !list.loading && !failed}<p class="count">{list.total} Treffer</p>{/if}
</header>

{#if !searched}
  <div class="m-note">Durchsucht Bibliothek und Archiv: Titel, Kanal, Beschreibung und Tags.</div>
{:else if list.loading}
  <div class="m-spin"><i class="fa-solid fa-spinner fa-spin"></i></div>
{:else if failed}
  <div class="m-note">
    <p>Die Suche ist fehlgeschlagen.</p>
    <button class="m-btn" onclick={run}><i class="fa-solid fa-rotate"></i> Erneut versuchen</button>
  </div>
{:else}
  {#each list.items as v (v.id)}
    <VideoRow title={v.title} channel={v.channel_name} duration={v.duration}
              thumb={api.thumbnailUrl(v.id)} archived={!!v.is_archived}
              onopen={() => go(`/video/${v.id}`)} />
  {:else}
    <div class="m-note">Nichts gefunden für "{searched}".</div>
  {/each}
  {#if list.loadingMore}<div class="m-spin"><i class="fa-solid fa-spinner fa-spin"></i></div>{/if}
{/if}
</div>

<style>
  .top { padding: calc(var(--m-safe-top) + 14px) 16px 10px; border-bottom: 1px solid var(--m-line); }
  .field {
    display: flex; align-items: center; gap: 10px; min-height: 50px; padding: 0 6px 0 14px;
    background: var(--m-surface-2); border: 1px solid var(--m-line); border-radius: var(--m-radius);
    color: var(--m-dim);
  }
  .field:focus-within { border-color: var(--m-accent); }
  input {
    flex: 1; min-width: 0; height: 48px; background: none; border: none; outline: none;
    color: var(--m-text); font-size: 1.02rem; -webkit-appearance: none; appearance: none;
  }
  input::-webkit-search-cancel-button { display: none; }
  .clear { width: 44px; height: 44px; color: var(--m-dim); }
  .count { margin-top: 10px; color: var(--m-faint); font-size: 0.82rem; }
</style>

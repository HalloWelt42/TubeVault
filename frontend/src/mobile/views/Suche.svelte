<!--
  Suche am Handy: dieselbe Suche wie am Rechner (Backend services/search) -
  Videos, Gesagtes mit Sprung an die Stelle, neue Videos der Abos zum Laden,
  Musik zum Abspielen. "Alle" zeigt einen Bereich seitenweise.
-->
<script>
  import { api } from '../../lib/api/client.js';
  import { toast } from '../../lib/stores/notifications.js';
  import { musicPlayer } from '../../lib/stores/musicPlayer.svelte.js';
  import { rememberSearch } from '../../lib/stores/searchHistory.js';
  import { createListLoader } from '../../lib/utils/listLoader.svelte.js';
  import { formatDuration } from '../../lib/utils/format.js';
  import { coverUrl } from '../../lib/utils/musicTrack.js';
  import { route, go } from '../router.js';
  import VideoRow from '../parts/VideoRow.svelte';
  import { nearEnd } from '../parts/nearEnd.js';

  const PER_PAGE = 20;
  const DEBOUNCE_MS = 280;
  const MIN_CHARS = 2;
  const SHOWN = 4;
  const TITLES = { videos: 'Videos', gesagt: 'Im Gesagten', abos: 'Bei Abos, noch nicht geladen', musik: 'Musik' };

  let query = $state($route.params.q || '');
  let searched = $state('');
  let overview = $state(null);
  let section = $state(null);          // null: Überblick, sonst ein Bereich seitenweise
  let failed = $state(false);
  let loading = $state(false);
  let queued = $state(new Set());
  let timer = null;
  let run = 0;

  const list = createListLoader(async (page) => {
    if (!section || !searched) return { items: [], total: 0 };
    const result = await api.searchSection(section, searched, { page, per_page: PER_PAGE });
    return { items: result.items, total: result.total };
  }, { keyOf: (item) => item.id ?? item.track?.id });

  let sections = $derived(overview?.sections || {});
  let total = $derived(['videos', 'gesagt', 'abos', 'musik'].reduce((sum, id) => sum + (sections[id]?.total || 0), 0));

  async function search() {
    const q = query.trim();
    const mine = ++run;
    section = null;
    if (q.length < MIN_CHARS) { searched = ''; overview = null; return; }
    searched = q;
    failed = false;
    loading = true;
    go('/suche', { q }, { replace: true });
    try {
      const result = await api.search(q, { limit: 8 });
      if (mine === run) overview = result;
    } catch { if (mine === run) failed = true; }
    if (mine === run) loading = false;
  }

  function onInput() {
    clearTimeout(timer);
    timer = setTimeout(search, DEBOUNCE_MS);
  }

  function clear() {
    query = '';
    search();
    go('/suche', {}, { replace: true });
  }

  function showAll(id) {
    section = id;
    list.load(true);
  }

  function open(hit, start = null) {
    rememberSearch(searched);
    go(`/video/${hit.id}`, start ? { t: Math.floor(start) } : {});
  }

  async function load(hit) {
    try {
      await api.addDownload({ url: `https://www.youtube.com/watch?v=${hit.video_id}` });
      queued = new Set([...queued, hit.video_id]);
      toast.success('In der Warteschlange');
    } catch (e) { toast.error(e.message); }
  }

  function play(items, index) {
    rememberSearch(searched);
    musicPlayer.playTracks(items.map((hit) => hit.track), index, `Suche: ${searched}`);
  }

  if ($route.params.q) search();
</script>

{#snippet rows(id, items)}
  {#if id === 'musik'}
    {#each items as hit, i (hit.track.id)}
      <VideoRow title={hit.track.title} channel={hit.track.artist} duration={hit.track.duration} thumb={coverUrl(hit.track)}
                onopen={() => play(items, i)} />
    {/each}
  {:else if id === 'abos'}
    {#each items as hit (hit.id)}
      {@const waiting = hit.in_queue || queued.has(hit.video_id)}
      <VideoRow title={hit.title} channel={hit.channel_name} duration={hit.duration} thumb={api.rssThumbUrl(hit.video_id)}
                language={hit.language} languageSource={hit.language_source} note="noch nicht geladen">
        {#snippet action()}
          <button class="m-btn" class:primary={!waiting} disabled={waiting} onclick={() => load(hit)}>
            <i class="fa-solid {waiting ? 'fa-clock' : 'fa-download'}"></i> {waiting ? 'Wartet' : 'Laden'}</button>
        {/snippet}
      </VideoRow>
    {/each}
  {:else}
    {#each items as hit (hit.id)}
      {@const spot = hit.spots?.[0]}
      <VideoRow title={hit.title} channel={hit.channel_name} duration={hit.duration} thumb={api.thumbnailUrl(hit.id)}
                archived={hit.is_archived} language={hit.language} languageSource={hit.language_source}
                note={spot ? `${formatDuration(Math.floor(spot.start))} ${spot.text}` : null}
                onopen={() => open(hit, spot?.start)} />
    {/each}
  {/if}
{/snippet}

<div class="m-view" use:nearEnd={{ onNearEnd: list.loadMore, canLoad: () => !!section && list.canLoad() }}>
<header class="top">
  <form class="field" role="search" onsubmit={(e) => { e.preventDefault(); clearTimeout(timer); search(); e.target.querySelector('input').blur(); }}>
    <i class="fa-solid fa-magnifying-glass"></i>
    <input type="search" placeholder="Titel, Gesagtes, Kanal, Musik" autocomplete="off" autocapitalize="off"
           enterkeyhint="search" bind:value={query} oninput={onInput} />
    {#if query}
      <button type="button" class="clear" aria-label="Eingabe löschen" onclick={clear}><i class="fa-solid fa-xmark"></i></button>
    {/if}
  </form>
  {#if section}
    <button class="back" onclick={() => section = null}><i class="fa-solid fa-chevron-left"></i> Alle Bereiche</button>
  {:else if searched && overview && !loading}
    <p class="count">{total.toLocaleString('de-DE')} Treffer</p>
  {/if}
</header>

{#if !searched}
  <div class="m-note">Durchsucht Bibliothek und Archiv, das Gesagte, neue Videos deiner Abos und deine Musik.</div>
{:else if loading && !overview}
  <div class="m-spin"><i class="fa-solid fa-spinner fa-spin"></i></div>
{:else if failed}
  <div class="m-note">
    <p>Die Suche ist fehlgeschlagen.</p>
    <button class="m-btn" onclick={search}><i class="fa-solid fa-rotate"></i> Erneut versuchen</button>
  </div>
{:else if section}
  <h2 class="bereich">{TITLES[section]} <span>{list.total.toLocaleString('de-DE')}</span></h2>
  {@render rows(section, list.items)}
  {#if list.loading || list.loadingMore}<div class="m-spin"><i class="fa-solid fa-spinner fa-spin"></i></div>{/if}
{:else if !total}
  <div class="m-note">
    Nichts gefunden für "{searched}".
    {#if overview?.suggestion}
      <button class="m-btn primary" onclick={() => { query = overview.suggestion.text; search(); }}>Meintest du {overview.suggestion.text}?</button>
    {/if}
  </div>
{:else}
  {#each Object.keys(TITLES) as id (id)}
    {#if sections[id]?.total}
      <h2 class="bereich">{TITLES[id]} <span>{sections[id].total.toLocaleString('de-DE')}{sections[id].more ? '+' : ''}</span>
        {#if sections[id].total > SHOWN}<button onclick={() => showAll(id)}>Alle</button>{/if}</h2>
      {@render rows(id, sections[id].items.slice(0, SHOWN))}
    {/if}
  {/each}
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
  .back { margin-top: 10px; min-height: 40px; color: var(--m-accent); font-weight: 600; }
  .bereich { display: flex; align-items: baseline; gap: 8px; margin: 18px 16px 6px; font-size: 1.05rem; }
  .bereich span { color: var(--m-faint); font-size: 0.85rem; font-weight: 500; }
  .bereich button { margin-left: auto; min-height: 36px; color: var(--m-accent); font-weight: 600; font-size: 0.95rem; }
</style>

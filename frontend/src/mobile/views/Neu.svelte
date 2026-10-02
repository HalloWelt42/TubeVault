<!--
  Neu: frische Videos aus den Abos. Geladene lassen sich abspielen; alles
  andere wird per Drücken und Halten eingereiht (Qualität: Kanal bzw.
  Einstellungen).
-->
<script>
  import { api } from '../../lib/api/client.js';
  import { formatDateRelative } from '../../lib/utils/format.js';
  import { getSettingNum } from '../../lib/stores/settings.js';
  import { createListLoader } from '../../lib/utils/listLoader.svelte.js';
  import { go } from '../router.js';
  import { say } from '../notice.js';
  import VideoRow from '../parts/VideoRow.svelte';
  import HoldButton from '../parts/HoldButton.svelte';
  import { nearEnd } from '../parts/nearEnd.js';

  let failed = $state(false);
  let queued = $state(new Set());   // in dieser Sitzung eingereiht

  const list = createListLoader(async (page) => {
    const data = await api.getFeedVideos({
      feedTab: 'active', page, perPage: getSettingNum('general.videos_per_page', 24),
    });
    return { items: data.entries || [], total: data.total || 0, hasMore: !!data.has_more };
  });

  async function reload() {
    failed = false;
    try { await list.load(true); } catch { failed = true; }
  }

  const isLoaded = (entry) => entry.video_status === 'ready';
  const isWaiting = (entry) => !!entry.is_in_queue || queued.has(entry.video_id);

  async function load(entry) {
    try {
      await api.addDownload({ url: `https://www.youtube.com/watch?v=${entry.video_id}` });
      queued = new Set([...queued, entry.video_id]);
      say('Eingereiht: ' + (entry.title || entry.video_id), 'ok');
    } catch (e) {
      say(e.message, 'warn');
    }
  }

  reload();
</script>

<div class="m-view" use:nearEnd={{ onNearEnd: list.loadMore, canLoad: list.canLoad }}>
  <header class="top">
    <h1 class="m-h1">Neu</h1>
    {#if !list.loading && !failed}<p class="count">{list.total} Videos aus den Abos</p>{/if}
  </header>

  {#if list.loading}
    <div class="m-spin"><i class="fa-solid fa-spinner fa-spin"></i></div>
  {:else if failed}
    <div class="m-note">
      <p>Die Liste konnte nicht geladen werden.</p>
      <button class="m-btn" onclick={reload}><i class="fa-solid fa-rotate"></i> Erneut versuchen</button>
    </div>
  {:else}
    {#each list.items as entry (entry.id)}
      <VideoRow title={entry.title || entry.video_id} channel={entry.channel_name} duration={entry.duration}
                thumb={isLoaded(entry) ? api.thumbnailUrl(entry.video_id) : api.rssThumbUrl(entry.video_id)}
                note={formatDateRelative(entry.published)}
                onopen={isLoaded(entry) ? () => go(`/video/${entry.video_id}`) : null}>
        {#snippet action()}
          {#if isLoaded(entry)}
            <span class="state ok" title="Geladen"><i class="fa-solid fa-circle-check"></i></span>
          {:else if isWaiting(entry)}
            <span class="state wait" title="In der Warteschlange"><i class="fa-solid fa-clock"></i></span>
          {:else}
            <HoldButton label="Laden" onfire={() => load(entry)} />
          {/if}
        {/snippet}
      </VideoRow>
    {:else}
      <div class="m-note">Nichts Neues aus den Abos.</div>
    {/each}
    {#if list.loadingMore}<div class="m-spin"><i class="fa-solid fa-spinner fa-spin"></i></div>{/if}
  {/if}
</div>

<style>
  .top { padding: calc(var(--m-safe-top) + 18px) 16px 10px; border-bottom: 1px solid var(--m-line); }
  .count { margin-top: 6px; color: var(--m-faint); font-size: 0.82rem; }
  .state { width: 52px; height: 52px; display: flex; align-items: center; justify-content: center; font-size: 1.15rem; }
  .state.ok { color: var(--m-ok); }
  .state.wait { color: var(--m-warn); }
</style>

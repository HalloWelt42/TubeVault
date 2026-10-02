<!--
  Eine Playlist: am Stück abspielen (in Reihenfolge oder gemischt) oder bei
  einem bestimmten Video einsteigen.
-->
<script>
  import { api } from '../../lib/api/client.js';
  import { formatDuration } from '../../lib/utils/format.js';
  import { go, back } from '../router.js';
  import { loadQueue, forgetQueue } from '../playQueue.js';
  import VideoRow from '../parts/VideoRow.svelte';

  let { id } = $props();

  let queue = $state(null);
  let failed = $state(false);
  let total = $derived((queue?.videos || []).reduce((sum, v) => sum + (v.duration || 0), 0));

  async function load() {
    failed = false;
    try { queue = await loadQueue(id); } catch { failed = true; }
  }

  function play(videoId) {
    go(`/video/${videoId}`, { liste: id });
  }

  async function playShuffled() {
    forgetQueue(id);
    const mixed = await loadQueue(id, true);
    if (mixed.videos.length) go(`/video/${mixed.videos[0].id}`, { liste: id, zufall: 1 });
  }

  load();
</script>

<div class="m-view">
  <header class="bar">
    <button class="back" aria-label="Zurück" onclick={back}><i class="fa-solid fa-chevron-left"></i></button>
  </header>

  {#if failed}
    <div class="m-note">
      <p>Die Playlist konnte nicht geladen werden.</p>
      <button class="m-btn" onclick={load}><i class="fa-solid fa-rotate"></i> Erneut versuchen</button>
    </div>
  {:else if !queue}
    <div class="m-spin"><i class="fa-solid fa-spinner fa-spin"></i></div>
  {:else}
    <section class="head">
      <h1 class="m-h1">{queue.name}</h1>
      <p class="meta">{queue.videos.length} Videos{#if total} · {formatDuration(total)}{/if}</p>
      {#if queue.videos.length > 0}
        <div class="actions">
          <button class="m-btn primary" onclick={() => play(queue.videos[0].id)}>
            <i class="fa-solid fa-play"></i> Abspielen
          </button>
          <button class="m-btn" onclick={playShuffled}>
            <i class="fa-solid fa-shuffle"></i> Zufällig
          </button>
        </div>
      {/if}
    </section>

    {#each queue.videos as v, index (v.id)}
      <VideoRow title={v.title} channel={v.channel_name} duration={v.duration}
                thumb={api.thumbnailUrl(v.id)} note={`${index + 1}`}
                onopen={() => play(v.id)} />
    {:else}
      <div class="m-note">In dieser Playlist ist kein geladenes Video.</div>
    {/each}
  {/if}
</div>

<style>
  .bar { padding: var(--m-safe-top) 4px 0; }
  .back { width: 52px; height: 48px; font-size: 1.15rem; color: var(--m-text); }
  .head { padding: 0 16px 14px; }
  .meta { color: var(--m-dim); margin-top: 4px; }
  .actions { display: flex; gap: 10px; margin-top: 14px; }
  .actions .m-btn { flex: 1; }
</style>

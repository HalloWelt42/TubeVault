<!-- Listen: alle Playlists; eine Playlist zeigt ihre Videos und spielt sie am Stück. -->
<script>
  import { api } from '../../lib/api/client.js';
  import { formatDuration } from '../../lib/utils/format.js';
  import { go } from '../router.js';

  let playlists = $state([]);
  let loading = $state(true);
  let failed = $state(false);

  async function load() {
    loading = true; failed = false;
    try { playlists = (await api.getPlaylists()).filter(p => p.video_count > 0); }
    catch { failed = true; }
    loading = false;
  }

  load();
</script>

<div class="m-view">
  <header class="top"><h1 class="m-h1">Listen</h1></header>

  {#if loading}
    <div class="m-spin"><i class="fa-solid fa-spinner fa-spin"></i></div>
  {:else if failed}
    <div class="m-note">
      <p>Der Server ist gerade nicht erreichbar.</p>
      <button class="m-btn" onclick={load}><i class="fa-solid fa-rotate"></i> Erneut versuchen</button>
    </div>
  {:else}
    {#each playlists as list (list.id)}
      <button class="list" onclick={() => go(`/liste/${list.id}`)}>
        <span class="cover">
          {#if list.cover_video_id}
            <img src={api.thumbnailUrl(list.cover_video_id)} alt="" loading="lazy" />
          {:else}
            <i class="fa-solid fa-list-ul"></i>
          {/if}
        </span>
        <span class="text">
          <span class="name">{list.name}</span>
          <span class="meta">
            {list.video_count} Videos{#if list.total_duration} · {formatDuration(list.total_duration)}{/if}
          </span>
        </span>
        <i class="fa-solid fa-chevron-right go"></i>
      </button>
    {:else}
      <div class="m-note">Noch keine Playlists. Angelegt werden sie in der vollen Ansicht.</div>
    {/each}
  {/if}
</div>

<style>
  .top { padding: calc(var(--m-safe-top) + 18px) 16px 8px; }
  .list {
    display: flex; align-items: center; gap: 12px; width: 100%; min-height: 76px;
    padding: 10px 16px; text-align: left; border-bottom: 1px solid var(--m-line);
  }
  .list:active { background: var(--m-surface); }
  .cover {
    flex: 0 0 96px; aspect-ratio: 16 / 9; border-radius: 8px; overflow: hidden;
    background: var(--m-surface-2); color: var(--m-faint);
    display: flex; align-items: center; justify-content: center;
  }
  .cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
  .name { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .meta { color: var(--m-dim); font-size: 0.84rem; }
  .go { color: var(--m-faint); }
</style>

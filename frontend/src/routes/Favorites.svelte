<script>
  import { api } from '../lib/api/client.js';
  import { toast } from '../lib/stores/notifications.js';
  import { navigate } from '../lib/router/router.js';
  import { formatDuration, formatDateRelative } from '../lib/utils/format.js';

  let lists = $state([]);
  let activeList = $state('Standard');
  let favorites = $state([]);
  let loading = $state(false);

  async function loadLists() {
    try {
      lists = await api.getFavoriteLists();
      if (lists.length > 0 && !lists.find(l => l.name === activeList)) {
        activeList = lists[0].name;
      }
    } catch (e) { toast.error(e.message); }
  }

  async function loadFavorites() {
    loading = true;
    try {
      favorites = await api.getFavorites(activeList);
    } catch (e) { toast.error(e.message); }
    finally { loading = false; }
  }

  function playVideo(id) {
    navigate(`/watch/${id}`);
  }

  async function removeFavorite(video) {
    try {
      await api.removeFavorite(video.id);
      favorites = favorites.filter(f => f.id !== video.id);
      const listIdx = lists.findIndex(l => l.name === activeList);
      if (listIdx >= 0) {
        lists[listIdx] = { ...lists[listIdx], count: lists[listIdx].count - 1 };
        lists = [...lists];
      }
      toast.info(`"${video.title?.substring(0, 40)}" entfernt`);
    } catch (e) { toast.error(e.message); }
  }

  $effect(() => { loadLists(); });
  $effect(() => { activeList; loadFavorites(); });
</script>

<div class="page">
  <div class="page-header">
    <h1 class="title">Favoriten</h1>
    <span class="subtitle">{favorites.length} Videos</span>
  </div>

  {#if lists.length > 0}
    <div class="list-tabs">
      {#each lists as list}
        <button
          class="tab-btn"
          class:active={activeList === list.name}
          onclick={() => activeList = list.name}
        >
          {list.name} ({list.count})
        </button>
      {/each}
    </div>
  {/if}

  {#if loading}
    <div class="loading">Wird geladen…</div>
  {:else if favorites.length > 0}
    <div class="video-grid">
      {#each favorites as fav (fav.id)}
        <div class="video-card">
          <button class="card-thumb" onclick={() => playVideo(fav.id)}>
            <img
              class="thumb"
              src={api.thumbnailUrl(fav.id)}
              alt={fav.title}
              loading="lazy"
              onerror={(e) => e.target.style.display = 'none'}
            />
            {#if fav.duration}
              <span class="duration">{formatDuration(fav.duration)}</span>
            {/if}
            <div class="play-overlay"><i class="fa-solid fa-play"></i></div>
          </button>
          <div class="card-body">
            <div class="card-text">
              <button class="card-title" onclick={() => playVideo(fav.id)}>
                {fav.title || fav.id}
              </button>
              <span class="card-channel">{fav.channel_name || 'Unbekannt'}</span>
              {#if fav.added_at}
                <span class="card-meta">Hinzugefügt {formatDateRelative(fav.added_at)}</span>
              {/if}
            </div>
            <button class="remove-btn" onclick={() => removeFavorite(fav)} title="Aus Favoriten entfernen">
              <i class="fa-solid fa-heart" style="color:var(--status-error); font-size:0.9rem"></i>
            </button>
          </div>
        </div>
      {/each}
    </div>
  {:else}
    <div class="empty">
      <i class="fa-regular fa-heart" style="font-size:3.5rem; color:var(--text-tertiary)"></i>
      <h3>Keine Favoriten</h3>
      <p>Markiere Videos als Favorit über die Watch-Seite.</p>
      <button class="btn-ghost" onclick={() => navigate('/library')}>Zur Bibliothek</button>
    </div>
  {/if}
</div>

<style>
  .page { padding: 24px; max-width: 1200px; }
  .page-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 16px; }
  .title { font-size: 1.5rem; font-weight: 700; color: var(--text-primary); margin: 0; }
  .subtitle { font-size: 0.82rem; color: var(--text-tertiary); }

  .list-tabs { display: flex; gap: 6px; margin-bottom: 20px; flex-wrap: wrap; }
  .tab-btn {
    padding: 7px 16px; background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 8px; color: var(--text-secondary); font-size: 0.85rem; cursor: pointer; transition: all 0.15s;
  }
  .tab-btn:hover { border-color: var(--accent-primary); }
  .tab-btn.active { background: var(--accent-muted); color: var(--accent-primary); border-color: var(--accent-primary); }

  .video-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }

  .video-card {
    background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 12px; overflow: hidden; transition: all 0.2s;
  }
  .video-card:hover { border-color: var(--accent-primary); transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.15); }

  .card-thumb {
    position: relative; aspect-ratio: 16/9; background: var(--bg-tertiary);
    overflow: hidden; cursor: pointer; display: block; width: 100%; border: none; padding: 0;
  }
  .thumb { width: 100%; height: 100%; object-fit: cover; display: block; }
  .duration {
    position: absolute; bottom: 8px; right: 8px; background: rgba(0,0,0,0.8);
    color: #fff; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; font-family: monospace;
  }
  .play-overlay {
    position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
    background: rgba(0,0,0,0.3); color: #fff; font-size: 2rem; opacity: 0; transition: opacity 0.2s;
  }
  .card-thumb:hover .play-overlay { opacity: 1; }

  .card-body { display: flex; gap: 8px; padding: 12px; align-items: flex-start; }
  .card-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .card-title {
    font-size: 0.9rem; font-weight: 600; color: var(--text-primary); margin: 0;
    background: none; border: none; padding: 0; cursor: pointer; text-align: left;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; line-height: 1.3;
  }
  .card-title:hover { color: var(--accent-primary); }
  .card-channel { font-size: 0.8rem; color: var(--text-secondary); }
  .card-meta { font-size: 0.72rem; color: var(--text-tertiary); }

  .remove-btn {
    flex-shrink: 0; width: 32px; height: 32px; border-radius: 8px;
    border: 1px solid transparent; background: none; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    opacity: 0.4; transition: all 0.15s;
  }
  .remove-btn:hover { opacity: 1; background: rgba(239,68,68,0.1); border-color: var(--status-error); }

  .loading { padding: 60px; text-align: center; color: var(--text-tertiary); }
  .empty { display: flex; flex-direction: column; align-items: center; padding: 60px 20px; text-align: center; color: var(--text-tertiary); }
  .empty h3 { margin: 16px 0 8px; color: var(--text-secondary); }
  .empty p { margin-bottom: 16px; font-size: 0.88rem; max-width: 380px; }
  .btn-ghost { padding: 7px 16px; background: transparent; border: 1px solid var(--border-primary); border-radius: 8px; color: var(--text-secondary); font-size: 0.82rem; cursor: pointer; }
  .btn-ghost:hover { border-color: var(--accent-primary); color: var(--text-primary); }
</style>

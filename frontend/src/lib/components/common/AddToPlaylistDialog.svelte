<!--
  TubeVault -  AddToPlaylistDialog v1.5.91
  Dialog zum Hinzufügen eines Videos zu einer oder mehreren Playlists.
  Aufruf: <AddToPlaylistDialog bind:videoId={selectedVideoId} />
  © HalloWelt42 -  Private Nutzung
-->
<script>
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';

  let { videoId = $bindable(null) } = $props();

  let playlists = $state([]);
  let loading = $state(false);
  let creating = $state(false);
  let newName = $state('');
  let videoPlaylists = $state(new Set()); // Playlists in denen Video schon ist

  let open = $derived(!!videoId);

  $effect(() => {
    if (videoId) loadData();
  });

  async function loadData() {
    loading = true;
    try {
      const allPl = await api.getPlaylists();
      playlists = allPl.playlists || allPl || [];

      // Prüfen in welchen Playlists das Video schon ist
      const existing = new Set();
      for (const pl of playlists) {
        try {
          const detail = await api.getPlaylist(pl.id);
          if (detail.videos?.some(v => v.id === videoId)) {
            existing.add(pl.id);
          }
        } catch { /* skip */ }
      }
      videoPlaylists = existing;
    } catch (e) { toast.error(e.message); }
    loading = false;
  }

  async function togglePlaylist(plId) {
    if (videoPlaylists.has(plId)) {
      // Entfernen
      try {
        await api.removeFromPlaylist(plId, videoId);
        videoPlaylists.delete(plId);
        videoPlaylists = new Set(videoPlaylists);
        toast.info('Aus Playlist entfernt');
      } catch (e) { toast.error(e.message); }
    } else {
      // Hinzufügen
      try {
        await api.addToPlaylist(plId, videoId);
        videoPlaylists.add(plId);
        videoPlaylists = new Set(videoPlaylists);
        toast.success('Zur Playlist hinzugefügt');
      } catch (e) {
        if (e.message?.includes('bereits')) toast.info('Bereits in Playlist');
        else toast.error(e.message);
      }
    }
  }

  async function createAndAdd() {
    if (!newName.trim()) return;
    creating = true;
    try {
      const res = await api.createPlaylist({ name: newName.trim() });
      const newId = res.id;
      await api.addToPlaylist(newId, videoId);
      toast.success(`"${newName}" erstellt & Video hinzugefügt`);
      newName = '';
      await loadData();
    } catch (e) { toast.error(e.message); }
    creating = false;
  }

  function close() { videoId = null; }
</script>

{#if open}
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="atpl-overlay" onclick={close} onkeydown={(e) => e.key === 'Escape' && close()}>
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="atpl-dialog" onclick={(e) => e.stopPropagation()}>
      <div class="atpl-header">
        <h3><i class="fa-solid fa-list-ul"></i> Zur Playlist hinzufügen</h3>
        <button class="atpl-close" onclick={close}><i class="fa-solid fa-xmark"></i></button>
      </div>

      {#if loading}
        <div class="atpl-loading"><i class="fa-solid fa-spinner fa-spin"></i> Lade Playlists…</div>
      {:else}
        <div class="atpl-body">
          {#if playlists.length > 0}
            <div class="atpl-list">
              {#each playlists as pl (pl.id)}
                <button class="atpl-item" class:active={videoPlaylists.has(pl.id)} onclick={() => togglePlaylist(pl.id)}>
                  <span class="atpl-check">
                    {#if videoPlaylists.has(pl.id)}
                      <i class="fa-solid fa-square-check"></i>
                    {:else}
                      <i class="fa-regular fa-square"></i>
                    {/if}
                  </span>
                  <span class="atpl-name">{pl.name}</span>
                  <span class="atpl-count">{pl.video_count || 0}</span>
                </button>
              {/each}
            </div>
          {:else}
            <div class="atpl-empty">Noch keine Playlists vorhanden.</div>
          {/if}

          <!-- Neue Playlist erstellen -->
          <div class="atpl-create">
            <input type="text" class="atpl-input" placeholder="Neue Playlist erstellen…"
              bind:value={newName}
              onkeydown={(e) => e.key === 'Enter' && createAndAdd()} />
            <button class="atpl-add-btn" onclick={createAndAdd} disabled={!newName.trim() || creating}>
              <i class="fa-solid fa-plus"></i>
            </button>
          </div>
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .atpl-overlay {
    position: fixed; inset: 0; background: rgba(0,0,0,0.6);
    z-index: 1000; display: flex; align-items: center; justify-content: center;
    animation: fadeIn 0.15s ease;
  }
  @keyframes fadeIn { from { opacity: 0; } }

  .atpl-dialog {
    background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 14px; width: 360px; max-width: 90vw; max-height: 70vh;
    display: flex; flex-direction: column; overflow: hidden;
    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
  }

  .atpl-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 16px; border-bottom: 1px solid var(--border-primary);
  }
  .atpl-header h3 { font-size: 0.95rem; font-weight: 700; margin: 0; display: flex; align-items: center; gap: 8px; }
  .atpl-close { background: none; border: none; color: var(--text-tertiary); cursor: pointer; font-size: 1rem; padding: 4px; }

  .atpl-body { padding: 12px 16px; overflow-y: auto; flex: 1; }
  .atpl-list { display: flex; flex-direction: column; gap: 2px; margin-bottom: 12px; }

  .atpl-item {
    display: flex; align-items: center; gap: 10px; padding: 8px 10px;
    border-radius: 8px; background: none; border: none; cursor: pointer;
    text-align: left; color: var(--text-primary); font-size: 0.85rem;
    transition: background 0.1s; width: 100%;
  }
  .atpl-item:hover { background: var(--bg-tertiary); }
  .atpl-item.active { background: rgba(99, 102, 241, 0.1); }
  .atpl-check { font-size: 1rem; width: 22px; color: var(--text-tertiary); }
  .atpl-item.active .atpl-check { color: var(--accent-primary); }
  .atpl-name { flex: 1; font-weight: 500; }
  .atpl-count { font-size: 0.72rem; color: var(--text-tertiary); }

  .atpl-create {
    display: flex; gap: 6px; padding-top: 10px; border-top: 1px solid var(--border-primary);
  }
  .atpl-input {
    flex: 1; padding: 7px 10px; background: var(--bg-tertiary); border: 1px solid var(--border-primary);
    border-radius: 8px; color: var(--text-primary); font-size: 0.82rem; outline: none;
  }
  .atpl-input:focus { border-color: var(--accent-primary); }
  .atpl-add-btn {
    width: 36px; height: 36px; border-radius: 8px; background: var(--accent-primary);
    color: #fff; border: none; cursor: pointer; font-size: 0.85rem;
    display: flex; align-items: center; justify-content: center;
  }
  .atpl-add-btn:disabled { opacity: 0.4; }

  .atpl-loading, .atpl-empty { padding: 24px; text-align: center; color: var(--text-tertiary); font-size: 0.85rem; }
</style>

<!--
  TubeVault -  QuickPlaylistBtn v1.6.0
  One-Click Button: Video zur gepinnten Playlist hinzufügen.
  Props: videoId (required), title/channelName/channelId (optional, für Stub-Erstellung)
  Varianten: size="sm" (Overlay), size="md" (Action-Bar)
  © HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
  SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
-->
<script>
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';
  import { quickPlaylist } from '../../stores/quickPlaylist.js';

  let {
    videoId,
    title = null,
    channelName = null,
    channelId = null,
    size = 'md',
    showLabel = false,
  } = $props();

  let adding = $state(false);
  let added = $state(false);
  let showPicker = $state(false);
  let playlists = $state([]);
  let loadingPl = $state(false);
  let pickerPos = $state({ top: 0, left: 0 });
  let wrapRef = $state(null);

  // Prüfen ob Video schon in Quick-Playlist ist (lazy, bei Hover)
  let checked = $state(false);
  async function checkMembership() {
    if (checked || !$quickPlaylist || !videoId) return;
    checked = true;
    try {
      const detail = await api.getPlaylist($quickPlaylist.id);
      if (detail.videos?.some(v => v.id === videoId)) {
        added = true;
      }
    } catch { /* Playlist evtl. gelöscht */ }
  }

  async function quickAdd(e) {
    e.stopPropagation();
    e.preventDefault();

    if (!$quickPlaylist) {
      // Keine Quick-Playlist gesetzt → Picker öffnen
      await loadPlaylists();
      if (wrapRef) {
        const rect = wrapRef.getBoundingClientRect();
        const spaceBelow = window.innerHeight - rect.bottom;
        const spaceRight = window.innerWidth - rect.right;
        pickerPos = {
          top: spaceBelow > 300 ? rect.bottom + 4 : rect.top - 280,
          left: spaceRight > 230 ? rect.left : rect.right - 220,
        };
      }
      showPicker = true;
      return;
    }

    if (added) {
      // Bereits drin → entfernen
      try {
        await api.removeFromPlaylist($quickPlaylist.id, videoId);
        added = false;
        toast.info(`Aus „${$quickPlaylist.name}" entfernt`);
      } catch (err) { toast.error(err.message); }
      return;
    }

    adding = true;
    try {
      await api.addToPlaylist($quickPlaylist.id, videoId, { title, channel_name: channelName, channel_id: channelId });
      added = true;
      toast.success(`→ ${$quickPlaylist.name}`);
    } catch (err) {
      if (err.message?.includes('bereits')) {
        added = true;
        toast.info('Bereits in Playlist');
      } else if (err.message?.includes('nicht gefunden') && err.message?.includes('Playlist')) {
        // Playlist wurde gelöscht
        quickPlaylist.set(null);
        toast.error('Quick-Playlist nicht mehr vorhanden');
      } else {
        toast.error(err.message);
      }
    }
    adding = false;
  }

  async function loadPlaylists() {
    loadingPl = true;
    try {
      const res = await api.getPlaylists();
      playlists = res.playlists || res || [];
    } catch { playlists = []; }
    loadingPl = false;
  }

  function pickPlaylist(pl, e) {
    e.stopPropagation();
    quickPlaylist.set({ id: pl.id, name: pl.name });
    showPicker = false;
    toast.success(`📌 „${pl.name}" als Quick-Playlist`);
    // Direkt hinzufügen
    setTimeout(() => quickAdd(new MouseEvent('click')), 100);
  }

  function closePicker(e) {
    e.stopPropagation();
    showPicker = false;
  }

  // Reset added-State wenn videoId wechselt
  $effect(() => {
    if (videoId) { added = false; checked = false; }
  });
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="qpl-wrap" class:qpl-sm={size === 'sm'} class:qpl-md={size === 'md'}
     bind:this={wrapRef} onmouseenter={checkMembership}>
  <button
    class="qpl-btn"
    class:qpl-active={added}
    class:qpl-adding={adding}
    class:qpl-no-target={!$quickPlaylist}
    onclick={quickAdd}
    title={$quickPlaylist ? (added ? `Aus „${$quickPlaylist.name}" entfernen` : `Zu „${$quickPlaylist.name}" hinzufügen`) : 'Quick-Playlist wählen'}
  >
    {#if adding}
      <i class="fa-solid fa-spinner fa-spin"></i>
    {:else if added}
      <i class="fa-solid fa-bookmark"></i>
    {:else if $quickPlaylist}
      <i class="fa-regular fa-bookmark"></i>
    {:else}
      <i class="fa-solid fa-bookmark" style="opacity:0.4"></i>
    {/if}
    {#if showLabel && $quickPlaylist}
      <span class="qpl-label">{$quickPlaylist.name}</span>
    {/if}
  </button>

  {#if showPicker}
    <div class="qpl-picker-overlay" onclick={closePicker}></div>
    <div class="qpl-picker" style="top:{pickerPos.top}px;left:{pickerPos.left}px">
      <div class="qpl-picker-head">
        <span>Quick-Playlist wählen</span>
        <button class="qpl-picker-close" onclick={closePicker}><i class="fa-solid fa-xmark"></i></button>
      </div>
      {#if loadingPl}
        <div class="qpl-picker-loading"><i class="fa-solid fa-spinner fa-spin"></i></div>
      {:else if playlists.length === 0}
        <div class="qpl-picker-empty">Keine Playlists vorhanden</div>
      {:else}
        <div class="qpl-picker-list">
          {#each playlists as pl (pl.id)}
            <button class="qpl-picker-item" onclick={(e) => pickPlaylist(pl, e)}>
              <i class="fa-solid fa-list-ul"></i>
              <span>{pl.name}</span>
              <span class="qpl-picker-count">{pl.video_count || 0}</span>
            </button>
          {/each}
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .qpl-wrap { position: relative; display: inline-flex; }

  .qpl-btn {
    display: flex; align-items: center; justify-content: center; gap: 6px;
    border: none; cursor: pointer; transition: all 0.15s;
    color: var(--text-secondary); background: none;
  }
  .qpl-btn:hover { color: var(--accent-primary); }

  /* Active = Video ist in Playlist */
  .qpl-btn.qpl-active { color: #f59e0b; }
  .qpl-btn.qpl-active:hover { color: #d97706; }

  /* No target = keine Quick-Playlist gesetzt */
  .qpl-btn.qpl-no-target { color: var(--text-tertiary); }
  .qpl-btn.qpl-no-target:hover { color: var(--text-secondary); }

  /* Size: sm (Overlay auf Thumbnail) */
  .qpl-sm .qpl-btn {
    width: 28px; height: 28px; border-radius: 50%;
    background: rgba(0,0,0,0.7); color: #fff; font-size: 0.72rem;
  }
  .qpl-sm .qpl-btn:hover { background: var(--accent-primary); color: #fff; }
  .qpl-sm .qpl-btn.qpl-active { background: rgba(245,158,11,0.9); color: #fff; }

  /* Size: md (Action-Bar) */
  .qpl-md .qpl-btn {
    width: 34px; height: 34px; border-radius: 8px; font-size: 0.95rem;
  }
  .qpl-md .qpl-btn:hover { background: var(--bg-tertiary); }

  .qpl-label { font-size: 0.75rem; font-weight: 500; white-space: nowrap; }

  /* Picker Dropdown */
  .qpl-picker-overlay {
    position: fixed; inset: 0; z-index: 999;
  }
  .qpl-picker {
    position: fixed; z-index: 1000;
    background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 10px; width: 220px; max-height: 280px;
    box-shadow: 0 12px 40px rgba(0,0,0,0.3);
    display: flex; flex-direction: column; overflow: hidden;
    animation: qplFadeIn 0.12s ease;
  }
  @keyframes qplFadeIn { from { opacity: 0; transform: translateY(-4px); } }

  .qpl-picker-head {
    display: flex; align-items: center; justify-content: space-between;
    padding: 10px 12px; font-size: 0.78rem; font-weight: 600;
    color: var(--text-secondary); border-bottom: 1px solid var(--border-primary);
  }
  .qpl-picker-close { background: none; border: none; color: var(--text-tertiary); cursor: pointer; font-size: 0.8rem; }
  .qpl-picker-list { overflow-y: auto; flex: 1; padding: 4px; }

  .qpl-picker-item {
    display: flex; align-items: center; gap: 8px; width: 100%;
    padding: 8px 10px; border: none; background: none;
    color: var(--text-primary); font-size: 0.82rem; cursor: pointer;
    border-radius: 6px; text-align: left;
  }
  .qpl-picker-item:hover { background: var(--bg-tertiary); }
  .qpl-picker-count { margin-left: auto; font-size: 0.7rem; color: var(--text-tertiary); }

  .qpl-picker-loading, .qpl-picker-empty {
    padding: 20px; text-align: center; color: var(--text-tertiary); font-size: 0.8rem;
  }
</style>

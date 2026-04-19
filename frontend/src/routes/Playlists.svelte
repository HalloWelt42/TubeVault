<!--
  TubeVault – Playlists v1.6.0
  Playlist-Verwaltung: Erstellen, Abspielen, Videos hinzufügen, Drag&Drop Sortieren.
  v1.6.0: Hover-Buttons im Feed-Stil (zentral, gross, weiss) via global.css
  © HalloWelt42 – Private Nutzung
-->
<script>
  import { api } from '../lib/api/client.js';
  import { route, navigate } from '../lib/router/router.js';
  import { toast } from '../lib/stores/notifications.js';
  import { formatDuration, formatSize, formatDateRelative, formatViews } from '../lib/utils/format.js';
  import { startQueue } from '../lib/stores/playlistQueue.js';
  import { quickPlaylist, pinPlaylist, unpinPlaylist } from '../lib/stores/quickPlaylist.js';
  import LikeBar from '../lib/components/common/LikeBar.svelte';

  function togglePin(pl) {
    if ($quickPlaylist?.id === pl.id) {
      unpinPlaylist();
      toast.info(`📌 „${pl.name}" losgelöst`);
    } else {
      pinPlaylist(pl.id, pl.name);
      toast.success(`📌 „${pl.name}" als Quick-Playlist`);
    }
  }

  let playlists = $state([]);
  let selectedPl = $state(null);
  let plVideos = $state([]);
  let loading = $state(true);

  // Create
  let showCreate = $state(false);
  let newName = $state('');
  let newDesc = $state('');

  // Edit
  let editingPl = $state(null);
  let editName = $state('');
  let editDesc = $state('');

  // Add Video
  let showAddVideo = $state(false);
  let addSearch = $state('');
  let addResults = $state([]);
  let addSearching = $state(false);
  let addSearchTimer = null;

  // Drag & Drop
  let dragIdx = $state(null);
  let dragOverIdx = $state(null);

  async function loadPlaylists() {
    loading = true;
    try {
      const res = await api.getPlaylists();
      playlists = res.playlists || res || [];
    } catch { toast.error('Playlists laden fehlgeschlagen'); }
    loading = false;
  }

  async function selectPlaylist(pl) {
    selectedPl = pl;
    showAddVideo = false;
    addSearch = '';
    addResults = [];
    try {
      const res = await api.getPlaylist(pl.id);
      plVideos = res.videos || [];
    } catch (e) { toast.error(e.message); plVideos = []; }
  }

  async function createPlaylist() {
    if (!newName.trim()) return;
    try {
      await api.createPlaylist({ name: newName.trim(), description: newDesc.trim() || undefined });
      toast.success(`"${newName}" erstellt`);
      newName = ''; newDesc = ''; showCreate = false;
      await loadPlaylists();
    } catch (e) { toast.error(e.message); }
  }

  async function deletePlaylist(id) {
    try {
      await api.deletePlaylist(id);
      if (selectedPl?.id === id) { selectedPl = null; plVideos = []; }
      if ($quickPlaylist?.id === id) { unpinPlaylist(); }
      toast.success('Playlist gelöscht');
      await loadPlaylists();
    } catch (e) { toast.error(e.message); }
  }

  function startEditPl(pl) {
    editingPl = pl.id;
    editName = pl.name;
    editDesc = pl.description || '';
  }

  async function saveEditPl() {
    if (!editName.trim() || !editingPl) return;
    try {
      await api.updatePlaylist(editingPl, { name: editName.trim(), description: editDesc.trim() || null });
      toast.success('Aktualisiert');
      const eid = editingPl;
      editingPl = null;
      await loadPlaylists();
      if (selectedPl?.id === eid) selectedPl = { ...selectedPl, name: editName, description: editDesc };
    } catch (e) { toast.error(e.message); }
  }

  async function removeVideo(videoId) {
    if (!selectedPl) return;
    try {
      await api.removeFromPlaylist(selectedPl.id, videoId);
      plVideos = plVideos.filter(v => v.id !== videoId);
      toast.info('Video entfernt');
    } catch (e) { toast.error(e.message); }
  }

  function playVideo(id) {
    navigate(`/watch/${id}`);
  }

  function playAll(startIdx = 0) {
    if (plVideos.length === 0) return;
    startQueue(selectedPl.id, selectedPl.name, plVideos, startIdx);
    navigate(`/watch/${plVideos[startIdx].id}`);
  }

  function back() { selectedPl = null; plVideos = []; showAddVideo = false; }

  // ─── Drag & Drop Reorder ───
  function onDragStart(e, idx) {
    dragIdx = idx;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', idx.toString());
  }
  function onDragOver(e, idx) { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; dragOverIdx = idx; }
  function onDragLeave() { dragOverIdx = null; }
  async function onDrop(e, idx) {
    e.preventDefault();
    if (dragIdx === null || dragIdx === idx) { dragIdx = null; dragOverIdx = null; return; }
    const moved = plVideos.splice(dragIdx, 1)[0];
    plVideos.splice(idx, 0, moved);
    plVideos = [...plVideos];
    dragIdx = null; dragOverIdx = null;
    try { await api.reorderPlaylist(selectedPl.id, plVideos.map(v => v.id)); }
    catch { toast.error('Sortierung speichern fehlgeschlagen'); }
  }
  function onDragEnd() { dragIdx = null; dragOverIdx = null; }

  // ─── Add Video Search ───
  function onAddSearchInput() {
    clearTimeout(addSearchTimer);
    if (!addSearch.trim()) { addResults = []; return; }
    addSearchTimer = setTimeout(searchVideos, 300);
  }
  async function searchVideos() {
    if (!addSearch.trim()) return;
    addSearching = true;
    try {
      const res = await api.searchLocal(addSearch, { per_page: 20 });
      const existing = new Set(plVideos.map(v => v.id));
      addResults = (res.videos || []).filter(v => !existing.has(v.id));
    } catch { addResults = []; }
    addSearching = false;
  }
  async function addVideoToPlaylist(videoId) {
    if (!selectedPl) return;
    try {
      await api.addToPlaylist(selectedPl.id, videoId);
      addResults = addResults.filter(v => v.id !== videoId);
      toast.success('Hinzugefügt');
      const res = await api.getPlaylist(selectedPl.id);
      plVideos = res.videos || [];
    } catch (e) {
      if (e.message?.includes('bereits')) toast.info('Bereits in Playlist');
      else toast.error(e.message);
    }
  }

  let totalDuration = $derived(plVideos.reduce((s, v) => s + (v.duration || 0), 0));

  $effect(() => { loadPlaylists(); });

  // Auto-open Playlist aus URL ?open=id
  $effect(() => {
    const openId = $route.params.open;
    const autoPlay = $route.params.play === '1';
    if (openId && playlists.length >= 0 && !loading) {
      let pl = playlists.find(p => String(p.id) === String(openId));
      if (pl && selectedPl?.id !== pl.id) {
        (async () => {
          await selectPlaylist(pl);
          if (autoPlay && plVideos.length > 0) playAll(0);
        })();
      } else if (!pl && selectedPl?.id !== Number(openId)) {
        // Playlist nicht in Liste (z.B. channel-only) – direkt laden
        (async () => {
          try {
            const res = await api.getPlaylist(openId);
            if (res) {
              const fakePl = { id: Number(openId), name: res.name || res.title || 'Playlist', ...res };
              await selectPlaylist(fakePl);
              if (autoPlay && plVideos.length > 0) playAll(0);
            }
          } catch { /* Playlist nicht gefunden */ }
        })();
      }
    }
  });
</script>

<div class="playlists-page">
  {#if selectedPl}
    <!-- ═══ Playlist Detail ═══ -->
    <div class="detail-header">
      <button class="btn-back" onclick={back}><i class="fa-solid fa-arrow-left"></i></button>
      <div class="detail-info">
        <h1>{selectedPl.name}</h1>
        {#if selectedPl.description}<p class="detail-desc">{selectedPl.description}</p>{/if}
        <span class="detail-meta">
          {plVideos.length} Video{plVideos.length !== 1 ? 's' : ''}
          {#if totalDuration > 0} · {formatDuration(totalDuration)}{/if}
        </span>
      </div>
      <div class="detail-actions">
        {#if plVideos.length > 0}
          <button class="btn-play-all" onclick={() => playAll(0)}><i class="fa-solid fa-play"></i> Alle abspielen</button>
        {/if}
        <button class="btn-add-video" onclick={() => showAddVideo = !showAddVideo}>
          <i class="fa-solid fa-plus"></i> Video hinzufügen
        </button>
      </div>
    </div>

    <!-- Add Video Panel -->
    {#if showAddVideo}
      <div class="add-video-panel">
        <div class="av-search-box">
          <i class="fa-solid fa-magnifying-glass"></i>
          <input type="text" placeholder="Video in Bibliothek suchen…" bind:value={addSearch} oninput={onAddSearchInput} />
          {#if addSearching}<i class="fa-solid fa-spinner fa-spin"></i>{/if}
        </div>
        {#if addResults.length > 0}
          <div class="av-results">
            {#each addResults as v (v.id)}
              <div class="av-row">
                <div class="av-thumb">
                  <img src={api.thumbnailUrl(v.id)} alt="" loading="lazy" onerror={(e) => e.target.style.display='none'} />
                </div>
                <div class="av-info">
                  <span class="av-title">{v.title}</span>
                  <span class="av-channel">{v.channel_name || '–'}</span>
                </div>
                <button class="av-add-btn" onclick={() => addVideoToPlaylist(v.id)} title="Hinzufügen">
                  <i class="fa-solid fa-plus"></i>
                </button>
              </div>
            {/each}
          </div>
        {:else if addSearch.trim() && !addSearching}
          <div class="av-empty">Keine passenden Videos gefunden.</div>
        {/if}
      </div>
    {/if}

    <!-- Video Liste mit Drag & Drop -->
    {#if plVideos.length === 0}
      <div class="empty">
        <i class="fa-solid fa-music empty-icon"></i>
        <p>Keine Videos in dieser Playlist.</p>
        <p class="empty-hint">Klicke „Video hinzufügen" oder nutze <i class="fa-solid fa-list-ul"></i> im Player.</p>
      </div>
    {:else}
      <div class="pl-video-list">
        {#each plVideos as v, i (v.id)}
          <div class="pl-video-item" class:dragging={dragIdx === i} class:drag-over={dragOverIdx === i}
            draggable="true"
            ondragstart={(e) => onDragStart(e, i)}
            ondragover={(e) => onDragOver(e, i)}
            ondragleave={onDragLeave}
            ondrop={(e) => onDrop(e, i)}
            ondragend={onDragEnd}>
            <span class="pl-drag-handle" title="Zum Sortieren ziehen"><i class="fa-solid fa-grip-vertical"></i></span>
            <span class="pl-index">{i + 1}</span>
            <button class="pl-video-thumb" onclick={() => playAll(i)}>
              <img src={api.thumbnailUrl(v.id)} alt="" loading="lazy" onerror={(e) => e.target.style.display='none'} />
              {#if v.duration}<span class="duration">{formatDuration(v.duration)}</span>{/if}
              {#if v.like_count && v.dislike_count != null}
                <LikeBar likes={v.like_count} dislikes={v.dislike_count} mode="thumbnail" />
              {/if}
            </button>
            <div class="pl-video-info">
              <button class="pl-video-title" onclick={() => playAll(i)}>{v.title}</button>
              <span class="pl-video-channel">{v.channel_name || 'Unbekannt'}</span>
              <div class="pl-video-meta">
                {#if v.view_count}<span>{formatViews(v.view_count)} Aufrufe</span>{/if}
                {#if v.file_size}<span>{formatSize(v.file_size)}</span>{/if}
                {#if v.like_count && v.dislike_count != null}
                  <LikeBar likes={v.like_count} dislikes={v.dislike_count} mode="compact" />
                {/if}
              </div>
            </div>
            <button class="btn-remove" onclick={() => removeVideo(v.id)} title="Entfernen"><i class="fa-solid fa-xmark"></i></button>
          </div>
        {/each}
      </div>
    {/if}

  {:else}
    <!-- ═══ Playlist-Übersicht ═══ -->
    <div class="page-header">
      <h1 class="page-title"><i class="fa-solid fa-list-ul"></i> Playlists</h1>
      <button class="btn-create" onclick={() => showCreate = !showCreate}><i class="fa-solid fa-plus"></i> Neue Playlist</button>
    </div>

    {#if showCreate}
      <div class="create-form">
        <input type="text" placeholder="Name" bind:value={newName} onkeydown={(e) => e.key === 'Enter' && createPlaylist()} />
        <input type="text" placeholder="Beschreibung (optional)" bind:value={newDesc} />
        <div class="create-actions">
          <button class="btn-save" onclick={createPlaylist} disabled={!newName.trim()}>Erstellen</button>
          <button class="btn-cancel" onclick={() => showCreate = false}>Abbrechen</button>
        </div>
      </div>
    {/if}

    {#if loading}
      <div class="loading"><i class="fa-solid fa-spinner fa-spin"></i> Laden…</div>
    {:else if playlists.length === 0}
      <div class="empty">
        <div class="empty-icon"><i class="fa-solid fa-music"></i></div>
        <p>Noch keine Playlists erstellt.</p>
      </div>
    {:else}
      <div class="playlist-grid">
        {#each playlists as pl (pl.id)}
          {#if editingPl === pl.id}
            <div class="playlist-card editing">
              <div class="pl-edit-form">
                <input type="text" class="pl-edit-input" bind:value={editName} placeholder="Name" />
                <input type="text" class="pl-edit-input" bind:value={editDesc} placeholder="Beschreibung" />
                <div class="pl-edit-actions">
                  <button class="btn-xs save" onclick={saveEditPl}><i class="fa-solid fa-check"></i></button>
                  <button class="btn-xs" onclick={() => editingPl = null}><i class="fa-solid fa-xmark"></i></button>
                </div>
              </div>
            </div>
          {:else}
            <div class="playlist-card">
              <div class="pl-cover">
                {#if pl.cover_video_id}
                  <img src={api.thumbnailUrl(pl.cover_video_id)} alt="" onerror={(e) => e.target.style.display='none'} />
                {:else}
                  <div class="pl-cover-fallback"><i class="fa-solid fa-music"></i></div>
                {/if}
                <!-- Hover-Overlay: Feed-Stil (zentrale runde Buttons, weiss auf dunkel) -->
                <div class="card-hover-actions">
                  <button class="hover-action-btn" onclick={() => selectPlaylist(pl)} title="Öffnen">
                    <i class="fa-solid fa-play"></i>
                  </button>
                  <button class="hover-action-btn"
                          class:pinned={$quickPlaylist?.id === pl.id}
                          onclick={(e) => { e.stopPropagation(); togglePin(pl); }}
                          title={$quickPlaylist?.id === pl.id ? 'Quick-Playlist lösen' : 'Als Quick-Playlist pinnen'}>
                    <i class="fa-solid fa-thumbtack"></i>
                  </button>
                  <button class="hover-action-btn" onclick={(e) => { e.stopPropagation(); startEditPl(pl); }} title="Bearbeiten">
                    <i class="fa-solid fa-pen"></i>
                  </button>
                  <button class="hover-action-btn danger" onclick={(e) => { e.stopPropagation(); deletePlaylist(pl.id); }} title="Löschen">
                    <i class="fa-regular fa-trash-can"></i>
                  </button>
                </div>
              </div>
              <button class="pl-card-info" onclick={() => selectPlaylist(pl)}>
                <h3 class="pl-name">{pl.name}</h3>
                {#if pl.description}<p class="pl-desc">{pl.description}</p>{/if}
                <div class="pl-card-meta">
                  <span>{pl.video_count || 0} Videos</span>
                  {#if pl.total_duration}<span>· {formatDuration(pl.total_duration)}</span>{/if}
                  {#if pl.source === 'youtube'}<span class="pl-yt-badge">YouTube</span>{/if}
                </div>
              </button>
            </div>
          {/if}
        {/each}
      </div>
    {/if}
  {/if}
</div>

<style>
  .playlists-page { padding: 24px; max-width: 1000px; }
  .page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
  .page-title { font-size: 1.4rem; font-weight: 700; color: var(--text-primary); margin: 0; display: flex; align-items: center; gap: 10px; }
  .page-title i { color: var(--accent-primary); }
  .btn-create { padding: 7px 18px; background: var(--accent-primary); color: #fff; border: none; border-radius: 8px; font-size: 0.85rem; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 6px; }

  .create-form { display: flex; flex-direction: column; gap: 10px; padding: 16px; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 10px; margin-bottom: 20px; }
  .create-form input { padding: 8px 14px; background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 8px; color: var(--text-primary); font-size: 0.88rem; outline: none; }
  .create-form input:focus { border-color: var(--accent-primary); }
  .create-actions { display: flex; gap: 8px; }
  .btn-save { padding: 7px 18px; background: var(--accent-primary); color: #fff; border: none; border-radius: 8px; font-size: 0.82rem; font-weight: 600; cursor: pointer; }
  .btn-save:disabled { opacity: 0.4; }
  .btn-cancel { padding: 7px 18px; background: none; border: 1px solid var(--border-primary); border-radius: 8px; color: var(--text-secondary); font-size: 0.82rem; cursor: pointer; }

  /* Playlist Grid */
  .playlist-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 14px; }
  .playlist-card { position: relative; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 12px; overflow: hidden; transition: all 0.15s; display: flex; flex-direction: column; }
  .playlist-card:hover { border-color: var(--accent-primary); }
  .playlist-card.editing { padding: 14px; }
  .pl-cover { position: relative; aspect-ratio: 16/9; background: var(--bg-tertiary); overflow: hidden; }
  .pl-cover img { width: 100%; height: 100%; object-fit: cover; }
  .pl-cover-fallback { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 2.5rem; color: var(--text-tertiary); }
  /* .card-hover-actions / .hover-action-btn – zentral in global.css (Feed-Stil) */
  .pl-card-info { padding: 12px 14px; background: none; border: none; cursor: pointer; text-align: left; width: 100%; color: inherit; display: flex; flex-direction: column; gap: 3px; }
  .pl-name { font-size: 0.92rem; font-weight: 600; color: var(--text-primary); margin: 0 0 2px; }
  .pl-desc { font-size: 0.76rem; color: var(--text-tertiary); margin: 0 0 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pl-card-meta { display: flex; gap: 4px; font-size: 0.72rem; color: var(--text-tertiary); }
  .pl-yt-badge { padding: 0 5px; background: var(--status-error); color: #fff; font-size: 0.6rem; border-radius: 3px; font-weight: 600; }
  .pl-edit-form { display: flex; flex-direction: column; gap: 8px; }
  .pl-edit-input { padding: 6px 10px; background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 6px; color: var(--text-primary); font-size: 0.85rem; }
  .pl-edit-actions { display: flex; gap: 4px; }
  .btn-xs { padding: 4px 10px; background: none; border: 1px solid var(--border-primary); border-radius: 6px; cursor: pointer; font-size: 0.82rem; color: var(--text-secondary); }
  .btn-xs.save { color: var(--status-success); border-color: var(--status-success); }

  /* Detail */
  .detail-header { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
  .btn-back { width: 36px; height: 36px; border-radius: 8px; background: none; border: 1px solid var(--border-primary); color: var(--text-secondary); cursor: pointer; display: flex; align-items: center; justify-content: center; }
  .btn-back:hover { border-color: var(--accent-primary); }
  .detail-info { flex: 1; }
  .detail-info h1 { font-size: 1.3rem; font-weight: 700; color: var(--text-primary); margin: 0 0 2px; }
  .detail-desc { font-size: 0.82rem; color: var(--text-secondary); margin: 0 0 2px; }
  .detail-meta { font-size: 0.78rem; color: var(--text-tertiary); }
  .detail-actions { display: flex; gap: 8px; flex-wrap: wrap; }
  .btn-play-all { padding: 8px 20px; background: var(--accent-primary); color: #fff; border: none; border-radius: 8px; font-size: 0.85rem; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 6px; }
  .btn-add-video { padding: 8px 16px; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 8px; font-size: 0.82rem; color: var(--text-secondary); cursor: pointer; display: flex; align-items: center; gap: 6px; }
  .btn-add-video:hover { border-color: var(--accent-primary); color: var(--accent-primary); }

  /* Add Video Panel */
  .add-video-panel { padding: 12px 14px; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 10px; margin-bottom: 14px; }
  .av-search-box { display: flex; align-items: center; gap: 8px; background: var(--bg-tertiary); border: 1px solid var(--border-primary); border-radius: 8px; padding: 6px 12px; }
  .av-search-box:focus-within { border-color: var(--accent-primary); }
  .av-search-box i { color: var(--text-tertiary); font-size: 0.8rem; }
  .av-search-box input { flex: 1; background: none; border: none; color: var(--text-primary); font-size: 0.85rem; outline: none; }
  .av-results { margin-top: 8px; max-height: 250px; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
  .av-row { display: flex; align-items: center; gap: 10px; padding: 5px 6px; border-radius: 6px; transition: background 0.1s; }
  .av-row:hover { background: var(--bg-tertiary); }
  .av-thumb { width: 64px; min-width: 64px; aspect-ratio: 16/9; border-radius: 4px; overflow: hidden; background: var(--bg-tertiary); }
  .av-thumb img { width: 100%; height: 100%; object-fit: cover; }
  .av-info { flex: 1; min-width: 0; }
  .av-title { font-size: 0.82rem; font-weight: 500; color: var(--text-primary); display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .av-channel { font-size: 0.72rem; color: var(--text-tertiary); }
  .av-add-btn { width: 30px; height: 30px; border-radius: 6px; background: var(--accent-primary); color: #fff; border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; flex-shrink: 0; }
  .av-empty { padding: 12px; text-align: center; font-size: 0.82rem; color: var(--text-tertiary); }

  /* Video List */
  .pl-video-list { display: flex; flex-direction: column; gap: 2px; }
  .pl-video-item { display: flex; align-items: center; gap: 10px; padding: 6px 8px; border-radius: 8px; transition: all 0.1s; border: 1px solid transparent; }
  .pl-video-item:hover { background: var(--bg-secondary); }
  .pl-video-item.dragging { opacity: 0.4; }
  .pl-video-item.drag-over { border-color: var(--accent-primary); background: rgba(99, 102, 241, 0.05); }
  .pl-drag-handle { cursor: grab; color: var(--text-tertiary); font-size: 0.82rem; padding: 4px; opacity: 0.3; transition: opacity 0.1s; }
  .pl-video-item:hover .pl-drag-handle { opacity: 1; }
  .pl-drag-handle:active { cursor: grabbing; }
  .pl-index { font-size: 0.78rem; color: var(--text-tertiary); width: 22px; text-align: center; flex-shrink: 0; }
  .pl-video-thumb { position: relative; width: 110px; min-width: 110px; aspect-ratio: 16/9; border-radius: 6px; overflow: hidden; background: var(--bg-tertiary); border: none; cursor: pointer; }
  .pl-video-thumb img { width: 100%; height: 100%; object-fit: cover; }
  .duration { position: absolute; bottom: 4px; right: 4px; background: rgba(0,0,0,0.8); color: #fff; font-size: 0.62rem; padding: 1px 4px; border-radius: 3px; }
  .pl-video-info { flex: 1; min-width: 0; }
  .pl-video-title { display: block; font-size: 0.85rem; font-weight: 600; color: var(--text-primary); background: none; border: none; cursor: pointer; text-align: left; padding: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; width: 100%; }
  .pl-video-title:hover { color: var(--accent-primary); }
  .pl-video-channel { font-size: 0.74rem; color: var(--text-tertiary); }
  .pl-video-meta { display: flex; gap: 6px; font-size: 0.68rem; color: var(--text-tertiary); align-items: center; margin-top: 2px; }
  .btn-remove { background: none; border: none; color: var(--text-tertiary); cursor: pointer; font-size: 0.82rem; opacity: 0; transition: opacity 0.1s; padding: 4px 8px; }
  .pl-video-item:hover .btn-remove { opacity: 0.7; }
  .btn-remove:hover { opacity: 1; color: var(--status-error); }

  .loading, .empty { padding: 50px 20px; text-align: center; color: var(--text-tertiary); font-size: 0.9rem; }
  .empty-icon { font-size: 2.5rem; color: var(--text-tertiary); margin-bottom: 12px; display: block; }
  .empty-hint { font-size: 0.78rem; color: var(--text-tertiary); margin-top: 4px; }
</style>

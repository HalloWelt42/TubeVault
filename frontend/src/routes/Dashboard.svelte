<!--
  TubeVault
  © HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
  SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
-->
<script>
  import { api } from '../lib/api/client.js';
  import { navigate } from '../lib/router/router.js';
  import { pendingDownloadUrl } from '../lib/stores/app.js';
  import { toast } from '../lib/stores/notifications.js';
  import { formatDuration } from '../lib/utils/format.js';
  import VideoCard from '../lib/components/video/VideoCard.svelte';
  import { shortcuts } from '../lib/stores/keyboard.js';

  let stats = $state(null);
  let videos = $state([]);
  let continueWatching = $state([]);
  let downloadUrl = $state('');
  let downloading = $state(false);
  let showShortcuts = $state(false);

  async function loadData() {
    try {
      const [s, v, h] = await Promise.all([
        api.getStats(),
        api.getVideos({ per_page: 8, sort_by: 'created_at', sort_order: 'desc' }),
        api.getHistory({ per_page: 6, in_progress: true }).catch(() => ({ videos: [] })),
      ]);
      stats = s;
      videos = v.videos;
      continueWatching = (h.videos || []).filter(v => v.last_position > 5 && v.duration && v.last_position < v.duration - 10).slice(0, 6);
    } catch (e) {
      toast.error('Dashboard laden fehlgeschlagen');
    }
  }

  async function startDownload() {
    if (!downloadUrl.trim()) return;
    const url = downloadUrl.trim();
    // Playlist/Kanal-URLs zur Downloads-Seite weiterleiten (brauchen Resolver)
    if (/[?&]list=/.test(url) || /\/playlist\?/.test(url) || /\/@[a-zA-Z0-9_.-]+/.test(url) || /\/channel\//.test(url) || /\/c\//.test(url)) {
      pendingDownloadUrl.set(url);
      navigate('/downloads');
      downloadUrl = '';
      return;
    }
    downloading = true;
    try {
      const result = await api.addDownload({ url, quality: 'best' });
      toast.success(`Download gestartet: ${result.video_id}`);
      downloadUrl = '';
      setTimeout(loadData, 3000);
    } catch (e) {
      toast.error('Download-Fehler: ' + e.message);
    }
    downloading = false;
  }

  function play(id) { navigate(`/watch/${id}`); }

  $effect(() => { loadData(); });

  $effect(() => {
    function onShowShortcuts() { showShortcuts = !showShortcuts; }
    window.addEventListener('tubevault:show-shortcuts', onShowShortcuts);
    return () => window.removeEventListener('tubevault:show-shortcuts', onShowShortcuts);
  });

  const shortcutLabels = {
    d: 'Dashboard', b: 'Bibliothek', s: 'Suche', h: 'Verlauf',
    p: 'Playlists', f: 'Favoriten', k: 'Kategorien', o: 'Downloads',
    t: 'Statistiken', e: 'Einstellungen',
  };
</script>

<div class="dashboard">
  <div class="welcome-section">
    <h1 class="page-title">Dashboard</h1>
    <p class="page-subtitle">Willkommen bei TubeVault</p>
  </div>

  <!-- Quick Download -->
  <div class="download-bar">
    <div class="download-input-wrap">
      <i class="fa-solid fa-link" style="color:var(--text-tertiary)"></i>
      <input type="text" class="download-input" placeholder="YouTube-URL einfügen…"
             bind:value={downloadUrl} onkeydown={(e) => e.key === 'Enter' && startDownload()}
             disabled={downloading} />
      <button class="btn-download" onclick={startDownload} disabled={downloading || !downloadUrl.trim()}>
        {downloading ? 'Lädt…' : 'Download'}
      </button>
    </div>
  </div>

  <!-- Weiterschauen (prominent, direkt nach Download-Bar) -->
  {#if continueWatching.length > 0}
    <div class="section continue-section">
      <div class="section-header">
        <h2 class="section-title"><i class="fa-solid fa-play"></i> Weiterschauen</h2>
        <button class="btn-link" onclick={() => navigate('/history')}>Verlauf <i class="fa-solid fa-arrow-right"></i></button>
      </div>
      <div class="continue-grid">
        {#each continueWatching as v}
          <button class="continue-card" onclick={() => play(v.id)}>
            <div class="continue-thumb">
              <img src={api.thumbnailUrl(v.id)} alt="" loading="lazy" onerror={(e) => e.target.style.display='none'} />
              <div class="progress-bar"><div class="progress-fill" style="width: {Math.round((v.last_position / v.duration) * 100)}%"></div></div>
              <span class="resume-badge"><i class="fa-solid fa-play"></i> {formatDuration(v.last_position)}</span>
            </div>
            <span class="continue-title">{v.title}</span>
          </button>
        {/each}
      </div>
    </div>
  {/if}

  <!-- Stats -->
  {#if stats}
    <div class="stats-grid">
      <div class="stat-card accent"><span class="stat-value">{stats.total_videos || 0}</span><span class="stat-label">Videos</span></div>
      <div class="stat-card"><span class="stat-value">{stats.total_size_human || '0 B'}</span><span class="stat-label">Belegt</span></div>
      {#if stats.storage_split}
        <div class="stat-card storage-split">
          <div class="storage-row">
            <span class="storage-label">Medien</span>
            <span class="storage-value">{stats.disk_media?.free_human || '–'} frei</span>
            <div class="storage-bar">
              <div class="storage-fill media" style="width:{stats.disk_media?.percent || 0}%"></div>
            </div>
          </div>
          <div class="storage-row">
            <span class="storage-label">System</span>
            <span class="storage-value">{stats.disk_meta?.free_human || '–'} frei</span>
            <div class="storage-bar">
              <div class="storage-fill meta" style="width:{stats.disk_meta?.percent || 0}%"></div>
            </div>
          </div>
        </div>
      {:else}
        <div class="stat-card"><span class="stat-value">{stats.disk?.free_human || '–'}</span><span class="stat-label">Frei</span></div>
      {/if}
      <div class="stat-card">
        <span class="stat-value">{stats.download_queue_active || 0}/{stats.download_queue_pending || 0}</span>
        <span class="stat-label">Downloads aktiv/wartend</span>
      </div>
      <div class="stat-card"><span class="stat-value">{stats.total_subscriptions || 0}</span><span class="stat-label">Abos</span></div>
    </div>
  {/if}

  <!-- Quick Actions -->
  <div class="quick-actions">
    <button class="qa-btn" onclick={() => { const el = document.querySelector('.sd-input'); if (el) el.focus(); }}><i class="fa-solid fa-magnifying-glass"></i> YouTube durchsuchen</button>
    <button class="qa-btn" onclick={() => navigate('/downloads')}><i class="fa-solid fa-download"></i> Downloads</button>
    <button class="qa-btn" onclick={() => navigate('/playlists')}><i class="fa-solid fa-music"></i> Playlists</button>
    <button class="qa-btn" onclick={() => navigate('/stats')}><i class="fa-solid fa-chart-simple"></i> Statistiken</button>
    <button class="qa-btn" onclick={() => showShortcuts = !showShortcuts}><i class="fa-regular fa-keyboard"></i> Tastenkürzel</button>
  </div>

  <!-- Shortcuts Modal -->
  {#if showShortcuts}
    <div class="shortcuts-panel">
      <div class="shortcuts-header">
        <h3><i class="fa-regular fa-keyboard"></i> Tastenkürzel</h3>
        <button class="btn-close" title="Schließen" onclick={() => showShortcuts = false}><i class="fa-solid fa-xmark"></i></button>
      </div>
      <div class="shortcuts-grid">
        {#each Object.entries(shortcutLabels) as [key, label]}
          <div class="shortcut-item">
            <kbd>Alt + {key.toUpperCase()}</kbd>
            <span>{label}</span>
          </div>
        {/each}
        <div class="shortcut-item"><kbd>Ctrl + K</kbd><span>Suche fokussieren</span></div>
        <div class="shortcut-item"><kbd>Esc</kbd><span>Suche leeren</span></div>
        <div class="shortcut-item"><kbd>?</kbd><span>Shortcuts anzeigen</span></div>
      </div>
    </div>
  {/if}

  <!-- Continue Watching -->
  <!-- Letzte Videos -->
  {#if videos.length > 0}
    <div class="section">
      <div class="section-header">
        <h2 class="section-title">Zuletzt heruntergeladen</h2>
        <button class="btn-link" onclick={() => navigate('/library')}>Alle <i class="fa-solid fa-arrow-right"></i></button>
      </div>
      <div class="video-grid">
        {#each videos as video (video.id)}
          <VideoCard {video} />
        {/each}
      </div>
    </div>
  {:else}
    <div class="empty-state">
      <i class="fa-solid fa-video" style="font-size:4rem; color:var(--text-tertiary)"></i>
      <h3>Noch keine Videos</h3>
      <p>Füge eine YouTube-URL oben ein, um dein erstes Video herunterzuladen.</p>
    </div>
  {/if}
</div>

<style>
  .dashboard { padding: 24px; max-width: 1200px; }
  .page-title { font-size: 1.6rem; font-weight: 700; color: var(--text-primary); margin: 0; }
  .page-subtitle { color: var(--text-secondary); margin: 4px 0 0; font-size: 0.9rem; }

  .download-bar { margin: 20px 0; }
  .download-input-wrap {
    display: flex; align-items: center; gap: 10px;
    background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 12px; padding: 8px 12px;
  }
  .download-input-wrap:focus-within { border-color: var(--accent-primary); }
  .download-input { flex: 1; background: none; border: none; color: var(--text-primary); font-size: 0.9rem; outline: none; }
  .download-input::placeholder { color: var(--text-tertiary); }
  .btn-download {
    padding: 8px 20px; background: var(--accent-primary); color: #fff; border: none;
    border-radius: 8px; font-size: 0.85rem; font-weight: 600; cursor: pointer; flex-shrink: 0;
  }
  .btn-download:disabled { opacity: 0.5; cursor: not-allowed; }

  .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 20px; }
  .stat-card {
    background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 10px; padding: 14px 16px; display: flex; flex-direction: column; gap: 2px;
  }
  .stat-card.accent { border-color: var(--accent-primary); }
  .stat-value { font-size: 1.2rem; font-weight: 700; color: var(--text-primary); }
  .stat-label { font-size: 0.72rem; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.03em; }

  .stat-card.storage-split { grid-column: span 2; gap: 8px; }
  .storage-row { display: flex; align-items: center; gap: 8px; }
  .storage-label { font-size: 0.72rem; color: var(--text-tertiary); font-weight: 600; text-transform: uppercase; width: 52px; flex-shrink: 0; }
  .storage-value { font-size: 0.78rem; color: var(--text-primary); font-weight: 600; min-width: 80px; }
  .storage-bar { flex: 1; height: 6px; background: var(--bg-tertiary); border-radius: 3px; overflow: hidden; }
  .storage-fill { height: 100%; border-radius: 3px; transition: width 0.3s; }
  .storage-fill.media { background: var(--accent-primary); }
  .storage-fill.meta { background: #8b5cf6; }

  /* Quick Actions */
  .quick-actions { display: flex; gap: 8px; margin-bottom: 24px; flex-wrap: wrap; }
  .qa-btn {
    padding: 7px 14px; background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 8px; color: var(--text-primary); font-size: 0.82rem; cursor: pointer; transition: all 0.12s;
  }
  .qa-btn:hover { border-color: var(--accent-primary); color: var(--accent-primary); }

  /* Shortcuts */
  .shortcuts-panel {
    background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 12px; padding: 16px 20px; margin-bottom: 20px;
  }
  .shortcuts-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
  .shortcuts-header h3 { margin: 0; font-size: 0.95rem; color: var(--text-primary); }
  .btn-close { background: none; border: none; color: var(--text-tertiary); cursor: pointer; font-size: 0.9rem; }
  .shortcuts-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 6px; }
  .shortcut-item { display: flex; align-items: center; gap: 10px; font-size: 0.82rem; color: var(--text-secondary); }
  kbd {
    display: inline-block; padding: 2px 7px; background: var(--bg-tertiary);
    border: 1px solid var(--border-primary); border-radius: 4px;
    font-family: monospace; font-size: 0.75rem; color: var(--text-primary); min-width: 70px; text-align: center;
  }

  /* Continue Watching */
  .continue-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
  .continue-card {
    display: flex; flex-direction: column; background: none; border: none; cursor: pointer;
    text-align: left; color: inherit; gap: 6px;
  }
  .continue-thumb {
    position: relative; aspect-ratio: 16/9; border-radius: 8px; overflow: hidden;
    background: var(--bg-tertiary);
  }
  .continue-thumb img { width: 100%; height: 100%; object-fit: cover; }
  .progress-bar {
    position: absolute; bottom: 0; left: 0; right: 0; height: 4px;
    background: rgba(255,255,255,0.3);
  }
  .progress-fill { height: 100%; background: var(--accent-primary); border-radius: 0 2px 2px 0; }
  .resume-badge {
    position: absolute; bottom: 8px; right: 8px;
    background: rgba(0,0,0,0.8); color: #fff; font-size: 0.68rem;
    padding: 1px 6px; border-radius: 4px; font-weight: 600;
  }
  .continue-title {
    font-size: 0.82rem; font-weight: 500; color: var(--text-primary);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }

  .section { margin-bottom: 28px; }
  .continue-section {
    background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 12px; padding: 16px 18px; margin-bottom: 24px;
  }
  .section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
  .section-title { font-size: 1.05rem; font-weight: 600; color: var(--text-primary); margin: 0; }
  .btn-link { background: none; border: none; color: var(--accent-primary); cursor: pointer; font-size: 0.82rem; }
  .btn-link:hover { text-decoration: underline; }

  .video-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }

  .empty-state {
    display: flex; flex-direction: column; align-items: center;
    padding: 60px 20px; text-align: center; color: var(--text-tertiary);
  }
  .empty-state h3 { margin: 16px 0 8px; color: var(--text-secondary); font-size: 1.1rem; }
  .empty-state p { font-size: 0.9rem; max-width: 400px; }
</style>

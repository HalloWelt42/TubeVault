<script>
  /**
   * TubeVault -  VideoCard v1.6.18
   * Typ-Badges klickbar (video→short→live), Like/Dislike Bar, QPL.
   * © HalloWelt42 -  Private Nutzung
   */
  import { api } from '../../api/client.js';
  import { navigate } from '../../router/router.js';
  import { toast } from '../../stores/notifications.js';
  import { formatDuration, formatSize, formatDateRelative, formatViews } from '../../utils/format.js';
  import LikeBar from '../common/LikeBar.svelte';
  import QuickPlaylistBtn from '../common/QuickPlaylistBtn.svelte';

  let { video, showArchiveBtn = true, onUpdate = null } = $props();
  let hidden = $state(false);

  function play() {
    navigate(`/watch/${video.id}`);
  }

  async function archiveVideo(e) {
    e.stopPropagation();
    try {
      await api.archiveVideo(video.id);
      hidden = true;
      toast.success('Archiviert');
    } catch (err) { toast.error(err.message); }
  }

  async function cycleType(e) {
    e.stopPropagation();
    const current = video.video_type || 'video';
    const order = ['video', 'short', 'live'];
    const next = order[(order.indexOf(current) + 1) % order.length];
    try {
      await api.setVideoType(video.id, next);
      video.video_type = next;
      const labels = { video: 'Video', short: 'Short', live: 'Live' };
      toast.success(`Typ → ${labels[next]}`);
      onUpdate?.();
    } catch (err) { toast.error(err.message); }
  }
</script>

{#if !hidden}
<div class="card-wrap">
  <button class="video-card" onclick={play}>
  <div class="thumbnail-wrap">
    <img
      class="thumbnail"
      src={api.thumbnailUrl(video.id)}
      alt={video.title}
      loading="lazy"
      onerror={(e) => e.target.style.display = 'none'}
    />
    <span class="duration-badge">{formatDuration(video.duration)}</span>
    {#if video.status !== 'ready'}
      <span class="status-badge status-{video.status}">{video.status}</span>
    {/if}
    {#if video.video_type === 'short'}
      <button class="type-badge type-short" onclick={cycleType} title="Klick: Typ ändern (Short → Live → Video)"><i class="fa-solid fa-mobile-screen"></i> Short</button>
    {:else if video.video_type === 'live'}
      <button class="type-badge type-live" onclick={cycleType} title="Klick: Typ ändern (Live → Video → Short)"><i class="fa-solid fa-tower-broadcast"></i> Live</button>
    {:else}
      <button class="type-badge type-video" onclick={cycleType} title="Klick: Typ ändern (Video → Short → Live)"><i class="fa-solid fa-play"></i> Video</button>
    {/if}
    <!-- Like/Dislike Thumbnail-Bar (Variante E) -->
    {#if video.like_count && video.dislike_count != null}
      <LikeBar likes={video.like_count} dislikes={video.dislike_count} mode="thumbnail" />
    {/if}
  </div>
  <div class="video-info">
    <h3 class="video-title">{video.title}</h3>
    <span class="video-channel">{video.channel_name || 'Unbekannt'}</span>
    <div class="video-meta">
      <span>{formatViews(video.view_count)} Aufrufe</span>
      <span class="meta-dot">·</span>
      <span>{formatSize(video.file_size)}</span>
      {#if video.like_count && video.dislike_count != null}
        <span class="meta-dot">·</span>
        <LikeBar likes={video.like_count} dislikes={video.dislike_count} mode="compact" />
      {/if}
    </div>
  </div>
</button>
  {#if showArchiveBtn && !video.is_archived}
    <button class="btn-archive" onclick={archiveVideo} title="Archivieren">
      <i class="fa-solid fa-box-archive"></i>
    </button>
  {/if}
  <div class="btn-qpl-overlay">
    <QuickPlaylistBtn videoId={video.id} title={video.title} channelName={video.channel_name} channelId={video.channel_id} size="sm" />
  </div>
</div>
{/if}

<style>
  .card-wrap { position: relative; }
  .btn-archive {
    position: absolute; top: 8px; right: 8px; z-index: 3;
    width: 28px; height: 28px; border-radius: 50%;
    background: rgba(0,0,0,0.7); color: #fff; border: none;
    cursor: pointer; font-size: 0.7rem; display: flex;
    align-items: center; justify-content: center;
    opacity: 0; transition: opacity 0.15s;
  }
  .card-wrap:hover .btn-archive { opacity: 1; }
  .btn-archive:hover { background: var(--accent-primary); }

  .btn-qpl-overlay {
    position: absolute; top: 8px; left: 8px; z-index: 3;
    opacity: 0; transition: opacity 0.15s;
  }
  .card-wrap:hover .btn-qpl-overlay { opacity: 1; }

  .video-card {
    display: flex; flex-direction: column; background: var(--bg-secondary);
    border: 1px solid var(--border-primary); border-radius: 12px;
    overflow: hidden; cursor: pointer; transition: all 0.2s;
    text-align: left; color: inherit;
  }
  .video-card:hover {
    border-color: var(--accent-primary); transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0,0,0,0.15);
  }
  .thumbnail-wrap { position: relative; aspect-ratio: 16/9; background: var(--bg-tertiary); overflow: hidden; }
  .thumbnail { width: 100%; height: 100%; object-fit: cover; }
  .duration-badge {
    position: absolute; bottom: 8px; right: 8px; background: rgba(0,0,0,0.8);
    color: #fff; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; font-family: monospace;
  }
  .status-badge {
    position: absolute; top: 8px; left: 8px; padding: 2px 8px; border-radius: 4px;
    font-size: 0.72rem; font-weight: 600; text-transform: uppercase;
  }
  .status-pending { background: var(--status-pending); color: #fff; }
  .status-downloading { background: var(--status-info); color: #fff; }
  .status-error { background: var(--status-error); color: #fff; }
  .type-badge {
    position: absolute; top: 8px; right: 8px; padding: 2px 8px; border-radius: 4px;
    font-size: 0.68rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.03em; display: flex; align-items: center; gap: 4px;
    border: none; cursor: pointer; transition: opacity 0.15s, transform 0.1s;
  }
  .type-badge:hover { transform: scale(1.05); }
  .type-short { background: rgba(171, 71, 188, 0.9); color: #fff; }
  .type-live { background: rgba(244, 67, 54, 0.9); color: #fff; }
  .type-video { background: rgba(100, 100, 100, 0.6); color: #fff; opacity: 0; transition: opacity 0.15s; }
  .card-wrap:hover .type-video { opacity: 1; }
  .video-info { padding: 12px; display: flex; flex-direction: column; gap: 4px; }
  .video-title {
    font-size: 0.9rem; font-weight: 600; color: var(--text-primary); margin: 0;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    overflow: hidden; line-height: 1.3;
  }
  .video-channel { font-size: 0.8rem; color: var(--text-secondary); }
  .video-meta { display: flex; align-items: center; gap: 5px; font-size: 0.75rem; color: var(--text-tertiary); flex-wrap: wrap; }
  .meta-dot { opacity: 0.5; }
</style>

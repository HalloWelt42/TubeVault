<!--
  VideoLinkDialog -  Beschreibungs-Video-Links verknüpfen.
  Öffnet Such-Dialog mit vorausgefüllter Video-ID.
  Prüft lokal → RSS → YouTube, erstellt Verknüpfung.
  © HalloWelt42
-->
<script>
  import { api } from '../../api/client.js';
  import { navigate } from '../../router/router.js';
  import { toast } from '../../stores/notifications.js';
  import RssSearchPicker from '../common/RssSearchPicker.svelte';
  import YouTubeSearchPicker from '../common/YouTubeSearchPicker.svelte';

  let { dialog = $bindable(null), parentVideoId = '', onLinked = () => {}, onVideoOpen = () => {} } = $props();

  let activeTab = $state('rss');

  async function lookup(videoId) {
    dialog = { videoId, status: 'loading', result: null, tab: 'auto' };
    activeTab = 'rss';

    // 1. Schon in Bibliothek?
    try {
      const local = await api.getVideo(videoId);
      if (local?.id && local.status === 'ready') {
        dialog = { videoId, status: 'found_local', result: local, tab: 'auto' };
        if (parentVideoId) {
          await api.createVideoLink(parentVideoId, videoId);
          onLinked();
        }
        return;
      }
    } catch { /* nicht lokal */ }

    // 2. Im RSS?
    try {
      const rss = await api.searchRss(videoId);
      if (rss?.entries?.length > 0) {
        dialog = { videoId, status: 'found_rss', result: rss.entries[0], tab: 'auto' };
        return;
      }
    } catch { /* nicht in RSS */ }

    // 3. Nicht gefunden → Such-Dialog
    dialog = { videoId, status: 'search', result: null, tab: 'search' };
  }

  function openVideo() {
    if (!dialog) return;
    navigate(`/watch/${dialog.videoId}`);
    dialog = null;
    onVideoOpen();
  }

  async function downloadAndLink() {
    if (!dialog) return;
    const vid = dialog.videoId;
    api.addDownload({ url: `https://www.youtube.com/watch?v=${vid}` });
    if (parentVideoId) {
      await api.createVideoLink(parentVideoId, vid);
      onLinked();
    }
    toast.success('Download gestartet + verknüpft');
    dialog = null;
  }

  async function handleSearchSelect(video) {
    if (!dialog) return;
    const linkedId = video.id || video.video_id;
    if (!linkedId) return;

    if (parentVideoId) {
      await api.createVideoLink(parentVideoId, linkedId);
      onLinked();
    }

    try {
      const local = await api.getVideo(linkedId);
      if (local?.id && local.status === 'ready') {
        toast.success(`Verknüpft: ${local.title}`);
        dialog = null;
        return;
      }
    } catch { /* */ }

    api.addDownload({ url: `https://www.youtube.com/watch?v=${linkedId}` });
    toast.success('Download gestartet + verknüpft');
    dialog = null;
  }

  function close() { dialog = null; }

  export { lookup };
</script>

{#if dialog}
  <div class="overlay" onclick={close} role="presentation">
    <div class="vld" onclick={(e) => e.stopPropagation()} role="dialog">
      <div class="vld-header">
        <h3><i class="fa-solid fa-link"></i> Video verknüpfen</h3>
        <button class="vld-close" onclick={close}><i class="fa-solid fa-xmark"></i></button>
      </div>

      <div class="vld-id">
        <code>{dialog.videoId}</code>
        <a href="https://www.youtube.com/watch?v={dialog.videoId}" target="_blank" rel="noopener" class="vld-yt">
          <i class="fa-brands fa-youtube"></i>
        </a>
      </div>

      {#if dialog.status === 'loading'}
        <div class="vld-center"><i class="fa-solid fa-spinner fa-spin"></i> Suche…</div>

      {:else if dialog.status === 'found_local'}
        <div class="vld-result">
          <div class="vld-badge ok"><i class="fa-solid fa-check-circle"></i> In Bibliothek -  automatisch verknüpft</div>
          <div class="vld-video">
            {#if dialog.result.thumbnail_path}
              <img src="/api/player/{dialog.videoId}/thumbnail" alt="" class="vld-thumb">
            {/if}
            <div class="vld-meta">
              <strong>{dialog.result.title}</strong>
              {#if dialog.result.channel_name}<span>{dialog.result.channel_name}</span>{/if}
            </div>
          </div>
          <div class="vld-actions">
            <button class="btn-primary" onclick={openVideo}><i class="fa-solid fa-play"></i> Öffnen</button>
            <button class="btn-ghost" onclick={close}>Schließen</button>
          </div>
        </div>

      {:else if dialog.status === 'found_rss'}
        <div class="vld-result">
          <div class="vld-badge rss"><i class="fa-solid fa-rss"></i> Im RSS-Katalog</div>
          <div class="vld-video">
            <div class="vld-meta">
              <strong>{dialog.result.title}</strong>
              {#if dialog.result.channel_name}<span>{dialog.result.channel_name}</span>{/if}
            </div>
          </div>
          <div class="vld-actions">
            <button class="btn-primary" onclick={downloadAndLink}><i class="fa-solid fa-download"></i> Herunterladen + Verknüpfen</button>
          </div>
        </div>

      {:else if dialog.status === 'search'}
        <div class="vld-tabs">
          <button class="vld-tab" class:active={activeTab==='rss'} onclick={() => activeTab='rss'}>
            <i class="fa-solid fa-rss"></i> RSS
          </button>
          <button class="vld-tab" class:active={activeTab==='yt'} onclick={() => activeTab='yt'}>
            <i class="fa-brands fa-youtube"></i> YouTube
          </button>
        </div>
        <div class="vld-picker">
          {#if activeTab === 'rss'}
            <RssSearchPicker initialQuery={dialog.videoId} onSelect={handleSearchSelect} />
          {:else}
            <YouTubeSearchPicker initialQuery={dialog.videoId} onSelect={handleSearchSelect} />
          {/if}
        </div>
        <div class="vld-actions">
          <button class="btn-ghost" onclick={downloadAndLink}>
            <i class="fa-solid fa-download"></i> Direkt herunterladen ({dialog.videoId})
          </button>
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .vld {
    background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 14px;
    padding: 20px; width: 520px; max-width: 95vw; max-height: 85vh; overflow-y: auto;
    box-shadow: 0 16px 48px rgba(0,0,0,0.4);
  }
  .vld-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
  .vld-header h3 { margin: 0; font-size: 1rem; display: flex; align-items: center; gap: 8px; }
  .vld-close { background: none; border: none; color: var(--text-tertiary); cursor: pointer; font-size: 1.1rem; padding: 4px; }
  .vld-close:hover { color: var(--text-primary); }
  .vld-id { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; padding: 6px 12px; background: var(--bg-secondary); border-radius: 8px; }
  .vld-id code { font-size: 0.82rem; color: var(--text-secondary); flex: 1; font-family: monospace; }
  .vld-yt { color: #ff0000; font-size: 1rem; }
  .vld-yt:hover { opacity: 0.7; }
  .vld-center { text-align: center; padding: 24px; color: var(--text-tertiary); }
  .vld-badge { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 6px; font-size: 0.78rem; font-weight: 600; margin-bottom: 12px; }
  .vld-badge.ok { background: rgba(34,197,94,0.1); color: var(--status-success, #22c55e); }
  .vld-badge.rss { background: rgba(59,130,246,0.1); color: var(--accent-primary); }
  .vld-video { display: flex; gap: 10px; align-items: flex-start; margin-bottom: 14px; }
  .vld-thumb { width: 120px; height: 68px; border-radius: 6px; object-fit: cover; flex-shrink: 0; }
  .vld-meta { flex: 1; }
  .vld-meta strong { display: block; font-size: 0.88rem; color: var(--text-primary); line-height: 1.3; }
  .vld-meta span { font-size: 0.76rem; color: var(--text-tertiary); }
  .vld-actions { display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; margin-top: 12px; }
  .vld-tabs { display: flex; gap: 4px; margin-bottom: 12px; }
  .vld-tab { padding: 6px 14px; border: 1px solid var(--border-primary); border-radius: 6px; background: var(--bg-secondary); color: var(--text-secondary); cursor: pointer; font-size: 0.8rem; display: flex; align-items: center; gap: 5px; }
  .vld-tab.active { background: var(--accent-primary); color: #fff; border-color: var(--accent-primary); }
  .vld-picker { min-height: 150px; max-height: 300px; overflow-y: auto; }
</style>

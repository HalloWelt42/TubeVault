<script>
  import { api, createActivitySocket } from '../lib/api/client.js';
  import { route, navigate, updateParams } from '../lib/router/router.js';
  import { toast } from '../lib/stores/notifications.js';
  import { getSettingNum, getSettingBool } from '../lib/stores/settings.js';
  import { formatDuration, formatSize, formatDate, formatViews, formatStreamSize, truncate } from '../lib/utils/format.js';
  import { formatDescription, parseDescClick } from '../lib/utils/description.js';
  import { marked } from 'marked';
  import ChapterPanel from '../lib/components/watch/ChapterPanel.svelte';
  import AdMarkerPanel from '../lib/components/watch/AdMarkerPanel.svelte';
  import SubtitlePanel from '../lib/components/watch/SubtitlePanel.svelte';
  import SubtitleLiveSidebar from '../lib/components/watch/SubtitleLiveSidebar.svelte';
  import NotesSidebar from '../lib/components/watch/NotesSidebar.svelte';
  import StreamPanel from '../lib/components/watch/StreamPanel.svelte';
  import EditPanel from '../lib/components/watch/EditPanel.svelte';
  import MetaPanel from '../lib/components/watch/MetaPanel.svelte';
  import LyricsPanel from '../lib/components/watch/LyricsPanel.svelte';
  import VideoLinkDialog from '../lib/components/watch/VideoLinkDialog.svelte';
  import LikeBar from '../lib/components/common/LikeBar.svelte';
  import AddToPlaylistDialog from '../lib/components/common/AddToPlaylistDialog.svelte';
  import { playlistQueue, nextInQueue, prevInQueue, hasNext, hasPrev, stopQueue, playAtIndex, startQueue } from '../lib/stores/playlistQueue.js';
  import { activateMiniPlayer, deactivateMiniPlayer, getMiniPlayerState } from '../lib/stores/miniPlayer.js';
  import QuickPlaylistBtn from '../lib/components/common/QuickPlaylistBtn.svelte';

  marked.setOptions({ breaks: true, gfm: true });
  function renderMarkdown(text) {
    if (!text) return '';
    try { return marked.parse(text); } catch { return text; }
  }

  let video = $state(null);
  let isFav = $state(false);
  let showFullDesc = $state(false);
  let videoEl = $state(null);
  let plListEl = $state(null);
  let positionRestored = $state(false);
  let saveTimer = $state(null);
  let playRecorded = $state(false);
  let previewMode = $state(false);
  let downloadingPreview = $state(false);

  // Stream-Auswahl Dialog (Preview-Modus)
  let streamDialog = $state(null);

  // Tabs: info, chapters, subtitles, streams, edit
  let activeTab = $state('info');
  let showLyricsSidebar = $state(false);
  let lyricsManualClose = $state(false);
  let lyricsLocked = $state(false);
  let showSubtitleSidebar = $state(false);
  let showNotesSidebar = $state(false);
  let videoPlaylists = $state([]);  // Playlists die dieses Video enthalten

  // Resizable Breite
  let contentWidth = $state(parseInt(localStorage.getItem('tv-content-width') || '1100'));
  let resizing = $state(false);
  let plStripIdx = $state(0);  // Welche Playlist im Strip angezeigt wird
  let neighbors = $state({ prev: null, next: null });  // Bibliothek-Nachbarn

  // Shared state (übergeben an Komponenten)
  let chapters = $state([]);
  let adMarkers = $state([]);
  let subtitles = $state([]);
  let videoLinkDialog = $state(null);
  let videoLinks = $state({});  // { linked_video_id: { title, channel_name, thumbnail_path, ... } }

  // Like/Dislike-Daten
  let likesData = $state(null);
  let addToPlaylistVideoId = $state(null);

  async function loadLikes(videoId) {
    if (!videoId || videoId.startsWith('local_')) { likesData = null; return; }
    try {
      likesData = await api.getVideoLikes(videoId);
    } catch { likesData = null; }
  }
  let thumbKey = $state(Date.now());  // Cache-Busting für Thumbnails


  async function loadVideo() {
    const id = $route.id;
    if (!id) { navigate('/'); return; }
    // MiniPlayer deaktivieren wenn wir das gleiche (oder ein anderes) Video laden
    const mpState = getMiniPlayerState();
    if (mpState.active) deactivateMiniPlayer();
    positionRestored = false;
    playRecorded = false;
    activeTab = 'info';
    previewMode = false;

    // URL-Params lesen
    const params = $route.params || {};
    const urlTab = params.tab;
    if (urlTab) activeTab = urlTab;

    try {
      video = await api.getVideoPreview(id);
      previewMode = video.preview_mode || false;

      if (!previewMode) {
        const favCheck = await api.checkFavorite(id);
        isFav = favCheck.is_favorite;
        loadChapters(id);
        loadAdMarkers(id);
        loadSubtitles(id);
        loadVideoLinks(id);
        loadLikes(id);
        loadVideoPlaylists(id);
        loadNeighbors(id);

        // Auto-Enrich: SponsorBlock, Kapitel, Untertitel, Thumbnail nachladen
        autoEnrichVideo(id);

        // Playlist aus URL wiederherstellen
        const urlPl = params.pl;
        const urlIdx = parseInt(params.idx) || 0;
        if (urlPl && !$playlistQueue.active) {
          try {
            const plData = await api.getPlaylist(urlPl);
            if (plData.videos?.length) {
              startQueue(parseInt(urlPl), plData.name || 'Playlist', plData.videos, urlIdx);
            }
          } catch {}
        }

        // Lyrics-Sidebar aus URL oder Auto
        const urlLyrics = params.lyrics;
        if (urlLyrics === '1') {
          showLyricsSidebar = true;
          lyricsLocked = true;
        } else if (lyricsLocked) {
          showLyricsSidebar = true;
        } else if (!lyricsManualClose) {
          try {
            const lyr = await api.getLyrics(id);
            showLyricsSidebar = lyr.is_music || lyr.has_lyrics || false;
          } catch { showLyricsSidebar = false; }
        }
      } else {
        watchForDownload();
      }
    } catch (e) {
      toast.error('Video nicht gefunden');
      navigate('/library');
    }
  }

  async function startPreviewDownload({ itag = null, audioItag = null, mergeAudio = true, priority = 0 } = {}) {
    const id = $route.id;
    if (!id || downloadingPreview) return;
    downloadingPreview = true;
    try {
      await api.addDownload({
        url: `https://www.youtube.com/watch?v=${id}`,
        quality: video?.download_quality || 'best',
        audio_only: video?.audio_only || false,
        itag, audio_itag: audioItag, merge_audio: mergeAudio, priority,
      });
      const label = priority >= 10 ? 'Sofort-Download gestartet' : 'In Queue gelegt';
      toast.success(label);
      streamDialog = null;
    } catch (e) { toast.error(e.message); }
    finally { downloadingPreview = false; }
  }

  async function openPreviewStreamDialog() {
    const id = $route.id;
    if (!id) return;
    streamDialog = { loading: true, streams: [], videoStreams: [], audioStreams: [], captions: [], selectedVideoItag: null, selectedAudioItag: null, mergeAudio: true };
    try {
      const info = await api.getVideoInfo(`https://www.youtube.com/watch?v=${id}`);
      const videoStreams = (info.streams || [])
        .filter(s => s.type === 'video')
        .sort((a, b) => (parseInt(b.quality) || 0) - (parseInt(a.quality) || 0));
      const audioStreams = (info.streams || [])
        .filter(s => s.type === 'audio')
        .sort((a, b) => (parseInt(b.quality) || 0) - (parseInt(a.quality) || 0));
      streamDialog = {
        ...streamDialog,
        streams: info.streams || [],
        videoStreams, audioStreams,
        captions: info.captions || [],
        title: info.title,
        loading: false,
        alreadyDownloaded: info.already_downloaded,
        // Auto-Preselect: bestes Video + bestes Audio
        selectedVideoItag: videoStreams[0]?.itag || null,
        selectedAudioItag: videoStreams[0]?.is_progressive ? null : (audioStreams[0]?.itag || null),
      };
    } catch (e) {
      toast.error(`Stream-Info: ${e.message}`);
      streamDialog = null;
    }
  }

  function goBack() {
    // Zurück zum Feed als Standard-Rücksprung
    navigate('/feed');
  }

  // YouTube-Video-ID aus URL extrahieren
  async function loadChapters(id) {
    try {
      const res = await api.getChapters(id);
      chapters = res.chapters || [];
    } catch { chapters = []; }
  }

  async function loadAdMarkers(id) {
    try {
      const res = await api.getAdMarkers(id);
      adMarkers = res.ad_markers || [];
    } catch { adMarkers = []; }
  }

  // Zeitstring "mm:ss" oder "hh:mm:ss" oder Sekunden zu Sekunden
  function getCurrentPlayerTime() {
    return videoEl ? Math.floor(videoEl.currentTime) : 0;
  }

  // Werbung ueberspringen: bei timeupdate pruefen
  function onTimeUpdate() {
    if (!videoEl || adMarkers.length === 0) { maybeSyncUrl(); return; }
    const t = videoEl.currentTime;
    for (const m of adMarkers) {
      if (t >= m.start_time && t < m.end_time - 0.5) {
        videoEl.currentTime = m.end_time;
        toast.info(`Werbung uebersprungen (${m.label || 'Werbung'})`);
        break;
      }
    }
    maybeSyncUrl();
  }

  async function loadSubtitles(id) {
    try {
      const res = await api.getSubtitles(id);
      subtitles = res.subtitles || [];
    } catch { subtitles = []; }
  }

  async function loadVideoLinks(id) {
    try {
      // Auto-Link: verknüpfe automatisch YT-IDs aus Beschreibung die schon lokal sind
      await api.autoLinkDescription(id);
      const res = await api.getVideoLinks(id);
      const map = {};
      for (const link of (res.links || [])) {
        map[link.linked_video_id] = link;
      }
      videoLinks = map;
    } catch { videoLinks = {}; }
  }

  function onLinkedUpdate() {
    if (video?.id) loadVideoLinks(video.id);
  }

  // Position
  function onVideoLoaded() {
    if (!video || positionRestored) return;
    positionRestored = true;

    // Player-Einstellungen anwenden
    if (videoEl) {
      videoEl.volume = getSettingNum('player.volume', 80) / 100;
      videoEl.playbackRate = getSettingNum('player.speed', 1.0);
    }

    const lastPos = video.last_position || 0;
    const q = $playlistQueue;
    const urlTime = parseInt($route.params?.t) || 0;

    // URL-Zeitstempel hat Vorrang
    if (urlTime > 0 && videoEl) {
      videoEl.currentTime = urlTime;
    } else if (q.active) {
      if (videoEl) videoEl.currentTime = 0;
    } else if (lastPos > 5 && videoEl && video.duration && lastPos < video.duration - 10) {
      videoEl.currentTime = lastPos;
      toast.info(`Fortgesetzt bei ${formatDuration(lastPos)}`);
    }

    // Autoplay: immer wenn Playlist-Queue aktiv, sonst nach Einstellung
    if ((q.active || getSettingBool('player.autoplay')) && videoEl) {
      videoEl.play().catch(() => {});
    }

    if (getSettingBool('player.save_position', true)) {
      startPositionSaving();
    }
  }

  function startPositionSaving() {
    stopPositionSaving();
    saveTimer = setInterval(() => saveCurrentPosition(), 10000);
  }

  function stopPositionSaving() {
    if (saveTimer) { clearInterval(saveTimer); saveTimer = null; }
  }

  async function saveCurrentPosition() {
    if (!videoEl || !video) return;
    if (!getSettingBool('player.save_position', true)) return;
    const pos = videoEl.currentTime;
    if (pos < 2) return;
    try { await api.savePosition(video.id, pos); } catch {}
  }

  function onPlay() {
    if (!playRecorded && video) {
      playRecorded = true;
      api.recordPlay(video.id, videoEl?.currentTime || 0).catch(() => {});
    }
    startPositionSaving();
  }

  function onPause() { saveCurrentPosition(); stopPositionSaving(); }

  function onEnded() {
    stopPositionSaving();
    if (video) api.savePosition(video.id, 0).catch(() => {});

    // Playlist-Queue: Nächstes Video abspielen (auch im Fullscreen)
    if (hasNext()) {
      const nextId = nextInQueue();
      if (nextId) {
        navigate(`/watch/${nextId}`);
        return;
      }
    }

    // Kein Queue oder Queue am Ende → Video ist fertig
  }

  // Queue-Navigation (Fullscreen-sicher)
  function playNextInQueue() {
    const nextId = nextInQueue();
    if (nextId) navigate(`/watch/${nextId}`);
  }

  function playPrevInQueue() {
    const prevId = prevInQueue();
    if (prevId) navigate(`/watch/${prevId}`);
  }

  // Sidebar: Video an bestimmtem Index abspielen
  // ─── URL State Sync ────────────────────────────────────
  function syncUrlState() {
    const q = $playlistQueue;
    updateParams({
      t: videoEl && videoEl.currentTime > 5 ? Math.floor(videoEl.currentTime) : null,
      pl: q.active ? q.playlistId : null,
      idx: q.active ? q.currentIndex : null,
      lyrics: showLyricsSidebar ? '1' : null,
    });
  }

  // Debounced URL sync on timeupdate (every 10s)
  let lastUrlSync = 0;
  function maybeSyncUrl() {
    if (!positionRestored) return;  // Warte bis Video geladen
    const now = Date.now();
    if (now - lastUrlSync > 10000) {
      lastUrlSync = now;
      syncUrlState();
    }
  }

  // ─── Playlist-Picker ─────────────────────────────────────
  async function loadVideoPlaylists(id) {
    try {
      const allPl = await api.getPlaylists();
      const withVideo = [];
      for (const pl of allPl) {
        try {
          const full = await api.getPlaylist(pl.id);
          const idx = (full.videos || []).findIndex(v => v.id === id);
          if (idx >= 0) {
            withVideo.push({ ...full, currentIdx: idx });
          }
        } catch {}
      }
      videoPlaylists = withVideo;
      // Auto-select: aktive Playlist oder erste
      const q = $playlistQueue;
      if (q.active) {
        const activeIdx = withVideo.findIndex(p => p.id === q.playlistId);
        plStripIdx = activeIdx >= 0 ? activeIdx : 0;
      } else {
        plStripIdx = 0;
      }
    } catch { videoPlaylists = []; }
  }

  async function loadNeighbors(id) {
    try {
      neighbors = await api.getVideoNeighbors(id);
    } catch { neighbors = { prev: null, next: null }; }
  }

  async function autoEnrichVideo(id) {
    try {
      const res = await api.autoEnrich(id);
      const e = res.enriched || {};
      let reloaded = false;
      if (e.sponsorblock > 0) { await loadAdMarkers(id); reloaded = true; }
      if (e.chapters > 0) { await loadChapters(id); reloaded = true; }
      if (e.chapter_thumbs > 0) { await loadChapters(id); }
      if (e.subtitles > 0) { await loadSubtitles(id); reloaded = true; }
      if (e.thumbnail) { thumbKey = Date.now(); }
    } catch(e) { /* Stille Fehler – kein Toast */ }
  }

  async function startPlaylistFromStrip(pl) {
    startQueue(pl.id, pl.name, pl.videos, pl.currentIdx >= 0 ? pl.currentIdx : 0);
    lyricsLocked = true;
    showLyricsSidebar = true;
    syncUrlState();
  }

  // ─── Sidebar Toggle (exklusiv: Lyrics / Untertitel / Notizen) ───
  function toggleSidebar(which) {
    if (which === 'lyrics') {
      showLyricsSidebar = !showLyricsSidebar;
      lyricsManualClose = !showLyricsSidebar;
      if (showLyricsSidebar) { showSubtitleSidebar = false; showNotesSidebar = false; }
    } else if (which === 'subtitles') {
      showSubtitleSidebar = !showSubtitleSidebar;
      if (showSubtitleSidebar) { showLyricsSidebar = false; lyricsManualClose = true; showNotesSidebar = false; }
    } else if (which === 'notes') {
      showNotesSidebar = !showNotesSidebar;
      if (showNotesSidebar) { showLyricsSidebar = false; lyricsManualClose = true; showSubtitleSidebar = false; }
    }
    syncUrlState();
  }

  // ─── Resize Hauptbereich ───
  let watchPageEl = $state(null);

  function startResize(e) {
    e.preventDefault();
    resizing = true;
    const rect = watchPageEl?.getBoundingClientRect();
    const left = rect?.left || 0;
    const onMove = (ev) => {
      const newW = Math.max(600, Math.min(ev.clientX - left + 8, window.innerWidth - left - 20));
      contentWidth = newW;
    };
    const onUp = () => {
      resizing = false;
      localStorage.setItem('tv-content-width', String(contentWidth));
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }

  function skipNext() {
    // Playlist-Modus: nächstes in Queue
    if ($playlistQueue.active) {
      const id = nextInQueue();
      if (id) navigate(`/watch/${id}`);
      return;
    }
    // Bibliothek-Modus: nächstes in historischer Reihenfolge
    if (neighbors.next) {
      navigate(`/watch/${neighbors.next.id}`);
    } else {
      // Kein Nachbar → am Ende der Bibliothek
    }
  }

  function skipPrev() {
    if ($playlistQueue.active) {
      const id = prevInQueue();
      if (id) navigate(`/watch/${id}`);
      return;
    }
    if (neighbors.prev) navigate(`/watch/${neighbors.prev.id}`);
  }

  function playFromSidebar(index) {
    const id = playAtIndex(index);
    if (id) navigate(`/watch/${id}`);
  }

  // Chapter klick → seek
  function seekToChapter(startTime) {
    if (videoEl) {
      videoEl.currentTime = startTime;
      videoEl.play();
    }
  }

  // Subtitle toggle
  // Favoriten
  async function toggleFavorite() {
    if (!video) return;
    try {
      if (isFav) {
        await api.removeFavorite(video.id);
        isFav = false;
        toast.info('Aus Favoriten entfernt');
      } else {
        await api.addFavorite({ video_id: video.id, list_name: 'Standard' });
        isFav = true;
        toast.success('Zu Favoriten hinzugefügt');
      }
    } catch (e) { toast.error(e.message); }
  }

  async function archiveFromWatch() {
    if (!video) return;
    try {
      if (video.is_archived) {
        await api.unarchiveVideo(video.id);
        video.is_archived = 0;
        toast.success('Dearchiviert');
      } else {
        await api.archiveVideo(video.id);
        video.is_archived = 1;
        toast.success('Archiviert');
      }
    } catch (e) { toast.error(e.message); }
  }

  async function toggleSuggest() {
    if (!video || previewMode) return;
    let next;
    if (!video.suggest_override) next = 'exclude';
    else if (video.suggest_override === 'exclude') next = 'include';
    else next = 'reset';
    try {
      await api.updateVideoSuggest(video.id, next);
      video.suggest_override = next === 'reset' ? null : next;
      const labels = { exclude: 'Aus Vorschlägen entfernt', include: 'In Vorschläge aufgenommen', reset: 'Standard wiederhergestellt' };
      toast.success(labels[next] || 'Aktualisiert');
    } catch (e) { toast.error(e.message); }
  }

  async function deleteVideo() {
    if (!video || previewMode) return;
    try {
      await api.deleteVideo(video.id);
      toast.success('Video gelöscht');
      navigate('/library');
    } catch (e) { toast.error(e.message); }
  }

  // Phase 3: Metadata bearbeiten
  function filterByTag(tag) {
    navigate('/library');
    window.dispatchEvent(new CustomEvent('tubevault:tag-filter', { detail: tag }));
  }

  async function setRating(r) {
    if (!video) return;
    const newRating = video.rating === r ? 0 : r;
    try {
      await api.setVideoRating(video.id, newRating);
      video = { ...video, rating: newRating };
    } catch (e) { toast.error(e.message); }
  }

  let actSocket = $state(null);
  function cleanup() {
    // Mini-Player aktivieren wenn Video lief
    if (video && videoEl && videoEl.currentTime > 1 && !videoEl.ended) {
      const ct = videoEl.currentTime;
      const dur = videoEl.duration || video.duration || 0;
      const vol = videoEl.volume;
      const playing = !videoEl.paused;
      // Watch-Video sofort stoppen (MiniPlayer öffnet eigenen Stream)
      videoEl.pause();
      activateMiniPlayer({
        videoId: video.id,
        title: video.title || video.id,
        channelName: video.channel_name || '',
        currentTime: ct,
        duration: dur,
        volume: vol,
        isPlaying: playing,
        audioOnly: video?.audio_only || false,
        thumbnailUrl: api.thumbnailUrl(video.id),
      });
    }
    saveCurrentPosition();
    stopPositionSaving();
    actSocket?.close();
    actSocket = null;
  }

  // Download-Abschluss erkennen → Preview-Seite automatisch neu laden
  function watchForDownload() {
    actSocket?.close();
    if (!previewMode) return;
    actSocket = createActivitySocket((msg) => {
      if (msg?.type !== 'job_update' || !msg.job) return;
      const j = msg.job;
      if (j.type === 'download' && j.status === 'done') {
        // Prüfe ob die video_id übereinstimmt
        const vid = j.metadata?.video_id || j.video_id || '';
        if (vid === $route.id) {
          toast.success('Download abgeschlossen – Seite wird aktualisiert');
          setTimeout(() => loadVideo(), 1000);
        }
      }
    });
  }

  // Delegated click handler für Beschreibungs-Links
  let videoLinkDialogRef;

  function handleDescClick(e) {
    const action = parseDescClick(e);
    if (!action) return;
    if (action.type === 'open_video') {
      navigate(`/watch/${action.value}`);
    } else if (action.type === 'youtube' && videoLinkDialogRef) {
      videoLinkDialogRef.lookup(action.value);
    } else if (action.type === 'tag') {
      filterByTag(action.value);
    } else if (action.type === 'timestamp' && videoEl) {
      videoEl.currentTime = action.value;
    }
  }

  let _lastLoadedId = null;

  $effect(() => {
    // Bei Video-Wechsel: erst alte Position speichern, dann neu laden
    const id = $route.id;
    return () => { saveCurrentPosition(); stopPositionSaving(); };
  });
  $effect(() => {
    const id = $route.id;
    if (id && id !== _lastLoadedId) {
      _lastLoadedId = id;
      lyricsManualClose = false;
      loadVideo();
    }
  });
  $effect(() => { return () => cleanup(); });
  $effect(() => {
    const h = () => saveCurrentPosition();
    window.addEventListener('beforeunload', h);
    document.addEventListener('visibilitychange', () => { if (document.hidden) saveCurrentPosition(); });
    return () => window.removeEventListener('beforeunload', h);
  });

  // Sidebar: auto-scroll zum aktuellen Video
  $effect(() => {
    const idx = $playlistQueue.currentIndex;
    if (plListEl && $playlistQueue.active) {
      const el = plListEl.children[idx];
      if (el) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  });
</script>

{#if video}
<div class="watch-page" class:with-lyrics-sidebar={(showLyricsSidebar || showSubtitleSidebar || showNotesSidebar) && !$playlistQueue.active} class:with-playlist-sidebar={$playlistQueue.active && !showLyricsSidebar && !showSubtitleSidebar && !showNotesSidebar} class:with-dual-sidebar={$playlistQueue.active && (showLyricsSidebar || showSubtitleSidebar || showNotesSidebar)} class:resizing={resizing} style:max-width="{contentWidth}px" bind:this={watchPageEl}>
  <div class="watch-main">

  <!-- Player-Bereich: Thumbnail (Preview) oder Video (Normal) -->
  <div class="player-section">
    {#if previewMode}
      <div class="player-wrap">
        {#if video.thumbnail_path || video.id}
          <img class="preview-thumb" src={video.thumbnail_path ? api.thumbnailUrl(video.id) : api.rssThumbUrl(video.id)} alt=""
               onerror={(e) => e.target.style.display='none'} />
        {:else}
          <div class="preview-placeholder"><i class="fa-solid fa-film"></i></div>
        {/if}
        <div class="preview-overlay">
          <button class="preview-dl-btn" onclick={() => startPreviewDownload({ priority: 10 })} disabled={downloadingPreview}>
            {#if downloadingPreview}
              <i class="fa-solid fa-spinner fa-spin"></i>
            {:else}
              <i class="fa-solid fa-download"></i>
            {/if}
          </button>
          <div class="preview-actions-bar">
            <button class="preview-bar-btn" onclick={openPreviewStreamDialog} disabled={downloadingPreview}>
              <i class="fa-solid fa-sliders"></i> Stream wählen
            </button>
            <button class="preview-bar-btn" onclick={() => startPreviewDownload({ priority: 0 })} disabled={downloadingPreview}>
              <i class="fa-solid fa-list"></i> In Queue
            </button>
          </div>
        </div>
      </div>
    {:else}
      <div class="player-wrap">
        <!-- svelte-ignore a11y_media_has_caption -->
        <video
          bind:this={videoEl}
          class="video-player"
          src={api.streamUrl(video.id)}
          poster={`${api.thumbnailUrl(video.id)}?v=${thumbKey}`}
          controls
          preload="metadata"
          onloadedmetadata={onVideoLoaded}
          onplay={onPlay}
          onpause={onPause}
          onended={onEnded}
          ontimeupdate={onTimeUpdate}
          crossorigin="anonymous"
        ></video>
      </div>
    {/if}
  </div>

  <!-- Video-Details: immer gleiche Struktur -->
  <div class="video-details">
    <h1 class="video-title">{video.title || video.id}</h1>

    <div class="video-meta-row">
      <div class="meta-left">
        <button class="channel" onclick={() => { if (video.channel_id) { navigate(`/channel/${video.channel_id}`); } }}>
          {video.channel_name || 'Unbekannt'}
        </button>
        {#if video.view_count}
          <span class="dot">·</span>
          <span>{formatViews(video.view_count)} Aufrufe</span>
        {/if}
        {#if video.published || video.upload_date}
          <span class="dot">·</span>
          <span>{formatDate(video.published || video.upload_date)}</span>
        {/if}
        {#if video.duration}
          <span class="dot">·</span>
          <span>{formatDuration(video.duration)}</span>
        {/if}
        {#if !previewMode && video.play_count > 0}
          <span class="dot">·</span>
          <span class="play-count">{video.play_count}× abgespielt</span>
        {/if}
      </div>
      <div class="meta-right">
        {#if previewMode}
          <a class="yt-link" href="https://www.youtube.com/watch?v={video.id}" target="_blank" rel="noopener">
            <i class="fa-solid fa-arrow-up-right-from-square"></i> YouTube
          </a>
        {:else}
          <button class="action-btn" class:active={isFav} onclick={toggleFavorite} title="Favorit">
            <i class={isFav ? 'fa-solid fa-heart' : 'fa-regular fa-heart'} style={isFav ? 'color:var(--status-error)' : ''}></i>
          </button>
          <QuickPlaylistBtn videoId={video.id} title={video.title} channelName={video.channel_name} channelId={video.channel_id} size="md" />
          <button class="action-btn" onclick={() => addToPlaylistVideoId = video.id} title="Zur Playlist hinzufügen">
            <i class="fa-solid fa-list-ul"></i>
          </button>
          <button class="action-btn" onclick={archiveFromWatch} title={video?.is_archived ? 'Dearchivieren' : 'Archivieren'}>
            <i class="fa-solid {video?.is_archived ? 'fa-box-open' : 'fa-box-archive'}"></i>
          </button>
          <button class="action-btn"
            class:suggest-exclude={video?.suggest_override === 'exclude'}
            class:suggest-include={video?.suggest_override === 'include'}
            onclick={toggleSuggest}
            title={video?.suggest_override === 'exclude' ? 'Aus Vorschlägen ausgeschlossen' : video?.suggest_override === 'include' ? 'Explizit eingeschlossen' : 'Standard (Kanal-Einstellung)'}>
            <i class="fa-solid fa-dice"></i>
          </button>
          <button class="action-btn" class:active={showLyricsSidebar} onclick={() => toggleSidebar('lyrics')} title="Lyrics">
            <i class="fa-solid fa-music"></i>
          </button>
          <button class="action-btn" class:active={showSubtitleSidebar} onclick={() => toggleSidebar('subtitles')} title="Untertitel">
            <i class="fa-solid fa-closed-captioning"></i>
            {#if subtitles.length > 0}<span class="btn-badge">{subtitles.length}</span>{/if}
          </button>
          <button class="action-btn" class:active={showNotesSidebar} onclick={() => toggleSidebar('notes')} title="Notizen">
            <i class="fa-solid fa-note-sticky"></i>
            {#if video?.notes}<span class="btn-badge"><i class="fa-solid fa-pen" style="font-size:0.4rem"></i></span>{/if}
          </button>
          <button class="action-btn danger" onclick={deleteVideo} title="Löschen">
            <i class="fa-regular fa-trash-can"></i>
          </button>
        {/if}
      </div>
    </div>

    <!-- Playlist Strip + Video Skip -->
    {#if !previewMode}
      {@const prevItem = $playlistQueue.active ? ($playlistQueue.videos[$playlistQueue.currentIndex - 1] || null) : neighbors.prev}
      {@const nextItem = $playlistQueue.active ? ($playlistQueue.videos[$playlistQueue.currentIndex + 1] || null) : neighbors.next}
      <div class="nav-strip">
        <!-- Skip Prev -->
        <button class="skip-btn" onclick={skipPrev} disabled={!prevItem}>
          <i class="fa-solid fa-backward-step"></i>
          {#if prevItem}
            <span class="skip-label">{prevItem.title || prevItem.channel_name || '?'}</span>
          {/if}
        </button>

        <!-- Playlist Info oder Bibliothek -->
        {#if videoPlaylists.length > 0}
          {@const pl = videoPlaylists[plStripIdx]}
          {@const isActive = $playlistQueue.active && $playlistQueue.playlistId === pl?.id}
          <div class="strip-main" class:active={isActive}>
            {#if videoPlaylists.length > 1}
              <button class="strip-pager" onclick={() => plStripIdx = (plStripIdx - 1 + videoPlaylists.length) % videoPlaylists.length}>
                <i class="fa-solid fa-chevron-left"></i>
              </button>
              <span class="strip-pager-num">{plStripIdx + 1}/{videoPlaylists.length}</span>
              <button class="strip-pager" onclick={() => plStripIdx = (plStripIdx + 1) % videoPlaylists.length}>
                <i class="fa-solid fa-chevron-right"></i>
              </button>
            {/if}
            <i class="fa-solid fa-list-ul strip-icon"></i>
            <button class="strip-name" onclick={() => startPlaylistFromStrip(pl)}>{pl.name}</button>
            <span class="strip-count">{pl.videos?.length || 0}</span>
            <span class="strip-pos">#{(pl.currentIdx ?? 0) + 1}</span>
            {#if isActive}
              <i class="fa-solid fa-volume-high strip-playing"></i>
            {:else}
              <button class="strip-play" onclick={() => startPlaylistFromStrip(pl)} title="Playlist ab hier starten">
                <i class="fa-solid fa-play"></i>
              </button>
            {/if}
          </div>
        {:else}
          <div class="strip-main library">
            <i class="fa-solid fa-clock-rotate-left strip-icon"></i>
            <span class="strip-label">Bibliothek</span>
          </div>
        {/if}

        <!-- Skip Next -->
        <button class="skip-btn" onclick={skipNext} disabled={!nextItem}>
          {#if nextItem}
            <span class="skip-label">{nextItem.title || nextItem.channel_name || '?'}</span>
          {/if}
          <i class="fa-solid fa-forward-step"></i>
        </button>
      </div>
    {/if}
    {#if likesData && likesData.likes + likesData.dislikes > 0}
      <LikeBar likes={likesData.likes} dislikes={likesData.dislikes} mode="bar" />
    {:else if video.like_count && video.dislike_count != null}
      <LikeBar likes={video.like_count} dislikes={video.dislike_count} mode="bar" />
    {/if}

    {#if previewMode}
      <!-- Beschreibung (Preview): einklappbar -->
      {#if video.description}
        <button class="desc-toggle" onclick={() => showFullDesc = !showFullDesc}>
          {#if showFullDesc}<i class="fa-solid fa-chevron-up"></i> Beschreibung ausblenden{:else}<i class="fa-solid fa-chevron-down"></i> Beschreibung{/if}
        </button>
        {#if showFullDesc}
          <div class="description" onclick={handleDescClick} role="presentation">{@html formatDescription(video.description, videoLinks)}</div>
        {/if}
      {/if}
    {:else}
    <div class="tabs">
      {#each [['info','<i class="fa-solid fa-circle-info"></i> Info'],['chapters','<i class="fa-solid fa-bookmark"></i> Kapitel'],['ads','<i class="fa-solid fa-forward"></i> Werbung'],['subtitles','<i class="fa-solid fa-closed-captioning"></i> Untertitel'],['streams','<i class="fa-solid fa-sliders"></i> Streams'],['meta','<i class="fa-solid fa-microchip"></i> Meta'],['edit','<i class="fa-solid fa-pen"></i> Bearbeiten']] as [id, label]}
        <button class="tab" class:active={activeTab === id} onclick={() => activeTab = id}>
          {@html label}
          {#if id === 'chapters' && chapters.length > 0}
            <span class="tab-badge">{chapters.length}</span>
          {/if}
          {#if id === 'ads' && adMarkers.length > 0}
            <span class="tab-badge ad-badge">{adMarkers.length}{#if adMarkers.some(m => m.source === 'sponsorblock')} <i class="fa-solid fa-shield-halved" style="font-size:0.55rem"></i>{/if}</span>
          {/if}
          {#if id === 'subtitles' && subtitles.length > 0}
            <span class="tab-badge">{subtitles.length}</span>
          {/if}
        </button>
      {/each}
    </div>

    <!-- Tab: Info -->
    {#if activeTab === 'info'}
      <div class="info-cards">
        <div class="info-card"><span class="info-label">Dauer</span><span class="info-value">{formatDuration(video.duration)}</span></div>
        <div class="info-card"><span class="info-label">Dateigröße</span><span class="info-value">{formatSize(video.file_size)}</span></div>
        <div class="info-card"><span class="info-label">Wiedergaben</span><span class="info-value">{video.play_count}</span></div>
        <div class="info-card">
          <span class="info-label">Bewertung</span>
          <span class="info-value rating-stars">
            {#each [1,2,3,4,5] as r}
              <button class="star-btn" class:filled={r <= (video.rating || 0)} title="{r} Sterne" onclick={() => setRating(r)}>
                <i class={r <= (video.rating || 0) ? 'fa-solid fa-star' : 'fa-regular fa-star'}></i>
              </button>
            {/each}
          </span>
        </div>
      </div>

      {#if video.tags?.length > 0}
        <div class="tags">
          {#each video.tags.slice(0, 15) as tag}
            <button class="tag" onclick={() => filterByTag(tag)}>{tag}</button>
          {/each}
        </div>
      {/if}

      {#if video.notes}
        <div class="notes-box">
          <span class="notes-label"><i class="fa-solid fa-pen-nib"></i> Notizen</span>
          <div class="md-content">{@html renderMarkdown(video.notes)}</div>
        </div>
      {/if}

      {#if video.description}
        <div class="description" onclick={handleDescClick} role="presentation">
          <div class="desc-body">{@html formatDescription(showFullDesc ? video.description : truncate(video.description, 300), videoLinks)}</div>
          {#if video.description.length > 300}
            <button class="btn-link" onclick={() => showFullDesc = !showFullDesc}>
              {showFullDesc ? 'Weniger' : 'Mehr anzeigen'}
            </button>
          {/if}
        </div>
      {/if}

    <!-- Tab: Chapters -->
    {:else if activeTab === 'chapters'}
      <ChapterPanel
        videoId={video.id}
        bind:chapters
        getCurrentTime={getCurrentPlayerTime}
        onSeek={seekToChapter}
      />

    <!-- Tab: Ad-Markers (Werbung) -->
    {:else if activeTab === 'ads'}
      <AdMarkerPanel
        videoId={video.id}
        bind:adMarkers
        onSeek={(t) => { if (videoEl) videoEl.currentTime = t; }}
      />

    <!-- Tab: Subtitles -->
    {:else if activeTab === 'subtitles'}
      <SubtitlePanel videoId={video.id} bind:subtitles videoEl={videoEl} />

    {:else if activeTab === 'streams'}
      <StreamPanel videoId={video.id} videoEl={videoEl} />

    {:else if activeTab === 'meta'}
      <MetaPanel {video} />

    {:else if activeTab === 'edit'}
      <EditPanel {video} onVideoUpdate={() => { thumbKey = Date.now(); loadVideo(); }} getCurrentTime={getCurrentPlayerTime} />
    {/if}
  {/if}
  </div>
  </div><!-- /watch-main -->

  <!-- Resize Handle -->
  {#if !showLyricsSidebar && !showSubtitleSidebar && !showNotesSidebar && !$playlistQueue.active}
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="resize-handle" onmousedown={startResize} title="Breite anpassen">
      <div class="resize-dots"></div>
    </div>
  {/if}

  <!-- Lyrics Sidebar (links von Playlist) -->
  {#if showLyricsSidebar && !previewMode}
  <aside class="lyrics-sidebar" style:right={$playlistQueue.active ? '350px' : '0'}>
    <div class="lyrics-sidebar-header">
      <span><i class="fa-solid fa-music"></i> Lyrics</span>
      <div class="lyrics-header-actions">
        <button class="sidebar-btn" class:active={lyricsLocked} onclick={() => { lyricsLocked = !lyricsLocked; syncUrlState(); }} title={lyricsLocked ? 'Lyrics lösen (schließt bei Nicht-Musik)' : 'Lyrics fixieren (bleibt offen bei Videowechsel)'}>
          <i class="fa-solid {lyricsLocked ? 'fa-lock' : 'fa-lock-open'}"></i>
        </button>
        <button class="sidebar-btn" onclick={() => { showLyricsSidebar = false; lyricsManualClose = true; lyricsLocked = false; syncUrlState(); }}><i class="fa-solid fa-xmark"></i></button>
      </div>
    </div>
    <div class="lyrics-sidebar-content">
      <LyricsPanel
        videoId={video.id}
        videoTitle={video.title}
        getCurrentTime={getCurrentPlayerTime}
        {videoEl}
        autoSearch={lyricsLocked}
      />
    </div>
  </aside>
  {/if}

  <!-- Subtitle Sidebar (mitlaufend wie Lyrics) -->
  {#if showSubtitleSidebar && !previewMode}
  <aside class="lyrics-sidebar" style:right={$playlistQueue.active ? '350px' : '0'}>
    <div class="lyrics-sidebar-header">
      <span><i class="fa-solid fa-closed-captioning"></i> Untertitel</span>
      <div class="lyrics-header-actions">
        <button class="sidebar-btn" onclick={() => toggleSidebar('subtitles')}><i class="fa-solid fa-xmark"></i></button>
      </div>
    </div>
    <div class="lyrics-sidebar-content">
      <SubtitleLiveSidebar videoId={video.id} {videoEl} bind:subtitles />
    </div>
  </aside>
  {/if}

  <!-- Notes Sidebar (Live-Preview MD Editor) -->
  {#if showNotesSidebar && !previewMode}
  <aside class="lyrics-sidebar" style:right={$playlistQueue.active ? '350px' : '0'}>
    <div class="lyrics-sidebar-header">
      <span><i class="fa-solid fa-note-sticky"></i> Notizen</span>
      <div class="lyrics-header-actions">
        <button class="sidebar-btn" onclick={() => toggleSidebar('notes')}><i class="fa-solid fa-xmark"></i></button>
      </div>
    </div>
    <div class="lyrics-sidebar-content">
      <NotesSidebar videoId={video.id} initialNotes={video.notes || ''} onNotesChange={(n) => { video.notes = n; }} />
    </div>
  </aside>
  {/if}

  <!-- Playlist Sidebar (ganz rechts) -->
  {#if $playlistQueue.active}
  <aside class="playlist-sidebar">
    <div class="pl-header">
      <div class="pl-header-top">
        <span class="pl-name"><i class="fa-solid fa-list-ul"></i> {$playlistQueue.playlistName}</span>
        <button class="pl-close" onclick={() => { stopQueue(); syncUrlState(); }} title="Queue beenden"><i class="fa-solid fa-xmark"></i></button>
      </div>
      <div class="pl-info">
        <span class="pl-pos">{$playlistQueue.currentIndex + 1} / {$playlistQueue.videos.length}</span>
        <span class="pl-sep">·</span>
        <span>{formatDuration($playlistQueue.videos.reduce((s, v) => s + (v.duration || 0), 0))} gesamt</span>
      </div>
      <div class="pl-controls">
        <button class="pl-ctrl-btn" onclick={playPrevInQueue} disabled={!hasPrev()} title="Vorheriges">
          <i class="fa-solid fa-backward-step"></i>
        </button>
        <button class="pl-ctrl-btn" onclick={playNextInQueue} disabled={!hasNext()} title="Nächstes">
          <i class="fa-solid fa-forward-step"></i>
        </button>
      </div>
    </div>
    <div class="pl-list" bind:this={plListEl}>
      {#each $playlistQueue.videos as plv, idx}
        <button
          class="pl-item"
          class:playing={idx === $playlistQueue.currentIndex}
          class:played={idx < $playlistQueue.currentIndex}
          onclick={() => playFromSidebar(idx)}
        >
          <span class="pl-index">
            {#if idx === $playlistQueue.currentIndex}
              <i class="fa-solid fa-volume-high"></i>
            {:else}
              {idx + 1}
            {/if}
          </span>
          <div class="pl-thumb">
            <img src={api.thumbnailUrl(plv.id)} alt="" loading="lazy" onerror={(e) => e.target.style.display='none'} />
            {#if plv.duration}<span class="pl-dur">{formatDuration(plv.duration)}</span>{/if}
          </div>
          <div class="pl-text">
            <span class="pl-text-title">{plv.title}</span>
            <span class="pl-text-channel">{plv.channel_name || ''}</span>
          </div>
        </button>
      {/each}
    </div>
    <div class="pl-footer">
      <span>{$playlistQueue.videos.length} Videos</span>
    </div>
  </aside>
  {/if}

</div>
{/if}

<!-- Stream-Dialog (Preview) -->
{#if video && streamDialog}
  <div class="dialog-backdrop" onclick={() => streamDialog = null} role="presentation">
    <div class="dialog" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.key === 'Escape' && (streamDialog = null)} role="dialog" tabindex="-1">
      <div class="dialog-header">
        <h2>Download-Optionen</h2>
        <button class="dialog-close" title="Schließen" onclick={() => streamDialog = null}><i class="fa-solid fa-xmark"></i></button>
      </div>

      {#if streamDialog.loading}
        <div class="dialog-loading"><i class="fa-solid fa-spinner fa-spin"></i> Streams werden geladen…</div>
      {:else}
        {#if streamDialog.alreadyDownloaded}
          <div class="dialog-warn"><i class="fa-solid fa-triangle-exclamation"></i> Bereits heruntergeladen.</div>
        {/if}

        <div class="stream-section">
          <h3><i class="fa-solid fa-video"></i> Video-Streams</h3>
          <div class="stream-list">
            {#each streamDialog.videoStreams as s}
              <label class="stream-option" class:selected={streamDialog.selectedVideoItag === s.itag}>
                <input type="radio" name="video-stream" value={s.itag}
                  checked={streamDialog.selectedVideoItag === s.itag}
                  onchange={() => {
                    streamDialog.selectedVideoItag = s.itag;
                    // Progressive Stream hat Audio dabei → Audio-Auswahl zurücksetzen
                    if (s.is_progressive) {
                      streamDialog.selectedAudioItag = null;
                    }
                  }} />
                <span class="stream-quality">{s.quality}</span>
                <span class="stream-codec">{s.codec}</span>
                <span class="stream-size">{formatStreamSize(s.file_size)}</span>
                {#if s.fps && s.fps > 30}
                  <span class="stream-fps">{s.fps}fps</span>
                {/if}
                {#if s.is_progressive}
                  <span class="stream-tag prog">V+A</span>
                {:else}
                  <span class="stream-tag adaptive">Video only</span>
                {/if}
              </label>
            {/each}
          </div>
        </div>

        {@const selVideo = streamDialog.videoStreams.find(s => s.itag === streamDialog.selectedVideoItag)}
        {@const isProgressive = selVideo?.is_progressive}

        <div class="stream-section" class:section-disabled={isProgressive}>
          <h3>
            <i class="fa-solid fa-music"></i> Audio-Streams
            {#if isProgressive}
              <span class="section-hint">– nicht nötig (Video enthält Audio)</span>
            {/if}
          </h3>
          <div class="stream-list">
            {#each streamDialog.audioStreams as s}
              <label class="stream-option" class:selected={streamDialog.selectedAudioItag === s.itag}
                     class:option-disabled={isProgressive}>
                <input type="radio" name="audio-stream" value={s.itag}
                  checked={streamDialog.selectedAudioItag === s.itag}
                  disabled={isProgressive}
                  onchange={() => streamDialog.selectedAudioItag = s.itag} />
                <span class="stream-quality">{s.quality}</span>
                <span class="stream-codec">{s.codec}</span>
                <span class="stream-size">{formatStreamSize(s.file_size)}</span>
              </label>
            {/each}
          </div>
        </div>

        <div class="dialog-options">
          {#if !isProgressive}
            <label class="option-check">
              <input type="checkbox" bind:checked={streamDialog.mergeAudio} />
              Audio einmischen (bei Video-only Streams)
            </label>
          {/if}
          {#if streamDialog.selectedVideoItag && !streamDialog.selectedAudioItag && !isProgressive}
            {#if selVideo && !selVideo.is_progressive}
              <p class="stream-hint"><i class="fa-solid fa-circle-info"></i> Video-only gewählt – wähle auch einen Audio-Stream oder aktiviere "Audio einmischen".</p>
            {/if}
          {/if}
          {#if isProgressive}
            <p class="stream-hint stream-hint-ok"><i class="fa-solid fa-circle-check"></i> Progressiver Stream gewählt – Audio ist bereits enthalten.</p>
          {/if}
        </div>

        {#if streamDialog.captions.length > 0}
          <div class="stream-section small">
            <h3><i class="fa-solid fa-closed-captioning"></i> Untertitel</h3>
            <span class="caption-list">{streamDialog.captions.map(c => c.name || c.code).join(', ')}</span>
          </div>
        {/if}

        <div class="dialog-actions">
          <!-- Auswahlzusammenfassung -->
          {#if streamDialog.selectedVideoItag}
            {@const sv = streamDialog.videoStreams.find(s => s.itag === streamDialog.selectedVideoItag)}
            {@const sa = streamDialog.audioStreams.find(s => s.itag === streamDialog.selectedAudioItag)}
            <div class="dl-summary">
              <span class="dl-sum-item">🎬 {sv?.quality} {sv?.codec}</span>
              {#if sv?.is_progressive}
                <span class="dl-sum-item dl-sum-ok">✓ Audio enthalten</span>
              {:else if sa}
                <span class="dl-sum-item">🎵 {sa.quality} {sa.codec}</span>
              {:else if streamDialog.mergeAudio}
                <span class="dl-sum-item">🎵 Auto (bestes Audio)</span>
              {:else}
                <span class="dl-sum-item dl-sum-warn">⚠ Kein Audio gewählt</span>
              {/if}
            </div>
          {/if}
          <div class="dl-buttons">
            <button class="btn-ghost" onclick={() => streamDialog = null}>Abbrechen</button>
            <button class="btn-queue-dl" onclick={() => startPreviewDownload({
              itag: streamDialog.selectedVideoItag, audioItag: streamDialog.selectedAudioItag,
              mergeAudio: streamDialog.mergeAudio, priority: 0
            })} disabled={!streamDialog.selectedVideoItag}><i class="fa-solid fa-list"></i> In Queue</button>
            <button class="btn-primary-dl" onclick={() => startPreviewDownload({
              itag: streamDialog.selectedVideoItag, audioItag: streamDialog.selectedAudioItag,
              mergeAudio: streamDialog.mergeAudio, priority: 10
            })} disabled={!streamDialog.selectedVideoItag}><i class="fa-solid fa-bolt"></i> Sofort laden</button>
          </div>
        </div>
      {/if}
    </div>
  </div>
{/if}

<!-- Video-Link-Lookup Dialog -->
<VideoLinkDialog bind:this={videoLinkDialogRef} bind:dialog={videoLinkDialog} parentVideoId={video?.id || ''} onLinked={onLinkedUpdate} onVideoOpen={loadVideo} />
<AddToPlaylistDialog bind:videoId={addToPlaylistVideoId} />

<style>
  .watch-page { padding: 12px 24px 24px; max-width: 1100px; position: relative; }
  .watch-page.with-lyrics-sidebar { max-width: none !important; padding-right: 470px; }
  .watch-page.with-playlist-sidebar { max-width: none !important; padding-right: 380px; }
  .watch-page.with-dual-sidebar { max-width: none !important; padding-right: 820px; }
  .watch-page.resizing { user-select: none; }
  .watch-main { flex: 1; min-width: 0; }

  /* ─── Resize Handle ─── */
  .resize-handle {
    position: absolute; top: 0; right: 0; width: 8px;
    height: 100%; cursor: col-resize; z-index: 15;
    display: flex; align-items: center; justify-content: center;
    opacity: 0.3; transition: opacity 0.2s;
  }
  .resize-handle:hover, .watch-page.resizing .resize-handle { opacity: 1; }
  .resize-dots {
    width: 4px; height: 40px; border-radius: 2px;
    background: var(--border-primary);
  }
  .resize-handle:hover .resize-dots { background: var(--accent-primary); }

  /* ─── Sidebar shared ─── */
  .lyrics-sidebar, .playlist-sidebar {
    position: fixed; top: 56px;
    bottom: var(--activity-panel-height, 34px);
    background: var(--bg-secondary);
    border-left: 1px solid var(--border-primary);
    display: flex; flex-direction: column;
    overflow: hidden;
    z-index: 20;
  }
  .lyrics-sidebar { width: 440px; }
  .playlist-sidebar { width: 350px; }

  /* Playlist: immer ganz rechts */
  .playlist-sidebar { right: 0; }

  /* Lyrics: rechts neben Playlist wenn beide da, sonst ganz rechts */
  .lyrics-sidebar { right: 0; }

  /* Lyrics Sidebar internals */
  .lyrics-sidebar-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 10px 14px; border-bottom: 1px solid var(--border-primary);
    font-size: 0.85rem; font-weight: 600; color: var(--text-primary);
    flex-shrink: 0;
  }
  .lyrics-sidebar-header i { margin-right: 6px; }
  .lyrics-header-actions { display: flex; gap: 4px; }
  .sidebar-btn {
    background: none; border: none; color: var(--text-tertiary); cursor: pointer;
    font-size: 0.82rem; padding: 4px 6px; border-radius: 4px;
  }
  .sidebar-btn:hover { color: var(--text-primary); background: var(--bg-tertiary); }
  .sidebar-btn.active { color: var(--accent-primary); }
  .lyrics-sidebar-content { flex: 1; overflow: hidden; padding: 8px; display: flex; flex-direction: column; }

  .pl-header {
    padding: 12px 14px 10px;
    border-bottom: 1px solid var(--border-primary);
    flex-shrink: 0;
  }
  .pl-header-top { display: flex; align-items: center; justify-content: space-between; }
  .pl-name { font-size: 0.88rem; font-weight: 700; color: var(--text-primary); display: flex; align-items: center; gap: 8px; }
  .pl-close {
    width: 28px; height: 28px; border-radius: 6px; border: none;
    background: transparent; color: var(--text-tertiary); cursor: pointer;
    display: flex; align-items: center; justify-content: center; font-size: 0.8rem;
  }
  .pl-close:hover { background: var(--bg-hover, var(--bg-tertiary)); color: var(--text-primary); }
  .pl-info {
    display: flex; gap: 6px; align-items: center; margin-top: 6px;
    font-size: 0.72rem; color: var(--text-tertiary);
  }
  .pl-pos { color: var(--accent-primary); font-weight: 600; }
  .pl-sep { opacity: 0.4; }
  .pl-controls {
    display: flex; gap: 4px; margin-top: 8px;
  }
  .pl-ctrl-btn {
    padding: 5px 12px; border-radius: 6px; border: 1px solid var(--border-primary);
    background: var(--bg-primary); color: var(--text-secondary);
    font-size: 0.72rem; cursor: pointer; display: flex; align-items: center; gap: 4px;
  }
  .pl-ctrl-btn:hover:not(:disabled) { border-color: var(--accent-primary); color: var(--accent-primary); }
  .pl-ctrl-btn:disabled { opacity: 0.3; cursor: not-allowed; }

  .pl-list {
    flex: 1; overflow-y: auto; overflow-x: hidden;
    scrollbar-width: thin;
    scrollbar-color: var(--border-primary) transparent;
  }

  .pl-item {
    display: flex; align-items: center; gap: 8px;
    padding: 7px 10px 7px 6px;
    cursor: pointer; border: none; background: none;
    width: 100%; text-align: left;
    border-left: 3px solid transparent;
    color: var(--text-primary);
    transition: background 0.12s;
  }
  .pl-item:hover { background: var(--bg-tertiary); }
  .pl-item.playing {
    background: color-mix(in srgb, var(--accent-primary) 12%, transparent);
    border-left-color: var(--accent-primary);
  }
  .pl-item.played .pl-text-title { color: var(--text-tertiary); }

  .pl-index {
    width: 22px; flex-shrink: 0; text-align: center;
    font-size: 0.7rem; color: var(--text-tertiary); font-weight: 500;
  }
  .pl-item.playing .pl-index { color: var(--accent-primary); }

  .pl-thumb {
    width: 90px; height: 50px; flex-shrink: 0; border-radius: 5px;
    background: var(--bg-tertiary); position: relative; overflow: hidden;
  }
  .pl-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .pl-dur {
    position: absolute; bottom: 2px; right: 2px;
    background: rgba(0,0,0,0.8); color: #fff; font-size: 0.6rem;
    padding: 1px 4px; border-radius: 3px; font-weight: 500;
  }

  .pl-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  .pl-text-title {
    font-size: 0.76rem; font-weight: 500; color: var(--text-primary);
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    overflow: hidden; line-height: 1.3;
  }
  .pl-text-channel {
    font-size: 0.66rem; color: var(--text-tertiary);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }

  .pl-footer {
    padding: 8px 14px; border-top: 1px solid var(--border-primary);
    flex-shrink: 0; font-size: 0.72rem; color: var(--text-tertiary);
  }

  @media (max-width: 960px) {
    .watch-page { max-width: none !important; }
    .watch-page.with-lyrics-sidebar, .watch-page.with-playlist-sidebar, .watch-page.with-dual-sidebar { padding-right: 24px; }
    .lyrics-sidebar, .playlist-sidebar {
      width: 100%; position: static;
      max-height: 300px; border-left: none;
      border-top: 1px solid var(--border-primary);
    }
    .resize-handle { display: none; }
  }

  .player-wrap {
    position: relative; background: #000; border-radius: 12px;
    overflow: hidden; aspect-ratio: 16/9; margin-bottom: 20px;
  }
  .video-player { width: 100%; height: 100%; display: block; }

  /* Suggestion Overlay */
  /* Preview Mode */
  .preview-thumb { width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; border-radius: 12px; }
  .preview-placeholder { width: 100%; aspect-ratio: 16/9; background: var(--bg-tertiary); display: flex; align-items: center; justify-content: center; font-size: 4rem; border-radius: 12px; color: var(--text-tertiary); }
  .preview-overlay {
    position: absolute; inset: 0; display: flex; flex-direction: column;
    align-items: center; justify-content: center; gap: 16px;
    background: rgba(0,0,0,0.5); border-radius: 12px;
  }
  .preview-dl-btn {
    width: 64px; height: 64px; border-radius: 50%;
    background: var(--accent-primary); color: #fff; border: none;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.4rem; cursor: pointer;
    transition: transform 0.15s, background 0.15s;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4);
  }
  .preview-dl-btn:hover:not(:disabled) { transform: scale(1.1); background: var(--accent-hover); }
  .preview-dl-btn:disabled { opacity: 0.6; }
  .preview-actions-bar {
    display: flex; gap: 8px;
  }
  .preview-bar-btn {
    display: flex; align-items: center; gap: 6px;
    padding: 8px 16px; background: rgba(0,0,0,0.6); color: #fff;
    border: 1px solid rgba(255,255,255,0.2); border-radius: 8px;
    font-size: 0.78rem; font-weight: 600; cursor: pointer;
    transition: all 0.15s; backdrop-filter: blur(4px);
  }
  .preview-bar-btn:hover:not(:disabled) { background: rgba(0,0,0,0.8); border-color: rgba(255,255,255,0.4); }
  .meta-right { display: flex; align-items: center; gap: 8px; }
  .desc-toggle {
    background: none; border: none; color: var(--accent-primary);
    font-size: 0.82rem; cursor: pointer; padding: 4px 0; margin-bottom: 4px;
    display: flex; align-items: center; gap: 6px;
  }
  .desc-toggle:hover { text-decoration: underline; }
  .yt-link { display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 8px; color: var(--text-secondary); font-size: 0.82rem; text-decoration: none; }
  .yt-link:hover { border-color: var(--accent-primary); color: var(--accent-primary); }

  .video-title { font-size: 1.3rem; font-weight: 700; color: var(--text-primary); margin: 0 0 12px; line-height: 1.3; }

  .video-meta-row { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; }
  .meta-left { display: flex; align-items: center; gap: 6px; font-size: 0.88rem; color: var(--text-secondary); }
  .channel { font-weight: 600; color: var(--text-primary); cursor: pointer; background: none; border: none; padding: 0; font-size: inherit; }
  .channel:hover { color: var(--accent-primary); }
  .dot { color: var(--text-tertiary); }
  .play-count { color: var(--accent-primary); font-weight: 500; }
  .meta-right { display: flex; gap: 6px; }

  .action-btn {
    display: flex; align-items: center; justify-content: center;
    width: 40px; height: 40px; background: var(--bg-secondary);
    border: 1px solid var(--border-primary); border-radius: 10px;
    color: var(--text-secondary); cursor: pointer; transition: all 0.15s;
    position: relative;
  }
  .action-btn:hover { border-color: var(--accent-primary); color: var(--text-primary); }
  .action-btn.active { border-color: var(--status-error); }
  .action-btn.danger:hover { border-color: var(--status-error); color: var(--status-error); }
  .action-btn.suggest-exclude { text-decoration: line-through; opacity: 0.5; border-color: var(--status-warning); color: var(--status-warning); }
  .action-btn.suggest-include { border-color: var(--status-success); color: var(--status-success); }
  .btn-badge { position: absolute; top: -4px; right: -4px; font-size: 0.55rem; background: var(--accent-primary); color: #fff; padding: 0 4px; border-radius: 6px; line-height: 1.4; pointer-events: none; }

  /* Playlist Picker */
  /* ─── Nav Strip (Playlist + Skip) ─── */
  .nav-strip {
    display: flex; align-items: center; gap: 6px; margin: 8px 0 5px;
  }
  .skip-btn {
    display: flex; align-items: center; gap: 5px;
    padding: 4px 8px; min-height: 32px; border-radius: 6px; border: 1px solid var(--border-secondary);
    background: none; color: var(--text-secondary); cursor: pointer; font-size: 0.78rem;
    flex-shrink: 1; min-width: 0; max-width: 200px; overflow: hidden;
  }
  .skip-btn:hover:not(:disabled) { border-color: var(--accent-primary); color: var(--accent-primary); }
  .skip-btn:disabled { opacity: 0.25; cursor: default; }
  .skip-btn i { flex-shrink: 0; }
  .skip-label {
    font-size: 0.68rem; color: var(--text-tertiary); white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis;
  }
  .skip-btn:hover:not(:disabled) .skip-label { color: var(--accent-primary); }

  .strip-main {
    flex: 1; display: flex; align-items: center; gap: 8px;
    padding: 5px 10px; background: var(--bg-tertiary); border-radius: 7px;
    border: 1px solid var(--border-primary); font-size: 0.78rem; min-width: 0;
  }
  .strip-main.active { border-color: var(--accent-primary); background: rgba(0,188,212,0.06); }
  .strip-main.library { color: var(--text-tertiary); }

  .strip-icon { color: var(--accent-primary); font-size: 0.68rem; flex-shrink: 0; }
  .strip-label { color: var(--text-tertiary); font-size: 0.75rem; }

  .strip-pager {
    background: none; border: none; color: var(--text-tertiary); cursor: pointer;
    width: 20px; height: 20px; font-size: 0.58rem; border-radius: 4px;
    display: flex; align-items: center; justify-content: center;
  }
  .strip-pager:hover { color: var(--text-primary); background: var(--bg-secondary); }
  .strip-pager-num { font-size: 0.62rem; color: var(--text-tertiary); font-variant-numeric: tabular-nums; }

  .strip-name {
    font-weight: 500; color: var(--text-primary); white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis; cursor: pointer;
    background: none; border: none; font: inherit; padding: 0; text-align: left;
  }
  .strip-name:hover { color: var(--accent-primary); }

  .strip-count {
    font-size: 0.65rem; color: var(--text-tertiary); background: var(--bg-secondary);
    padding: 1px 5px; border-radius: 4px; flex-shrink: 0;
  }
  .strip-pos {
    font-size: 0.65rem; color: var(--accent-primary); font-weight: 600;
    font-variant-numeric: tabular-nums; flex-shrink: 0;
  }
  .strip-playing { color: var(--accent-primary); font-size: 0.65rem; flex-shrink: 0; }
  .strip-play {
    background: none; border: 1px solid var(--border-secondary); color: var(--text-tertiary);
    cursor: pointer; width: 24px; height: 24px; border-radius: 5px; font-size: 0.6rem;
    display: flex; align-items: center; justify-content: center; flex-shrink: 0; margin-left: auto;
  }
  .strip-play:hover { color: var(--accent-primary); border-color: var(--accent-primary); }

  /* Tabs */
  .tabs { display: flex; gap: 2px; margin-bottom: 16px; border-bottom: 1px solid var(--border-primary); padding-bottom: 0; }
  .tab {
    display: flex; align-items: center; gap: 4px;
    padding: 8px 14px; background: none; border: none; border-bottom: 2px solid transparent;
    color: var(--text-secondary); font-size: 0.82rem; cursor: pointer; transition: all 0.12s;
  }
  .tab:hover { color: var(--text-primary); }
  .tab.active { color: var(--accent-primary); border-bottom-color: var(--accent-primary); font-weight: 600; }
  .tab-badge { font-size: 0.65rem; background: var(--accent-muted); color: var(--accent-primary); padding: 0 5px; border-radius: 8px; }

  .info-cards { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
  .info-card { background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 8px; padding: 10px 16px; display: flex; flex-direction: column; gap: 2px; }
  .info-label { font-size: 0.72rem; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.04em; }
  .info-value { font-size: 0.95rem; font-weight: 600; color: var(--text-primary); }

  .tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; }
  .tag { padding: 3px 10px; background: var(--accent-muted); color: var(--accent-primary); border-radius: 12px; font-size: 0.76rem; font-weight: 500; cursor: pointer; border: 1px solid transparent; transition: all 0.15s; }
  .tag:hover { border-color: var(--accent-primary); background: var(--accent-primary); color: #fff; }

  .notes-box { background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 10px; padding: 12px 16px; margin-bottom: 16px; }
  .notes-label { font-size: 0.72rem; color: var(--text-tertiary); text-transform: uppercase; display: flex; align-items: center; gap: 4px; margin-bottom: 8px; }
  .md-content, .md-preview { font-size: 0.88rem; color: var(--text-secondary); line-height: 1.6; }
  :global(.md-content h1, .md-preview h1) { font-size: 1.2rem; margin: 0 0 8px; color: var(--text-primary); }
  :global(.md-content h2, .md-preview h2) { font-size: 1.05rem; margin: 0 0 6px; color: var(--text-primary); }
  :global(.md-content h3, .md-preview h3) { font-size: 0.95rem; margin: 0 0 4px; color: var(--text-primary); }
  :global(.md-content p, .md-preview p) { margin: 0 0 8px; }
  :global(.md-content ul, .md-preview ul, .md-content ol, .md-preview ol) { margin: 0 0 8px; padding-left: 20px; }
  :global(.md-content li, .md-preview li) { margin: 2px 0; }
  :global(.md-content a, .md-preview a) { color: var(--accent-primary); text-decoration: none; }
  :global(.md-content a:hover, .md-preview a:hover) { text-decoration: underline; }
  :global(.md-content code, .md-preview code) { background: var(--bg-tertiary); padding: 1px 5px; border-radius: 3px; font-size: 0.82rem; }
  :global(.md-content pre, .md-preview pre) { background: var(--bg-tertiary); padding: 10px; border-radius: 6px; overflow-x: auto; margin: 0 0 8px; }
  :global(.md-content blockquote, .md-preview blockquote) { border-left: 3px solid var(--accent-primary); padding-left: 12px; margin: 0 0 8px; color: var(--text-tertiary); }
  :global(.md-content strong, .md-preview strong) { color: var(--text-primary); }
  :global(.md-content img, .md-preview img) { max-width: 100%; border-radius: 6px; }

  .description { background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 10px; padding: 16px; }
  .description p, .desc-body { margin: 0; font-size: 0.88rem; color: var(--text-secondary); line-height: 1.6; white-space: pre-line; word-break: break-word; }

  .btn-link { background: none; border: none; color: var(--accent-primary); cursor: pointer; font-size: 0.85rem; padding: 8px 0 0; }


  /* Ad-Markers (Werbung) */
  .ad-badge { background: rgba(239,83,80,0.15) !important; color: #EF5350 !important; }


  /* Edit */
  .rating-stars { display: flex; gap: 2px; }
  .star-btn { background: none; border: none; font-size: 1.2rem; cursor: pointer; color: var(--text-tertiary); transition: color 0.1s, transform 0.1s; padding: 1px; line-height: 1; }
  .star-btn.filled { color: #f59e0b; }
  .star-btn:hover { color: #f59e0b; transform: scale(1.15); }


  /* Watch-spezifische Stream-Dialog Styles */
  .stream-section.small h3 { font-size: 0.75rem; }
  .stream-tag.prog { background: var(--status-success); color: #fff; }
  .stream-tag.adaptive { background: var(--bg-tertiary); color: var(--text-tertiary); }
  .option-check { display: flex; align-items: center; gap: 8px; font-size: 0.82rem; color: var(--text-secondary); cursor: pointer; }
  .option-check input { accent-color: var(--accent-primary); }
  .stream-hint { font-size: 0.76rem; color: var(--status-warning); margin-top: 6px; display: flex; align-items: center; gap: 6px; }
  .stream-hint-ok { color: var(--status-success); }
  .section-disabled { opacity: 0.4; pointer-events: none; }
  .section-hint { font-size: 0.72rem; font-weight: 400; color: var(--text-tertiary); }
  .option-disabled { opacity: 0.4; cursor: not-allowed; }
  .caption-list { font-size: 0.78rem; color: var(--text-tertiary); }
  .dl-summary {
    display: flex; gap: 10px; align-items: center; margin-bottom: 10px;
    padding: 6px 10px; background: var(--bg-secondary); border-radius: 8px;
    font-size: 0.78rem; color: var(--text-secondary);
  }
  .dl-sum-ok { color: var(--status-success); }
  .dl-sum-warn { color: var(--status-warning); }
  .dl-buttons { display: flex; gap: 8px; justify-content: flex-end; }
  .btn-queue-dl { padding: 8px 18px; background: var(--bg-tertiary); border: 1px solid var(--border-primary); border-radius: 8px; color: var(--text-primary); font-size: 0.85rem; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 6px; }
  .btn-queue-dl:hover { border-color: var(--accent-primary); }
  .btn-primary-dl { display: flex; align-items: center; gap: 6px; padding: 8px 18px; background: var(--accent-primary); color: #fff; border: none; border-radius: 8px; font-size: 0.85rem; font-weight: 600; cursor: pointer; }
  .btn-primary-dl:hover { background: var(--accent-hover); }
</style>

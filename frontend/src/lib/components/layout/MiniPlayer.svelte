<!--
  TubeVault -  MiniPlayer v1.9.12
  Kompakter Player in der Sidebar für persistente Wiedergabe.
  Playlist-Queue-Navigation + Bibliothek-Fallback.
  Audio: Auto-Advance. Video: manuell skippen.
  © HalloWelt42 -  Private Nutzung
-->
<script>
  import { miniPlayer, deactivateMiniPlayer, updateMiniPlayerTime, activateMiniPlayer } from '../../stores/miniPlayer.js';
  import { playlistQueue, nextInQueue, prevInQueue, hasNext, hasPrev } from '../../stores/playlistQueue.js';
  import { navigate } from '../../router/router.js';
  import { api } from '../../api/client.js';

  let videoEl = $state(null);
  let audioOnly = $state(false);
  let isPlaying = $state(false);
  let currentTime = $state(0);
  let duration = $state(0);
  let seekHover = $state(false);

  // Init-Tracking
  let _initDone = false;
  let _initVideoId = null;
  let _startTime = 0;
  let _shouldPlay = false;

  // Bibliothek-Nachbarn (Fallback wenn keine Queue aktiv)
  let _neighbors = $state({ prev: null, next: null });
  let _neighborsFor = null;  // videoId für die Nachbarn geladen wurden

  let mp = $derived($miniPlayer);
  let q = $derived($playlistQueue);

  // Wenn sich die videoId ändert → Init vorbereiten
  $effect(() => {
    const vid = mp.videoId;
    const active = mp.active;
    if (active && vid && vid !== _initVideoId) {
      _initVideoId = vid;
      _initDone = false;
      _startTime = mp.currentTime || 0;
      _shouldPlay = mp.isPlaying ?? true;
      audioOnly = mp.audioOnly ?? false;
      // Bibliothek-Nachbarn laden wenn keine Queue
      if (!$playlistQueue.active && vid !== _neighborsFor) {
        loadNeighbors(vid);
      }
    }
  });

  async function loadNeighbors(videoId) {
    try {
      _neighbors = await api.getVideoNeighbors(videoId);
      _neighborsFor = videoId;
    } catch {
      _neighbors = { prev: null, next: null };
      _neighborsFor = videoId;
    }
  }

  function onCanPlay() {
    if (!videoEl || _initDone) return;
    _initDone = true;
    videoEl.volume = $miniPlayer.volume ?? 0.8;
    if (_startTime > 1) {
      videoEl.currentTime = _startTime;
    }
    if (_shouldPlay) {
      videoEl.play().catch(() => {});
    }
  }

  function togglePlay() {
    if (!videoEl) return;
    if (videoEl.paused) {
      videoEl.play().catch(() => {});
    } else {
      videoEl.pause();
    }
  }

  // ─── Navigation: Playlist-Queue ODER Bibliothek ────────
  function playNext() {
    if ($playlistQueue.active && hasNext()) {
      const nextId = nextInQueue();
      if (nextId) { switchToVideo(nextId); return; }
    }
    if (!$playlistQueue.active && _neighbors.next) {
      const n = _neighbors.next;
      switchToVideo(n.id, n.title, n.channel_name);
      return;
    }
    // Nichts mehr → stoppen
    if (videoEl) videoEl.pause();
    isPlaying = false;
  }

  function playPrev() {
    if ($playlistQueue.active && hasPrev()) {
      const prevId = prevInQueue();
      if (prevId) { switchToVideo(prevId); return; }
    }
    if (!$playlistQueue.active && _neighbors.prev) {
      const n = _neighbors.prev;
      switchToVideo(n.id, n.title, n.channel_name);
    }
  }

  function switchToVideo(videoId, title, channelName) {
    if (!videoEl) return;
    videoEl.pause();

    // Titel aus Queue oder Parameter
    const t = title || getQueueTitle(videoId) || videoId;
    const ch = channelName || getQueueChannel(videoId) || '';

    // Direkt neue Source laden + .load() für Browser
    videoEl.src = api.streamUrl(videoId);
    videoEl.load();

    // Init-State vorbereiten
    _initDone = false;
    _initVideoId = videoId;
    _startTime = 0;
    _shouldPlay = true;

    // Store aktualisieren (UI: Titel, Thumbnail, Badge)
    activateMiniPlayer({
      videoId,
      title: t,
      channelName: ch,
      currentTime: 0,
      duration: 0,
      volume: videoEl?.volume ?? 0.8,
      isPlaying: true,
      audioOnly,
      thumbnailUrl: api.thumbnailUrl(videoId),
    });

    // Bibliothek-Nachbarn für neues Video laden
    if (!$playlistQueue.active) {
      loadNeighbors(videoId);
    }
  }

  function getQueueTitle(videoId) {
    const qState = $playlistQueue;
    if (!qState.active) return null;
    const v = qState.videos.find(v => v.id === videoId);
    return v?.title || null;
  }

  function getQueueChannel(videoId) {
    const qState = $playlistQueue;
    if (!qState.active) return null;
    const v = qState.videos.find(v => v.id === videoId);
    return v?.channel_name || null;
  }

  function toggleAudioOnly() {
    audioOnly = !audioOnly;
  }

  function goToSource() {
    const state = $miniPlayer;
    if (!state.videoId) return;
    const t = Math.floor(currentTime);
    if (videoEl) { videoEl.pause(); videoEl.src = ''; }
    _initDone = false;
    _initVideoId = null;
    deactivateMiniPlayer();
    navigate(`/watch/${state.videoId}${t > 5 ? `?t=${t}` : ''}`);
  }

  function stopMini() {
    if (videoEl) { videoEl.pause(); videoEl.src = ''; }
    _initDone = false;
    _initVideoId = null;
    deactivateMiniPlayer();
  }

  function onTimeUpdate() {
    if (!videoEl) return;
    currentTime = videoEl.currentTime;
    duration = videoEl.duration || 0;
    isPlaying = !videoEl.paused;
    if (Math.abs(currentTime - ($miniPlayer.currentTime || 0)) > 2) {
      updateMiniPlayerTime(currentTime);
    }
  }

  function onPlay() { isPlaying = true; }
  function onPause() { isPlaying = false; }

  function onEnded() {
    isPlaying = false;
    const vid = $miniPlayer.videoId;
    if (vid) api.savePosition(vid, 0).catch(() => {});

    // Audio/Musik: automatisch weiter. Video: stoppen.
    if (audioOnly) {
      playNext();
    }
  }

  function seekTo(e) {
    if (!videoEl || !duration) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    videoEl.currentTime = pct * duration;
  }

  function fmt(s) {
    if (!s || isNaN(s)) return '0:00';
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, '0')}`;
  }

  // ─── Derived: Skip-Buttons aktivieren ──────────────────
  let canPrev = $derived(
    (q.active && q.currentIndex > 0) ||
    (!q.active && _neighbors.prev !== null)
  );
  let canNext = $derived(
    (q.active && q.currentIndex < q.videos.length - 1) ||
    (!q.active && _neighbors.next !== null)
  );
  let queueInfo = $derived.by(() => {
    if (q.active && q.videos.length > 0) {
      return `${q.currentIndex + 1}/${q.videos.length}`;
    }
    return null;
  });
</script>

{#if mp.active && mp.videoId}
  <div class="mini-player" class:audio-only={audioOnly}>
    <div class="mp-video-wrap">
      <!-- svelte-ignore a11y_media_has_caption -->
      <video
        bind:this={videoEl}
        class="mp-video"
        class:hidden={audioOnly}
        src={api.streamUrl(mp.videoId)}
        poster={api.thumbnailUrl(mp.videoId)}
        preload="auto"
        oncanplay={onCanPlay}
        ontimeupdate={onTimeUpdate}
        onplay={onPlay}
        onpause={onPause}
        onended={onEnded}
      ></video>
      {#if audioOnly}
        <div class="mp-audio-overlay">
          <i class="fa-solid fa-headphones"></i>
        </div>
      {/if}
      <button class="mp-close" onclick={stopMini} title="Schließen">
        <i class="fa-solid fa-xmark"></i>
      </button>
      {#if queueInfo}
        <div class="mp-queue-badge">{queueInfo}</div>
      {:else if !q.active}
        <div class="mp-queue-badge mp-lib-badge"><i class="fa-solid fa-clock-rotate-left"></i></div>
      {/if}
    </div>

    <!-- Progress bar -->
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <div
      class="mp-progress"
      class:hover={seekHover}
      onclick={seekTo}
      onmouseenter={() => seekHover = true}
      onmouseleave={() => seekHover = false}
      role="progressbar"
      aria-valuenow={currentTime}
      aria-valuemin={0}
      aria-valuemax={duration}
    >
      <div class="mp-progress-fill" style="width:{duration ? (currentTime/duration*100) : 0}%"></div>
    </div>

    <!-- Title -->
    <button class="mp-title" onclick={goToSource} title="{mp.title} — zurück zum Video">
      {mp.title}
    </button>

    <!-- Controls -->
    <div class="mp-controls">
      <button onclick={playPrev} disabled={!canPrev} title="Vorheriges Video">
        <i class="fa-solid fa-backward-step"></i>
      </button>
      <button class="mp-play" onclick={togglePlay} title={isPlaying ? 'Pause' : 'Play'}>
        <i class="fa-solid {isPlaying ? 'fa-pause' : 'fa-play'}"></i>
      </button>
      <button onclick={playNext} disabled={!canNext} title="Nächstes Video">
        <i class="fa-solid fa-forward-step"></i>
      </button>
      <button class="mp-audio-btn" class:active={audioOnly} onclick={toggleAudioOnly} title={audioOnly ? 'Video an' : 'Nur Audio'}>
        <i class="fa-solid {audioOnly ? 'fa-video' : 'fa-headphones'}"></i>
      </button>
      <button onclick={goToSource} title="Zurück zum Video">
        <i class="fa-solid fa-up-right-from-square"></i>
      </button>
    </div>

    <!-- Time -->
    <div class="mp-time">{fmt(currentTime)} / {fmt(duration)}</div>
  </div>
{/if}

<style>
  .mini-player {
    margin: 0 4px;
    border-radius: 8px;
    overflow: hidden;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-primary);
  }

  .mp-video-wrap {
    position: relative;
    width: 100%;
    aspect-ratio: 16 / 9;
    background: #000;
  }

  .mp-video {
    width: 100%;
    height: 100%;
    object-fit: contain;
    display: block;
  }
  .mp-video.hidden { opacity: 0; }

  .mp-audio-overlay {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-tertiary);
    color: var(--accent-primary);
    font-size: 2rem;
  }

  .mp-close {
    position: absolute;
    top: 4px;
    right: 4px;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: rgba(0,0,0,0.6);
    color: #fff;
    border: none;
    cursor: pointer;
    font-size: 0.6rem;
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0;
    transition: opacity 0.15s;
  }
  .mp-video-wrap:hover .mp-close { opacity: 1; }

  .mp-queue-badge {
    position: absolute;
    bottom: 4px;
    right: 4px;
    padding: 1px 6px;
    border-radius: 4px;
    background: rgba(0,0,0,0.7);
    color: var(--accent-primary);
    font-size: 0.6rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  .mp-lib-badge {
    color: var(--text-tertiary);
    font-size: 0.5rem;
  }

  .mp-progress {
    height: 3px;
    background: var(--bg-hover);
    cursor: pointer;
    transition: height 0.1s;
  }
  .mp-progress.hover { height: 6px; }
  .mp-progress-fill {
    height: 100%;
    background: var(--accent-primary);
    border-radius: 0 1px 1px 0;
    transition: width 0.3s linear;
  }

  .mp-title {
    display: block;
    width: 100%;
    padding: 4px 8px 2px;
    font-size: 0.7rem;
    font-weight: 600;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    background: none;
    border: none;
    cursor: pointer;
    text-align: left;
  }
  .mp-title:hover { color: var(--accent-primary); }

  .mp-controls {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 2px;
    padding: 2px 4px;
  }
  .mp-controls button {
    width: 28px;
    height: 24px;
    border: none;
    background: none;
    color: var(--text-secondary);
    cursor: pointer;
    border-radius: 4px;
    font-size: 0.7rem;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.1s;
  }
  .mp-controls button:hover:not(:disabled) {
    background: var(--bg-hover);
    color: var(--text-primary);
  }
  .mp-controls button:disabled {
    opacity: 0.3;
    cursor: default;
  }
  .mp-play {
    width: 32px !important;
    height: 28px !important;
    font-size: 0.85rem !important;
    color: var(--accent-primary) !important;
  }
  .mp-audio-btn.active {
    color: var(--accent-primary) !important;
    background: var(--accent-muted);
  }

  .mp-time {
    text-align: center;
    font-size: 0.6rem;
    color: var(--text-tertiary);
    padding: 0 8px 6px;
    font-variant-numeric: tabular-nums;
  }

  .mini-player.audio-only .mp-video-wrap {
    aspect-ratio: auto;
    height: 48px;
  }
</style>

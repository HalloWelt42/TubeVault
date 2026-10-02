<!--
  Wiedergabe: Player oben, darunter das Nötigste (Titel, Kanal, Favorit,
  Kapitel, Beschreibung). Die Position wird gemerkt und fortgesetzt, wenn die
  Einstellung "Position merken" eingeschaltet ist.
-->
<script>
  import { api } from '../../lib/api/client.js';
  import { formatDuration, formatDateRelative } from '../../lib/utils/format.js';
  import { getSettingBool, getSettingNum } from '../../lib/stores/settings.js';
  import { back } from '../router.js';
  import { say } from '../notice.js';
  import HoldButton from '../parts/HoldButton.svelte';

  let { id } = $props();

  const SAVE_EVERY_MS = 10000;
  const RESUME_MIN_S = 5;
  const RESUME_END_GAP_S = 10;
  const LONG_DESCRIPTION_CHARS = 180;

  let video = $state(null);
  let failed = $state(false);
  let isFav = $state(false);
  let chapters = $state([]);
  let showDescription = $state(false);
  let queued = $state(false);
  let player = $state(null);
  let playRecorded = false;
  let saveTimer = null;

  const remember = () => getSettingBool('player.save_position', true);
  let isLongDescription = $derived(
    (video?.description || '').length > LONG_DESCRIPTION_CHARS
    || (video?.description || '').split('\n').length > 4
  );

  async function load() {
    failed = false;
    try {
      video = await api.getVideoPreview(id);
      if (!video.preview_mode) {
        api.checkFavorite(id).then(r => { isFav = !!r.is_favorite; }).catch(() => {});
        api.getChapters(id).then(r => { chapters = r.chapters || []; }).catch(() => {});
      }
    } catch { failed = true; }
  }

  function onLoadedMetadata() {
    player.volume = getSettingNum('player.volume', 80) / 100;
    player.playbackRate = getSettingNum('player.speed', 1.0);
    const pos = video.last_position || 0;
    if (remember() && pos > RESUME_MIN_S && pos < (player.duration || 0) - RESUME_END_GAP_S) {
      player.currentTime = pos;
      say('Fortgesetzt bei ' + formatDuration(pos));
    }
  }

  function savePosition() {
    if (!player || !remember() || player.currentTime < 1) return;
    api.savePosition(id, player.currentTime).catch(() => {});
  }

  function onPlay() {
    if (!playRecorded) {
      playRecorded = true;
      api.recordPlay(id, player.currentTime).catch(() => {});
    }
    clearInterval(saveTimer);
    saveTimer = setInterval(savePosition, SAVE_EVERY_MS);
  }

  function onPause() {
    clearInterval(saveTimer);
    savePosition();
  }

  async function toggleFavorite() {
    try {
      if (isFav) await api.removeFavorite(id);
      else await api.addFavorite({ video_id: id, list_name: 'Standard' });
      isFav = !isFav;
      say(isFav ? 'Zu den Favoriten hinzugefügt' : 'Aus den Favoriten entfernt', 'ok');
    } catch (e) { say(e.message, 'warn'); }
  }

  async function download() {
    try {
      await api.addDownload({ url: `https://www.youtube.com/watch?v=${id}` });
      queued = true;
      say('Eingereiht', 'ok');
    } catch (e) { say(e.message, 'warn'); }
  }

  function seek(seconds) {
    if (!player) return;
    player.currentTime = seconds;
    player.play().catch(() => {});
  }

  $effect(() => {
    load();
    const onHide = () => { if (document.hidden) savePosition(); };
    document.addEventListener('visibilitychange', onHide);
    return () => {
      document.removeEventListener('visibilitychange', onHide);
      clearInterval(saveTimer);
      savePosition();
    };
  });
</script>

<div class="m-view video-view">
  <header class="bar">
    <button class="back" aria-label="Zurück" onclick={back}><i class="fa-solid fa-chevron-left"></i></button>
  </header>

  {#if failed}
    <div class="m-note">
      <p>Das Video konnte nicht geladen werden.</p>
      <button class="m-btn" onclick={load}><i class="fa-solid fa-rotate"></i> Erneut versuchen</button>
    </div>
  {:else if !video}
    <div class="m-spin"><i class="fa-solid fa-spinner fa-spin"></i></div>
  {:else}
    {#if video.preview_mode}
      <div class="stage poster">
        <img src={api.rssThumbUrl(id)} alt="" />
      </div>
    {:else}
      <!-- svelte-ignore a11y_media_has_caption -->
      <video class="stage" bind:this={player} src={api.streamUrl(id)} poster={api.thumbnailUrl(id)}
             controls playsinline preload="metadata"
             onloadedmetadata={onLoadedMetadata} onplay={onPlay} onpause={onPause} onended={onPause}></video>
    {/if}

    <section class="info">
      <h1 class="title">{video.title}</h1>
      <p class="meta">
        {video.channel_name || 'Unbekannt'}
        {#if video.duration} · {formatDuration(video.duration)}{/if}
        {#if video.upload_date || video.published} · {formatDateRelative(video.upload_date || video.published)}{/if}
      </p>

      {#if video.preview_mode}
        <div class="load">
          {#if queued}
            <span class="waiting"><i class="fa-solid fa-clock"></i> In der Warteschlange</span>
          {:else}
            <HoldButton label="Laden" onfire={download} />
            <span class="hint">Gedrückt halten, um das Video zu laden</span>
          {/if}
        </div>
      {:else}
        <button class="m-btn fav" class:on={isFav} onclick={toggleFavorite}>
          <i class="{isFav ? 'fa-solid' : 'fa-regular'} fa-heart"></i> {isFav ? 'Favorit' : 'Zu Favoriten'}
        </button>
      {/if}
    </section>

    {#if chapters.length > 0}
      <h2 class="m-h2">Kapitel</h2>
      {#each chapters as chapter (chapter.id ?? chapter.start_time)}
        <button class="chapter" onclick={() => seek(chapter.start_time)}>
          <span class="time">{formatDuration(chapter.start_time)}</span>
          <span class="name">{chapter.title}</span>
        </button>
      {/each}
    {/if}

    {#if video.description}
      <h2 class="m-h2">Beschreibung</h2>
      <p class="description" class:open={showDescription || !isLongDescription}>{video.description}</p>
      {#if isLongDescription}
        <button class="more" onclick={() => showDescription = !showDescription}>
          {showDescription ? 'Weniger zeigen' : 'Mehr zeigen'}
        </button>
      {/if}
    {/if}
  {/if}
</div>

<style>
  .video-view { background: var(--m-bg); padding-bottom: calc(var(--m-safe-bottom) + 24px); }
  .bar { padding: var(--m-safe-top) 4px 0; }
  .back { width: 52px; height: 48px; font-size: 1.15rem; color: var(--m-text); }
  .stage { display: block; width: 100%; aspect-ratio: 16 / 9; background: #000; max-height: 62dvh; }
  .poster img { width: 100%; height: 100%; object-fit: contain; display: block; }
  .info { padding: 16px; }
  .title { font-size: 1.2rem; font-weight: 600; line-height: 1.25; }
  .meta { margin-top: 6px; color: var(--m-dim); font-size: 0.9rem; }
  .fav { margin-top: 16px; }
  .fav.on { color: var(--m-accent); border-color: var(--m-accent); }
  .load { display: flex; align-items: center; gap: 12px; margin-top: 16px; }
  .hint { color: var(--m-dim); font-size: 0.9rem; }
  .waiting { color: var(--m-warn); font-weight: 600; min-height: 52px; display: flex; align-items: center; gap: 8px; }
  .chapter {
    width: 100%; min-height: var(--m-touch); padding: 8px 16px; text-align: left;
    display: flex; gap: 14px; align-items: baseline; border-bottom: 1px solid var(--m-line);
  }
  .chapter:active { background: var(--m-surface); }
  .time { flex: 0 0 auto; color: var(--m-accent); font-weight: 600; font-variant-numeric: tabular-nums; font-size: 0.9rem; }
  .description {
    padding: 0 16px; color: var(--m-dim); white-space: pre-wrap; overflow-wrap: anywhere;
    display: -webkit-box; -webkit-line-clamp: 4; line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden;
  }
  .description.open { display: block; }
  .more { min-height: var(--m-touch); padding: 0 16px; color: var(--m-accent); font-weight: 600; }
</style>

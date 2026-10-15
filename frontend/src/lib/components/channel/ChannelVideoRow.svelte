<!--
  Ein Video auf der Kanalseite (Entwurf mockups/kanal.html): Bild mit Dauer,
  Titel, Marken nur für Abweichungen (neu, nicht geladen, wartet, gelöscht,
  gesperrt, Short, Live), Datum, Aufrufe, Größe. Nicht Geladenes ist
  abgeblendet. Die Hauptaktion (Abspielen bzw. Laden) steht immer, Playlist
  und Mehr erscheinen beim Überfahren.
-->
<script>
  import { api } from '../../api/client.js';
  import { formatDate, formatDuration, formatSize, formatViews } from '../../utils/format.js';
  import LanguageLabel from '../common/LanguageLabel.svelte';
  import QuickPlaylistBtn from '../common/QuickPlaylistBtn.svelte';

  /** video: Eintrag aus api.getChannelVideos; onplay(video), onload(video), onmore(event, video) */
  let { video, channel, loading = false, onplay, onload, onmore } = $props();

  let local = $derived(!!video.is_downloaded);
  let image = $derived(local && video.thumbnail_path ? api.thumbnailUrl(video.video_id) : api.rssThumbUrl(video.video_id));
  let mark = $derived(local ? null
    : video.is_in_queue ? { cls: 'wartet', icon: 'fa-clock', text: 'Wartet', title: 'Steht in den Downloads' }
    : video.is_deleted ? { cls: '', icon: 'fa-trash-can', text: 'Gelöscht', title: 'Von dir gelöscht: wird nie von selbst geladen, nur wenn du es ausdrücklich lädst' }
    : video.blocked_reason ? { cls: 'gesperrt', icon: 'fa-ban', text: 'Gesperrt', title: video.blocked_reason }
    : { cls: '', icon: 'fa-cloud', text: 'Nicht geladen', title: 'Liegt nur bei der Quelle' });

  function fallback(event) {
    const img = event.currentTarget;
    if (local && !img.dataset.quelle) { img.dataset.quelle = '1'; img.src = api.rssThumbUrl(video.video_id); }
    else img.style.visibility = 'hidden';
  }
</script>

<div class="zeile" class:fern={!local}>
  <button class="bild" onclick={() => (local ? onplay(video) : onload(video))} title={local ? 'Abspielen' : 'Herunterladen'}>
    <img src={image} alt="" loading="lazy" onerror={fallback} />
    {#if video.duration}<span class="dauer zahl">{formatDuration(video.duration)}</span>{/if}
  </button>
  <div class="text">
    <button class="titel" onclick={() => (local ? onplay(video) : onload(video))}>{video.title || video.video_id}</button>
    <div class="angaben">
      {#if video.rss_status === 'new'}<span class="marke neu">Neu</span>{/if}
      {#if mark}<span class="marke {mark.cls}" title={mark.title}><i class="fa-solid {mark.icon}"></i> {mark.text}</span>{/if}
      {#if video.video_type === 'short'}<span class="marke short"><i class="fa-solid fa-bolt"></i> Short</span>{/if}
      {#if video.video_type === 'live'}<span class="marke live"><i class="fa-solid fa-tower-broadcast"></i> Live</span>{/if}
      <LanguageLabel code={video.language} source={video.language_source} />
      {#if video.published}<span class="zahl">{formatDate(video.published)}</span>{/if}
      {#if video.view_count}<span class="zahl">{formatViews(video.view_count)} Aufrufe</span>{/if}
      {#if local && video.file_size}<span class="zahl">{formatSize(video.file_size)}</span>{/if}
    </div>
  </div>
  <div class="tun">
    <span class="neben"><QuickPlaylistBtn videoId={video.video_id} title={video.title} channelName={channel?.channel_name}
                                           channelId={video.channel_id || channel?.channel_id} size="sm" /></span>
    <button class="neben" onclick={(e) => onmore(e, video)} title="Mehr" aria-label="Mehr"><i class="fa-solid fa-ellipsis"></i></button>
    {#if local}
      <button class="haupt spielen" onclick={() => onplay(video)} title="Abspielen" aria-label="Abspielen"><i class="fa-solid fa-play"></i></button>
    {:else if video.is_in_queue}
      <span class="haupt" title="Wartet in den Downloads"><i class="fa-solid fa-clock"></i></span>
    {:else}
      <button class="haupt laden" onclick={() => onload(video)} disabled={loading} title="Herunterladen" aria-label="Herunterladen">
        <i class="fa-solid {loading ? 'fa-spinner fa-spin' : 'fa-download'}"></i></button>
    {/if}
  </div>
</div>

<style>
  .zeile { display: grid; grid-template-columns: 168px minmax(0, 1fr) auto; align-items: center; gap: var(--tv-a4);
           padding: var(--tv-a2); border-radius: var(--tv-ecke); }
  .zeile:hover { background: var(--tv-flaeche); }
  .bild { position: relative; aspect-ratio: 16 / 9; padding: 0; border: 0; border-radius: var(--tv-ecke-klein); overflow: hidden;
          background: var(--tv-mulde); cursor: pointer; }
  .bild img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .fern .bild img { opacity: 0.45; filter: grayscale(0.6); }
  .dauer { position: absolute; right: 5px; bottom: 6px; padding: 1px 6px; border-radius: var(--tv-ecke-klein);
           background: var(--tv-schleier); color: var(--tv-text); font-size: var(--tv-gr-marke); }
  .text { min-width: 0; }
  .titel { display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
           padding: 0; border: 0; background: none; color: var(--tv-text); font: inherit; font-weight: 600; line-height: 1.3;
           text-align: left; cursor: pointer; }
  .titel:hover { color: var(--tv-akzent); }
  .fern .titel { color: var(--tv-text-2); }
  .angaben { display: flex; flex-wrap: wrap; align-items: center; gap: 4px var(--tv-a3); margin-top: 4px;
             font-size: var(--tv-gr-klein); color: var(--tv-text-3); }
  .marke { display: inline-flex; align-items: center; gap: 5px; height: 24px; padding: 0 8px; border-radius: var(--tv-ecke-klein);
           font-size: var(--tv-gr-marke); font-weight: 700; background: var(--tv-karte-2); color: var(--tv-text-2); }
  .marke.neu { color: var(--tv-akzent); background: rgba(var(--tv-akzent-rgb), 0.12); }
  .marke.wartet { color: var(--tv-info); background: rgba(var(--tv-info-rgb), 0.12); }
  .marke.gesperrt { color: var(--tv-warnung); }
  .marke.short { color: var(--tv-art-short); }
  .marke.live { color: var(--tv-art-live); }
  .tun { display: flex; align-items: center; gap: 2px; }
  .neben { opacity: 0; transition: opacity var(--tv-schnell); }
  .zeile:hover .neben, .neben:focus-visible, .neben:focus-within { opacity: 1; }
  button.neben, .haupt { width: 40px; height: 40px; display: grid; place-items: center; border: 0; border-radius: var(--tv-ecke);
                         background: none; color: var(--tv-text-2); cursor: pointer; font-size: 16px; }
  button.neben:hover { background: var(--tv-karte-2); color: var(--tv-text); }
  .haupt.spielen { background: var(--tv-akzent); color: var(--tv-akzent-text); }
  .haupt.spielen:hover { background: var(--tv-akzent-hell); }
  .haupt.laden { background: var(--tv-karte-2); color: var(--tv-text); }
  .haupt.laden:hover:not(:disabled) { background: var(--tv-karte-3); }
  span.haupt { cursor: default; color: var(--tv-info); }
</style>

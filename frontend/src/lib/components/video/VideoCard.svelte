<script>
  /**
   * TubeVault – Videokachel (Gestaltung nach mockups/stil.css: .kachel)
   *
   * Bild mit dünner Kante, darunter Titel und eine Zeile Angaben. Auf dem
   * Bild nur Abweichendes: Art (Short, Live), zusätzliche Tonspuren, Dauer und
   * wie weit schon gesehen. Beim Überfahren: in Playlist, archivieren.
   * © HalloWelt42 – Private Nutzung
   */
  import { api } from '../../api/client.js';
  import { navigate } from '../../router/router.js';
  import { toast } from '../../stores/notifications.js';
  import { formatDuration, formatDate, formatViews } from '../../utils/format.js';
  import LikeBar from '../common/LikeBar.svelte';
  import QuickPlaylistBtn from '../common/QuickPlaylistBtn.svelte';
  import HoverActionOverlay from '../common/HoverActionOverlay.svelte';
  import HoverActionBtn from '../common/HoverActionBtn.svelte';

  // onPlay: statt einfach zu öffnen, z.B. in einer Warteschlange abspielen
  let { video, showArchiveBtn = true, onUpdate = null, onPlay = null } = $props();
  let hidden = $state(false);

  // Gesehener Anteil: erst ab ein paar Sekunden, damit Antippen nicht zählt
  const SEEN_FROM_SECONDS = 5;
  let seen = $derived(
    video.duration && video.last_position > SEEN_FROM_SECONDS
      ? Math.min(1, video.last_position / video.duration) : 0);

  function play() {
    if (onPlay) onPlay(video);
    else navigate(`/watch/${video.id}`);
  }

  async function archiveVideo(e) {
    e.stopPropagation();
    try {
      await api.archiveVideo(video.id);
      hidden = true;
      toast.success('Archiviert');
      onUpdate?.();   // die Liste des Aufrufers neu laden
    } catch (err) { toast.error(err.message); }
  }

  function openChannel(e) {
    e.stopPropagation();
    if (video.channel_id) navigate(`/channel/${video.channel_id}`);
  }

  function onCardKeydown(e) {
    // Enter/Leertaste auf der Kachel (nicht auf inneren Knöpfen) spielt das Video
    if ((e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget) {
      e.preventDefault();
      play();
    }
  }
</script>

{#if !hidden}
<!-- role="button" statt <button>, damit innere Knöpfe (Kanal) valide bleiben;
     .card-wrap und .video-card tragen die Überfahr-Aktionen (global.css) -->
<div class="card-wrap kachel video-card" role="button" tabindex="0" onclick={play} onkeydown={onCardKeydown}>
  <div class="bild">
    <img src={api.thumbnailUrl(video.id)} alt="" loading="lazy"
         onerror={(e) => e.target.style.visibility = 'hidden'} />

    <div class="arten">
      {#if video.status !== 'ready'}
        <span class="art status-{video.status}">{video.status}</span>
      {/if}
      {#if video.video_type === 'short'}
        <span class="art short"><i class="fa-solid fa-mobile-screen"></i> Short</span>
      {:else if video.video_type === 'live'}
        <span class="art live"><i class="fa-solid fa-tower-broadcast"></i> Live</span>
      {/if}
      {#each video.extra_audio || [] as track}
        {#if track === 'neu'}
          <span class="art vertont" title="In der Originalsprache mit anderer Stimme neu gesprochen - in der Wiedergabe umschaltbar">
            <i class="fa-solid fa-microphone-lines"></i> neu gesprochen
          </span>
        {:else}
          <span class="art vertont" title="Übersetzte Tonspur ({track.toUpperCase()}) - in der Wiedergabe umschaltbar">
            <i class="fa-solid fa-language"></i> {track.toUpperCase()}
          </span>
        {/if}
      {/each}
    </div>

    <span class="dauer zahl">{formatDuration(video.duration)}</span>
    {#if seen}
      <div class="gesehen" title="Zu {Math.round(seen * 100)} % gesehen"><b style:width="{seen * 100}%"></b></div>
    {/if}

    <HoverActionOverlay>
      <QuickPlaylistBtn videoId={video.id} title={video.title}
                        channelName={video.channel_name} channelId={video.channel_id} size="sm" />
      {#if showArchiveBtn && !video.is_archived}
        <HoverActionBtn variant="warn" onclick={archiveVideo} title="Archivieren">
          <i class="fa-solid fa-box-archive"></i>
        </HoverActionBtn>
      {/if}
    </HoverActionOverlay>
  </div>

  <div class="text">
    <h3 class="titel">{video.title}</h3>
    <div class="meta">
      {#if video.channel_id}
        <button class="kanal" onclick={openChannel} title="Zum Kanal">{video.channel_name || 'Unbekannt'}</button>
      {:else}
        <span class="kanal">{video.channel_name || 'Unbekannt'}</span>
      {/if}
      {#if video.view_count}<span class="zahl">{formatViews(video.view_count)} Aufrufe</span>{/if}
      {#if video.upload_date}<span class="zahl">{formatDate(video.upload_date)}</span>{/if}
      {#if video.like_count && video.dislike_count != null}
        <LikeBar likes={video.like_count} dislikes={video.dislike_count} mode="compact" />
      {/if}
    </div>
  </div>
</div>
{/if}

<style>
  .kachel { display: flex; flex-direction: column; gap: var(--tv-a2); cursor: pointer; color: var(--tv-text); position: relative; }
  .kachel:focus-visible { outline: 2px solid var(--tv-akzent); outline-offset: 4px; }

  .bild {
    position: relative; aspect-ratio: 16 / 9; overflow: hidden; background: var(--tv-mulde);
    border-radius: var(--tv-ecke); outline: 1px solid var(--tv-rand); outline-offset: -1px;
  }
  .bild img { width: 100%; height: 100%; object-fit: cover; display: block; transition: transform 300ms ease; }
  .kachel:hover .bild img { transform: scale(1.04); }

  .arten { position: absolute; left: 8px; top: 8px; display: flex; flex-wrap: wrap; gap: 4px; z-index: 1; }
  .art {
    display: inline-flex; align-items: center; gap: 5px; height: 24px; padding: 0 8px;
    font-size: var(--tv-gr-marke); font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
    border-radius: var(--tv-ecke-klein); background: var(--tv-schleier); color: var(--tv-text);
  }
  .art.short { color: var(--tv-art-short); }
  .art.live { color: var(--tv-art-live); }
  .art.vertont { color: var(--tv-art-vertont); text-transform: none; letter-spacing: 0; }
  .art.status-error { color: var(--tv-gefahr); }
  .art.status-pending, .art.status-downloading { color: var(--tv-info); }

  .dauer {
    position: absolute; right: 8px; bottom: 8px; z-index: 1;
    height: 24px; padding: 0 7px; display: flex; align-items: center;
    background: var(--tv-schleier); border-radius: var(--tv-ecke-klein);
    font-size: var(--tv-gr-marke); font-weight: 600;
  }
  .gesehen { position: absolute; left: 0; right: 0; bottom: 0; height: 4px; background: rgba(0, 0, 0, 0.5); z-index: 1; }
  .gesehen b { display: block; height: 100%; background: var(--tv-akzent); }

  .text { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .titel {
    margin: 0; font-size: var(--tv-gr-text); font-weight: 600; line-height: 1.3;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .kachel:hover .titel { color: var(--tv-akzent); }
  .meta {
    display: flex; flex-wrap: wrap; align-items: center; gap: 2px 10px;
    font-size: var(--tv-gr-klein); color: var(--tv-text-2);
  }
  .kanal {
    background: none; border: none; padding: 0; font: inherit; text-align: left;
    color: var(--tv-text); font-weight: 500; cursor: pointer;
  }
  button.kanal:hover { color: var(--tv-akzent); text-decoration: underline; }
</style>

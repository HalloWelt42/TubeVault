<!--
  TubeVault - Vergleichen: Original und Nachvertonung an derselben Stelle
  (Entwurf mockups/nachvertonung.html?zustand=vergleich)
  Das Video spielt klein mit; der Umschalter wechselt nur den Ton. Die
  vertonte Spur läuft im Gleichlauf mit dem Video (utils/audioTrackSync.js),
  genau wie in der Wiedergabe.
-->
<script>
  import { onDestroy } from 'svelte';
  import { api } from '../../api/client.js';
  import { followVideo } from '../../utils/audioTrackSync.js';
  import { formatDuration } from '../../utils/format.js';
  import { direction } from '../../utils/dubbingText.js';

  let { request, onClose } = $props();

  const STEP_SECONDS = 5;

  let videoEl = $state(null);
  let audioEl = $state(null);
  let dubbed = $state(true);          // true: vertonte Spur hörbar, false: Original
  let paused = $state(true);
  let time = $state(0);
  let measured = $state(0);          // Dauer laut Video, sobald bekannt
  let lang = $derived(direction(request));
  let newLabel = $derived(lang.revoice ? 'Neu gesprochen' : lang.target);
  let length = $derived(measured || request.duration || 0);

  // Gleichlauf nur, solange die vertonte Spur hörbar sein soll
  $effect(() => {
    if (!dubbed || !videoEl || !audioEl) return;
    const sync = followVideo(videoEl, audioEl);
    return () => sync.stop();
  });

  function toggle() {
    if (!videoEl) return;
    if (videoEl.paused) videoEl.play().catch(() => {});
    else videoEl.pause();
  }

  function seekTo(seconds) {
    if (!videoEl || !length) return;
    videoEl.currentTime = Math.max(0, Math.min(length, seconds));
  }

  function seekClick(event) {
    const box = event.currentTarget.getBoundingClientRect();
    seekTo(((event.clientX - box.left) / box.width) * length);
  }

  function seekKey(event) {
    if (event.key === 'ArrowLeft') { event.preventDefault(); seekTo(time - STEP_SECONDS); }
    if (event.key === 'ArrowRight') { event.preventDefault(); seekTo(time + STEP_SECONDS); }
  }

  onDestroy(() => { videoEl?.pause(); audioEl?.pause(); });
</script>

<section class="vergleich" aria-label="Vergleichen">
  <!-- svelte-ignore a11y_media_has_caption -->
  <video bind:this={videoEl} src={api.streamUrl(request.video_id)} poster={api.thumbnailUrl(request.video_id)}
         preload="metadata" playsinline onclick={toggle}
         onplay={() => paused = false} onpause={() => paused = true}
         ontimeupdate={() => time = videoEl.currentTime}
         onloadedmetadata={() => measured = videoEl.duration || 0}></video>
  <audio bind:this={audioEl} src={api.audioTrackUrl(request.video_id, request.track_id)} preload="auto"></audio>

  <div class="mitte">
    <div class="kopf">
      <b>Vergleichen</b>
      <span class="titel" title={request.title}>{request.title || request.video_id}</span>
    </div>
    <div class="tv-leise tv-klein">Gleiche Stelle, Ton im Wechsel: Original und neu gesprochen.</div>
    <div class="zeitleiste">
      <button class="tv-knopf symbol klein" onclick={toggle} title={paused ? 'Abspielen' : 'Anhalten'}>
        <i class="fa-solid {paused ? 'fa-play' : 'fa-pause'}"></i></button>
      <span class="zahl">{formatDuration(Math.floor(time))}</span>
      <div class="balken" role="slider" tabindex="0" aria-label="Stelle im Video" aria-valuemin="0"
           aria-valuemax={Math.floor(length)} aria-valuenow={Math.floor(time)}
           title="Klicken springt an die Stelle, Pfeiltasten 5 Sekunden"
           onclick={seekClick} onkeydown={seekKey}>
        <b style:width="{length ? (time / length) * 100 : 0}%"></b>
      </div>
      <span class="zahl">{formatDuration(Math.floor(length))}</span>
    </div>
  </div>

  <div class="wechsel" role="group" aria-label="Ton">
    <button class:an={!dubbed} onclick={() => dubbed = false} title="Originalton des Videos">Original</button>
    <button class:an={dubbed} onclick={() => dubbed = true} title="Die vertonte Tonspur">{newLabel}</button>
  </div>
  <button class="tv-knopf symbol klein ohne zu" onclick={onClose} title="Vergleich schließen"><i class="fa-solid fa-xmark"></i></button>
</section>

<style>
  .vergleich { display: flex; gap: var(--tv-a4); align-items: center; padding: var(--tv-a4); margin-bottom: var(--tv-a4);
               background: var(--tv-karte); border-radius: var(--tv-ecke); }
  video { width: 200px; aspect-ratio: 16 / 9; flex: none; background: var(--tv-mulde); border-radius: var(--tv-ecke-klein);
          object-fit: cover; cursor: pointer; }
  .mitte { flex: 1; min-width: 0; }
  .kopf { display: flex; gap: var(--tv-a2); align-items: baseline; min-width: 0; }
  .kopf .titel { color: var(--tv-text-2); font-size: var(--tv-gr-klein); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .zeitleiste { display: flex; gap: var(--tv-a2); align-items: center; margin-top: var(--tv-a2); font-size: var(--tv-gr-klein); }
  .balken { flex: 1; height: 8px; background: var(--tv-mulde); border-radius: 1px; overflow: hidden; cursor: pointer; }
  .balken:focus-visible { outline: 1px solid rgba(var(--tv-akzent-rgb), 0.7); outline-offset: 2px; }
  .balken b { display: block; height: 100%; background: var(--tv-akzent); }
  .wechsel { display: inline-flex; flex: none; background: var(--tv-mulde); border-radius: var(--tv-ecke); padding: 2px; }
  .wechsel button { height: 34px; padding: 0 var(--tv-a3); border: 0; background: none; color: var(--tv-text-2);
                    border-radius: var(--tv-ecke-klein); font: inherit; font-size: var(--tv-gr-klein); cursor: pointer; }
  .wechsel button.an { background: var(--tv-karte-3); color: var(--tv-akzent); font-weight: 700; }
  .zu { align-self: flex-start; }

  @container liste (max-width: 700px) {
    .vergleich { flex-wrap: wrap; }
    video { width: 160px; }
    .mitte { flex-basis: calc(100% - 220px); }
    .wechsel { margin-left: auto; }
  }
</style>

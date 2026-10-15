<!--
  Karte "Gewählter Auftrag" in der rechten Spalte der Downloads-Seite.
-->
<script>
  import { api } from '../../api/client.js';
  import { navigate } from '../../router/router.js';
  import DownloadProgress from '../common/DownloadProgress.svelte';
  import { statusOf, canRetry, canDelay, canCancel, PRIORITY_LABELS } from './jobStatus.js';

  let {
    item, live = null, phaseFill = null,
    onClose = () => {}, onRetry = () => {}, onDelay = () => {}, onIgnore = () => {}, onCancel = () => {},
  } = $props();

  let status = $derived(statusOf(item.status));
  let stage = $derived(live?.stage || item.status);
  let progress = $derived(live?.progress ?? item.progress ?? 0);
  // Fertig geladen (oder als Reupload übersprungen): hier liegt das Video
  let target = $derived(item.status === 'done' ? (item.same_as?.id || item.video_id) : null);
  let playing = $state(false);
  $effect(() => { item.id; playing = false; });
</script>

<section class="tv-karte detail-panel">
  <h3><i class="fa-solid fa-circle-info"></i> Gewählter Auftrag
    <button class="tv-knopf ohne symbol klein schliessen" onclick={onClose} title="Schließen (Esc)"><i class="fa-solid fa-xmark"></i></button>
  </h3>
  <div class="vorschau">
    {#if playing && target}
      <!-- svelte-ignore a11y_media_has_caption -->
      <video src={api.streamUrl(target)} controls autoplay></video>
    {:else if target}
      <button class="abspielen" onclick={() => playing = true} title="Hier abspielen">
        <img src={api.thumbnailUrl(target)} alt="" onerror={(e) => e.target.style.visibility = 'hidden'} />
        <i class="fa-solid fa-play spielen"></i>
      </button>
    {:else if item.video_id}
      <img src={api.rssThumbUrl(item.video_id)} alt="" onerror={(e) => e.target.style.visibility = 'hidden'} />
    {/if}
  </div>
  <div class="titel">{item.title || item.video_id}</div>

  {#if item.status === 'active' && progress > 0}
    <DownloadProgress data={{ progress, stage, stage_label: live?.stage_label || '', phases: live?.phases || null, phaseFills: phaseFill }} />
  {/if}

  <dl class="angaben">
    <dt>Zustand</dt><dd><span class="tv-zustand {status.css}"><i class="fa-solid {status.icon}"></i> {status.label}</span></dd>
    {#if live?.stage_label}<dt>Schritt</dt><dd>{live.stage_label}</dd>{/if}
    {#if item.priority > 0}<dt>Priorität</dt><dd>{PRIORITY_LABELS[item.priority] || item.priority}</dd>{/if}
    {#if item.video_id}<dt>Video-ID</dt><dd class="kennung">{item.video_id}</dd>{/if}
  </dl>

  {#if item.error_message}
    <div class="tv-fehlertext"><i class="fa-solid fa-triangle-exclamation"></i><span>{item.error_message}</span></div>
  {/if}

  <div class="aktionen">
    {#if target}
      <button class="tv-knopf haupt klein" onclick={() => navigate(`/watch/${target}`)}>
        <i class="fa-solid fa-arrow-up-right-from-square"></i> Ansehen</button>
    {/if}
    {#if canRetry(item)}<button class="tv-knopf klein" onclick={onRetry}><i class="fa-solid fa-rotate-right"></i> Erneut</button>{/if}
    {#if canDelay(item)}
      <button class="tv-knopf klein" onclick={() => onDelay(5)}>In 5 Min</button>
      <button class="tv-knopf klein" onclick={() => onDelay(30)}>In 30 Min</button>
      <button class="tv-knopf klein" onclick={onIgnore}><i class="fa-solid fa-ban"></i> Ausschließen</button>
    {/if}
    {#if canCancel(item)}<button class="tv-knopf klein gefahr" onclick={onCancel}><i class="fa-solid fa-xmark"></i> Abbrechen</button>{/if}
  </div>
</section>

<style>
  h3 .schliessen { margin-left: auto; }
  .vorschau { aspect-ratio: 16 / 9; overflow: hidden; background: var(--tv-mulde); border-radius: var(--tv-ecke-klein); margin-bottom: var(--tv-a3); }
  .vorschau img, .vorschau video { width: 100%; height: 100%; object-fit: cover; display: block; }
  .vorschau video { object-fit: contain; background: #000; }
  .abspielen { position: relative; width: 100%; height: 100%; padding: 0; border: 0; background: none; cursor: pointer; display: grid; place-items: center; }
  .abspielen img { position: absolute; inset: 0; }
  .spielen { position: relative; font-size: 34px; color: var(--tv-text); opacity: 0.75; text-shadow: 0 2px 10px rgba(0, 0, 0, 0.6);
             transition: opacity var(--tv-schnell); }
  .abspielen:hover .spielen { opacity: 1; }
  .titel { font-weight: 600; margin-bottom: var(--tv-a3); }
  .angaben { display: grid; grid-template-columns: auto 1fr; gap: 6px var(--tv-a3); align-items: center; font-size: var(--tv-gr-klein); margin: var(--tv-a3) 0; }
  .angaben dt { color: var(--tv-text-3); }
  .angaben dd { margin: 0; }
  .kennung { font-family: ui-monospace, monospace; }
  .aktionen { display: flex; flex-wrap: wrap; gap: var(--tv-a2); margin-top: var(--tv-a3); }
</style>

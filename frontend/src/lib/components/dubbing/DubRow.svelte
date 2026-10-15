<!--
  TubeVault - Ein Auftrag der Nachvertonung als Zeile (Entwurf mockups/nachvertonung.html)
  Bild, Titel, Kanal, Dauer und wann; Sprachen und Stimme; rechts feste
  Plätze für die Aktionen, damit nichts springt:
    1 Abspielen mit der vertonten Spur (wenn es sie gibt), sonst Erneut versuchen
    2 Vergleichen (wenn es die Spur gibt)
    3 Mit anderer Stimme neu vertonen
    4 Mehr
  Eine Rückfrage (confirm) erscheint direkt unter der Zeile.
-->
<script>
  import { api } from '../../api/client.js';
  import { formatDuration } from '../../utils/format.js';
  import { direction, timing } from '../../utils/dubbingText.js';
  import InlineConfirm from './InlineConfirm.svelte';

  let {
    item,
    comparing = false,
    canRevoice = false,
    confirm = null,          // { text, label, run } oder null
    onOpen, onPlay, onCompare, onRevoice, onRetry, onMenu, onConfirmClose,
  } = $props();

  const FAILED = ['error', 'skipped', 'cancelled'];
  let lang = $derived(direction(item));
  let failed = $derived(FAILED.includes(item.status));
</script>

<div class="zeile" class:vergleich={comparing} role="listitem">
  <button class="bild" onclick={() => onOpen(item)} title="Video öffnen">
    <img src={api.thumbnailUrl(item.video_id)} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
    {#if item.duration}<span class="dauer zahl">{formatDuration(item.duration)}</span>{/if}
  </button>

  <div class="text">
    <button class="titel" onclick={() => onOpen(item)} title="Video öffnen">{item.title || item.video_id}</button>
    <div class="meta">{[item.channel_name, timing(item)].filter(Boolean).join(' · ')}</div>
    {#if item.note && item.status !== 'done'}
      <div class="notiz" class:fehler={item.status === 'error'} title={item.note}>{item.note}</div>
    {/if}
  </div>

  <div class="sprache">
    <span class="sprachen">
      {#if lang.revoice}{lang.target}, neu gesprochen
      {:else if lang.source}{lang.source} <i class="fa-solid fa-arrow-right"></i> {lang.target}
      {:else}nach {lang.target}{/if}
    </span>
    <div class="stimme" title="Stimme">{item.voice || 'Vorauswahl'}</div>
  </div>

  <div class="tun">
    {#if item.track_id}
      <button class="spielen" onclick={() => onPlay(item)} title="Auf {lang.target} abspielen"><i class="fa-solid fa-play"></i></button>
    {:else if failed}
      <button class="spielen" onclick={() => onRetry(item)} title="Erneut versuchen"><i class="fa-solid fa-rotate-right"></i></button>
    {:else}<span></span>{/if}
    {#if item.track_id}
      <button class:an={comparing} onclick={() => onCompare(item)} title="Original und Neu im Wechsel vergleichen"><i class="fa-solid fa-code-compare"></i></button>
    {:else}<span></span>{/if}
    {#if canRevoice}
      <button onclick={(e) => onRevoice(e, item)} title={item.status === 'queued' ? 'Andere Stimme wählen' : 'Mit anderer Stimme neu vertonen'}>
        <i class="fa-solid fa-microphone"></i></button>
    {:else}<span></span>{/if}
    <button onclick={(e) => onMenu(e, item)} title="Mehr"><i class="fa-solid fa-ellipsis"></i></button>
  </div>
</div>
{#if confirm}
  <InlineConfirm text={confirm.text} confirmLabel={confirm.label} onConfirm={confirm.run} onCancel={onConfirmClose} />
{/if}

<style>
  .zeile { display: grid; grid-template-columns: 160px minmax(0, 1fr) 160px 164px; grid-template-areas: "bild text sprache tun";
           gap: var(--tv-a3); align-items: center; padding: 6px var(--tv-a2); border-radius: var(--tv-ecke); }
  .zeile:hover { background: var(--tv-flaeche); }
  .zeile.vergleich { background: rgba(var(--tv-akzent-rgb), 0.08); }
  .bild { grid-area: bild; position: relative; aspect-ratio: 16 / 9; padding: 0; border: 0; border-radius: var(--tv-ecke-klein);
          overflow: hidden; background: var(--tv-mulde); cursor: pointer; }
  .bild img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .dauer { position: absolute; right: 5px; bottom: 5px; padding: 0 5px; height: 20px; display: grid; place-items: center;
           background: var(--tv-schleier); border-radius: var(--tv-ecke-klein); font-size: var(--tv-gr-marke); font-weight: 700; color: var(--tv-text); }
  .text { grid-area: text; min-width: 0; }
  .titel { display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; padding: 0; border: 0;
           background: none; color: var(--tv-text); font: inherit; font-weight: 600; text-align: left; cursor: pointer; }
  .titel:hover { color: var(--tv-akzent); }
  .meta { font-size: var(--tv-gr-klein); color: var(--tv-text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .notiz { font-size: var(--tv-gr-klein); color: var(--tv-text-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .notiz.fehler { color: var(--tv-gefahr); }
  .sprache { grid-area: sprache; min-width: 0; }
  .sprachen { display: inline-flex; align-items: center; flex-wrap: wrap; gap: 4px 6px; font-weight: 700; font-size: var(--tv-gr-marke); }
  .stimme { font-size: var(--tv-gr-klein); color: var(--tv-text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .tun { grid-area: tun; display: grid; grid-template-columns: repeat(4, 38px); justify-content: end; gap: 2px; }
  .tun button { width: 38px; height: 38px; border: 0; background: none; color: var(--tv-text-2); border-radius: var(--tv-ecke);
                cursor: pointer; font-size: 15px; }
  .tun button:hover { background: var(--tv-karte-2); color: var(--tv-text); }
  .tun button.spielen { background: var(--tv-akzent); color: var(--tv-akzent-text); }
  .tun button.spielen:hover { background: var(--tv-akzent-hell); }
  .tun button.an { color: var(--tv-akzent); background: var(--tv-karte-2); }

  /* Schmale Spalte: Sprachen und Aktionen unter den Text */
  @container liste (max-width: 700px) {
    .zeile { grid-template-columns: 128px minmax(0, 1fr) auto; grid-template-areas: "bild text text" "bild sprache tun"; row-gap: var(--tv-a1); }
  }
  @container liste (max-width: 460px) {
    .zeile { grid-template-columns: 96px minmax(0, 1fr); grid-template-areas: "bild text" "sprache sprache" "tun tun"; }
    .tun { justify-content: start; }
  }
</style>

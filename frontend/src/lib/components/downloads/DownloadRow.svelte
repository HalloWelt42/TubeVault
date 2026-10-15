<!--
  Eine Zeile der Warteschlange (Gestaltung nach mockups/downloads.html: .auftrag).
  Zeigt nur die Knöpfe, die im jeweiligen Zustand etwas tun - so bleibt dem
  Titel Platz.
-->
<script>
  import { api } from '../../api/client.js';
  import DownloadProgress from '../common/DownloadProgress.svelte';
  import { statusOf, canRetry, canDelay, canCancel, PRIORITY_LABELS } from './jobStatus.js';

  let {
    item,
    live = null,            // Live-Stand aus dem Aktivitätskanal
    phaseFill = null,
    selected = false,
    onSelect = () => {},
    onRetry = () => {},
    onDelay = () => {},     // (minuten)
    onIgnore = () => {},
    onCancel = () => {},
    onPriority = () => {},
  } = $props();

  let status = $derived(statusOf(item.status));
  let stage = $derived(live?.stage || item.status);
  let progress = $derived(live?.progress ?? item.progress ?? 0);
  let waiting = $derived(item.status === 'queued' || item.status === 'retry_wait');

  // Klicks auf Knöpfe wählen die Zeile nicht zusätzlich aus
  const act = (fn) => (e) => { e.stopPropagation(); fn(); };
</script>

<div class="auftrag" class:gewaehlt={selected} role="button" tabindex="0"
     onclick={onSelect} onkeydown={(e) => e.key === 'Enter' && onSelect()}>
  <div class="vorschau">
    {#if item.video_id}
      <img src={api.rssThumbUrl(item.video_id)} alt="" loading="lazy" onerror={(e) => e.target.style.visibility = 'hidden'} />
    {/if}
  </div>

  <div class="text">
    <div class="titel" title={item.title || item.video_id}>{item.title || item.video_id}</div>
    <div class="zeile2">
      {#if waiting}
        <button class="tv-zustand {status.css}" onclick={act(onPriority)}
                title="Priorität wechseln (Normal, Hoch, Sofort)">
          <i class="fa-solid {status.icon}"></i> {status.label}{#if item.priority > 0}{' · '}{PRIORITY_LABELS[item.priority] || `Priorität ${item.priority}`}{/if}
        </button>
      {:else}
        <span class="tv-zustand {status.css}"><i class="fa-solid {status.icon}"></i> {status.label}</span>
      {/if}
      {#if item.status === 'active' && live?.stage_label}<span>{live.stage_label}</span>{/if}
      {#if item.status === 'done' && item.completed_at}<span class="zahl">{item.completed_at.slice(11, 16)}</span>{/if}
    </div>
    {#if item.status === 'active' && progress > 0}
      <DownloadProgress data={{ progress, stage, stage_label: live?.stage_label || '', phases: live?.phases || null, phaseFills: phaseFill }} />
    {/if}
    {#if item.error_message && (item.status === 'error' || item.status === 'retry_wait' || item.status === 'parked')}
      <div class="tv-fehlertext"><i class="fa-solid fa-triangle-exclamation"></i><span>{item.error_message}</span></div>
    {/if}
  </div>

  <div class="knoepfe">
    {#if canRetry(item)}
      <button class="tv-knopf ohne symbol klein" onclick={act(onRetry)} title="Erneut versuchen"><i class="fa-solid fa-rotate-right"></i></button>
    {/if}
    {#if canDelay(item)}
      <button class="tv-knopf ohne klein" onclick={act(() => onDelay(5))} title="In 5 Minuten erneut versuchen">5 Min</button>
      <button class="tv-knopf ohne klein" onclick={act(() => onDelay(30))} title="In 30 Minuten erneut versuchen">30 Min</button>
      <button class="tv-knopf ohne symbol klein" onclick={act(onIgnore)} title="Dauerhaft ausschließen"><i class="fa-solid fa-ban"></i></button>
    {/if}
    {#if canCancel(item)}
      <button class="tv-knopf ohne symbol klein" onclick={act(onCancel)} title="Abbrechen"><i class="fa-solid fa-xmark"></i></button>
    {/if}
  </div>
</div>

<style>
  .auftrag {
    display: grid; grid-template-columns: 128px minmax(0, 1fr) auto; gap: var(--tv-a3); align-items: center;
    padding: var(--tv-a3); border-radius: var(--tv-ecke); cursor: pointer;
  }
  .auftrag + :global(.auftrag) { margin-top: 2px; }
  .auftrag:hover { background: var(--tv-flaeche); }
  .auftrag.gewaehlt { background: var(--tv-karte); outline: 1px solid rgba(var(--tv-akzent-rgb), 0.5); }
  .auftrag:focus-visible { outline: 2px solid var(--tv-akzent); }
  .vorschau { aspect-ratio: 16 / 9; overflow: hidden; background: var(--tv-mulde); border-radius: var(--tv-ecke-klein); }
  .vorschau img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .text { min-width: 0; display: flex; flex-direction: column; gap: 6px; }
  .titel { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .zeile2 { display: flex; gap: var(--tv-a3); align-items: center; flex-wrap: wrap; font-size: var(--tv-gr-klein); color: var(--tv-text-2); }
  .knoepfe { display: flex; gap: 2px; }
</style>

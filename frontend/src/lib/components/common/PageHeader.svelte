<!--
  TubeVault – Seitenkopf (Gestaltung nach mockups/stil.css: .seitenkopf)
  Titel, Anzahl (und wahlweise Gesamtgröße) in der Zahlenschrift, optional
  "Filter zurücksetzen", rechts Platz für Aktionen der Seite.
  © HalloWelt42 – Private Nutzung
-->
<script>
  import { formatSize } from '../../utils/format.js';

  let {
    title,
    icon = null,
    count = null,
    bytes = null,          // Gesamtgröße der Treffer, falls bekannt
    unit = 'Video',
    unitPlural = null,
    hasFilter = false,
    onClearFilter = null,
    children,
  } = $props();

  let unitLabel = $derived(count === 1 ? unit : (unitPlural || unit + 's'));
</script>

<div class="page-header">
  <h1 class="page-title">
    {#if icon}<i class={icon}></i>{/if}
    {title}
  </h1>
  {#if count !== null}
    <span class="page-count zahl">
      {count.toLocaleString('de-DE')} {unitLabel}{#if bytes}{' · '}{formatSize(bytes)}{/if}
    </span>
  {/if}
  {#if hasFilter && onClearFilter}
    <button class="tv-knopf klein ohne" onclick={onClearFilter}>
      <i class="fa-solid fa-xmark"></i> Filter zurücksetzen
    </button>
  {/if}
  <div class="header-actions">
    {@render children?.()}
  </div>
</div>

<style>
  .page-header { display: flex; align-items: flex-end; gap: var(--tv-a4); margin-bottom: var(--tv-a5); flex-wrap: wrap; }
  .page-title {
    margin: 0; display: flex; align-items: center; gap: var(--tv-a3);
    font-size: var(--tv-gr-seite); font-weight: 700; line-height: 1.15; color: var(--tv-text);
  }
  .page-title i { color: var(--tv-akzent); font-size: 0.8em; }
  .page-count { font-size: var(--tv-gr-titel); font-weight: 500; color: var(--tv-text-3); }
  .header-actions { margin-left: auto; display: flex; gap: var(--tv-a2); align-items: center; }
</style>

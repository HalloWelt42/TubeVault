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
    iconColor = null,      // eigene Farbe des Symbols (z.B. Farbe einer Kategorie)
    count = null,
    bytes = null,          // Gesamtgröße der Treffer, falls bekannt
    unit = 'Video',
    unitPlural = null,
    hasFilter = false,
    onClearFilter = null,
    info = null,           // freie Kennzahlen statt Anzahl, z.B. "41 Videos · 21:37 Std."
    onBack = null,         // Zurück-Knopf vor dem Titel
    children,
  } = $props();

  let unitLabel = $derived(count === 1 ? unit : (unitPlural || unit + 's'));
</script>

<div class="page-header">
  {#if onBack}
    <button class="tv-knopf ohne symbol zurueck" onclick={onBack} title="Zurück"><i class="fa-solid fa-arrow-left"></i></button>
  {/if}
  <h1 class="page-title">
    {#if icon}<i class={icon} style:color={iconColor}></i>{/if}
    {title}
  </h1>
  {#if info}
    <span class="page-count zahl">{info}</span>
  {:else if count !== null}
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
  .header-actions { margin-left: auto; display: flex; gap: var(--tv-a2); align-items: center; flex-wrap: wrap; }
  .zurueck { align-self: center; }
</style>

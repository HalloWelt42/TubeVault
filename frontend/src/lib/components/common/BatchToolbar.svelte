<!--
  TubeVault – BatchToolbar v1.0.0
  Einheitliche Auswahl-Leiste für den Mehrfach-Modus: Zähler, „Alle wählen",
  danach seitenspezifische Aktions-Buttons (Snippet-Children). Button-Styles
  für Children kommen per :global unter .bulk-bar aus dieser Komponente —
  Seiten brauchen keine eigenen bulk-CSS-Kopien mehr.
  Konvention für Children: <button class="bulk-btn"> (+ .bulk-danger /
  .bulk-type für rote bzw. violette Hover-Akzente), <span class="bulk-sep">|</span>.
  © HalloWelt42 – Private Nutzung
-->
<script>
  // onDone: Auswahl-Modus mit "Fertig"; die Leiste steht dann auch ohne Auswahl
  let { selectedCount = 0, totalCount = 0, onSelectAll = null, onDone = null,
        hint = 'Videos antippen, um sie auszuwählen', children } = $props();
</script>

{#if selectedCount > 0 || onDone}
  <div class="bulk-bar">
    {#if selectedCount > 0}
      <span class="bulk-count zahl">{selectedCount.toLocaleString('de-DE')} ausgewählt</span>
    {:else}
      <span class="bulk-hinweis">{hint}</span>
    {/if}
    {#if onSelectAll}
      <button class="tv-knopf klein" onclick={onSelectAll}>
        <i class="fa-solid fa-check-double"></i> Alle <span class="zahl">({totalCount.toLocaleString('de-DE')})</span>
      </button>
      <span class="tv-trenner"></span>
    {/if}
    {#if selectedCount > 0}{@render children?.()}{/if}
    {#if onDone}
      <button class="tv-knopf klein ohne fertig" onclick={onDone}><i class="fa-solid fa-xmark"></i> Fertig</button>
    {/if}
  </div>
{/if}

<style>
  /* Auswahlleiste (mockups/stil.css: .filter mit Akzentkante) */
  .bulk-bar {
    display: flex; align-items: center; gap: var(--tv-a2); flex-wrap: wrap;
    padding: var(--tv-a3) var(--tv-a4); margin-bottom: var(--tv-a3);
    background: var(--tv-flaeche); border: 1px solid rgba(var(--tv-akzent-rgb), 0.55); border-radius: var(--tv-ecke);
  }
  .bulk-count { font-weight: 600; color: var(--tv-akzent); margin-right: var(--tv-a2); }
  .bulk-hinweis { color: var(--tv-text-2); margin-right: var(--tv-a2); }
  .fertig { margin-left: auto; }
  /* Ältere Seiten reichen noch .bulk-btn / .bulk-sep herein: gleiche Gestalt wie tv-knopf klein */
  .bulk-bar :global(.bulk-btn) {
    display: inline-flex; align-items: center; gap: var(--tv-a2); height: 34px; padding: 0 var(--tv-a3);
    background: var(--tv-karte-2); border: 1px solid var(--tv-rand-stark); border-radius: var(--tv-ecke);
    color: var(--tv-text); font: inherit; font-size: var(--tv-gr-klein); font-weight: 600; cursor: pointer;
  }
  .bulk-bar :global(.bulk-btn:hover) { background: var(--tv-karte-3); }
  .bulk-bar :global(.bulk-danger) { color: var(--tv-gefahr); }
  .bulk-bar :global(.bulk-sep) { color: transparent; width: 1px; align-self: stretch; background: var(--tv-rand); overflow: hidden; }
</style>

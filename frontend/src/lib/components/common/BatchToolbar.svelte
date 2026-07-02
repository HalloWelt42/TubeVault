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
  let { selectedCount = 0, totalCount = 0, onSelectAll = null, children } = $props();
</script>

{#if selectedCount > 0}
  <div class="bulk-bar">
    <span class="bulk-count">{selectedCount} ausgewählt</span>
    {#if onSelectAll}
      <button class="bulk-btn" onclick={onSelectAll}>
        <i class="fa-solid fa-check-double"></i> Alle ({totalCount})
      </button>
      <span class="bulk-sep">|</span>
    {/if}
    {@render children?.()}
  </div>
{/if}

<style>
  .bulk-bar { display:flex; align-items:center; gap:8px; padding:10px 14px; background:var(--bg-secondary); border:1px solid var(--accent-primary); border-radius:10px; margin-bottom:14px; flex-wrap:wrap; }
  .bulk-count { font-size:0.82rem; font-weight:600; color:var(--accent-primary); margin-right:4px; }
  .bulk-bar :global(.bulk-btn), .bulk-btn {
    padding:5px 12px; background:var(--bg-tertiary); border:1px solid var(--border-primary);
    border-radius:6px; color:var(--text-secondary); font-size:0.78rem; cursor:pointer;
    display:flex; align-items:center; gap:5px;
  }
  .bulk-bar :global(.bulk-btn:hover), .bulk-btn:hover { border-color:var(--accent-primary); color:var(--text-primary); }
  .bulk-bar :global(.bulk-danger:hover) { border-color:var(--status-error); color:var(--status-error); }
  .bulk-bar :global(.bulk-type:hover) { border-color:#ab47bc; color:#ab47bc; }
  .bulk-bar :global(.bulk-sep), .bulk-sep { color:var(--border-primary); font-size:0.9rem; }
</style>

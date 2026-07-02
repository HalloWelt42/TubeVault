<!--
  TubeVault – PageHeader v1.0.0
  Einheitlicher Seitenkopf: Titel (+Icon), Zähler, optional
  „Filter zurücksetzen", rechts Platz für seitenspezifische Aktionen
  (Snippet-Children — Styles der Buttons kommen aus der Seite).
  © HalloWelt42 – Private Nutzung
-->
<script>
  let {
    title,
    icon = null,
    count = null,
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
    <span class="page-count">{count} {unitLabel}</span>
  {/if}
  {#if hasFilter && onClearFilter}
    <button class="btn-clear-filter" onclick={onClearFilter}>
      <i class="fa-solid fa-xmark"></i> Filter zurücksetzen
    </button>
  {/if}
  <div class="header-actions">
    {@render children?.()}
  </div>
</div>

<style>
  .page-header { display:flex; align-items:baseline; gap:12px; margin-bottom:16px; flex-wrap:wrap; }
  .page-title { font-size:1.6rem; font-weight:700; color:var(--text-primary); margin:0; display:flex; align-items:center; gap:10px; }
  .page-title i { color:var(--accent-primary); }
  .page-count { font-size:0.9rem; color:var(--text-tertiary); }
  .btn-clear-filter { padding:5px 12px; background:none; border:1px solid var(--border-primary); border-radius:6px; color:var(--text-secondary); font-size:0.78rem; cursor:pointer; }
  .btn-clear-filter:hover { border-color:var(--status-error); color:var(--status-error); }
  .header-actions { margin-left:auto; display:flex; gap:6px; align-items:center; }
</style>

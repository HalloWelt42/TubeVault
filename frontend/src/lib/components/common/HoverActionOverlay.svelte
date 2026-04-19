<!--
  TubeVault – HoverActionOverlay v1.0.0
  Zentraler Overlay-Container für Hover-Action-Buttons.
  © HalloWelt42 – Private Nutzung
-->
<script>
  let { children } = $props();
</script>

<div class="card-hover-actions">
  {@render children?.()}
</div>

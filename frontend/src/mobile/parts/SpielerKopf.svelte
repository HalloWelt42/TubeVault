<!--
  Kopf der großen Spieleransichten: links Schließen, in der Mitte zwei
  Zeilen (z.B. "Spielt aus" / "ABBA Gold"), rechts ein Knopf der Ansicht.
-->
<script>
  let { oben, name, onclose, rechts = null } = $props();
</script>

<header class="kopf">
  <button class="m-rund" onclick={onclose} aria-label="Schließen"><i class="fa-solid fa-chevron-down"></i></button>
  <div class="mitte">
    <div class="oben">{oben}</div>
    <div class="name">{name}</div>
  </div>
  {#if rechts}{@render rechts()}{:else}<span></span>{/if}
</header>

<style>
  .kopf { display: grid; grid-template-columns: 44px minmax(0, 1fr) 44px; align-items: center; gap: 8px; height: 60px; flex: none; text-align: center; }
  .oben { font-size: 13px; font-weight: 600; color: var(--m-faint); letter-spacing: 0.06em; text-transform: uppercase; }
  .name { font-size: 15px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>

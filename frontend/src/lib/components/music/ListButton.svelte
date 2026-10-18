<!--
  Knopf "Zur Liste" der Abspielleiste: öffnet die Wahl der Wiedergabelisten
  (ListChooser) als schwebendes Feld nach oben.
-->
<script>
  import { clickedInside } from '../../utils/clickOutside.js';
  import ListChooser from './ListChooser.svelte';

  let { track } = $props();

  let open = $state(false);
  let box = $state(null);

  function outside(e) {
    if (open && !clickedInside(e, box)) open = false;
  }
</script>

<svelte:window onpointerdown={outside} onkeydown={(e) => { if (e.key === 'Escape') open = false; }} />

<div class="listen-knopf" bind:this={box}>
  <button class="taste" class:an={open} onclick={() => open = !open} title="Zur Liste: in eine Wiedergabeliste legen"
          aria-expanded={open}>
    <i class="fa-solid fa-square-plus"></i></button>
  {#if open}
    <div class="feld"><ListChooser {track} onDone={() => open = false} /></div>
  {/if}
</div>

<style>
  .listen-knopf { position: relative; flex: none; }
  .taste { width: 38px; height: 38px; display: grid; place-items: center; border: 0; background: none;
           color: var(--tv-text-2); border-radius: var(--tv-ecke); cursor: pointer; font-size: 16px; }
  .taste:hover, .taste.an { color: var(--tv-text); background: var(--tv-karte-2); }
  .feld { position: absolute; left: 0; bottom: calc(100% + 8px); z-index: 60; width: 320px; max-height: 50vh;
          display: flex; flex-direction: column; padding: var(--tv-a3); background: var(--tv-karte); border-radius: var(--tv-ecke);
          box-shadow: var(--tv-schatten); }
</style>

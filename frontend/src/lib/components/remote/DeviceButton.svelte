<!--
  Knopf "Geräte" am Rechner: öffnet die Geräteliste (DeviceList) als
  schwebendes Feld; mit "up" öffnet es nach oben (Leisten am unteren Rand).
-->
<script>
  import { remote } from '../../stores/remote.svelte.js';
  import DeviceList from './DeviceList.svelte';

  /** up: Feld öffnet nach oben (Leisten unten); framed: Knopf mit Fläche wie in Aktionsreihen */
  let { up = false, framed = false } = $props();

  let open = $state(false);
  let box = $state(null);
  let others = $derived(Math.max(0, remote.visible.length - 1));

  function outside(e) {
    if (open && box && !box.contains(e.target)) open = false;
  }
</script>

<svelte:window onpointerdown={outside} onkeydown={(e) => { if (e.key === 'Escape') open = false; }} />

<div class="geraete-knopf" bind:this={box}>
  <button class="taste" class:an={open} class:flaeche={framed} onclick={() => open = !open}
          title="Geräte: Wiedergabe hierher holen oder an ein anderes Gerät schicken" aria-expanded={open}>
    <i class="fa-solid fa-tower-broadcast"></i>
    {#if others}<span class="zahl anzahl">{others}</span>{/if}
  </button>
  {#if open}
    <div class="feld" class:oben={up}>
      <DeviceList onDone={() => open = false} />
    </div>
  {/if}
</div>

<style>
  .geraete-knopf { position: relative; }
  .taste { position: relative; width: 38px; height: 38px; display: grid; place-items: center; border: 0; background: none;
           color: var(--tv-text-2); border-radius: var(--tv-ecke); cursor: pointer; font-size: 16px; }
  .taste:hover, .taste.an { color: var(--tv-text); background: var(--tv-karte-2); }
  .taste.flaeche { width: 40px; height: 40px; background: var(--tv-karte-2); }
  .taste.flaeche:hover, .taste.flaeche.an { background: var(--tv-karte-3); }
  .anzahl { position: absolute; right: 2px; top: 2px; min-width: 16px; height: 16px; padding: 0 3px; border-radius: 8px;
            background: var(--tv-info); color: #0b1a22; font-size: 13px; line-height: 16px; font-weight: 700; }
  .feld { position: absolute; right: 0; top: calc(100% + 8px); z-index: 60; width: 400px; max-height: 70vh; overflow-y: auto;
          padding: var(--tv-a3); background: var(--tv-karte); border-radius: var(--tv-ecke); box-shadow: var(--tv-schatten); }
  .feld.oben { top: auto; bottom: calc(100% + 8px); }
</style>

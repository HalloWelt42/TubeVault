<!--
  Läuft gerade (Mobil). Die Adresse wählt die Ansicht:
    /m/jetzt                    großer Spieler, bei Hörbüchern deren Ansicht
    /m/jetzt?ansicht=liedtext   mitlaufender Liedtext
    /m/jetzt?ansicht=schlange   Warteschlange bzw. Teile des Hörbuchs
  Den Farbton des Covers legt diese Seite als --m-farbton für den Verlauf
  dahinter fest. Der Knopf Geräte öffnet "Abspielen auf" (Fernsteuerung).
-->
<script>
  import { untrack } from 'svelte';
  import { musicPlayer as player } from '../../lib/stores/musicPlayer.svelte.js';
  import { coverUrl } from '../../lib/utils/musicTrack.js';
  import { loadTint } from '../../lib/utils/coverTint.js';
  import { route, back } from '../router.js';
  import Spieler from './jetzt/Spieler.svelte';
  import Hoerbuch from './jetzt/Hoerbuch.svelte';
  import Liedtext from './jetzt/Liedtext.svelte';
  import Warteschlange from './jetzt/Warteschlange.svelte';
  import DeviceSheet from '../parts/DeviceSheet.svelte';
  import { remote } from '../../lib/stores/remote.svelte.js';

  let devicesOpen = $state(false);

  let ansicht = $derived($route.params.ansicht || 'spieler');
  let cover = $derived(player.current ? coverUrl(player.current) : null);
  let tint = $state(null);

  // Farbton zum Cover: nur das Bild wird verfolgt
  $effect(() => {
    const url = cover;
    untrack(() => {
      if (!url) { tint = null; return; }
      loadTint(url).then((color) => { if (cover === url) tint = color; });
    });
  });
</script>

<div class="jetzt" style:--m-farbton={tint}>
  {#if !player.current}
    <header class="kopf">
      <button class="m-rund" onclick={back} aria-label="Schließen"><i class="fa-solid fa-chevron-down"></i></button>
    </header>
    <div class="m-note"><i class="fa-solid fa-music"></i> Noch läuft nichts.</div>
  {:else if ansicht === 'liedtext'}
    <Liedtext />
  {:else if ansicht === 'schlange'}
    <Warteschlange />
  {:else if player.audiobook}
    <Hoerbuch extra={geraete} />
  {:else}
    <Spieler extra={geraete} />
  {/if}
</div>

{#snippet geraete()}
  <button class:an={!!remote.elsewhere} onclick={() => devicesOpen = true} aria-label="Geräte: abspielen auf ...">
    <i class="fa-solid fa-tower-broadcast"></i>Geräte</button>
{/snippet}

{#if devicesOpen}<DeviceSheet onClose={() => devicesOpen = false} />{/if}

<style>
  .jetzt { height: 100%; overflow: hidden; background: var(--m-bg); }
  .kopf { display: flex; align-items: center; height: calc(var(--m-safe-top) + 60px); padding: var(--m-safe-top) 16px 0; }
</style>

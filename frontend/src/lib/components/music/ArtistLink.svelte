<!--
  Name des Interpreten als Verweis: ein Klick öffnet unter Musik alle seine
  Titel, wie die Wahl im Bereich Interpreten. Klick und Eingabetaste gehen
  nicht weiter an die umgebende Zeile oder Kachel (die sonst abspielte).
-->
<script>
  import { navigate } from '../../router/router.js';

  let { track } = $props();

  function open(e) {
    e.stopPropagation();
    navigate('/music', { quelle: track.artist_source });
  }
</script>

{#if track.artist_source}
  <button class="interpret" onclick={open} onkeydown={(e) => e.stopPropagation()}
          title="Alle Titel von {track.artist}">{track.artist}</button>
{:else}{track.artist}{/if}

<style>
  .interpret { display: inline; max-width: 100%; padding: 0; border: 0; background: none; color: inherit; font: inherit;
               text-align: left; cursor: pointer; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; vertical-align: bottom; }
  .interpret:hover { color: var(--tv-akzent); text-decoration: underline; }
  .interpret:focus-visible { outline: 2px solid var(--tv-akzent); outline-offset: 2px; }
</style>

<!--
  Abschnitte des laufenden Titels (z.B. die Titelliste eines Mixes), in der
  Warteschlange direkt unter dem Titel eingefügt. Antippen springt hin; Weiter
  und Zurück gehen erst durch diese Abschnitte, dann zum nächsten Titel
  (lib/utils/segments.js). Genutzt am Rechner (NowPlaying) und am Handy.
-->
<script>
  import { musicPlayer as player } from '../../stores/musicPlayer.svelte.js';
  import { formatDuration } from '../../utils/format.js';
</script>

{#if player.segments.length}
  <div class="abschnitte" role="list" aria-label="Abschnitte des Titels">
    {#each player.segments as segment, i (segment.start)}
      <button class="abschnitt" class:jetzt={i === player.segmentIndex} class:vorbei={i < player.segmentIndex}
              role="listitem" onclick={() => player.seek(segment.start)} title="Hierhin springen">
        <span class="zahl nr">{#if i === player.segmentIndex}<i class="fa-solid fa-volume-high"></i>{:else}{i + 1}{/if}</span>
        <span class="titel">{segment.title || `Abschnitt ${i + 1}`}</span>
        <span class="zahl zeit">{formatDuration(Math.floor(segment.start))}</span>
      </button>
    {/each}
  </div>
{/if}

<style>
  .abschnitte { display: flex; flex-direction: column; margin: 2px 0 8px 22px; padding-left: 10px;
                background: linear-gradient(var(--tv-karte-3), var(--tv-karte-3)) left / 2px 100% no-repeat; }
  .abschnitt { display: grid; grid-template-columns: 30px minmax(0, 1fr) auto; gap: 8px; align-items: center; min-height: 44px;
               padding: 0 8px; border: 0; border-radius: var(--tv-ecke-klein); background: none; color: var(--tv-text-2);
               font: inherit; font-size: var(--tv-gr-klein); text-align: left; cursor: pointer; }
  .abschnitt:hover { background: var(--tv-karte-2); color: var(--tv-text); }
  .abschnitt.vorbei { color: var(--tv-text-3); }
  .abschnitt.jetzt { color: var(--tv-akzent); font-weight: 700; background: rgba(var(--tv-akzent-rgb), 0.08); }
  .nr { text-align: center; color: inherit; }
  .titel { min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .zeit { color: var(--tv-text-3); }
</style>

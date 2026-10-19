<!--
  Die Interpreten eines Titels als Verweise: die Angabe steht, wie sie im Tag
  steht ("50 Cent, Nate Dogg"), jeder Genannte ist für sich ein Verweis und
  öffnet unter Musik alle seine Titel, wie die Wahl im Bereich Interpreten
  (utils/trackArtists.js). Klick und Eingabetaste gehen nicht weiter an die
  umgebende Zeile oder Kachel (die sonst abspielte).
-->
<script>
  import { navigate } from '../../router/router.js';
  import { artistSegments } from '../../utils/trackArtists.js';

  let { track } = $props();

  let segments = $derived(artistSegments(track));

  function open(e, source) {
    e.preventDefault();
    e.stopPropagation();
    navigate('/music', { quelle: source });
  }
</script>

{#each segments as part, i (i)}{#if part.source}<a class="interpret" href="/music?quelle={encodeURIComponent(part.source)}"
  onclick={(e) => open(e, part.source)} onkeydown={(e) => e.stopPropagation()}
  title="Alle Titel von {part.text}">{part.text}</a>{:else}{part.text}{/if}{/each}

<style>
  .interpret { color: inherit; text-decoration: none; cursor: pointer; }
  .interpret:hover { color: var(--tv-akzent); text-decoration: underline; }
  .interpret:focus-visible { outline: 2px solid var(--tv-akzent); outline-offset: 2px; }
</style>

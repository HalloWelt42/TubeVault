<!--
  Gefundene Titel der eigenen Musiksammlung; ein Klick spielt den Titel
  (die übrigen Treffer folgen in der Warteschlange).
-->
<script>
  import { musicPlayer } from '../../stores/musicPlayer.svelte.js';
  import { coverUrl } from '../../utils/musicTrack.js';
  import { formatDuration } from '../../utils/format.js';
  import { MUSIC_FOUND } from '../../constants/searchChoices.js';
  import Marked from './Marked.svelte';

  let { items = [], terms = [], query = '' } = $props();

  function play(index) {
    musicPlayer.playTracks(items.map((hit) => hit.track), index, `Suche: ${query}`);
  }
</script>

<div class="liste">
  {#each items as hit, index (hit.track.id)}
    <button class="titel" class:laeuft={musicPlayer.current?.id === hit.track.id} onclick={() => play(index)} title="Abspielen">
      <img src={coverUrl(hit.track)} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
      <span class="text">
        <span class="name"><Marked text={hit.track.title} {terms} /></span>
        <span class="zeile"><Marked text={hit.track.artist} {terms} />{#if hit.track.album} · <Marked text={hit.track.album} {terms} />{/if}{#if hit.year} · <span class="zahl">{hit.year}</span>{/if}</span>
      </span>
      <span class="fund">{hit.found.map((place) => MUSIC_FOUND[place]).join(', ')}</span>
      <span class="zahl leise">{formatDuration(hit.track.duration || 0)}</span>
    </button>
  {/each}
</div>

<style>
  .liste { display: flex; flex-direction: column; gap: 4px; }
  .titel { display: grid; grid-template-columns: 48px minmax(0, 1fr) auto auto; gap: var(--tv-a3); align-items: center;
           padding: 6px var(--tv-a2); border: 0; border-radius: var(--tv-ecke); background: none; color: var(--tv-text);
           font: inherit; text-align: left; cursor: pointer; }
  .titel:hover { background: var(--tv-flaeche); }
  .titel.laeuft { background: rgba(var(--tv-akzent-rgb), 0.1); }
  img { width: 48px; height: 48px; object-fit: cover; border-radius: var(--tv-ecke-klein); background: var(--tv-mulde); }
  .text { min-width: 0; display: flex; flex-direction: column; }
  .name { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .zeile { font-size: var(--tv-gr-klein); color: var(--tv-text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .fund, .leise { font-size: var(--tv-gr-klein); color: var(--tv-text-3); }
</style>

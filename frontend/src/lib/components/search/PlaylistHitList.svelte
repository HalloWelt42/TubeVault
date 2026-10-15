<!--
  Gefundene eigene Playlists: Name und Beschreibung hervorgehoben, Zahl der Videos.
-->
<script>
  import { navigate } from '../../router/router.js';
  import Marked from './Marked.svelte';

  let { items = [], terms = [] } = $props();
</script>

<div class="liste">
  {#each items as playlist (playlist.id)}
    <button class="eintrag" onclick={() => navigate('/playlists', { open: playlist.id })} title="Playlist öffnen">
      <i class="fa-solid fa-list"></i>
      <span class="text">
        <span class="name"><Marked text={playlist.name} {terms} /></span>
        {#if playlist.description}<span class="beschreibung"><Marked text={playlist.description} {terms} /></span>{/if}
      </span>
      <span class="zahl leise">{playlist.video_count} Videos</span>
      {#if playlist.meaning}<span class="sinn" title="Inhaltlich verwandt"><i class="fa-solid fa-wand-magic-sparkles"></i></span>{/if}
    </button>
  {/each}
</div>

<style>
  .liste { display: flex; flex-direction: column; gap: 4px; }
  .eintrag { display: grid; grid-template-columns: 28px minmax(0, 1fr) auto auto; gap: var(--tv-a3); align-items: center;
             padding: var(--tv-a2) var(--tv-a3); border: 0; border-radius: var(--tv-ecke); background: var(--tv-flaeche);
             color: var(--tv-text); font: inherit; text-align: left; cursor: pointer; }
  .eintrag:hover { background: var(--tv-karte); }
  .eintrag > i { color: var(--tv-akzent); text-align: center; }
  .text { min-width: 0; display: flex; flex-direction: column; }
  .name { font-weight: 700; }
  .beschreibung { font-size: var(--tv-gr-klein); color: var(--tv-text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .leise { font-size: var(--tv-gr-klein); color: var(--tv-text-3); }
  .sinn { color: var(--tv-info); }
</style>

<!--
  Zur Liste: einen Titel in eine Wiedergabeliste der Musik legen. Suchfeld
  über den vorhandenen Listen; ein Klick legt ihn ans Ende, ein Hinweis sagt
  wohin (oder dass er schon drin steht). Rechner (ListButton über der
  Abspielleiste) und Handy (Blatt in "Läuft gerade") nutzen dieselbe Wahl.
-->
<script>
  import { onMount } from 'svelte';
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';
  import { emitMusicChange } from '../../utils/musicChanges.js';

  let { track, onDone = () => {} } = $props();

  let lists = $state(null);
  let query = $state('');

  let shown = $derived((lists || []).filter((list) =>
    list.name.toLocaleLowerCase('de').includes(query.trim().toLocaleLowerCase('de'))));

  onMount(async () => {
    try { lists = await api.musicPlaylists(); } catch (e) { toast.error(e.message); onDone(); }
  });

  async function choose(list) {
    try {
      const { added } = await api.musicAddToPlaylist(list.key.split(':')[1], [track.id]);
      if (added) {
        toast.success(`In "${list.name}" gelegt`);
        emitMusicChange({ reload: true, playlist: list.key });
      } else {
        toast.info(`Steht schon in "${list.name}"`);
      }
      onDone();
    } catch (e) { toast.error(e.message); }
  }

  const focus = (node) => { node.focus(); };
</script>

<div class="wahl">
  <input type="search" class="suche" bind:value={query} placeholder="Liste suchen" aria-label="Liste suchen"
         autocomplete="off" enterkeyhint="search" use:focus
         onkeydown={(e) => { if (e.key === 'Enter' && shown.length === 1) choose(shown[0]); }} />
  <div class="listen">
    {#each shown as list (list.key)}
      <button class="liste" onclick={() => choose(list)}>
        <i class="fa-solid fa-list-ul"></i><span class="name">{list.name}</span><span class="zahl">{list.count}</span></button>
    {:else}
      <p class="leer">{lists === null ? 'Lädt ...' : lists.length ? 'Keine passende Liste' : 'Noch keine Wiedergabeliste'}</p>
    {/each}
  </div>
</div>

<style>
  .wahl { display: flex; flex-direction: column; gap: var(--tv-a2); min-height: 0; }
  .suche { height: 40px; padding: 0 var(--tv-a3); border: 1px solid var(--tv-rand); border-radius: var(--tv-ecke);
           background: var(--tv-mulde); color: var(--tv-text); font: inherit; }
  .suche:focus { outline: 2px solid rgba(var(--tv-akzent-rgb), 0.5); outline-offset: 0; }
  .listen { display: flex; flex-direction: column; gap: 2px; min-height: 0; overflow-y: auto; }
  .liste { display: grid; grid-template-columns: 20px minmax(0, 1fr) auto; gap: var(--tv-a2); align-items: center;
           min-height: 44px; padding: 0 var(--tv-a2); border: 0; border-radius: var(--tv-ecke-klein); background: none;
           color: var(--tv-text); font: inherit; text-align: left; cursor: pointer; }
  .liste:hover, .liste:focus-visible { background: var(--tv-karte-3); }
  .liste i { color: var(--tv-text-3); }
  .name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .zahl { color: var(--tv-text-3); font-size: var(--tv-gr-klein); }
  .leer { margin: 0; padding: var(--tv-a3) var(--tv-a2); color: var(--tv-text-3); }
</style>

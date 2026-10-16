<!--
  Bereich "Ausgeblendet" der Musik (Rechner): ausgeschlossene Alben und
  ausgeblendete Titel der Sammlung. Zurückholen einzeln (Knopf je Zeile)
  oder mehrere (Haken setzen, dann "Zurückholen"). Was zurückkommt, steht
  sofort wieder in allen Listen und Mixen (utils/musicHiding.js).
-->
<script>
  import { onMount } from 'svelte';
  import { api } from '../../api/client.js';
  import { coverUrl } from '../../utils/musicTrack.js';
  import { formatDuration } from '../../utils/format.js';
  import { restoreHidden } from '../../utils/musicHiding.js';
  import { onMusicChange } from '../../utils/musicChanges.js';
  import { toast } from '../../stores/notifications.js';

  let area = $state(null);              // { tracks, albums }
  let chosenTracks = $state(new Set());
  let chosenAlbums = $state(new Set());

  let total = $derived(area ? area.tracks.length + area.albums.length : 0);
  let chosen = $derived(chosenTracks.size + chosenAlbums.size);

  async function load() {
    try {
      area = await api.musicHidden();
      // Was nicht mehr da ist, ist auch nicht mehr gewählt
      chosenTracks = new Set(area.tracks.map((t) => t.id).filter((id) => chosenTracks.has(id)));
      chosenAlbums = new Set(area.albums.map((a) => a.source).filter((s) => chosenAlbums.has(s)));
    } catch (e) { toast.error(e.message); }
  }

  const flip = (set, key) => { const next = new Set(set); if (!next.delete(key)) next.add(key); return next; };

  function chooseAll() {
    const all = chosen < total;
    chosenTracks = new Set(all ? area.tracks.map((t) => t.id) : []);
    chosenAlbums = new Set(all ? area.albums.map((a) => a.source) : []);
  }

  async function restore(tracks, albums) {
    try {
      const result = await restoreHidden({ tracks, albums });
      const count = result.tracks + result.albums;
      toast.success(count === 1 ? 'Zurückgeholt' : `${count} zurückgeholt`);
    } catch (e) { toast.error(e.message); }
  }

  onMount(() => {
    load();
    return onMusicChange((change) => { if (change.reload) load(); });
  });
</script>

{#if !area}
  <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt ...</div>
{:else if !total}
  <div class="tv-leer">Nichts ausgeblendet. Ausblenden geht im Menü eines Titels, ganze Alben schließt der Knopf im Album aus.</div>
{:else}
  <div class="leiste">
    <button class="tv-knopf klein" onclick={chooseAll}>
      <i class="fa-regular {chosen < total ? 'fa-square-check' : 'fa-square'}"></i> {chosen < total ? 'Alle wählen' : 'Keine wählen'}</button>
    <button class="tv-knopf haupt klein" disabled={!chosen} onclick={() => restore([...chosenTracks], [...chosenAlbums])}>
      <i class="fa-solid fa-rotate-left"></i> Zurückholen{#if chosen}<span class="zahl">&nbsp;({chosen})</span>{/if}</button>
    <span class="tv-schwach tv-klein">Zurückgeholtes steht sofort wieder in allen Listen und Mixen.</span>
  </div>

  {#if area.albums.length}
    <h2>Ausgeschlossene Alben <span class="zahl tv-schwach">{area.albums.length}</span></h2>
    <div class="liste">
      {#each area.albums as album (album.source)}
        <label class="zeile">
          <input type="checkbox" checked={chosenAlbums.has(album.source)} onchange={() => chosenAlbums = flip(chosenAlbums, album.source)} />
          <span class="bild"><i class="fa-solid fa-compact-disc"></i></span>
          <span class="text"><span class="t">{album.name}</span>
            <span class="tv-leise tv-klein">{album.subtitle || ''} · <span class="zahl">{album.count}</span> Titel</span></span>
          <button class="tv-knopf klein" onclick={(e) => { e.preventDefault(); restore([], [album.source]); }}>
            <i class="fa-solid fa-rotate-left"></i> Zurückholen</button>
        </label>
      {/each}
    </div>
  {/if}

  {#if area.tracks.length}
    <h2>Ausgeblendete Titel <span class="zahl tv-schwach">{area.tracks.length}</span></h2>
    <div class="liste">
      {#each area.tracks as track (track.id)}
        <label class="zeile">
          <input type="checkbox" checked={chosenTracks.has(track.id)} onchange={() => chosenTracks = flip(chosenTracks, track.id)} />
          <img class="bild" src={coverUrl(track)} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
          <span class="text"><span class="t">{track.title}</span>
            <span class="tv-leise tv-klein">{track.artist}{#if track.album}{' · '}{track.album}{/if}
              · <span class="zahl">{formatDuration(track.duration || 0)}</span></span></span>
          <button class="tv-knopf klein" onclick={(e) => { e.preventDefault(); restore([track.id], []); }}>
            <i class="fa-solid fa-rotate-left"></i> Zurückholen</button>
        </label>
      {/each}
    </div>
  {/if}
{/if}

<style>
  .leiste { display: flex; align-items: center; gap: var(--tv-a2); flex-wrap: wrap; margin-bottom: var(--tv-a4); }
  h2 { margin: var(--tv-a4) 0 var(--tv-a2); font-size: var(--tv-gr-titel); }
  .liste { display: flex; flex-direction: column; gap: 2px; }
  .zeile { display: grid; grid-template-columns: auto 48px minmax(0, 1fr) auto; gap: var(--tv-a3); align-items: center;
           padding: 6px var(--tv-a2); border-radius: var(--tv-ecke); cursor: pointer; }
  .zeile:hover { background: var(--tv-flaeche); }
  .bild { width: 48px; height: 48px; object-fit: cover; border-radius: var(--tv-ecke-klein); background: var(--tv-mulde);
          display: grid; place-items: center; color: var(--tv-text-3); font-size: 20px; }
  .text { min-width: 0; display: flex; flex-direction: column; }
  .text > span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .t { font-weight: 600; }
</style>

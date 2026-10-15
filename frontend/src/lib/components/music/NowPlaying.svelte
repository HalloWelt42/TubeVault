<!--
  Läuft gerade: Bild, Titel, Warteschlange (verschiebbar), mitlaufender
  Liedtext (Klick auf eine Zeile springt dorthin) und Angaben zum Titel.
-->
<script>
  import { api } from '../../api/client.js';
  import { musicPlayer as player } from '../../stores/musicPlayer.svelte.js';
  import { formatDuration } from '../../utils/format.js';
  import { parseLrc, lineAt } from '../../utils/lrc.js';
  import { scrollWithin } from '../../utils/scrollRoot.js';

  // schlange | liedtext | infos; Navigation kommt vom Router der jeweiligen Oberfläche
  let { view = 'schlange', onOpenArtist = null, onOpenVideo = null } = $props();

  let track = $derived(player.current);
  let lyrics = $state({ id: null, plain: '', synced: [], offset: 0 });
  let lyricsEl = $state(null);
  let dragFrom = $state(null);

  // Liedtext des laufenden Titels laden
  $effect(() => {
    const id = track?.id;
    if (!id || lyrics.id === id) return;
    lyrics = { id, plain: '', synced: [], offset: 0 };
    api.getLyrics(id).then((res) => {
      if (player.current?.id !== id) return;
      lyrics = { id, plain: res.plain || '', synced: parseLrc(res.synced), offset: res.offset || 0 };
    }).catch(() => {});
  });

  let activeLine = $derived(lineAt(lyrics.synced, player.time, lyrics.offset));
  $effect(() => {
    if (view !== 'liedtext' || activeLine < 0 || !lyricsEl) return;
    const line = lyricsEl.querySelector(`[data-zeile="${activeLine}"]`);
    if (line) scrollWithin(lyricsEl, line, 'center');
  });

  function drop(to) {
    if (dragFrom !== null) player.move(dragFrom, to);
    dragFrom = null;
  }
</script>

<div class="jetzt">
  {#if track}
    <div class="kopf">
      <img src={api.thumbnailUrl(track.id)} alt="" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
      <div class="titel">{track.title}</div>
      {#if onOpenArtist}
        <button class="interpret" onclick={() => onOpenArtist(track)}>{track.artist}</button>
      {:else}<div class="tv-leise">{track.artist}</div>{/if}
      {#if player.title}<div class="tv-schwach tv-klein">aus: {player.title}</div>{/if}
    </div>
    <div class="tv-reiter">
      <button class:aktiv={view === 'schlange'} onclick={() => view = 'schlange'}><i class="fa-solid fa-list-ol"></i> Als Nächstes</button>
      <button class:aktiv={view === 'liedtext'} onclick={() => view = 'liedtext'}><i class="fa-solid fa-align-left"></i> Liedtext</button>
      <button class:aktiv={view === 'infos'} onclick={() => view = 'infos'}><i class="fa-solid fa-circle-info"></i> Infos</button>
    </div>

    {#if view === 'schlange'}
      <div class="schlange">
        {#each player.queue as item, i (item.id + ':' + i)}
          {#if i >= player.index}
            <div class="eintrag" class:aktuell={i === player.index} role="listitem" draggable={i !== player.index}
                 ondragstart={() => dragFrom = i} ondragover={(e) => e.preventDefault()} ondrop={() => drop(i)}>
              <i class="fa-solid {i === player.index ? 'fa-volume-high' : 'fa-grip-vertical'} griff"></i>
              <button class="eintrag-text" onclick={() => player.jump(i)} title="Abspielen">
                <img src={api.thumbnailUrl(item.id)} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
                <span class="text"><span class="t">{item.title}</span><span class="tv-leise">{item.artist}</span></span>
              </button>
              <span class="zahl tv-leise">{formatDuration(item.duration || 0)}</span>
              {#if i !== player.index}
                <button class="weg" onclick={() => player.remove(i)} title="Aus der Warteschlange"><i class="fa-solid fa-xmark"></i></button>
              {/if}
            </div>
          {/if}
        {/each}
        {#if player.upcoming.length === 0}
          <div class="tv-leer tv-klein">Danach ist Schluss{player.repeat === 'all' ? ' - es geht von vorn los' : ''}.</div>
        {/if}
      </div>
    {:else if view === 'liedtext'}
      <div class="liedtext" bind:this={lyricsEl}>
        {#if lyrics.synced.length}
          {#each lyrics.synced as line, i}
            <button class="zeile" class:an={i === activeLine} class:vorbei={i < activeLine} data-zeile={i}
                    onclick={() => player.seek(line.time + lyrics.offset)}>{line.text || '♪'}</button>
          {/each}
        {:else if lyrics.plain}
          <pre>{lyrics.plain}</pre>
        {:else}
          <div class="tv-leer tv-klein">Kein Liedtext. Suchen und festlegen lässt er sich in der Videoansicht.</div>
        {/if}
      </div>
    {:else}
      <dl class="infos tv-klein">
        <dt>Interpret</dt><dd>{track.artist}</dd>
        {#if track.album}<dt>Album</dt><dd>{track.album}</dd>{/if}
        <dt>Kanal</dt><dd>{track.channel_name || '-'}</dd>
        <dt>Dauer</dt><dd class="zahl">{formatDuration(track.duration || 0)}</dd>
        <dt>Gehört</dt><dd class="zahl">{track.play_count || 0}x</dd>
      </dl>
      <div class="infos-tasten">
        <button class="tv-knopf klein" onclick={() => player.playSource(`similar:${track.id}`)}>
          <i class="fa-solid fa-wand-magic-sparkles"></i> Ähnliche Titel</button>
        {#if onOpenVideo}
          <button class="tv-knopf klein" onclick={() => { player.pause(); onOpenVideo(track); }}>
            <i class="fa-solid fa-display"></i> Als Video</button>
        {/if}
      </div>
    {/if}
  {:else}
    <div class="tv-leer"><i class="fa-solid fa-music"></i> Noch läuft nichts.</div>
  {/if}
</div>

<style>
  .jetzt { display: flex; flex-direction: column; min-height: 0; height: 100%; }
  .kopf { padding: var(--tv-a4); }
  .kopf img { width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: var(--tv-ecke); background: var(--tv-mulde); }
  .titel { margin-top: var(--tv-a3); font-weight: 700; font-size: 19px; }
  .interpret { padding: 0; border: 0; background: none; color: var(--tv-text-2); font: inherit; cursor: pointer; }
  .interpret:hover { color: var(--tv-akzent); text-decoration: underline; }
  .tv-reiter { padding: 0 var(--tv-a4); }
  .schlange, .liedtext { flex: 1; min-height: 0; overflow-y: auto; padding: var(--tv-a2) var(--tv-a3) var(--tv-a4); }
  .eintrag { display: grid; grid-template-columns: 18px minmax(0, 1fr) auto 28px; gap: var(--tv-a2); align-items: center;
             padding: 4px 6px; border-radius: var(--tv-ecke); font-size: var(--tv-gr-klein); }
  .eintrag:hover { background: var(--tv-flaeche); }
  .eintrag.aktuell { background: var(--tv-karte); }
  .eintrag.aktuell .t { color: var(--tv-akzent); }
  .griff { color: var(--tv-text-3); cursor: grab; }
  .eintrag.aktuell .griff { color: var(--tv-akzent); cursor: default; }
  .eintrag-text { display: flex; align-items: center; gap: var(--tv-a2); min-width: 0; padding: 0; border: 0; background: none;
                  color: var(--tv-text); font: inherit; text-align: left; cursor: pointer; }
  .eintrag-text img { width: 40px; height: 40px; flex: none; object-fit: cover; border-radius: var(--tv-ecke-klein); }
  .text { display: flex; flex-direction: column; min-width: 0; }
  .text > span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .t { font-weight: 600; }
  .weg { width: 28px; height: 28px; border: 0; background: none; color: var(--tv-text-3); cursor: pointer; border-radius: var(--tv-ecke-klein); }
  .weg:hover { color: var(--tv-gefahr); background: var(--tv-karte-2); }
  .zeile { display: block; width: 100%; padding: 6px 4px; border: 0; background: none; text-align: left; font: inherit;
           font-size: 18px; font-weight: 600; color: var(--tv-text-3); cursor: pointer; line-height: 1.35; }
  .zeile.vorbei { color: var(--tv-text-2); }
  .zeile.an { color: var(--tv-akzent); }
  .zeile:hover { color: var(--tv-text); }
  pre { white-space: pre-wrap; font: inherit; color: var(--tv-text-2); }
  .infos { display: grid; grid-template-columns: auto 1fr; gap: 6px var(--tv-a3); padding: var(--tv-a3) var(--tv-a4); }
  .infos dt { color: var(--tv-text-3); }
  .infos-tasten { display: flex; gap: var(--tv-a2); flex-wrap: wrap; padding: 0 var(--tv-a4); }
</style>

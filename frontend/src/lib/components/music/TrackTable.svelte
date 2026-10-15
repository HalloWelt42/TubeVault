<!--
  Titelliste der Musik: dicht, ein Klick spielt ab dieser Stelle (onPlay
  bekommt den Index), Herz und Menü je Zeile.
-->
<script>
  import { api } from '../../api/client.js';
  import { musicPlayer as player } from '../../stores/musicPlayer.svelte.js';
  import { formatDuration } from '../../utils/format.js';

  let { tracks = [], numbered = true, showPlays = false, onPlay = () => {}, onMenu = () => {}, onFavorite = () => {} } = $props();
</script>

<div class="liste">
  <div class="zeile kopfzeile" class:mit-zahl={showPlays}>
    <span class="nr">{numbered ? '#' : ''}</span><span></span><span>Titel</span><span>Interpret</span>
    {#if showPlays}<span>Gehört</span>{/if}<span>Dauer</span><span></span><span></span>
  </div>
  {#each tracks as track, i (track.id)}
    {@const current = player.current?.id === track.id}
    <div class="zeile" class:laeuft={current} class:mit-zahl={showPlays} role="button" tabindex="0"
         onclick={() => current ? player.toggle() : onPlay(i)} onkeydown={(e) => e.key === 'Enter' && onPlay(i)}
         oncontextmenu={(e) => onMenu(e, track)}>
      <span class="nr">
        {#if current && player.playing}<i class="fa-solid fa-volume-high"></i>
        {:else}<span class="ziffer">{numbered ? i + 1 : ''}</span><i class="fa-solid fa-play spielen"></i>{/if}
      </span>
      <img src={api.thumbnailUrl(track.id)} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
      <span class="t" title={track.title}>{track.title}</span>
      <span class="w" title={track.artist}>{track.artist}</span>
      {#if showPlays}<span class="zahl w">{track.play_count}x</span>{/if}
      <span class="zahl w">{formatDuration(track.duration || 0)}</span>
      <button class="knopf" class:an={track.favorite} onclick={(e) => { e.stopPropagation(); onFavorite(track); }}
              title="Lieblingssong"><i class="fa-{track.favorite ? 'solid' : 'regular'} fa-heart"></i></button>
      <button class="knopf" onclick={(e) => onMenu(e, track)} title="Mehr"><i class="fa-solid fa-ellipsis"></i></button>
    </div>
  {/each}
</div>

<style>
  .zeile { display: grid; grid-template-columns: 32px 48px minmax(0, 2fr) minmax(0, 1fr) 64px 34px 34px; gap: var(--tv-a3);
           align-items: center; padding: 6px var(--tv-a2); border-radius: var(--tv-ecke); cursor: pointer; }
  .zeile.mit-zahl { grid-template-columns: 32px 48px minmax(0, 2fr) minmax(0, 1fr) 70px 64px 34px 34px; }
  .zeile:hover { background: var(--tv-flaeche); }
  .zeile:focus-visible { outline: 2px solid var(--tv-akzent); }
  .zeile.laeuft .t, .zeile.laeuft .nr { color: var(--tv-akzent); }
  .kopfzeile { cursor: default; font-size: var(--tv-gr-marke); font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
               color: var(--tv-text-3); }
  .kopfzeile:hover { background: none; }
  .nr { text-align: right; color: var(--tv-text-3); font-family: var(--tv-schrift-zahl); }
  .nr .spielen { display: none; color: var(--tv-text); }
  .zeile:not(.kopfzeile):hover .nr .ziffer { display: none; }
  .zeile:not(.kopfzeile):hover .nr .spielen { display: inline; }
  img { width: 48px; height: 48px; object-fit: cover; border-radius: var(--tv-ecke-klein); background: var(--tv-mulde); }
  .t { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .w { font-size: var(--tv-gr-klein); color: var(--tv-text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .knopf { width: 34px; height: 34px; display: grid; place-items: center; border: 0; background: none; color: var(--tv-text-3);
           border-radius: var(--tv-ecke-klein); cursor: pointer; }
  .knopf:hover { color: var(--tv-text); background: var(--tv-karte-2); }
  .knopf.an { color: var(--tv-symbol-rot); }
  @media (max-width: 700px) {
    .zeile, .zeile.mit-zahl { grid-template-columns: 24px 44px minmax(0, 1fr) 34px 34px; }
    .zeile .w, .kopfzeile { display: none; }
  }
</style>

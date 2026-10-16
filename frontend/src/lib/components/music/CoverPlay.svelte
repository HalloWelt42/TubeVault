<!--
  Cover mit Abspieltaste (Listen-Baukasten, beide Seiten): Klick spielt den
  Titel (onplay) bzw. hält ihn an oder setzt fort, wenn er schon der laufende
  ist. Das Zeichen liegt mittig über dem ganzen Cover; es zeigt sich beim
  Überfahren und am laufenden Titel.
-->
<script>
  import { coverUrl } from '../../utils/musicTrack.js';
  import { musicPlayer as player } from '../../stores/musicPlayer.svelte.js';

  let { track, onplay } = $props();

  let current = $derived(player.current?.id === track.id);
  let running = $derived(current && player.playing);

  function click(e) {
    e.stopPropagation();
    if (current) player.toggle();
    else onplay();
  }
</script>

<button class="cover" class:laeuft={current} draggable="false" onclick={click} ondblclick={(e) => e.stopPropagation()}
        title={running ? 'Anhalten' : current ? 'Fortsetzen' : 'Abspielen'}>
  <img src={coverUrl(track)} alt="" loading="lazy" draggable="false" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
  <i class="fa-solid {running ? 'fa-pause' : 'fa-play'}"></i>
</button>

<style>
  .cover { position: relative; width: 40px; height: 40px; flex: none; padding: 0; border: 0; border-radius: var(--tv-ecke-klein);
           overflow: hidden; background: var(--tv-mulde); cursor: pointer; }
  .cover:focus-visible { outline: 2px solid var(--tv-akzent); outline-offset: 2px; }
  img { width: 100%; height: 100%; object-fit: cover; display: block; }
  /* Font Awesome 7 setzt eine feste Breite: ausdrücklich über das ganze Cover strecken, sonst steht das Zeichen links */
  i { position: absolute; inset: 0; width: 100%; height: 100%; display: grid; place-items: center;
      background: rgba(8, 13, 16, 0.55); color: var(--tv-text); font-size: 15px; opacity: 0; }
  .cover:hover i, .cover:focus-visible i, .cover.laeuft i { opacity: 1; }
  .cover.laeuft i { color: var(--tv-akzent); }
</style>

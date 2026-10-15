<!--
  Kachel eines Musiktitels: quadratisches Bild, ein Klick spielt sofort
  (onPlay), das Menü öffnet Weiteres. Der laufende Titel zeigt Pegelbalken.
-->
<script>
  import { api } from '../../api/client.js';
  import { musicPlayer as player } from '../../stores/musicPlayer.svelte.js';

  let { track, onPlay = () => {}, onMenu = () => {} } = $props();

  let current = $derived(player.current?.id === track.id);
</script>

<div class="song" class:laeuft={current} role="button" tabindex="0" title="{track.title} - Klick spielt sofort"
     onclick={() => current ? player.toggle() : onPlay()} onkeydown={(e) => e.key === 'Enter' && onPlay()}
     oncontextmenu={(e) => onMenu(e, track)}>
  <div class="cover">
    <img src={api.thumbnailUrl(track.id)} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
    {#if current && player.playing}<div class="wellen"><b></b><b></b><b></b><b></b></div>{/if}
    <button class="mehr" onclick={(e) => onMenu(e, track)} title="Mehr"><i class="fa-solid fa-ellipsis"></i></button>
    <span class="spielen"><i class="fa-solid {current && player.playing ? 'fa-pause' : 'fa-play'}"></i></span>
  </div>
  <div class="name">{track.title}</div>
  <div class="wer">{track.artist}</div>
</div>

<style>
  .song { position: relative; cursor: pointer; min-width: 0; }
  .song:focus-visible { outline: 2px solid var(--tv-akzent); outline-offset: 3px; }
  .cover { position: relative; aspect-ratio: 1; border-radius: var(--tv-ecke); overflow: hidden; background: var(--tv-mulde); }
  .cover img { width: 100%; height: 100%; object-fit: cover; display: block; transition: transform 0.25s; }
  .song:hover .cover img { transform: scale(1.04); }
  .spielen { position: absolute; right: 10px; bottom: 10px; width: 48px; height: 48px; display: grid; place-items: center;
             background: var(--tv-akzent); color: var(--tv-akzent-text); border-radius: var(--tv-ecke); font-size: 18px;
             opacity: 0; transform: translateY(6px); transition: opacity 0.15s, transform 0.15s; box-shadow: 0 6px 18px rgba(0, 0, 0, 0.45); }
  .song:hover .spielen, .song.laeuft .spielen { opacity: 1; transform: none; }
  .mehr { position: absolute; right: 8px; top: 8px; width: 34px; height: 34px; display: grid; place-items: center; border: 0;
          border-radius: var(--tv-ecke-klein); background: rgba(8, 13, 16, 0.7); color: var(--tv-text); opacity: 0; cursor: pointer; }
  .song:hover .mehr { opacity: 1; }
  .name { margin-top: 8px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .wer { font-size: var(--tv-gr-klein); color: var(--tv-text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .laeuft .name { color: var(--tv-akzent); }
  .wellen { position: absolute; left: 10px; bottom: 12px; display: flex; align-items: flex-end; gap: 3px; height: 18px; }
  .wellen b { width: 4px; background: var(--tv-akzent); animation: welle 0.9s ease-in-out infinite; }
  .wellen b:nth-child(2) { animation-delay: 0.2s; }
  .wellen b:nth-child(3) { animation-delay: 0.4s; }
  .wellen b:nth-child(4) { animation-delay: 0.1s; }
  @keyframes welle { 0%, 100% { height: 4px; } 50% { height: 18px; } }
  @media (hover: none) { .mehr { opacity: 1; } }
</style>

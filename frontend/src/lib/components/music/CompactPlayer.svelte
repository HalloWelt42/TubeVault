<!--
  Schlanke Musiksteuerung in der Fußleiste (Musikleiste eingeklappt, siehe
  stores/playerBar.svelte.js): kleines Bild, Titel, Zurück/Abspielen/Weiter,
  Stand als feine Linie, Aufklappen zur großen Leiste.
-->
<script>
  import { musicPlayer as player } from '../../stores/musicPlayer.svelte.js';
  import { playerBar } from '../../stores/playerBar.svelte.js';
  import { coverUrl } from '../../utils/musicTrack.js';
  import { formatDuration } from '../../utils/format.js';

  let track = $derived(player.current);
  let progress = $derived(player.duration ? Math.min(1, player.time / player.duration) : 0);
  let title = $derived(player.segment ? `${player.segment.title} · ${track?.title}` : track?.title);
</script>

{#if track}
  <span class="schlank" title="{title} - {track.artist}">
    <img src={coverUrl(track)} alt="" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
    <span class="text"><span class="t">{title}</span><span class="lauf"><b style:width="{progress * 100}%"></b></span></span>
    <span class="zahl zeit">{formatDuration(Math.floor(player.time))}</span>
    <button onclick={() => player.prev()} title="Zurück"><i class="fa-solid fa-backward-step"></i></button>
    <button class="haupt" onclick={() => player.toggle()} title={player.playing ? 'Pause' : 'Abspielen'}>
      <i class="fa-solid {player.loading ? 'fa-spinner fa-spin' : player.playing ? 'fa-pause' : 'fa-play'}"></i></button>
    <button onclick={() => player.next()} title="Weiter"><i class="fa-solid fa-forward-step"></i></button>
    <button onclick={() => playerBar.setCompact(false)} title="Große Musikleiste zeigen"><i class="fa-solid fa-chevron-up"></i></button>
  </span>
{/if}

<style>
  .schlank { display: inline-flex; align-items: center; gap: 4px; min-width: 0; max-width: 460px; }
  img { width: 26px; height: 26px; flex: none; object-fit: cover; border-radius: var(--tv-ecke-klein); background: var(--tv-mulde); }
  .text { min-width: 0; display: flex; flex-direction: column; gap: 3px; margin: 0 4px; }
  .t { font-size: var(--tv-gr-klein); color: var(--tv-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 240px; }
  .lauf { position: relative; height: 2px; background: var(--tv-karte-3); border-radius: 1px; }
  .lauf b { position: absolute; left: 0; top: 0; bottom: 0; background: var(--tv-akzent); border-radius: 1px; }
  .zeit { font-size: 13px; color: var(--tv-text-3); margin-right: 2px; }
  button { width: 28px; height: 28px; flex: none; display: grid; place-items: center; border: 0; border-radius: var(--tv-ecke);
           background: none; color: var(--tv-text-2); cursor: pointer; font-size: 13px; }
  button:hover { color: var(--tv-text); background: var(--tv-karte-2); }
  button.haupt { background: var(--tv-text); color: var(--tv-grund); border-radius: 50%; }
</style>

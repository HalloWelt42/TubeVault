<!--
  Läuft gerade (Mobil): große Steuerung oben, darunter Bild, Warteschlange,
  mitlaufender Liedtext und Infos - dieselbe Ansicht wie am Rechner.
-->
<script>
  import { musicPlayer as player } from '../../lib/stores/musicPlayer.svelte.js';
  import { formatDuration } from '../../lib/utils/format.js';
  import NowPlaying from '../../lib/components/music/NowPlaying.svelte';
  import { back, go } from '../router.js';

  let progress = $derived(player.duration ? player.time / player.duration : 0);

  function seek(e) {
    const box = e.currentTarget.getBoundingClientRect();
    player.seek(Math.max(0, Math.min(1, (e.clientX - box.left) / box.width)) * player.duration);
  }
</script>

<div class="jetzt m-view">
  <header class="top">
    <button class="zurueck" onclick={back} aria-label="Schließen"><i class="fa-solid fa-chevron-down"></i></button>
    <span class="m-h2">Läuft gerade</span>
  </header>

  {#if player.current}
    <div class="steuerung">
      <div class="spur" role="slider" tabindex="0" aria-label="Stelle im Titel" aria-valuenow={Math.round(player.time)}
           onpointerdown={seek}><b style:width="{progress * 100}%"></b></div>
      <div class="zeiten"><span>{formatDuration(Math.floor(player.time))}</span><span>{formatDuration(Math.floor(player.duration))}</span></div>
      <div class="tasten">
        <button class:an={player.shuffle} onclick={() => player.toggleShuffle()} aria-label="Zufall"><i class="fa-solid fa-shuffle"></i></button>
        <button onclick={() => player.prev()} aria-label="Zurück"><i class="fa-solid fa-backward-step"></i></button>
        <button class="gross" onclick={() => player.toggle()} aria-label={player.playing ? 'Pause' : 'Abspielen'}>
          <i class="fa-solid {player.playing ? 'fa-pause' : 'fa-play'}"></i></button>
        <button onclick={() => player.next()} aria-label="Weiter"><i class="fa-solid fa-forward-step"></i></button>
        <button class:an={player.repeat !== 'off'} onclick={() => player.cycleRepeat()} aria-label="Wiederholen">
          <i class="fa-solid fa-repeat"></i>{#if player.repeat === 'one'}<b>1</b>{/if}</button>
      </div>
    </div>
  {/if}

  <div class="rest"><NowPlaying onOpenVideo={(t) => go(`/video/${t.id}`)} /></div>
</div>

<style>
  .jetzt { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
  .top { display: flex; align-items: center; gap: 10px; padding: calc(var(--m-safe-top) + 8px) 12px 4px; }
  .zurueck { width: var(--m-touch); height: var(--m-touch); font-size: 1.3rem; }
  .steuerung { padding: 4px 18px 10px; }
  .spur { position: relative; height: 22px; touch-action: none; }
  .spur::before { content: ''; position: absolute; left: 0; right: 0; top: 9px; height: 4px; background: var(--m-line); border-radius: 2px; }
  .spur b { position: absolute; left: 0; top: 9px; height: 4px; background: var(--m-accent); border-radius: 2px; }
  .zeiten { display: flex; justify-content: space-between; font-family: var(--tv-schrift-zahl); font-size: 0.85rem; color: var(--m-dim); }
  .tasten { display: flex; justify-content: space-between; align-items: center; margin-top: 6px; }
  .tasten button { position: relative; width: 56px; height: 56px; display: grid; place-items: center; font-size: 1.35rem; color: var(--m-dim); }
  .tasten button.an { color: var(--m-accent); }
  .tasten button.gross { width: 72px; height: 72px; font-size: 1.7rem; background: var(--m-text); color: var(--m-bg); border-radius: var(--m-radius); }
  .tasten b { position: absolute; right: 10px; bottom: 10px; font-size: 0.75rem; }
  .rest { flex: 1; min-height: 0; overflow: hidden; }
</style>

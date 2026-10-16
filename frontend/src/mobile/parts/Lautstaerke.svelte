<!--
  Lautstärke des Musikspielers am Handy: leise links, laut rechts, dazwischen
  die Bahn. Ziehen oder Tippen stellt sofort. Steht nur da, wo die Seite die
  Lautstärke stellen kann (musicPlayer.volumeAdjustable; am iPhone über den
  Verstärker, lib/utils/softVolume.js).
-->
<script>
  import { musicPlayer as player } from '../../lib/stores/musicPlayer.svelte.js';

  const KEY_STEP = 0.05;

  let dragging = false;

  function fraction(e) {
    const box = e.currentTarget.getBoundingClientRect();
    return Math.max(0, Math.min(1, (e.clientX - box.left) / box.width));
  }

  function down(e) {
    e.currentTarget.setPointerCapture(e.pointerId);
    dragging = true;
    player.setVolume(fraction(e));
  }

  function move(e) {
    if (dragging) player.setVolume(fraction(e));
  }

  function key(e) {
    const step = { ArrowLeft: -KEY_STEP, ArrowDown: -KEY_STEP, ArrowRight: KEY_STEP, ArrowUp: KEY_STEP }[e.key];
    if (!step) return;
    e.preventDefault();
    player.setVolume(player.volume + step);
  }
</script>

<div class="laut">
  <i class="fa-solid {player.volume === 0 ? 'fa-volume-xmark' : 'fa-volume-low'}" aria-hidden="true"></i>
  <div class="regler" role="slider" tabindex="0" aria-label="Lautstärke" aria-valuemin="0" aria-valuemax="100"
       aria-valuenow={Math.round(player.volume * 100)}
       onpointerdown={down} onpointermove={move} onpointerup={() => dragging = false} onpointercancel={() => dragging = false}
       onkeydown={key}>
    <span class="bahn"><b style:width="{player.volume * 100}%"></b></span>
  </div>
  <i class="fa-solid fa-volume-high" aria-hidden="true"></i>
</div>

<style>
  .laut { display: grid; grid-template-columns: 24px minmax(0, 1fr) 24px; gap: 10px; align-items: center; flex: none;
          color: var(--m-faint); font-size: 15px; }
  .regler { height: 36px; display: flex; align-items: center; touch-action: none; cursor: pointer; }
  .bahn { position: relative; flex: 1; height: 4px; border-radius: 2px; background: rgba(255, 255, 255, 0.15); }
  .bahn b { position: absolute; left: 0; top: 0; bottom: 0; border-radius: inherit; background: var(--m-dim); }
  .bahn b::after { content: ''; position: absolute; right: -7px; top: -5px; width: 14px; height: 14px; border-radius: 50%;
                   background: var(--m-text); }
</style>

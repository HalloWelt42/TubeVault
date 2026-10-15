<!--
  Spur eines Titels am Handy: Stand mit Griff und darunter die Zeiten.
  Ziehen zeigt die Stelle schon an, gesprungen wird beim Loslassen (sonst
  lädt der Ton bei jedem Zucken neu). Die Berührfläche ist höher als die
  sichtbare Linie. "schmal": nur die Linie, ohne Griff und Zeiten.
-->
<script>
  import { formatDuration } from '../../lib/utils/format.js';

  const KEY_STEP_S = 5;

  // marks: Stellen von Abschnitten (Sekunden), als feine Striche auf der Bahn
  let { time = 0, duration = 0, onseek, mitte = null, schmal = false, marks = [] } = $props();

  let dragging = $state(null);   // Anteil 0..1 während des Ziehens
  let shown = $derived(dragging ?? (duration ? Math.min(1, Math.max(0, time / duration)) : 0));

  function fraction(e) {
    const box = e.currentTarget.getBoundingClientRect();
    return Math.max(0, Math.min(1, (e.clientX - box.left) / box.width));
  }

  function down(e) {
    if (!duration) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    dragging = fraction(e);
  }

  function move(e) {
    if (dragging !== null) dragging = fraction(e);
  }

  function up() {
    if (dragging === null) return;
    const value = dragging;
    dragging = null;
    onseek?.(value * duration);
  }

  function key(e) {
    const step = { ArrowLeft: -KEY_STEP_S, ArrowRight: KEY_STEP_S }[e.key];
    if (!step || !duration) return;
    e.preventDefault();
    onseek?.(Math.max(0, Math.min(duration, time + step)));
  }
</script>

<div class="spur" class:schmal class:zieht={dragging !== null} role="slider" tabindex="0" aria-label="Stelle im Titel"
     aria-valuemin="0" aria-valuemax={Math.round(duration)} aria-valuenow={Math.round(shown * duration)}
     onpointerdown={down} onpointermove={move} onpointerup={up} onpointercancel={() => dragging = null} onkeydown={key}>
  <span class="bahn"><b style:width="{shown * 100}%"></b>
    {#if duration}{#each marks.filter((mark) => mark < duration) as mark (mark)}<i class="marke" style:left="{(mark / duration) * 100}%"></i>{/each}{/if}</span>
</div>
{#if !schmal}
  <div class="zeiten">
    <span class="zahl">{formatDuration(Math.floor(shown * duration))}</span>
    {#if mitte}<span class="mitte">{mitte}</span>{/if}
    <span class="zahl">{formatDuration(Math.floor(duration))}</span>
  </div>
{/if}

<style>
  .spur { position: relative; height: 32px; display: flex; align-items: center; touch-action: none; cursor: pointer; flex: none; }
  .spur.schmal { height: 24px; align-items: flex-start; }
  .bahn { position: relative; flex: 1; height: 6px; border-radius: 3px; background: rgba(255, 255, 255, 0.15); }
  .schmal .bahn { height: 4px; border-radius: 2px; }
  .bahn b { position: absolute; left: 0; top: 0; bottom: 0; border-radius: inherit; background: var(--m-text); }
  .schmal .bahn b { background: var(--m-accent); }
  .spur:not(.schmal) .bahn b::after { content: ''; position: absolute; right: -8px; top: -5px; width: 16px; height: 16px;
                                       border-radius: 50%; background: var(--m-text); }
  .zieht .bahn b::after { transform: scale(1.25); }
  .marke { position: absolute; top: -3px; width: 2px; height: 12px; margin-left: -1px; border-radius: 1px;
           background: rgba(255, 255, 255, 0.55); pointer-events: none; }
  .zeiten { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; font-size: 14px; color: var(--m-faint); flex: none; }
  .mitte { font-size: 14px; font-weight: 600; }
</style>

<!--
  Drücken und Halten: für Aktionen mit Folgen (z.B. Download starten).
  Ein Ring füllt sich; erst wenn er voll ist, wird ausgelöst. Loslassen oder
  Wegziehen bricht ab - ein versehentliches Antippen bewirkt nichts.
-->
<script>
  let { icon = 'fa-download', label, holdMs = 650, onfire, disabled = false } = $props();

  let holding = $state(false);
  let timer = null;

  function start(e) {
    if (disabled) return;
    e.preventDefault();
    holding = true;
    timer = setTimeout(() => {
      holding = false;
      timer = null;
      navigator.vibrate?.(30);
      onfire?.();
    }, holdMs);
  }

  function cancel() {
    holding = false;
    clearTimeout(timer);
    timer = null;
  }
</script>

<button class="hold" class:holding {disabled} aria-label="{label} (gedrückt halten)"
        style="--hold-ms: {holdMs}ms"
        onpointerdown={start} onpointerup={cancel} onpointerleave={cancel} onpointercancel={cancel}
        oncontextmenu={(e) => e.preventDefault()}>
  <svg viewBox="0 0 48 48" aria-hidden="true">
    <circle class="track" cx="24" cy="24" r="21" />
    <circle class="fill" cx="24" cy="24" r="21" />
  </svg>
  <i class="fa-solid {icon}"></i>
</button>

<style>
  .hold {
    position: relative; width: 52px; height: 52px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    color: var(--m-accent); font-size: 1.05rem;
    touch-action: none; user-select: none; -webkit-user-select: none; -webkit-touch-callout: none;
  }
  .hold:disabled { color: var(--m-faint); }
  svg { position: absolute; inset: 2px; transform: rotate(-90deg); }
  circle { fill: none; stroke-width: 3; }
  .track { stroke: var(--m-line); }
  .fill {
    stroke: var(--m-accent); stroke-linecap: round;
    stroke-dasharray: 132; stroke-dashoffset: 132;
  }
  .holding .fill { stroke-dashoffset: 0; transition: stroke-dashoffset var(--hold-ms) linear; }
  .holding { background: var(--m-surface-2); }
</style>

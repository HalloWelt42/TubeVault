<!--
  TubeVault -  MiniProgress v1.8.60
  Kompakte Phasen-Leiste (4px) ohne Labels.
  Vorausgefüllte dunkle Phasenfarben + helle Füllung für Kontrast.
  © HalloWelt42 -  Private Nutzung
-->
<script>
  let { progress = 0, stage = '', phases = null, status = '' } = $props();

  const DEFAULT_PHASES = [
    { id: 'resolving',         start: 0.00, end: 0.08, color: '#90A4AE' },
    { id: 'downloading_video', start: 0.08, end: 0.58, color: '#4CAF50' },
    { id: 'downloading_audio', start: 0.58, end: 0.88, color: '#2196F3' },
    { id: 'merging',           start: 0.88, end: 0.92, color: '#FF9800' },
    { id: 'finalizing',        start: 0.92, end: 1.00, color: '#9C27B0' },
  ];

  let ph = $derived(phases?.length ? phases : DEFAULT_PHASES);

  function segFill(seg) {
    if (status === 'done' || stage === 'done') return 100;
    const map = { resolved: 'resolving', retry_wait: '' };
    const phaseId = map[stage] ?? stage;
    const idx = ph.findIndex(p => p.id === phaseId || phaseId.startsWith(p.id));
    const si = ph.indexOf(seg);
    if (si < idx) return 100;
    if (si > idx) return 0;
    const span = seg.end - seg.start;
    if (span <= 0) return 0;
    return Math.max(0, Math.min(100, ((progress - seg.start) / span) * 100));
  }
</script>

<div class="mp">
  {#each ph as seg (seg.id)}
    {@const w = (seg.end - seg.start) * 100}
    {@const fill = segFill(seg)}
    <div class="mp-seg" style="width:{w}%; --seg-color:{seg.color}">
      <div class="mp-fill" style="width:{fill}%"></div>
    </div>
  {/each}
</div>

<style>
  .mp {
    display: flex;
    height: 4px;
    border-radius: 2px;
    overflow: hidden;
    gap: 1px;
    flex: 0 1 120px;
    min-width: 30px;
    max-width: 120px;
    background: rgba(255,255,255,0.03);
  }
  .mp-seg {
    height: 100%;
    position: relative;
    overflow: hidden;
    /* Dunkle Grundfarbe: Phase-Farbe bei 20% */
    background: color-mix(in srgb, var(--seg-color) 20%, transparent);
  }
  .mp-seg:first-child { border-radius: 2px 0 0 2px; }
  .mp-seg:last-child  { border-radius: 0 2px 2px 0; }
  .mp-fill {
    position: absolute;
    top: 0; left: 0; bottom: 0;
    background: var(--seg-color);
    border-radius: inherit;
    transition: width 0.6s ease;
  }
</style>

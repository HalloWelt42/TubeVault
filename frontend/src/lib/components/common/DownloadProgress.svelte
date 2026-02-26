<!--
  TubeVault – DownloadProgress v1.8.60
  Mehrstufiger Fortschrittsbalken mit vorausgefüllten Phasen-Farben.
  Jedes Segment zeigt dunkle Grundfarbe + helle Füllfarbe für hohen Kontrast.
  © HalloWelt42 – Private Nutzung
-->
<script>
  /**
   * @type {{ progress: number, stage: string, stage_label: string, phases?: Array, status?: string }}
   */
  let { data = {} } = $props();

  // Fallback-Phasen wenn Backend noch keine schickt
  const DEFAULT_PHASES = [
    { id: 'resolving',         label: 'Auflösen',    start: 0.00, end: 0.08, color: '#90A4AE', status: 'pending' },
    { id: 'downloading_video', label: 'Video ↓',     start: 0.08, end: 0.58, color: '#4CAF50', status: 'pending' },
    { id: 'downloading_audio', label: 'Audio ↓',     start: 0.58, end: 0.88, color: '#2196F3', status: 'pending' },
    { id: 'merging',           label: 'Merge',        start: 0.88, end: 0.92, color: '#FF9800', status: 'pending' },
    { id: 'finalizing',        label: 'Abschluss',    start: 0.92, end: 1.00, color: '#9C27B0', status: 'pending' },
  ];

  let phases = $derived(data.phases?.length ? data.phases : inferPhases());
  let progress = $derived(data.progress ?? 0);
  let stageLabel = $derived(data.stage_label || '');

  function inferPhases() {
    const p = structuredClone(DEFAULT_PHASES);
    const stage = data.stage || '';
    const status = data.status || '';

    if (stage === 'done' || status === 'done') {
      p.forEach(ph => { ph.status = 'done'; });
      return p;
    }
    if (stage === 'error' || status === 'error') {
      const prog = data.progress ?? 0;
      p.forEach(ph => {
        if (prog >= ph.end) ph.status = 'done';
        else if (prog >= ph.start) ph.status = 'active';
        else ph.status = 'pending';
      });
      return p;
    }

    const map = { resolved: 'resolving', retry_wait: '' };
    const phaseId = map[stage] ?? stage;
    const idx = p.findIndex(ph => ph.id === phaseId || phaseId.startsWith(ph.id));
    p.forEach((ph, i) => {
      if (i < idx) ph.status = 'done';
      else if (i === idx) ph.status = 'active';
      else ph.status = 'pending';
    });
    return p;
  }

  function phaseProgress(phase) {
    if (phase.status === 'done') return 100;
    if (phase.status === 'pending') return 0;
    const span = phase.end - phase.start;
    if (span <= 0) return 0;
    const inner = Math.max(0, Math.min(1, (progress - phase.start) / span));
    return inner * 100;
  }

  function phaseWidth(phase) {
    return (phase.end - phase.start) * 100;
  }
</script>

<div class="dp-wrap">
  <!-- Mehrstufiger Balken: dunkle Grundfarbe + helle Füllung -->
  <div class="dp-bar">
    {#each phases as phase (phase.id)}
      {@const w = phaseWidth(phase)}
      {@const fill = phaseProgress(phase)}
      <div
        class="dp-segment"
        class:active={phase.status === 'active'}
        class:done={phase.status === 'done'}
        class:pending={phase.status === 'pending'}
        style="width:{w}%; --phase-color:{phase.color}"
        title="{phase.label}: {fill.toFixed(0)}%"
      >
        <div
          class="dp-fill"
          style="width:{fill}%"
        ></div>
      </div>
    {/each}
  </div>

  <!-- Phase-Labels -->
  <div class="dp-labels">
    {#each phases as phase (phase.id)}
      {@const w = phaseWidth(phase)}
      <span
        class="dp-label"
        class:is-active={phase.status === 'active'}
        class:is-done={phase.status === 'done'}
        style="width:{w}%; color:{phase.status === 'active' ? phase.color : ''}"
      >
        {#if phase.status === 'done'}
          <i class="fa-solid fa-check" style="font-size:0.55rem"></i>
        {:else if phase.status === 'active'}
          <span class="dp-pulse" style="background:{phase.color}"></span>
        {/if}
        {phase.label}
      </span>
    {/each}
  </div>

  <!-- Detail-Zeile -->
  {#if stageLabel}
    <div class="dp-detail">
      <span class="dp-detail-text">{stageLabel}</span>
      <span class="dp-pct">{(progress * 100).toFixed(1)}%</span>
    </div>
  {/if}
</div>

<style>
  .dp-wrap {
    padding: 4px 0 2px;
  }

  /* ─── Balken ─── */
  .dp-bar {
    display: flex;
    height: 10px;
    border-radius: 5px;
    overflow: hidden;
    gap: 1px;
    background: rgba(255,255,255,0.03);
  }

  .dp-segment {
    position: relative;
    height: 100%;
    overflow: hidden;
    /* Dunkle Grundfarbe: Phase-Farbe bei 18% Deckkraft → immer sichtbar */
    background: color-mix(in srgb, var(--phase-color) 18%, transparent);
  }
  .dp-segment:first-child { border-radius: 5px 0 0 5px; }
  .dp-segment:last-child  { border-radius: 0 5px 5px 0; }

  /* Helle Füllung: volle Phase-Farbe */
  .dp-fill {
    position: absolute;
    top: 0; left: 0; bottom: 0;
    background: var(--phase-color);
    border-radius: inherit;
    transition: width 0.6s ease;
  }

  .dp-segment.active .dp-fill {
    animation: dp-glow 1.5s ease-in-out infinite;
  }

  .dp-segment.done .dp-fill {
    width: 100% !important;
    opacity: 0.75;
  }

  @keyframes dp-glow {
    0%, 100% { filter: brightness(1); }
    50% { filter: brightness(1.4); }
  }

  /* ─── Labels ─── */
  .dp-labels {
    display: flex;
    margin-top: 3px;
    gap: 1px;
  }
  .dp-label {
    font-size: 0.6rem;
    text-align: center;
    color: var(--text-tertiary);
    white-space: nowrap;
    overflow: visible;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 2px;
    line-height: 1;
    padding: 1px 0;
  }
  .dp-label.is-active {
    font-weight: 600;
  }
  .dp-label.is-done {
    color: var(--text-tertiary);
    opacity: 0.6;
  }
  .dp-label.is-done i {
    color: var(--status-success);
  }

  .dp-pulse {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    display: inline-block;
    animation: dp-blink 1s ease-in-out infinite;
  }
  @keyframes dp-blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }

  /* ─── Detail-Zeile ─── */
  .dp-detail {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 2px;
    font-size: 0.65rem;
    line-height: 1.2;
  }
  .dp-detail-text {
    color: var(--text-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
    min-width: 0;
  }
  .dp-pct {
    color: var(--text-primary);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    margin-left: 8px;
    flex-shrink: 0;
  }
</style>

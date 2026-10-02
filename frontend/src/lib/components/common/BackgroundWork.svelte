<!--
  TubeVault – Laufende Hintergrundarbeiten
  Kleine Anzeige in der Statusleiste: was im Hintergrund läuft, wie weit es
  ist, seit wann und wie lange noch. Ein Klick klappt die Einzelheiten auf.
  Zeigt sich nur, solange etwas läuft.
-->
<script>
  import { api } from '../../api/client.js';
  import { parseServerTime } from '../../utils/format.js';

  const REFRESH_MS = 8000;

  let items = $state([]);
  let open = $state(false);
  let now = $state(Date.now());

  async function load() {
    try { items = (await api.getBackgroundWork()).items || []; } catch { /* Statusleiste bleibt still */ }
    now = Date.now();
    if (items.length === 0) open = false;
  }

  function percent(item) {
    return item.progress === null || item.progress === undefined ? null : Math.round(item.progress * 100);
  }

  function span(seconds) {
    if (seconds < 90) return `${Math.max(1, Math.round(seconds))} s`;
    if (seconds < 5400) return `${Math.round(seconds / 60)} Min`;
    return `${(seconds / 3600).toFixed(1).replace('.', ',')} Std`;
  }

  function runningFor(item) {
    if (!item.since) return null;
    const started = parseServerTime(item.since).getTime();
    return Number.isNaN(started) ? null : span((now - started) / 1000);
  }

  function summary(item) {
    const p = percent(item);
    return p === null ? item.label : `${item.label} ${p} %`;
  }

  $effect(() => {
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => clearInterval(timer);
  });
</script>

{#if items.length > 0}
  <div class="bg-work">
    <button class="chip" class:open onclick={() => open = !open}
            title="Laufende Hintergrundarbeiten anzeigen">
      <i class="fa-solid fa-gear fa-spin"></i>
      <span class="chip-text">{items.length === 1 ? summary(items[0]) : `${items.length} Hintergrundarbeiten`}</span>
    </button>
    {#if open}
      <div class="panel" role="status">
        {#each items as item (item.key)}
          <div class="row">
            <div class="row-head">
              <span class="row-label">{item.label}</span>
              {#if percent(item) !== null}<span class="row-pct">{percent(item)} %</span>{/if}
            </div>
            {#if percent(item) !== null}
              <div class="track"><span style="width: {percent(item)}%"></span></div>
            {/if}
            <div class="row-meta">
              {#if item.total}<span>{item.done.toLocaleString('de-DE')} von {item.total.toLocaleString('de-DE')}</span>{/if}
              {#if runningFor(item)}<span>läuft seit {runningFor(item)}</span>{/if}
              {#if item.eta_seconds}<span>noch etwa {span(item.eta_seconds)}</span>{/if}
              {#if item.waiting > 0}<span>{item.waiting} weitere warten</span>{/if}
            </div>
            {#if item.detail}<div class="row-detail">{item.detail}</div>{/if}
          </div>
        {/each}
      </div>
    {/if}
  </div>
{/if}

<style>
  .bg-work { position: relative; display: flex; align-items: center; }
  .chip {
    display: flex; align-items: center; gap: 6px; max-width: 320px;
    padding: 2px 10px; border: none; border-radius: 999px; cursor: pointer;
    background: var(--accent-muted); color: var(--accent-primary);
    font: inherit; font-weight: 600; white-space: nowrap;
  }
  .chip.open, .chip:hover { background: var(--accent-primary); color: #fff; }
  .chip-text { overflow: hidden; text-overflow: ellipsis; }
  .panel {
    position: absolute; right: 0; bottom: calc(100% + 10px); z-index: 60; width: 360px;
    padding: 14px; display: flex; flex-direction: column; gap: 14px;
    background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 12px;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
    font-size: 0.8rem; color: var(--text-secondary); white-space: normal;
  }
  .row-head { display: flex; justify-content: space-between; gap: 10px; }
  .row-label { color: var(--text-primary); font-weight: 600; }
  .row-pct { color: var(--accent-primary); font-weight: 600; font-variant-numeric: tabular-nums; }
  .track { margin: 7px 0 6px; height: 5px; background: var(--bg-tertiary); border-radius: 3px; overflow: hidden; }
  .track span { display: block; height: 100%; background: var(--accent-primary); transition: width 0.5s; }
  .row-meta { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 0.74rem; color: var(--text-tertiary); }
  .row-detail { margin-top: 4px; font-size: 0.74rem; }
</style>

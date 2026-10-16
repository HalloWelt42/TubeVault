<!--
  TubeVault – Laufende Hintergrundarbeiten
  Kleine Anzeige in der Statusleiste: was im Hintergrund läuft, wie weit es
  ist, seit wann und wie lange noch. Ein Klick klappt die Einzelheiten auf.
  Zeigt sich nur, solange etwas läuft. Arbeiten mit Schalter (switch_key)
  lassen sich direkt hier anhalten und fortsetzen.
-->
<script>
  import { onMount } from 'svelte';
  import { parseServerTime, formatClock } from '../../utils/format.js';
  import { toast } from '../../stores/notifications.js';
  import { workPercent as percent } from '../../utils/backgroundWork.js';
  import { backgroundWork } from '../../stores/backgroundWork.svelte.js';


  let items = $derived(backgroundWork.items || []);
  let open = $state(false);
  let now = $state(Date.now());
  let switching = $state(null);   // key der Arbeit, deren Schalter gerade umgelegt wird
  let allPaused = $derived(items.length > 0 && items.every(i => i.paused));

  // Laufzeiten mitzählen; ohne Arbeiten klappt die Anzeige zu
  $effect(() => {
    backgroundWork.items;
    now = Date.now();
  });
  $effect(() => { if (items.length === 0) open = false; });

  function runningFor(item) {
    if (!item.since) return null;
    const started = parseServerTime(item.since).getTime();
    return Number.isNaN(started) ? null : formatClock((now - started) / 1000);
  }

  function summary(item) {
    const p = percent(item);
    return p === null ? item.label : `${item.label} ${p} %`;
  }

  async function toggle(item) {
    switching = item.key;
    try {
      await backgroundWork.toggle(item);
    } catch (e) { toast.error(e.message); }
    switching = null;
  }

  onMount(() => backgroundWork.use());
</script>

{#if items.length > 0}
  <div class="bg-work">
    <button class="chip" class:open onclick={() => open = !open}
            title="Laufende Hintergrundarbeiten anzeigen">
      <i class="fa-solid {allPaused ? 'fa-pause' : 'fa-gear fa-spin'}"></i>
      <span class="chip-text">{items.length === 1 ? summary(items[0]) : `${items.length} Hintergrundarbeiten`}</span>
    </button>
    {#if open}
      <div class="panel" role="status">
        {#each items as item (item.key)}
          <div class="row">
            <div class="row-head">
              <span class="row-label">{item.label}</span>
              {#if percent(item) !== null}<span class="row-pct">{percent(item)} %</span>{/if}
              {#if item.switch_key}
                <button class="tv-knopf klein" class:haupt={item.paused} onclick={() => toggle(item)}
                        disabled={switching === item.key}>
                  <i class="fa-solid {switching === item.key ? 'fa-spinner fa-spin' : item.paused ? 'fa-play' : 'fa-pause'}"></i>
                  {item.paused ? 'Fortsetzen' : 'Anhalten'}</button>
              {/if}
            </div>
            {#if percent(item) !== null}
              <div class="track"><span style="width: {percent(item)}%"></span></div>
            {/if}
            <div class="row-meta">
              {#if item.total}<span class="zahl">{item.done.toLocaleString('de-DE')} von {item.total.toLocaleString('de-DE')} erledigt</span>{/if}
              {#if runningFor(item) && !item.paused}<span>läuft seit <span class="zahl">{runningFor(item)}</span></span>{/if}
              {#if item.eta_seconds}<span title="Tage:Stunden:Minuten:Sekunden">noch etwa <span class="zahl">{formatClock(item.eta_seconds)}</span></span>{/if}
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
    padding: 2px 10px; border: none; border-radius: var(--tv-ecke); cursor: pointer;
    background: var(--accent-muted); color: var(--accent-primary);
    font: inherit; font-weight: 600; white-space: nowrap;
  }
  .chip.open, .chip:hover { background: var(--accent-primary); color: var(--accent-text); }
  .chip-text { overflow: hidden; text-overflow: ellipsis; }
  .panel {
    position: absolute; right: 0; bottom: calc(100% + 10px); z-index: 60; width: 360px;
    padding: 14px; display: flex; flex-direction: column; gap: 14px;
    background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: var(--tv-ecke);
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
    font-size: 0.8rem; color: var(--text-secondary); white-space: normal;
  }
  .row-head { display: flex; align-items: center; gap: 10px; }
  .row-label { flex: 1; color: var(--text-primary); font-weight: 600; }
  .row-pct { color: var(--accent-primary); font-weight: 600; font-variant-numeric: tabular-nums; }
  .track { margin: 7px 0 6px; height: 5px; background: var(--bg-tertiary); border-radius: 1px; overflow: hidden; }
  .track span { display: block; height: 100%; background: var(--accent-primary); transition: width 0.5s; }
  .row-meta { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 0.74rem; color: var(--text-tertiary); }
  .row-detail { margin-top: 4px; font-size: 0.74rem; }
</style>

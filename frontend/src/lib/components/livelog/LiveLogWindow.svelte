<!--
  TubeVault - Live-Log (Entwurf mockups/werkzeuge.html, Freigabe 16.10.2026)
  Schwebendes Fenster: Verbindung in Worten, Anhalten, Reiter (Alle, Server,
  Abfragen, Browser, Aufträge), Fehlerzahl als Filter, Suche (auch als
  Muster), Stufe ab Info (Details auf Wunsch), Speichern, Leeren,
  Mitrollen. Verschieben und Größe ändern nur innerhalb des Fensters.
  Daten: stores/liveLog.svelte.js; Meldungen des Browsers: utils/frontendLog.js.
-->
<script>
  import { untrack } from 'svelte';
  import { liveLog } from '../../stores/liveLog.svelte.js';
  import LogLines from './LogLines.svelte';
  import LogJobs from './LogJobs.svelte';
  import { TABS, THRESHOLDS, exportText, filterEntries, isError, levelOf } from './logView.js';

  let { visible = $bindable(false) } = $props();

  const MIN_W = 560;
  const MIN_H = 300;
  const MARGIN = 8;

  let tab = $state('alle');
  let threshold = $state(1);
  let query = $state('');
  let pattern = $state(false);
  let follow = $state(true);
  let minimized = $state(false);
  let jobSummary = $state(null);
  let frame = $state({ x: 300, y: 90, w: 980, h: 560 });
  let lines = $state(null);

  let jobsTab = $derived(tab === 'auftraege');
  let shown = $derived(filterEntries(liveLog.entries, { tab, threshold, query, pattern }));
  let errors = $derived(liveLog.entries.filter(isError).length);
  let warnings = $derived(liveLog.entries.filter((entry) => levelOf(entry.level).rank === 2).length);

  // Öffnen verbindet (und rückt das Fenster in den sichtbaren Bereich), Schließen trennt
  $effect(() => {
    if (!visible) { liveLog.close(); return; }
    liveLog.open();
    untrack(() => { frame = clamp(frame); });
  });

  /** Fenster immer ganz im sichtbaren Bereich halten. */
  function clamp({ x, y, w, h }) {
    const width = Math.max(MIN_W, Math.min(w, window.innerWidth - 2 * MARGIN));
    const height = Math.max(MIN_H, Math.min(h, window.innerHeight - 2 * MARGIN));
    return {
      w: width, h: height,
      x: Math.max(MARGIN, Math.min(x, window.innerWidth - width - MARGIN)),
      y: Math.max(MARGIN, Math.min(y, window.innerHeight - 48 - MARGIN)),
    };
  }

  /** Ziehen am Kopf bzw. am Griff unten rechts (Zeiger, auch Berührung). */
  function drag(event, resize) {
    if (event.button !== 0 || event.target.closest('button, input, select')) return;
    event.preventDefault();
    const start = { px: event.clientX, py: event.clientY, ...frame };
    const move = (e) => {
      const dx = e.clientX - start.px;
      const dy = e.clientY - start.py;
      frame = clamp(resize ? { ...start, w: start.w + dx, h: start.h + dy } : { ...start, x: start.x + dx, y: start.y + dy });
    };
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  }

  function onlyErrors() {
    threshold = threshold === 3 ? 1 : 3;
    if (jobsTab) tab = 'alle';
  }

  function save() {
    const blob = new Blob([exportText(shown)], { type: 'text/plain' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `tubevault-live-log-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.txt`;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  function followNow() {
    follow = true;
    lines?.toEnd();
  }
</script>

<svelte:window onresize={() => (frame = clamp(frame))} />

{#if visible}
  <section class="fenster" style:left="{frame.x}px" style:top="{frame.y}px" style:width="{frame.w}px"
           style:height={minimized ? 'auto' : `${frame.h}px`} aria-label="Live-Log">
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="kopf" onpointerdown={(e) => drag(e, false)}>
      <span class="titel"><i class="fa-solid fa-terminal"></i> Live-Log</span>
      <span class="verbindung" class:aus={!liveLog.connected}
            title={liveLog.connected ? 'Mit dem Server verbunden; nach einem Neustart verbindet es sich selbst neu' : 'Verbindung getrennt, es wird neu verbunden'}>
        <b></b> {liveLog.connected ? 'verbunden' : 'getrennt'}</span>
      <div class="rechts">
        <button class="tv-knopf ohne klein" class:aktiv={liveLog.paused} onclick={() => liveLog.togglePause()}
                title={liveLog.paused ? 'Gesammelte Meldungen zeigen und weiterlaufen' : 'Neue Meldungen sammeln statt anzeigen'}>
          <i class="fa-solid {liveLog.paused ? 'fa-play' : 'fa-pause'}"></i>
          {#if liveLog.paused}Fortsetzen <span class="zahl">({liveLog.held})</span>{:else}Anhalten{/if}</button>
        <button class="tv-knopf ohne symbol klein" onclick={() => (minimized = !minimized)} title={minimized ? 'Aufklappen' : 'Verkleinern'}
                aria-label={minimized ? 'Aufklappen' : 'Verkleinern'}><i class="fa-solid {minimized ? 'fa-window-maximize' : 'fa-window-minimize'}"></i></button>
        <button class="tv-knopf ohne symbol klein" onclick={() => (visible = false)} title="Schließen" aria-label="Schließen">
          <i class="fa-solid fa-xmark"></i></button>
      </div>
    </div>

    {#if !minimized}
      <div class="leiste">
        <div class="tv-reiter reiter">
          {#each TABS as item (item.id)}
            <button class:aktiv={tab === item.id} onclick={() => (tab = item.id)}>
              <i class="fa-solid {item.icon}"></i> {item.label}
              {#if item.jobs && jobSummary?.active}<span class="tv-zaehler akzent">{jobSummary.active}</span>{/if}</button>
          {/each}
        </div>
        {#if !jobsTab}
          <div class="werkzeuge">
            {#if errors}
              <button class="fehlerchip" class:an={threshold === 3} onclick={onlyErrors} title={threshold === 3 ? 'Wieder alles ab Info zeigen' : 'Nur Fehler zeigen'}>
                <i class="fa-solid fa-circle-xmark"></i> <span class="zahl">{errors}</span> Fehler</button>
            {/if}
            <span class="suche">
              <input class="tv-eingabe" placeholder="In Meldungen suchen" bind:value={query} aria-label="In Meldungen suchen" />
              <button class="tv-knopf ohne klein muster" class:aktiv={pattern} onclick={() => (pattern = !pattern)}
                      title="Als Muster suchen (regulärer Ausdruck, z. B. GET .*feed)">Muster</button>
            </span>
            <select class="tv-eingabe stufe" bind:value={threshold} aria-label="Ab welcher Stufe"
                    title="Details sind vor allem die laufenden Abfragen der Oberfläche">
              {#each THRESHOLDS as option (option.value)}<option value={option.value}>{option.label}</option>{/each}
            </select>
            <button class="tv-knopf ohne symbol klein" onclick={save} title="Gezeigte Meldungen als Textdatei speichern" aria-label="Speichern">
              <i class="fa-solid fa-file-export"></i></button>
            <button class="tv-knopf ohne symbol klein" onclick={() => liveLog.clear()} title="Anzeige leeren (der Server behält alles)" aria-label="Anzeige leeren">
              <i class="fa-solid fa-eraser"></i></button>
          </div>
        {/if}
      </div>

      {#if jobsTab}
        <LogJobs onsummary={(summary) => (jobSummary = summary)} />
      {:else}
        <LogLines bind:this={lines} entries={shown} bind:follow connected={liveLog.connected} />
      {/if}

      <div class="fuss">
        {#if jobsTab}
          <span>{#if jobSummary}<span class="zahl">{jobSummary.active}</span> laufen, <span class="zahl">{jobSummary.queued}</span> warten{/if}</span>
        {:else}
          <span><span class="zahl">{shown.length.toLocaleString('de-DE')}</span> Meldungen
            {#if errors || warnings}, davon <span class="zahl">{errors}</span> Fehler und <span class="zahl">{warnings}</span> Warnungen{/if}</span>
          <button class="tv-knopf ohne klein mitrollen" class:aktiv={follow} onclick={followNow}
                  title="Neue Meldungen ans Ende rollen; beim Hochrollen aus, unten wieder an">
            <i class="fa-solid fa-arrows-down-to-line"></i> {follow ? 'Mitrollen an' : 'Zum Ende'}</button>
        {/if}
      </div>
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <div class="griff" onpointerdown={(e) => drag(e, true)} title="Größe ändern"></div>
    {/if}
  </section>
{/if}

<style>
  .fenster { position: fixed; z-index: 900; display: flex; flex-direction: column; overflow: hidden;
             background: var(--tv-leiste); border: 1px solid var(--tv-rand-stark); border-radius: var(--tv-ecke); box-shadow: var(--tv-schatten); }
  .kopf { display: flex; align-items: center; gap: var(--tv-a3); height: 48px; flex: none; padding: 0 var(--tv-a2) 0 var(--tv-a4);
          background: var(--tv-flaeche); cursor: move; touch-action: none; user-select: none; }
  .titel { font-weight: 700; display: flex; align-items: center; gap: var(--tv-a2); }
  .titel i { color: var(--tv-akzent); }
  .verbindung { display: inline-flex; align-items: center; gap: 6px; height: 26px; padding: 0 8px; border-radius: var(--tv-ecke-klein);
                font-size: var(--tv-gr-marke); font-weight: 700; color: var(--tv-erfolg); background: rgba(var(--tv-erfolg-rgb), 0.12); }
  .verbindung.aus { color: var(--tv-gefahr); background: rgba(var(--tv-gefahr-rgb), 0.12); }
  .verbindung b { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
  .kopf .rechts { margin-left: auto; display: flex; gap: 2px; }
  .leiste { display: flex; align-items: center; gap: var(--tv-a2); flex-wrap: wrap; flex: none; padding: var(--tv-a2) var(--tv-a3);
            border-bottom: 1px solid var(--tv-rand); }
  .reiter button { height: 34px; padding: 0 var(--tv-a3); }
  .werkzeuge { margin-left: auto; display: flex; flex-wrap: wrap; align-items: center; gap: var(--tv-a2); }
  .werkzeuge .tv-eingabe { height: 34px; }
  .suche { display: inline-flex; align-items: center; gap: 2px; }
  .suche .tv-eingabe { width: 220px; }
  .muster { font-size: var(--tv-gr-marke); }
  .stufe { width: 150px; }
  .fehlerchip { display: inline-flex; align-items: center; gap: 6px; height: 30px; padding: 0 10px; border: 0; border-radius: var(--tv-ecke-klein);
                background: rgba(var(--tv-gefahr-rgb), 0.14); color: var(--tv-gefahr); font: inherit; font-size: var(--tv-gr-marke); font-weight: 700; cursor: pointer; }
  .fehlerchip.an { background: var(--tv-gefahr); color: var(--tv-text); }
  .fuss { display: flex; align-items: center; gap: var(--tv-a4); height: 40px; flex: none; padding: 0 var(--tv-a5) 0 var(--tv-a4);
          border-top: 1px solid var(--tv-rand); font-size: var(--tv-gr-klein); color: var(--tv-text-2); }
  .mitrollen { margin-left: auto; }
  .griff { position: absolute; right: 0; bottom: 0; width: 18px; height: 18px; cursor: nwse-resize; touch-action: none;
           background: linear-gradient(135deg, transparent 50%, var(--tv-rand-stark) 50%); }

  @media (max-width: 700px) {
    .suche .tv-eingabe { width: 150px; }
    .werkzeuge { margin-left: 0; }
  }
</style>

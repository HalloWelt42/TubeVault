<!--
  Meldungen im Live-Log (Entwurf mockups/werkzeuge.html): Zeit, Bereich als
  Wort, Stufe als Zeichen und Zeilenfarbe, die ganze Meldung (bricht um),
  Verlauf (Traceback) zum Aufklappen, Tageswechsel als Trenner.
  Mitrollen: neue Meldungen rollen ans Ende; wer hochrollt, schaltet es
  aus, wer wieder unten ankommt, wieder an.
-->
<script>
  import { tick } from 'svelte';
  import { areaOf, levelOf } from './logView.js';

  let { entries, follow = $bindable(true), connected = true } = $props();

  const BOTTOM_PX = 40;
  let box = $state(null);
  let open = $state(new Set());

  function toggle(key) {
    const next = new Set(open);
    next.has(key) ? next.delete(key) : next.add(key);
    open = next;
  }

  const dayLabel = (entry) => new Date(entry.epoch * 1000).toLocaleDateString('de-DE',
    { weekday: 'long', day: '2-digit', month: '2-digit', year: 'numeric' });
  const fullDate = (entry) => (entry.epoch ? new Date(entry.epoch * 1000).toLocaleString('de-DE') : entry.ts);

  function onScroll() {
    const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < BOTTOM_PX;
    if (atBottom !== follow) follow = atBottom;
  }

  /** Ans Ende rollen (Knopf "Mitrollen" und neue Meldungen). */
  export async function toEnd() {
    await tick();
    if (box) box.scrollTop = box.scrollHeight;
  }

  $effect(() => {
    entries;
    if (follow) toEnd();
  });
</script>

<div class="zeilen" bind:this={box} onscroll={onScroll}>
  {#each entries as entry, i (entry.key)}
    {@const level = levelOf(entry.level)}
    {@const area = areaOf(entry.cat)}
    {#if i === 0 || entry.day !== entries[i - 1].day}
      <div class="tag">{dayLabel(entry)}</div>
    {/if}
    <div class="zeile {level.cls}">
      <span class="zeit zahl" title={fullDate(entry)}>{entry.ts}</span>
      <span class="bereich" style:--farbe={area.color} title={entry.cat}>{area.label}</span>
      <span class="stufe" title={level.label}>{#if level.icon}<i class="fa-solid {level.icon}"></i>{/if}</span>
      <span class="text">
        {#if entry.name}<span class="quelle">{entry.name}</span>{/if}{entry.msg}
        {#if entry.trace}
          <button class="verlauf" onclick={() => toggle(entry.key)} aria-expanded={open.has(entry.key)}>
            {open.has(entry.key) ? 'Verlauf zu' : 'Verlauf auf'}</button>
        {/if}
      </span>
    </div>
    {#if entry.trace && open.has(entry.key)}<pre class="trace">{entry.trace}</pre>{/if}
  {:else}
    <div class="leer">
      {#if connected}Noch keine Meldungen in dieser Ansicht.
      {:else}<i class="fa-solid fa-plug-circle-xmark"></i> Keine Verbindung zum Server, es wird neu verbunden ...{/if}
    </div>
  {/each}
</div>

<style>
  .zeilen { flex: 1; min-height: 0; overflow-y: auto; padding: var(--tv-a1) 0; font-size: var(--tv-gr-klein); }
  .zeile { display: grid; grid-template-columns: 76px 112px 22px minmax(0, 1fr); gap: var(--tv-a3); align-items: baseline;
           padding: 5px var(--tv-a4); }
  .zeile:hover { background: var(--tv-flaeche); }
  .zeit { color: var(--tv-text-3); }
  .bereich { font-size: var(--tv-gr-marke); font-weight: 700; color: var(--farbe); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .stufe { text-align: center; }
  .text { color: var(--tv-text); overflow-wrap: anywhere; min-width: 0; }
  .quelle { color: var(--tv-text-3); margin-right: 6px; }
  .detail .text { color: var(--tv-text-3); }
  .warnung { background: rgba(var(--tv-warnung-rgb), 0.06); }
  .warnung .stufe { color: var(--tv-warnung); }
  .fehler { background: rgba(var(--tv-gefahr-rgb), 0.08); }
  .fehler .stufe { color: var(--tv-gefahr); }
  .verlauf { margin-left: 8px; padding: 0; border: 0; background: none; color: var(--tv-akzent); font: inherit;
             font-size: var(--tv-gr-marke); font-weight: 700; cursor: pointer; }
  .trace { margin: 0 var(--tv-a4) var(--tv-a2) calc(76px + 112px + 22px + 3 * var(--tv-a3) + var(--tv-a4)); padding: var(--tv-a2) var(--tv-a3);
           background: var(--tv-mulde); border-radius: var(--tv-ecke-klein); color: var(--tv-text-2);
           font: 14px/1.45 ui-monospace, Menlo, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
  .tag { margin: var(--tv-a2) var(--tv-a4); text-align: center; font-size: var(--tv-gr-marke); font-weight: 700; letter-spacing: 0.08em;
         text-transform: uppercase; color: var(--tv-text-3); }
  .leer { padding: var(--tv-a6) var(--tv-a4); text-align: center; color: var(--tv-text-3); }
  .leer i { color: var(--tv-gefahr); }

  @media (max-width: 700px) {
    .zeile { grid-template-columns: 68px 22px minmax(0, 1fr); }
    .bereich { display: none; }
    .trace { margin-left: var(--tv-a4); }
  }
</style>

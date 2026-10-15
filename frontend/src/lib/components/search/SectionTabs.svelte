<!--
  Bereiche der Suche mit Zahl der Treffer: Alles und jeder Bereich, der
  etwas gefunden hat (Videos ist immer da), rechts "Bei der Quelle suchen".
-->
<script>
  import { SECTIONS, SOURCE_SECTION } from '../../constants/searchChoices.js';

  /** sections: Overview.sections (Bereich -> { total, more }); active: Bereich oder null (Alles) */
  let { sections = {}, active = null, onchoose } = $props();

  let shown = $derived(SECTIONS.filter((s) => s.id === 'videos' || sections[s.id]?.total || s.id === active));
  const count = (id) => sections[id]?.total || 0;
</script>

<div class="bereiche" role="tablist">
  <button role="tab" aria-selected={!active} class:aktiv={!active} onclick={() => onchoose(null)}>
    <i class="fa-solid fa-layer-group"></i> Alles</button>
  {#each shown as section (section.id)}
    <button role="tab" aria-selected={active === section.id} class:aktiv={active === section.id}
            onclick={() => onchoose(section.id)} title={section.hint}>
      <i class="fa-solid {section.icon}"></i> {section.label}
      <span class="tv-zaehler">{count(section.id).toLocaleString('de-DE')}{sections[section.id]?.more ? '+' : ''}</span>
    </button>
  {/each}
  <button role="tab" aria-selected={active === SOURCE_SECTION.id} class="quelle" class:aktiv={active === SOURCE_SECTION.id}
          onclick={() => onchoose(SOURCE_SECTION.id)} title={SOURCE_SECTION.hint}>
    <i class="fa-solid {SOURCE_SECTION.icon}"></i> Bei der Quelle suchen</button>
</div>

<style>
  .bereiche { display: flex; gap: var(--tv-a1); flex-wrap: wrap; margin-top: var(--tv-a3); }
  button { display: inline-flex; align-items: center; gap: 8px; height: 40px; padding: 0 var(--tv-a3); border: 1px solid transparent;
           border-radius: var(--tv-ecke); background: none; color: var(--tv-text-2); font: inherit; font-weight: 600;
           font-size: var(--tv-gr-klein); cursor: pointer; }
  button:hover { background: var(--tv-flaeche); color: var(--tv-text); }
  button.aktiv { background: var(--tv-flaeche); border-color: var(--tv-rand-stark); color: var(--tv-text); }
  button.aktiv i { color: var(--tv-akzent); }
  .quelle { margin-left: auto; color: var(--tv-akzent); }
</style>

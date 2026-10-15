<!--
  TubeVault - Sprachfilter als Chips (Suche, Kanäle): "Alle" und je Sprache
  Flagge, Name und Zähler, Mehrfachauswahl. Erscheint erst, wenn es etwas
  zu wählen gibt (mindestens zwei Sprachen oder eine Auswahl).
  counts: [{ code, count }] vom Backend, passend zu den übrigen Filtern.
-->
<script>
  import { languageCatalog, languageChoices, loadLanguages } from '../../utils/language.js';

  let { counts = [], selected = [], onchange } = $props();

  loadLanguages();
  const choices = $derived(languageChoices($languageCatalog, counts, selected));

  function toggle(code) {
    onchange(selected.includes(code) ? selected.filter((c) => c !== code) : [...selected, code]);
  }
</script>

{#if choices.length > 1 || selected.length > 0}
  <div class="sprachen" role="group" aria-label="Nach Sprache filtern">
    <span class="tv-etikett">Sprache</span>
    <button class="tv-chip" class:aktiv={selected.length === 0} onclick={() => onchange([])}>Alle</button>
    {#each choices as lang (lang.code)}
      <button class="tv-chip" class:aktiv={selected.includes(lang.code)} onclick={() => toggle(lang.code)}>
        {#if lang.flag}<span class="flagge" aria-hidden="true">{lang.flag}</span>{/if}
        {lang.name}
        <span class="tv-zaehler">{lang.count.toLocaleString('de-DE')}</span>
      </button>
    {/each}
  </div>
{/if}

<style>
  .sprachen { display: flex; align-items: center; gap: var(--tv-a2); flex-wrap: wrap; }
  .flagge { font-size: 15px; line-height: 1; }
</style>

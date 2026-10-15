<!--
  Filter der Suche: Sprachen (mit Zählern), Länge, Zeitraum, Ort, Stand,
  rechts Ordnung und Sinngemäß (Genauigkeit der Bedeutungssuche). Jede Wahl
  öffnet ein Menü an der Klickstelle; gewählte Filter sind hervorgehoben.
  Angaben im Suchtext (länge:>20 ...) gehen vor - die Suche meldet sie in
  effective zurück, dann steht hier, was wirkt.
-->
<script>
  import { settings } from '../../stores/settings.js';
  import { LENGTHS, LOCATIONS, ORDERS, PERIODS, PRECISIONS, STATES, choiceLabel } from '../../constants/searchChoices.js';
  import ActionMenu from '../common/ActionMenu.svelte';
  import LanguageChips from '../common/LanguageChips.svelte';

  /** filters: searchState-Filter; effective: wirksame Filter vom Backend (SearchFilters) */
  let { filters, effective = null, languageCounts = [], onchange } = $props();

  let menu;
  let meaningAvailable = $derived($settings['ai.enabled'] === 'true');
  let defaultPrecision = $derived($settings['ai.precision'] || 'ausgewogen');

  // Angaben aus dem Suchtext, die ein Feld der Seite überdecken
  let fromText = $derived({
    laenge: effective && (effective.min_seconds != null || effective.max_seconds != null),
    zeitraum: effective && (effective.year_from != null || effective.year_to != null),
    ort: effective && effective.location && effective.location !== filters.ort,
  });

  const DEFS = [
    { key: 'laenge', label: 'Länge', list: LENGTHS, none: 'alle' },
    { key: 'zeitraum', label: 'Zeitraum', list: PERIODS, none: 'jederzeit' },
    { key: 'ort', label: 'Ort', list: LOCATIONS, none: 'alle' },
    { key: 'stand', label: 'Stand', list: STATES, none: 'alle' },
  ];

  function set(key, value) {
    onchange({ ...filters, [key]: value });
  }

  function open(event, def) {
    menu.open(event, def.label, [
      { icon: filters[def.key] ? undefined : 'fa-check', label: def.none.charAt(0).toUpperCase() + def.none.slice(1), run: () => set(def.key, null) },
      ...def.list.map((choice) => ({ icon: filters[def.key] === choice.id ? 'fa-check' : undefined, label: choice.label,
                                     hint: choice.hint, run: () => set(def.key, choice.id) })),
    ]);
  }

  function openOrder(event) {
    menu.open(event, 'Ordnung', ORDERS.map((choice) => ({
      icon: filters.ordnung === choice.id ? 'fa-check' : undefined, label: choice.label, run: () => set('ordnung', choice.id) })));
  }

  function openPrecision(event) {
    const current = filters.genau || defaultPrecision;
    menu.open(event, 'Sinngemäß', PRECISIONS.map((choice) => ({
      icon: current === choice.id ? 'fa-check' : undefined, label: choice.label, hint: choice.hint,
      run: () => set('genau', choice.id === defaultPrecision ? null : choice.id) })));
  }

  function shown(def) {
    if (fromText[def.key]) return 'aus dem Suchtext';
    return choiceLabel(def.list, filters[def.key]) || def.none;
  }
</script>

<div class="filter">
  <LanguageChips counts={languageCounts} selected={filters.sprache} onchange={(list) => set('sprache', list)} />
  <div class="wahlen">
    {#each DEFS as def (def.key)}
      <button class="wahl" class:an={filters[def.key] || fromText[def.key]} onclick={(e) => open(e, def)}>
        {def.label} <b>{shown(def)}</b> <i class="fa-solid fa-chevron-down"></i></button>
    {/each}
    <span class="rechts">
      <button class="wahl" class:an={filters.ordnung !== 'passend'} onclick={openOrder}>
        Ordnung <b>{choiceLabel(ORDERS, filters.ordnung)}</b> <i class="fa-solid fa-chevron-down"></i></button>
      {#if meaningAvailable}
        <button class="wahl" class:an={!!filters.genau} onclick={openPrecision} title="Findet auch Verwandtes ohne das Wort">
          Sinngemäß <b>{choiceLabel(PRECISIONS, filters.genau || defaultPrecision)}</b> <i class="fa-solid fa-chevron-down"></i></button>
      {/if}
    </span>
  </div>
</div>

<ActionMenu bind:this={menu} />

<style>
  .filter { display: flex; flex-direction: column; gap: var(--tv-a2); margin-top: var(--tv-a2); }
  .wahlen { display: flex; flex-wrap: wrap; align-items: center; gap: var(--tv-a2); }
  .rechts { margin-left: auto; display: flex; gap: var(--tv-a2); }
  .wahl { display: inline-flex; align-items: center; gap: 7px; height: 34px; padding: 0 10px; border: 0; border-radius: var(--tv-ecke);
          background: var(--tv-karte); color: var(--tv-text-2); font: inherit; font-size: var(--tv-gr-klein); white-space: nowrap; cursor: pointer; }
  .wahl b { color: var(--tv-text); font-weight: 600; }
  .wahl i { font-size: 11px; }
  .wahl:hover { background: var(--tv-karte-2); }
  .wahl.an { background: rgba(var(--tv-akzent-rgb), 0.12); color: var(--tv-akzent); }
  .wahl.an b { color: var(--tv-akzent); }
</style>

<!--
  TubeVault – MultiFilter v1.5.52
  Wiederverwendbare Filter-Leiste: Typ, Kanal, Kategorie, Tags (Mehrfachauswahl)
  © HalloWelt42 – Private Nutzung
-->
<script>
  import { onMount } from 'svelte';
  import { api } from '../../api/client.js';
  import { settings } from '../../stores/settings.js';

  // Props
  let {
    showTypes = true,
    showChannels = true,
    showCategories = false,
    showTags = false,
    showSearch = false,
    showDuration = false,
    showMusic = false,
    feedTab = 'active',
    // Startauswahl im Format von onchange ({ types, channels, categories,
    // keywords, search, is_music }). Damit zeigt die Leiste von Anfang an
    // genau das, was die Seite filtert (z.B. gespeicherte Auswahl, Verweis).
    initial = null,
    onchange = () => {},
  } = $props();

  const fromList = (v) => (v ? String(v).split(',').filter(Boolean) : []);

  // Selektionen
  let selectedTypes = $state(fromList(initial?.types));
  let selectedChannels = $state(fromList(initial?.channels));
  let selectedCategories = $state(fromList(initial?.categories));
  let selectedTags = $state(fromList(initial?.keywords));
  let selectedDurations = $state([]);
  let musicOnly = $state(!!initial?.is_music);
  let extraAudioOnly = $state(!!initial?.extra_audio);
  let customDurMin = $state('');
  let customDurMax = $state('');
  let customDurActive = $state(false);
  let searchText = $state(initial?.search || '');
  let searchTimer = null;

  // Dropdown-Daten
  let channels = $state([]);
  let categories = $state([]);
  let tags = $state([]);

  // Dropdown-Visibility
  let showChannelDD = $state(false);
  let showCategoryDD = $state(false);
  let showTagDD = $state(false);

  // Suchfelder in Dropdowns
  let channelSearch = $state('');
  let categorySearch = $state('');
  let tagSearch = $state('');

  // Sind Shorts global ausgeschlossen, gibt es dafür auch keinen Filter
  const visibleTypes = $derived(
    VIDEO_TYPES.filter(t => t.id !== 'short' || $settings['shorts.exclude'] !== 'true')
  );

  const VIDEO_TYPES = [
    { id: 'video', label: 'Videos', icon: 'fa-solid fa-play' },
    { id: 'short', label: 'Shorts', icon: 'fa-solid fa-bolt' },
    { id: 'live', label: 'Live', icon: 'fa-solid fa-tower-broadcast' },
  ];

  const DURATION_RANGES = [
    { id: '0-60', label: '< 1 Min', min: 0, max: 60 },
    { id: '60-300', label: '1–5 Min', min: 60, max: 300 },
    { id: '300-1200', label: '5–20 Min', min: 300, max: 1200 },
    { id: '1200-3600', label: '20–60 Min', min: 1200, max: 3600 },
    { id: '3600-0', label: '> 1 Std', min: 3600, max: 0 },
  ];

  // Einmalig laden - KEIN $effect (verhindert Reset bei Parent-Rerender).
  // onMount bleibt synchron, sonst ginge die Abmeldung des Klick-Lauschers verloren
  onMount(() => {
    document.addEventListener('click', onClickOutside);
    loadChoices();
    return () => document.removeEventListener('click', onClickOutside);
  });

  async function loadChoices() {
    if (showChannels) {
      try {
        // Im Feed-Modus: Kanäle aus Subscriptions/RSS, sonst aus Videos
        if (showTags) {
          channels = await api.getFeedChannels(feedTab) || [];
        } else {
          channels = await api.getVideoChannels() || [];
        }
      } catch { channels = []; }
    }
    if (showCategories) {
      try { categories = await api.getCategoriesFlat() || []; } catch { categories = []; }
    }
    if (showTags) {
      try { tags = await api.getFeedTags(feedTab) || []; } catch { tags = []; }
    }
  }

  // Tags neu laden (von aussen aufrufbar)
  export async function reloadTags(tab) {
    if (showTags) {
      try { tags = await api.getFeedTags(tab || feedTab) || []; } catch { tags = []; }
    }
  }

  function emitChange() {
    let durationMin = null;
    let durationMax = null;

    if (customDurActive) {
      // Custom-Werte in Minuten → Sekunden
      if (customDurMin !== '' && !isNaN(customDurMin)) durationMin = Number(customDurMin) * 60;
      if (customDurMax !== '' && !isNaN(customDurMax)) durationMax = Number(customDurMax) * 60;
    } else if (selectedDurations.length > 0) {
      const ranges = selectedDurations.map(id => DURATION_RANGES.find(r => r.id === id)).filter(Boolean);
      durationMin = Math.min(...ranges.map(r => r.min));
      durationMax = Math.max(...ranges.map(r => r.max));
      if (ranges.some(r => r.max === 0)) durationMax = null;
    }

    onchange({
      types: selectedTypes.length > 0 ? selectedTypes.join(',') : null,
      channels: selectedChannels.length > 0 ? selectedChannels.join(',') : null,
      categories: selectedCategories.length > 0 ? selectedCategories.join(',') : null,
      keywords: selectedTags.length > 0 ? selectedTags.join(',') : null,
      search: searchText.trim() || null,
      durationMin,
      durationMax,
      is_music: musicOnly || null,
      extra_audio: extraAudioOnly || null,
    });
  }

  function toggleType(id) {
    selectedTypes = selectedTypes.includes(id)
      ? selectedTypes.filter(t => t !== id)
      : [...selectedTypes, id];
    emitChange();
  }

  function toggleChannel(chId) {
    selectedChannels = selectedChannels.includes(chId)
      ? selectedChannels.filter(c => c !== chId)
      : [...selectedChannels, chId];
    emitChange();
  }

  function toggleCategory(catId) {
    selectedCategories = selectedCategories.includes(catId)
      ? selectedCategories.filter(c => c !== catId)
      : [...selectedCategories, catId];
    emitChange();
  }

  function toggleTag(tag) {
    selectedTags = selectedTags.includes(tag)
      ? selectedTags.filter(t => t !== tag)
      : [...selectedTags, tag];
    emitChange();
  }

  function toggleDuration(id) {
    customDurActive = false;
    selectedDurations = selectedDurations.includes(id)
      ? selectedDurations.filter(d => d !== id)
      : [...selectedDurations, id];
    emitChange();
  }

  function applyCustomDuration() {
    if (customDurMin === '' && customDurMax === '') {
      customDurActive = false;
    } else {
      customDurActive = true;
      selectedDurations = [];
    }
    emitChange();
  }

  function clearCustomDuration() {
    customDurMin = '';
    customDurMax = '';
    customDurActive = false;
    emitChange();
  }

  function clearAll() {
    selectedTypes = [];
    selectedChannels = [];
    selectedCategories = [];
    selectedTags = [];
    selectedDurations = [];
    customDurMin = '';
    customDurMax = '';
    customDurActive = false;
    musicOnly = false;
    extraAudioOnly = false;
    searchText = '';
    channelSearch = '';
    categorySearch = '';
    tagSearch = '';
    emitChange();
  }

  function onSearchInput(val) {
    searchText = val;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => emitChange(), 300);
  }

  function closeAllDropdowns() {
    showChannelDD = false;
    showCategoryDD = false;
    showTagDD = false;
  }

  function onClickOutside(e) {
    if (showChannelDD && !e.target.closest('.filter-dropdown-wrap.channel')) showChannelDD = false;
    if (showCategoryDD && !e.target.closest('.filter-dropdown-wrap.category')) showCategoryDD = false;
    if (showTagDD && !e.target.closest('.filter-dropdown-wrap.tag')) showTagDD = false;
  }

  let hasActive = $derived(
    selectedTypes.length > 0 || selectedChannels.length > 0 ||
    selectedCategories.length > 0 || selectedTags.length > 0 ||
    selectedDurations.length > 0 || customDurActive || searchText.trim().length > 0 ||
    musicOnly || extraAudioOnly
  );

  let filteredChannels = $derived(
    channelSearch
      ? channels.filter(c => (c.channel_name || c.channel_id).toLowerCase().includes(channelSearch.toLowerCase()))
      : channels
  );

  let filteredCategories = $derived(
    categorySearch
      ? categories.filter(c => c.name.toLowerCase().includes(categorySearch.toLowerCase()))
      : categories
  );

  // Tags: Suche durchsucht ALLE Tags, ohne Suche Top 50
  let filteredTags = $derived(
    tagSearch
      ? tags.filter(t => t.tag.toLowerCase().includes(tagSearch.toLowerCase()))
      : tags.slice(0, 50)
  );

  export function reset() { clearAll(); }
</script>

<div class="multi-filter">
  {#if showSearch}
    <div class="filter-search">
      <i class="fa-solid fa-magnifying-glass search-icon"></i>
      <input type="text" placeholder="Suchen…" value={searchText}
             oninput={(e) => onSearchInput(e.target.value)} />
      {#if searchText}
        <button class="search-clear" onclick={() => { searchText = ''; emitChange(); }}>
          <i class="fa-solid fa-xmark"></i>
        </button>
      {/if}
    </div>
  {/if}

  <!-- Typ-Chips -->
  {#if showTypes}
    <div class="filter-group">
      <span class="filter-label">Art</span>
      <div class="chip-row">
        {#each visibleTypes as vt}
          <button class="filter-chip" class:active={selectedTypes.includes(vt.id)}
                  onclick={() => toggleType(vt.id)}>
            <i class={vt.icon}></i> {vt.label}
          </button>
        {/each}
        {#if showMusic}
          <button class="filter-chip music-chip" class:active={musicOnly}
                  onclick={() => { musicOnly = !musicOnly; emitChange(); }}>
            <i class="fa-solid fa-music"></i> Musik
          </button>
          <button class="filter-chip music-chip" class:active={extraAudioOnly}
                  title="Nur Videos mit zusätzlicher Tonspur (nachvertont)"
                  onclick={() => { extraAudioOnly = !extraAudioOnly; emitChange(); }}>
            <i class="fa-solid fa-language"></i> Nachvertont
          </button>
        {/if}
      </div>
    </div>
  {/if}

  <!-- Dauer-Chips + Custom -->
  {#if showDuration}
    <div class="filter-group dur-group">
      <span class="filter-label">Dauer</span>
      <div class="chip-row">
        {#each DURATION_RANGES as dr}
          <button class="filter-chip" class:active={!customDurActive && selectedDurations.includes(dr.id)}
                  onclick={() => toggleDuration(dr.id)}>
            <i class="fa-solid fa-clock"></i> {dr.label}
          </button>
        {/each}
      </div>
      <div class="dur-custom" class:active={customDurActive}>
        <input type="number" class="dur-input" placeholder="von" min="0"
               bind:value={customDurMin}
               onchange={applyCustomDuration} title="Min. Dauer (Minuten)" />
        <span class="dur-sep">-</span>
        <input type="number" class="dur-input" placeholder="bis" min="0"
               bind:value={customDurMax}
               onchange={applyCustomDuration} title="Max. Dauer (Minuten)" />
        <span class="dur-unit">Min</span>
        {#if customDurActive}
          <button class="dur-clear" onclick={clearCustomDuration} title="Custom löschen">
            <i class="fa-solid fa-xmark"></i>
          </button>
        {/if}
      </div>
    </div>
  {/if}

  <!-- Kanal-Dropdown -->
  {#if showChannels && channels.length > 0}
    <div class="filter-group">
      <span class="filter-label">Kanal</span>
      <div class="filter-dropdown-wrap channel">
        <button class="dropdown-trigger" onclick={(e) => { e.stopPropagation(); showChannelDD = !showChannelDD; showCategoryDD = false; showTagDD = false; }}>
          {selectedChannels.length === 0 ? 'Alle Kanäle' : `${selectedChannels.length} ausgewählt`}
          <i class="fa-solid fa-chevron-down dd-arrow" class:open={showChannelDD}></i>
        </button>
        {#if showChannelDD}
          <div class="dropdown-panel" onclick={(e) => e.stopPropagation()}>
            {#if channels.length > 6}
              <input class="dd-search" type="text" placeholder="Kanal suchen…"
                     value={channelSearch} oninput={(e) => channelSearch = e.target.value} />
            {/if}
            <div class="dd-list">
              {#each filteredChannels as ch (ch.channel_id)}
                <div class="dd-option" class:selected={selectedChannels.includes(ch.channel_id)}
                     onclick={() => toggleChannel(ch.channel_id)} role="option" tabindex="-1">
                  <input type="checkbox" checked={selectedChannels.includes(ch.channel_id)} tabindex="-1" />
                  <span class="dd-name">{ch.channel_name || ch.channel_id}</span>
                  <span class="dd-count">{(ch.count ?? 0).toLocaleString('de-DE')}</span>
                </div>
              {/each}
              {#if filteredChannels.length === 0}
                <span class="dd-empty">Kein Kanal gefunden</span>
              {/if}
            </div>
          </div>
        {/if}
      </div>
    </div>
  {/if}

  <!-- Kategorie-Dropdown -->
  {#if showCategories && categories.length > 0}
    <div class="filter-group">
      <span class="filter-label">Kategorie</span>
      <div class="filter-dropdown-wrap category">
        <button class="dropdown-trigger" onclick={(e) => { e.stopPropagation(); showCategoryDD = !showCategoryDD; showChannelDD = false; showTagDD = false; }}>
          {selectedCategories.length === 0 ? 'Alle Kategorien' : `${selectedCategories.length} ausgewählt`}
          <i class="fa-solid fa-chevron-down dd-arrow" class:open={showCategoryDD}></i>
        </button>
        {#if showCategoryDD}
          <div class="dropdown-panel" onclick={(e) => e.stopPropagation()}>
            {#if categories.length > 6}
              <input class="dd-search" type="text" placeholder="Kategorie suchen…"
                     value={categorySearch} oninput={(e) => categorySearch = e.target.value} />
            {/if}
            <div class="dd-list">
              {#each filteredCategories as cat (cat.id)}
                <div class="dd-option" class:selected={selectedCategories.includes(String(cat.id))}
                     onclick={() => toggleCategory(String(cat.id))} role="option" tabindex="-1">
                  <input type="checkbox" checked={selectedCategories.includes(String(cat.id))} tabindex="-1" />
                  <span class="dd-name">{cat.name}</span>
                  {#if cat.video_count}<span class="dd-count">{cat.video_count}</span>{/if}
                </div>
              {/each}
              {#if filteredCategories.length === 0}
                <span class="dd-empty">Keine Kategorie gefunden</span>
              {/if}
            </div>
          </div>
        {/if}
      </div>
    </div>
  {/if}

  <!-- Tag-Dropdown (Mehrfachauswahl, durchsuchbar) -->
  {#if showTags && tags.length > 0}
    <div class="filter-group">
      <span class="filter-label">Schlagwörter</span>
      <div class="filter-dropdown-wrap tag">
        <button class="dropdown-trigger" onclick={(e) => { e.stopPropagation(); showTagDD = !showTagDD; showChannelDD = false; showCategoryDD = false; }}>
          {selectedTags.length === 0 ? 'Alle Tags' : `${selectedTags.length} ausgewählt`}
          <i class="fa-solid fa-chevron-down dd-arrow" class:open={showTagDD}></i>
        </button>
        {#if showTagDD}
          <div class="dropdown-panel dropdown-wide" onclick={(e) => e.stopPropagation()}>
            <input class="dd-search" type="text" placeholder="Tag suchen… ({tags.length} gesamt)"
                   value={tagSearch} oninput={(e) => tagSearch = e.target.value} />
            <div class="dd-list">
              {#each filteredTags as t (t.tag)}
                <div class="dd-option" class:selected={selectedTags.includes(t.tag)}
                     onclick={() => toggleTag(t.tag)} role="option" tabindex="-1">
                  <input type="checkbox" checked={selectedTags.includes(t.tag)} tabindex="-1" />
                  <span class="dd-name">{t.tag}</span>
                  <span class="dd-count">{(t.count ?? 0).toLocaleString('de-DE')}</span>
                </div>
              {/each}
              {#if filteredTags.length === 0}
                <span class="dd-empty">Kein Tag gefunden</span>
              {/if}
              {#if !tagSearch && tags.length > 50}
                <span class="dd-hint">Suche zeigt alle {tags.length} Tags</span>
              {/if}
            </div>
          </div>
        {/if}
      </div>
    </div>
  {/if}

  {#if hasActive}
    <button class="filter-reset" onclick={clearAll}>
      <i class="fa-solid fa-xmark"></i> Zurücksetzen
    </button>
  {/if}
</div>

<!-- Aktive Filter-Chips mit x zum Entfernen -->
{#if hasActive}
  <div class="active-badges">
    {#each selectedTypes as t}
      <button class="fbadge type" onclick={() => toggleType(t)}>
        {VIDEO_TYPES.find(v => v.id === t)?.label || t} <i class="fa-solid fa-xmark"></i>
      </button>
    {/each}
    {#each selectedChannels as chId}
      <button class="fbadge channel" onclick={() => toggleChannel(chId)}>
        {channels.find(c => c.channel_id === chId)?.channel_name || chId} <i class="fa-solid fa-xmark"></i>
      </button>
    {/each}
    {#each selectedCategories as catId}
      <button class="fbadge category" onclick={() => toggleCategory(catId)}>
        {categories.find(c => String(c.id) === catId)?.name || catId} <i class="fa-solid fa-xmark"></i>
      </button>
    {/each}
    {#each selectedTags as tag}
      <button class="fbadge tag" onclick={() => toggleTag(tag)}>
        <i class="fa-solid fa-tag"></i> {tag} <i class="fa-solid fa-xmark"></i>
      </button>
    {/each}
  </div>
{/if}

<style>
  /* Gestaltung nach mockups/stil.css: .filter, .chip, .eingabe */
  .multi-filter {
    display: flex; align-items: center; gap: var(--tv-a2) var(--tv-a4); flex-wrap: wrap;
    padding: var(--tv-a3) var(--tv-a4); background: var(--tv-flaeche);
    border-radius: var(--tv-ecke); margin-bottom: var(--tv-a3);
  }
  .filter-group { display: flex; align-items: center; gap: var(--tv-a2); flex-wrap: wrap; }
  .filter-label {
    font-size: var(--tv-gr-marke); font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--tv-text-3); white-space: nowrap;
  }

  .filter-search {
    display: flex; align-items: center; gap: var(--tv-a2); height: 40px; width: 260px;
    padding: 0 var(--tv-a2) 0 var(--tv-a3);
    background: var(--tv-karte); border: 1px solid var(--tv-rand); border-radius: var(--tv-ecke);
  }
  .filter-search:focus-within { border-color: rgba(var(--tv-akzent-rgb), 0.6); }
  .search-icon { color: var(--tv-text-3); }
  .filter-search input {
    flex: 1; min-width: 0; border: none; background: none; outline: none;
    color: var(--tv-text); font: inherit; font-size: var(--tv-gr-klein);
  }
  .filter-search input::placeholder { color: var(--tv-text-3); }
  .search-clear { background: none; border: none; color: var(--tv-text-3); cursor: pointer; padding: 2px 4px; }
  .search-clear:hover { color: var(--tv-text); }

  .chip-row { display: flex; flex-wrap: wrap; gap: var(--tv-a2); }
  .filter-chip, .dropdown-trigger {
    display: inline-flex; align-items: center; gap: 7px; height: 34px; padding: 0 var(--tv-a3);
    background: var(--tv-karte); border: 1px solid var(--tv-rand); border-radius: var(--tv-ecke);
    color: var(--tv-text-2); font: inherit; font-size: var(--tv-gr-klein); font-weight: 500;
    cursor: pointer; white-space: nowrap;
    transition: color var(--tv-schnell), border-color var(--tv-schnell), background var(--tv-schnell);
  }
  .filter-chip:hover, .dropdown-trigger:hover { color: var(--tv-text); border-color: var(--tv-rand-stark); }
  .filter-chip.active {
    background: rgba(var(--tv-akzent-rgb), 0.12); border-color: rgba(var(--tv-akzent-rgb), 0.55); color: var(--tv-akzent);
  }
  .filter-chip.music-chip:first-of-type { margin-left: var(--tv-a2); }

  .filter-dropdown-wrap { position: relative; }
  .dd-arrow { font-size: 12px; transition: transform var(--tv-schnell); }
  .dd-arrow.open { transform: rotate(180deg); }
  .dropdown-panel {
    position: absolute; top: calc(100% + 4px); left: 0; z-index: 100;
    min-width: 260px; max-width: 360px; padding: var(--tv-a2);
    background: var(--tv-karte); border: 1px solid var(--tv-rand-stark);
    border-radius: var(--tv-ecke); box-shadow: var(--tv-schatten);
  }
  .dropdown-wide { min-width: 300px; max-width: 420px; }
  .dd-search {
    width: 100%; height: 36px; padding: 0 var(--tv-a3); margin-bottom: var(--tv-a1);
    background: var(--tv-flaeche); border: 1px solid var(--tv-rand); border-radius: var(--tv-ecke);
    color: var(--tv-text); font: inherit; font-size: var(--tv-gr-klein); outline: none;
  }
  .dd-search:focus { border-color: rgba(var(--tv-akzent-rgb), 0.6); }
  .dd-list { max-height: 300px; overflow-y: auto; display: flex; flex-direction: column; gap: 1px; }
  .dd-option {
    display: flex; align-items: center; gap: var(--tv-a2); padding: 7px var(--tv-a2);
    border-radius: var(--tv-ecke-klein); cursor: pointer; user-select: none;
    font-size: var(--tv-gr-klein); color: var(--tv-text-2);
  }
  .dd-option:hover { background: var(--tv-karte-2); color: var(--tv-text); }
  .dd-option.selected { background: rgba(var(--tv-akzent-rgb), 0.12); color: var(--tv-akzent); font-weight: 600; }
  .dd-option input[type="checkbox"] { accent-color: var(--tv-akzent); width: 15px; height: 15px; flex-shrink: 0; pointer-events: none; }
  .dd-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .dd-count {
    min-width: 22px; height: 20px; padding: 0 6px; display: inline-grid; place-items: center; flex-shrink: 0;
    font-family: var(--tv-schrift-zahl); font-size: var(--tv-gr-marke); font-weight: 600;
    background: var(--tv-karte-2); color: var(--tv-text-2); border-radius: var(--tv-ecke-klein);
  }
  .dd-empty, .dd-hint { display: block; padding: var(--tv-a3); text-align: center; color: var(--tv-text-3); font-size: var(--tv-gr-klein); }

  .filter-reset {
    margin-left: auto; height: 34px; padding: 0 var(--tv-a3);
    background: none; border: 1px solid transparent; border-radius: var(--tv-ecke);
    color: var(--tv-text-2); font: inherit; font-size: var(--tv-gr-klein); cursor: pointer;
  }
  .filter-reset:hover { color: var(--tv-gefahr); background: rgba(var(--tv-gefahr-rgb), 0.08); }

  /* Gewählte Filter einzeln entfernbar */
  .active-badges { display: flex; gap: var(--tv-a2); flex-wrap: wrap; margin-bottom: var(--tv-a3); }
  .fbadge {
    display: inline-flex; align-items: center; gap: 6px; height: 30px; padding: 0 var(--tv-a3);
    border: 1px solid transparent; border-radius: var(--tv-ecke);
    font: inherit; font-size: var(--tv-gr-klein); font-weight: 600; cursor: pointer;
  }
  .fbadge.type { background: rgba(var(--tv-akzent-rgb), 0.12); color: var(--tv-akzent); }
  .fbadge.channel { background: rgba(192, 132, 252, 0.14); color: var(--tv-art-musik); }
  .fbadge.category { background: rgba(var(--tv-warnung-rgb), 0.14); color: var(--tv-warnung); }
  .fbadge.tag { background: rgba(var(--tv-erfolg-rgb), 0.14); color: var(--tv-erfolg); }
  .fbadge:hover { border-color: currentColor; }

  /* Eigene Dauer von-bis */
  .dur-custom {
    display: flex; align-items: center; gap: 4px; height: 34px; padding: 0 var(--tv-a2);
    background: var(--tv-karte); border: 1px solid var(--tv-rand); border-radius: var(--tv-ecke);
  }
  .dur-custom.active { border-color: rgba(var(--tv-akzent-rgb), 0.55); }
  .dur-input {
    width: 52px; border: none; background: none; outline: none; text-align: center;
    color: var(--tv-text); font-family: var(--tv-schrift-zahl); font-size: var(--tv-gr-klein);
    -moz-appearance: textfield;
  }
  .dur-input::placeholder { color: var(--tv-text-3); font-family: var(--tv-schrift); }
  .dur-input::-webkit-inner-spin-button,
  .dur-input::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
  .dur-sep, .dur-unit { color: var(--tv-text-3); font-size: var(--tv-gr-klein); }
  .dur-clear { background: none; border: none; color: var(--tv-text-3); cursor: pointer; padding: 2px 4px; }
  .dur-clear:hover { color: var(--tv-gefahr); }
</style>

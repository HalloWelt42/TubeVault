<!--
  TubeVault -  MultiFilter v1.5.52
  Wiederverwendbare Filter-Leiste: Typ, Kanal, Kategorie, Tags (Mehrfachauswahl)
  © HalloWelt42 -  Private Nutzung
-->
<script>
  import { onMount } from 'svelte';
  import { api } from '../../api/client.js';

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
    onchange = () => {},
  } = $props();

  // Selektionen
  let selectedTypes = $state([]);
  let selectedChannels = $state([]);
  let selectedCategories = $state([]);
  let selectedTags = $state([]);
  let selectedDurations = $state([]);
  let musicOnly = $state(false);
  let customDurMin = $state('');
  let customDurMax = $state('');
  let customDurActive = $state(false);
  let searchText = $state('');
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

  // Einmalig laden -  KEIN $effect (verhindert Reset bei Parent-Rerender)
  onMount(async () => {
    if (showChannels) {
      try {
        // Im Feed-Modus: Kanaele aus Subscriptions/RSS, sonst aus Videos
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
    document.addEventListener('click', onClickOutside);
    return () => document.removeEventListener('click', onClickOutside);
  });

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
    selectedDurations.length > 0 || customDurActive || searchText.trim().length > 0
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
      <span class="filter-label">Typ:</span>
      <div class="chip-row">
        {#each VIDEO_TYPES as vt}
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
        {/if}
      </div>
    </div>
  {/if}

  <!-- Dauer-Chips + Custom -->
  {#if showDuration}
    <div class="filter-group dur-group">
      <span class="filter-label">Dauer:</span>
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
        <span class="dur-sep">–</span>
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
      <span class="filter-label">Kanal:</span>
      <div class="filter-dropdown-wrap channel">
        <button class="dropdown-trigger" onclick={(e) => { e.stopPropagation(); showChannelDD = !showChannelDD; showCategoryDD = false; showTagDD = false; }}>
          {selectedChannels.length === 0 ? 'Alle Kanaele' : `${selectedChannels.length} ausgewaehlt`}
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
                  <span class="dd-count">{ch.count}</span>
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
      <span class="filter-label">Kategorie:</span>
      <div class="filter-dropdown-wrap category">
        <button class="dropdown-trigger" onclick={(e) => { e.stopPropagation(); showCategoryDD = !showCategoryDD; showChannelDD = false; showTagDD = false; }}>
          {selectedCategories.length === 0 ? 'Alle Kategorien' : `${selectedCategories.length} ausgewaehlt`}
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
      <span class="filter-label">Tags:</span>
      <div class="filter-dropdown-wrap tag">
        <button class="dropdown-trigger" onclick={(e) => { e.stopPropagation(); showTagDD = !showTagDD; showChannelDD = false; showCategoryDD = false; }}>
          {selectedTags.length === 0 ? 'Alle Tags' : `${selectedTags.length} ausgewaehlt`}
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
                  <span class="dd-count">{t.count}</span>
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
      <i class="fa-solid fa-xmark"></i> Zuruecksetzen
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
  .multi-filter {
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    padding: 10px 14px; background: var(--bg-secondary);
    border: 1px solid var(--border-primary); border-radius: 10px;
    margin-bottom: 14px;
  }
  .filter-group { display: flex; align-items: center; gap: 6px; }
  .filter-label {
    font-size: 0.72rem; color: var(--text-tertiary); font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.04em; white-space: nowrap;
  }

  .filter-search {
    display: flex; align-items: center; gap: 6px;
    background: var(--bg-primary); border: 1px solid var(--border-primary);
    border-radius: 8px; padding: 0 10px; min-width: 160px;
  }
  .filter-search:focus-within { border-color: var(--accent-primary); }
  .search-icon { font-size: 0.76rem; color: var(--text-tertiary); }
  .filter-search input {
    flex: 1; border: none; background: none; color: var(--text-primary);
    font-size: 0.82rem; padding: 6px 0; outline: none;
  }
  .search-clear {
    background: none; border: none; color: var(--text-tertiary);
    cursor: pointer; font-size: 0.72rem; padding: 2px;
  }
  .search-clear:hover { color: var(--text-primary); }

  .chip-row { display: flex; gap: 4px; }
  .filter-chip {
    display: flex; align-items: center; gap: 4px;
    padding: 4px 10px; background: var(--bg-primary);
    border: 1px solid var(--border-primary); border-radius: 6px;
    color: var(--text-secondary); font-size: 0.78rem; cursor: pointer;
    transition: all 0.12s; white-space: nowrap;
  }
  .filter-chip:hover { border-color: var(--accent-primary); color: var(--text-primary); }
  .filter-chip.active {
    background: var(--accent-primary); color: #fff;
    border-color: var(--accent-primary); font-weight: 600;
  }
  .filter-chip i { font-size: 0.7rem; }
  .filter-chip.music-chip { margin-left: 6px; border-left: 2px solid var(--border-secondary); padding-left: 10px; }

  .filter-dropdown-wrap { position: relative; }
  .dropdown-trigger {
    display: flex; align-items: center; gap: 6px;
    padding: 4px 10px; background: var(--bg-primary);
    border: 1px solid var(--border-primary); border-radius: 6px;
    color: var(--text-secondary); font-size: 0.78rem; cursor: pointer;
    transition: all 0.12s; white-space: nowrap;
  }
  .dropdown-trigger:hover { border-color: var(--accent-primary); }
  .dd-arrow { font-size: 0.6rem; transition: transform 0.15s; }
  .dd-arrow.open { transform: rotate(180deg); }

  .dropdown-panel {
    position: absolute; top: calc(100% + 4px); left: 0;
    background: var(--bg-primary); border: 1px solid var(--border-primary);
    border-radius: 10px; box-shadow: 0 8px 24px rgba(0,0,0,0.25);
    z-index: 100; min-width: 220px; max-width: 320px; padding: 6px;
  }
  .dropdown-wide { min-width: 280px; max-width: 400px; }
  .dd-search {
    width: 100%; padding: 6px 10px; border: 1px solid var(--border-primary);
    border-radius: 6px; background: var(--bg-secondary); color: var(--text-primary);
    font-size: 0.78rem; outline: none; margin-bottom: 4px; box-sizing: border-box;
  }
  .dd-search:focus { border-color: var(--accent-primary); }
  .dd-list { max-height: 260px; overflow-y: auto; display: flex; flex-direction: column; gap: 1px; }
  .dd-option {
    display: flex; align-items: center; gap: 8px;
    padding: 5px 8px; border-radius: 6px; cursor: pointer;
    font-size: 0.8rem; color: var(--text-secondary); transition: background 0.1s;
    user-select: none;
  }
  .dd-option:hover { background: var(--bg-hover); }
  .dd-option.selected { background: var(--accent-muted); color: var(--accent-primary); font-weight: 600; }
  .dd-option input[type="checkbox"] { accent-color: var(--accent-primary); width: 14px; height: 14px; flex-shrink: 0; pointer-events: none; }
  .dd-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .dd-count {
    font-size: 0.68rem; background: var(--bg-tertiary); padding: 0 5px;
    border-radius: 8px; color: var(--text-tertiary); font-weight: 600; flex-shrink: 0;
  }
  .dd-empty { padding: 12px; text-align: center; color: var(--text-tertiary); font-size: 0.78rem; }
  .dd-hint { display: block; padding: 6px 8px; text-align: center; color: var(--text-tertiary); font-size: 0.7rem; font-style: italic; }

  .filter-reset {
    margin-left: auto; padding: 4px 10px; background: none;
    border: 1px solid var(--border-primary); border-radius: 6px;
    color: var(--text-tertiary); font-size: 0.76rem; cursor: pointer;
  }
  .filter-reset:hover { border-color: var(--status-error); color: var(--status-error); }

  .active-badges { display: flex; gap: 5px; flex-wrap: wrap; margin-bottom: 12px; }
  .fbadge {
    display: flex; align-items: center; gap: 4px;
    padding: 3px 10px; border: none; border-radius: 6px;
    font-size: 0.76rem; font-weight: 600; cursor: pointer; transition: all 0.12s;
  }
  .fbadge i { font-size: 0.62rem; }
  .fbadge.type { background: var(--accent-muted); color: var(--accent-primary); }
  .fbadge.channel { background: rgba(139,92,246,0.12); color: #8b5cf6; }
  .fbadge.category { background: rgba(245,158,11,0.12); color: #d97706; }
  .fbadge.tag { background: rgba(16,185,129,0.12); color: #059669; }
  .fbadge:hover { opacity: 0.7; }

  /* Custom Duration */
  .dur-group { flex-wrap: wrap; }
  .dur-custom {
    display: flex; align-items: center; gap: 4px;
    padding: 2px 6px; background: var(--bg-primary);
    border: 1px solid var(--border-primary); border-radius: 6px;
    transition: border-color 0.12s;
  }
  .dur-custom.active { border-color: var(--accent-primary); }
  .dur-input {
    width: 48px; padding: 3px 4px; border: none; background: none;
    color: var(--text-primary); font-size: 0.78rem; text-align: center;
    outline: none; -moz-appearance: textfield;
  }
  .dur-input::placeholder { color: var(--text-tertiary); }
  .dur-input::-webkit-inner-spin-button,
  .dur-input::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
  .dur-sep { color: var(--text-tertiary); font-size: 0.72rem; }
  .dur-unit { font-size: 0.68rem; color: var(--text-tertiary); font-weight: 600; }
  .dur-clear {
    background: none; border: none; color: var(--text-tertiary);
    cursor: pointer; font-size: 0.68rem; padding: 2px;
  }
  .dur-clear:hover { color: var(--status-error); }
</style>

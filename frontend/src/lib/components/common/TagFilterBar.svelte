<!--
  TubeVault – TagFilterBar v1.0.0
  Wiederverwendbare Tag-Filter-Leiste: Tag-Suche, Top-15 mit Aufklappen,
  aktive Tags als Badges. Ersetzt die identischen Kopien aus Bibliothek
  und Archiv (Markup + Styles waren doppelt gepflegt).
  © HalloWelt42 – Private Nutzung
-->
<script>
  import { tagKey } from '../../utils/tagKey.js';

  // allTags: [{ tag, key, count }] vom Server (key: Schlüssel des Schlagworts, Schreibweise egal)
  let { allTags = [], activeTags = [], onToggle = () => {} } = $props();

  let activeKeys = $derived(new Set(activeTags.map(tagKey)));

  let tagSearch = $state('');
  let showAllTags = $state(false);

  let filteredTags = $derived(
    tagSearch ? allTags.filter(t => t.tag.toLowerCase().includes(tagSearch.toLowerCase())) : allTags
  );
  let visibleTags = $derived(tagSearch ? filteredTags : (showAllTags ? allTags : allTags.slice(0, 15)));
</script>

{#if allTags.length > 0}
  <div class="tag-bar">
    <span class="tv-etikett">Schlagwörter</span>
    <label class="tag-search">
      <i class="fa-solid fa-magnifying-glass"></i>
      <input type="text" placeholder="Suchen ({allTags.length.toLocaleString('de-DE')})" bind:value={tagSearch} />
      {#if tagSearch}<button class="tag-search-clear" onclick={() => tagSearch = ''} title="Leeren"><i class="fa-solid fa-xmark"></i></button>{/if}
    </label>
    {#each visibleTags as t}
      <button class="tv-chip" class:aktiv={activeKeys.has(tagKey(t.key ?? t.tag))} onclick={() => onToggle(t.tag)}>
        {t.tag} <span class="tv-zaehler">{(t.count ?? 0).toLocaleString('de-DE')}</span>
      </button>
    {/each}
    {#if !tagSearch && allTags.length > 15}
      {#if allTags.length <= 60}
        <button class="tv-chip ohne-rahmen" onclick={() => showAllTags = !showAllTags}>
          {showAllTags ? 'weniger' : `+ ${allTags.length - 15} weitere`}
        </button>
      {:else}
        <span class="tag-hint">weitere über die Suche ({allTags.length.toLocaleString('de-DE')} insgesamt)</span>
      {/if}
    {/if}
    {#if tagSearch && visibleTags.length === 0}<span class="tag-hint">Kein Schlagwort gefunden</span>{/if}
  </div>
{/if}

{#if activeTags.length > 0}
  <div class="active-filter">
    {#each activeTags as tag}
      <button class="tv-chip aktiv" onclick={() => onToggle(tag)} title="Schlagwort entfernen">
        <i class="fa-solid fa-tag"></i> {tag} <i class="fa-solid fa-xmark"></i>
      </button>
    {/each}
  </div>
{/if}

<style>
  /* Gestaltung nach mockups/stil.css: .reihe-chips */
  .tag-bar { display: flex; flex-wrap: wrap; align-items: center; gap: var(--tv-a2); margin-bottom: var(--tv-a3); }
  .tag-bar .tv-etikett { margin-right: var(--tv-a2); }
  .tag-search {
    display: flex; align-items: center; gap: 6px; height: 34px; padding: 0 var(--tv-a2) 0 var(--tv-a3);
    background: var(--tv-karte); border: 1px solid var(--tv-rand); border-radius: var(--tv-ecke);
    color: var(--tv-text-3); width: 210px;
  }
  .tag-search:focus-within { border-color: rgba(var(--tv-akzent-rgb), 0.6); }
  .tag-search input { flex: 1; min-width: 0; background: none; border: 0; outline: 0; color: var(--tv-text); font: inherit; font-size: var(--tv-gr-klein); }
  .tag-search-clear { background: none; border: none; color: var(--tv-text-3); cursor: pointer; padding: 2px 4px; }
  .tag-hint { font-size: var(--tv-gr-klein); color: var(--tv-text-3); }
  .active-filter { display: flex; gap: var(--tv-a2); margin-bottom: var(--tv-a3); flex-wrap: wrap; }
</style>

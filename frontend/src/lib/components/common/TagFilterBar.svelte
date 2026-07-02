<!--
  TubeVault – TagFilterBar v1.0.0
  Wiederverwendbare Tag-Filter-Leiste: Tag-Suche, Top-15 mit Aufklappen,
  aktive Tags als Badges. Ersetzt die identischen Kopien aus Bibliothek
  und Archiv (Markup + Styles waren doppelt gepflegt).
  © HalloWelt42 – Private Nutzung
-->
<script>
  let { allTags = [], activeTags = [], onToggle = () => {} } = $props();

  let tagSearch = $state('');
  let showAllTags = $state(false);

  let filteredTags = $derived(
    tagSearch ? allTags.filter(t => t.tag.toLowerCase().includes(tagSearch.toLowerCase())) : allTags
  );
  let visibleTags = $derived(tagSearch ? filteredTags : (showAllTags ? allTags : allTags.slice(0, 15)));
</script>

{#if allTags.length > 0}
  <div class="tag-bar">
    <span class="tag-label">Tags:</span>
    <div class="tag-search-wrap">
      <i class="fa-solid fa-magnifying-glass tag-search-icon"></i>
      <input type="text" class="tag-search" placeholder="Tag suchen… ({allTags.length})" bind:value={tagSearch} />
      {#if tagSearch}<button class="tag-search-clear" onclick={() => tagSearch = ''}><i class="fa-solid fa-xmark"></i></button>{/if}
    </div>
    <div class="tag-list">
      {#each visibleTags as t}
        <button class="tag-chip" class:active={activeTags.includes(t.tag)} onclick={() => onToggle(t.tag)}>
          {t.tag} <span class="tag-count">{t.count}</span>
        </button>
      {/each}
      {#if !tagSearch && allTags.length > 15}
        {#if allTags.length <= 60}
          <button class="tag-toggle" onclick={() => showAllTags = !showAllTags}>
            {showAllTags ? 'weniger' : `+${allTags.length - 15} weitere`}
          </button>
        {:else}
          <span class="tag-hint">Weitere Tags über Suche finden ({allTags.length} gesamt)</span>
        {/if}
      {/if}
      {#if tagSearch && visibleTags.length === 0}<span class="tag-empty">Kein Tag gefunden</span>{/if}
    </div>
  </div>
{/if}

{#if activeTags.length > 0}
  <div class="active-filter">
    {#each activeTags as tag}
      <button class="filter-badge" onclick={() => onToggle(tag)}>
        <i class="fa-solid fa-tag"></i> {tag} <i class="fa-solid fa-xmark"></i>
      </button>
    {/each}
  </div>
{/if}

<style>
  .tag-bar { display:flex; align-items:flex-start; gap:8px; margin-bottom:14px; padding:10px 14px; background:var(--bg-secondary); border:1px solid var(--border-primary); border-radius:10px; }
  .tag-label { font-size:0.76rem; color:var(--text-tertiary); font-weight:600; text-transform:uppercase; letter-spacing:0.04em; padding-top:4px; white-space:nowrap; }
  .tag-search-wrap { display:flex; align-items:center; gap:5px; background:var(--bg-primary); border:1px solid var(--border-primary); border-radius:8px; padding:2px 8px; min-width:140px; flex-shrink:0; }
  .tag-search-wrap:focus-within { border-color:var(--accent-primary); }
  .tag-search-icon { font-size:0.68rem; color:var(--text-tertiary); }
  .tag-search { border:none; background:none; color:var(--text-primary); font-size:0.78rem; padding:3px 0; outline:none; width:100%; }
  .tag-search-clear { background:none; border:none; color:var(--text-tertiary); cursor:pointer; font-size:0.68rem; padding:2px; }
  .tag-empty { font-size:0.76rem; color:var(--text-tertiary); padding:2px 6px; }
  .tag-list { display:flex; flex-wrap:wrap; gap:5px; }
  .tag-chip { display:flex; align-items:center; gap:4px; padding:3px 10px; background:var(--bg-primary); border:1px solid var(--border-primary); border-radius:14px; color:var(--text-secondary); font-size:0.76rem; cursor:pointer; transition:all 0.12s; }
  .tag-chip:hover { border-color:var(--accent-primary); color:var(--text-primary); }
  .tag-chip.active { background:var(--accent-primary); color:#fff; border-color:var(--accent-primary); font-weight:600; }
  .tag-chip.active .tag-count { background:rgba(255,255,255,0.25); color:#fff; }
  .tag-count { font-size:0.65rem; background:var(--bg-tertiary); color:var(--text-tertiary); padding:0 5px; border-radius:8px; font-weight:600; }
  .tag-toggle { padding:3px 10px; background:none; border:1px dashed var(--border-primary); border-radius:14px; color:var(--accent-primary); font-size:0.76rem; cursor:pointer; }
  .tag-hint { padding:3px 10px; font-size:0.72rem; color:var(--text-tertiary); font-style:italic; }
  .active-filter { display:flex; gap:6px; margin-bottom:12px; flex-wrap:wrap; }
  .filter-badge { padding:4px 10px; background:var(--accent-muted); color:var(--accent-primary); border:none; border-radius:6px; font-size:0.78rem; font-weight:600; cursor:pointer; }
  .filter-badge:hover { background:var(--accent-primary); color:#fff; }
</style>

<!--
  Steuerleiste einer Sammlung (Favoriten, Playlist, Verlauf): Suche, Stand,
  Sortierung, weitere Chip-Gruppen (children), rechts Zusatzknöpfe (rechts),
  Ansicht Liste/Kacheln und Auswählen. Gruppen ohne Werte entfallen.
-->
<script>
  let {
    search = $bindable(''),
    placeholder = 'Suchen',
    states = null,          // [{ key, label, count }]
    state = $bindable(''),
    sorts = null,           // [{ key, label, title? }]
    sort = $bindable(''),
    view = $bindable(null), // 'liste' | 'kacheln' | null (kein Umschalter)
    onSelect = null,        // Auswählen-Knopf
    children,
    rechts,
  } = $props();
</script>

<div class="tv-filter leiste">
  <input class="tv-eingabe suche" type="search" {placeholder} bind:value={search} />

  {#if states}
    <span class="tv-trenner"></span>
    {#each states as option (option.key)}
      <button class="tv-chip" class:aktiv={state === option.key} onclick={() => state = option.key}>
        {option.label}{#if option.count !== undefined}<span class="tv-zaehler">{option.count}</span>{/if}
      </button>
    {/each}
  {/if}

  {#if sorts}
    <span class="tv-trenner"></span>
    <span class="tv-etikett">Sortieren</span>
    {#each sorts as option (option.key)}
      <button class="tv-chip" class:aktiv={sort === option.key} title={option.title} onclick={() => sort = option.key}>{option.label}</button>
    {/each}
  {/if}

  {@render children?.()}

  <div class="rechts">
    {@render rechts?.()}
    {#if view}
      <div class="ansicht" role="group" aria-label="Ansicht">
        <button class:an={view === 'liste'} onclick={() => view = 'liste'} title="Liste"><i class="fa-solid fa-list"></i></button>
        <button class:an={view === 'kacheln'} onclick={() => view = 'kacheln'} title="Kacheln"><i class="fa-solid fa-table-cells-large"></i></button>
      </div>
    {/if}
    {#if onSelect}
      <button class="tv-knopf klein" onclick={onSelect}><i class="fa-regular fa-square-check"></i> Auswählen</button>
    {/if}
  </div>
</div>

<style>
  .leiste { margin-bottom: 0; }
  .suche { width: 240px; }
  .rechts { margin-left: auto; display: flex; gap: var(--tv-a2); align-items: center; }
  .ansicht { display: inline-flex; background: var(--tv-karte); border: 1px solid var(--tv-rand); border-radius: var(--tv-ecke); }
  .ansicht button { width: 38px; height: 32px; border: 0; background: none; color: var(--tv-text-3); cursor: pointer;
                    border-radius: var(--tv-ecke-klein); }
  .ansicht button.an { background: var(--tv-karte-3); color: var(--tv-akzent); }
</style>

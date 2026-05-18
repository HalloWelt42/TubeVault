<!--
  TubeVault – Admin DataTable v1.0.0

  Wiederverwendbare Tabelle für Admin-Views.
  Features:
  - Spalten-definitionen (mit Custom-Rendering via Snippet)
  - Sortierung (klick auf sortable-Header)
  - Status-Tabs (filter)
  - Suche (debounced vom Parent geliefert)
  - Paginierung
  - Bulk-Select + Bulk-Actions

  Parent ist für Datenbeschaffung verantwortlich, Tabelle rendert nur.
-->
<script>
  let {
    columns = [],           // [{ key, label, sortable?, align?, width? }]
    rows = [],
    getRowId = (r) => r.id,
    loading = false,

    // Paging
    total = 0,
    page = 1,
    perPage = 50,
    onPage = () => {},
    perPageOptions = [25, 50, 100, 200],
    onPerPage = () => {},

    // Sortierung
    sort = null,
    order = 'desc',
    onSort = () => {},

    // Filter-Tabs
    filterTabs = null,       // [{ id, label, count? }]
    activeTab = null,
    onTabChange = () => {},

    // Suche
    searchValue = '',
    searchPlaceholder = 'Suchen…',
    onSearch = () => {},

    // Bulk-Select
    selectable = false,
    selected = new Set(),
    onSelectChange = () => {},
    bulkActions = [],        // [{ label, icon, variant?, onClick(ids) }]

    // Slots
    rowCell,                 // (column, row) => Snippet für Zellen-Rendering
    rowActions,              // (row) => Snippet für Actions-Spalte
    emptyMessage = 'Keine Einträge',
  } = $props();

  let searchTimer = null;
  function onSearchInput(e) {
    if (searchTimer) clearTimeout(searchTimer);
    const v = e.target.value;
    searchTimer = setTimeout(() => onSearch(v), 300);
  }

  let totalPages = $derived(Math.max(1, Math.ceil(total / perPage)));

  function toggleSort(col) {
    if (!col.sortable) return;
    if (sort === col.key) {
      onSort(col.key, order === 'asc' ? 'desc' : 'asc');
    } else {
      onSort(col.key, 'desc');
    }
  }

  function isAllSelected() {
    return rows.length > 0 && rows.every(r => selected.has(getRowId(r)));
  }
  function toggleAll() {
    const s = new Set(selected);
    if (isAllSelected()) {
      for (const r of rows) s.delete(getRowId(r));
    } else {
      for (const r of rows) s.add(getRowId(r));
    }
    onSelectChange(s);
  }
  function toggleOne(id) {
    const s = new Set(selected);
    if (s.has(id)) s.delete(id); else s.add(id);
    onSelectChange(s);
  }
</script>

<div class="dt">
  <!-- Controls -->
  {#if filterTabs || onSearch !== undefined}
    <div class="dt-controls">
      {#if filterTabs}
        <div class="dt-tabs">
          {#each filterTabs as tab}
            <button class="dt-tab" class:active={activeTab === tab.id}
                    onclick={() => onTabChange(tab.id)}>
              {tab.label}
              {#if tab.count !== undefined}<span class="dt-tab-count">{tab.count.toLocaleString('de-DE')}</span>{/if}
            </button>
          {/each}
        </div>
      {/if}
      <input type="text" class="dt-search" placeholder={searchPlaceholder}
             value={searchValue} oninput={onSearchInput} />
      <select class="dt-per-page" value={perPage} onchange={(e) => onPerPage(parseInt(e.target.value))}>
        {#each perPageOptions as n}<option value={n}>{n}/Seite</option>{/each}
      </select>
    </div>
  {/if}

  <!-- Bulk-Action-Bar (erscheint wenn was ausgewählt ist) -->
  {#if selectable && selected.size > 0}
    <div class="dt-bulk">
      <span><strong>{selected.size}</strong> ausgewählt</span>
      {#each bulkActions as act}
        <button class="dt-bulk-btn"
                class:danger={act.variant === 'danger'}
                onclick={() => act.onClick([...selected])}>
          {#if act.icon}<i class={act.icon}></i>{/if} {act.label}
        </button>
      {/each}
      <button class="dt-bulk-clear" onclick={() => onSelectChange(new Set())}>Auswahl leeren</button>
    </div>
  {/if}

  <!-- Body -->
  {#if loading}
    <div class="dt-state"><i class="fa-solid fa-spinner fa-spin"></i> Laden…</div>
  {:else if rows.length === 0}
    <div class="dt-state">{emptyMessage}</div>
  {:else}
    <div class="dt-wrap">
      <table class="dt-table">
        <thead>
          <tr>
            {#if selectable}
              <th style="width:36px">
                <input type="checkbox" checked={isAllSelected()} onchange={toggleAll} />
              </th>
            {/if}
            {#each columns as col}
              <th class:sortable={col.sortable} class:active-sort={sort === col.key}
                  style:text-align={col.align || 'left'}
                  style:width={col.width || 'auto'}
                  onclick={() => toggleSort(col)}>
                {col.label}
                {#if col.sortable && sort === col.key}
                  <i class="fa-solid {order === 'asc' ? 'fa-caret-up' : 'fa-caret-down'} dt-sort-icon"></i>
                {/if}
              </th>
            {/each}
            {#if rowActions}<th style="width:110px; text-align:right"></th>{/if}
          </tr>
        </thead>
        <tbody>
          {#each rows as row (getRowId(row))}
            <tr class:selected={selected.has(getRowId(row))}>
              {#if selectable}
                <td>
                  <input type="checkbox"
                         checked={selected.has(getRowId(row))}
                         onchange={() => toggleOne(getRowId(row))} />
                </td>
              {/if}
              {#each columns as col}
                <td style:text-align={col.align || 'left'}>
                  {#if rowCell}{@render rowCell(col, row)}{:else}{row[col.key] ?? '–'}{/if}
                </td>
              {/each}
              {#if rowActions}
                <td class="dt-row-actions">{@render rowActions(row)}</td>
              {/if}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    {#if totalPages > 1}
      <div class="dt-pagination">
        <span class="dt-info">{total.toLocaleString('de-DE')} Einträge · Seite {page} / {totalPages}</span>
        <div class="dt-pg">
          <button class="dt-pg-btn" onclick={() => onPage(1)} disabled={page === 1}>«</button>
          <button class="dt-pg-btn" onclick={() => onPage(page - 1)} disabled={page === 1}>‹</button>
          <button class="dt-pg-btn" onclick={() => onPage(page + 1)} disabled={page >= totalPages}>›</button>
          <button class="dt-pg-btn" onclick={() => onPage(totalPages)} disabled={page >= totalPages}>»</button>
        </div>
      </div>
    {/if}
  {/if}
</div>

<style>
  .dt { display: flex; flex-direction: column; }
  .dt-controls { display: flex; gap: 10px; align-items: center; margin-bottom: 14px; flex-wrap: wrap; }

  .dt-tabs { display: flex; gap: 2px; }
  .dt-tab { padding: 6px 14px; background: var(--bg-tertiary); border: 1px solid var(--border-primary); color: var(--text-secondary); cursor: pointer; font-size: 0.82rem; display: flex; align-items: center; gap: 6px; }
  .dt-tab:first-child { border-radius: 8px 0 0 8px; }
  .dt-tab:last-child { border-radius: 0 8px 8px 0; }
  .dt-tab + .dt-tab { border-left: none; }
  .dt-tab.active { background: var(--accent-primary); color: #fff; border-color: var(--accent-primary); }
  .dt-tab-count { font-size: 0.72rem; opacity: 0.9; background: rgba(255,255,255,0.18); padding: 1px 6px; border-radius: 3px; font-family: monospace; }
  .dt-tab:not(.active) .dt-tab-count { background: var(--bg-secondary); }

  .dt-search { flex: 1 1 240px; padding: 7px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-primary); border-radius: 8px; color: var(--text-primary); font-size: 0.85rem; outline: none; }
  .dt-search:focus { border-color: var(--accent-primary); }
  .dt-per-page { padding: 7px 10px; background: var(--bg-tertiary); border: 1px solid var(--border-primary); border-radius: 8px; color: var(--text-secondary); font-size: 0.82rem; cursor: pointer; }

  .dt-bulk {
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
    padding: 10px 14px; margin-bottom: 12px;
    background: var(--accent-muted); border-radius: 10px;
    color: var(--accent-primary); font-size: 0.85rem;
  }
  .dt-bulk-btn {
    display: flex; align-items: center; gap: 6px;
    padding: 6px 12px; background: var(--accent-primary); color: #fff;
    border: none; border-radius: 6px; font-size: 0.82rem; cursor: pointer;
  }
  .dt-bulk-btn:hover { filter: brightness(1.1); }
  .dt-bulk-btn.danger { background: var(--status-error); }
  .dt-bulk-clear { background: none; border: none; color: var(--accent-primary); cursor: pointer; font-size: 0.82rem; text-decoration: underline; margin-left: auto; }

  .dt-state { padding: 40px; text-align: center; color: var(--text-tertiary); }

  .dt-wrap { overflow-x: auto; }
  .dt-table { width: 100%; border-collapse: collapse; }
  .dt-table th { padding: 10px 12px; font-size: 0.72rem; text-transform: uppercase; color: var(--text-tertiary); border-bottom: 1px solid var(--border-primary); font-weight: 600; text-align: left; user-select: none; }
  .dt-table th.sortable { cursor: pointer; }
  .dt-table th.sortable:hover { color: var(--text-primary); }
  .dt-table th.active-sort { color: var(--accent-primary); }
  .dt-sort-icon { margin-left: 4px; font-size: 0.78rem; }

  .dt-table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text-secondary); border-bottom: 1px solid var(--border-primary); vertical-align: top; }
  .dt-table tr:hover td { background: var(--bg-tertiary); }
  .dt-table tr.selected td { background: var(--accent-muted); }

  .dt-row-actions { white-space: nowrap; text-align: right; }

  .dt-pagination { display: flex; justify-content: space-between; align-items: center; margin-top: 14px; padding-top: 10px; border-top: 1px solid var(--border-primary); }
  .dt-info { font-size: 0.82rem; color: var(--text-tertiary); }
  .dt-pg { display: flex; gap: 4px; }
  .dt-pg-btn { width: 32px; height: 32px; background: var(--bg-tertiary); border: 1px solid var(--border-primary); border-radius: 6px; color: var(--text-secondary); cursor: pointer; }
  .dt-pg-btn:hover:not(:disabled) { border-color: var(--accent-primary); color: var(--accent-primary); }
  .dt-pg-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  input[type="checkbox"] { cursor: pointer; }
</style>

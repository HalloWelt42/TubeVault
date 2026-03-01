<script>
  /**
   * TubeVault -  Pagination v1.5.52
   * Einfache Seitennavigation
   * © HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
  SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
   */
  let { page = 1, totalPages = 1, onchange = () => {} } = $props();
</script>

{#if totalPages > 1}
  <div class="pagination">
    <button class="pg-btn" disabled={page <= 1} onclick={() => onchange(page - 1)}>
      <i class="fa-solid fa-chevron-left"></i>
    </button>
    {#each Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
      if (totalPages <= 7) return i + 1;
      if (page <= 4) return i + 1;
      if (page >= totalPages - 3) return totalPages - 6 + i;
      return page - 3 + i;
    }) as p}
      <button class="pg-btn" class:active={p === page} onclick={() => onchange(p)}>{p}</button>
    {/each}
    <button class="pg-btn" disabled={page >= totalPages} onclick={() => onchange(page + 1)}>
      <i class="fa-solid fa-chevron-right"></i>
    </button>
  </div>
{/if}

<style>
  .pagination { display: flex; align-items: center; justify-content: center; gap: 4px; margin-top: 20px; }
  .pg-btn {
    min-width: 36px; height: 36px;
    display: flex; align-items: center; justify-content: center;
    border-radius: 8px; border: 1px solid var(--border-primary);
    background: var(--bg-secondary); color: var(--text-secondary);
    font-size: 0.82rem; cursor: pointer;
  }
  .pg-btn:hover:not(:disabled) { border-color: var(--accent-primary); color: var(--text-primary); }
  .pg-btn.active { background: var(--accent-primary); color: #fff; border-color: var(--accent-primary); }
  .pg-btn:disabled { opacity: 0.4; cursor: not-allowed; }
</style>

<!--
  TubeVault -  LikeBar v1.5.90
  Wiederverwendbare Like/Dislike-Ratio-Anzeige.
  Modes: 'bar' (Variante A), 'compact' (für Cards/Meta), 'thumbnail' (Variante E).
  © HalloWelt42 -  Private Nutzung
-->
<script>
  import { formatViews } from '../../utils/format.js';

  /**
   * @type {{ likes: number, dislikes: number, mode?: 'bar'|'compact'|'thumbnail' }}
   */
  let { likes = 0, dislikes = 0, mode = 'bar' } = $props();

  let total = $derived(likes + dislikes);
  let ratio = $derived(total > 0 ? likes / total : 0);
  let pct = $derived((ratio * 100).toFixed(1));
  let pctInt = $derived(Math.round(ratio * 100));
  let color = $derived(ratio >= 0.8 ? 'var(--status-success)' : ratio >= 0.5 ? '#f59e0b' : 'var(--status-error)');
</script>

{#if total > 0}
  {#if mode === 'bar'}
    <!-- Variante A: Voller Balken mit Daumen + Zahlen -->
    <div class="lb-bar">
      <div class="lb-counts">
        <span class="lb-like"><i class="fa-solid fa-thumbs-up"></i> {formatViews(likes)}</span>
        <span class="lb-dislike"><i class="fa-solid fa-thumbs-down"></i> {formatViews(dislikes)}</span>
      </div>
      <div class="lb-track">
        <div class="lb-fill" style="width: {pct}%; background: {color}"></div>
      </div>
      <span class="lb-pct" style="color: {color}">{pct}%</span>
    </div>

  {:else if mode === 'compact'}
    <!-- Kompakt: Mini-Balken + Prozent für Card-Meta -->
    <span class="lb-compact">
      <i class="fa-solid fa-thumbs-up lb-c-icon" style="color: {color}"></i>
      <span class="lb-c-track"><span class="lb-c-fill" style="width: {pct}%; background: {color}"></span></span>
      <span class="lb-c-pct" style="color: {color}">{pctInt}%</span>
    </span>

  {:else if mode === 'thumbnail'}
    <!-- Variante E: Dünner Balken am unteren Thumbnail-Rand -->
    <div class="lb-thumb">
      <div class="lb-thumb-fill" style="width: {pct}%; background: {color}"></div>
    </div>
  {/if}
{/if}

<style>
  /* ═══ MODE: bar (Variante A) ═══ */
  .lb-bar {
    display: flex; align-items: center; gap: 10px;
    padding: 6px 12px; background: var(--bg-tertiary); border-radius: 8px;
  }
  .lb-counts { display: flex; gap: 10px; font-size: 0.78rem; font-weight: 600; }
  .lb-like { color: var(--status-success); display: flex; align-items: center; gap: 4px; }
  .lb-dislike { color: var(--status-error); display: flex; align-items: center; gap: 4px; }
  .lb-track { flex: 1; max-width: 200px; height: 5px; background: var(--status-error); border-radius: 3px; overflow: hidden; }
  .lb-fill { height: 100%; border-radius: 3px; transition: width 0.4s; }
  .lb-pct { font-size: 0.82rem; font-weight: 700; min-width: 42px; text-align: right; font-variant-numeric: tabular-nums; }

  /* ═══ MODE: compact (Card-Meta) ═══ */
  .lb-compact { display: inline-flex; align-items: center; gap: 4px; }
  .lb-c-icon { font-size: 0.58rem; }
  .lb-c-track { width: 36px; height: 3px; background: var(--bg-tertiary); border-radius: 2px; overflow: hidden; }
  .lb-c-fill { height: 100%; border-radius: 2px; transition: width 0.4s; }
  .lb-c-pct { font-size: 0.62rem; font-weight: 600; font-variant-numeric: tabular-nums; }

  /* ═══ MODE: thumbnail (Variante E) ═══ */
  .lb-thumb { position: absolute; bottom: 0; left: 0; right: 0; height: 3px; background: var(--status-error); }
  .lb-thumb-fill { height: 100%; transition: width 0.4s; }
</style>

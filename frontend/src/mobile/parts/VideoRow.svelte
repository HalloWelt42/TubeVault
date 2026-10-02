<!--
  Eine Zeile der Mobil-Listen: Vorschaubild links, Titel und Kanal rechts.
  Die ganze Zeile ist die Berührfläche. Rechts kann eine Aktion stehen
  (Snippet), die nicht zum Öffnen zählt.
-->
<script>
  import { formatDuration } from '../../lib/utils/format.js';

  let {
    title,
    channel = null,
    duration = null,
    thumb,
    archived = false,
    progress = null,      // 0..1 = angefangen gesehen
    note = null,          // kurzer Zusatz, z.B. Datum
    onopen = null,
    action = null,
  } = $props();

  let thumbFailed = $state(false);
</script>

<div class="row">
  <button class="open" onclick={onopen} disabled={!onopen}>
    <span class="thumb">
      {#if thumb && !thumbFailed}
        <img src={thumb} alt="" loading="lazy" onerror={() => thumbFailed = true} />
      {:else}
        <i class="fa-solid fa-film"></i>
      {/if}
      {#if duration}<span class="dur">{formatDuration(duration)}</span>{/if}
      {#if progress !== null}<span class="bar"><span style="width: {Math.round(progress * 100)}%"></span></span>{/if}
    </span>
    <span class="text">
      <span class="title">{title}</span>
      <span class="meta">
        {channel || 'Unbekannt'}{#if note}{' · '}{note}{/if}
        {#if archived}<span class="mark"><i class="fa-solid fa-box-archive"></i> Archiv</span>{/if}
      </span>
    </span>
  </button>
  {#if action}<div class="action">{@render action()}</div>{/if}
</div>

<style>
  .row { display: flex; align-items: stretch; border-bottom: 1px solid var(--m-line); }
  .open {
    flex: 1; min-width: 0; display: flex; gap: 12px; align-items: center;
    padding: 10px 16px; text-align: left; min-height: 84px;
  }
  .open:active:not(:disabled) { background: var(--m-surface); }
  .thumb {
    position: relative; flex: 0 0 124px; aspect-ratio: 16 / 9; border-radius: 8px;
    overflow: hidden; background: var(--m-surface-2);
    display: flex; align-items: center; justify-content: center; color: var(--m-faint);
  }
  .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .dur {
    position: absolute; right: 4px; bottom: 4px; padding: 1px 5px; border-radius: 4px;
    background: rgba(0, 0, 0, 0.82); font-size: 0.72rem; font-weight: 600;
  }
  .bar { position: absolute; left: 0; right: 0; bottom: 0; height: 3px; background: rgba(255, 255, 255, 0.25); }
  .bar span { display: block; height: 100%; background: var(--m-accent); }
  .text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
  .title {
    font-weight: 600; font-size: 0.98rem;
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .meta { color: var(--m-dim); font-size: 0.84rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .mark { margin-left: 6px; color: var(--m-faint); }
  .action { display: flex; align-items: center; padding-right: 12px; }
</style>

<!--
  Hinweis anstelle des Players, wenn das Gerät ein Video nicht abspielt
  (HELF-242): sagt warum und bestellt die kompatible Fassung, mit Fortschritt.
  source: PlayableSource (lib/utils/playableSource.svelte.js)
-->
<script>
  import { formatDuration } from '../../utils/format.js';

  let { source, duration = 0 } = $props();
  let starting = $state(false);
  let error = $state('');

  let repack = $derived(source.blocked?.way === 'umpacken');
  let effort = $derived(repack ? 'dauert nur Sekunden'
    : duration ? `dauert etwa ${formatDuration(duration)}` : 'dauert etwa so lange wie das Video');

  async function start() {
    starting = true; error = '';
    try { await source.convert(); }
    catch (e) { error = e.message; }
    finally { starting = false; }
  }
</script>

{#if source.blocked}
  <div class="kompatibel">
    <i class="fa-solid fa-film symbol"></i>
    <p>Dieses Gerät spielt das Video nicht ab <span class="art">({source.blocked.label})</span>.</p>
    {#if source.job}
      <div class="balken" role="progressbar" aria-valuenow={Math.round(source.job.progress * 100)} aria-valuemin="0" aria-valuemax="100">
        <div class="fuellung" style:width="{Math.max(source.job.progress, 0.02) * 100}%"></div>
      </div>
      <p class="stand">
        {#if source.job.status === 'queued'}Wartet auf den Start ...{:else}{repack ? 'Wird umgepackt' : 'Wird umgewandelt'}, <span class="zahl">{Math.round(source.job.progress * 100)} %</span>{/if}
      </p>
      <p class="klein">Du kannst die Seite verlassen; die Fassung bleibt für alle Geräte.</p>
    {:else}
      {#if source.blocked.failed}<p class="fehler">Das Umwandeln hat nicht geklappt.</p>{/if}
      {#if error}<p class="fehler">{error}</p>{/if}
      <button class="knopf" onclick={start} disabled={starting}>
        <i class="fa-solid {starting ? 'fa-spinner fa-spin' : 'fa-wand-magic-sparkles'}"></i>
        {repack ? 'Für dieses Gerät umpacken' : 'Für dieses Gerät umwandeln'}
      </button>
      <p class="klein">Legt eine H.264-Fassung neben das Original, {effort}.</p>
    {/if}
  </div>
{/if}

<style>
  .kompatibel {
    display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--tv-a3);
    aspect-ratio: 16 / 9; width: 100%; padding: var(--tv-a5) var(--tv-a4);
    background: var(--tv-grund); color: var(--tv-text-2); text-align: center;
  }
  .symbol { font-size: 28px; color: var(--tv-text-3); }
  p { margin: 0; }
  .art { color: var(--tv-text-3); }
  .klein { font-size: 15px; color: var(--tv-text-3); }
  .stand { color: var(--tv-text); }
  .fehler { color: var(--tv-warnung); }
  .knopf {
    min-height: 48px; padding: 0 var(--tv-a5);
    display: inline-flex; align-items: center; gap: var(--tv-a2);
    border-radius: var(--tv-ecke); border: 1px solid var(--tv-akzent);
    background: var(--tv-akzent); color: var(--tv-akzent-text); font-weight: 600; font-size: inherit;
  }
  .knopf:disabled { opacity: 0.6; }
  .balken { width: min(320px, 100%); height: 8px; border-radius: 4px; background: var(--tv-flaeche); overflow: hidden; }
  .fuellung { height: 100%; background: var(--tv-akzent); transition: width 0.4s; }
</style>

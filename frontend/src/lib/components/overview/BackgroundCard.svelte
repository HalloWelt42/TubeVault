<!--
  Hintergrundarbeiten in der Übersicht: je Arbeit Stand und, wo es einen
  Schalter gibt, Fortsetzen oder Anhalten. Angehaltene Arbeiten stehen immer
  hier (Pause ist bei ihnen der Normalfall). Lädt sich selbst nach.
-->
<script>
  import { onDestroy, onMount } from 'svelte';
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';
  import { workPercent, switchWork } from '../../utils/backgroundWork.js';
  import OverviewCard from './OverviewCard.svelte';

  const REFRESH_MS = 8000;

  let items = $state(null);
  let switching = $state(null);   // key der Arbeit, deren Schalter gerade umgelegt wird
  let timer;

  async function load() {
    try { items = (await api.getBackgroundWork()).items || []; } catch { /* bleibt beim letzten Stand */ }
  }

  async function toggle(item) {
    switching = item.key;
    try {
      await switchWork(item);
      await load();
    } catch (e) { toast.error(e.message); }
    switching = null;
  }

  onMount(() => { load(); timer = setInterval(load, REFRESH_MS); });
  onDestroy(() => clearInterval(timer));
</script>

{#if items?.length}
  <OverviewCard title="Hintergrundarbeiten">
    {#each items as item (item.key)}
      <div class="arbeit" title={item.detail || ''}>
        <div class="text">
          <div class="n">{item.label}</div>
          <div class="w">
            {#if item.total}<span class="zahl">{item.done.toLocaleString('de-DE')} von {item.total.toLocaleString('de-DE')}</span> · {/if}
            {#if item.paused}angehalten{:else if workPercent(item) !== null}<span class="zahl">{workPercent(item)} %</span>{:else}läuft{/if}
          </div>
        </div>
        {#if item.switch_key}
          <button class="tv-knopf klein" class:haupt={item.paused} onclick={() => toggle(item)} disabled={switching === item.key}>
            <i class="fa-solid {switching === item.key ? 'fa-spinner fa-spin' : item.paused ? 'fa-play' : 'fa-pause'}"></i>
            {item.paused ? 'Fortsetzen' : 'Anhalten'}</button>
        {/if}
      </div>
    {/each}
  </OverviewCard>
{/if}

<style>
  .arbeit { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--tv-a2); align-items: center; padding: 6px 0; }
  .n { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .w { font-size: var(--tv-gr-klein); color: var(--tv-text-3); }
</style>

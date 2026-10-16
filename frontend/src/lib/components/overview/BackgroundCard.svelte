<!--
  Hintergrundarbeiten in der Übersicht: je Arbeit Stand und, wo es einen
  Schalter gibt, Fortsetzen oder Anhalten. Angehaltene Arbeiten stehen immer
  hier (Pause ist bei ihnen der Normalfall). Lädt sich selbst nach.
-->
<script>
  import { onMount } from 'svelte';
  import { toast } from '../../stores/notifications.js';
  import { workPercent } from '../../utils/backgroundWork.js';
  import { backgroundWork } from '../../stores/backgroundWork.svelte.js';
  import OverviewCard from './OverviewCard.svelte';


  let items = $derived(backgroundWork.items);
  let switching = $state(null);   // key der Arbeit, deren Schalter gerade umgelegt wird


  async function toggle(item) {
    switching = item.key;
    try {
      await backgroundWork.toggle(item);
    } catch (e) { toast.error(e.message); }
    switching = null;
  }

  onMount(() => backgroundWork.use());   // ein Abruf für Karte und Statusleiste
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

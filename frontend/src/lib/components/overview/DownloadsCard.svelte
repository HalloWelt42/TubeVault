<!--
  Downloads in der Übersicht: was gerade lädt (mit Fortschritt), wie viele
  warten, und die Warteschlange anhalten oder fortsetzen. Lädt sich selbst
  nach, während etwas läuft öfter.
-->
<script>
  import { onDestroy, onMount } from 'svelte';
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';
  import OverviewCard from './OverviewCard.svelte';

  const BUSY_MS = 4000;    // so oft, solange etwas lädt
  const IDLE_MS = 15000;   // sonst

  let queue = $state(null);
  let paused = $state(false);
  let switching = $state(false);
  let timer;

  let active = $derived((queue?.queue || []).filter((job) => job.status === 'active'));
  let waiting = $derived(queue?.queued_count || 0);
  let failed = $derived(queue?.error_count || 0);

  async function load() {
    clearTimeout(timer);
    try {
      const [q, status] = await Promise.all([api.getQueue(), api.getQueueStatus()]);
      queue = q;
      paused = !!status.paused;
    } catch { /* bleibt beim letzten Stand */ }
    timer = setTimeout(load, active.length ? BUSY_MS : IDLE_MS);
  }

  async function togglePause() {
    switching = true;
    try {
      if (paused) await api.resumeQueue();
      else await api.pauseQueue();
      await load();
    } catch (e) { toast.error(e.message); }
    switching = false;
  }

  onMount(load);
  onDestroy(() => clearTimeout(timer));
</script>

<OverviewCard title="Downloads" more={{ label: 'Öffnen', path: '/downloads' }}>
  {#snippet extra()}
    {#if paused}<span class="tv-zustand warnung"><i class="fa-solid fa-pause"></i> angehalten</span>{/if}
  {/snippet}

  {#if queue}
    {#each active as job (job.id)}
      <div class="job">
        <div class="zeile">
          <span class="t">{job.title || job.video_id}</span>
          <span class="zahl tv-leise">{Math.round((job.progress || 0) * 100)} %</span>
        </div>
        <div class="balken"><b style:width="{Math.round((job.progress || 0) * 100)}%"></b></div>
      </div>
    {/each}

    <div class="fuss">
      <span class="tv-leise">
        {#if waiting || active.length}<span class="zahl">{waiting.toLocaleString('de-DE')}</span> warten{:else}Nichts in Arbeit{/if}
        {#if failed} · <span class="fehler"><span class="zahl">{failed}</span> mit Fehler</span>{/if}
      </span>
      {#if waiting || active.length || paused}
        <button class="tv-knopf klein" class:haupt={paused} onclick={togglePause} disabled={switching}
                title={paused ? 'Warteschlange wieder abarbeiten' : 'Laufenden Download anhalten, nichts Neues beginnen'}>
          <i class="fa-solid {switching ? 'fa-spinner fa-spin' : paused ? 'fa-play' : 'fa-pause'}"></i>
          {paused ? 'Fortsetzen' : 'Anhalten'}</button>
      {/if}
    </div>
  {/if}
</OverviewCard>

<style>
  .job + .job { margin-top: var(--tv-a3); }
  .zeile { display: flex; justify-content: space-between; gap: var(--tv-a2); }
  .t { min-width: 0; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .balken { position: relative; height: 6px; margin-top: 6px; border-radius: var(--tv-ecke-klein); background: var(--tv-karte-3); overflow: hidden; }
  .balken b { position: absolute; left: 0; top: 0; bottom: 0; background: var(--tv-akzent); transition: width 0.4s; }
  .fuss { display: flex; align-items: center; justify-content: space-between; gap: var(--tv-a2); margin-top: var(--tv-a3); font-size: var(--tv-gr-klein); }
  .fuss:first-child { margin-top: 0; }
  .fehler { color: var(--tv-gefahr); }
</style>

<!--
  Reiter "Aufträge" im Live-Log (Entwurf mockups/werkzeuge.html): laufende
  und wartende Aufträge mit Fortschritt und Abbrechen, Warteschlange
  anhalten oder fortsetzen, Dienste im Hintergrund an- und abschalten.
  Fragt nur, solange der Reiter offen ist.
-->
<script>
  import { onMount } from 'svelte';
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';

  let { onsummary = () => {} } = $props();

  const POLL_MS = 2000;
  const JOB_ICONS = { download: 'fa-download', channel_scan: 'fa-satellite-dish', scan: 'fa-magnifying-glass', playlist_fetch: 'fa-list-ul' };

  let jobs = $state([]);
  let stats = $state(null);
  let tasks = $state([]);
  let busy = $state(false);

  async function load() {
    try {
      [jobs, stats, tasks] = await Promise.all([api.getActiveJobs(), api.getJobStats(), api.getTasks()]);
      onsummary({ active: stats.active || 0, queued: stats.queued || 0 });
    } catch { /* nächster Versuch beim nächsten Takt */ }
  }

  async function act(run) {
    busy = true;
    try { await run(); await load(); } catch (e) { toast.error(e.message); }
    busy = false;
  }

  const cancel = (job) => act(() => api.cancelJob(job.id));
  const toggleQueue = () => act(() => (stats?.paused ? api.resumeQueue() : api.pauseQueue()));
  const toggleTask = (task) => act(() => api.setTaskRunning(task.name, task.status !== 'running'));

  let running = $derived(jobs.filter((job) => job.status === 'active'));
  let waiting = $derived(jobs.filter((job) => job.status !== 'active'));

  onMount(() => {
    load();
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  });
</script>

<div class="auftraege">
  {#each running as job (job.id)}
    <div class="auftrag">
      <i class="fa-solid {JOB_ICONS[job.type] || 'fa-gear'} art"></i>
      <span class="titel">{job.title || job.type}</span>
      <span class="tv-zustand laeuft">läuft</span>
      <button class="tv-knopf ohne symbol klein" onclick={() => cancel(job)} disabled={busy} title="Abbrechen" aria-label="Abbrechen">
        <i class="fa-solid fa-xmark"></i></button>
      {#if job.progress > 0}<div class="balken"><b style:width="{Math.round(job.progress * 100)}%"></b></div>{/if}
      {#if job.description || job.progress > 0}
        <div class="info">{#if job.progress > 0}<span class="zahl">{Math.round(job.progress * 100)} %</span>{job.description ? ' · ' : ''}{/if}{job.description || ''}</div>
      {/if}
    </div>
  {/each}

  <div class="auftrag">
    <i class="fa-solid fa-clock art warte"></i>
    <span class="titel">
      {#if waiting.length}<span class="zahl">{waiting.length}</span> {waiting.length === 1 ? 'Auftrag wartet' : 'Aufträge warten'}{:else}Nichts wartet{/if}
      {#if stats?.paused} · Warteschlange angehalten{/if}
    </span>
    <span></span>
    {#if stats}
      <button class="tv-knopf ohne klein" onclick={toggleQueue} disabled={busy}>
        <i class="fa-solid {stats.paused ? 'fa-play' : 'fa-pause'}"></i> {stats.paused ? 'Warteschlange fortsetzen' : 'Warteschlange anhalten'}</button>
    {/if}
  </div>

  {#if tasks.length}
    <div class="tv-etikett gruppe">Dienste im Hintergrund</div>
    {#each tasks as task (task.name)}
      {@const on = task.status === 'running'}
      <div class="dienst">
        <span class="punkt" class:aus={!on} class:fehler={task.status === 'crashed'}></span>
        <span class="name">{task.label}</span>
        <span class="tv-schwach">{on ? 'läuft' : task.status === 'crashed' ? 'abgestürzt' : 'angehalten'}</span>
        <button class="tv-knopf ohne symbol klein" onclick={() => toggleTask(task)} disabled={busy}
                title={on ? 'Anhalten' : 'Starten'} aria-label={on ? 'Anhalten' : 'Starten'}>
          <i class="fa-solid {on ? 'fa-stop' : 'fa-play'}"></i></button>
      </div>
    {/each}
  {/if}
</div>

<style>
  .auftraege { flex: 1; min-height: 0; overflow-y: auto; padding: var(--tv-a1) 0; font-size: var(--tv-gr-klein); }
  .auftrag { display: grid; grid-template-columns: 22px minmax(0, 1fr) auto auto; gap: var(--tv-a1) var(--tv-a3); align-items: center;
             padding: var(--tv-a2) var(--tv-a4); }
  .titel { font-size: var(--tv-gr-text); overflow-wrap: anywhere; }
  .art { color: var(--tv-akzent); }
  .art.warte { color: var(--tv-info); }
  .balken { grid-column: 2 / -1; height: 5px; background: var(--tv-mulde); border-radius: 1px; overflow: hidden; }
  .balken b { display: block; height: 100%; background: var(--tv-akzent); }
  .info { grid-column: 2 / -1; color: var(--tv-text-3); }
  .gruppe { padding: var(--tv-a3) var(--tv-a4) var(--tv-a1); }
  .dienst { display: flex; align-items: center; gap: var(--tv-a3); padding: 4px var(--tv-a4); }
  .punkt { width: 9px; height: 9px; flex: none; border-radius: 50%; background: var(--tv-erfolg); }
  .punkt.aus { background: var(--tv-text-3); }
  .punkt.fehler { background: var(--tv-gefahr); }
  .name { flex: 1; min-width: 0; }
</style>

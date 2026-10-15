<!--
  Zustand der Dienste in Worten, Erklärung beim Überfahren: Quelle (mit
  Bremse aufheben bzw. wieder einschalten), Kanalprüfung, Bewertungsdienst.
  Steht in der Übersicht; die Fußleiste bleibt frei für die Spielerleiste.
-->
<script>
  import { onDestroy, onMount } from 'svelte';
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';

  const REFRESH_MS = 20000;

  let status = $state(null);
  let timer;

  async function load() {
    try { status = await api.getStatus(); } catch { status = null; }
  }

  onMount(() => { load(); timer = setInterval(load, REFRESH_MS); });
  onDestroy(() => clearInterval(timer));

  let source = $derived(status?.services?.youtube || {});
  let throttled = $derived(!!status?.rate_limiter_warning
    || (status?.cooldown?.cooldown ?? 0) > (status?.cooldown?.cooldown_base ?? Infinity));
  let rssRunning = $derived(status?.services?.rss?.running ?? status?.rss?.worker_running ?? false);
  let rydOk = $derived(status?.services?.ryd?.ok ?? false);

  async function releaseBrake() {
    try {
      await api.resetRateLimit();
      toast.success('Bremse aufgehoben');
      await load();
    } catch (e) { toast.error(e.message); }
  }

  // Die Bremse lässt sich hier nur wieder einschalten; Ausschalten führte nur
  // zu schnelleren Sperren durch die Quelle.
  async function enableBrake() {
    try {
      await api.toggleRateLimit();
      await load();
    } catch (e) { toast.error(e.message); }
  }
</script>

{#if !status}
  <span class="dienste"><span class="dienst" title="Server nicht erreichbar"><span class="led err"></span> Server?</span></span>
{:else}
  <span class="dienste">
    {#if source.bot_detected}
      <span class="dienst" title="Die Quelle hält uns für einen Automaten und sperrt; eine Stunde Pause, dann geht es weiter.">
        <span class="led sperre"></span> Quelle gesperrt</span>
    {:else if source.ok === false}
      <span class="dienst" title="Abrufe bei der Quelle scheitern gerade{source.block_count ? ` (${source.block_count} Sperren)` : ''}.">
        <span class="led err"></span> Quelle blockiert</span>
    {:else if throttled}
      <span class="dienst" title="Die Quelle hat gebremst; Abrufe laufen vorerst in größerem Abstand.">
        <span class="led warn"></span> Quelle gebremst</span>
      <button class="knopf" onclick={releaseBrake} title="Bremse aufheben: wieder im normalen Abstand abrufen">
        <i class="fa-solid fa-rotate-right"></i></button>
    {:else}
      <span class="dienst" title="Abrufe bei der Quelle laufen normal."><span class="led ok"></span> Quelle</span>
    {/if}
    {#if status.rate_limiter_disabled}
      <span class="dienst" title="Die Abstände zwischen Abrufen sind ausgeschaltet. Die Quelle sperrt dann schneller.">
        <span class="led warn"></span> ohne Bremse</span>
      <button class="knopf" onclick={enableBrake} title="Abstände zwischen Abrufen wieder einschalten">
        <i class="fa-solid fa-toggle-off"></i></button>
    {/if}
    <span class="dienst" title={rssRunning ? 'Kanäle werden regelmäßig auf neue Videos geprüft.' : 'Die Kanalprüfung ist ausgeschaltet (Einstellungen).'}>
      <span class="led" class:ok={rssRunning} class:aus={!rssRunning}></span> Kanalprüfung</span>
    <span class="dienst" title={rydOk ? 'Der Dienst für Mag-ich- und Mag-ich-nicht-Zahlen ist erreichbar.' : 'Der Dienst für Mag-ich-Zahlen ist nicht erreichbar; neue Videos bekommen vorerst keine.'}>
      <span class="led" class:ok={rydOk} class:aus={!rydOk}></span> Bewertungen</span>
  </span>
{/if}

<style>
  .dienste { display: inline-flex; align-items: center; gap: var(--tv-a3); flex-wrap: wrap; }
  .dienst { display: inline-flex; align-items: center; gap: 6px; height: 34px; padding: 0 var(--tv-a3); border-radius: var(--tv-ecke);
            background: var(--tv-karte); color: var(--tv-text-2); font-size: var(--tv-gr-klein); white-space: nowrap; }
  .led { width: 9px; height: 9px; border-radius: 50%; flex: none; }
  .led.ok { background: var(--tv-erfolg); }
  .led.warn { background: var(--tv-warnung); }
  .led.err { background: var(--tv-gefahr); }
  .led.sperre { background: var(--tv-warnung); animation: puls 1.5s ease-in-out infinite; }
  .led.aus { background: var(--tv-text-3); opacity: 0.5; }
  @keyframes puls { 50% { opacity: 0.35; } }
  .knopf { width: 34px; height: 34px; border: 0; border-radius: var(--tv-ecke); background: var(--tv-karte); color: var(--tv-text-2); cursor: pointer; }
  .knopf:hover { color: var(--tv-text); background: var(--tv-karte-2); }
</style>

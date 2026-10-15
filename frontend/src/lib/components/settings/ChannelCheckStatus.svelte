<!--
  Stand der Kanalprüfung (Einstellungen, Abschnitt Kanäle): läuft sie, was
  wurde zuletzt geprüft, wie oft wird geprüft. Einzelheiten aufklappbar.
-->
<script>
  import { formatDateRelative } from '../../utils/format.js';

  let { scheduler } = $props();

  const DAY = 86400;
  // Verteilung der Prüfabstände in vier verständlichen Stufen
  let buckets = $derived.by(() => {
    const steps = [
      { label: '2x täglich oder öfter', test: (s) => s < DAY },
      { label: 'alle 1 bis 7 Tage', test: (s) => s < 8 * DAY },
      { label: 'alle 8 bis 29 Tage', test: (s) => s < 30 * DAY },
      { label: 'monatlich', test: () => true },
    ];
    const counts = steps.map(() => 0);
    for (const d of scheduler?.interval_distribution || []) {
      counts[steps.findIndex(step => step.test(d.interval))] += d.count;
    }
    const total = counts.reduce((a, b) => a + b, 0) || 1;
    return steps.map((step, i) => ({ label: step.label, count: counts[i], share: counts[i] / total }));
  });
  let running = $derived(scheduler?.running && scheduler?.rss_enabled);
  const days = (seconds) => seconds >= DAY ? `${Math.round(seconds / DAY)} Tage` : `${Math.round(seconds / 3600)} Std.`;
</script>

{#if scheduler}
  <div class="stand">
    <div class="kopf">
      <span class="tv-zustand {running ? 'laeuft' : ''}"><i class="fa-solid {running ? 'fa-clock' : 'fa-circle-pause'}"></i> {running ? 'Prüfung läuft' : 'Prüfung steht'}</span>
      <span class="tv-leise tv-klein">zuletzt {scheduler.last_checked_channel || '-'} {scheduler.last_checked_at ? formatDateRelative(scheduler.last_checked_at) : ''}</span>
      <span class="tv-leise tv-klein zahl">{scheduler.feeds_pending} fällig</span>
    </div>

    <div class="verteilung">
      <span class="tv-etikett ganz">So oft wird gerade geprüft</span>
      {#each buckets as b}
        <span>{b.label}</span>
        <div class="balken"><b style:width="{(b.share * 100).toFixed(1)}%"></b></div>
        <span class="zahl">{b.count} Kanäle</span>
      {/each}
    </div>

    <details class="mehr">
      <summary>Einzelheiten</summary>
      <div class="zahlen tv-klein">
        <span class="zahl">{scheduler.subscriptions.total} Abos</span>
        <span class="zahl">{scheduler.subscriptions.enabled} aktiv</span>
        {#if scheduler.subscriptions.unchecked}<span class="zahl">{scheduler.subscriptions.unchecked} noch nie geprüft</span>{/if}
        {#if scheduler.subscriptions.disabled}<span class="zahl">{scheduler.subscriptions.disabled} abgeschaltet</span>{/if}
        <span class="zahl">{scheduler.entries.total.toLocaleString('de-DE')} Feed-Einträge</span>
        {#if scheduler.auto_download.enabled}
          <span class="zahl">Auto-Download bei {scheduler.auto_download.channels} Kanälen,
            heute {scheduler.auto_download.today_count}{Number(scheduler.auto_download.daily_limit) > 0 ? ` von ${scheduler.auto_download.daily_limit}` : ''}</span>
        {/if}
      </div>
      {#if scheduler.upcoming?.length}
        <div class="tv-etikett liste-titel">Als Nächstes</div>
        {#each scheduler.upcoming as u}
          <div class="zeile tv-klein"><span>{u.channel_name || u.channel_id}</span><span class="zahl tv-schwach">alle {days(u.check_interval)}</span></div>
        {/each}
      {/if}
      {#if scheduler.recent_errors?.length}
        <div class="tv-etikett liste-titel">Kanäle mit Fehlern</div>
        {#each scheduler.recent_errors as e}
          <div class="zeile tv-klein"><span>{e.channel_name} <span class="zahl tv-schwach">{e.error_count}x</span></span>
            <span class="tv-schwach fehler" title={e.last_error}>{(e.last_error || '').slice(0, 80)}</span></div>
        {/each}
      {/if}
    </details>
  </div>
{/if}

<style>
  .stand { padding: var(--tv-a3) var(--tv-a4) var(--tv-a4); border-top: 1px solid var(--tv-rand); }
  .kopf { display: flex; gap: var(--tv-a3); align-items: center; flex-wrap: wrap; }
  .verteilung { display: grid; grid-template-columns: 200px 1fr 100px; gap: 6px var(--tv-a3); align-items: center; font-size: var(--tv-gr-klein); margin-top: var(--tv-a3); }
  .verteilung .ganz { grid-column: 1 / -1; }
  .verteilung .zahl { text-align: right; }
  .balken { height: 8px; background: var(--tv-mulde); border-radius: 1px; overflow: hidden; }
  .balken b { display: block; height: 100%; background: var(--tv-akzent); }
  .mehr { margin-top: var(--tv-a3); }
  .mehr summary { cursor: pointer; color: var(--tv-text-2); font-size: var(--tv-gr-klein); }
  .zahlen { display: flex; gap: var(--tv-a3); flex-wrap: wrap; margin: var(--tv-a2) 0; color: var(--tv-text-2); }
  .liste-titel { display: block; margin: var(--tv-a3) 0 var(--tv-a1); }
  .zeile { display: flex; justify-content: space-between; gap: var(--tv-a3); padding: 3px 0; }
  .fehler { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 60%; }
</style>

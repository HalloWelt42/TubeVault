<!--
  Wiederherstellen (Einstellungen > System, Entwurf mockups/werkzeuge.html):
  Nutzerdaten sichern und zurückspielen, die Datenbank aus den
  Begleitdateien neu aufbauen (mit Probelauf), dazu der Stand der
  Inhaltsdateien. Vorher lag das in der Verwaltung.
-->
<script>
  import { onDestroy, onMount } from 'svelte';
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';

  let { confirm } = $props();      // Rückfrage über den ConfirmDialog der Seite

  const POLL_MS = 2000;

  let status = $state(null);
  let busy = $state('');
  let timer = null;

  let latest = $derived(status?.userdata_exports?.[0] || null);
  let rebuild = $derived(status?.rebuild || null);

  async function load() {
    try {
      status = await api.restoreStatus();
      clearTimeout(timer);
      if (status.rebuild?.running) timer = setTimeout(load, POLL_MS);   // Fortschritt live
    } catch (e) { toast.error(e.message); }
  }

  const when = (iso) => (iso ? new Date(iso).toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' }) : '');
  const num = (value) => Number(value || 0).toLocaleString('de-DE');

  async function run(label, action, done) {
    busy = label;
    try { const result = await action(); if (done) toast.success(done(result)); await load(); }
    catch (e) { toast.error(e.message); }
    busy = '';
  }

  const exportNow = () => run('sichern', () => api.restoreUserdataExport(), () => 'Nutzerdaten gesichert');

  async function restoreLatest() {
    if (!latest) return;
    const ok = await confirm('Nutzerdaten zurückspielen?',
      `Spielt die Sicherung vom ${when(latest.created_at)} zurück. Vorhandene Einträge und frischere Werte bleiben unangetastet, Fehlendes kommt dazu.`,
      { confirmLabel: 'Zurückspielen', danger: false });
    if (!ok) return;
    run('zurück', () => api.restoreUserdata(latest.folder), (result) => {
      const parts = Object.entries(result.tables || {}).map(([table, v]) => [table, v.inserted ?? v.updated ?? 0]).filter(([, n]) => n);
      return parts.length ? `Zurückgespielt: ${parts.map(([t, n]) => `${t} ${num(n)}`).join(', ')}` : 'Nichts zu tun, alles war schon da';
    });
  }

  async function startRebuild(dryRun) {
    if (!dryRun) {
      const ok = await confirm('Datenbank aus den Begleitdateien neu aufbauen?',
        'Legt fehlende Einträge aus den info.json neben den Videos neu an. Bestehende Einträge werden nie überschrieben.',
        { confirmLabel: 'Neu aufbauen' });
      if (!ok) return;
    }
    run('aufbau', () => api.restoreRebuild(dryRun), () => (dryRun ? 'Probelauf gestartet' : 'Wiederaufbau gestartet'));
  }

  onMount(load);
  onDestroy(() => clearTimeout(timer));
</script>

<section class="tv-karte">
  <h3><i class="fa-solid fa-life-ring"></i> Wiederherstellen</h3>
  {#if status}
    <div class="zeile">
      <div class="text">Nutzerdaten sichern
        <div class="e">Favoriten, Verlauf, Playlists und Notizen als Datei; täglich von selbst, die letzten 14 Stände bleiben.
          {#if latest}Zuletzt <span class="zahl">{when(latest.created_at)}</span>.{/if}</div></div>
      <button class="tv-knopf ohne klein" onclick={exportNow} disabled={!!busy}>
        <i class="fa-solid {busy === 'sichern' ? 'fa-spinner fa-spin' : 'fa-plus'}"></i> Jetzt sichern</button>
    </div>
    <div class="zeile">
      <div class="text">Nutzerdaten zurückspielen
        <div class="e">{#if latest}Neueste Sicherung vom <span class="zahl">{when(latest.created_at)}</span>; Vorhandenes bleibt, Fehlendes kommt dazu.{:else}Noch keine Sicherung vorhanden.{/if}</div></div>
      <button class="tv-knopf klein" onclick={restoreLatest} disabled={!latest || !!busy}>
        <i class="fa-solid {busy === 'zurück' ? 'fa-spinner fa-spin' : 'fa-clock-rotate-left'}"></i> Zurückspielen</button>
    </div>
    <div class="zeile">
      <div class="text">Datenbank aus den Begleitdateien neu aufbauen
        <div class="e">Für den Notfall: liest neben jedem Video info.json, Beschreibung und Kapitel. Der Probelauf zeigt nur, was er täte.</div>
        <div class="e stand">
          {#if status.content_files_missing}
            <i class="fa-solid fa-spinner fa-spin"></i> <span class="zahl">{num(status.content_files_missing)}</span> Inhaltsdateien werden noch im Hintergrund geschrieben
          {:else}
            <i class="fa-solid fa-circle-check gut"></i> Alle Inhalte liegen als Datei neben den Videos
          {/if}
        </div>
        {#if rebuild && (rebuild.running || rebuild.done)}
          <div class="e stand">
            {rebuild.running ? (rebuild.dry_run ? 'Probelauf läuft' : 'Wiederaufbau läuft') : (rebuild.dry_run ? 'Letzter Probelauf' : 'Letzter Wiederaufbau')}:
            <span class="zahl">{num(rebuild.done)}</span> von <span class="zahl">{num(rebuild.total)}</span> Ordnern,
            <span class="zahl">{num(rebuild.restored)}</span> {rebuild.dry_run ? 'würden angelegt' : 'angelegt'},
            <span class="zahl">{num(rebuild.existing)}</span> schon vorhanden{#if rebuild.invalid}, <span class="zahl">{num(rebuild.invalid)}</span> ohne gültige Begleitdatei{/if}{#if rebuild.no_media}, <span class="zahl">{num(rebuild.no_media)}</span> ohne Videodatei{/if}
          </div>
        {/if}
      </div>
      <div class="tun">
        <button class="tv-knopf klein" onclick={() => startRebuild(true)} disabled={!!busy || rebuild?.running}>
          <i class="fa-solid fa-flask"></i> Probelauf</button>
        <button class="tv-knopf klein gefahr" onclick={() => startRebuild(false)} disabled={!!busy || rebuild?.running}>
          <i class="fa-solid fa-rotate"></i> Neu aufbauen</button>
      </div>
    </div>
  {:else}
    <p class="tv-schwach tv-klein"><i class="fa-solid fa-spinner fa-spin"></i> Lädt ...</p>
  {/if}
</section>

<style>
  .zeile { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--tv-a4); align-items: center; padding: var(--tv-a3) 0;
           border-top: 1px solid var(--tv-rand); }
  .zeile:first-of-type { border-top: 0; }
  .e { font-size: var(--tv-gr-klein); color: var(--tv-text-3); }
  .stand { margin-top: var(--tv-a1); color: var(--tv-text-2); }
  .gut { color: var(--tv-erfolg); }
  .tun { display: flex; gap: var(--tv-a2); flex-wrap: wrap; justify-content: flex-end; }

  @media (max-width: 700px) {
    .zeile { grid-template-columns: 1fr; }
    .tun { justify-content: flex-start; }
  }
</style>

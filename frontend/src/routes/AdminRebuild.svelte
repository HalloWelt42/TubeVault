<!--
  TubeVault – AdminRebuild v1.0.0
  Meta-Redundanz-Cockpit: Sidecar-Abdeckung (info.json neben den Videos),
  Nutzerdaten-Exporte (JSONL, täglich) und der Offline-Wiederaufbau der DB.
  © HalloWelt42 – Private Nutzung
-->
<script>
  import { onDestroy } from 'svelte';
  import { api } from '../lib/api/client.js';
  import { toast } from '../lib/stores/notifications.js';
  import ConfirmDialog from '../lib/components/common/ConfirmDialog.svelte';

  let confirmRef;
  let status = $state(null);
  let loading = $state(true);
  let busy = $state(false);
  let pollTimer = null;

  async function load(showSpinner = false) {
    if (showSpinner) loading = true;
    try {
      status = await api.adminRedundancyStatus();
      // Solange Backfill/Rebuild läuft: Fortschritt live nachladen
      const running = status?.sidecars?.backfill?.running || status?.rebuild?.running;
      clearTimeout(pollTimer);
      if (running) pollTimer = setTimeout(() => load(), 2000);
    } catch (e) { toast.error(e.message); }
    finally { loading = false; }
  }

  async function startBackfill() {
    if (!await confirmRef.ask('Sidecar-Backfill starten?',
      `Schreibt info.json neben alle ${status?.sidecars?.videos_ready ?? '?'} Videos (gedrosselt, unveränderte werden übersprungen).`,
      { confirmLabel: 'Starten' })) return;
    busy = true;
    try { await api.adminSidecarBackfill(); toast.success('Backfill gestartet'); await load(); }
    catch (e) { toast.error(e.message); }
    busy = false;
  }

  async function exportNow() {
    busy = true;
    try {
      const r = await api.adminUserdataExport();
      toast.success(`Nutzerdaten exportiert: ${r.folder}`);
      await load();
    } catch (e) { toast.error(e.message); }
    busy = false;
  }

  async function restoreLatest() {
    const latest = status?.userdata_exports?.[0];
    if (!latest) return;
    if (!await confirmRef.ask('Nutzerdaten zurückspielen?',
      `Spielt „${latest.folder}" zurück. Vorhandene Einträge und frischere Werte bleiben unangetastet.`,
      { confirmLabel: 'Zurückspielen' })) return;
    busy = true;
    try {
      const r = await api.adminUserdataRestore(latest.folder);
      const parts = Object.entries(r.tables || {})
        .map(([t, v]) => `${t}: ${v.inserted ?? v.updated ?? 0}`)
        .filter(s => !s.endsWith(': 0'));
      toast.success(parts.length ? `Zurückgespielt – ${parts.join(', ')}` : 'Nichts zu tun – alles vorhanden');
    } catch (e) { toast.error(e.message); }
    busy = false;
  }

  async function startRebuild(dryRun) {
    if (!dryRun && !await confirmRef.ask('Offline-Wiederaufbau starten?',
      'Legt fehlende Datenbank-Einträge aus den info.json-Sidecars neu an. Bestehende Einträge werden nie überschrieben.',
      { confirmLabel: 'Wiederaufbau starten' })) return;
    busy = true;
    try {
      await api.adminRebuildStart(dryRun);
      toast.success(dryRun ? 'Probelauf gestartet' : 'Wiederaufbau gestartet');
      await load();
    } catch (e) { toast.error(e.message); }
    busy = false;
  }

  function pct(part, total) {
    return total > 0 ? Math.round((part / total) * 100) : 0;
  }
  function fmtCounts(counts) {
    const sum = Object.values(counts || {}).reduce((a, b) => a + b, 0);
    return `${sum} Einträge`;
  }

  $effect(() => { load(true); });
  onDestroy(() => clearTimeout(pollTimer));

  let sc = $derived(status?.sidecars);
  let bf = $derived(status?.sidecars?.backfill);
  let rb = $derived(status?.rebuild);
</script>

<div class="page">
  <header class="head">
    <div>
      <h1><i class="fa-solid fa-life-ring"></i> Wiederaufbau</h1>
      <p class="subtitle">Meta-Redundanz neben den Videos – die Datenbank lässt sich komplett offline aus Dateien wiederherstellen.</p>
    </div>
    <button class="btn" onclick={() => load(true)} disabled={loading}>
      <i class="fa-solid fa-arrows-rotate" class:fa-spin={loading}></i> Aktualisieren
    </button>
  </header>

  {#if loading && !status}
    <div class="empty">Lade Status…</div>
  {:else if status}
    <!-- ── 1) Sidecars ── -->
    <section class="card">
      <div class="card-head">
        <h2><i class="fa-solid fa-file-circle-check"></i> Meta-Sidecars (info.json)</h2>
        <span class="hint">{status.videos_root}</span>
      </div>
      <p class="desc">Neben jedem Video liegt eine <code>info.json</code> mit Titel, Kanal, Tags &amp; Co.
        Sie wird bei Download, Import und jeder Änderung automatisch aktuell gehalten.</p>
      <div class="progress-row">
        <div class="bar"><div class="fill" style="width:{pct(sc?.sidecars_present, sc?.videos_ready)}%"></div></div>
        <span class="bar-label">{sc?.sidecars_present ?? 0} / {sc?.videos_ready ?? 0} Videos versorgt
          {#if sc?.sidecars_missing > 0}· <b class="warn">{sc.sidecars_missing} fehlen</b>{/if}
        </span>
      </div>
      {#if bf?.running}
        <div class="running"><i class="fa-solid fa-spinner fa-spin"></i>
          Backfill läuft: {bf.done} / {bf.total} · {bf.written} geschrieben · {bf.skipped} übersprungen
          {#if bf.errors > 0}· <span class="warn">{bf.errors} Fehler</span>{/if}
        </div>
      {:else}
        <div class="actions">
          <button class="btn btn-primary" onclick={startBackfill} disabled={busy || sc?.sidecars_missing === 0}>
            <i class="fa-solid fa-wand-magic-sparkles"></i>
            {sc?.sidecars_missing === 0 ? 'Alle Videos versorgt' : `Backfill starten (${sc?.sidecars_missing ?? '?'} fehlend)`}
          </button>
        </div>
      {/if}
    </section>

    <!-- ── 2) Nutzerdaten ── -->
    <section class="card">
      <div class="card-head">
        <h2><i class="fa-solid fa-user-shield"></i> Nutzerdaten-Exporte</h2>
        <span class="hint">{status.userdata_root}</span>
      </div>
      <p class="desc">Favoriten, Verlauf, Playlists, Kategorien, Abos, Bewertungen – alles, was nicht
        in den Sidecars steckt. Läuft täglich automatisch, die letzten 14 Stände bleiben erhalten.</p>
      {#if status.userdata_exports?.length > 0}
        <div class="export-list">
          {#each status.userdata_exports.slice(0, 5) as ex}
            <div class="export-row">
              <i class="fa-solid fa-box-archive"></i>
              <span class="export-name">{ex.folder}</span>
              <span class="export-meta">{ex.created_at || ''} · {fmtCounts(ex.counts)}</span>
            </div>
          {/each}
        </div>
      {:else}
        <div class="empty-inline">Noch kein Export vorhanden – der erste läuft automatisch, oder jetzt manuell.</div>
      {/if}
      <div class="actions">
        <button class="btn btn-primary" onclick={exportNow} disabled={busy}>
          <i class="fa-solid fa-download"></i> Jetzt exportieren
        </button>
        <button class="btn" onclick={restoreLatest} disabled={busy || !status.userdata_exports?.length}>
          <i class="fa-solid fa-clock-rotate-left"></i> Neuesten Export zurückspielen
        </button>
      </div>
    </section>

    <!-- ── 3) Offline-Wiederaufbau ── -->
    <section class="card">
      <div class="card-head">
        <h2><i class="fa-solid fa-hammer"></i> Offline-Wiederaufbau</h2>
      </div>
      <p class="desc">Der Notfall-Weg: Geht die Datenbank verloren, werden fehlende Einträge aus den
        Sidecars neu aufgebaut (Videodatei wird im Ordner gefunden, Beschreibung kommt aus dem Textarchiv).
        Bestehende Einträge werden <b>nie</b> überschrieben – der Probelauf zählt nur.</p>
      {#if rb?.running}
        <div class="running"><i class="fa-solid fa-spinner fa-spin"></i>
          {rb.dry_run ? 'Probelauf' : 'Wiederaufbau'} läuft: {rb.done} / {rb.total} Ordner
          · {rb.restored} {rb.dry_run ? 'wiederherstellbar' : 'wiederhergestellt'}
          · {rb.existing} vorhanden
        </div>
      {:else}
        {#if rb?.total > 0}
          <div class="result">Letzter Lauf{rb.dry_run ? ' (Probelauf)' : ''}:
            {rb.restored} {rb.dry_run ? 'wiederherstellbar' : 'wiederhergestellt'},
            {rb.existing} bereits vorhanden, {rb.invalid} ohne gültiges Sidecar,
            {rb.no_media} ohne Mediendatei</div>
        {/if}
        <div class="actions">
          <button class="btn" onclick={() => startRebuild(true)} disabled={busy}>
            <i class="fa-solid fa-flask"></i> Probelauf (zählt nur)
          </button>
          <button class="btn btn-danger" onclick={() => startRebuild(false)} disabled={busy}>
            <i class="fa-solid fa-hammer"></i> Wiederaufbau starten
          </button>
        </div>
      {/if}
    </section>
  {/if}
</div>

<ConfirmDialog bind:this={confirmRef} />

<style>
  .page { padding: 32px 40px; width: 100%; }
  .head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
  .head h1 { font-size: 1.5rem; font-weight: 700; color: var(--text-primary); margin: 0 0 4px; display: flex; align-items: center; gap: 10px; }
  .head h1 i { color: var(--accent-primary); }
  .subtitle { color: var(--text-tertiary); font-size: 0.86rem; margin: 0; }

  .card { background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 12px; padding: 18px 20px; margin-bottom: 16px; }
  .card-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 6px; }
  .card-head h2 { font-size: 1.02rem; font-weight: 600; color: var(--text-primary); margin: 0; display: flex; align-items: center; gap: 8px; }
  .card-head h2 i { color: var(--accent-primary); font-size: 0.9rem; }
  .hint { font-size: 0.7rem; color: var(--text-tertiary); font-family: monospace; }
  .desc { font-size: 0.82rem; color: var(--text-secondary); margin: 0 0 14px; line-height: 1.5; }
  .desc code { background: var(--bg-tertiary); padding: 1px 5px; border-radius: 4px; font-size: 0.76rem; }

  .progress-row { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
  .bar { flex: 1; height: 8px; background: var(--bg-tertiary); border-radius: 4px; overflow: hidden; }
  .fill { height: 100%; background: var(--status-success); border-radius: 4px; transition: width 0.4s; }
  .bar-label { font-size: 0.78rem; color: var(--text-secondary); white-space: nowrap; }
  .warn { color: var(--status-warning); }

  .running { display: flex; align-items: center; gap: 8px; font-size: 0.82rem; color: var(--accent-primary); padding: 8px 0; }
  .result { font-size: 0.78rem; color: var(--text-tertiary); margin-bottom: 10px; }

  .actions { display: flex; gap: 8px; flex-wrap: wrap; }
  .btn { display: inline-flex; align-items: center; gap: 7px; padding: 8px 14px; border-radius: 8px; font-size: 0.82rem; cursor: pointer; background: var(--bg-tertiary); border: 1px solid var(--border-primary); color: var(--text-primary); transition: all 0.15s; }
  .btn:hover:not(:disabled) { border-color: var(--accent-primary); }
  .btn:disabled { opacity: 0.45; cursor: default; }
  .btn-primary { background: var(--accent-primary); border-color: var(--accent-primary); color: #fff; }
  .btn-primary:hover:not(:disabled) { filter: brightness(1.1); }
  .btn-danger { border-color: var(--status-error); color: var(--status-error); }
  .btn-danger:hover:not(:disabled) { background: color-mix(in srgb, var(--status-error) 12%, transparent); }

  .export-list { display: flex; flex-direction: column; gap: 4px; margin-bottom: 14px; }
  .export-row { display: flex; align-items: center; gap: 10px; font-size: 0.8rem; color: var(--text-secondary); padding: 5px 8px; background: var(--bg-tertiary); border-radius: 6px; }
  .export-row i { color: var(--text-tertiary); font-size: 0.75rem; }
  .export-name { font-family: monospace; font-size: 0.75rem; color: var(--text-primary); }
  .export-meta { margin-left: auto; font-size: 0.72rem; color: var(--text-tertiary); }

  .empty { text-align: center; color: var(--text-tertiary); padding: 60px 0; }
  .empty-inline { font-size: 0.8rem; color: var(--text-tertiary); margin-bottom: 12px; }
</style>

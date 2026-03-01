<!--
  TubeVault
  © HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
  SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
-->
<script>
  import { api } from '../lib/api/client.js';
  import { toast } from '../lib/stores/notifications.js';
  import { formatSize } from '../lib/utils/format.js';

  let stats = $state(null);
  let storage = $state(null);
  let exports = $state([]);
  let loading = $state(true);
  let backingUp = $state(false);
  let exporting = $state({});
  let cleaningTemp = $state(false);

  async function load() {
    loading = true;
    try {
      const [s, st, ex] = await Promise.all([
        api.getStats(),
        api.getStorage(),
        api.getExports(),
      ]);
      stats = s;
      storage = st;
      exports = Array.isArray(ex) ? ex : (ex.exports || []);
    } catch (e) {
      toast.error('Stats laden fehlgeschlagen');
    }
    loading = false;
  }

  async function createBackup() {
    backingUp = true;
    try {
      await api.backupCreate();
      toast.success('Backup erstellt (siehe Einstellungen → Backup)');
    } catch (e) { toast.error(e.message); }
    backingUp = false;
  }

  function exportData(type) {
    const base = window.location.port === '8032' ? '' : `${window.location.protocol}//${window.location.hostname}:8031`;
    const urls = {
      videos_json: '/api/exports/videos/json',
      videos_csv: '/api/exports/videos/csv',
      subs_csv: '/api/exports/subscriptions/csv',
      playlists_json: '/api/exports/playlists/json',
    };
    if (urls[type]) {
      window.open(base + urls[type], '_blank');
      toast.success('Export wird heruntergeladen');
    }
  }

  async function deleteExport(filename) {
    try {
      await api.deleteExport(filename);
      exports = exports.filter(e => e.name !== filename);
      toast.info('Export gelöscht');
    } catch (e) { toast.error(e.message); }
  }

  async function cleanupTemp() {
    cleaningTemp = true;
    try {
      const res = await api.cleanupTemp();
      toast.success(`${res.freed_human || '0 B'} freigegeben`);
      storage = await api.getStorage();
    } catch (e) { toast.error(e.message); }
    cleaningTemp = false;
  }

  function pct(used, total) {
    if (!total) return 0;
    return Math.round((used / total) * 100);
  }

  $effect(() => { load(); });
</script>

<div class="stats-page">
  <h1 class="page-title">Statistiken & Verwaltung</h1>

  {#if loading}
    <div class="loading">Lade…</div>
  {:else if stats}
    <!-- Stats Grid -->
    <div class="stats-grid">
      <div class="stat-card accent">
        <span class="stat-value">{stats.total_videos || 0}</span>
        <span class="stat-label">Videos</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{stats.total_size_human || '0 B'}</span>
        <span class="stat-label">Gesamtgröße</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{stats.total_subscriptions || 0}</span>
        <span class="stat-label">Abonnements</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{stats.db_size_human || '0 B'}</span>
        <span class="stat-label">Datenbank</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{stats.download_queue_active || 0} / {stats.download_queue_pending || 0}</span>
        <span class="stat-label">Downloads aktiv / wartend</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{stats.active_jobs || 0}</span>
        <span class="stat-label">Aktive Jobs</span>
      </div>
    </div>

    <!-- Speicher -->
    {#if storage}
      <section class="section">
        <h2>Speicher</h2>
        {#if storage.disk}
          <div class="disk-bar-wrap">
            <div class="disk-info">
              <span>{formatSize(storage.disk.used)} / {formatSize(storage.disk.total)}</span>
              <span>{pct(storage.disk.used, storage.disk.total)}% belegt</span>
            </div>
            <div class="disk-bar">
              <div class="disk-fill" style="width: {pct(storage.disk.used, storage.disk.total)}%"></div>
            </div>
            <span class="disk-free">{formatSize(storage.disk.free)} frei</span>
          </div>
        {/if}
        <div class="dir-grid">
          {#each Object.entries(storage.directories || {}) as [name, dir]}
            <div class="dir-card">
              <span class="dir-name">{name}</span>
              <span class="dir-size">{dir.size_human}</span>
            </div>
          {/each}
        </div>
        <button class="btn-sm" onclick={cleanupTemp} disabled={cleaningTemp}>
          {cleaningTemp ? 'Räume auf…' : 'Temp aufräumen'}
        </button>
      </section>
    {/if}

    <!-- Backup & Export -->
    <section class="section">
      <h2>Backup & Export</h2>
      <div class="export-actions">
        <button class="btn-export" onclick={createBackup} disabled={backingUp}>
          {backingUp ? 'Erstelle…' : 'DB-Backup'}
        </button>
        <button class="btn-export" onclick={() => exportData('videos_json')} disabled={exporting.videos_json}>
          Videos JSON
        </button>
        <button class="btn-export" onclick={() => exportData('videos_csv')} disabled={exporting.videos_csv}>
          <i class="fa-solid fa-file-csv"></i> Videos CSV
        </button>
        <button class="btn-export" onclick={() => exportData('subs_csv')} disabled={exporting.subs_csv}>
          <i class="fa-solid fa-file-csv"></i> Abos CSV
        </button>
        <button class="btn-export" onclick={() => exportData('playlists_json')} disabled={exporting.playlists_json}>
          Playlists JSON
        </button>
      </div>

      {#if exports.length > 0}
        <div class="export-list">
          <h3>Vorhandene Exports</h3>
          {#each exports as exp}
            <div class="export-item">
              <span class="export-name">{exp.name}</span>
              <span class="export-size">{exp.size_human || formatSize(exp.size)}</span>
              <span class="export-date">{exp.created_at || ''}</span>
              <button class="btn-del" onclick={() => deleteExport(exp.filename)}><i class="fa-solid fa-xmark"></i></button>
            </div>
          {/each}
        </div>
      {/if}
    </section>
  {/if}
</div>

<style>
  .stats-page { padding: 24px; max-width: 1000px; }
  .page-title { font-size: 1.4rem; font-weight: 700; color: var(--text-primary); margin: 0 0 20px; }

  .stats-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 12px; margin-bottom: 28px;
  }
  .stat-card {
    background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 10px; padding: 16px; display: flex; flex-direction: column; gap: 4px;
  }
  .stat-card.accent { border-color: var(--accent-primary); }
  .stat-value { font-size: 1.3rem; font-weight: 700; color: var(--text-primary); }
  .stat-label { font-size: 0.76rem; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.04em; }

  .section { margin-bottom: 28px; }
  .section h2 { font-size: 1.1rem; font-weight: 600; color: var(--text-primary); margin: 0 0 14px; }

  /* Disk */
  .disk-bar-wrap { margin-bottom: 14px; }
  .disk-info { display: flex; justify-content: space-between; font-size: 0.82rem; color: var(--text-secondary); margin-bottom: 6px; }
  .disk-bar { height: 10px; background: var(--bg-tertiary); border-radius: 5px; overflow: hidden; }
  .disk-fill { height: 100%; background: var(--accent-primary); border-radius: 5px; transition: width 0.3s; }
  .disk-free { font-size: 0.78rem; color: var(--status-success); font-weight: 600; }

  .dir-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 8px; margin-bottom: 12px; }
  .dir-card {
    background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 8px; padding: 10px 14px; display: flex; flex-direction: column; gap: 2px;
  }
  .dir-name { font-size: 0.78rem; color: var(--text-tertiary); text-transform: capitalize; }
  .dir-size { font-size: 0.95rem; font-weight: 600; color: var(--text-primary); }

  /* Export */
  .export-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
  .btn-export {
    padding: 8px 16px; background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 8px; color: var(--text-primary); font-size: 0.82rem; cursor: pointer;
  }
  .btn-export:hover { border-color: var(--accent-primary); }
  .btn-export:disabled { opacity: 0.4; cursor: default; }

  .export-list h3 { font-size: 0.88rem; color: var(--text-secondary); margin: 0 0 8px; }
  .export-item {
    display: flex; align-items: center; gap: 12px; padding: 8px 12px;
    background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 6px; margin-bottom: 4px; font-size: 0.82rem;
  }
  .export-name { flex: 1; color: var(--text-primary); font-family: monospace; font-size: 0.78rem; }
  .export-size { color: var(--text-tertiary); min-width: 60px; }
  .export-date { color: var(--text-tertiary); font-size: 0.76rem; }
  .btn-del {
    background: none; border: none; color: var(--text-tertiary); cursor: pointer;
    font-size: 0.8rem; padding: 2px 6px;
  }
  .btn-del:hover { color: var(--status-error); }

  .btn-sm {
    padding: 6px 14px; background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 6px; color: var(--text-primary); font-size: 0.82rem; cursor: pointer;
  }
  .btn-sm:hover { border-color: var(--accent-primary); }
  .btn-sm:disabled { opacity: 0.4; }

  .loading { padding: 60px; text-align: center; color: var(--text-tertiary); }
</style>

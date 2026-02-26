<!--
  TubeVault -  Settings v1.5.52
  © HalloWelt42 -  Private Nutzung
  Alle Einstellungen sichtbar, erklärt, transparent
-->
<script>
  import { api } from '../lib/api/client.js';
  import { toast } from '../lib/stores/notifications.js';
  import { formatSize } from '../lib/utils/format.js';
  import { theme } from '../lib/stores/theme.js';
  import { settings as globalSettings } from '../lib/stores/settings.js';
  import { onMount } from 'svelte';
  import ApiEndpoints from '../lib/components/settings/ApiEndpoints.svelte';

  let settings = $state({});
  let scheduler = $state(null);
  let systemStats = $state(null);
  let cleaningGhosts = $state(false);
  let runningFullCleanup = $state(false);
  let cleanupProtocol = $state(null);
  let loading = $state(true);

  // Backup
  let backups = $state([]);
  let backupStats = $state(null);
  let creatingBackup = $state(false);
  let restoringBackup = $state(false);
  let confirmRestore = $state(null);

  let activeCategory = $state('scanner');
  let pollTimer = null;

  const SETTING_DEFS = {
    'rss.enabled': { label: 'Scanner aktiv', desc: 'Prüft automatisch alle abonnierten Kanäle auf neue Videos per RSS-Feed', type: 'toggle', category: 'scanner' },
    'rss.interval': { label: 'Basis-Prüfintervall', desc: 'Startintervall für neue Abos. Verdoppelt sich bei jedem Poll ohne neue Videos (bis max 7 Tage). Neue Videos setzen auf diesen Wert zurück.', type: 'duration', category: 'scanner', min: 300, max: 86400 },
    'rss.max_age_days': { label: 'Maximales Video-Alter', desc: 'Videos älter als X Tage werden ignoriert. YouTube-RSS liefert max. 15 Videos -  bei inaktiven Kanälen können alle älter sein.', type: 'number', category: 'scanner', min: 7, max: 365, unit: 'Tage' },
    'feed.hide_shorts': { label: 'Shorts ausblenden', desc: 'Shorts im Feed nicht anzeigen (über Typ-Filter erreichbar)', type: 'toggle', category: 'feed' },
    'feed.auto_classify': { label: 'Auto-Erkennung (Short/Live)', desc: 'Neue RSS-Videos automatisch als Short oder Livestream klassifizieren', type: 'toggle', category: 'feed' },
    'feed.auto_refresh': { label: 'Kanal-Rescan im Hintergrund', desc: 'Ältere Kanäle periodisch neu scannen (Metadaten, Avatare)', type: 'toggle', category: 'feed' },
    'feed.refresh_interval_days': { label: 'Rescan-Intervall', desc: 'Wie oft Kanäle im Hintergrund re-gescannt werden', type: 'number', category: 'feed', min: 1, max: 30, unit: 'Tage' },
    'rss.auto_download': { label: 'Auto-Download aktiv', desc: 'Neue Videos von Kanälen mit Auto-DL automatisch zur Queue', type: 'toggle', category: 'auto_dl' },
    'rss.auto_quality': { label: 'Auto-Download Qualität', type: 'select', category: 'auto_dl', options: ['360p','480p','720p','1080p','best'] },
    'rss.auto_dl_daily_limit': { label: 'Tageslimit', desc: 'Max. Auto-Downloads pro Tag (Schutz vor Massen-Downloads)', type: 'number', category: 'auto_dl', min: 1, max: 200, unit: 'pro Tag' },
    'download.quality': { label: 'Standard-Qualität', desc: 'Voreinstellung für manuelle Downloads', type: 'select', category: 'download', options: ['360p','480p','720p','1080p','1440p','2160p','best'] },
    'download.format': { label: 'Container-Format', type: 'select', category: 'download', options: ['mp4','mkv','webm'] },
    'download.concurrent': { label: 'Gleichzeitige Downloads', desc: 'Neustart nötig bei Änderung (Server-Konfiguration)', type: 'number', category: 'download', min: 1, max: 5 },
    'download.auto_thumbnail': { label: 'Thumbnail herunterladen', type: 'toggle', category: 'download' },
    'download.auto_subtitle': { label: 'Untertitel herunterladen', type: 'toggle', category: 'download' },
    'download.subtitle_lang': { label: 'Untertitel-Sprachen', desc: 'Kommagetrennt, z.B. de,en', type: 'text', category: 'download' },
    'download.auto_chapters': { label: 'Kapitel speichern', type: 'toggle', category: 'download' },
    'player.volume': { label: 'Standard-Lautstärke', type: 'number', category: 'player', min: 0, max: 100, unit: '%' },
    'player.autoplay': { label: 'Autoplay', type: 'toggle', category: 'player' },
    'player.speed': { label: 'Geschwindigkeit', type: 'select', category: 'player', options: ['0.5','0.75','1.0','1.25','1.5','1.75','2.0'] },
    'player.save_position': { label: 'Position merken', desc: 'Wiedergabeposition beim Schließen speichern', type: 'toggle', category: 'player' },
    'general.videos_per_page': { label: 'Videos pro Seite', type: 'number', category: 'general', min: 12, max: 96 },
  };

  const CATEGORIES = [
    { key: 'scanner', label: 'Scanner-Status', icon: 'fa-satellite-dish', isLive: true },
    { key: 'feed', label: 'Feed', icon: 'fa-rss' },
    { key: 'auto_dl', label: 'Auto-Download', icon: 'fa-robot' },
    { key: 'download', label: 'Downloads', icon: 'fa-download' },
    { key: 'player', label: 'Player', icon: 'fa-play' },
    { key: 'general', label: 'Allgemein', icon: 'fa-gear' },
    { key: 'api', label: 'Dienste & APIs', icon: 'fa-plug' },
    { key: 'system', label: 'System', icon: 'fa-server' },
  ];

  onMount(() => {
    load();
    loadScheduler();
    loadBackups();
    pollTimer = setInterval(loadScheduler, 5000);
    return () => clearInterval(pollTimer);
  });

  async function load() {
    loading = true;
    try {
      const [groups, stats] = await Promise.all([api.getSettings(), api.getStats()]);
      const flat = {};
      for (const g of groups) for (const s of g.settings) flat[s.key] = s.value;
      settings = flat;
      systemStats = stats;
    } catch (e) { toast.error(e.message); }
    loading = false;
  }

  async function loadScheduler() {
    try { scheduler = await api.getSchedulerStatus(); } catch {}
  }

  async function save(key, value) {
    settings[key] = String(value);
    try {
      await api.updateSetting(key, String(value));
      globalSettings.update(s => ({ ...s, [key]: String(value) }));
      toast.success('Gespeichert');
    }
    catch (e) { toast.error(e.message); }
  }

  function toggleSetting(key) { save(key, settings[key] === 'true' ? 'false' : 'true'); }

  async function cleanupGhosts() {
    cleaningGhosts = true;
    try {
      const res = await api.cleanupGhosts();
      if (res.ghosts_found === 0) {
        toast.success('Keine Ghost-Einträge gefunden');
      } else {
        toast.success(`${res.cleaned} Ghost-Einträge bereinigt`);
      }
    } catch (e) { toast.error(e.message); }
    cleaningGhosts = false;
  }

  async function runFullCleanup() {
    runningFullCleanup = true;
    cleanupProtocol = null;
    try {
      const res = await api.cleanupFull();
      cleanupProtocol = res;
      toast.success(`Bereinigung: ${res.totals.cleaned} Einträge, ${res.totals.freed_human} freigegeben`);
    } catch (e) { toast.error(e.message); }
    runningFullCleanup = false;
  }

  // ═══ Backup-Funktionen ═══
  async function loadBackups() {
    try {
      const [list, stats] = await Promise.all([api.backupList(), api.backupStats()]);
      backups = list.backups || [];
      backupStats = stats;
    } catch {}
  }

  async function createBackup() {
    creatingBackup = true;
    try {
      const res = await api.backupCreate();
      toast.success(`Backup erstellt: ${res.filename}`);
      await loadBackups();
    } catch (e) { toast.error(e.message); }
    creatingBackup = false;
  }

  async function deleteBackup(filename) {
    try {
      await api.backupDelete(filename);
      toast.success('Backup gelöscht');
      await loadBackups();
    } catch (e) { toast.error(e.message); }
  }

  async function restoreBackup(filename) {
    restoringBackup = true;
    try {
      const res = await api.backupRestore(filename);
      toast.success(`Wiederhergestellt! Sicherheits-Backup: ${res.safety_backup}`);
      confirmRestore = null;
      await loadBackups();
      // Settings neu laden
      await load();
    } catch (e) { toast.error(e.message); }
    restoringBackup = false;
  }

  async function uploadAndRestore(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.endsWith('.db')) { toast.error('Nur .db Dateien erlaubt'); return; }
    restoringBackup = true;
    try {
      const res = await api.backupRestoreUpload(file);
      toast.success(`Aus Upload wiederhergestellt! Sicherheits-Backup: ${res.safety_backup}`);
      await loadBackups();
      await load();
    } catch (err) { toast.error(err.message); }
    restoringBackup = false;
    e.target.value = '';
  }


  async function resetAll() {
    if (!confirm('Alle Einstellungen zurücksetzen?')) return;
    try { await api.resetSettings(); toast.success('Zurückgesetzt'); await load(); }
    catch (e) { toast.error(e.message); }
  }

  function settingsFor(catKey) {
    return Object.entries(SETTING_DEFS).filter(([_, d]) => d.category === catKey)
      .map(([key, def]) => ({ key, ...def, value: settings[key] ?? '' }));
  }

  function fmtDur(secs) {
    if (!secs) return '–';
    secs = Number(secs);
    if (secs < 60) return `${secs}s`;
    if (secs < 3600) return `${Math.round(secs / 60)} Min`;
    if (secs < 86400) return `${(secs / 3600).toFixed(1)} Std`;
    return `${(secs / 86400).toFixed(1)} Tage`;
  }

  function fmtTime(iso) {
    if (!iso) return '–';
    try {
      const diff = (Date.now() - new Date(iso)) / 1000;
      if (diff < 60) return `vor ${Math.round(diff)}s`;
      if (diff < 3600) return `vor ${Math.round(diff / 60)} Min`;
      return new Date(iso).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
    } catch { return iso; }
  }
</script>

<div class="settings-page">
  <h1 class="page-title"><i class="fa-solid fa-gear"></i> Einstellungen</h1>

  {#if loading}
    <div class="loading"><i class="fa-solid fa-spinner fa-spin"></i> Lade…</div>
  {:else}

  <div class="cat-tabs">
    {#each CATEGORIES as cat}
      <button class="cat-tab" class:active={activeCategory === cat.key} onclick={() => activeCategory = cat.key}>
        <i class="fa-solid {cat.icon}"></i> {cat.label}
        {#if cat.isLive && scheduler?.running}<span class="live-dot"></span>{/if}
      </button>
    {/each}
  </div>

  <!-- ═══ SCANNER LIVE STATUS ═══ -->
  {#if activeCategory === 'scanner'}
    <div class="setting-card">
      <div class="card-header">
        <i class="fa-solid fa-satellite-dish"></i>
        <h3>RSS-Scanner</h3>
        {#if scheduler?.running}
          <span class="status-pill active"><i class="fa-solid fa-clock"></i> Cron-Modus</span>
        {:else}
          <span class="status-pill inactive"><i class="fa-solid fa-circle"></i> Gestoppt</span>
        {/if}
      </div>

      {#if scheduler}
        <div class="live-grid">
          <div class="live-item">
            <span class="live-label">Zuletzt geprüft</span>
            <span class="live-value">{scheduler.last_checked_channel || '–'}</span>
            <span class="live-sub">{fmtTime(scheduler.last_checked_at)}</span>
          </div>
          <div class="live-item">
            <span class="live-label">Fällige Feeds</span>
            <span class="live-value big">{scheduler.feeds_pending}</span>
            <span class="live-sub">warten auf Prüfung</span>
          </div>
          <div class="live-item">
            <span class="live-label">Letzter Cron-Lauf</span>
            {#if scheduler.last_cron_job}
              <span class="live-value">{scheduler.last_cron_job.status === 'active' ? '⏳ läuft…' : '✓ ' + (scheduler.last_cron_job.result || 'fertig')}</span>
              <span class="live-sub">{fmtTime(scheduler.last_cron_job.completed_at || scheduler.last_cron_job.started_at)}</span>
            {:else}
              <span class="live-value">–</span>
              <span class="live-sub">Noch kein Durchlauf</span>
            {/if}
          </div>
          <div class="live-item">
            <span class="live-label">Geprüft (gesamt)</span>
            <span class="live-value big">{scheduler.feeds_checked_total || 0}</span>
          </div>
        </div>

        <div class="sub-section">
          <h4><i class="fa-solid fa-users"></i> Abonnements</h4>
          <div class="stat-pills">
            <span class="pill">{scheduler.subscriptions.total} Gesamt</span>
            <span class="pill ok">{scheduler.subscriptions.enabled} Aktiv</span>
            <span class="pill">{scheduler.subscriptions.checked} Geprüft</span>
            {#if scheduler.subscriptions.unchecked > 0}<span class="pill warn">{scheduler.subscriptions.unchecked} Ungeprüft</span>{/if}
            {#if scheduler.subscriptions.with_errors > 0}<span class="pill err">{scheduler.subscriptions.with_errors} Fehler</span>{/if}
            {#if scheduler.subscriptions.disabled > 0}<span class="pill dim">{scheduler.subscriptions.disabled} Deaktiviert</span>{/if}
          </div>
        </div>

        <div class="sub-section">
          <h4><i class="fa-solid fa-rss"></i> RSS-Entries</h4>
          <div class="stat-pills">
            <span class="pill">{scheduler.entries.total} Entries</span>
            <span class="pill ok">{scheduler.subscriptions.channels_with_entries} Kanäle mit Videos</span>
            {#if scheduler.subscriptions.channels_without_entries > 0}<span class="pill warn">{scheduler.subscriptions.channels_without_entries} ohne Videos</span>{/if}
          </div>
          <p class="hint">Ohne Videos = kein Upload in den letzten {scheduler.active_settings.max_age_days} Tagen oder YouTube liefert nur ältere Einträge.</p>
        </div>

        {#if scheduler.auto_download.enabled}
        <div class="sub-section">
          <h4><i class="fa-solid fa-robot"></i> Auto-Download</h4>
          <div class="stat-pills">
            <span class="pill ok">Aktiv</span>
            <span class="pill">{scheduler.auto_download.today_count} / {scheduler.auto_download.daily_limit} heute</span>
          </div>
        </div>
        {/if}

        {#if scheduler.interval_distribution?.length > 0}
        <div class="sub-section">
          <h4><i class="fa-solid fa-clock"></i> Prüf-Intervalle</h4>
          <div class="interval-bars">
            {#each scheduler.interval_distribution as dist}
              <div class="interval-row">
                <span class="interval-label">{fmtDur(dist.interval)}</span>
                <div class="interval-bar"><div class="interval-fill" style="width:{Math.min(100, (dist.count / scheduler.subscriptions.enabled) * 100)}%"></div></div>
                <span class="interval-count">{dist.count} Kanäle</span>
              </div>
            {/each}
          </div>
          <p class="hint">Bei Fehlern verdoppelt sich das Intervall (max 24h). Nach Erfolg: zurück auf Standardwert.</p>
        </div>
        {/if}

        {#if scheduler.upcoming?.length > 0}
        <div class="sub-section">
          <h4><i class="fa-solid fa-list-check"></i> Nächste in der Queue</h4>
          <div class="upcoming-list">
            {#each scheduler.upcoming as u}
              <div class="upcoming-item">
                <span class="up-name">{u.channel_name || u.channel_id}</span>
                <span class="up-meta">Intervall: {fmtDur(u.check_interval)}{#if u.error_count > 0} · <span class="text-err">{u.error_count}× Fehler</span>{/if}</span>
              </div>
            {/each}
          </div>
        </div>
        {/if}

        {#if scheduler.recent_errors?.length > 0}
        <div class="sub-section">
          <h4><i class="fa-solid fa-triangle-exclamation"></i> Fehler</h4>
          <div class="upcoming-list">
            {#each scheduler.recent_errors as e}
              <div class="upcoming-item err-item">
                <span class="up-name">{e.channel_name}</span>
                <span class="up-meta">{e.error_count}× · Intervall: {fmtDur(e.check_interval)}</span>
                {#if e.last_error}<span class="up-err">{e.last_error.substring(0, 120)}</span>{/if}
              </div>
            {/each}
          </div>
        </div>
        {/if}
      {:else}
        <div class="loading"><i class="fa-solid fa-spinner fa-spin"></i> Lade…</div>
      {/if}
    </div>

    <div class="setting-card">
      <div class="card-header"><i class="fa-solid fa-sliders"></i><h3>Scanner-Einstellungen</h3></div>
      {#each settingsFor('scanner') as item}
        {@render settingRow(item)}
      {/each}
    </div>

  {:else if activeCategory === 'api'}
    <ApiEndpoints />

  {:else if activeCategory === 'system'}
    {#if systemStats}
    <div class="setting-card">
      <div class="card-header"><i class="fa-solid fa-server"></i><h3>System</h3></div>
      <div class="sys-grid">
        <div class="sys-item"><span class="sys-label">Version</span><span class="sys-value">{systemStats.version}</span></div>
        <div class="sys-item"><span class="sys-label">Videos</span><span class="sys-value">{systemStats.video_count || 0}</span></div>
        <div class="sys-item"><span class="sys-label">Belegt</span><span class="sys-value">{systemStats.total_size_human}</span></div>
        <div class="sys-item"><span class="sys-label">DB-Größe</span><span class="sys-value">{systemStats.db_size_human}</span></div>
        {#if systemStats.storage_split}
          <div class="sys-item"><span class="sys-label">Medien frei</span><span class="sys-value">{systemStats.disk_media?.free_human || '–'}</span></div>
          <div class="sys-item"><span class="sys-label">System frei</span><span class="sys-value">{systemStats.disk_meta?.free_human || '–'}</span></div>
        {:else}
          <div class="sys-item"><span class="sys-label">Frei</span><span class="sys-value">{systemStats.disk?.free_human || '–'}</span></div>
          <div class="sys-item"><span class="sys-label">Auslastung</span><span class="sys-value">{systemStats.disk?.percent || '–'}%</span></div>
        {/if}
        <div class="sys-item"><span class="sys-label">Abos</span><span class="sys-value">{systemStats.total_subscriptions || 0}</span></div>
        <div class="sys-item"><span class="sys-label">Downloads</span><span class="sys-value">{systemStats.download_queue_active || 0} aktiv</span></div>
      </div>
    </div>
    {/if}
    <div class="setting-card">
      <div class="card-header"><i class="fa-solid fa-palette"></i><h3>Erscheinungsbild</h3></div>
      <div class="theme-toggle">
        <button class="theme-btn" class:active={$theme === 'dark'} onclick={() => theme.set('dark')}><i class="fa-solid fa-moon"></i> Dunkel</button>
        <button class="theme-btn" class:active={$theme === 'light'} onclick={() => theme.set('light')}><i class="fa-solid fa-sun"></i> Hell</button>
      </div>
    </div>
    <div class="setting-card">
      <div class="card-header"><i class="fa-solid fa-wrench"></i><h3>Wartung</h3></div>
      <div class="action-row">
        <button class="action-btn accent" onclick={runFullCleanup} disabled={runningFullCleanup}>
          <i class="fa-solid {runningFullCleanup ? 'fa-spinner fa-spin' : 'fa-broom'}"></i>
          {runningFullCleanup ? 'Bereinigung läuft…' : 'Volle DB-Bereinigung'}
        </button>
        <span class="action-hint">Ghosts, verwaiste Zuordnungen, alte Jobs, Temp + VACUUM</span>
      </div>
      {#if cleanupProtocol}
        <div class="cleanup-protocol">
          <div class="cp-header">
            <span class="cp-title"><i class="fa-solid fa-clipboard-list"></i> Protokoll</span>
            <span class="cp-summary">{cleanupProtocol.totals.cleaned} bereinigt · {cleanupProtocol.totals.freed_human} freigegeben</span>
          </div>
          <div class="cp-list">
            {#each cleanupProtocol.protocol as step}
              <div class="cp-row" class:cp-active={step.count > 0 || step.freed > 0}>
                <span class="cp-icon">{step.count > 0 || step.freed > 0 ? '✅' : '⚪'}</span>
                <span class="cp-detail">{step.detail}</span>
              </div>
            {/each}
          </div>
        </div>
      {/if}
    </div>

    <!-- Backup & Restore -->
    <div class="setting-card">
      <div class="card-header"><i class="fa-solid fa-box-archive"></i><h3>Backup & Restore</h3></div>

      <!-- Stats -->
      {#if backupStats}
        <div class="backup-stats">
          <span class="bs-item"><i class="fa-solid fa-database"></i> DB: {formatSize(backupStats.db_size)}</span>
          <span class="bs-item"><i class="fa-solid fa-film"></i> {backupStats.tables?.videos ?? 0} Videos</span>
          <span class="bs-item"><i class="fa-solid fa-bookmark"></i> {backupStats.tables?.chapters ?? 0} Kapitel</span>
          <span class="bs-item"><i class="fa-solid fa-rss"></i> {backupStats.tables?.subscriptions ?? 0} Abos</span>
          <span class="bs-item"><i class="fa-solid fa-satellite-dish"></i> {backupStats.tables?.rss_entries ?? 0} RSS</span>
        </div>
      {/if}

      <!-- Erstellen -->
      <div class="action-row">
        <button class="action-btn" onclick={createBackup} disabled={creatingBackup}>
          <i class="fa-solid fa-plus"></i> {creatingBackup ? 'Erstelle…' : 'Neues Backup erstellen'}
        </button>
        <span class="action-hint">SQLite-DB sicher exportieren (VACUUM INTO)</span>
      </div>

      <!-- Upload -->
      <div class="action-row">
        <label class="action-btn upload-btn" class:disabled={restoringBackup}>
          <i class="fa-solid fa-upload"></i> DB-Datei hochladen & wiederherstellen
          <input type="file" accept=".db" onchange={uploadAndRestore} disabled={restoringBackup} style="display:none" />
        </label>
        <span class="action-hint">Externe .db Datei als Backup einspielen</span>
      </div>

      <!-- Liste -->
      {#if backups.length > 0}
        <div class="backup-list">
          {#each backups as b}
            <div class="backup-item">
              <div class="backup-info">
                <span class="backup-name">{b.filename}</span>
                <span class="backup-meta">{formatSize(b.size)} · {new Date(b.created_at).toLocaleString('de-DE')}</span>
              </div>
              <div class="backup-actions">
                <a class="backup-btn" href={api.backupDownloadUrl(b.filename)} download title="Herunterladen">
                  <i class="fa-solid fa-download"></i>
                </a>
                {#if confirmRestore === b.filename}
                  <button class="backup-btn danger" onclick={() => restoreBackup(b.filename)} disabled={restoringBackup} title="Bestätigen">
                    {#if restoringBackup}<i class="fa-solid fa-spinner fa-spin"></i>{:else}<i class="fa-solid fa-check"></i> Ja{/if}
                  </button>
                  <button class="backup-btn" onclick={() => confirmRestore = null} title="Abbrechen">
                    <i class="fa-solid fa-xmark"></i>
                  </button>
                {:else}
                  <button class="backup-btn warn" onclick={() => confirmRestore = b.filename} title="Wiederherstellen">
                    <i class="fa-solid fa-clock-rotate-left"></i>
                  </button>
                {/if}
                <button class="backup-btn danger" onclick={() => deleteBackup(b.filename)} title="Löschen">
                  <i class="fa-solid fa-trash-can"></i>
                </button>
              </div>
            </div>
          {/each}
        </div>
      {:else}
        <p class="no-backups">Noch keine Backups vorhanden</p>
      {/if}
    </div>

    <div class="setting-card danger-card">
      <div class="card-header"><i class="fa-solid fa-triangle-exclamation"></i><h3>Gefahrenzone</h3></div>
      <div class="action-row">
        <button class="action-btn danger" onclick={resetAll}><i class="fa-solid fa-rotate-left"></i> Alle Einstellungen zurücksetzen</button>
        <span class="action-hint">Setzt alle Werte auf Standard zurück</span>
      </div>
    </div>

  {:else}
    {#each CATEGORIES.filter(c => c.key === activeCategory && !c.isLive && c.key !== 'system') as cat}
      <div class="setting-card">
        <div class="card-header"><i class="fa-solid {cat.icon}"></i><h3>{cat.label}</h3></div>
        {#each settingsFor(cat.key) as item}
          {@render settingRow(item)}
        {/each}
      </div>
    {/each}
  {/if}
  {/if}
</div>

{#snippet settingRow(item)}
  <div class="setting-row">
    <div class="setting-info">
      <span class="setting-label">{item.label}</span>
      {#if item.desc}<span class="setting-desc">{item.desc}</span>{/if}
    </div>
    <div class="setting-control">
      {#if item.type === 'toggle'}
        <button class="toggle" class:on={item.value === 'true'} onclick={() => toggleSetting(item.key)}><span class="toggle-knob"></span></button>
      {:else if item.type === 'duration'}
        <div class="duration-wrap">
          <input type="number" class="number-input" value={item.value} min={item.min} max={item.max} onchange={(e) => save(item.key, e.target.value)} />
          <span class="duration-hint">{fmtDur(item.value)}</span>
        </div>
      {:else if item.type === 'number'}
        <div class="number-wrap">
          <input type="number" class="number-input" value={item.value} min={item.min} max={item.max} onchange={(e) => save(item.key, e.target.value)} />
          {#if item.unit}<span class="unit-hint">{item.unit}</span>{/if}
        </div>
      {:else if item.type === 'select'}
        <select class="select-input" value={item.value} onchange={(e) => save(item.key, e.target.value)}>
          {#each item.options as opt}<option value={opt}>{opt}</option>{/each}
        </select>
      {:else}
        <input type="text" class="text-input" value={item.value} onchange={(e) => save(item.key, e.target.value)} />
      {/if}
    </div>
  </div>
{/snippet}

<style>
  .settings-page { padding: 24px; max-width: 800px; }
  .page-title { font-size: 1.5rem; font-weight: 700; color: var(--text-primary); margin: 0 0 20px; display: flex; align-items: center; gap: 10px; }
  .page-title i { color: var(--accent-primary); font-size: 1.2rem; }
  .loading { text-align: center; padding: 48px; color: var(--text-tertiary); }
  .cat-tabs { display: flex; gap: 4px; margin-bottom: 20px; flex-wrap: wrap; }
  .cat-tab { display: flex; align-items: center; gap: 6px; padding: 7px 14px; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 8px; color: var(--text-secondary); font-size: 0.78rem; cursor: pointer; transition: all 0.15s; }
  .cat-tab:hover { border-color: var(--accent-primary); color: var(--text-primary); }
  .cat-tab.active { border-color: var(--accent-primary); background: var(--accent-muted); color: var(--accent-primary); font-weight: 600; }
  .cat-tab i { font-size: 0.8rem; }
  .live-dot { width: 6px; height: 6px; border-radius: 50%; background: #22c55e; animation: pulse-dot 2s ease-in-out infinite; }
  @keyframes pulse-dot { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }
  .setting-card { background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 12px; padding: 20px; margin-bottom: 16px; }
  .danger-card { border-color: #ef444466; }

  /* Backup */
  .backup-stats { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; padding: 10px 12px; background: var(--bg-tertiary); border-radius: 8px; }
  .bs-item { font-size: 0.76rem; color: var(--text-secondary); display: flex; align-items: center; gap: 5px; }
  .bs-item i { color: var(--text-tertiary); font-size: 0.7rem; }
  .upload-btn { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; }
  .upload-btn.disabled { opacity: 0.5; pointer-events: none; }
  .backup-list { display: flex; flex-direction: column; gap: 6px; margin-top: 12px; }
  .backup-item { display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; background: var(--bg-tertiary); border-radius: 8px; gap: 10px; }
  .backup-info { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .backup-name { font-size: 0.78rem; font-weight: 500; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .backup-meta { font-size: 0.68rem; color: var(--text-tertiary); }
  .backup-actions { display: flex; gap: 4px; flex-shrink: 0; }
  .backup-btn { background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 5px; padding: 4px 8px; font-size: 0.72rem; color: var(--text-secondary); cursor: pointer; display: inline-flex; align-items: center; gap: 4px; text-decoration: none; }
  .backup-btn:hover { border-color: var(--accent-primary); color: var(--accent-primary); }
  .backup-btn.warn { color: var(--status-warning); border-color: var(--status-warning); }
  .backup-btn.warn:hover { background: var(--status-warning); color: #fff; }
  .backup-btn.danger { color: var(--status-error); border-color: var(--status-error); }
  .backup-btn.danger:hover { background: var(--status-error); color: #fff; }
  .no-backups { font-size: 0.78rem; color: var(--text-tertiary); margin: 8px 0 0 0; }
  .card-header { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--border-primary); }
  .card-header i { color: var(--accent-primary); font-size: 1rem; width: 20px; text-align: center; }
  .card-header h3 { margin: 0; font-size: 1rem; font-weight: 600; color: var(--text-primary); flex: 1; }
  .status-pill { display: flex; align-items: center; gap: 5px; padding: 3px 10px; border-radius: 12px; font-size: 0.7rem; font-weight: 600; }
  .status-pill.active { background: #22c55e20; color: #22c55e; }
  .status-pill.inactive { background: #ef444420; color: #ef4444; }
  .status-pill i { font-size: 0.45rem; }
  .live-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px; }
  .live-item { background: var(--bg-tertiary); border-radius: 8px; padding: 12px; }
  .live-label { display: block; font-size: 0.7rem; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 4px; }
  .live-value { display: block; font-size: 0.95rem; font-weight: 600; color: var(--text-primary); }
  .live-value.big { font-size: 1.4rem; font-family: monospace; }
  .live-sub { display: block; font-size: 0.72rem; color: var(--text-tertiary); margin-top: 2px; }
  .sub-section { margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--border-primary); }
  .sub-section h4 { font-size: 0.85rem; font-weight: 600; color: var(--text-primary); margin: 0 0 10px; display: flex; align-items: center; gap: 8px; }
  .sub-section h4 i { color: var(--accent-primary); font-size: 0.8rem; }
  .stat-pills { display: flex; flex-wrap: wrap; gap: 6px; }
  .pill { padding: 4px 10px; background: var(--bg-tertiary); border-radius: 6px; font-size: 0.75rem; color: var(--text-secondary); font-weight: 500; }
  .pill.ok { background: #22c55e18; color: #22c55e; }
  .pill.warn { background: #f59e0b18; color: #d97706; }
  .pill.err { background: #ef444418; color: #ef4444; }
  .pill.dim { opacity: 0.5; }
  .hint { font-size: 0.72rem; color: var(--text-tertiary); margin: 8px 0 0; line-height: 1.5; }
  .interval-bars { display: flex; flex-direction: column; gap: 6px; }
  .interval-row { display: flex; align-items: center; gap: 10px; }
  .interval-label { width: 60px; font-size: 0.75rem; color: var(--text-secondary); font-weight: 500; text-align: right; }
  .interval-bar { flex: 1; height: 8px; background: var(--bg-tertiary); border-radius: 4px; overflow: hidden; }
  .interval-fill { height: 100%; background: var(--accent-primary); border-radius: 4px; transition: width 0.3s; min-width: 2px; }
  .interval-count { font-size: 0.72rem; color: var(--text-tertiary); min-width: 65px; }
  .upcoming-list { display: flex; flex-direction: column; gap: 6px; }
  .upcoming-item { background: var(--bg-tertiary); border-radius: 6px; padding: 8px 12px; }
  .err-item { border-left: 3px solid #ef4444; }
  .up-name { display: block; font-size: 0.82rem; font-weight: 600; color: var(--text-primary); }
  .up-meta { font-size: 0.72rem; color: var(--text-tertiary); }
  .up-err { display: block; font-size: 0.68rem; color: #ef4444; margin-top: 3px; font-family: monospace; word-break: break-all; }
  .text-err { color: #ef4444; }
  .setting-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 10px 0; border-bottom: 1px solid var(--border-primary); }
  .setting-row:last-of-type { border-bottom: none; }
  .setting-info { flex: 1; min-width: 0; }
  .setting-label { display: block; font-size: 0.88rem; color: var(--text-primary); font-weight: 500; }
  .setting-desc { display: block; font-size: 0.75rem; color: var(--text-tertiary); margin-top: 2px; line-height: 1.4; }
  .setting-control { flex-shrink: 0; }
  .toggle { position: relative; width: 44px; height: 24px; background: var(--bg-tertiary); border: 1px solid var(--border-primary); border-radius: 12px; cursor: pointer; transition: all 0.2s; padding: 0; }
  .toggle.on { background: var(--accent-primary); border-color: var(--accent-primary); }
  .toggle-knob { position: absolute; top: 2px; left: 2px; width: 18px; height: 18px; border-radius: 50%; background: white; transition: transform 0.2s; box-shadow: 0 1px 3px rgba(0,0,0,0.2); }
  .toggle.on .toggle-knob { transform: translateX(20px); }
  .duration-wrap { display: flex; align-items: center; gap: 8px; }
  .duration-hint { font-size: 0.72rem; color: var(--text-tertiary); min-width: 50px; }
  .number-wrap { display: flex; align-items: center; gap: 6px; }
  .number-input { width: 90px; padding: 6px 10px; text-align: right; background: var(--bg-tertiary); border: 1px solid var(--border-primary); border-radius: 8px; color: var(--text-primary); font-size: 0.85rem; font-family: monospace; outline: none; }
  .number-input:focus { border-color: var(--accent-primary); }
  .unit-hint { font-size: 0.72rem; color: var(--text-tertiary); }
  .select-input { padding: 6px 10px; min-width: 120px; background: var(--bg-tertiary); border: 1px solid var(--border-primary); border-radius: 8px; color: var(--text-primary); font-size: 0.85rem; outline: none; cursor: pointer; }
  .select-input:focus { border-color: var(--accent-primary); }
  .text-input { width: 160px; padding: 6px 10px; background: var(--bg-tertiary); border: 1px solid var(--border-primary); border-radius: 8px; color: var(--text-primary); font-size: 0.85rem; outline: none; }
  .text-input:focus { border-color: var(--accent-primary); }
  .theme-toggle { display: flex; gap: 8px; }
  .theme-btn { padding: 8px 20px; display: flex; align-items: center; gap: 6px; background: var(--bg-tertiary); border: 1px solid var(--border-primary); border-radius: 8px; color: var(--text-secondary); cursor: pointer; font-size: 0.85rem; transition: all 0.2s; }
  .theme-btn:hover { border-color: var(--accent-primary); }
  .theme-btn.active { background: var(--accent-muted); color: var(--accent-primary); border-color: var(--accent-primary); }
  .action-row { display: flex; align-items: center; gap: 12px; padding-top: 14px; margin-top: 6px; border-top: 1px solid var(--border-primary); }
  .action-btn { padding: 8px 16px; display: flex; align-items: center; gap: 6px; background: var(--accent-muted); border: 1px solid var(--accent-primary); border-radius: 8px; color: var(--accent-primary); cursor: pointer; font-size: 0.82rem; font-weight: 500; transition: all 0.2s; white-space: nowrap; }
  .action-btn:hover { background: var(--accent-primary); color: white; }
  .action-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .action-btn.danger { background: #ef444418; border-color: #ef4444; color: #ef4444; }
  .action-btn.danger:hover { background: #ef4444; color: white; }
  .action-hint { font-size: 0.75rem; color: var(--text-tertiary); }
  .sys-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0; }
  .sys-item { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--border-primary); font-size: 0.85rem; }
  .sys-item:nth-last-child(-n+2) { border-bottom: none; }
  .sys-item:nth-child(odd) { padding-right: 16px; border-right: 1px solid var(--border-primary); }
  .sys-item:nth-child(even) { padding-left: 16px; }
  .sys-label { color: var(--text-secondary); }
  .sys-value { color: var(--text-primary); font-weight: 500; font-family: monospace; }
  @media (max-width: 600px) {
    .cat-tabs { overflow-x: auto; flex-wrap: nowrap; }
    .setting-row { flex-direction: column; align-items: flex-start; gap: 8px; }
    .live-grid { grid-template-columns: 1fr; }
    .sys-grid { grid-template-columns: 1fr; }
    .sys-item:nth-child(odd) { padding-right: 0; border-right: none; }
    .sys-item:nth-child(even) { padding-left: 0; }
    .action-row { flex-direction: column; align-items: flex-start; }
  }

  /* Cleanup Protocol */
  .cleanup-protocol { margin: 12px 0; background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 8px; padding: 12px; }
  .cp-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
  .cp-title { font-size: 0.82rem; font-weight: 600; color: var(--text-primary); display: flex; align-items: center; gap: 6px; }
  .cp-summary { font-size: 0.75rem; color: var(--accent-primary); font-weight: 500; }
  .cp-list { display: flex; flex-direction: column; gap: 4px; }
  .cp-row { display: flex; align-items: center; gap: 8px; padding: 4px 6px; border-radius: 4px; font-size: 0.76rem; color: var(--text-tertiary); }
  .cp-row.cp-active { color: var(--text-primary); background: var(--accent-muted); }
  .cp-icon { font-size: 0.8rem; flex-shrink: 0; }
  .cp-detail { flex: 1; }
  .action-btn.accent { background: var(--accent-muted); border-color: var(--accent-primary); color: var(--accent-primary); }
  .action-btn.accent:hover { background: var(--accent-primary); color: #fff; }
</style>

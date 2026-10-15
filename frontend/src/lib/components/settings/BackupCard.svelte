<!--
  Sicherung und Wiederherstellung der Datenbank (Einstellungen, Abschnitt System).
-->
<script>
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';
  import { formatSize } from '../../utils/format.js';

  let { onRestored = () => {} } = $props();   // Einstellungen danach neu laden

  let backups = $state([]);
  let stats = $state(null);
  let creating = $state(false);
  let restoring = $state(false);
  let confirmRestore = $state(null);

  async function load() {
    try {
      const [list, s] = await Promise.all([api.backupList(), api.backupStats()]);
      backups = list.backups || [];
      stats = s;
    } catch {}
  }
  $effect(() => { load(); });

  async function create() {
    creating = true;
    try { toast.success(`Gesichert: ${(await api.backupCreate()).filename}`); await load(); }
    catch (e) { toast.error(e.message); }
    creating = false;
  }

  async function remove(filename) {
    try { await api.backupDelete(filename); toast.success('Sicherung gelöscht'); await load(); }
    catch (e) { toast.error(e.message); }
  }

  async function restore(filename) {
    restoring = true;
    try {
      const res = await api.backupRestore(filename);
      toast.success(`Zurückgespielt; vorheriger Stand gesichert als ${res.safety_backup}`);
      confirmRestore = null;
      await load();
      onRestored();
    } catch (e) { toast.error(e.message); }
    restoring = false;
  }

  async function uploadAndRestore(e) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    if (!file.name.endsWith('.db')) { toast.error('Nur .db-Dateien'); return; }
    restoring = true;
    try {
      const res = await api.backupRestoreUpload(file);
      toast.success(`Zurückgespielt; vorheriger Stand gesichert als ${res.safety_backup}`);
      await load();
      onRestored();
    } catch (err) { toast.error(err.message); }
    restoring = false;
  }
</script>

<section class="tv-karte">
  <h3><i class="fa-solid fa-floppy-disk"></i> Sicherung</h3>
  {#if stats}
    <p class="tv-leise tv-klein zahl">Datenbank {formatSize(stats.db_size)} · {stats.tables?.videos ?? 0} Videos · {stats.tables?.subscriptions ?? 0} Abos · {stats.tables?.chapters ?? 0} Kapitel</p>
  {/if}
  <div class="knoepfe">
    <button class="tv-knopf klein" onclick={create} disabled={creating}><i class="fa-solid {creating ? 'fa-spinner fa-spin' : 'fa-plus'}"></i> Jetzt sichern</button>
    <label class="tv-knopf klein" class:aus={restoring}>
      <i class="fa-solid fa-upload"></i> Datei zurückspielen
      <input type="file" accept=".db" onchange={uploadAndRestore} disabled={restoring} hidden />
    </label>
  </div>
  {#each backups as b}
    <div class="sicherung">
      <div class="text"><div class="name">{b.filename}</div>
        <div class="tv-schwach tv-klein zahl">{formatSize(b.size)} · {new Date(b.created_at).toLocaleString('de-DE')}</div></div>
      <a class="tv-knopf ohne symbol klein" href={api.backupDownloadUrl(b.filename)} download title="Herunterladen"><i class="fa-solid fa-download"></i></a>
      {#if confirmRestore === b.filename}
        <button class="tv-knopf klein gefahr" onclick={() => restore(b.filename)} disabled={restoring}>
          <i class="fa-solid {restoring ? 'fa-spinner fa-spin' : 'fa-check'}"></i> Zurückspielen</button>
        <button class="tv-knopf ohne symbol klein" onclick={() => confirmRestore = null} title="Abbrechen"><i class="fa-solid fa-xmark"></i></button>
      {:else}
        <button class="tv-knopf ohne symbol klein" onclick={() => confirmRestore = b.filename} title="Diesen Stand zurückspielen"><i class="fa-solid fa-clock-rotate-left"></i></button>
      {/if}
      <button class="tv-knopf ohne symbol klein gefahr" onclick={() => remove(b.filename)} title="Löschen"><i class="fa-solid fa-trash-can"></i></button>
    </div>
  {:else}
    <p class="tv-schwach tv-klein">Noch keine Sicherung vorhanden.</p>
  {/each}
</section>

<style>
  .knoepfe { display: flex; gap: var(--tv-a2); margin: var(--tv-a3) 0; flex-wrap: wrap; }
  .aus { opacity: 0.5; pointer-events: none; }
  .sicherung { display: flex; align-items: center; gap: 2px; padding: 6px 0; border-top: 1px solid var(--tv-rand); }
  .sicherung .text { flex: 1; min-width: 0; }
  .sicherung .name { font-size: var(--tv-gr-klein); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>

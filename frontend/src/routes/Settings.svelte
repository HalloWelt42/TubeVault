<!--
  TubeVault – Einstellungen (Gestaltung nach mockups/einstellungen.html)
  Fester Kopf mit Sprungmarken, darunter alle Abschnitte in einem Rollfeld.
  Die Regler kommen aus dem Einstellungs-Schema des Backends (Art, Grenzen,
  Auswahl, Erklärung) - eine Stelle für Datenbank, Prüfung und Oberfläche.
  © HalloWelt42 – Private Nutzung
-->
<script>
  import { api } from '../lib/api/client.js';
  import { toast } from '../lib/stores/notifications.js';
  import { formatSize } from '../lib/utils/format.js';
  import { settings as globalSettings, reloadSettings } from '../lib/stores/settings.js';
  import ConfirmDialog from '../lib/components/common/ConfirmDialog.svelte';
  import ApiEndpoints from '../lib/components/settings/ApiEndpoints.svelte';
  import SettingRow from '../lib/components/settings/SettingRow.svelte';
  import ChannelCheckStatus from '../lib/components/settings/ChannelCheckStatus.svelte';
  import BackupCard from '../lib/components/settings/BackupCard.svelte';
  import MaintenanceCard from '../lib/components/settings/MaintenanceCard.svelte';
  import RestoreCard from '../lib/components/settings/RestoreCard.svelte';

  let confirmRef;
  const confirm = (...args) => confirmRef.ask(...args);

  const SECTIONS = [
    { id: 'channels', label: 'Kanäle', icon: 'fa-satellite-dish' },
    { id: 'downloads', label: 'Downloads', icon: 'fa-download' },
    { id: 'view', label: 'Ansicht', icon: 'fa-display' },
    { id: 'music', label: 'Musik', icon: 'fa-music' },
    { id: 'extensions', label: 'Erweiterungen', icon: 'fa-puzzle-piece' },
    { id: 'system', label: 'System', icon: 'fa-server' },
  ];

  let schema = $state([]);
  let values = $state({});
  let loading = $state(true);
  let scheduler = $state(null);
  let systemStats = $state(null);
  let shorts = $state(null);
  let semantic = $state(null);
  let deletingShorts = $state(false);

  async function load() {
    loading = true;
    try {
      const [groups, defs, stats] = await Promise.all([api.getSettings(), api.getSettingsSchema(), api.getStats()]);
      schema = defs;
      const flat = {};
      for (const g of groups) for (const s of g.settings) flat[s.key] = s.value;
      values = flat;
      systemStats = stats;
    } catch (e) { toast.error(e.message); }
    loading = false;
  }
  const loadScheduler = () => api.getSchedulerStatus().then(s => scheduler = s).catch(() => {});
  const loadShorts = () => api.getShortsOverview().then(s => shorts = s).catch(() => shorts = null);
  const loadSemantic = () => api.getSemanticOverview().then(s => semantic = s).catch(() => semantic = null);

  $effect(() => {
    load(); loadScheduler(); loadShorts(); loadSemantic();
    const iv = setInterval(loadScheduler, 5000);
    return () => clearInterval(iv);
  });

  async function save(key, value) {
    const before = values[key];
    values[key] = String(value);
    try {
      const res = await api.updateSetting(key, String(value));   // das Backend prüft und liefert den Wert
      values[key] = res.value;
      globalSettings.update(s => ({ ...s, [key]: res.value }));
      if (key.startsWith('ai.')) loadSemantic();
      if (key.startsWith('rss.')) loadScheduler();
      toast.success('Gespeichert');
    } catch (e) {
      values[key] = before;
      toast.error(e.message);
    }
  }

  async function removeShorts() {
    const ok = await confirm(`${shorts.confirmed_shorts} Shorts löschen?`,
      'Gelöscht werden nur Videos, die die Quelle als Short bestätigt hat. Sie sind danach restlos weg.',
      { confirmLabel: 'Shorts löschen' });
    if (!ok) return;
    deletingShorts = true;
    try { toast.success(`${(await api.deleteShorts()).deleted} Shorts gelöscht`); }
    catch (e) { toast.error(e.message); }
    deletingShorts = false;
    loadShorts();
  }

  async function afterRestore() { await load(); await reloadSettings(); }

  const rowsOf = (section) => schema.filter(d => d.section === section);

  // ─── Sprungmarken: Klick rollt zum Abschnitt, der sichtbare ist hervorgehoben ───
  let scroller = $state(null);
  let current = $state('channels');
  function jump(id) {
    const target = scroller?.querySelector(`#abschnitt-${id}`);
    if (target) scroller.scrollTo({ top: target.offsetTop - scroller.offsetTop - 8, behavior: 'smooth' });
  }
  function onScroll() {
    let best = SECTIONS[0].id;
    for (const s of SECTIONS) {
      const el = scroller.querySelector(`#abschnitt-${s.id}`);
      if (el && el.getBoundingClientRect().top - scroller.getBoundingClientRect().top < 120) best = s.id;
    }
    current = best;
  }
</script>

{#snippet rows(section)}
  {#each rowsOf(section) as def (def.key)}
    <SettingRow {def} value={values[def.key] ?? def.default} onSave={(v) => save(def.key, v)} />
  {/each}
{/snippet}

<div class="tv-seite">
  <div class="tv-seitenkopf">
    <div class="kopfzeile">
      <h1>Einstellungen</h1>
      <span class="tv-schwach tv-klein">Änderungen gelten sofort</span>
    </div>
    <div class="tv-reiter">
      {#each SECTIONS as s}
        <button class:aktiv={current === s.id} onclick={() => jump(s.id)}><i class="fa-solid {s.icon}"></i> {s.label}</button>
      {/each}
    </div>
  </div>

  <div class="tv-rollfeld" data-scroll-root bind:this={scroller} onscroll={onScroll}>
    {#if loading}
      <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt ...</div>
    {:else}
      <div class="inhalt">
        <section class="gruppe" id="abschnitt-channels">
          <h2><i class="fa-solid fa-satellite-dish"></i> Kanäle</h2>
          {@render rows('channels')}
          {#if shorts?.confirmed_shorts > 0}
            <div class="zusatz">
              <div class="name" title="Gelöscht werden nur Videos, die die Quelle als Short bestätigt hat.{shorts.unverified > 0 ? ` ${shorts.unverified} werden noch geprüft und bleiben.` : ''}">
                Shorts im Bestand <span class="zahl tv-leise">{shorts.confirmed_shorts.toLocaleString('de-DE')} · {formatSize(shorts.confirmed_bytes)}</span></div>
              <button class="tv-knopf klein gefahr" onclick={removeShorts} disabled={deletingShorts}>
                <i class="fa-solid {deletingShorts ? 'fa-spinner fa-spin' : 'fa-trash-can'}"></i> Alle löschen</button>
            </div>
          {/if}
          <ChannelCheckStatus {scheduler} />
        </section>

        <section class="gruppe" id="abschnitt-downloads">
          <h2><i class="fa-solid fa-download"></i> Downloads</h2>
          {@render rows('downloads')}
          <div class="zusatz tv-klein tv-leise">Drosselung und Pause zwischen Downloads stehen auf der Downloads-Seite.</div>
        </section>

        <section class="gruppe" id="abschnitt-view">
          <h2><i class="fa-solid fa-display"></i> Ansicht</h2>
          {@render rows('view')}
        </section>

        <section class="gruppe" id="abschnitt-music">
          <h2><i class="fa-solid fa-music"></i> Musik</h2>
          <p class="einleitung tv-klein tv-leise">Interpreten trennen: nennt ein Titel mehrere ("50 Cent, Nate Dogg", "feat."), zählt er
            bei jedem. Getrennt wird von selbst, wenn ein Teil auch allein vorkommt; die Listen legen es fest.</p>
          {@render rows('music')}
        </section>

        <section class="gruppe" id="abschnitt-extensions">
          <h2><i class="fa-solid fa-puzzle-piece"></i> Erweiterungen</h2>
          {@render rows('extensions')}
          {#if semantic?.enabled}
            <div class="zusatz tv-klein">
              <span class="tv-zustand {semantic.available ? 'fertig' : 'warnung'}">KI-Dienst {semantic.available ? 'erreichbar' : 'nicht erreichbar'}</span>
              <span class="zahl tv-leise">{semantic.indexed.toLocaleString('de-DE')} Videos und {semantic.passages_indexed.toLocaleString('de-DE')} Textstellen eingebettet{#if semantic.pending + semantic.passages_pending > 0}, {(semantic.pending + semantic.passages_pending).toLocaleString('de-DE')} warten{/if}</span>
            </div>
          {/if}
        </section>

        <section id="abschnitt-system">
          <h2 class="ueberschrift"><i class="fa-solid fa-server"></i> System</h2>
          <div class="gruppe">{@render rows('system')}</div>
          {#if systemStats}
            <div class="tv-kennzahlen system">
              <div class="tv-kennzahl"><b class="klein">{systemStats.version}</b><span>Version</span></div>
              <div class="tv-kennzahl"><b class="klein">{(systemStats.video_count || 0).toLocaleString('de-DE')}</b><span>Videos</span></div>
              <div class="tv-kennzahl"><b class="klein">{formatSize(systemStats.total_size_bytes)}</b><span>Belegt</span></div>
              <div class="tv-kennzahl"><b class="klein">{formatSize((systemStats.storage_split ? systemStats.disk_media : systemStats.disk)?.free)}</b><span>Frei</span></div>
              <div class="tv-kennzahl"><b class="klein">{formatSize(systemStats.db_size_bytes)}</b><span>Datenbank</span></div>
            </div>
          {/if}
          <BackupCard onRestored={afterRestore} />
          <RestoreCard {confirm} />
          <MaintenanceCard {confirm} onReset={afterRestore} />
          <details class="tv-karte dienste">
            <summary><i class="fa-solid fa-plug"></i> Dienste und Schnittstellen</summary>
            <ApiEndpoints />
          </details>
        </section>
      </div>
    {/if}
  </div>
</div>

<ConfirmDialog bind:this={confirmRef} />

<style>
  .kopfzeile { display: flex; align-items: baseline; gap: var(--tv-a4); margin-bottom: var(--tv-a4); }
  .kopfzeile h1 { margin: 0; font-size: var(--tv-gr-seite); }
  .inhalt { max-width: 1000px; }
  .gruppe { background: var(--tv-flaeche); border-radius: var(--tv-ecke); margin-bottom: var(--tv-a5); }
  .gruppe h2, .ueberschrift {
    display: flex; align-items: center; gap: var(--tv-a3); margin: 0; padding: var(--tv-a4);
    font-size: var(--tv-gr-titel); border-bottom: 1px solid var(--tv-rand);
  }
  .ueberschrift { padding: 0 0 var(--tv-a3); border: 0; }
  .gruppe h2 i, .ueberschrift i { color: var(--tv-akzent); width: 22px; text-align: center; }
  .zusatz { display: flex; align-items: center; justify-content: space-between; gap: var(--tv-a3); padding: var(--tv-a3) var(--tv-a4); border-top: 1px solid var(--tv-rand); flex-wrap: wrap; }
  .zusatz .name { font-weight: 600; }
  .einleitung { margin: 0; padding: var(--tv-a3) var(--tv-a4) 0; }
  .system { margin-bottom: var(--tv-a3); }
  .tv-kennzahl b.klein { font-size: 20px; }
  .dienste { margin-top: var(--tv-a3); }
  .dienste summary { cursor: pointer; font-weight: 600; display: flex; align-items: center; gap: var(--tv-a2); }
  .dienste summary i { color: var(--tv-akzent); }
</style>

<!--
  Reiter "Diagnose" der Kanalseite (Entwurf mockups/kanal.html): Dateien
  aller geladenen Videos samt Begleitdateien, aus denen sich die Datenbank
  neu aufbauen lässt, und die Vollständigkeit des Katalogs
  (Backend services/channel_diagnosis).
-->
<script>
  import { onMount } from 'svelte';
  import { api } from '../../api/client.js';
  import { formatDate } from '../../utils/format.js';
  import { num } from './channelView.js';

  let { channelId } = $props();

  let result = $state(null);
  let loading = $state(false);
  let failed = $state('');

  async function load() {
    loading = true;
    failed = '';
    try { result = await api.getChannelDiagnosis(channelId); }
    catch (e) { failed = e.message; }
    loading = false;
  }

  const FILE_ROWS = [
    ['videos', 'Videodateien', 'Die Videos selbst'],
    ['thumbnails', 'Vorschaubilder', ''],
    ['sidecars', 'Begleitdatei info.json', 'Metadaten neben dem Video; daraus lässt sich die Datenbank neu aufbauen'],
    ['descriptions', 'Beschreibung als Datei', 'Gezählt werden Videos mit Beschreibung'],
    ['chapters', 'Kapitel als Datei', 'Gezählt werden Videos mit Kapiteln'],
  ];
  const whole = (count) => count.present >= count.total;

  onMount(load);
</script>

{#if failed}
  <div class="tv-fehlertext"><i class="fa-solid fa-triangle-exclamation"></i><span>{failed}</span></div>
{:else if !result}
  <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Dateien werden geprüft ...</div>
{:else}
  {@const files = result.files}
  {@const catalog = result.catalog}
  <div class="raster">
    <section class="tv-karte">
      <h3><i class="fa-solid fa-hard-drive"></i> Dateien
        <button class="tv-knopf ohne klein neu" onclick={load} disabled={loading}>
          <i class="fa-solid fa-rotate {loading ? 'fa-spin' : ''}"></i> Neu prüfen</button></h3>
      <dl class="werte">
        {#each FILE_ROWS as [key, label, hint] (key)}
          {#if files[key].total > 0}
            <dt title={hint}>{label}</dt>
            <dd class:gut={whole(files[key])} class:lueckig={!whole(files[key])}>
              <span class="zahl">{num(files[key].present)}</span> von <span class="zahl">{num(files[key].total)}</span></dd>
          {/if}
        {/each}
        <dt>Untertitel</dt><dd><span class="zahl">{num(files.subtitles)}</span> Videos</dd>
        <dt>Kanalbild</dt><dd class:gut={files.avatar} class:lueckig={!files.avatar}>{files.avatar ? 'vorhanden' : 'fehlt'}</dd>
        <dt>Banner</dt><dd class:gut={files.banner}>{files.banner ? 'vorhanden' : 'keins'}</dd>
      </dl>
    </section>

    <section class="tv-karte">
      <h3><i class="fa-solid fa-database"></i> Katalog</h3>
      <dl class="werte">
        <dt>Einträge</dt><dd class="zahl">{num(catalog.entries)}</dd>
        <dt>Videos, Shorts, Live</dt><dd class="zahl">{num(catalog.videos)} · {num(catalog.shorts)} · {num(catalog.live)}</dd>
        {#each [['no_duration', 'ohne Länge'], ['no_views', 'ohne Aufrufe'], ['no_description', 'ohne Beschreibung'], ['no_title', 'ohne Titel']] as [key, label] (key)}
          <dt>{label}</dt><dd class="zahl" class:lueckig={catalog[key] > 0}>{num(catalog[key])}</dd>
        {/each}
      </dl>
      <p class="hinweis tv-klein">
        {#if catalog.scan_running}Ein Scan läuft gerade.
        {:else if catalog.last_scanned}Ganz gescannt am <span class="zahl">{formatDate(catalog.last_scanned)}</span>; Lücken füllt der nächste Scan.
        {:else}Noch nie ganz gescannt: bekannt sind nur die neuesten Videos.{/if}
      </p>
    </section>
  </div>
{/if}

<style>
  .raster { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: var(--tv-a3); align-items: start; }
  .raster .tv-karte + .tv-karte { margin-top: 0; }
  h3 .neu { margin-left: auto; }
  .werte { display: grid; grid-template-columns: 1fr auto; gap: 6px var(--tv-a4); margin: 0; font-size: var(--tv-gr-klein); }
  .werte dt { color: var(--tv-text-2); }
  .werte dd { margin: 0; text-align: right; }
  .werte dd.gut { color: var(--tv-erfolg); }
  .werte dd.lueckig { color: var(--tv-warnung); }
  .hinweis { margin: var(--tv-a3) 0 0; color: var(--tv-text-3); }
</style>

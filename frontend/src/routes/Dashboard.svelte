<!--
  TubeVault - Übersicht (Gestaltung nach mockups/uebersicht.html)
  Fester Kopf mit Kennzahlen, Diensten und Laden-Zeile; darunter zwei
  Spalten, die jede für sich rollen: links was weitergeht und was neu ist
  (Weiterschauen, Weiterhören, gemerkte Suchen, Neu bei Abos, Zuletzt
  geladen), rechts der
  Betrieb (Speicher, Downloads, Hintergrundarbeiten, Sprachen, Geräte).
  Die Karten rechts laden sich selbst nach. Frisch eingerichtet stehen
  links die ersten Schritte.
  © HalloWelt42 - Private Nutzung
-->
<script>
  import { onMount } from 'svelte';
  import { api } from '../lib/api/client.js';
  import { navigate } from '../lib/router/router.js';
  import { onVideoMutation } from '../lib/utils/videoMutations.js';
  import SystemStatus from '../lib/components/common/SystemStatus.svelte';
  import DeviceList from '../lib/components/remote/DeviceList.svelte';
  import QuickLoad from '../lib/components/overview/QuickLoad.svelte';
  import OverviewSection from '../lib/components/overview/OverviewSection.svelte';
  import OverviewCard from '../lib/components/overview/OverviewCard.svelte';
  import MediaTile from '../lib/components/overview/MediaTile.svelte';
  import ContinueListening from '../lib/components/overview/ContinueListening.svelte';
  import SavedSearches from '../lib/components/overview/SavedSearches.svelte';
  import FirstSteps from '../lib/components/overview/FirstSteps.svelte';
  import ShortcutsCard from '../lib/components/overview/ShortcutsCard.svelte';
  import StorageCard from '../lib/components/overview/StorageCard.svelte';
  import DownloadsCard from '../lib/components/overview/DownloadsCard.svelte';
  import BackgroundCard from '../lib/components/overview/BackgroundCard.svelte';
  import LanguagesCard from '../lib/components/overview/LanguagesCard.svelte';

  const WATCHING = 6;      // Kacheln unter Weiterschauen
  const ROW = 3;           // Kacheln unter Neu bei Abos und Zuletzt geladen
  const SEEN_FROM_S = 5;   // ab dann zeigt eine Kachel den Stand

  let stats = $state(null);
  let watching = $state({ videos: [], total: 0 });
  let feed = $state({ entries: [], total: 0 });
  let recent = $state([]);
  let showShortcuts = $state(false);
  let quickLoad;

  // Frisch eingerichtet: weder Videos noch Abos
  let empty = $derived(!!stats && !stats.total_videos && !stats.total_subscriptions);

  const count = (n) => (n || 0).toLocaleString('de-DE');
  const seen = (position, duration) => (duration && position > SEEN_FROM_S ? position / duration : null);
  const watch = (id) => navigate(`/watch/${id}`);

  async function loadData() {
    const [s, history, news, latest] = await Promise.all([
      api.getStats().catch(() => null),
      api.getHistory({ per_page: WATCHING, state: 'started' }).catch(() => null),
      api.getFeedVideos({ perPage: ROW }).catch(() => null),
      api.getVideos({ per_page: ROW, sort_by: 'download_date', sort_order: 'desc' }).catch(() => null),
    ]);
    if (s) stats = s;
    if (history) watching = { videos: history.videos || [], total: history.total || 0 };
    if (news) feed = { entries: news.entries || [], total: news.total || 0 };
    if (latest) recent = latest.videos || [];
  }

  onMount(() => {
    loadData();
    const stopMutations = onVideoMutation(() => loadData());
    const toggleShortcuts = () => { showShortcuts = !showShortcuts; };
    window.addEventListener('tubevault:show-shortcuts', toggleShortcuts);
    return () => {
      stopMutations();
      window.removeEventListener('tubevault:show-shortcuts', toggleShortcuts);
    };
  });
</script>

<div class="tv-seite">
  <div class="tv-seitenkopf">
    <div class="kopf">
      <h1>Übersicht</h1>
      {#if stats}
        <span class="zahlen tv-leise">
          {#if empty}Noch leer
          {:else}<span class="zahl">{count(stats.total_videos)}</span> in der Bibliothek ·
            <span class="zahl">{count(stats.archives_count)}</span> im Archiv ·
            <span class="zahl">{count(stats.total_subscriptions)}</span> Abos{/if}
        </span>
      {/if}
      <span class="dienste"><SystemStatus /></span>
    </div>
    <QuickLoad bind:this={quickLoad} onQueued={loadData} />
  </div>

  <div class="tv-spalten">
    <div class="tv-rollfeld" data-scroll-root>
      {#if showShortcuts}<ShortcutsCard onclose={() => showShortcuts = false} />{/if}

      {#if empty}
        <FirstSteps onLoad={() => quickLoad.focus()} />
      {:else}
        {#if watching.videos.length}
          <OverviewSection title="Weiterschauen" count={watching.total} more={{ label: 'Verlauf', path: '/history' }}>
            <div class="reihe">
              {#each watching.videos as v (v.id)}
                <MediaTile image={api.thumbnailUrl(v.id)} title={v.title} subtitle={v.channel_name} duration={v.duration}
                           progress={seen(v.position ?? v.last_position, v.duration) ?? 0}
                           language={v.language} languageSource={v.language_source} onopen={() => watch(v.id)} />
              {/each}
            </div>
          </OverviewSection>
        {/if}

        <ContinueListening />

        <SavedSearches />

        {#if feed.entries.length}
          <OverviewSection title="Neu bei Abos" count={feed.total} more={{ label: 'Zum Feed', path: '/feed' }}>
            <div class="reihe">
              {#each feed.entries as e (e.id)}
                <MediaTile image={api.rssThumbUrl(e.video_id)} title={e.title} subtitle={e.channel_name} duration={e.duration}
                           language={e.language} languageSource={e.language_source} onopen={() => watch(e.video_id)} />
              {/each}
            </div>
          </OverviewSection>
        {/if}

        {#if recent.length}
          <OverviewSection title="Zuletzt geladen" more={{ label: 'Zur Bibliothek', path: '/library' }}>
            <div class="reihe">
              {#each recent as v (v.id)}
                <MediaTile image={api.thumbnailUrl(v.id)} title={v.title} subtitle={v.channel_name} duration={v.duration}
                           progress={seen(v.last_position, v.duration)}
                           language={v.language} languageSource={v.language_source} onopen={() => watch(v.id)} />
              {/each}
            </div>
          </OverviewSection>
        {/if}
      {/if}
    </div>

    <div class="tv-rollfeld">
      {#if stats}<StorageCard {stats} />{/if}
      <DownloadsCard />
      <BackgroundCard />
      <LanguagesCard />
      <OverviewCard title="Geräte"><DeviceList heading={false} /></OverviewCard>
    </div>
  </div>
</div>

<style>
  .kopf { display: flex; align-items: baseline; gap: var(--tv-a4); flex-wrap: wrap; }
  h1 { margin: 0; font-size: var(--tv-gr-seite); }
  .dienste { margin-left: auto; }
  .reihe { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--tv-a5) var(--tv-a4); }

  @media (max-width: 1279px) {
    .reihe { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }
</style>

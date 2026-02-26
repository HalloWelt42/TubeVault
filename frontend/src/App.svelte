<script>
  import { route } from './lib/router/router.js';
  import { routeDefinitions } from './lib/router/routes.js';
  import { loadSettings } from './lib/stores/settings.js';
  import { playlistQueue, stopQueue } from './lib/stores/playlistQueue.js';
  import { miniPlayer as miniPlayerStore } from './lib/stores/miniPlayer.js';
  import { get } from 'svelte/store';
  import Header from './lib/components/layout/Header.svelte';
  import Sidebar from './lib/components/layout/Sidebar.svelte';
  import Toast from './lib/components/common/Toast.svelte';
  import ActivityPanel from './lib/components/common/ActivityPanel.svelte';
  import LogTerminal from './lib/components/common/LogTerminal.svelte';
  import './lib/styles/global.css';

  import Dashboard from './routes/Dashboard.svelte';
  import Library from './routes/Library.svelte';
  import Watch from './routes/Watch.svelte';
  import Downloads from './routes/Downloads.svelte';
  import Favorites from './routes/Favorites.svelte';
  import Categories from './routes/Categories.svelte';
  import Settings from './routes/Settings.svelte';
  import Subscriptions from './routes/Subscriptions.svelte';
  import Feed from './routes/Feed.svelte';
  import ChannelDetail from './routes/ChannelDetail.svelte';
  import Archives from './routes/Archives.svelte';
  import History from './routes/History.svelte';
  import Playlists from './routes/Playlists.svelte';
  import Stats from './routes/Stats.svelte';
  import OwnVideos from './routes/OwnVideos.svelte';

  /** Route-Key → Svelte-Komponente */
  const pages = {
    dashboard: Dashboard,
    library: Library,
    watch: Watch,
    downloads: Downloads,
    favorites: Favorites,
    categories: Categories,
    settings: Settings,
    subscriptions: Subscriptions,
    feed: Feed,
    channel: ChannelDetail,
    archives: Archives,
    history: History,
    playlists: Playlists,
    playlist: Playlists,
    stats: Stats,
    'own-videos': OwnVideos,
    category: Categories,
    search: Library,
  };

  import { onConnectionChange } from './lib/api/client.js';

  let CurrentPage = $derived(pages[$route.page] || Dashboard);

  // Einstellungen beim Start laden
  loadSettings();
  let logVisible = $state(false);
  let offline = $state(false);

  // Playlist-Queue schließen wenn Watch-Seite verlassen wird (aber NICHT wenn MiniPlayer übernimmt)
  let prevPage = $state('');
  $effect(() => {
    const page = $route.page;
    if (prevPage === 'watch' && page !== 'watch') {
      // Kurz warten — cleanup() in Watch setzt MiniPlayer erst danach
      setTimeout(() => {
        const mp = get(miniPlayerStore);
        if (!mp.active) stopQueue();
      }, 100);
    }
    prevPage = page;
  });

  onConnectionChange(ok => { offline = !ok; });
</script>

<div class="app">
  {#if offline}
    <div class="offline-banner">
      <i class="fa-solid fa-plug-circle-xmark"></i> Backend nicht erreichbar — Verbindung zum Pi prüfen
    </div>
  {/if}
  <Header />
  <div class="app-body">
    <Sidebar onToggleLog={() => logVisible = !logVisible} logActive={logVisible} />
    <div class="content-area">
      <main class="main-content">
        {#key $route.page + ($route.id || '')}
          <CurrentPage />
        {/key}
      </main>
      <ActivityPanel />
    </div>
  </div>
</div>
<Toast />
<LogTerminal bind:visible={logVisible} />

<style>
  :global(*) {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }

  :global(html) {
    scrollbar-color: var(--scrollbar-thumb) var(--scrollbar-track);
    color-scheme: dark;
  }

  :global(body) {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    line-height: 1.5;
    overflow: hidden;
  }

  :global(::-webkit-scrollbar) { width: 8px; }
  :global(::-webkit-scrollbar-track) { background: var(--scrollbar-track); }
  :global(::-webkit-scrollbar-thumb) { background: var(--scrollbar-thumb); border-radius: 4px; }
  :global(::-webkit-scrollbar-thumb:hover) { background: var(--scrollbar-hover); }

  :global(a) { color: var(--accent-primary); text-decoration: none; }
  :global(a:hover) { text-decoration: underline; }

  /* Material Design Icon-Farben – hohe Sättigung, guter Kontrast */
  :global(.fa-solid.fa-download, .fa-solid.fa-cloud-arrow-down) { color: #42A5F5; }
  :global(.fa-solid.fa-play) { color: #66BB6A; }
  :global(.fa-solid.fa-satellite-dish) { color: #AB47BC; }
  :global(.fa-solid.fa-tower-broadcast) { color: #EF5350; }
  :global(.fa-solid.fa-mobile-screen) { color: #AB47BC; }
  :global(.fa-solid.fa-heart) { color: #EF5350; }
  :global(.fa-solid.fa-star) { color: #FFA726; }
  :global(.fa-solid.fa-chart-simple) { color: #26C6DA; }
  :global(.fa-solid.fa-broom) { color: #8D6E63; }
  :global(.fa-solid.fa-wand-magic-sparkles) { color: #CE93D8; }
  :global(.fa-solid.fa-file-import) { color: #78909C; }
  :global(.fa-solid.fa-box-archive) { color: #A1887F; }
  :global(.fa-solid.fa-image) { color: #4DB6AC; }
  :global(.fa-solid.fa-circle-check) { color: #66BB6A; }
  :global(.fa-solid.fa-triangle-exclamation) { color: #FFA726; }
  :global(.fa-solid.fa-circle-xmark) { color: #EF5350; }
  :global(.fa-solid.fa-bolt) { color: #FFCA28; }
  :global(.fa-regular.fa-keyboard) { color: #90A4AE; }

  /* Buttons überschreiben: Icons in Buttons erben Button-Farbe */
  :global(button .fa-solid, button .fa-regular,
          .btn .fa-solid, .btn .fa-regular,
          .btn-sm .fa-solid, .overlay-btn .fa-solid,
          .type-badge .fa-solid, .badge .fa-solid) {
    color: inherit;
  }

  .app {
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }

  .app-body {
    display: flex;
    flex: 1;
    overflow: hidden;
  }

  .content-area {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .main-content {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    overflow-x: hidden;
  }

  /* Mobile Responsive */
  @media (max-width: 768px) {
    :global(.video-grid) {
      grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)) !important;
      gap: 10px !important;
    }
    :global(.stats-grid) {
      grid-template-columns: repeat(2, 1fr) !important;
    }
    :global(.result-thumb) {
      width: 120px !important;
      min-width: 120px !important;
    }
    :global(.tag-bar) {
      padding: 8px 10px !important;
    }
    :global(.toolbar) {
      flex-direction: column;
      align-items: flex-start !important;
    }
  }

  @media (max-width: 480px) {
    :global(.video-grid) {
      grid-template-columns: 1fr !important;
    }
    :global(.download-input-wrap) {
      flex-direction: column !important;
    }
    :global(.search-box) {
      max-width: 100% !important;
    }
  }

  .offline-banner {
    background: var(--status-error); color: #fff; padding: 8px 16px;
    text-align: center; font-size: 0.82rem; font-weight: 600;
    display: flex; align-items: center; justify-content: center; gap: 8px;
    animation: offlinePulse 2s ease-in-out infinite;
  }
  @keyframes offlinePulse { 50% { opacity: 0.8; } }
</style>

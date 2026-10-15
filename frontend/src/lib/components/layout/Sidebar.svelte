<!--
  TubeVault – Sidebar v1.5.54
  © HalloWelt42 – Private Nutzung
-->
<script>
  import VersionMark from './VersionMark.svelte';
  import { route, navigate } from '../../router/router.js';
  import { getMainRoutes, getSystemRoutes, getAdminRoutes } from '../../router/routes.js';
  import { sidebarOpen } from '../../stores/app.js';
  import { miniPlayer } from '../../stores/miniPlayer.js';
  import { api } from '../../api/client.js';
  import { settings } from '../../stores/settings.js';
  import MiniPlayer from './MiniPlayer.svelte';
  import VideoSuggestion from './VideoSuggestion.svelte';

  let { onToggleLog = () => {}, logActive = false } = $props();

  let badges = $state({});

  // Routen aus zentraler Registry
  // Einträge mit `feature` erscheinen nur, wenn die Einstellung eingeschaltet ist
  const navItems = $derived(getMainRoutes().filter(r => !r.feature || $settings[r.feature] === 'true'));
  const systemItems = getSystemRoutes();
  const adminItems = getAdminRoutes();

  function nav(routeKey) {
    const item = [...navItems, ...systemItems, ...adminItems].find(r => r.key === routeKey);
    if (item) navigate(item.path);
  }

  async function loadBadges() {
    try {
      badges = await api.getBadges();
    } catch { /* still */ }
  }

  $effect(() => {
    loadBadges();
    const iv = setInterval(loadBadges, 8000);
    return () => clearInterval(iv);
  });
</script>

{#if $sidebarOpen}
<aside class="sidebar">
  <nav class="sidebar-nav">
    {#each navItems as item}
      <button
        class="nav-item"
        class:active={$route.page === item.key}
        onclick={() => nav(item.key)}
      >
        <i class={item.icon} style:--symbolfarbe={item.iconColor}></i>
        <span>{item.label}</span>
        {#if item.badge && badges[item.badge]}
          <span class="badge" class:pulse={item.badge === 'active_downloads' && badges[item.badge] > 0}
                class:accent={item.badge === 'new_feed'}>
            {badges[item.badge].toLocaleString('de-DE')}
          </span>
        {/if}
      </button>
    {/each}
  </nav>

  <div class="sidebar-divider"></div>

  <div class="sidebar-section">
    <span class="sidebar-label">System</span>
    {#each systemItems as item}
      <button class="nav-item" class:active={$route.page === item.key} onclick={() => nav(item.key)}>
        <i class={item.icon} style:--symbolfarbe={item.iconColor}></i>
        <span>{item.label}</span>
      </button>
    {/each}
    <button class="nav-item" class:active={logActive} onclick={onToggleLog}>
      <i class="fa-solid fa-terminal"></i>
      <span>Live-Log</span>
      {#if logActive}
        <span class="badge accent">ON</span>
      {/if}
    </button>
  </div>

  <!-- Admin: nur als DEZENTER Link unten; das komplette Admin-Menü liegt im
       eigenen Admin-Layout (AdminLayout.svelte), nicht hier. -->
  {#if adminItems.length > 0}
    <button class="nav-item admin-link" onclick={() => nav('admin')} title="Admin-Bereich">
      <i class="fa-solid fa-screwdriver-wrench"></i>
      <span>Admin</span>
    </button>
  {/if}

  <!-- Mini-Player oder Video-Vorschlag -->
  <div class="sidebar-player-area">
    {#if $miniPlayer.active}
      <MiniPlayer />
    {:else if $route.page !== 'watch'}
      <VideoSuggestion />
    {/if}
  </div>

  <div class="sidebar-footer">
    <VersionMark />
  </div>
</aside>
{/if}

<style>
  /* Gestaltung nach mockups/stil.css (Schale: .seite, .navi, .zaehler) */
  .sidebar {
    width: 256px;
    background: var(--tv-leiste);
    border-right: 1px solid var(--tv-rand);
    overflow-y: auto;
    padding: var(--tv-a3) var(--tv-a2);
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
  }
  .sidebar-nav, .sidebar-section { display: flex; flex-direction: column; gap: 2px; }

  .nav-item {
    display: flex; align-items: center; gap: var(--tv-a3);
    width: 100%; padding: 9px var(--tv-a3);
    background: none; border: none; border-radius: var(--tv-ecke);
    color: var(--tv-text-2); font-size: var(--tv-gr-text); font-weight: 500; text-align: left;
    cursor: pointer; transition: background var(--tv-schnell), color var(--tv-schnell);
  }
  /* Symbole behalten ihre eigene Farbe (iconColor im Routen-Verzeichnis), sonst gedämpft */
  .nav-item i { width: 20px; text-align: center; color: var(--symbolfarbe, var(--tv-text-3)); }
  .nav-item:hover { background: var(--tv-flaeche); color: var(--tv-text); }
  .nav-item.active { background: var(--tv-karte-2); color: var(--tv-text); font-weight: 600; }
  .nav-item.active i { color: var(--symbolfarbe, var(--tv-akzent)); }

  .badge {
    margin-left: auto; min-width: 26px; height: 22px; padding: 0 7px;
    display: inline-grid; place-items: center;
    font-family: var(--tv-schrift-zahl); font-size: var(--tv-gr-marke); font-weight: 600;
    font-variant-numeric: tabular-nums;
    background: var(--tv-karte-2); color: var(--tv-text-2); border-radius: var(--tv-ecke-klein);
  }
  .badge.accent { background: rgba(var(--tv-akzent-rgb), 0.16); color: var(--tv-akzent); }
  .badge.pulse { background: rgba(var(--tv-info-rgb), 0.2); color: var(--tv-info); animation: badge-pulse 2s ease-in-out infinite; }
  @keyframes badge-pulse { 50% { opacity: 0.6; } }

  .sidebar-divider { height: 1px; background: var(--tv-rand); margin: var(--tv-a3) var(--tv-a2); }
  .sidebar-label {
    padding: var(--tv-a2) var(--tv-a3) var(--tv-a1);
    font-size: var(--tv-gr-marke); font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
    color: var(--tv-text-3);
  }

  .sidebar-player-area { margin-top: auto; padding: var(--tv-a2) 0 var(--tv-a1); }
  .sidebar-footer {
    padding: var(--tv-a2) var(--tv-a3); border-top: 1px solid var(--tv-rand);
    font-size: var(--tv-gr-marke); color: var(--tv-text-3); white-space: nowrap;
  }

  @media (max-width: 768px) {
    .sidebar {
      position: fixed; top: 60px; left: 0; bottom: 0; z-index: 90;
      box-shadow: var(--tv-schatten);
    }
  }
</style>

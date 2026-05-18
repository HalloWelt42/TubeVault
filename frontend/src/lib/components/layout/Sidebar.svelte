<!--
  TubeVault – Sidebar v1.5.54
  © HalloWelt42 – Private Nutzung
-->
<script>
  import { route, navigate } from '../../router/router.js';
  import { getMainRoutes, getSystemRoutes, getAdminRoutes } from '../../router/routes.js';
  import { sidebarOpen } from '../../stores/app.js';
  import { miniPlayer } from '../../stores/miniPlayer.js';
  import { api } from '../../api/client.js';
  import MiniPlayer from './MiniPlayer.svelte';
  import VideoSuggestion from './VideoSuggestion.svelte';

  let { onToggleLog = () => {}, logActive = false } = $props();

  let badges = $state({});

  // Routen aus zentraler Registry
  const navItems = getMainRoutes();
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
        <i class={item.icon}></i>
        <span>{item.label}</span>
        {#if item.badge && badges[item.badge]}
          <span class="badge" class:pulse={item.badge === 'active_downloads' && badges[item.badge] > 0}
                class:accent={item.badge === 'new_feed'}>
            {badges[item.badge]}
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
        <i class={item.icon}></i>
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
    © HalloWelt42 – TubeVault
  </div>
</aside>
{/if}

<style>
  .sidebar {
    width: 220px;
    background: var(--bg-secondary);
    border-right: 1px solid var(--border-primary);
    overflow-y: auto;
    padding: 12px 8px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
  }

  .sidebar-nav {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .nav-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 14px;
    border-radius: 8px;
    background: none;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    font-size: 0.88rem;
    width: 100%;
    text-align: left;
    transition: all 0.15s;
  }
  .nav-item i { width: 20px; text-align: center; font-size: 0.95rem; }

  /* Material-Design Icon-Farben – NUR in der Sidebar (scoped).
     Dank Svelte-scoped-CSS sind diese Regeln automatisch auf dieses
     Component beschränkt, ohne :global oder !important. */
  .nav-item :global(.fa-solid.fa-download),
  .nav-item :global(.fa-solid.fa-cloud-arrow-down) { color: #42A5F5; }
  .nav-item :global(.fa-solid.fa-play) { color: #66BB6A; }
  .nav-item :global(.fa-solid.fa-satellite-dish) { color: #AB47BC; }
  .nav-item :global(.fa-solid.fa-tower-broadcast) { color: #EF5350; }
  .nav-item :global(.fa-solid.fa-mobile-screen) { color: #AB47BC; }
  .nav-item :global(.fa-solid.fa-heart) { color: #EF5350; }
  .nav-item :global(.fa-solid.fa-star) { color: #FFA726; }
  .nav-item :global(.fa-solid.fa-chart-simple) { color: #26C6DA; }
  .nav-item :global(.fa-solid.fa-broom) { color: #8D6E63; }
  .nav-item :global(.fa-solid.fa-wand-magic-sparkles) { color: #CE93D8; }
  .nav-item :global(.fa-solid.fa-file-import) { color: #78909C; }
  .nav-item :global(.fa-solid.fa-box-archive) { color: #A1887F; }
  .nav-item :global(.fa-solid.fa-image) { color: #4DB6AC; }
  .nav-item :global(.fa-solid.fa-circle-check) { color: #66BB6A; }
  .nav-item :global(.fa-solid.fa-triangle-exclamation) { color: #FFA726; }
  .nav-item :global(.fa-solid.fa-circle-xmark) { color: #EF5350; }
  .nav-item :global(.fa-solid.fa-bolt) { color: #FFCA28; }
  .nav-item :global(.fa-regular.fa-keyboard) { color: #90A4AE; }
  .nav-item:hover {
    background: var(--bg-hover);
    color: var(--text-primary);
  }
  .nav-item.active {
    background: var(--accent-muted);
    color: var(--accent-primary);
    font-weight: 600;
  }

  .badge {
    margin-left: auto;
    font-size: 0.65rem;
    font-weight: 700;
    padding: 1px 7px;
    border-radius: 10px;
    background: var(--bg-tertiary);
    color: var(--text-tertiary);
    min-width: 20px;
    text-align: center;
  }
  .badge.accent {
    background: var(--accent-primary);
    color: #fff;
  }
  .badge.pulse {
    background: var(--status-info);
    color: #fff;
    animation: badge-pulse 2s ease-in-out infinite;
  }
  @keyframes badge-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
  }

  .sidebar-divider {
    height: 1px;
    background: var(--border-primary);
    margin: 12px 8px;
  }

  .sidebar-section { display: flex; flex-direction: column; gap: 2px; }

  .sidebar-label {
    font-size: 0.72rem;
    text-transform: uppercase;
    color: var(--text-tertiary);
    letter-spacing: 0.06em;
    padding: 8px 14px 4px;
    font-weight: 600;
  }

  .sidebar-footer {
    padding: 8px 14px;
    font-size: 0.62rem;
    color: var(--text-tertiary);
    border-top: 1px solid var(--border-primary);
    white-space: nowrap;
  }

  .sidebar-player-area {
    margin-top: auto;
    padding: 8px 0 4px;
  }

  @media (max-width: 768px) {
    .sidebar {
      position: fixed;
      top: 56px;
      left: 0;
      bottom: 0;
      z-index: 90;
      width: 240px;
      box-shadow: 4px 0 20px rgba(0,0,0,0.3);
    }
  }
</style>

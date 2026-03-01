<!--
  TubeVault -  Sidebar v1.5.55
  © HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
  SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
-->
<script>
  import { route, navigate } from '../../router/router.js';
  import { getMainRoutes, getSystemRoutes } from '../../router/routes.js';
  import { sidebarOpen } from '../../stores/app.js';
  import { miniPlayer } from '../../stores/miniPlayer.js';
  import { api } from '../../api/client.js';
  import MiniPlayer from './MiniPlayer.svelte';
  import VideoSuggestion from './VideoSuggestion.svelte';
  import DonateOverlay from '../common/DonateOverlay.svelte';

  let { onToggleLog = () => {}, logActive = false } = $props();

  let badges = $state({});
  let showDonate = $state(false);

  // Routen aus zentraler Registry
  const navItems = getMainRoutes();
  const systemItems = getSystemRoutes();

  function nav(routeKey) {
    const item = [...navItems, ...systemItems].find(r => r.key === routeKey);
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

  <!-- Mini-Player oder Video-Vorschlag -->
  <div class="sidebar-player-area">
    {#if $miniPlayer.active}
      <MiniPlayer />
    {:else if $route.page !== 'watch'}
      <VideoSuggestion />
    {/if}
  </div>

  <div class="sidebar-footer">
    © HalloWelt42 -  TubeVault
  </div>
  <button class="donate-btn" onclick={() => showDonate = true}>
    Jetzt Danke sagen! ❤️
  </button>
</aside>

<DonateOverlay bind:visible={showDonate} />
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

  .donate-btn {
    display: block;
    width: calc(100% - 16px);
    margin: 6px 8px 8px;
    padding: 6px 10px;
    border-radius: 8px;
    background: rgba(239, 68, 68, 0.12);
    border: 1px solid rgba(239, 68, 68, 0.25);
    color: #ef4444;
    cursor: pointer;
    font-size: 0.72rem;
    font-weight: 600;
    text-align: center;
    white-space: normal;
    line-height: 1.3;
    transition: all 0.15s;
  }
  .donate-btn:hover {
    background: rgba(239, 68, 68, 0.2);
    border-color: #ef4444;
    transform: translateY(-1px);
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

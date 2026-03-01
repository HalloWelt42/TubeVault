<!--
  TubeVault -  Header v1.5.88
  Mit integrierter Universal-Suche (SearchDropdown).
  © HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
  SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
-->
<script>
  import { route, navigate } from '../../router/router.js';
  import { sidebarOpen } from '../../stores/app.js';
  import { theme } from '../../stores/theme.js';
  import SearchDropdown from './SearchDropdown.svelte';

  function toggleSidebar() {
    sidebarOpen.update(v => !v);
  }
</script>

<header class="header">
  <div class="header-left">
    <button class="btn-icon" onclick={toggleSidebar} title="Sidebar">
      <i class="fa-solid fa-bars"></i>
    </button>
    <button class="logo" onclick={() => navigate('/')}>
      <svg width="28" height="28" viewBox="0 0 32 32"><rect width="32" height="32" rx="6" fill="var(--accent-primary)"/><polygon points="13,8 13,24 25,16" fill="white"/></svg>
      <span class="logo-text">TubeVault</span>
    </button>
  </div>

  <div class="header-center">
    <SearchDropdown />
  </div>

  <div class="header-right">
    <button class="btn-icon" onclick={() => navigate('downloads')} title="Downloads">
      <i class="fa-solid fa-download"></i>
    </button>
    <button class="btn-icon" onclick={() => theme.toggle()} title="Theme wechseln">
      {#if $theme === 'dark'}
        <i class="fa-solid fa-sun"></i>
      {:else}
        <i class="fa-solid fa-moon"></i>
      {/if}
    </button>
    <button class="btn-icon" onclick={() => navigate('settings')} title="Einstellungen">
      <i class="fa-solid fa-gear"></i>
    </button>
  </div>
</header>

<style>
  .header {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 10px 20px;
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border-primary);
    height: 56px;
    position: sticky;
    top: 0;
    z-index: 100;
  }
  .header-left { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
  .header-center { flex: 1; max-width: 600px; margin: 0 auto; }
  .header-right { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
  .logo {
    display: flex; align-items: center; gap: 10px;
    background: none; border: none; cursor: pointer; color: var(--text-primary);
  }
  .logo-text { font-size: 1.2rem; font-weight: 700; letter-spacing: -0.02em; }
  .btn-icon {
    display: flex; align-items: center; justify-content: center;
    width: 36px; height: 36px; background: none; border: none;
    color: var(--text-secondary); cursor: pointer; border-radius: 8px;
    transition: all 0.15s; font-size: 1rem;
  }
  .btn-icon:hover { background: var(--bg-hover); color: var(--text-primary); }
</style>

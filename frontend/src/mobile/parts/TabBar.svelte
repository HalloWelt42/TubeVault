<!-- Untere Leiste: die vier Bereiche der Mobil-Ansicht. -->
<script>
  import { route, go } from '../router.js';

  const tabs = [
    { view: 'start', path: '/', label: 'Start', icon: 'fa-house' },
    { view: 'videos', path: '/videos', label: 'Videos', icon: 'fa-photo-film' },
    { view: 'suche', path: '/suche', label: 'Suche', icon: 'fa-magnifying-glass' },
    { view: 'neu', path: '/neu', label: 'Neu', icon: 'fa-rss' },
  ];
</script>

<nav class="tabbar">
  {#each tabs as tab (tab.view)}
    <button class:active={$route.view === tab.view} onclick={() => go(tab.path)}
            aria-current={$route.view === tab.view ? 'page' : undefined}>
      <i class="fa-solid {tab.icon}"></i>
      <span>{tab.label}</span>
    </button>
  {/each}
</nav>

<style>
  .tabbar {
    flex: 0 0 auto; display: flex;
    padding: 0 var(--m-safe-right) var(--m-safe-bottom) var(--m-safe-left);
    background: var(--m-surface); border-top: 1px solid var(--m-line);
  }
  button {
    flex: 1; height: var(--m-tabbar);
    display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px;
    color: var(--m-faint); font-size: 0.7rem; font-weight: 600; letter-spacing: 0.03em;
  }
  button i { font-size: 1.15rem; }
  button.active { color: var(--m-accent); }
</style>

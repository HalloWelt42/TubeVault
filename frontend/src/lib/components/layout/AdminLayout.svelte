<!--
  TubeVault – Admin Layout v1.0.0
  Komplett eigene Seite mit eigenem Menü. Keine Haupt-Sidebar,
  kein ActivityPanel – nur Admin-relevante Bereiche.
-->
<script>
  import { route, navigate } from '../../router/router.js';
  import { getAdminRoutes } from '../../router/routes.js';

  let { children } = $props();

  const adminItems = getAdminRoutes();

  function isActive(key) {
    return $route.page === key;
  }

  function backToApp() {
    navigate('/');
  }
</script>

<div class="admin-layout">
  <aside class="admin-sidebar">
    <div class="admin-brand">
      <i class="fa-solid fa-screwdriver-wrench"></i>
      <span>Admin</span>
    </div>

    <nav class="admin-nav">
      {#each adminItems as item}
        <button
          class="admin-nav-item"
          class:active={isActive(item.key)}
          onclick={() => navigate(item.path)}
        >
          <i class={item.icon}></i>
          <span>{item.label}</span>
        </button>
      {/each}
    </nav>

    <div class="admin-spacer"></div>

    <button class="admin-back" onclick={backToApp} title="Zurück zur App">
      <i class="fa-solid fa-arrow-left"></i>
      <span>Zur App</span>
    </button>
  </aside>

  <main class="admin-main">
    {@render children?.()}
  </main>
</div>

<style>
  .admin-layout {
    display: flex;
    width: 100%;
    height: 100%;
    background: var(--bg-primary);
  }

  .admin-sidebar {
    width: 220px; flex-shrink: 0;
    background: var(--bg-secondary);
    border-right: 1px solid var(--border-primary);
    display: flex; flex-direction: column;
    padding: 16px 10px;
  }

  .admin-brand {
    display: flex; align-items: center; gap: 10px;
    padding: 8px 12px 16px;
    font-size: 1rem; font-weight: 700;
    color: var(--accent-primary);
    border-bottom: 1px solid var(--border-primary);
    margin-bottom: 12px;
  }
  .admin-brand i { font-size: 1.1rem; }

  .admin-nav {
    display: flex; flex-direction: column; gap: 2px;
  }
  .admin-nav-item {
    display: flex; align-items: center; gap: 12px;
    padding: 10px 14px;
    border: none; background: none; cursor: pointer;
    color: var(--text-secondary); font-size: 0.88rem;
    text-align: left; border-radius: 8px;
    transition: background 0.12s;
  }
  .admin-nav-item:hover { background: var(--bg-hover); color: var(--text-primary); }
  .admin-nav-item.active {
    background: var(--accent-muted); color: var(--accent-primary); font-weight: 600;
  }
  .admin-nav-item i { width: 18px; text-align: center; font-size: 0.92rem; }

  .admin-spacer { flex: 1; }

  .admin-back {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 14px; margin-top: 12px;
    background: none; border: 1px solid var(--border-primary);
    border-radius: 8px; cursor: pointer;
    color: var(--text-tertiary); font-size: 0.85rem;
    transition: all 0.12s;
  }
  .admin-back:hover { border-color: var(--accent-primary); color: var(--accent-primary); }

  .admin-main {
    flex: 1; min-width: 0;
    overflow-y: auto; overflow-x: hidden;
  }
</style>

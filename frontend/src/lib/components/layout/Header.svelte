<!--
  TubeVault – Header v1.5.88
  Mit dem Suchfeld samt Aufklappliste (SearchBox).
  © HalloWelt42 – Private Nutzung
-->
<script>
  import { route, navigate } from '../../router/router.js';
  import { sidebarOpen } from '../../stores/app.js';
  import SearchBox from './SearchBox.svelte';
  import UpdateHint from './UpdateHint.svelte';

  function toggleSidebar() {
    sidebarOpen.update(v => !v);
  }
</script>

<header class="header">
  <div class="header-left">
    <button class="btn-icon" onclick={toggleSidebar} title="Seitenleiste ein- oder ausblenden">
      <i class="fa-solid fa-bars"></i>
    </button>
    <button class="logo" onclick={() => navigate('/')}>
      <img class="logo-mark" src="/favicon.svg" alt="" />
      <span class="logo-text">TubeVault</span>
    </button>
  </div>

  <div class="header-center">
    <SearchBox />
  </div>

  <div class="header-right">
    <UpdateHint />
    <button class="btn-icon" onclick={() => navigate('/downloads')} title="Downloads">
      <i class="fa-solid fa-download"></i>
    </button>
    <button class="btn-icon" onclick={() => navigate('/settings')} title="Einstellungen">
      <i class="fa-solid fa-gear"></i>
    </button>
  </div>
</header>

<style>
  /* Gestaltung nach mockups/stil.css (Schale: .kopf, .marke, .suche) */
  .header {
    display: flex; align-items: center; gap: var(--tv-a4);
    height: 60px; padding: 0 var(--tv-a4);
    background: var(--tv-leiste); border-bottom: 1px solid var(--tv-rand);
    position: sticky; top: 0; z-index: 100;
  }
  .header-left { display: flex; align-items: center; gap: var(--tv-a2); flex-shrink: 0; width: calc(256px - var(--tv-a4)); }
  .header-center { flex: 1; max-width: 680px; }
  .header-right { display: flex; align-items: center; gap: var(--tv-a1); flex-shrink: 0; margin-left: auto; }
  .logo {
    display: flex; align-items: center; gap: 10px;
    background: none; border: none; cursor: pointer; color: var(--tv-text);
  }
  /* Das App-Symbol selbst (eine Quelle: public/favicon.svg) */
  .logo-mark { width: 34px; height: 34px; display: block; border-radius: var(--tv-ecke-klein); }
  .logo-text { font-size: 20px; font-weight: 700; letter-spacing: 0.02em; }
  .btn-icon {
    display: grid; place-items: center; width: 40px; height: 40px;
    background: none; border: 1px solid transparent; border-radius: var(--tv-ecke);
    color: var(--tv-text-2); cursor: pointer; font-size: 17px;
    transition: background var(--tv-schnell), color var(--tv-schnell);
  }
  .btn-icon:hover { background: var(--tv-karte); color: var(--tv-text); }
</style>

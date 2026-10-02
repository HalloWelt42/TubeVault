<!--
  TubeVault – Mobil-Ansicht
  Vier Bereiche in einer unteren Leiste, das Video legt sich darüber. Besuchte
  Bereiche bleiben eingehängt: Wer aus einem Video zurückkommt, steht wieder
  an derselben Stelle der Liste.
-->
<script>
  import { loadSettings } from '../lib/stores/settings.js';
  import { route } from './router.js';
  import { notice } from './notice.js';
  import TabBar from './parts/TabBar.svelte';
  import Start from './views/Start.svelte';
  import Videos from './views/Videos.svelte';
  import Suche from './views/Suche.svelte';
  import Neu from './views/Neu.svelte';
  import Video from './views/Video.svelte';

  const tabViews = { start: Start, videos: Videos, suche: Suche, neu: Neu };

  let ready = $state(false);
  let activeTab = $state('start');
  let visited = $state(new Set());

  loadSettings().finally(() => { ready = true; });

  $effect(() => {
    const view = $route.view;
    if (view in tabViews) {
      activeTab = view;
      if (!visited.has(view)) visited = new Set([...visited, view]);
    } else if (visited.size === 0) {
      visited = new Set(['start']);   // direkter Einstieg über ein Video
    }
  });
</script>

<div class="shell">
  <main class="views">
    {#if ready}
      {#each Object.entries(tabViews) as [name, View] (name)}
        {#if visited.has(name)}
          <div class="pane" hidden={name !== activeTab}><View /></div>
        {/if}
      {/each}
      {#if $route.view === 'video'}
        {#key $route.id}
          <div class="pane over"><Video id={$route.id} /></div>
        {/key}
      {/if}
    {/if}
    {#if $notice}
      <div class="notice {$notice.kind}" role="status">{$notice.text}</div>
    {/if}
  </main>
  {#if $route.view !== 'video'}<TabBar />{/if}
</div>

<style>
  .shell { height: 100dvh; display: flex; flex-direction: column; background: var(--m-bg); }
  .views { position: relative; flex: 1; min-height: 0; }
  .pane { position: absolute; inset: 0; }
  .pane[hidden] { display: none; }
  .pane.over { z-index: 2; background: var(--m-bg); }
  .notice {
    position: absolute; left: 12px; right: 12px; bottom: 12px; z-index: 5;
    padding: 12px 16px; border-radius: var(--m-radius);
    background: var(--m-surface-2); border: 1px solid var(--m-line);
    font-weight: 600; text-align: center;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .notice.ok { border-color: var(--m-ok); }
  .notice.warn { border-color: var(--m-warn); }
</style>

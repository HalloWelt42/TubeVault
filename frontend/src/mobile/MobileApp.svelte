<!--
  TubeVault – Mobil-Ansicht
  Die Bereiche liegen in einer unteren Leiste, Playlist und Video legen sich darüber. Besuchte
  Bereiche bleiben eingehängt: Wer aus einem Video zurückkommt, steht wieder
  an derselben Stelle der Liste.
-->
<script>
  import { loadSettings } from '../lib/stores/settings.js';
  import { go, route } from './router.js';
  import { say } from './notice.js';
  import { remote } from '../lib/stores/remote.svelte.js';
  import VersionBar from '../lib/components/common/VersionBar.svelte';
  import { startVersionWatch } from '../lib/utils/versionWatch.js';
  import { notice } from './notice.js';
  import TabBar from './parts/TabBar.svelte';
  import Start from './views/Start.svelte';
  import Videos from './views/Videos.svelte';
  import Suche from './views/Suche.svelte';
  import Neu from './views/Neu.svelte';
  import Video from './views/Video.svelte';
  import Listen from './views/Listen.svelte';
  import Liste from './views/Liste.svelte';
  import Musik from './views/Musik.svelte';
  import Jetzt from './views/Jetzt.svelte';
  import MusicMiniBar from './parts/MusicMiniBar.svelte';
  import Meldungen from './parts/Meldungen.svelte';
  import Fern from './views/Fern.svelte';

  const tabViews = { start: Start, videos: Videos, musik: Musik, listen: Listen, suche: Suche, neu: Neu };

  let ready = $state(false);
  let activeTab = $state('start');
  let visited = $state(new Set());

  loadSettings().finally(() => { ready = true; });
  // Nach einem Update neu laden: sofort, wenn nichts spielt, sonst beim nächsten Anhalten
  startVersionWatch(route, { eager: true });

  // Fernsteuerung: dieses Handy ist ein Gerät; übernommene Wiedergaben öffnen sich hier
  remote.start({
    notify: (text) => say(text),
    openVideo: (v) => go(`/video/${v.id}`, { liste: v.liste?.startsWith('playlist:') ? v.liste.slice(9) : null,
                                              t: Math.floor(v.stelle) || null, weiter: 1 }),
    openPlayer: () => go('/jetzt'),
  });

  $effect(() => {
    const view = $route.view;
    if (view in tabViews) {
      activeTab = view;
      if (!visited.has(view)) visited = new Set([...visited, view]);
    } else if (view === 'liste') {
      activeTab = 'listen';
      if (!visited.has('listen')) visited = new Set([...visited, 'listen']);
    } else if (visited.size === 0) {
      visited = new Set(['start']);   // direkter Einstieg über ein Video
    }
  });
</script>

<div class="shell">
  <VersionBar />
  <main class="views">
    {#if ready}
      {#each Object.entries(tabViews) as [name, View] (name)}
        {#if visited.has(name)}
          <div class="pane" hidden={name !== activeTab}><View /></div>
        {/if}
      {/each}
      {#if $route.view === 'liste'}
        {#key $route.id}
          <div class="pane over"><Liste id={$route.id} /></div>
        {/key}
      {/if}
      {#if $route.view === 'jetzt'}
        <div class="pane over"><Jetzt /></div>
      {/if}
      {#if $route.view === 'fern'}
        <div class="pane over"><Fern id={$route.params.id || null} /></div>
      {/if}
      {#if $route.view === 'video'}
        <!-- Innerhalb einer Playlist bleibt der Player derselbe: nur so darf
             das Telefon das nächste Stück ohne erneuten Tipp starten. -->
        {#key $route.params.liste ? `liste-${$route.params.liste}` : $route.id}
          <div class="pane over">
            <Video id={$route.id} listId={$route.params.liste || null} shuffle={$route.params.zufall === '1'}
                   startAt={Number($route.params.t) || 0} handoff={$route.params.weiter === '1'} />
          </div>
        {/key}
      {/if}
    {/if}
    <div class="meldungen">
      {#if $notice}
        <div class="notice {$notice.kind}" role="status">{$notice.text}</div>
      {/if}
      <Meldungen />
    </div>
  </main>
  {#if $route.view !== 'video' && $route.view !== 'jetzt' && $route.view !== 'fern'}
    <MusicMiniBar />
    <TabBar />
  {/if}
</div>

<style>
  /* Der obere Schutzbereich (Uhrzeit, Kamera) gilt einmal für die ganze Ansicht:
     nichts, auch keine Hinweisleiste, liegt darunter. Die Ansichten rechnen ihn
     deshalb nicht noch einmal ein (--m-safe-top innen 0). */
  .shell { height: 100dvh; display: flex; flex-direction: column; background: var(--m-bg);
           padding-top: env(safe-area-inset-top, 0px); }
  .shell > :global(*) { --m-safe-top: 0px; }
  .views { position: relative; flex: 1; min-height: 0; }
  .pane { position: absolute; inset: 0; }
  .pane[hidden] { display: none; }
  .pane.over { z-index: 2; background: var(--m-bg); }
  /* Kurze Hinweise und Meldungen (mit Rückgängig) unten über allen Ansichten */
  .meldungen {
    position: absolute; left: 12px; right: 12px; bottom: 12px; z-index: 5;
    display: flex; flex-direction: column; gap: 8px; pointer-events: none;
  }
  .meldungen > :global(*) { pointer-events: auto; }
  .notice {
    padding: 12px 16px; border-radius: var(--m-radius);
    background: var(--m-surface-2); border: 1px solid var(--m-line);
    font-weight: 600; text-align: center;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .notice.ok { border-color: var(--m-ok); }
  .notice.warn { border-color: var(--m-warn); }
</style>

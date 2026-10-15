<!--
  Tastenkürzel (öffnet sich mit "?"): die Sprungziele aus stores/keyboard.js
  mit den Namen der Seiten aus router/routes.js, dazu die festen Kürzel.
-->
<script>
  import { shortcuts } from '../../stores/keyboard.js';
  import { routeDefinitions } from '../../router/routes.js';

  let { onclose } = $props();

  const pageName = (path) => Object.values(routeDefinitions).find((r) => r.path === path)?.label || path;
  const entries = [
    ...Object.entries(shortcuts).map(([key, path]) => [`Alt + ${key.toUpperCase()}`, pageName(path)]),
    ['S oder Strg + K', 'Suchfeld'],
    ['Esc', 'Suchfeld verlassen'],
    ['?', 'Tastenkürzel ein- und ausblenden'],
  ];
</script>

<section class="kuerzel">
  <div class="kopf">
    <h2><i class="fa-regular fa-keyboard"></i> Tastenkürzel</h2>
    <button class="tv-knopf ohne symbol klein" onclick={onclose} title="Schließen" aria-label="Schließen"><i class="fa-solid fa-xmark"></i></button>
  </div>
  <div class="liste">
    {#each entries as [keys, label] (keys)}
      <div class="eintrag"><kbd>{keys}</kbd><span>{label}</span></div>
    {/each}
  </div>
</section>

<style>
  .kuerzel { margin-bottom: var(--tv-a5); padding: var(--tv-a4); border-radius: var(--tv-ecke); background: var(--tv-flaeche); }
  .kopf { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--tv-a3); }
  h2 { margin: 0; font-size: var(--tv-gr-titel); }
  h2 i { color: var(--tv-akzent); }
  .liste { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: var(--tv-a2) var(--tv-a4); }
  .eintrag { display: flex; align-items: center; gap: var(--tv-a3); color: var(--tv-text-2); }
  kbd { min-width: 96px; padding: 2px 8px; border-radius: var(--tv-ecke-klein); background: var(--tv-karte-3);
        color: var(--tv-text); font-family: var(--tv-schrift-zahl); font-size: var(--tv-gr-klein); text-align: center; }
</style>

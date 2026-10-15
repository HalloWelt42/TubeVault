<!--
  Abschnitt der Übersicht (linke Spalte): Überschrift, optional Anzahl und ein
  Verweis auf die zugehörige Seite, darunter der Inhalt.
-->
<script>
  import { navigate } from '../../router/router.js';

  /** more: { label, path, params? } für den Verweis rechts im Kopf */
  let { title, count = null, more = null, children } = $props();
</script>

<section class="abschnitt">
  <div class="kopf">
    <h2>{title}</h2>
    {#if count !== null}<span class="zahl tv-schwach">{count.toLocaleString('de-DE')}</span>{/if}
    {#if more}<button class="mehr" onclick={() => navigate(more.path, more.params)}>{more.label} <i class="fa-solid fa-arrow-right"></i></button>{/if}
  </div>
  {@render children()}
</section>

<style>
  .abschnitt { margin-bottom: var(--tv-a5); }
  .kopf { display: flex; align-items: baseline; gap: var(--tv-a3); margin-bottom: var(--tv-a3); }
  h2 { margin: 0; font-size: var(--tv-gr-titel); }
  .mehr { margin-left: auto; padding: 0; border: 0; background: none; color: var(--tv-akzent); font: inherit;
          font-weight: 600; font-size: var(--tv-gr-klein); cursor: pointer; }
  .mehr:hover { color: var(--tv-akzent-hell); }
</style>

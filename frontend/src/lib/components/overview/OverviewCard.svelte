<!--
  Karte der Übersicht (rechte Spalte): kleine Überschrift in Versalien,
  optional ein Verweis auf die zugehörige Seite, darunter der Inhalt.
-->
<script>
  import { navigate } from '../../router/router.js';

  /** more: { label, path, params? } für den Verweis rechts im Kopf; extra: weitere Teile im Kopf */
  let { title, more = null, extra = null, children } = $props();
</script>

<section class="karte">
  <h3>
    <span class="tv-etikett">{title}</span>
    {#if extra}{@render extra()}{/if}
    {#if more}<button class="mehr" onclick={() => navigate(more.path, more.params)}>{more.label}</button>{/if}
  </h3>
  {@render children()}
</section>

<style>
  .karte { padding: var(--tv-a4); border-radius: var(--tv-ecke); background: var(--tv-flaeche); }
  .karte + :global(.karte) { margin-top: var(--tv-a3); }
  h3 { display: flex; align-items: center; gap: var(--tv-a2); min-height: 24px; margin: 0 0 var(--tv-a3); font-size: inherit; }
  .mehr { margin-left: auto; padding: 0; border: 0; background: none; color: var(--tv-akzent); font: inherit;
          font-weight: 600; font-size: var(--tv-gr-klein); cursor: pointer; }
  .mehr:hover { color: var(--tv-akzent-hell); }
</style>

<!--
  Text mit hervorgehobenen Fundstellen (utils/searchHighlight.js).
  terms: die Begriffe, wie die Suche sie liefert ([{ words, prefix }]).
-->
<script>
  import { markParts } from '../../utils/searchHighlight.js';

  let { text = '', terms = [] } = $props();
  let parts = $derived(markParts(text, terms));
</script>

{#each parts as part, i (i)}{#if part.hit}<mark>{part.text}</mark>{:else}{part.text}{/if}{/each}

<style>
  mark { padding: 0 2px; border-radius: 2px; background: rgba(var(--tv-akzent-rgb), 0.22); color: var(--tv-text); }
</style>

<!--
  Regeln einer Kategorie als Chips: Kanal, Schlagwort, "inhaltlich wie"
  (in der Farbe der Bedeutungssuche). Mit onOpen führt ein Klick zu den Regeln.
-->
<script>
  import { kindOf, ruleText } from '../../utils/categoryRules.js';

  let { rules = [], onOpen = null } = $props();
</script>

{#each rules as rule (rule.id ?? `${rule.kind}:${rule.value}`)}
  {@const kind = kindOf(rule.kind)}
  {#if onOpen}
    <button class="regel" class:bedeutung={rule.kind === 'semantic'} onclick={onOpen}
            title="{kind.label}: {rule.kind === 'channel' ? ruleText(rule) : rule.value} - Regeln bearbeiten">
      <i class="fa-solid {kind.icon}"></i><span>{ruleText(rule)}</span></button>
  {:else}
    <span class="regel" class:bedeutung={rule.kind === 'semantic'} title="{kind.label}: {rule.kind === 'channel' ? ruleText(rule) : rule.value}">
      <i class="fa-solid {kind.icon}"></i><span>{ruleText(rule)}</span></span>
  {/if}
{/each}

<style>
  .regel { display: inline-flex; align-items: center; gap: 6px; min-height: 26px; max-width: 100%; padding: 2px 8px;
           border: 0; border-radius: var(--tv-ecke-klein); background: var(--tv-karte-2); color: var(--tv-text-2);
           font-family: inherit; font-size: var(--tv-gr-marke); font-weight: 700; text-align: left; }
  .regel span { display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .regel i { flex: none; color: var(--tv-text-3); }
  .regel.bedeutung, .regel.bedeutung i { color: var(--tv-bedeutung); }
  button.regel { cursor: pointer; }
  button.regel:hover { background: var(--tv-karte-3); }
</style>

<!--
  Was die Suche durchsucht und wie man genauer sucht (Suchsprache).
  Rechte Spalte der Suche, solange kein Treffer gewählt ist.
-->
<script>
  import { SEARCHED, SEARCH_RULES } from '../../constants/searchChoices.js';

  /** onexample(text): ein Beispiel der Suchsprache übernehmen */
  let { onexample = null } = $props();
</script>

<div class="hilfe">
  <div class="etikett">Was durchsucht wird</div>
  <div class="quellen">
    {#each SEARCHED as name (name)}<span><i class="fa-solid fa-check"></i>{name}</span>{/each}
    <span class="wunsch"><i class="fa-solid fa-globe"></i>Quelle, nur auf Wunsch</span>
  </div>
  <div class="etikett">So findest du genauer</div>
  {#each SEARCH_RULES as rule (rule.code)}
    <div class="regel">
      {#if onexample}<button class="code" onclick={() => onexample(rule.code)} title="Ins Suchfeld übernehmen">{rule.code}</button>
      {:else}<code>{rule.code}</code>{/if}
      <span>{rule.text}</span>
    </div>
  {/each}
  <p>Groß- und Kleinschreibung und Akzente spielen keine Rolle. Wortanfänge zählen ab vier Zeichen, damit "Lem" nicht "Lemma" findet.</p>
  <p class="tasten"><kbd>/</kbd> oder <kbd>S</kbd> Suchfeld · <kbd>↑</kbd> <kbd>↓</kbd> Treffer wählen · <kbd>Enter</kbd> abspielen</p>
</div>

<style>
  .hilfe { padding: var(--tv-a4); border-radius: var(--tv-ecke); background: var(--tv-flaeche); }
  .etikett { margin: var(--tv-a4) 0 var(--tv-a2); font-size: var(--tv-gr-marke); font-weight: 700; letter-spacing: 0.1em;
             text-transform: uppercase; color: var(--tv-text-3); }
  .etikett:first-child { margin-top: 0; }
  .quellen { display: flex; flex-wrap: wrap; gap: 6px; }
  .quellen span { display: inline-flex; align-items: center; gap: 6px; height: 30px; padding: 0 9px; border-radius: var(--tv-ecke);
                  background: var(--tv-karte-2); font-size: var(--tv-gr-klein); }
  .quellen i { color: var(--tv-akzent); }
  .quellen .wunsch i { color: var(--tv-info); }
  .regel { display: grid; grid-template-columns: 130px minmax(0, 1fr); gap: var(--tv-a3); align-items: baseline; padding: 5px 0;
           font-size: var(--tv-gr-klein); }
  code, .code { justify-self: start; padding: 0; border: 0; background: none; color: var(--tv-akzent);
                font-family: var(--tv-schrift-zahl); font-size: var(--tv-gr-klein); cursor: pointer; text-align: left; }
  code { cursor: default; }
  .code:hover { text-decoration: underline; }
  p { margin: var(--tv-a3) 0 0; font-size: var(--tv-gr-klein); color: var(--tv-text-3); line-height: 1.5; }
  kbd { display: inline-block; min-width: 22px; padding: 0 6px; border-radius: var(--tv-ecke-klein); background: var(--tv-karte-3);
        color: var(--tv-text); font-family: var(--tv-schrift-zahl); font-size: var(--tv-gr-marke); text-align: center; }
</style>

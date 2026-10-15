<!--
  Erste Schritte: steht in der Übersicht, solange weder Videos noch Abos da
  sind. Jeder Schritt führt direkt dorthin, wo man ihn erledigt.
-->
<script>
  import { navigate } from '../../router/router.js';
  import OverviewSection from './OverviewSection.svelte';

  /** onLoad: zum Laden-Feld oben springen */
  let { onLoad } = $props();

  const steps = [
    { title: 'Kanäle abonnieren', text: 'Neue Videos erscheinen im Feed; geladen wird nur, was du willst.', run: () => navigate('/subscriptions') },
    { title: 'Ein Video laden', text: 'Adresse oben einfügen, Qualität wählen, Laden.', run: () => onLoad() },
    { title: 'Musik einbinden', text: 'Eigene Sammlung lesend einhängen, sie erscheint in der Musik.', run: () => navigate('/music') },
  ];
</script>

<OverviewSection title="Erste Schritte">
  <div class="schritte">
    {#each steps as step, i (step.title)}
      <button class="schritt" onclick={step.run}>
        <span class="nr zahl">{i + 1}</span>
        <b>{step.title}</b>
        <span class="tv-leise tv-klein">{step.text}</span>
      </button>
    {/each}
  </div>
</OverviewSection>

<style>
  .schritte { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: var(--tv-a3); }
  .schritt { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; padding: var(--tv-a4); border: 0;
             border-radius: var(--tv-ecke); background: var(--tv-flaeche); color: var(--tv-text); font: inherit; text-align: left; cursor: pointer; }
  .schritt:hover { background: var(--tv-karte); }
  .nr { width: 32px; height: 32px; display: grid; place-items: center; margin-bottom: var(--tv-a2); border-radius: 50%;
        background: rgba(var(--tv-akzent-rgb), 0.14); color: var(--tv-akzent); font-weight: 700; }
</style>

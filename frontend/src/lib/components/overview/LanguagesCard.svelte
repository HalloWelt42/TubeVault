<!--
  Sprachen der Bibliothek in der Übersicht: Anteile als Balken, darunter die
  häufigsten Sprachen als Chips; ein Klick zeigt die Bibliothek gefiltert.
  Erscheint erst, wenn es mehr als eine Sprache gibt.
-->
<script>
  import { onMount } from 'svelte';
  import { api } from '../../api/client.js';
  import { navigate } from '../../router/router.js';
  import { languageCatalog, languageInfo, loadLanguages, UNKNOWN } from '../../utils/language.js';
  import OverviewCard from './OverviewCard.svelte';

  const NAMED = 4;   // so viele Sprachen mit Namen, der Rest als "weitere"

  let counts = $state([]);

  onMount(async () => {
    loadLanguages();
    try { counts = (await api.getVideos({ per_page: 1, with_language_counts: true })).language_counts || []; } catch { counts = []; }
  });

  let known = $derived(counts.filter((c) => c.code !== UNKNOWN));
  let unknown = $derived(counts.find((c) => c.code === UNKNOWN)?.count || 0);
  let named = $derived(known.slice(0, NAMED).map((c) => ({ ...languageInfo($languageCatalog, c.code), code: c.code, count: c.count })));
  let rest = $derived(known.slice(NAMED));
  let restCount = $derived(rest.reduce((sum, c) => sum + c.count, 0));

  // Balken: die drei häufigsten farbig, alles Übrige zusammen grau
  const TONES = ['eins', 'zwei', 'drei'];
  let bar = $derived([
    ...known.slice(0, 3).map((c, i) => ({ count: c.count, tone: TONES[i] })),
    { count: known.slice(3).reduce((sum, c) => sum + c.count, 0) + unknown, tone: 'rest' },
  ].filter((part) => part.count > 0));

  const show = (codes) => navigate('/library', { sprache: codes.join(',') });
</script>

{#if known.length > 1}
  <OverviewCard title="Sprachen" more={{ label: 'In der Bibliothek', path: '/library' }}>
    <div class="balken" aria-hidden="true">
      {#each bar as part (part.tone)}<span class={part.tone} style:flex={part.count}></span>{/each}
    </div>
    <div class="chips">
      {#each named as lang (lang.code)}
        <button class="tv-chip" onclick={() => show([lang.code])} title="Bibliothek: nur {lang.name}">
          {#if lang.flag}<span class="flagge" aria-hidden="true">{lang.flag}</span>{/if}
          {lang.name} <span class="zahl tv-schwach">{lang.count.toLocaleString('de-DE')}</span></button>
      {/each}
      {#if restCount}
        <button class="tv-chip" onclick={() => show(rest.map((c) => c.code))} title="Bibliothek: alle übrigen Sprachen">
          weitere <span class="zahl tv-schwach">{restCount.toLocaleString('de-DE')}</span></button>
      {/if}
      {#if unknown}
        <button class="tv-chip" onclick={() => show([UNKNOWN])} title="Bibliothek: Videos ohne erkannte Sprache">
          unbekannt <span class="zahl tv-schwach">{unknown.toLocaleString('de-DE')}</span></button>
      {/if}
    </div>
  </OverviewCard>
{/if}

<style>
  .balken { display: flex; height: 12px; margin-bottom: var(--tv-a3); border-radius: var(--tv-ecke-klein); overflow: hidden; }
  .eins { background: var(--tv-akzent); }
  .zwei { background: var(--tv-info); }
  .drei { background: var(--tv-warnung); }
  .rest { background: var(--tv-text-3); }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .flagge { font-size: 15px; line-height: 1; }
</style>

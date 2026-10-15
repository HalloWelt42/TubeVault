<!--
  Gemerkte Suchen als Karten: Name, Filter in Worten, neue Treffer seit dem
  letzten Öffnen. Öffnen führt zur Suche (und wertet das Neue als gesehen);
  Vergessen fragt nicht nach - die Suche lässt sich jederzeit neu merken.
  Genutzt auf der Suche-Seite und in der Übersicht.
-->
<script>
  import { api } from '../../api/client.js';
  import { navigate } from '../../router/router.js';
  import { toast } from '../../stores/notifications.js';
  import { LENGTHS, LOCATIONS, PERIODS, STATES, choiceLabel } from '../../constants/searchChoices.js';
  import { addressParams, filtersFromSaved } from '../../utils/searchState.js';
  import { languageCatalog, languageInfo, loadLanguages } from '../../utils/language.js';

  /** items: gemerkte Suchen (api.savedSearches); onchange: nach Vergessen */
  let { items = [], compact = false, onchange = () => {} } = $props();

  loadLanguages();

  function describe(saved) {
    const f = saved.filters || {};
    const parts = [
      f.languages?.length ? f.languages.map((code) => languageInfo($languageCatalog, code).name).join(', ') : 'alle Sprachen',
      choiceLabel(LENGTHS, f.length), choiceLabel(PERIODS, f.period), choiceLabel(LOCATIONS, f.location), choiceLabel(STATES, f.state),
    ];
    return parts.filter(Boolean).join(' · ');
  }

  async function open(saved) {
    try { await api.seenSavedSearch(saved.id); } catch { /* Öffnen geht trotzdem */ }
    navigate('/search', addressParams({ q: saved.query, section: null, filters: filtersFromSaved(saved.filters) }));
  }

  async function forget(saved, event) {
    event.stopPropagation();
    try {
      await api.deleteSavedSearch(saved.id);
      toast.success(`Vergessen: ${saved.name}`);
      onchange();
    } catch (e) { toast.error(e.message); }
  }
</script>

<div class="gemerkt" class:compact>
  {#each items as saved (saved.id)}
    {@const fresh = saved.new_videos + saved.new_feed}
    <div class="karte" role="button" tabindex="0" onclick={() => open(saved)} onkeydown={(e) => e.key === 'Enter' && open(saved)}
         title="Suche öffnen: {saved.query}">
      <div class="kopf">
        <i class="fa-solid fa-star"></i>
        <span class="name">{saved.name}</span>
        {#if fresh}
          <span class="neu" title="{saved.new_videos} neu geladen, {saved.new_feed} neu bei Abos"><span class="zahl">{fresh}</span> neu</span>
        {/if}
        <button class="vergessen" onclick={(e) => forget(saved, e)} title="Gemerkte Suche vergessen" aria-label="Vergessen">
          <i class="fa-solid fa-xmark"></i></button>
      </div>
      {#if !compact}<div class="filter">{saved.query !== saved.name ? `${saved.query} · ` : ''}{describe(saved)}</div>{/if}
    </div>
  {/each}
</div>

<style>
  .gemerkt { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: var(--tv-a3); }
  .gemerkt.compact { grid-template-columns: 1fr; gap: 4px; }
  .karte { padding: var(--tv-a3) var(--tv-a4); border-radius: var(--tv-ecke); background: var(--tv-flaeche); cursor: pointer; }
  .compact .karte { padding: var(--tv-a2) var(--tv-a3); background: var(--tv-karte); }
  .karte:hover { background: var(--tv-karte-2); }
  .kopf { display: flex; align-items: center; gap: var(--tv-a2); }
  .kopf > i { color: var(--tv-warnung); }
  .name { flex: 1; min-width: 0; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .neu { padding: 1px 8px; border-radius: var(--tv-ecke-klein); background: rgba(var(--tv-akzent-rgb), 0.16); color: var(--tv-akzent);
         font-size: var(--tv-gr-marke); font-weight: 700; white-space: nowrap; }
  .vergessen { width: 30px; height: 30px; border: 0; border-radius: var(--tv-ecke); background: none; color: var(--tv-text-3); cursor: pointer; }
  .vergessen:hover { background: var(--tv-karte-3); color: var(--tv-text); }
  .filter { margin-top: 4px; font-size: var(--tv-gr-klein); color: var(--tv-text-3); }
</style>

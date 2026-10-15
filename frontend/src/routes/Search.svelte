<!--
  TubeVault - Suche (Gestaltung nach mockups/suche.html)
  Fester Kopf mit Suchfeld, Merken, Bereichen samt Zahlen und Filtern;
  darunter links die Treffer (Alles: je Bereich die besten, sonst ein Bereich
  seitenweise), rechts die Vorschau des gewählten Treffers mit allen
  Fundstellen. Ohne Suchtext: zuletzt gesucht, gemerkte Suchen, Suchsprache.
  Der ganze Zustand steht in der Adresse (utils/searchState.js), Pfeiltasten
  wählen Treffer, Enter spielt ab. Die Quelle wird nur auf Wunsch gefragt.
  © HalloWelt42 - Private Nutzung
-->
<script>
  import { onMount, tick, untrack } from 'svelte';
  import { api } from '../lib/api/client.js';
  import { navigate, route, updateParams } from '../lib/router/router.js';
  import { toast } from '../lib/stores/notifications.js';
  import { clearSearchHistory, forgetSearch, rememberSearch, searchHistory } from '../lib/stores/searchHistory.js';
  import { createListLoader } from '../lib/utils/listLoader.svelte.js';
  import { infiniteScroll } from '../lib/utils/infiniteScroll.js';
  import { activeFilterCount, addressParams, apiParams, emptyFilters, filtersFromSaved, filtersToSaved, readSearch } from '../lib/utils/searchState.js';
  import { SECTIONS } from '../lib/constants/searchChoices.js';
  import SectionTabs from '../lib/components/search/SectionTabs.svelte';
  import SearchFilterBar from '../lib/components/search/SearchFilterBar.svelte';
  import VideoHitRow from '../lib/components/search/VideoHitRow.svelte';
  import FeedHitRow from '../lib/components/search/FeedHitRow.svelte';
  import ChannelHitList from '../lib/components/search/ChannelHitList.svelte';
  import PlaylistHitList from '../lib/components/search/PlaylistHitList.svelte';
  import MusicHitList from '../lib/components/search/MusicHitList.svelte';
  import HitPreview from '../lib/components/search/HitPreview.svelte';
  import SearchHelp from '../lib/components/search/SearchHelp.svelte';
  import SavedSearchList from '../lib/components/search/SavedSearchList.svelte';
  import SourceResults from '../lib/components/search/SourceResults.svelte';

  const PER_PAGE = 24;
  const VIDEO_SECTIONS = new Set(['videos', 'gesagt', 'kapitel', 'sinngemaess']);
  const PLAYLIST_MAX = 1000;
  // So viele Treffer je Bereich zeigt "Alles" (die Übersicht liefert bis zu 5)
  const SHOWN = { videos: 5, gesagt: 3, kapitel: 3, abos: 3 };

  const initial = readSearch($route.params);
  let input = $state(initial.q);         // was im Feld steht
  let q = $state(initial.q);             // was gesucht wird
  let section = $state(initial.section);
  let filters = $state(initial.filters);

  let overview = $state(null);
  let loading = $state(false);
  let saved = $state([]);
  let selected = $state(null);
  let field;
  let run = 0;

  let terms = $derived(overview?.terms || []);
  let sections = $derived(overview?.sections || {});
  let wordTotal = $derived(Object.entries(sections).filter(([name]) => name !== 'sinngemaess')
    .reduce((sum, [, page]) => sum + page.total, 0));
  let savedHere = $derived(saved.find((s) => s.query === q && JSON.stringify(filtersFromSaved(s.filters)) === JSON.stringify(filters)));
  const shown = (id) => (sections[id]?.items || []).slice(0, SHOWN[id] ?? 5);

  // Ein Bereich seitenweise
  const list = createListLoader(async (page) => {
    if (!q || !section || section === 'quelle') return { items: [], total: 0 };
    const result = await api.searchSection(section, q, { ...apiParams(filters), page, per_page: PER_PAGE });
    return { items: result.items, total: result.total };
  }, { keyOf: (item) => item.id ?? item.channel_id ?? item.track?.id });

  // Wählbare Treffer in Anzeigefolge (Pfeiltasten, Vorschau)
  let selectable = $derived(section
    ? (VIDEO_SECTIONS.has(section) ? list.items : [])
    : [...shown('videos'), ...shown('gesagt'), ...shown('kapitel')]);

  async function loadOverview() {
    const mine = ++run;
    if (!q) { overview = null; selected = null; return; }
    loading = true;
    try {
      const result = await api.search(q, { ...apiParams(filters), limit: 5 });
      if (mine !== run) return;
      overview = result;
      if (!section) selected = selectable[0] || null;
    } catch (e) {
      if (mine === run) toast.error(e.message);
    }
    if (mine === run) loading = false;
  }

  async function reload() {
    updateParams(addressParams({ q, section, filters }));
    await loadOverview();
    if (section && section !== 'quelle') {
      await list.load(true);
      selected = VIDEO_SECTIONS.has(section) ? list.items[0] || null : null;
    }
  }

  function submit(event) {
    event?.preventDefault();
    q = input.trim();
    if (q) rememberSearch(q);
    reload();
  }

  function searchFor(text) {
    input = text;
    submit();
  }

  function chooseSection(id) {
    section = id;
    selected = null;
    reload();
  }

  function changeFilters(next) {
    filters = next;
    reload();
  }

  function play(hit, start = null) {
    navigate(`/watch/${hit.id}`, start ? { t: Math.floor(start) } : {});
  }

  async function loadSaved() {
    try { saved = await api.savedSearches(); } catch { saved = []; }
  }

  async function toggleSaved() {
    try {
      if (savedHere) {
        await api.deleteSavedSearch(savedHere.id);
        toast.success(`Vergessen: ${savedHere.name}`);
      } else {
        await api.saveSearch({ query: q, filters: filtersToSaved(filters) });
        toast.success(`Gemerkt: ${q} - neue Treffer erscheinen in der Übersicht`);
      }
      await loadSaved();
    } catch (e) { toast.error(e.message); }
  }

  // ─── Treffer als Playlist ───
  let playlistName = $state(null);       // null: kein Formular offen
  let playlistBusy = $state(false);

  async function saveAsPlaylist(event) {
    event.preventDefault();
    playlistBusy = true;
    try {
      const ids = await api.searchVideoIds(q, { ...apiParams(filters), limit: PLAYLIST_MAX });
      const result = await api.createPlaylistFromVideos(playlistName.trim(), ids);
      toast.success(`Playlist "${result.name}" mit ${result.video_count} Videos angelegt`);
      playlistName = null;
    } catch (e) { toast.error(e.message); }
    playlistBusy = false;
  }

  // ─── Tastatur: Pfeile wählen, Enter spielt, Esc zurück ins Feld ───
  async function move(step) {
    if (!selectable.length) return;
    const index = selectable.indexOf(selected);
    selected = selectable[Math.max(0, Math.min(selectable.length - 1, index < 0 ? 0 : index + step))];
    await tick();
    document.querySelector(`[data-pos="${selectable.indexOf(selected)}"]`)?.scrollIntoView({ block: 'nearest' });
  }

  function onFieldKey(event) {
    if (event.key === 'ArrowDown' && selectable.length) {
      event.preventDefault();
      field.blur();
      move(selectable.includes(selected) ? 0 : 1);
    }
  }

  function onWindowKey(event) {
    const tag = event.target?.tagName?.toLowerCase();
    if (tag === 'input' || tag === 'textarea' || event.target?.isContentEditable || event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      move(event.key === 'ArrowDown' ? 1 : -1);
    } else if (event.key === 'Enter' && selected && selectable.includes(selected)) {
      event.preventDefault();
      play(selected);
    } else if (event.key === 'Escape') {
      field?.focus();
    }
  }

  // Suche von außen (Kopfzeile, Verweise): Adresse geändert
  $effect(() => {
    const params = $route.params;
    untrack(() => {
      const next = readSearch(params);
      if (next.q === q && next.section === section && JSON.stringify(next.filters) === JSON.stringify(filters)) return;
      input = next.q;
      q = next.q;
      section = next.section;
      filters = next.filters;
      selected = null;
      reload();
    });
  });

  onMount(() => {
    loadSaved();
    if (q) reload();
    else tick().then(() => field?.focus());
  });

  const sectionOf = (id) => SECTIONS.find((s) => s.id === id);
  const positionOf = (hit) => selectable.indexOf(hit);
</script>

<svelte:window onkeydown={onWindowKey} />

{#snippet head(id, label = null)}
  {@const def = sectionOf(id)}
  <div class="abschnitt-kopf">
    <h2>{label || def.label}</h2>
    <span class="zahl tv-schwach">{sections[id].total.toLocaleString('de-DE')}{sections[id].more ? '+' : ''}</span>
    <span class="erkl">{def.hint}</span>
    {#if sections[id].total > shown(id).length}
      <button class="mehr" onclick={() => chooseSection(id)}>Alle {sections[id].total.toLocaleString('de-DE')}{sections[id].more ? '+' : ''}</button>
    {/if}
  </div>
{/snippet}

{#snippet videoRows(items)}
  {#each items as hit, i (hit.id + i)}
    <div data-pos={positionOf(hit)}>
      <VideoHitRow {hit} {terms} selected={selected === hit} onselect={(h) => selected = h} onplay={play} />
    </div>
  {/each}
{/snippet}

<div class="tv-seite">
  <div class="tv-seitenkopf">
    <form class="kopf" onsubmit={submit}>
      <h1>Suche</h1>
      <label class="feld">
        <i class="fa-solid fa-magnifying-glass"></i>
        <input bind:this={field} bind:value={input} onkeydown={onFieldKey} placeholder="Was suchst du?" aria-label="Suchtext"
               autocomplete="off" spellcheck="false" />
        {#if input}
          <button type="button" class="leeren" onclick={() => { input = ''; field.focus(); }} title="Feld leeren" aria-label="Feld leeren">
            <i class="fa-solid fa-xmark"></i></button>
        {/if}
      </label>
      <button type="submit" class="tv-knopf haupt gross" disabled={!input.trim()}><i class="fa-solid fa-magnifying-glass"></i> Suchen</button>
      {#if q}
        <button type="button" class="tv-knopf gross" class:aktiv={!!savedHere} onclick={toggleSaved}
                title={savedHere ? 'Gemerkte Suche vergessen' : 'Suche samt Filtern merken; neue Treffer erscheinen in der Übersicht'}>
          <i class="fa-{savedHere ? 'solid' : 'regular'} fa-star"></i> {savedHere ? 'Gemerkt' : 'Merken'}</button>
      {/if}
    </form>
    {#if q}
      <SectionTabs {sections} active={section} onchoose={chooseSection} />
      <SearchFilterBar {filters} effective={overview?.filters} languageCounts={overview?.language_counts || []} onchange={changeFilters} />
    {/if}
  </div>

  <div class="tv-spalten">
    <div class="tv-rollfeld" data-scroll-root>
      {#if !q}
        {#if $searchHistory.length}
          <section class="abschnitt">
            <div class="abschnitt-kopf"><h2>Zuletzt gesucht</h2>
              <button class="mehr" onclick={clearSearchHistory}>Verlauf leeren</button></div>
            <div class="verlauf">
              {#each $searchHistory.slice(0, 12) as entry (entry.query)}
                <span class="eintrag">
                  <button onclick={() => searchFor(entry.query)}><i class="fa-solid fa-clock-rotate-left"></i> {entry.query}</button>
                  <button class="weg" onclick={() => forgetSearch(entry.query)} title="Aus dem Verlauf nehmen" aria-label="Aus dem Verlauf nehmen">
                    <i class="fa-solid fa-xmark"></i></button>
                </span>
              {/each}
            </div>
          </section>
        {/if}
        <section class="abschnitt">
          <div class="abschnitt-kopf"><h2>Gemerkte Suchen</h2><span class="erkl">neue Treffer erscheinen hier und in der Übersicht</span></div>
          {#if saved.length}
            <SavedSearchList items={saved} onchange={loadSaved} />
          {:else}
            <p class="leise">Noch nichts gemerkt. Nach einer Suche merkt "Merken" sie samt Filtern.</p>
          {/if}
        </section>

      {:else if section === 'quelle'}
        <SourceResults {q} {terms} />

      {:else if section}
        {@const def = sectionOf(section)}
        <div class="abschnitt-kopf">
          <h2>{def.label}</h2>
          <span class="zahl tv-schwach">{list.total.toLocaleString('de-DE')}{sections[section]?.more ? '+' : ''}</span>
          <span class="erkl">{def.hint}</span>
          {#if section === 'videos' && list.total > 1}
            {@render playlistButton()}
          {/if}
        </div>
        {#if VIDEO_SECTIONS.has(section)}
          {@render videoRows(list.items)}
        {:else if section === 'abos'}
          {#each list.items as hit (hit.id)}<FeedHitRow {hit} {terms} />{/each}
        {:else if section === 'kanaele'}
          <ChannelHitList items={list.items} {terms} />
        {:else if section === 'playlists'}
          <PlaylistHitList items={list.items} {terms} />
        {:else if section === 'musik'}
          <MusicHitList items={list.items} {terms} query={q} />
        {/if}
        {#if list.loading && !list.items.length}<div class="hinweis"><i class="fa-solid fa-spinner fa-spin"></i> Suche läuft</div>{/if}
        {#if !list.loading && !list.items.length}<div class="hinweis">In diesem Bereich nichts gefunden.</div>{/if}
        <div use:infiniteScroll={{ onLoadMore: list.loadMore, canLoad: list.canLoad }}></div>
        {#if list.loadingMore}<div class="hinweis"><i class="fa-solid fa-spinner fa-spin"></i> Weitere Treffer</div>{/if}

      {:else if !overview}
        <div class="hinweis"><i class="fa-solid fa-spinner fa-spin"></i> Suche läuft</div>

      {:else if !wordTotal && !sections.sinngemaess?.total}
        <div class="nichts">
          <h2>Nichts gefunden für "{q}"</h2>
          <p class="leise">Weder in Bibliothek und Archiv noch im Gesagten, bei Abos, Kanälen, Playlists oder in der Musik.</p>
          {#if overview.suggestion}
            <button class="meintest" onclick={() => searchFor(overview.suggestion.text)}>
              <i class="fa-solid fa-spell-check"></i> Meintest du {overview.suggestion.text}?
              <span class="zahl">{overview.suggestion.total}</span> Videos</button>
          {/if}
          <div class="auswege">
            {#if activeFilterCount(filters)}
              <button class="tv-knopf" onclick={() => changeFilters(emptyFilters())}><i class="fa-solid fa-filter-circle-xmark"></i> Filter aufheben</button>
            {/if}
            {#if overview.semantic === false && filters.genau === 'aus'}
              <button class="tv-knopf" onclick={() => changeFilters({ ...filters, genau: null })}><i class="fa-solid fa-wand-magic-sparkles"></i> Auch sinngemäß suchen</button>
            {:else if overview.semantic && filters.genau !== 'weit'}
              <button class="tv-knopf" onclick={() => changeFilters({ ...filters, genau: 'weit' })}><i class="fa-solid fa-wand-magic-sparkles"></i> Sinngemäß weiter fassen</button>
            {/if}
            <button class="tv-knopf" onclick={() => chooseSection('quelle')}><i class="fa-solid fa-globe"></i> Bei der Quelle suchen</button>
          </div>
        </div>

      {:else}
        {#if overview.suggestion}
          <button class="meintest oben" onclick={() => searchFor(overview.suggestion.text)}>
            <i class="fa-solid fa-spell-check"></i> Kein Wort getroffen. Meintest du {overview.suggestion.text}?
            <span class="zahl">{overview.suggestion.total}</span> Videos</button>
        {/if}
        {#if sections.videos?.total}
          <section class="abschnitt">
            {@render head('videos')}
            {@render videoRows(shown('videos'))}
          </section>
        {/if}
        {#if sections.gesagt?.total}
          <section class="abschnitt">{@render head('gesagt')}{@render videoRows(shown('gesagt'))}</section>
        {/if}
        {#if sections.kapitel?.total}
          <section class="abschnitt">{@render head('kapitel')}{@render videoRows(shown('kapitel'))}</section>
        {/if}
        {#if sections.abos?.total}
          <section class="abschnitt">{@render head('abos', 'Bei Abos, noch nicht geladen')}
            {#each shown('abos') as hit (hit.id)}<FeedHitRow {hit} {terms} />{/each}</section>
        {/if}
        {#if sections.kanaele?.total}
          <section class="abschnitt">{@render head('kanaele')}<ChannelHitList items={sections.kanaele.items} {terms} /></section>
        {/if}
        {#if sections.playlists?.total}
          <section class="abschnitt">{@render head('playlists')}<PlaylistHitList items={sections.playlists.items} {terms} /></section>
        {/if}
        {#if sections.musik?.total}
          <section class="abschnitt">{@render head('musik')}<MusicHitList items={sections.musik.items} {terms} query={q} /></section>
        {/if}
        {#if sections.sinngemaess?.total}
          <div class="lose">
            <i class="fa-solid fa-wand-magic-sparkles"></i>
            <span><span class="zahl">{sections.sinngemaess.total}</span> weitere nur sinngemäß verwandt, ohne das Wort</span>
            <button class="tv-knopf klein ohne" onclick={() => chooseSection('sinngemaess')}>Ansehen</button>
          </div>
        {/if}
        <div class="quelle">
          <i class="fa-solid fa-globe"></i>
          <div><b>Mehr bei der Quelle?</b><div class="leise">Fragt die Quelle nur auf Wunsch und schont so die Abrufgrenze.</div></div>
          <button class="tv-knopf" onclick={() => chooseSection('quelle')}><i class="fa-solid fa-magnifying-glass"></i> Bei der Quelle suchen</button>
        </div>
      {/if}
    </div>

    <div class="tv-rollfeld">
      {#if selected && q}
        <HitPreview hit={selected} {q} {terms} onplay={play} />
      {:else}
        <SearchHelp onexample={(code) => { input = `${input.trim()} ${code}`.trim(); field.focus(); }} />
      {/if}
    </div>
  </div>
</div>

{#snippet playlistButton()}
  {#if playlistName === null}
    <button class="mehr" onclick={() => playlistName = q} title="Alle Videotreffer in dieser Reihenfolge als Playlist speichern (bis {PLAYLIST_MAX})">
      <i class="fa-solid fa-list"></i> Als Playlist</button>
  {:else}
    <form class="playlist" onsubmit={saveAsPlaylist}>
      <input class="tv-eingabe" bind:value={playlistName} aria-label="Name der Playlist" />
      <button class="tv-knopf klein haupt" disabled={!playlistName.trim() || playlistBusy}>
        <i class="fa-solid {playlistBusy ? 'fa-spinner fa-spin' : 'fa-check'}"></i> Anlegen</button>
      <button type="button" class="tv-knopf klein ohne" onclick={() => playlistName = null}>Abbrechen</button>
    </form>
  {/if}
{/snippet}

<style>
  .kopf { display: flex; align-items: center; gap: var(--tv-a3); }
  h1 { margin: 0; font-size: var(--tv-gr-seite); }
  .feld { flex: 1; display: flex; align-items: center; gap: var(--tv-a2); height: 48px; padding: 0 var(--tv-a3);
          border-radius: var(--tv-ecke); background: var(--tv-mulde); color: var(--tv-text-3); cursor: text; }
  .feld:focus-within { outline: 1px solid rgba(var(--tv-akzent-rgb), 0.6); }
  .feld input { flex: 1; min-width: 0; height: 100%; border: 0; background: none; color: var(--tv-text); font: inherit;
                font-size: 19px; font-weight: 600; outline: 0; }
  .feld input::placeholder { font-weight: 400; color: var(--tv-text-3); }
  .leeren { width: 34px; height: 34px; border: 0; border-radius: var(--tv-ecke); background: none; color: var(--tv-text-3); cursor: pointer; }
  .leeren:hover { background: var(--tv-karte-2); color: var(--tv-text); }
  .gross { height: 48px; }

  .abschnitt { margin-bottom: var(--tv-a5); }
  .abschnitt-kopf { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--tv-a2) var(--tv-a3); margin-bottom: var(--tv-a2); }
  .abschnitt-kopf h2 { margin: 0; font-size: var(--tv-gr-titel); }
  .erkl { font-size: var(--tv-gr-klein); color: var(--tv-text-3); }
  .mehr { margin-left: auto; padding: 0; border: 0; background: none; color: var(--tv-akzent); font: inherit; font-weight: 600;
          font-size: var(--tv-gr-klein); white-space: nowrap; cursor: pointer; }
  .mehr:hover { color: var(--tv-akzent-hell); }
  .playlist { margin-left: auto; display: flex; gap: var(--tv-a2); }
  .playlist .tv-eingabe { height: 34px; width: 240px; }

  .verlauf { display: flex; flex-wrap: wrap; gap: var(--tv-a2); }
  .eintrag { display: inline-flex; align-items: center; border-radius: var(--tv-ecke); background: var(--tv-flaeche); }
  .eintrag button { height: 36px; padding: 0 var(--tv-a3); border: 0; background: none; color: var(--tv-text); font: inherit; cursor: pointer; }
  .eintrag button i { color: var(--tv-text-3); margin-right: 4px; }
  .eintrag .weg { padding: 0 10px; color: var(--tv-text-3); }
  .eintrag button:hover { color: var(--tv-akzent); }
  .leise { color: var(--tv-text-3); }
  .hinweis { padding: var(--tv-a4); color: var(--tv-text-3); font-size: var(--tv-gr-klein); }

  .lose { display: flex; align-items: center; gap: var(--tv-a2); margin-bottom: var(--tv-a4); padding: var(--tv-a3);
          border-radius: var(--tv-ecke); background: var(--tv-flaeche); color: var(--tv-text-2); font-size: var(--tv-gr-klein); }
  .lose > i { color: var(--tv-info); }
  .lose .tv-knopf { margin-left: auto; }
  .quelle { display: flex; align-items: center; gap: var(--tv-a3); padding: var(--tv-a4); border-radius: var(--tv-ecke);
            background: rgba(var(--tv-info-rgb), 0.08); }
  .quelle > i { font-size: 26px; color: var(--tv-info); }
  .quelle .leise { font-size: var(--tv-gr-klein); }
  .quelle .tv-knopf { margin-left: auto; }

  .nichts { padding: var(--tv-a5); border-radius: var(--tv-ecke); background: var(--tv-flaeche); }
  .nichts h2 { margin: 0 0 var(--tv-a2); }
  .meintest { display: inline-flex; align-items: center; gap: var(--tv-a2); margin-top: var(--tv-a3); height: 44px; padding: 0 var(--tv-a4);
              border: 0; border-radius: var(--tv-ecke); background: rgba(var(--tv-akzent-rgb), 0.14); color: var(--tv-akzent);
              font: inherit; font-weight: 700; cursor: pointer; }
  .meintest:hover { background: rgba(var(--tv-akzent-rgb), 0.22); }
  .meintest.oben { margin: 0 0 var(--tv-a4); }
  .auswege { display: flex; flex-wrap: wrap; gap: var(--tv-a2); margin-top: var(--tv-a4); }
</style>

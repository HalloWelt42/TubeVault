<!--
  TubeVault - Suchfeld im Kopf mit Aufklappliste (Gestaltung nach mockups/suche.html, "Beim Tippen")

  Leer: zuletzt gesucht und gemerkte Suchen. Beim Tippen eine gebündelte
  Anfrage (nur Wörter, ohne Bedeutungssuche - das bleibt schnell): Ergänzungen
  aus dem Wortschatz, dann je Bereich die besten Treffer. Pfeiltasten wählen,
  Enter öffnet, Tab übernimmt eine Ergänzung ins Feld, Strg+Enter zeigt alle
  Treffer auf der Suche-Seite, Esc schließt. Eine Adresse der Quelle (oder
  eine Video-Kennung) geht zum Laden an die Downloads.
-->
<script>
  import { api } from '../../api/client.js';
  import { navigate } from '../../router/router.js';
  import { pendingDownloadUrl } from '../../stores/app.js';
  import { toast } from '../../stores/notifications.js';
  import { musicPlayer } from '../../stores/musicPlayer.svelte.js';
  import { rememberSearch, searchHistory } from '../../stores/searchHistory.js';
  import { fold } from '../../utils/searchHighlight.js';
  import { formatDuration } from '../../utils/format.js';
  import { coverUrl } from '../../utils/musicTrack.js';
  import { addressParams, filtersFromSaved } from '../../utils/searchState.js';
  import Marked from '../search/Marked.svelte';

  const DEBOUNCE_MS = 220;
  const MIN_CHARS = 2;
  const SHOW = { videos: 3, gesagt: 2, kapitel: 2, abos: 2, kanaele: 2, musik: 3, playlists: 2 };
  const GROUPS = [
    ['videos', 'Videos'], ['gesagt', 'Im Gesagten'], ['kapitel', 'Kapitel'], ['abos', 'Bei Abos, noch nicht geladen'],
    ['kanaele', 'Kanäle'], ['musik', 'Musik'], ['playlists', 'Playlists'],
  ];

  let text = $state('');
  let open = $state(false);
  let overview = $state(null);
  let completions = $state([]);
  let saved = $state([]);
  let active = $state(-1);           // gewählter Eintrag (Pfeiltasten)
  let field;
  let box;
  let timer;
  let run = 0;

  let terms = $derived(overview?.terms || []);
  let typed = $derived(text.trim());

  // Vorschläge: Ergänzungen und passende Einträge des Verlaufs, ohne Doppelte
  let suggestions = $derived.by(() => {
    if (typed.length < MIN_CHARS) return [];
    const wanted = fold(typed);
    const fromHistory = $searchHistory.map((entry) => entry.query).filter((query) => fold(query).startsWith(wanted) && query !== typed);
    const seen = new Set();
    return [...fromHistory.map((query) => ({ query, history: true })), ...completions.map((query) => ({ query, history: false }))]
      .filter((s) => !seen.has(fold(s.query)) && seen.add(fold(s.query))).slice(0, 4);
  });

  // Alle wählbaren Einträge in Anzeigefolge; jeder weiß, was Enter tut
  let entries = $derived.by(() => {
    if (typed.length < MIN_CHARS) {
      return [
        ...$searchHistory.slice(0, 6).map((entry) => ({ kind: 'verlauf', key: `v:${entry.query}`, query: entry.query })),
        ...saved.map((item) => ({ kind: 'gemerkt', key: `g:${item.id}`, item })),
      ];
    }
    const list = suggestions.map((s) => ({ kind: 'vorschlag', key: `s:${s.query}`, ...s }));
    for (const [id] of GROUPS) {
      for (const hit of (overview?.sections?.[id]?.items || []).slice(0, SHOW[id])) {
        list.push({ kind: id, key: `${id}:${hit.id ?? hit.channel_id ?? hit.track?.id}`, hit });
      }
    }
    return list;
  });

  function groupStart(id) {
    return entries.findIndex((entry) => entry.kind === id);
  }

  async function loadSaved() {
    try { saved = await api.savedSearches(); } catch { saved = []; }
  }

  function show() {
    open = true;
    active = -1;
    if (typed.length < MIN_CHARS) loadSaved();
  }

  function close() {
    open = false;
    active = -1;
  }

  function onInput() {
    open = true;
    active = -1;
    clearTimeout(timer);
    if (typed.length < MIN_CHARS) {
      run++;
      overview = null;
      completions = [];
      return;
    }
    timer = setTimeout(lookup, DEBOUNCE_MS);
  }

  async function lookup() {
    const mine = ++run;
    const query = typed;
    try {
      const [result, words] = await Promise.all([
        api.search(query, { limit: 3, meaning: false }),
        api.searchComplete(query).catch(() => []),
      ]);
      if (mine !== run) return;
      overview = result;
      completions = words;
    } catch { /* die Seite zeigt den Fehler, hier bleibt es still */ }
  }

  /** Adresse der Quelle oder eine Video-Kennung (mit Ziffer oder - _, damit Wörter nicht zählen) */
  function isSourceAddress(value) {
    return /(?:youtube\.com|youtu\.be)\//.test(value) || (/^[A-Za-z0-9_-]{11}$/.test(value) && /[0-9_-]/.test(value));
  }

  function toPage(query, section = null) {
    rememberSearch(query);
    close();
    field?.blur();
    text = '';                 // weiter geht es im großen Feld der Suche-Seite
    navigate('/search', { q: query, ...(section ? { bereich: section } : {}) });
  }

  async function loadFeed(hit) {
    try {
      await api.addDownload({ url: `https://www.youtube.com/watch?v=${hit.video_id}` });
      hit.in_queue = true;
      overview = { ...overview };
      toast.success(`In der Warteschlange: ${hit.title}`);
    } catch (e) { toast.error(e.message); }
  }

  function activate(entry) {
    if (!entry) return;
    if (entry.kind === 'verlauf' || entry.kind === 'vorschlag') return toPage(entry.query);
    if (entry.kind === 'gemerkt') {
      api.seenSavedSearch(entry.item.id).catch(() => {});
      close();
      return navigate('/search', addressParams({ q: entry.item.query, section: null, filters: filtersFromSaved(entry.item.filters) }));
    }
    const hit = entry.hit;
    if (typed) rememberSearch(typed);
    close();
    field?.blur();
    if (entry.kind === 'musik') return musicPlayer.playTracks([hit.track], 0, `Suche: ${typed}`);
    if (entry.kind === 'kanaele') return navigate(`/channel/${hit.channel_id}`);
    if (entry.kind === 'playlists') return navigate('/playlists', { open: hit.id });
    if (entry.kind === 'abos') return navigate(`/watch/${hit.video_id}`);
    const start = hit.spots?.[0]?.start;
    navigate(`/watch/${hit.id}`, (entry.kind === 'gesagt' || entry.kind === 'kapitel') && start ? { t: Math.floor(start) } : {});
  }

  function onKeydown(event) {
    if (event.key === 'Escape') {
      close();
      field.blur();
    } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      open = true;
      if (!entries.length) return;
      // Reihum über alle Einträge; -1 ist das Feld selbst
      active += event.key === 'ArrowDown' ? 1 : -1;
      if (active >= entries.length) active = -1;
      if (active < -1) active = entries.length - 1;
      box?.querySelector(`[data-eintrag="${active}"]`)?.scrollIntoView({ block: 'nearest' });
    } else if (event.key === 'Tab' && active >= 0 && entries[active]?.kind === 'vorschlag') {
      event.preventDefault();
      text = `${entries[active].query} `;
      onInput();
    } else if (event.key === 'Enter') {
      event.preventDefault();
      if (!typed && active < 0) return;
      if ((event.ctrlKey || event.metaKey) && typed) return toPage(typed);
      if (active >= 0) return activate(entries[active]);
      if (isSourceAddress(typed)) {
        pendingDownloadUrl.set(typed);
        text = '';
        close();
        return navigate('/downloads');
      }
      toPage(typed);
    }
  }

  function outside(event) {
    if (open && box && !box.contains(event.target)) close();
  }
</script>

<svelte:window onpointerdown={outside} />

<div class="suche" bind:this={box}>
  <label class="feld" class:offen={open}>
    <i class="fa-solid fa-magnifying-glass"></i>
    <input bind:this={field} bind:value={text} data-suchfeld oninput={onInput} onfocus={show} onkeydown={onKeydown}
           placeholder="Suchen: Videos, Gesagtes, Abos, Kanäle, Musik" aria-label="Suchen" autocomplete="off" spellcheck="false"
           role="combobox" aria-expanded={open} aria-controls="suchliste" />
    {#if text}
      <button class="leeren" onclick={() => { text = ''; onInput(); field.focus(); }} title="Feld leeren" aria-label="Feld leeren">
        <i class="fa-solid fa-xmark"></i></button>
    {/if}
    <kbd class="taste" title="Suchfeld: S, / oder Strg+K">/</kbd>
  </label>

  {#if open && (entries.length || typed.length >= MIN_CHARS)}
    <div class="liste" id="suchliste" role="listbox">
      <div class="koerper">
        {#if typed.length < MIN_CHARS}
          {#if $searchHistory.length}<div class="gruppe">Zuletzt gesucht</div>{/if}
          {#each entries as entry, i (entry.key)}
            {#if entry.kind === 'gemerkt' && i === groupStart('gemerkt')}<div class="gruppe">Gemerkte Suchen</div>{/if}
            <button class="eintrag" class:aktiv={active === i} data-eintrag={i} role="option" aria-selected={active === i}
                    onmouseenter={() => active = i} onclick={() => activate(entry)}>
              {#if entry.kind === 'verlauf'}
                <i class="fa-solid fa-clock-rotate-left"></i><span class="t">{entry.query}</span>
              {:else}
                <i class="fa-solid fa-star stern"></i><span class="t">{entry.item.name}</span>
                {#if entry.item.new_videos + entry.item.new_feed}
                  <span class="neu"><span class="zahl">{entry.item.new_videos + entry.item.new_feed}</span> neu</span>
                {/if}
              {/if}
            </button>
          {/each}
        {:else}
          {#each entries as entry, i (entry.key)}
            {#if entry.kind !== 'vorschlag' && i === groupStart(entry.kind)}
              {@const total = overview?.sections?.[entry.kind]?.total || 0}
              <div class="gruppe">{GROUPS.find(([id]) => id === entry.kind)[1]}
                {#if total > SHOW[entry.kind]}<button class="alle" onclick={() => toPage(typed, entry.kind)}>{total.toLocaleString('de-DE')} ansehen</button>{/if}
              </div>
            {/if}
            {#if entry.kind === 'vorschlag'}
              <button class="eintrag" class:aktiv={active === i} data-eintrag={i} role="option" aria-selected={active === i}
                      onmouseenter={() => active = i} onclick={() => activate(entry)} title="Tab übernimmt den Vorschlag ins Feld">
                <i class="fa-solid {entry.history ? 'fa-clock-rotate-left' : 'fa-magnifying-glass'}"></i>
                <span class="t"><b>{entry.query.slice(0, typed.length)}</b>{entry.query.slice(typed.length)}</span>
                {#if entry.history}<span class="leise">zuletzt gesucht</span>{/if}
              </button>
            {:else}
              {@const hit = entry.hit}
              <div class="treffer" class:aktiv={active === i} data-eintrag={i} role="option" aria-selected={active === i} tabindex="-1"
                   onmouseenter={() => active = i} onclick={() => activate(entry)} onkeydown={() => {}}>
                {#if entry.kind === 'musik'}
                  <img class="quadrat" src={coverUrl(hit.track)} alt="" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
                  <span class="text"><span class="t"><Marked text={hit.track.title} {terms} /></span>
                    <span class="w">{hit.track.artist}{hit.track.album ? ` · ${hit.track.album}` : ''}</span></span>
                  <span class="zahl leise">{formatDuration(hit.track.duration || 0)}</span>
                {:else if entry.kind === 'kanaele'}
                  <img class="rund" src={api.channelAvatarUrl(hit.channel_id)} alt="" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
                  <span class="text"><span class="t"><Marked text={hit.channel_name} {terms} /></span>
                    <span class="w">{hit.subscribed ? 'abonniert' : 'in der Bibliothek'}{hit.videos ? ` · ${hit.videos} Treffer` : ''}</span></span>
                  <span></span>
                {:else if entry.kind === 'playlists'}
                  <span class="symbol"><i class="fa-solid fa-list"></i></span>
                  <span class="text"><span class="t"><Marked text={hit.name} {terms} /></span><span class="w">{hit.video_count} Videos</span></span>
                  <span></span>
                {:else if entry.kind === 'abos'}
                  <img src={api.rssThumbUrl(hit.video_id)} alt="" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
                  <span class="text"><span class="t"><Marked text={hit.title} {terms} /></span><span class="w">{hit.channel_name || ''}</span></span>
                  <button class="tv-knopf klein haupt" onclick={(e) => { e.stopPropagation(); loadFeed(hit); }} disabled={hit.in_queue}>
                    <i class="fa-solid {hit.in_queue ? 'fa-clock' : 'fa-download'}"></i> {hit.in_queue ? 'Wartet' : 'Laden'}</button>
                {:else}
                  <img src={api.thumbnailUrl(hit.id)} alt="" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
                  <span class="text">
                    {#if hit.spots?.length}
                      <span class="t"><span class="zeit zahl">{formatDuration(Math.floor(hit.spots[0].start))}</span> <Marked text={hit.spots[0].text} {terms} /></span>
                      <span class="w">{hit.title}</span>
                    {:else}
                      <span class="t"><Marked text={hit.title} {terms} /></span>
                      <span class="w">{hit.channel_name || ''}{hit.is_archived ? ' · Archiv' : ''}</span>
                    {/if}
                  </span>
                  {#if active === i}<kbd>Enter</kbd>{:else}<span class="zahl leise">{formatDuration(hit.duration || 0)}</span>{/if}
                {/if}
              </div>
            {/if}
          {/each}
          {#if overview && !entries.some((entry) => entry.kind !== 'vorschlag')}
            <div class="leer">Nichts gefunden.{#if overview.suggestion} Meintest du
              <button class="alle" onclick={() => toPage(overview.suggestion.text)}>{overview.suggestion.text}</button>?{/if}</div>
          {/if}
        {/if}
      </div>
      <div class="fusszeile">
        <span><kbd>↑</kbd> <kbd>↓</kbd> wählen</span>
        <span><kbd>Enter</kbd> öffnen</span>
        {#if typed.length >= MIN_CHARS}
          <span><kbd>Tab</kbd> übernehmen</span>
          <button class="alle" onclick={() => toPage(typed)}><kbd>Strg</kbd>+<kbd>Enter</kbd> alle Treffer</button>
          <button class="quelle" onclick={() => toPage(typed, 'quelle')}><i class="fa-solid fa-globe"></i> Bei der Quelle suchen</button>
        {:else}
          <span><kbd>Esc</kbd> schließen</span>
        {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .suche { position: relative; width: 100%; }
  .feld { display: flex; align-items: center; gap: var(--tv-a2); height: 40px; padding: 0 var(--tv-a2) 0 var(--tv-a3);
          border: 1px solid var(--tv-rand); border-radius: var(--tv-ecke); background: var(--tv-karte); color: var(--tv-text-3); cursor: text; }
  .feld:focus-within, .feld.offen { border-color: rgba(var(--tv-akzent-rgb), 0.6); }
  .feld input { flex: 1; min-width: 0; height: 100%; border: 0; background: none; color: var(--tv-text); font: inherit; outline: 0; }
  .feld input::placeholder { color: var(--tv-text-3); }
  .leeren { width: 30px; height: 30px; border: 0; border-radius: var(--tv-ecke); background: none; color: var(--tv-text-3); cursor: pointer; }
  .leeren:hover { background: var(--tv-karte-2); color: var(--tv-text); }
  kbd { display: inline-block; min-width: 22px; padding: 0 6px; border-radius: var(--tv-ecke-klein); background: var(--tv-karte-3);
        color: var(--tv-text); font-family: var(--tv-schrift-zahl); font-size: var(--tv-gr-marke); text-align: center; }
  .taste { color: var(--tv-text-3); }

  .liste { position: absolute; left: 0; top: calc(100% + 6px); z-index: 300; width: max(100%, 720px); max-height: calc(100vh - 90px);
           display: flex; flex-direction: column; border-radius: var(--tv-ecke); background: var(--tv-karte); box-shadow: var(--tv-schatten); }
  .koerper { overflow-y: auto; padding: var(--tv-a2); }
  .gruppe { display: flex; align-items: baseline; padding: var(--tv-a2) var(--tv-a2) 2px; font-size: var(--tv-gr-marke); font-weight: 700;
            letter-spacing: 0.1em; text-transform: uppercase; color: var(--tv-text-3); }
  .alle { margin-left: auto; padding: 0; border: 0; background: none; color: var(--tv-akzent); font: inherit; font-size: var(--tv-gr-marke);
          font-weight: 600; letter-spacing: 0; text-transform: none; cursor: pointer; }
  .eintrag { display: flex; align-items: center; gap: var(--tv-a2); width: 100%; height: 38px; padding: 0 var(--tv-a2); border: 0;
             border-radius: var(--tv-ecke-klein); background: none; color: var(--tv-text); font: inherit; text-align: left; cursor: pointer; }
  .eintrag > i { width: 18px; color: var(--tv-text-3); text-align: center; }
  .eintrag .stern { color: var(--tv-warnung); }
  .eintrag .t { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .treffer { display: grid; grid-template-columns: 96px minmax(0, 1fr) auto; gap: var(--tv-a3); align-items: center;
             padding: 6px var(--tv-a2); border-radius: var(--tv-ecke-klein); cursor: pointer; }
  .treffer img { width: 96px; aspect-ratio: 16 / 9; object-fit: cover; border-radius: var(--tv-ecke-klein); background: var(--tv-mulde); display: block; }
  .treffer img.quadrat { width: 54px; aspect-ratio: 1; justify-self: center; }
  .treffer img.rund { width: 44px; aspect-ratio: 1; border-radius: 50%; justify-self: center; }
  .symbol { display: grid; place-items: center; color: var(--tv-akzent); font-size: 20px; }
  .text { min-width: 0; display: flex; flex-direction: column; }
  .t { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .w { font-size: var(--tv-gr-klein); color: var(--tv-text-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .zeit { color: var(--tv-akzent); }
  .aktiv { background: rgba(var(--tv-akzent-rgb), 0.12); box-shadow: inset 0 0 0 1px rgba(var(--tv-akzent-rgb), 0.45); }
  .leise { font-size: var(--tv-gr-klein); color: var(--tv-text-3); }
  .neu { padding: 1px 8px; border-radius: var(--tv-ecke-klein); background: rgba(var(--tv-akzent-rgb), 0.16); color: var(--tv-akzent);
         font-size: var(--tv-gr-marke); font-weight: 700; }
  .leer { padding: var(--tv-a3); color: var(--tv-text-2); }
  .fusszeile { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; padding: var(--tv-a2) var(--tv-a3);
               background: var(--tv-karte-2); font-size: var(--tv-gr-marke); color: var(--tv-text-3);
               border-radius: 0 0 var(--tv-ecke) var(--tv-ecke); }
  .fusszeile .alle { margin-left: 0; color: var(--tv-text-3); }
  .fusszeile .alle:hover { color: var(--tv-text); }
  .quelle { margin-left: auto; padding: 0; border: 0; background: none; color: var(--tv-akzent); font: inherit; font-weight: 600;
            font-size: var(--tv-gr-klein); cursor: pointer; }
</style>

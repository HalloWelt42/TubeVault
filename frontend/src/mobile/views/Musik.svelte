<!--
  Musik (Mobil) nach mockups/mobil-musik.html: Quelle (Alle, Sammlung,
  Videos; gilt überall, auch für die Mixe), Weiterhören des zuletzt
  gehörten Hörbuchs, Mixe und die Bereiche Interpreten, Alben, Kanäle und
  Hörbücher als Raster. Eine Kachel öffnet ihre Titel (?quelle=), die Lupe
  sucht in der Musik (?suche=1), Ausgeblendetes holt ?ausgeblendet=1 zurück;
  alles liegt über der Übersicht, die so ihre Stelle behält. Ein geöffnetes
  Album lässt sich ganz ausschließen. Gespielt wird über den Musikspieler;
  Änderungen von überall kommen über utils/musicChanges.js.
-->
<script>
  import { onMount, untrack } from 'svelte';
  import { api } from '../../lib/api/client.js';
  import { coverUrl } from '../../lib/utils/musicTrack.js';
  import { musicPlayer as player } from '../../lib/stores/musicPlayer.svelte.js';
  import { toast } from '../../lib/stores/notifications.js';
  import { formatDuration, formatDurationLong } from '../../lib/utils/format.js';
  import { bookToResume } from '../../lib/utils/bookProgress.js';
  import { createListLoader } from '../../lib/utils/listLoader.svelte.js';
  import { route, go, back } from '../router.js';
  import { nearEnd } from '../parts/nearEnd.js';
  import Ausgeblendet from '../parts/Ausgeblendet.svelte';
  import { excludeAlbum, restoreHidden } from '../../lib/utils/musicHiding.js';
  import { isRemoved, onMusicChange } from '../../lib/utils/musicChanges.js';

  const MIXES = [
    { key: 'all', name: 'Alles zufällig', icon: 'fa-shuffle', shuffle: true },
    { key: 'favorites', name: 'Lieblingssongs', icon: 'fa-heart', shuffle: true },
    { key: 'forgotten', name: 'Lange nicht gehört', icon: 'fa-hourglass-half', shuffle: true },
    { key: 'often', name: 'Oft gehört', icon: 'fa-fire', shuffle: false },
  ];
  // Quelle der Musik: die globale Einstellung music.source
  const SOURCES = [
    { key: 'alle', label: 'Alle' },
    { key: 'sammlung', label: 'Sammlung', count: 'sammlung' },
    { key: 'videos', label: 'Videos', count: 'videos' },
  ];
  const AREAS = [
    { id: 'interpreten', label: 'Interpreten', count: 'artists', load: () => api.musicArtists() },
    { id: 'alben', label: 'Alben', count: 'albums', load: () => api.musicAlbums() },
    { id: 'kanaele', label: 'Kanäle', count: 'channels', load: () => api.musicChannels() },
    { id: 'hoerbuecher', label: 'Hörbücher', count: 'books', load: () => api.musicBooks() },
  ];
  const KIND_LABELS = { datei: 'Sammlung', video: 'Videos' };
  const AREA_KEY = 'musik.bereich';
  const STEP = 30;               // Kacheln bzw. Titel je Nachladen beim Rollen
  const SEARCH_PAGE = 50;
  const SEARCH_MIN = 2;
  const DEBOUNCE_MS = 280;

  let overview = $state(null);
  let books = $state([]);
  let failed = $state(false);

  // ─── Übersicht ───
  let area = $state(readArea());
  let items = $state([]);        // Gruppen bzw. Hörbücher des Bereichs
  let areaLoading = $state(false);
  let shown = $state(STEP);
  let areaRun = 0;

  let counts = $derived(overview?.counts || {});
  let areas = $derived(AREAS.filter((a) => counts[a.count] > 0));
  let activeArea = $derived(areas.find((a) => a.id === area) || areas[0] || null);
  let resume = $derived(bookToResume(books));
  let showSources = $derived(!!overview && ((overview.sources.sammlung > 0 && overview.sources.videos > 0) || overview.source !== 'alle'));
  let empty = $derived(!!overview && !counts.tracks && !counts.books);

  function readArea() {
    try { return localStorage.getItem(AREA_KEY) || 'interpreten'; } catch { return 'interpreten'; }
  }

  function chooseArea(id) {
    area = id;
    try { localStorage.setItem(AREA_KEY, id); } catch { /* Speicher gesperrt */ }
  }

  async function loadOverview() {
    failed = false;
    try { overview = await api.musicOverview(); } catch { failed = true; }
  }

  async function loadBooks() {
    try { books = await api.musicBooks(); } catch { /* Weiterhören fehlt dann nur */ }
  }

  async function loadArea(id) {
    const run = ++areaRun;
    const def = AREAS.find((a) => a.id === id);
    items = [];
    shown = STEP;
    if (!def) return;
    areaLoading = true;
    try {
      const result = await def.load();
      if (run === areaRun) items = result;
    } catch (e) {
      if (run === areaRun) toast.error(e.message);
    } finally {
      if (run === areaRun) areaLoading = false;
    }
  }

  // Bereich gewechselt (oder erst nach dem Laden der Übersicht bekannt): seine Kacheln laden
  $effect(() => {
    const id = activeArea?.id;
    untrack(() => loadArea(id));
  });

  async function chooseSource(key) {
    if (!overview || overview.source === key) return;
    overview = { ...overview, source: key };
    try {
      await api.updateSetting('music.source', key);
      await loadOverview();
      await loadArea(activeArea?.id);
    } catch (e) {
      toast.error(e.message);
      loadOverview();
    }
  }

  async function play(source, { shuffle = false, start = null } = {}) {
    try {
      if (!await player.playSource(source, { shuffle, start })) toast.info('Dort gibt es noch keine Titel');
    } catch (e) { toast.error(e.message); }
  }

  function playResume() {
    if (player.audiobook === resume.key) player.toggle();
    else play(`hoerbuch:${resume.key}`);
  }

  function groupLine(group) {
    if (activeArea?.id === 'alben' && group.subtitle) return group.subtitle;
    if (activeArea?.id === 'interpreten' && overview?.source === 'alle' && group.kinds?.length)
      return group.kinds.map((kind) => KIND_LABELS[kind] || kind).join(', ');
    return `${group.count} Titel`;
  }

  function bookLine(book) {
    if (book.finished) return 'Zu Ende gehört';
    if (book.current_part) return `Teil ${book.current_part} von ${book.parts}`;
    return book.author || `${book.parts} Teile`;
  }

  const bookShare = (book) => (book.duration ? (book.duration - book.remaining) / book.duration : 0);

  // ─── Geöffnete Gruppe und Suche: die Adresse ist die Wahrheit ───
  let openKey = $state(null);    // Gruppe laut Adresse (wird nur in untrack verglichen)
  let opened = $state(null);     // { source, title, tracks }
  let openedShown = $state(STEP);
  let searching = $state(false);
  let hiddenOpen = $state(false);

  async function openGroup(key) {
    openKey = key;
    opened = null;
    openedShown = STEP;
    if (!key) return;
    try {
      const list = await api.musicPlay(key);
      if (openKey === key) opened = list;
    } catch (e) {
      if (openKey === key) toast.error(e.message);
    }
  }

  $effect(() => {
    const current = $route;
    if (current.view !== 'musik') return;
    const key = current.params.quelle || null;
    const search = current.params.suche === '1';
    const hidden = current.params.ausgeblendet === '1';
    untrack(() => {
      searching = search;
      hiddenOpen = hidden;
      if (key !== openKey) openGroup(key);
      if (!key && !search && !hidden) loadBooks();   // zurück in der Übersicht: Weiterhören auffrischen
    });
  });

  // ─── Suche in der Musik ───
  let query = $state('');
  let searched = $state('');
  let searchTimer = null;
  const results = createListLoader(async (page) => {
    const r = await api.musicTracks({ q: searched, offset: (page - 1) * SEARCH_PAGE, limit: SEARCH_PAGE });
    return { items: r.items, total: r.total };
  });

  function onSearchInput() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(runSearch, DEBOUNCE_MS);
  }

  async function runSearch() {
    const q = query.trim();
    searched = q.length >= SEARCH_MIN ? q : '';
    if (!searched) { results.items = []; results.total = 0; return; }
    try { await results.load(true); } catch (e) { toast.error(e.message); }
  }

  const focus = (node) => { node.focus(); };

  // ─── Herausnehmen und Zurückholen, gleich wo (Spieler, Ausgeblendet, Album) ───
  async function excludeOpened() {
    const album = opened.source;
    try {
      const entry = await excludeAlbum(album);
      toast.undo(`Album "${entry.name}" ausgeschlossen`, () => restoreHidden({ albums: [album] }).catch((e) => toast.error(e.message)));
    } catch (e) { toast.error(e.message); }
  }

  // Herausgenommenes verschwindet sofort; Zahlen, Kacheln und die offene Gruppe kommen leise neu
  async function onChange(change) {
    const gone = isRemoved(change);
    if (opened) opened = { ...opened, tracks: opened.tracks.filter((t) => !gone(t)) };
    results.items = results.items.filter((t) => !gone(t));
    if (!change.reload) return;
    loadOverview();
    const def = activeArea;
    try {
      if (def) { const fresh = await def.load(); if (activeArea?.id === def.id) items = fresh; }
      if (openKey) {
        const fresh = await api.musicPlay(openKey);
        if (fresh.tracks.length) opened = fresh;
        else back();                     // Gruppe leer: es gibt sie nicht mehr
      }
    } catch { /* bleibt beim bisherigen Stand */ }
  }
  onMount(() => onMusicChange(onChange));

  loadOverview();
</script>

<div class="musik">
  <header class="kopf">
    <h1 class="m-h1">Musik</h1>
    {#if overview && !empty}
      <button class="m-rund" onclick={() => go('/musik', { suche: '1' })} aria-label="In der Musik suchen"><i class="fa-solid fa-magnifying-glass"></i></button>
    {/if}
  </header>

  <div class="rollfeld" use:nearEnd={{ onNearEnd: () => { shown += STEP; }, canLoad: () => shown < items.length }}>
    <div class="inhalt">
      {#if failed}
        <div class="m-note"><p>Der Server ist gerade nicht erreichbar.</p>
          <button class="m-btn" onclick={loadOverview}><i class="fa-solid fa-rotate"></i> Erneut versuchen</button></div>
      {:else if !overview}
        <div class="m-spin"><i class="fa-solid fa-spinner fa-spin"></i></div>
      {:else if empty}
        <div class="m-note"><p>Noch keine Musik. Am Rechner auf der Kanalseite "Musikkanal" wählen, Videos in der
          Bibliothek als Musik festlegen oder einen Musikordner einhängen.</p></div>
      {:else}
        {#if showSources}
          <div class="quelle" role="radiogroup" aria-label="Quelle der Musik">
            {#each SOURCES as s (s.key)}
              <button role="radio" aria-checked={overview.source === s.key} class:an={overview.source === s.key} onclick={() => chooseSource(s.key)}>
                {s.label}{#if s.count}<span class="zahl anzahl">{overview.sources[s.count].toLocaleString('de-DE')}</span>{/if}</button>
            {/each}
          </div>
        {/if}

        {#if resume}
          <div class="weiter">
            <button class="weiter-text" onclick={playResume}>
              <span class="bild">{#if resume.cover_id}<img src={coverUrl(resume.cover_id)} alt="" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />{/if}
                <i class="fa-solid fa-book-open"></i></span>
              <span class="text">
                <span class="art"><i class="fa-solid fa-book-open"></i> Weiterhören</span>
                <span class="t">{resume.title}</span>
                <span class="w">Teil <span class="zahl">{resume.current_part}</span> von <span class="zahl">{resume.parts}</span>
                  · noch <span class="zahl">{formatDurationLong(Math.max(60, resume.remaining))}</span></span>
                <span class="balken"><b style:width="{bookShare(resume) * 100}%"></b></span>
              </span>
            </button>
            <button class="spiel" onclick={playResume} aria-label={player.audiobook === resume.key && player.playing ? 'Pause' : 'Weiterhören'}>
              <i class="fa-solid {player.audiobook === resume.key && player.playing ? 'fa-pause' : 'fa-play'}"></i></button>
          </div>
        {/if}

        {#if counts.tracks}
          <div class="mixe">
            {#each MIXES as mix (mix.key)}
              <button class="mix" onclick={() => play(mix.key, { shuffle: mix.shuffle })}><i class="fa-solid {mix.icon}"></i><span>{mix.name}</span></button>
            {/each}
          </div>
        {/if}

        {#if areas.length}
          <div class="bereiche" role="tablist" style:--anzahl={areas.length}>
            {#each areas as a (a.id)}
              <button role="tab" aria-selected={activeArea?.id === a.id} class:an={activeArea?.id === a.id} onclick={() => chooseArea(a.id)}>{a.label}</button>
            {/each}
          </div>

          {#if areaLoading}
            <div class="m-spin"><i class="fa-solid fa-spinner fa-spin"></i></div>
          {:else}
            <div class="raster">
              {#each items.slice(0, shown) as item (item.key)}
                {#if activeArea?.id === 'hoerbuecher'}
                  <button class="kachel" class:laeuft={player.audiobook === item.key} onclick={() => play(`hoerbuch:${item.key}`)}>
                    <span class="bild"><i class="fa-solid fa-book-open"></i>
                      {#if item.cover_id}<img src={coverUrl(item.cover_id)} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />{/if}
                      {#if item.current_part && !item.finished}<span class="stand"><b style:width="{bookShare(item) * 100}%"></b></span>{/if}
                    </span>
                    <span class="t">{item.title}</span>
                    <span class="w">{bookLine(item)}</span>
                  </button>
                {:else}
                  <button class="kachel" onclick={() => go('/musik', { quelle: item.key })}>
                    <span class="bild"><i class="fa-solid fa-music"></i>
                      {#if item.covers?.[0]}<img src={coverUrl(item.covers[0])} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />{/if}
                    </span>
                    <span class="t">{item.name}</span>
                    <span class="w">{groupLine(item)}</span>
                  </button>
                {/if}
              {/each}
            </div>
            {#if items.length > shown}
              <p class="mehr"><span class="zahl">{shown}</span> von <span class="zahl">{items.length}</span>, weitere beim Rollen</p>
            {/if}
          {/if}
        {/if}
        {#if counts.hidden}
          <button class="ausgeblendet" onclick={() => go('/musik', { ausgeblendet: '1' })}>
            <i class="fa-solid fa-eye-slash"></i><span>Ausgeblendet</span><span class="zahl">{counts.hidden}</span>
            <i class="fa-solid fa-chevron-right"></i></button>
        {/if}
      {/if}
    </div>
  </div>

  {#if searching}
    <div class="ebene">
      <header class="kopf suche">
        <button class="m-rund" onclick={back} aria-label="Suche schließen"><i class="fa-solid fa-chevron-left"></i></button>
        <input type="search" placeholder="Titel, Interpret, Album" bind:value={query} oninput={onSearchInput}
               enterkeyhint="search" autocomplete="off" use:focus />
      </header>
      <div class="rollfeld" use:nearEnd={{ onNearEnd: results.loadMore, canLoad: results.canLoad }}>
        <div class="liste">
          {#if !searched}
            <p class="m-note">Mindestens <span class="zahl">{SEARCH_MIN}</span> Zeichen eingeben.</p>
          {:else if results.loading}
            <div class="m-spin"><i class="fa-solid fa-spinner fa-spin"></i></div>
          {:else}
            {#each results.items as track, i (track.id)}
              {@render titelZeile(track, () => player.playTracks(results.items, i, `Suche: ${searched}`))}
            {:else}
              <p class="m-note">Nichts gefunden.</p>
            {/each}
            {#if results.total > results.items.length}
              <p class="mehr"><span class="zahl">{results.items.length}</span> von <span class="zahl">{results.total}</span>, weitere beim Rollen</p>
            {/if}
          {/if}
        </div>
      </div>
    </div>
  {:else if hiddenOpen}
    <div class="ebene">
      <header class="kopf">
        <button class="m-rund" onclick={back} aria-label="Zurück"><i class="fa-solid fa-chevron-left"></i></button>
        <h1 class="m-h1 titel">Ausgeblendet</h1>
      </header>
      <div class="rollfeld"><Ausgeblendet /></div>
    </div>
  {:else if opened || openKey}
    <div class="ebene">
      <header class="kopf">
        <button class="m-rund" onclick={back} aria-label="Zurück"><i class="fa-solid fa-chevron-left"></i></button>
        <h1 class="m-h1 titel">{opened?.title || ''}</h1>
        {#if opened?.source?.startsWith('album:')}
          <button class="m-rund" onclick={excludeOpened} aria-label="Album ausschließen"><i class="fa-solid fa-ban"></i></button>
        {/if}
      </header>
      <div class="rollfeld" use:nearEnd={{ onNearEnd: () => { openedShown += STEP; }, canLoad: () => !!opened && openedShown < opened.tracks.length }}>
        {#if !opened}
          <div class="m-spin"><i class="fa-solid fa-spinner fa-spin"></i></div>
        {:else}
          <div class="knoepfe">
            <button class="m-btn primary" onclick={() => play(opened.source)}><i class="fa-solid fa-play"></i> Abspielen</button>
            <button class="m-btn" onclick={() => play(opened.source, { shuffle: true })}><i class="fa-solid fa-shuffle"></i> Zufällig</button>
          </div>
          <div class="liste">
            {#each opened.tracks.slice(0, openedShown) as track (track.id)}
              {@render titelZeile(track, () => play(opened.source, { start: track.id }))}
            {/each}
            <p class="mehr">
              {#if opened.tracks.length > openedShown}<span class="zahl">{openedShown}</span> von {/if}<span class="zahl">{opened.tracks.length}</span> Titel
            </p>
          </div>
        {/if}
      </div>
    </div>
  {/if}
</div>

{#snippet titelZeile(track, onplay)}
  <button class="zeile" class:laeuft={player.current?.id === track.id} onclick={onplay}>
    <img src={coverUrl(track)} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
    <span class="text"><span class="t">{track.title}</span><span class="w">{track.artist}</span></span>
    <span class="zahl dauer">{formatDuration(track.duration || 0)}</span>
  </button>
{/snippet}

<style>
  .musik { position: relative; height: 100%; display: flex; flex-direction: column; overflow: hidden; background: var(--m-bg); }
  .kopf { display: flex; align-items: center; gap: 12px; flex: none; height: calc(var(--m-safe-top) + 60px);
          padding: var(--m-safe-top) calc(var(--m-safe-right) + 12px) 0 calc(var(--m-safe-left) + 16px); background: var(--tv-leiste); }
  .kopf .m-h1 { flex: 1; min-width: 0; font-size: 22px; font-weight: 700; }
  .titel { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .rollfeld { flex: 1; min-height: 0; overflow-y: auto; overflow-x: hidden; overscroll-behavior: contain; }
  .inhalt { display: flex; flex-direction: column; gap: 16px; padding: 16px calc(var(--m-safe-right) + 16px) 24px calc(var(--m-safe-left) + 16px); }

  /* Quelle: global, gilt auch für Mixe */
  .quelle { display: grid; grid-template-columns: repeat(3, 1fr); gap: 3px; padding: 3px; background: var(--tv-mulde); border-radius: var(--m-radius); }
  .quelle button { min-height: 44px; padding: 0 4px; border-radius: var(--tv-ecke-klein); color: var(--m-dim); font-size: 15px; font-weight: 600; white-space: nowrap; }
  .quelle button.an { background: var(--tv-karte-3); color: var(--m-accent); }
  .anzahl { margin-left: 4px; font-size: 13px; color: var(--m-faint); }

  .weiter { display: grid; grid-template-columns: minmax(0, 1fr) 52px; gap: 12px; align-items: center; padding: 12px;
            background: var(--tv-karte); border-radius: var(--m-radius); }
  .weiter-text { display: grid; grid-template-columns: 76px minmax(0, 1fr); gap: 12px; align-items: center; min-width: 0; text-align: left; }
  .weiter-text .bild { width: 76px; height: 76px; }
  .weiter-text .text { display: flex; flex-direction: column; min-width: 0; }
  .art { font-size: 13px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--tv-art-vertont); }
  .weiter-text .t { font-size: 17px; font-weight: 700; }
  .weiter-text .w { font-size: 15px; color: var(--m-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .balken { display: block; height: 4px; margin-top: 6px; border-radius: 2px; background: var(--tv-mulde); overflow: hidden; }
  .balken b, .stand b { display: block; height: 100%; background: var(--m-accent); }
  .spiel { width: 52px; height: 52px; border-radius: var(--m-radius); background: var(--m-accent); color: var(--m-accent-ink); font-size: 20px; }

  .mixe { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .mix { display: flex; align-items: center; gap: 8px; min-height: 56px; padding: 6px 12px; border-radius: var(--m-radius);
         background: var(--tv-karte); font-size: 16px; font-weight: 600; text-align: left; line-height: 1.2; }
  .mix i { width: 32px; height: 32px; flex: none; display: grid; place-items: center; border-radius: var(--tv-ecke-klein);
           background: rgba(var(--tv-akzent-rgb), 0.14); color: var(--m-accent); font-size: 15px; }
  .mix:active { background: var(--tv-karte-2); }

  .bereiche { display: grid; grid-template-columns: repeat(var(--anzahl), 1fr); gap: 4px; }
  .bereiche button { min-height: 44px; padding: 0 2px; border-radius: var(--tv-ecke-klein); background: var(--m-surface);
                     color: var(--m-dim); font-size: 15px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .bereiche button.an { background: rgba(var(--tv-akzent-rgb), 0.14); color: var(--m-accent); }

  .raster { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px 12px; }
  .kachel { display: flex; flex-direction: column; min-width: 0; text-align: left; }
  .bild { position: relative; display: grid; place-items: center; overflow: hidden; border-radius: var(--tv-ecke-klein);
          background: var(--m-surface); color: var(--m-faint); font-size: 24px; flex: none; }
  .kachel .bild { width: 100%; aspect-ratio: 1; }
  .bild img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
  .stand { position: absolute; left: 0; right: 0; bottom: 0; height: 4px; background: rgba(0, 0, 0, 0.5); }
  .kachel .t { margin-top: 6px; font-size: 15px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .kachel .w { font-size: 13px; color: var(--m-faint); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .kachel.laeuft .t { color: var(--m-accent); }
  .mehr { padding: 8px 0; font-size: 15px; color: var(--m-faint); text-align: center; }
  .ausgeblendet { display: grid; grid-template-columns: 24px minmax(0, 1fr) auto 16px; gap: 10px; align-items: center; min-height: 52px;
                  padding: 0 14px; border-radius: var(--m-radius); background: var(--tv-karte); color: var(--m-dim);
                  font-weight: 600; text-align: left; }
  .ausgeblendet .zahl { color: var(--m-faint); }

  /* Gruppe oder Suche: über der Übersicht, die so ihre Stelle behält */
  .ebene { position: absolute; inset: 0; z-index: 1; display: flex; flex-direction: column; background: var(--m-bg); }
  .suche input { flex: 1; min-width: 0; height: 44px; padding: 0 12px; border: 0; border-radius: var(--m-radius);
                 background: var(--tv-mulde); color: var(--m-text); font-size: 17px; }
  .suche input:focus { outline: 2px solid rgba(var(--tv-akzent-rgb), 0.5); outline-offset: 0; }
  .knoepfe { display: flex; gap: 10px; padding: 16px calc(var(--m-safe-right) + 16px) 8px calc(var(--m-safe-left) + 16px); }
  .knoepfe .m-btn { flex: 1; }
  .liste { padding: 4px 0 24px; }
  .zeile { width: 100%; display: flex; align-items: center; gap: 12px; min-height: 64px;
           padding: 6px calc(var(--m-safe-right) + 16px) 6px calc(var(--m-safe-left) + 16px); text-align: left; }
  .zeile:active { background: var(--m-surface); }
  .zeile img { width: 52px; height: 52px; flex: none; object-fit: cover; border-radius: var(--tv-ecke-klein); background: var(--m-surface); }
  .zeile .text { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .zeile .t { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .zeile .w { font-size: 15px; color: var(--m-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .zeile.laeuft .t { color: var(--m-accent); }
  .dauer { font-size: 15px; color: var(--m-dim); }
</style>

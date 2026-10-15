<!--
  TubeVault – Musik (Gestaltung nach mockups/musik.html)
  Die als Musik gekennzeichneten Videos als Sammlung: Start, Titel,
  Interpreten, Alben, Lieblingssongs, Wiedergabelisten, Verlauf und
  Musikkanäle. Jede Gruppe ist eine dynamische Wiedergabeliste und lässt sich
  der Reihe nach oder zufällig abspielen; ein Klick auf eine Kachel spielt
  sofort. Rechts "Läuft gerade" mit Warteschlange und Liedtext.
  © HalloWelt42 – Private Nutzung
-->
<script>
  import HiddenFiles from '../lib/components/music/HiddenFiles.svelte';
  import { untrack } from 'svelte';
  import { get } from 'svelte/store';
  import { api } from '../lib/api/client.js';
  import { coverUrl } from '../lib/utils/musicTrack.js';
  import { route, navigate, updateParams } from '../lib/router/router.js';
  import { toast } from '../lib/stores/notifications.js';
  import { musicPlayer as player } from '../lib/stores/musicPlayer.svelte.js';
  import { formatDurationLong } from '../lib/utils/format.js';
  import { createListLoader } from '../lib/utils/listLoader.svelte.js';
  import { infiniteScroll } from '../lib/utils/infiniteScroll.js';
  import MusicTile from '../lib/components/music/MusicTile.svelte';
  import GroupTile from '../lib/components/music/GroupTile.svelte';
  import TrackTable from '../lib/components/music/TrackTable.svelte';
  import TrackMenu from '../lib/components/music/TrackMenu.svelte';
  import NowPlaying from '../lib/components/music/NowPlaying.svelte';

  const TABS = [
    { id: 'start', label: 'Start', icon: 'fa-house' },
    { id: 'titel', label: 'Titel', icon: 'fa-music', count: 'tracks' },
    { id: 'interpreten', label: 'Interpreten', icon: 'fa-microphone', count: 'artists' },
    { id: 'alben', label: 'Alben', icon: 'fa-compact-disc', count: 'albums' },
    { id: 'lieblingssongs', label: 'Lieblingssongs', icon: 'fa-heart', count: 'favorites' },
    { id: 'wiedergabelisten', label: 'Wiedergabelisten', icon: 'fa-list-ul' },
    { id: 'verlauf', label: 'Verlauf', icon: 'fa-clock-rotate-left' },
    { id: 'kanaele', label: 'Musikkanäle', icon: 'fa-tv', count: 'channels' },
    { id: 'hoerbuecher', label: 'Hörbücher', icon: 'fa-book-open', count: 'books', onlyWithCount: true },
    { id: 'jetzt', label: 'Läuft gerade', icon: 'fa-headphones', narrowOnly: true },
  ];
  const SORTS = [['added', 'Neu'], ['title', 'Titel'], ['artist', 'Interpret'], ['plays', 'Oft gehört'], ['duration', 'Dauer'], ['last_played', 'Zuletzt gehört']];
  // Mixe auf der Startseite: dynamische Listen ohne eigene Gruppe
  const MIXES = [
    { key: 'all', name: 'Alles zufällig', icon: 'fa-shuffle', shuffle: true },
    { key: 'favorites', name: 'Lieblingssongs', icon: 'fa-heart', shuffle: true },
    { key: 'forgotten', name: 'Lange nicht gehört', icon: 'fa-hourglass-half', shuffle: true },
    { key: 'new', name: 'Neu in der Sammlung', icon: 'fa-star', shuffle: false },
  ];

  const params = get(route).params || {};
  let tab = $state(TABS.some(t => t.id === params.tab) ? params.tab : 'start');
  let source = $state(params.quelle || null);       // geöffnete Gruppe, z.B. "artist:abba"
  let nowView = $state(params.ansicht || 'schlange');
  let query = $state(params.q || '');
  let sort = $state(params.sort || 'added');
  let overview = $state(null);
  let groups = $state([]);                             // Interpreten, Alben, Kanäle, Wiedergabelisten
  let groupTracks = $state(null);                      // Titel der geöffneten Gruppe oder des Verlaufs
  let groupHeadHeight = $state(0);                     // Höhe des stehenden Gruppenkopfs (Spaltenköpfe darunter)
  let books = $state([]);                              // Hörbücher (eigener Bereich)
  let loading = $state(false);
  let menu;

  // Klick auf eine Musik-Adresse, während die Seite schon offen ist
  $effect(() => {
    const p = $route.params || {};
    untrack(() => {
      if (p.quelle !== undefined && p.quelle !== source) source = p.quelle || null;
      if (p.tab && p.tab !== tab && TABS.some(t => t.id === p.tab)) tab = p.tab;
      if (p.ansicht) nowView = p.ansicht;
    });
  });

  const counts = $derived(overview?.counts || {});

  // Quelle der Musik (gilt global für Seite und Spieler): alle | sammlung | videos
  const SOURCES = [
    { key: 'alle', label: 'Alles', icon: 'fa-layer-group' },
    { key: 'sammlung', label: 'Eigene Sammlung', icon: 'fa-compact-disc', count: 'sammlung' },
    { key: 'videos', label: 'Musikvideos', icon: 'fa-film', count: 'videos' },
  ];
  let scanning = $state(false);

  async function chooseSource(key) {
    if (overview?.source === key) return;
    try {
      await api.updateSetting('music.source', key);
      await loadOverview();
      await loadTab();
    } catch (e) { toast.error(e.message); }
  }

  async function scanCollection() {
    scanning = true;
    try {
      const r = await api.musicFilesScan();
      toast.success(`${r.files.toLocaleString('de-DE')} Dateien, ${r.read.toLocaleString('de-DE')} neu gelesen, ${r.removed} entfernt`);
      await loadOverview();
      await loadTab();
    } catch (e) { toast.error(e.message); }
    finally { scanning = false; }
  }

  async function loadOverview() {
    try { overview = await api.musicOverview(); } catch (e) { toast.error(e.message); }
  }

  // Titel (seitenweise, sortiert, durchsuchbar) und Lieblingssongs
  const PAGE = 100;
  const list = createListLoader(async (page) => {
    const r = await api.musicTracks({ sort, q: query.trim(), favorites: tab === 'lieblingssongs',
                                      offset: (page - 1) * PAGE, limit: PAGE });
    return { items: r.items, total: r.total };
  });

  async function loadTab() {
    loading = true;
    groupTracks = null;
    try {
      if (source) {
        groupTracks = await api.musicPlay(source);
      } else if (tab === 'titel' || tab === 'lieblingssongs') {
        await list.load(true);
      } else if (tab === 'interpreten') {
        groups = await api.musicArtists();
      } else if (tab === 'alben') {
        groups = await api.musicAlbums();
      } else if (tab === 'kanaele') {
        groups = await api.musicChannels();
      } else if (tab === 'wiedergabelisten') {
        const playlists = await api.getPlaylists();
        groups = (Array.isArray(playlists) ? playlists : playlists.playlists || []).map(p => ({
          key: `playlist:${p.id}`, name: p.name, count: p.video_count || 0, duration: 0, covers: [] }));
      } else if (tab === 'verlauf') {
        groupTracks = await api.musicPlay('recent');
      } else if (tab === 'hoerbuecher') {
        books = await api.musicBooks();
      }
    } catch (e) { toast.error(e.message); }
    loading = false;
  }

  $effect(() => { loadOverview(); });
  $effect(() => { tab; source; sort; untrack(loadTab); });

  let searchTimer;
  function onSearch() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      if (tab !== 'titel') chooseTab('titel'); else list.load(true);
      updateParams({ q: query.trim() || null });
    }, 300);
  }

  function chooseTab(id) {
    tab = id;
    source = null;
    updateParams({ tab: id === 'start' ? null : id, quelle: null });
  }

  function openGroup(key) {
    source = key;
    updateParams({ quelle: key });
  }

  function chooseSort(value) {
    sort = value;
    updateParams({ sort: value === 'added' ? null : value });
  }

  // ─── Abspielen ───
  async function play(key, shuffle = false) {
    try {
      if (!await player.playSource(key, { shuffle })) toast.info('Dort gibt es noch keine Titel');
    } catch (e) { toast.error(e.message); }
  }

  /** Klick auf einen Titel einer sichtbaren Liste: von dort an abspielen */
  function playFrom(tracks, index, title, key = null) {
    if (key) player.playSource(key, { start: tracks[index].id }).catch((e) => toast.error(e.message));
    else player.playTracks(tracks, index, title);
  }

  // Änderungen aus dem Menü in die sichtbaren Listen übernehmen
  function changed(track, change) {
    if (change.restored) { loadOverview(); loadTab(); return; }
    const update = (items) => change.removed ? items.filter(t => t.id !== track.id)
                                             : items.map(t => t.id === track.id ? { ...t, ...change } : t);
    list.items = update(list.items);
    if (groupTracks) groupTracks = { ...groupTracks, tracks: update(groupTracks.tracks) };
    if (overview) overview = { ...overview, new: update(overview.new), often: update(overview.often) };
    if (change.removed) loadOverview();
  }

  async function favorite(track) {
    try { changed(track, { favorite: await player.toggleFavorite(track) }); } catch (e) { toast.error(e.message); }
  }

  const openMenu = (e, track) => menu?.open(e, track);
  const onOpenArtist = (track) => openGroup(track.artist_source);
  const onOpenVideo = (track) => navigate(`/watch/${track.id}`);
  const groupName = $derived(groupTracks?.title || '');
  const groupDuration = $derived((groupTracks?.tracks || []).reduce((sum, t) => sum + (t.duration || 0), 0));
</script>

<div class="tv-seite">
  <div class="tv-seitenkopf">
    <div class="kopfzeile">
      <h1>Musik</h1>
      {#if overview}
        <span class="tv-schwach zahl">{counts.tracks} Titel · {counts.artists} Interpreten · {formatDurationLong(counts.duration)}</span>
        <div class="quellen" role="group" aria-label="Quelle der Musik">
          {#each SOURCES as q (q.key)}
            <button class:an={overview.source === q.key} onclick={() => chooseSource(q.key)}
                    title={q.key === 'alle' ? 'Sammlung und Musikvideos; doppelte Songs nur einmal (die Datei gilt)' : ''}>
              <i class="fa-solid {q.icon}"></i> {q.label}{#if q.count}<span class="zahl">{(overview.sources[q.count] || 0).toLocaleString('de-DE')}</span>{/if}
            </button>
          {/each}
          <button class="einlesen" onclick={scanCollection} disabled={scanning} title="Eigene Sammlung neu einlesen (nur Neues und Geändertes)">
            <i class="fa-solid fa-rotate" class:fa-spin={scanning}></i></button>
          <HiddenFiles onRestored={() => { loadOverview(); loadTab(); }} />
        </div>
      {/if}
      <div class="aktionen">
        <input class="tv-eingabe suche" bind:value={query} oninput={onSearch} placeholder="Titel, Interpret, Album" />
        {#if player.active && !player.playing}
          <button class="tv-knopf" onclick={() => player.resume()} title="Weiter mit der letzten Warteschlange">
            <i class="fa-solid fa-rotate-left"></i> Weiterhören</button>
        {/if}
        <button class="tv-knopf haupt" onclick={() => play('all', true)}><i class="fa-solid fa-shuffle"></i> Alles zufällig</button>
      </div>
    </div>
    <div class="tv-reiter">
      {#each TABS.filter(t => !t.onlyWithCount || counts[t.count]) as t (t.id)}
        <button class:aktiv={tab === t.id && !source} class:schmal={t.narrowOnly} onclick={() => chooseTab(t.id)}>
          <i class="fa-solid {t.icon}"></i> {t.label}{#if t.count && counts[t.count]}<span class="tv-zaehler">{counts[t.count]}</span>{/if}
        </button>
      {/each}
    </div>
  </div>

  <div class="musik">
    <div class="tv-rollfeld" data-scroll-root>
      {#if source}
        <!-- Geöffnete Gruppe: Interpret, Album, Kanal, Wiedergabeliste, Mix -->
        <div class="gruppenkopf" bind:clientHeight={groupHeadHeight}>
          <button class="tv-knopf ohne klein" onclick={() => { source = null; updateParams({ quelle: null }); }}>
            <i class="fa-solid fa-arrow-left"></i> Zurück</button>
          {#if groupTracks}
            <div class="gruppen-titel">
              <h2>{groupName}</h2>
              <span class="tv-leise zahl">{groupTracks.tracks.length} Titel · {formatDurationLong(groupDuration)}</span>
            </div>
            <div class="tasten">
              <button class="tv-knopf haupt" onclick={() => play(source)} disabled={!groupTracks.tracks.length}>
                <i class="fa-solid fa-play"></i> Abspielen</button>
              <button class="tv-knopf" onclick={() => play(source, true)} disabled={!groupTracks.tracks.length}>
                <i class="fa-solid fa-shuffle"></i> Zufällig</button>
              <a class="tv-knopf" href={api.musicZipUrl(source)} download
                 title="Alle Titel nur als Ton in einem ZIP (wie geladen, ohne Neukodierung, ohne Werbestellen)">
                <i class="fa-solid fa-file-zipper"></i> Als ZIP</a>
            </div>
          {/if}
        </div>
        {#if groupTracks}
          <TrackTable tracks={groupTracks.tracks} onMenu={openMenu} onFavorite={favorite} stickyTop={`calc(${groupHeadHeight}px - var(--tv-a2))`}
                      onPlay={(i) => playFrom(groupTracks.tracks, i, groupName, source)} />
        {:else if loading}
          <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt ...</div>
        {/if}

      {:else if tab === 'start'}
        {#if !overview}
          <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt ...</div>
        {:else if !counts.tracks}
          <div class="start-leer tv-karte">
            <h3><i class="fa-solid fa-music"></i> Noch keine Musik</h3>
            <p class="tv-leise">Musik ist, was du festlegst - automatisch nur Eindeutiges. Am schnellsten geht es über
              ganze Kanäle: auf der Kanalseite "Musikkanal" wählen, dann gelten alle Videos darin als Musik; Ausreißer
              nimmst du einzeln wieder heraus. Einzelne Videos legst du in der Bibliothek per Mehrfachauswahl fest.</p>
          </div>
        {:else}
          {#if player.active}
            <section class="abschnitt">
              <div class="weiter">
                <img src={coverUrl(player.current)} alt="" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
                <div class="text">
                  <span class="tv-etikett">{player.playing ? 'Läuft gerade' : 'Weiterhören'}</span>
                  <div class="titel">{player.current.title}</div>
                  <div class="tv-leise tv-klein">{player.current.artist} · noch {player.upcoming.length} Titel in der Warteschlange</div>
                </div>
                <button class="tv-knopf haupt" onclick={() => player.toggle()}>
                  <i class="fa-solid {player.playing ? 'fa-pause' : 'fa-play'}"></i> {player.playing ? 'Pause' : 'Fortsetzen'}</button>
              </div>
            </section>
          {/if}

          <section class="abschnitt">
            <div class="abschnitt-kopf"><h2>Mixe</h2></div>
            <div class="raster">
              {#each MIXES as mix (mix.key)}
                <button class="mix" onclick={() => play(mix.key, mix.shuffle)}>
                  <i class="fa-solid {mix.icon}"></i><span>{mix.name}</span></button>
              {/each}
            </div>
          </section>

          {#if overview.artists.length}
            <section class="abschnitt">
              <div class="abschnitt-kopf"><h2>Interpreten</h2>
                <button class="mehr" onclick={() => chooseTab('interpreten')}>Alle zeigen</button></div>
              <div class="raster">
                {#each overview.artists as group (group.key)}<GroupTile {group} onOpen={() => openGroup(group.key)} />{/each}
              </div>
            </section>
          {/if}

          <section class="abschnitt">
            <div class="abschnitt-kopf"><h2>Neu in der Sammlung</h2>
              <button class="mehr" onclick={() => chooseTab('titel')}>Alle zeigen</button></div>
            <div class="raster">
              {#each overview.new as track, i (track.id)}
                <MusicTile {track} onMenu={openMenu} onPlay={() => playFrom(overview.new, i, 'Neu in der Sammlung', 'new')} />
              {/each}
            </div>
          </section>

          {#if overview.often.length}
            <section class="abschnitt">
              <div class="abschnitt-kopf"><h2>Oft gehört</h2></div>
              <TrackTable tracks={overview.often} showPlays onMenu={openMenu} onFavorite={favorite}
                          onPlay={(i) => playFrom(overview.often, i, 'Oft gehört', 'often')} />
            </section>
          {/if}

          {#if overview.channels.length}
            <section class="abschnitt">
              <div class="abschnitt-kopf"><h2>Musikkanäle</h2>
                <button class="mehr" onclick={() => chooseTab('kanaele')}>Alle zeigen</button></div>
              <div class="raster">
                {#each overview.channels.slice(0, 6) as group (group.key)}<GroupTile {group} onOpen={() => openGroup(group.key)} />{/each}
              </div>
            </section>
          {/if}
        {/if}

      {:else if tab === 'titel' || tab === 'lieblingssongs'}
        <div class="leiste">
          <button class="tv-knopf haupt klein" onclick={() => play(tab === 'titel' ? 'all' : 'favorites')}>
            <i class="fa-solid fa-play"></i> Alle abspielen</button>
          <button class="tv-knopf klein" onclick={() => play(tab === 'titel' ? 'all' : 'favorites', true)}>
            <i class="fa-solid fa-shuffle"></i> Zufällig</button>
          <span class="tv-trenner"></span>
          <span class="tv-etikett">Sortieren</span>
          {#each SORTS as [value, label]}
            <button class="tv-chip" class:aktiv={sort === value} onclick={() => chooseSort(value)}>{label}</button>
          {/each}
          <span class="tv-schwach tv-klein zahl anzahl">{list.total} Titel</span>
        </div>
        {#if list.loading}
          <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt ...</div>
        {:else if !list.items.length}
          <div class="tv-leer">{tab === 'lieblingssongs' ? 'Noch keine Lieblingssongs - das Herz an einem Titel setzt einen.' : 'Keine Titel gefunden.'}</div>
        {:else}
          <TrackTable tracks={list.items} onMenu={openMenu} onFavorite={favorite}
                      onPlay={(i) => playFrom(list.items, i, tab === 'titel' ? 'Titel' : 'Lieblingssongs')} />
          <div use:infiniteScroll={{ onLoadMore: list.loadMore, canLoad: list.canLoad }}></div>
        {/if}

      {:else if tab === 'verlauf'}
        {#if groupTracks?.tracks.length}
          <TrackTable tracks={groupTracks.tracks} onMenu={openMenu} onFavorite={favorite}
                      onPlay={(i) => playFrom(groupTracks.tracks, i, 'Zuletzt gehört')} />
        {:else if !loading}
          <div class="tv-leer">Noch nichts gehört.</div>
        {/if}

      {:else if tab === 'jetzt'}
        <div class="jetzt-schmal"><NowPlaying view={nowView} {onOpenArtist} {onOpenVideo} /></div>

      {:else if tab === 'hoerbuecher'}
        <!-- Hörbücher: nie zufällig, immer in ihrer Reihenfolge, Weiterhören an der gemerkten Stelle -->
        {#if loading}
          <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt ...</div>
        {:else}
          <div class="buecher">
            {#each books as book (book.key)}
              <div class="buch" class:laeuft={player.audiobook === book.key}>
                <div class="buch-bild">
                  {#if book.cover_id}<img src={coverUrl(book.cover_id)} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
                  {:else}<i class="fa-solid fa-book-open"></i>{/if}
                </div>
                <div class="buch-text">
                  <div class="buch-titel">{book.title}</div>
                  {#if book.author}<div class="tv-leise tv-klein">{book.author}</div>{/if}
                  <div class="tv-schwach tv-klein">
                    {#if book.finished}Zu Ende gehört
                    {:else if book.current_part}Teil <span class="zahl">{book.current_part}</span> von <span class="zahl">{book.parts}</span> · noch <span class="zahl">{formatDurationLong(book.remaining)}</span>
                    {:else}<span class="zahl">{book.parts}</span> Teile · <span class="zahl">{formatDurationLong(book.duration)}</span>{/if}
                  </div>
                  <div class="buch-fort"><b style:width="{book.duration ? Math.round((book.duration - book.remaining) / book.duration * 100) : 0}%"></b></div>
                  <div class="buch-tasten">
                    <button class="tv-knopf klein haupt" onclick={() => player.playSource(`hoerbuch:${book.key}`)}>
                      <i class="fa-solid fa-{book.current_part && !book.finished ? 'rotate-left' : 'play'}"></i>
                      {book.current_part && !book.finished ? 'Weiterhören' : 'Anhören'}</button>
                    {#if book.current_part}
                      <button class="tv-knopf klein" onclick={async () => { await api.musicBookRestart(book.key); await player.playSource(`hoerbuch:${book.key}`); }}>
                        <i class="fa-solid fa-backward-step"></i> Von vorn</button>
                    {/if}
                  </div>
                </div>
              </div>
            {:else}
              <div class="tv-leer">Keine Hörbücher in der Sammlung.</div>
            {/each}
          </div>
        {/if}

      {:else}
        {#if loading}
          <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt ...</div>
        {:else if !groups.length}
          <div class="tv-leer tv-klein">
            {#if tab === 'alben'}Alben entstehen, sobald an Titeln ein Album eingetragen ist (Liedtext-Fenster der Videoansicht).
            {:else if tab === 'kanaele'}Noch kein Musikkanal - auf der Kanalseite "Musikkanal" wählen.
            {:else}Hier ist noch nichts.{/if}
          </div>
        {:else}
          <div class="raster">
            {#each groups as group (group.key)}
              <GroupTile {group} icon={tab === 'wiedergabelisten' ? 'fa-list-ul' : null} onOpen={() => openGroup(group.key)} />
            {/each}
          </div>
        {/if}
      {/if}
    </div>

    <aside class="jetzt-spalte">
      <NowPlaying view={nowView} {onOpenArtist} {onOpenVideo} />
    </aside>
  </div>
</div>

<TrackMenu bind:this={menu} onChanged={changed} />

<style>
  .kopfzeile { display: flex; align-items: baseline; gap: var(--tv-a4); margin-bottom: var(--tv-a4); flex-wrap: wrap; }
  .kopfzeile h1 { margin: 0; font-size: var(--tv-gr-seite); }
  .quellen { display: inline-flex; align-items: center; gap: 2px; padding: 2px; background: var(--tv-mulde); border-radius: var(--tv-ecke);
             align-self: center; }
  .quellen button { display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 10px; border: 0; background: none;
                    color: var(--tv-text-2); border-radius: var(--tv-ecke-klein); font: inherit; font-size: var(--tv-gr-klein); cursor: pointer; }
  .quellen button.an { background: var(--tv-karte-3); color: var(--tv-akzent); font-weight: 700; }
  .quellen button .zahl { color: var(--tv-text-3); font-size: var(--tv-gr-marke); }
  .quellen .einlesen { width: 32px; padding: 0; justify-content: center; }
  .aktionen { margin-left: auto; display: flex; gap: var(--tv-a2); align-items: center; flex-wrap: wrap; }
  .suche { width: 240px; }
  .tv-reiter .schmal { display: none; }
  .buecher { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: var(--tv-a4); }
  .buch { display: grid; grid-template-columns: 112px minmax(0, 1fr); gap: var(--tv-a3); padding: var(--tv-a3);
          background: var(--tv-karte); border-radius: var(--tv-ecke); }
  .buch.laeuft { outline: 1px solid rgba(var(--tv-akzent-rgb), 0.6); }
  .buch-bild { width: 112px; aspect-ratio: 1; border-radius: var(--tv-ecke-klein); overflow: hidden; background: var(--tv-mulde);
               display: grid; place-items: center; color: var(--tv-text-3); font-size: 32px; }
  .buch-bild img { width: 100%; height: 100%; object-fit: cover; }
  .buch-text { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
  .buch-titel { font-weight: 700; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .buch-fort { height: 4px; background: var(--tv-mulde); border-radius: 1px; overflow: hidden; margin-top: 2px; }
  .buch-fort b { display: block; height: 100%; background: var(--tv-akzent); }
  .buch-tasten { display: flex; gap: var(--tv-a2); margin-top: auto; padding-top: var(--tv-a2); }

  .musik { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr) 360px; }
  /* Eigene Höhe als Maß für "Läuft gerade" (Bildgröße), nichts ragt heraus */
  .jetzt-spalte { border-left: 1px solid var(--tv-rand); background: var(--tv-leiste); min-height: 0;
                  overflow: hidden; container-type: size; }
  @media (max-width: 1100px) {
    .musik { grid-template-columns: minmax(0, 1fr); }
    .jetzt-spalte { display: none; }
    .tv-reiter .schmal { display: inline-flex; }
  }

  .abschnitt { margin-bottom: var(--tv-a6); }
  .abschnitt-kopf { display: flex; align-items: baseline; gap: var(--tv-a3); margin-bottom: var(--tv-a3); }
  .abschnitt-kopf h2 { margin: 0; font-size: var(--tv-gr-titel); }
  .mehr { margin-left: auto; padding: 0; border: 0; background: none; color: var(--tv-text-2); font: inherit;
          font-size: var(--tv-gr-klein); cursor: pointer; }
  .mehr:hover { color: var(--tv-akzent); }
  .raster { display: grid; grid-template-columns: repeat(auto-fill, minmax(176px, 1fr)); gap: var(--tv-a4); }

  .weiter { display: flex; align-items: center; gap: var(--tv-a4); padding: var(--tv-a3); background: var(--tv-flaeche); border-radius: var(--tv-ecke); }
  .weiter img { width: 96px; aspect-ratio: 1; object-fit: cover; border-radius: var(--tv-ecke-klein); }
  .weiter .text { flex: 1; min-width: 0; }
  .weiter .titel { font-weight: 700; font-size: 19px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  .mix { display: flex; flex-direction: column; justify-content: flex-end; gap: var(--tv-a2); aspect-ratio: 2 / 1;
         padding: var(--tv-a4); border: 0; border-radius: var(--tv-ecke); cursor: pointer; text-align: left; font: inherit;
         font-weight: 700; font-size: 18px; color: var(--tv-text);
         background: linear-gradient(135deg, rgba(192, 132, 252, 0.35), rgba(var(--tv-akzent-rgb), 0.15)); }
  .mix i { font-size: 24px; color: var(--tv-art-musik); }
  .mix:hover { filter: brightness(1.15); }

  /* Kopf der geöffneten Gruppe bleibt beim Rollen stehen, die Spaltenköpfe direkt darunter */
  .gruppenkopf { position: sticky; top: calc(-1 * var(--tv-a2)); z-index: 3; display: flex; align-items: center; gap: var(--tv-a4);
                 flex-wrap: wrap; margin: calc(-1 * var(--tv-a2)) 0 0; padding: var(--tv-a3) 0; background: var(--tv-grund); }
  .gruppen-titel h2 { margin: 0; font-size: 26px; }
  .gruppenkopf .tasten { margin-left: auto; display: flex; gap: var(--tv-a2); }
  .leiste { display: flex; align-items: center; gap: var(--tv-a2); flex-wrap: wrap; margin-bottom: var(--tv-a3); }
  .anzahl { margin-left: auto; }
  .start-leer { max-width: 760px; }
  .start-leer p { margin: 0; }
  .jetzt-schmal { max-width: 520px; }
</style>

<!--
  TubeVault – Aufräumen
  Bestand sichten und ausmisten: Shorts, alle Videos eines Kanals, große und
  lange nicht gesehene Videos. Klick wählt aus, Umschalt-Klick wählt einen
  Bereich, "Alle auswählen" nimmt die ganze Sicht über alle Seiten.
  Gelöscht wird restlos (Dateien, Datenbank, Suche); gelöschte Videos holt
  der Auto-Download nicht von selbst zurück.
-->
<script>
  import { api } from '../lib/api/client.js';
  import { route, updateParams } from '../lib/router/router.js';
  import { toast } from '../lib/stores/notifications.js';
  import { formatDuration, formatSize, formatDateRelative } from '../lib/utils/format.js';
  import { createListLoader } from '../lib/utils/listLoader.svelte.js';
  import { infiniteScroll } from '../lib/utils/infiniteScroll.js';
  import ConfirmDialog from '../lib/components/common/ConfirmDialog.svelte';

  const VIEWS = [
    { id: 'shorts', label: 'Shorts', icon: 'fa-solid fa-mobile-screen',
      hint: 'Alle als Short geführten Videos (ab dem Start von Shorts im September 2020). Falsch eingeordnete mit "Kein Short" umstellen; "Kanal schützen" nimmt alle Videos eines Kanals dauerhaft aus den Shorts. Beides verschwindet sofort aus dieser Liste.' },
    { id: 'channel', label: 'Nach Kanal', icon: 'fa-solid fa-tv',
      hint: 'Alle geladenen Videos eines Kanals.' },
    { id: 'big', label: 'Groß und selten gesehen', icon: 'fa-solid fa-hard-drive',
      hint: 'Größte Videos zuerst, mit letzter Wiedergabe.' },
  ];
  const PAGE = 60;
  const DELETE_CHUNK = 100;

  let confirmRef;
  let view = $state(VIEWS.some(v => v.id === $route.params?.sicht) ? $route.params.sicht : 'shorts');
  let channelId = $state($route.params?.kanal || null);
  let channelList = $state([]);
  let channelFilter = $state('');
  let totalBytes = $state(0);

  let exempt = $state([]);           // Kanäle, die nie Shorts führen

  async function loadExempt() {
    try { exempt = await api.cleanupExemptChannels(); } catch { exempt = []; }
  }

  // Ganzer Kanal führt nie Shorts: alle seine Kacheln verschwinden
  async function protectChannel(video) {
    const name = video.channel_name || video.channel_id;
    const ok = await confirmRef.ask(
      `"${name}" schützen?`,
      'Videos dieses Kanals gelten künftig nie als Short - auch neue nicht. Sie verschwinden aus dieser Liste, aus dem Shorts-Ausschluss und lassen sich hier nicht mehr als Short löschen.',
      { confirmLabel: 'Kanal schützen', danger: false });
    if (!ok) return;
    try {
      const result = await api.setShortExempt(video.channel_id, true);
      const gone = list.items.filter(v => v.channel_id === video.channel_id);
      list.items = list.items.filter(v => v.channel_id !== video.channel_id);
      list.total = Math.max(0, list.total - result.changed);
      totalBytes = Math.max(0, totalBytes - gone.reduce((sum, v) => sum + (v.file_size || 0), 0));
      selected = new Set([...selected].filter(id => !gone.some(v => v.id === id)));
      allSelected = false;
      toast.success(`"${name}" geschützt, ${result.changed} Videos umgestellt`);
      loadExempt();
    } catch (e) { toast.error(e.message); }
  }

  async function unprotectChannel(channel) {
    try {
      await api.setShortExempt(channel.channel_id, false);
      toast.info(`Schutz für "${channel.channel_name || channel.channel_id}" aufgehoben (bestehende Videos bleiben Videos)`);
      loadExempt();
    } catch (e) { toast.error(e.message); }
  }

  let selected = $state(new Set());
  let allSelected = $state(false);     // ganze Sicht über alle Seiten ausgewählt
  let lastClicked = null;              // Anker für Umschalt-Klick
  let busy = $state('');               // laufende Mengenaktion (Text)

  const list = createListLoader(async (page) => {
    if (view === 'channel' && !channelId) return { items: [], total: 0 };
    const offset = page === 1 ? 0 : list.items.length;
    const result = await api.cleanupVideos(view, { channelId, offset, limit: PAGE });
    totalBytes = result.total_bytes;
    return { items: result.videos, total: result.total };
  });

  let currentView = $derived(VIEWS.find(v => v.id === view));
  let currentChannel = $derived(channelList.find(c => c.channel_id === channelId));
  let channelMatches = $derived(
    channelFilter.trim()
      ? channelList.filter(c => (c.channel_name || c.channel_id).toLowerCase().includes(channelFilter.trim().toLowerCase())).slice(0, 12)
      : channelList.slice(0, 12)
  );
  let selectedCount = $derived(allSelected ? list.total : selected.size);
  let selectedBytes = $derived(
    allSelected ? totalBytes
      : list.items.filter(v => selected.has(v.id)).reduce((sum, v) => sum + (v.file_size || 0), 0)
  );

  function resetSelection() { selected = new Set(); allSelected = false; lastClicked = null; }

  function chooseView(id) {
    view = id;
    resetSelection();
    updateParams({ sicht: id, kanal: id === 'channel' ? channelId : null });
    list.load(true);
  }

  function chooseChannel(channel) {
    channelId = channel.channel_id;
    channelFilter = '';
    resetSelection();
    updateParams({ sicht: 'channel', kanal: channelId });
    list.load(true);
  }

  function toggle(video, event) {
    allSelected = false;
    const next = new Set(selected);
    if (event.shiftKey && lastClicked) {
      // Bereich zwischen letztem Klick und diesem auswählen
      const ids = list.items.map(v => v.id);
      const [from, to] = [ids.indexOf(lastClicked), ids.indexOf(video.id)].sort((a, b) => a - b);
      if (from >= 0) ids.slice(from, to + 1).forEach(id => next.add(id));
    } else if (next.has(video.id)) {
      next.delete(video.id);
    } else {
      next.add(video.id);
    }
    lastClicked = video.id;
    selected = next;
  }

  function selectLoaded() {
    allSelected = false;
    selected = new Set(list.items.map(v => v.id));
  }

  async function selectAll() {
    try {
      selected = new Set(await api.cleanupIds(view, view === 'channel' ? channelId : null));
      allSelected = true;
    } catch (e) { toast.error(e.message); }
  }

  // Falsch eingeordnetes Video: als normales Video führen und aus der Liste nehmen,
  // damit es nicht versehentlich mit den Shorts gelöscht wird
  async function notAShort(video) {
    try {
      await api.setTypeBatch([video.id], 'video');
      list.items = list.items.filter(v => v.id !== video.id);
      list.total = Math.max(0, list.total - 1);
      totalBytes = Math.max(0, totalBytes - (video.file_size || 0));
      if (selected.has(video.id)) {
        const next = new Set(selected);
        next.delete(video.id);
        selected = next;
      }
      allSelected = false;
      toast.success(`"${video.title}" gilt jetzt als Video`);
    } catch (e) { toast.error(e.message); }
  }

  async function deleteSelected() {
    const ids = [...selected];
    if (!ids.length) return;
    const ok = await confirmRef.ask(
      `${ids.length} ${ids.length === 1 ? 'Video' : 'Videos'} restlos löschen?`,
      `Gibt ${formatSize(selectedBytes)} frei. Dateien, Einträge und Suchtreffer verschwinden; `
      + 'der Auto-Download holt diese Videos nicht von selbst zurück.',
      { confirmLabel: 'Restlos löschen' });
    if (!ok) return;
    let deleted = 0, freed = 0;
    try {
      for (let i = 0; i < ids.length; i += DELETE_CHUNK) {
        busy = `Lösche ${Math.min(i + DELETE_CHUNK, ids.length)} von ${ids.length}…`;
        const result = await api.cleanupDelete(ids.slice(i, i + DELETE_CHUNK));
        deleted += result.deleted;
        freed += result.freed_bytes;
      }
      toast.success(`${deleted} gelöscht, ${formatSize(freed)} frei`);
    } catch (e) {
      toast.error(`Nach ${deleted} gelöschten abgebrochen: ${e.message}`);
    }
    busy = '';
    resetSelection();
    list.load(true);
    if (view === 'channel') loadChannels();
  }

  function openVideo(video, event) {
    event.stopPropagation();
    window.open(`/watch/${video.id}`, '_blank', 'noopener');
  }

  function lastSeen(video) {
    if (!video.last_played) return 'nie gesehen';
    return `gesehen ${formatDateRelative(video.last_played)}`;
  }

  async function loadChannels() {
    try { channelList = await api.cleanupChannels(); } catch { channelList = []; }
  }

  $effect(() => { loadChannels(); loadExempt(); list.load(true); });
</script>

<!-- Fester Kopf mit Sichten, Kanalwahl und Auswahlleiste; darunter rollen die Zeilen
     (Entwurf mockups/werkzeuge.html, Zustand Aufräumen) -->
<div class="tv-seite">
 <div class="tv-seitenkopf">
  <div class="kopfzeile">
    <h1>Aufräumen</h1>
    <span class="tv-leise">Bestand ausmisten, restlos löschen</span>
  </div>
  <div class="tv-reiter reiter">
    {#each VIEWS as v (v.id)}
      <button class:aktiv={view === v.id} onclick={() => chooseView(v.id)}><i class={v.icon}></i> {v.label}</button>
    {/each}
  </div>
  <p class="hinweis">{currentView.hint}</p>

  {#if view === 'shorts' && exempt.length > 0}
    <div class="geschuetzt">
      <span class="tv-leise"><i class="fa-solid fa-shield-halved"></i> Geschützte Kanäle (nie Shorts):</span>
      {#each exempt as channel (channel.channel_id)}
        <span class="tv-chip">{channel.channel_name || channel.channel_id}
          <button class="weg" title="Schutz aufheben" aria-label="Schutz aufheben" onclick={() => unprotectChannel(channel)}><i class="fa-solid fa-xmark"></i></button>
        </span>
      {/each}
    </div>
  {/if}

  {#if view === 'channel'}
    <div class="kanalwahl">
      {#if currentChannel}
        <span class="gewaehlt"><i class="fa-solid fa-tv"></i> {currentChannel.channel_name || currentChannel.channel_id}
          · <span class="zahl">{currentChannel.videos}</span> Videos · <span class="zahl">{formatSize(currentChannel.bytes)}</span></span>
      {/if}
      <input class="tv-eingabe" type="text" placeholder="Kanal suchen" bind:value={channelFilter} aria-label="Kanal suchen" />
      <div class="kanaele">
        {#each channelMatches as c (c.channel_id)}
          <button class="tv-chip" class:aktiv={c.channel_id === channelId} onclick={() => chooseChannel(c)}>
            {c.channel_name || c.channel_id} <span class="tv-zaehler">{c.videos}</span></button>
        {/each}
      </div>
    </div>
  {/if}

  <div class="auswahl" class:aktiv={selectedCount > 0}>
    {#if selectedCount > 0}
      <i class="fa-solid fa-square-check"></i>
      <span><span class="zahl">{selectedCount}</span> gewählt, <span class="zahl">{formatSize(selectedBytes)}</span></span>
    {:else}
      <span><span class="zahl">{list.total}</span> Videos, <span class="zahl">{formatSize(totalBytes)}</span></span>
    {/if}
    <div class="rechts">
      {#if selectedCount > 0}<button class="tv-knopf ohne klein" onclick={resetSelection}>Auswahl aufheben</button>{/if}
      <button class="tv-knopf ohne klein" onclick={selectLoaded} disabled={!list.items.length}>Geladene wählen</button>
      <button class="tv-knopf klein" onclick={selectAll} disabled={!list.total}>Alle <span class="zahl">{list.total}</span> wählen</button>
      <button class="tv-knopf klein gefahr" onclick={deleteSelected} disabled={!selectedCount || !!busy}>
        <i class="fa-solid fa-trash-can"></i> {busy || 'Restlos löschen'}</button>
    </div>
  </div>
 </div>

 <div class="tv-rollfeld" data-scroll-root>
  {#if list.loading}
    <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt ...</div>
  {:else if view === 'channel' && !channelId}
    <div class="tv-leer">Oben einen Kanal wählen.</div>
  {:else if list.items.length === 0}
    <div class="tv-leer">Nichts mehr da.</div>
  {:else}
    <div class="zeilen">
      {#each list.items as video (video.id)}
        {@const isSelected = selected.has(video.id)}
        <div class="zeile" class:gewaehlt={isSelected} role="button" tabindex="0" aria-pressed={isSelected}
             onclick={(e) => toggle(video, e)} onkeydown={(e) => e.key === ' ' && (e.preventDefault(), toggle(video, e))}>
          <i class="fa-{isSelected ? 'solid fa-square-check' : 'regular fa-square'} haken"></i>
          <div class="bild">
            <img src={api.thumbnailUrl(video.id)} alt="" loading="lazy" />
            {#if video.duration}<span class="dauer zahl">{formatDuration(video.duration)}</span>{/if}
          </div>
          <div class="text">
            <div class="titel">{video.title || video.id}</div>
            <div class="angaben">
              <span>{video.channel_name || 'Unbekannt'}</span>
              <span>{lastSeen(video)}</span>
              {#if video.is_archived}<span>Archiv</span>{/if}
              {#if view === 'shorts' && !video.type_verified}<span class="unsicher" title="Von der Quelle noch nicht bestätigt">ungeprüft</span>{/if}
            </div>
            {#if view === 'shorts'}
              <div class="tun">
                <button class="tv-knopf ohne klein" onclick={(e) => { e.stopPropagation(); notAShort(video); }}
                        title="Ist kein Short: als normales Video führen und aus dieser Liste nehmen">
                  <i class="fa-solid fa-rotate-left"></i> Kein Short</button>
                <button class="tv-knopf ohne klein" onclick={(e) => { e.stopPropagation(); protectChannel(video); }}
                        title="Alle Videos dieses Kanals dauerhaft nie als Short führen">
                  <i class="fa-solid fa-shield-halved"></i> Kanal schützen</button>
              </div>
            {/if}
          </div>
          <span class="groesse zahl">{formatSize(video.file_size || 0)}</span>
          <button class="tv-knopf ohne symbol klein" title="In neuem Tab ansehen" aria-label="In neuem Tab ansehen" onclick={(e) => openVideo(video, e)}>
            <i class="fa-solid fa-up-right-from-square"></i></button>
        </div>
      {/each}
    </div>
    <div use:infiniteScroll={{ onLoadMore: list.loadMore, canLoad: list.canLoad }}></div>
    {#if list.loadingMore}<div class="tv-leer klein"><i class="fa-solid fa-spinner fa-spin"></i></div>{/if}
  {/if}
 </div>
</div>

<ConfirmDialog bind:this={confirmRef} />

<style>
  .kopfzeile { display: flex; align-items: baseline; gap: var(--tv-a4); flex-wrap: wrap; margin-bottom: var(--tv-a4); }
  .kopfzeile h1 { margin: 0; font-size: var(--tv-gr-seite); }
  .reiter { margin-bottom: var(--tv-a2); }
  .hinweis { margin: 0 0 var(--tv-a3); max-width: 900px; font-size: var(--tv-gr-klein); color: var(--tv-text-3); }
  .geschuetzt { display: flex; flex-wrap: wrap; align-items: center; gap: var(--tv-a2); margin-bottom: var(--tv-a3); font-size: var(--tv-gr-klein); }
  .weg { border: 0; background: none; color: inherit; cursor: pointer; padding: 0 2px; }
  .kanalwahl { margin-bottom: var(--tv-a3); }
  .kanalwahl .gewaehlt { display: block; margin-bottom: var(--tv-a2); font-weight: 600; }
  .kanalwahl .tv-eingabe { width: min(420px, 100%); }
  .kanaele { display: flex; flex-wrap: wrap; gap: var(--tv-a2); margin-top: var(--tv-a2); }
  .auswahl { display: flex; align-items: center; gap: var(--tv-a3); flex-wrap: wrap; padding: var(--tv-a2) var(--tv-a2) var(--tv-a2) var(--tv-a4);
             border-radius: var(--tv-ecke); background: var(--tv-flaeche); font-size: var(--tv-gr-klein); color: var(--tv-text-2); }
  .auswahl.aktiv { background: rgba(var(--tv-akzent-rgb), 0.08); color: var(--tv-text); }
  .auswahl.aktiv > i { color: var(--tv-akzent); }
  .auswahl .rechts { margin-left: auto; display: flex; flex-wrap: wrap; gap: var(--tv-a2); }
  .zeilen { display: flex; flex-direction: column; gap: 2px; }
  .zeile { display: grid; grid-template-columns: 26px 160px minmax(0, 1fr) auto auto; gap: var(--tv-a4); align-items: center;
           padding: var(--tv-a2); border-radius: var(--tv-ecke); cursor: pointer; user-select: none; outline: 0; }
  .zeile:hover, .zeile:focus-visible { background: var(--tv-flaeche); }
  .zeile.gewaehlt { background: rgba(var(--tv-akzent-rgb), 0.08); }
  .haken { font-size: 19px; color: var(--tv-text-3); }
  .zeile.gewaehlt .haken { color: var(--tv-akzent); }
  .bild { position: relative; aspect-ratio: 16 / 9; border-radius: var(--tv-ecke-klein); overflow: hidden; background: var(--tv-mulde); }
  .bild img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .dauer { position: absolute; right: 5px; bottom: 6px; padding: 1px 6px; border-radius: var(--tv-ecke-klein);
           background: var(--tv-schleier); font-size: var(--tv-gr-marke); }
  .text { min-width: 0; }
  .titel { font-weight: 600; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .angaben { display: flex; flex-wrap: wrap; gap: 2px var(--tv-a3); margin-top: 4px; font-size: var(--tv-gr-klein); color: var(--tv-text-3); }
  .unsicher { color: var(--tv-warnung); font-weight: 600; }
  .tun { display: flex; flex-wrap: wrap; gap: var(--tv-a1); margin-top: var(--tv-a1); }
  .groesse { font-weight: 600; text-align: right; min-width: 90px; }
  .tv-leer.klein { padding: var(--tv-a4); }

  @media (max-width: 700px) {
    .zeile { grid-template-columns: 26px 110px minmax(0, 1fr); }
    .groesse { grid-column: 3; text-align: left; }
  }
</style>

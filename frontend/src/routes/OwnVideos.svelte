<!--
  TubeVault – Eigene Videos (Gestaltung nach mockups/eigene-videos.html und
  mockups/eigene-videos-bestand.html)
  Alte Dateien aus früheren Sammlungen einordnen: einlesen lassen (läuft im
  Hintergrund, Geprüftes erscheint sofort), mit Bibliothek und Feed
  vergleichen, dann löschen, übernehmen oder einem Kanal zuordnen.
  Der Stand bleibt gespeichert; die Seite zeigt ihn beim nächsten Öffnen
  ohne neues Einlesen. Ohne Sammlung (kein externes Laufwerk) bleibt sie leer.
  © HalloWelt42 – Private Nutzung
-->
<script>
  import { untrack } from 'svelte';
  import { get } from 'svelte/store';
  import { api } from '../lib/api/client.js';
  import { toast } from '../lib/stores/notifications.js';
  import { route, updateParams } from '../lib/router/router.js';
  import { formatSize } from '../lib/utils/format.js';
  import { createListLoader } from '../lib/utils/listLoader.svelte.js';
  import { infiniteScroll } from '../lib/utils/infiniteScroll.js';
  import { scrollWithin } from '../lib/utils/scrollRoot.js';
  import ConfirmDialog from '../lib/components/common/ConfirmDialog.svelte';
  import FolderBar from '../lib/components/own/FolderBar.svelte';
  import OwnFileRow from '../lib/components/own/OwnFileRow.svelte';
  import OwnFileDetail from '../lib/components/own/OwnFileDetail.svelte';
  import OwnLibrary from '../lib/components/own/OwnLibrary.svelte';
  import { FINDINGS } from '../lib/components/own/ownStatus.js';

  const PAGE = 50;
  const POLL_MS = 3000;
  const initial = get(route).params || {};

  let confirmRef;
  let tab = $state(initial.tab === 'eingeordnet' ? 'eingeordnet' : 'einordnen');
  let collection = $state(null);
  let folderId = $state(initial.folder ? Number(initial.folder) : null);
  let finding = $state(initial.befund || '');
  let query = $state('');
  let channels = $state([]);
  let selectedId = $state(null);
  let working = $state(false);
  let libraryTotals = $state({ count: 0, bytes: 0 });
  let detailRef = $state(null);
  let listEl = $state(null);
  let detailEl = $state(null);

  let folder = $derived(collection?.folders.find(f => f.id === folderId) || null);
  let openCounts = $derived(folder?.open_by_finding || {});
  let openTotal = $derived(Object.values(openCounts).reduce((a, b) => a + b, 0));
  let busy = $derived(Boolean(folder && ['running', 'queued'].includes(folder.state)) || Boolean(collection?.bulk));

  // ─── Laden ───
  async function loadCollection() {
    try {
      collection = await api.ownCollection();
      if (!collection.folders.some(f => f.id === folderId)) folderId = collection.folders[0]?.id ?? null;
    } catch (e) { toast.error(e.message); }
  }

  const list = createListLoader(async (page) => {
    if (!folderId) return { items: [], total: 0 };
    const r = await api.ownFiles(folderId, { finding, q: query.trim(), offset: (page - 1) * PAGE, limit: PAGE });
    return { items: r.items, total: r.total };
  });

  /** Geladene Zeilen auffrischen, ohne die Liste neu aufzubauen (Einlesen läuft) */
  async function refreshList() {
    if (!folderId || list.loading) return;
    try {
      const r = await api.ownFiles(folderId, { finding, q: query.trim(), offset: 0, limit: Math.min(200, Math.max(PAGE, list.items.length)) });
      list.items = r.items;
      list.total = r.total;
    } catch {}
  }

  const loadLibraryTotals = () =>
    api.ownLibrary(0, 1).then(r => libraryTotals = { count: r.total, bytes: r.total_bytes }).catch(() => {});

  $effect(() => {
    loadCollection();
    api.ownChannels().then(c => channels = c).catch(() => {});
    loadLibraryTotals();
  });

  // Filter und Ordner bestimmen die Liste
  // (die Suche lädt verzögert selbst, sie soll hier nicht mitzählen)
  $effect(() => { folderId; finding; untrack(() => list.load(true)); });

  // Während eingelesen oder sammelweise eingeordnet wird: Stand nachziehen
  $effect(() => {
    if (!busy) return;
    const timer = setInterval(async () => { await loadCollection(); await refreshList(); }, POLL_MS);
    return () => clearInterval(timer);
  });

  let searchTimer;
  function onSearch() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => list.load(true), 300);
  }

  // ─── Auswahl ───
  let selected = $derived(list.items.find(f => f.id === selectedId) || null);
  $effect(() => {
    if (tab === 'einordnen' && !selected && list.items.length) selectedId = list.items[0].id;
  });

  // Andere Datei: Detail von oben zeigen
  $effect(() => { selectedId; detailEl?.scrollTo({ top: 0 }); });

  function move(step) {
    const i = list.items.findIndex(f => f.id === selectedId);
    const next = list.items[Math.max(0, Math.min(list.items.length - 1, i + step))];
    if (!next) return;
    selectedId = next.id;
    const row = listEl?.querySelector(`[data-datei="${next.id}"]`);
    if (row) scrollWithin(listEl, row, 'nearest');
  }

  function onKey(e) {
    if (tab !== 'einordnen' || !selected) return;
    if (e.target.closest?.('input, textarea, select, [contenteditable]')) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); move(e.key === 'ArrowDown' ? 1 : -1); }
    else if (['1', '2', '3', '4'].includes(e.key)) { e.preventDefault(); detailRef?.press(e.key); }
  }

  // ─── Einlesen ───
  function chooseFolder(id) {
    folderId = id;
    selectedId = null;
    updateParams({ folder: id });
  }

  async function addFolder(path) {
    try {
      const { id } = await api.ownAddFolder(path);
      await loadCollection();
      chooseFolder(id);
      toast.success('Wird eingelesen - Geprüftes erscheint sofort');
    } catch (e) { toast.error(e.message); }
  }

  /** Nach dem Anstoßen von Hintergrundarbeit: Kleines ist fertig, bevor der
      nächste Abruf kommt - dann einmal selbst nachladen */
  function followUp() {
    setTimeout(async () => { await loadCollection(); list.load(true); loadLibraryTotals(); }, 800);
  }

  async function scan(id) {
    try { await api.ownScanFolder(id); followUp(); } catch (e) { toast.error(e.message); }
  }

  async function pause(id) {
    try { await api.ownPauseFolder(id); await loadCollection(); } catch (e) { toast.error(e.message); }
  }

  function chooseFinding(id) {
    finding = finding === id ? '' : id;
    selectedId = null;
    updateParams({ befund: finding });
  }

  function chooseTab(next) {
    tab = next;
    updateParams({ tab: next === 'einordnen' ? null : next });
  }

  // ─── Einordnen ───
  /** Aktion für die gewählte Datei; danach weiter zur nächsten */
  async function act(work, message) {
    const file = selected;
    if (!file || working) return;
    working = true;
    try {
      await work(file);
      toast.success(message);
      const i = list.items.findIndex(f => f.id === file.id);
      list.items = list.items.filter(f => f.id !== file.id);
      list.total = Math.max(0, list.total - 1);
      selectedId = list.items[Math.min(i, list.items.length - 1)]?.id ?? null;
      loadCollection();
      loadLibraryTotals();
    } catch (e) { toast.error(e.message); }
    working = false;
  }

  async function remove() {
    const file = selected;
    // Sicher Doppeltes geht ohne Rückfrage, alles andere wird bestätigt
    if (!(file.finding === 'duplicate' && file.match?.in_library)) {
      const ok = await confirmRef.ask('Alte Datei löschen?', `${file.name} wird samt Begleitdateien endgültig gelöscht.`,
        { confirmLabel: 'Löschen' });
      if (!ok) return;
    }
    act((f) => api.ownDelete(f.id), 'Alte Datei gelöscht');
  }

  const adopt = (videoId) => act((f) => api.ownAdopt(f.id, videoId), 'In die Bibliothek übernommen');
  const assign = (name, id, title) => act((f) => api.ownAssign(f.id, name, id, title), `Dem Kanal ${name} zugeordnet`)
    .then(() => api.ownChannels().then(c => channels = c).catch(() => {}));
  async function replace() {
    const ok = await confirmRef.ask('Datei in der Bibliothek ersetzen?',
      'Die alte Datei kommt in die Bibliothek, die bisherige Datei des Videos wird gelöscht.', { confirmLabel: 'Ersetzen' });
    if (ok) act((f) => api.ownReplace(f.id), 'Datei ersetzt');
  }
  const skip = () => act((f) => api.ownSkip(f.id), 'Übersprungen');
  const reopen = () => act((f) => api.ownReopen(f.id), 'Wieder offen');

  async function bulk(action) {
    const n = action === 'delete_duplicates' ? openCounts.duplicate : openCounts.certain;
    const ok = action === 'delete_duplicates'
      ? await confirmRef.ask(`${n} doppelte Dateien löschen?`,
          'Gelöscht werden nur alte Dateien, deren Video schon in der Bibliothek liegt - samt Begleitdateien, endgültig.',
          { confirmLabel: 'Alle löschen' })
      : await confirmRef.ask(`${n} sicher erkannte Videos übernehmen?`,
          'Die Dateien werden in die Bibliothek verschoben. Das läuft im Hintergrund und kann dauern.',
          { confirmLabel: 'Alle übernehmen' });
    if (!ok) return;
    try { await api.ownBulk(folderId, action); followUp(); } catch (e) { toast.error(e.message); }
  }

  let wasBusy = false;
  $effect(() => {
    // Ende des Einlesens oder einer Sammelaktion: Liste einmal ganz neu
    if (wasBusy && !busy) list.load(true);
    wasBusy = busy;
  });
</script>

<svelte:window onkeydown={onKey} />

<div class="tv-seite">
  <div class="tv-seitenkopf">
    <div class="kopfzeile">
      <h1>Eigene Videos</h1>
      <span class="tv-schwach zahl">
        {#if tab === 'eingeordnet'}{libraryTotals.count.toLocaleString('de-DE')} Videos{' · '}{formatSize(libraryTotals.bytes)}
        {:else}alte Dateien einordnen{/if}
      </span>
    </div>
    <div class="tv-reiter">
      <button class:aktiv={tab === 'einordnen'} onclick={() => chooseTab('einordnen')}>
        <i class="fa-solid fa-wand-magic-sparkles"></i> Einordnen{#if openTotal}<span class="tv-zaehler">{openTotal.toLocaleString('de-DE')}</span>{/if}
      </button>
      <button class:aktiv={tab === 'eingeordnet'} onclick={() => chooseTab('eingeordnet')}>
        <i class="fa-solid fa-folder-tree"></i> Eingeordnet{#if libraryTotals.count}<span class="tv-zaehler">{libraryTotals.count.toLocaleString('de-DE')}</span>{/if}
      </button>
    </div>

    {#if tab === 'einordnen' && collection?.folders.length}
      <FolderBar folders={collection.folders} candidates={collection.candidates} selectedId={folderId}
                 onSelect={chooseFolder} onAdd={addFolder} onScan={scan} onPause={pause} />
      <div class="befunde">
        {#each FINDINGS as f (f.id)}
          {#if openCounts[f.id] || finding === f.id}
            <button class="tv-chip" class:aktiv={finding === f.id} onclick={() => chooseFinding(f.id)}>
              <span class="farbe" style:background={f.farbe}></span> {f.label}
              <span class="tv-zaehler">{(openCounts[f.id] || 0).toLocaleString('de-DE')}</span>
            </button>
          {/if}
        {/each}
        <button class="tv-chip" class:aktiv={finding === 'done'} onclick={() => chooseFinding('done')}>
          <i class="fa-solid fa-check"></i> Erledigt</button>
        <input class="tv-eingabe suche" bind:value={query} oninput={onSearch} placeholder="Datei suchen" />
        <div class="aktionen">
          {#if collection.bulk}
            <span class="tv-zustand laeuft"><i class="fa-solid fa-spinner fa-spin"></i>
              {collection.bulk.done + collection.bulk.failed} von {collection.bulk.total}
              {collection.bulk.action === 'delete_duplicates' ? 'gelöscht' : 'übernommen'}</span>
          {:else}
            {#if openCounts.duplicate}
              <button class="tv-knopf gefahr" onclick={() => bulk('delete_duplicates')} disabled={busy}>
                <i class="fa-solid fa-trash-can"></i> {openCounts.duplicate.toLocaleString('de-DE')} Doppelte löschen</button>
            {/if}
            {#if openCounts.certain}
              <button class="tv-knopf" onclick={() => bulk('adopt_certain')} disabled={busy}>
                <i class="fa-solid fa-check-double"></i> {openCounts.certain.toLocaleString('de-DE')} sichere übernehmen</button>
            {/if}
          {/if}
        </div>
      </div>
    {/if}
  </div>

  {#if tab === 'eingeordnet'}
    <OwnLibrary onTotals={(count, bytes) => libraryTotals = { count, bytes }} />
  {:else if !collection}
    <div class="tv-rollfeld"><div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt ...</div></div>
  {:else if !collection.folders.length}
    <div class="tv-rollfeld">
      <div class="start tv-karte">
        {#if !collection.available || !collection.candidates.length}
          <h3><i class="fa-solid fa-box-open"></i> Keine Sammlung eingebunden</h3>
          <p class="tv-leise">Hier lassen sich alte Videodateien aus früheren Sammlungen einordnen: Doppeltes löschen,
            Bekanntes in die Bibliothek übernehmen, Eigenes einem Kanal zuordnen.</p>
          <p class="tv-leise">Dafür gehören die Dateien in den Sammlungsordner des Servers
            (<span class="zahl">data/scan</span>, mit Unterordnern je Kanal). Ein anderes Laufwerk lässt sich in der
            Datei <span class="zahl">.env</span> über <span class="zahl">TUBEVAULT_SCAN_SOURCE</span> einbinden.</p>
        {:else}
          <h3><i class="fa-solid fa-folder-open"></i> Ordner einlesen</h3>
          <p class="tv-leise">Das Einlesen läuft im Hintergrund; was geprüft ist, erscheint sofort. Der Stand bleibt gespeichert.</p>
          <div class="ordner">
            {#each collection.candidates as c}
              <button class="tv-chip" onclick={() => addFolder(c)}><i class="fa-solid fa-folder"></i> {c}</button>
            {/each}
          </div>
          <button class="tv-knopf haupt" onclick={() => addFolder('')}><i class="fa-solid fa-layer-group"></i> Ganze Sammlung einlesen</button>
        {/if}
      </div>
    </div>
  {:else}
    <div class="tv-spalten">
      <div class="tv-rollfeld" data-scroll-root bind:this={listEl}>
        {#if list.loading}
          <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt ...</div>
        {:else if !list.items.length}
          <div class="tv-leer">
            {#if busy}<i class="fa-solid fa-magnifying-glass"></i> Dateien werden gesucht ...
            {:else if finding === 'done'}<i class="fa-solid fa-inbox"></i> Noch nichts erledigt.
            {:else}<i class="fa-solid fa-circle-check"></i> Hier ist alles eingeordnet.{/if}
          </div>
        {:else}
          {#each list.items as file (file.id)}
            <div data-datei={file.id}>
              <OwnFileRow {file} selected={file.id === selectedId} onSelect={() => selectedId = file.id} />
            </div>
          {/each}
          <div use:infiniteScroll={{ onLoadMore: list.loadMore, canLoad: list.canLoad }}></div>
          <div class="tastatur tv-klein">
            <span><kbd>1</kbd> löschen</span><span><kbd>2</kbd> zuordnen</span>
            <span><kbd>3</kbd> eigenem Kanal</span><span><kbd>4</kbd> überspringen</span>
            <span><kbd>↑</kbd><kbd>↓</kbd> nächste Datei</span>
          </div>
        {/if}
      </div>
      <div class="tv-rollfeld" bind:this={detailEl}>
        {#if selected}
          <OwnFileDetail bind:this={detailRef} file={selected} {channels} {working}
                         onDelete={remove} onAdopt={adopt} onAssign={assign} onReplace={replace}
                         onSkip={skip} onReopen={reopen} />
        {:else}
          <div class="tv-leer tv-klein">Datei links wählen.</div>
        {/if}
      </div>
    </div>
  {/if}
</div>

<ConfirmDialog bind:this={confirmRef} />

<style>
  .kopfzeile { display: flex; align-items: baseline; gap: var(--tv-a4); margin-bottom: var(--tv-a4); }
  .kopfzeile h1 { margin: 0; font-size: var(--tv-gr-seite); }
  .befunde { display: flex; gap: var(--tv-a2); flex-wrap: wrap; align-items: center; margin-top: var(--tv-a3); }
  .befunde .farbe { width: 10px; height: 10px; border-radius: 2px; }
  .suche { width: 220px; height: 34px; }
  .befunde .aktionen { margin-left: auto; display: flex; gap: var(--tv-a2); align-items: center; }
  .start { max-width: 760px; }
  .start p { margin: 0 0 var(--tv-a3); }
  .ordner { display: flex; gap: var(--tv-a2); flex-wrap: wrap; margin-bottom: var(--tv-a4); }
  .tastatur { display: flex; gap: var(--tv-a3); flex-wrap: wrap; color: var(--tv-text-3); padding: var(--tv-a3) var(--tv-a3) 0; }
  kbd { font-family: var(--tv-schrift-zahl); font-size: 13px; background: var(--tv-karte-2); border-radius: var(--tv-ecke-klein);
        padding: 1px 6px; color: var(--tv-text); }
</style>

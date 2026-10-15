<!--
  Kategorien (Entwurf mockups/kategorien.html)
  Übersicht: Kopf mit Kennzahlen, Themen erkennen und Neue Kategorie, Suche
  und Sortierung (Größe, Name, Zuletzt gefüllt); Kasten "Videos ohne
  Kategorie" (je Kanal eine Kategorie wählen = Regel "Kanal ist"); Kacheln
  mit Bildcollage, Farbe, Zahlen und Regeln.
  Themen erkennen: Vorschläge der lokalen KI mit Übernehmen, Ansehen, Verwerfen.
  Kategorie (?open=<id>): Regeln als Chips, Stand, Sortierung, Videos mit
  Grund je Video, Umordnen per Ziehen, Auswahl, von Hand hinzufügen und
  herausnehmen, Abspielen; Seitenblatt "Regeln" mit Vorschau und Farbe.
-->
<script>
  import { onMount, untrack } from 'svelte';
  import { api } from '../lib/api/client.js';
  import { navigate, route, updateParams } from '../lib/router/router.js';
  import { toast } from '../lib/stores/notifications.js';
  import { playlistQueue } from '../lib/stores/playlistQueue.js';
  import { musicPlayer } from '../lib/stores/musicPlayer.svelte.js';
  import { formatDuration } from '../lib/utils/format.js';
  import { infiniteScroll } from '../lib/utils/infiniteScroll.js';
  import { onVideoMutation } from '../lib/utils/videoMutations.js';
  import { stateChips, filterItems, sortItems, moveItem, totalTime } from '../lib/utils/collection.js';
  import { playCollection, continueCollection, listenCollection, playAfterCurrent } from '../lib/utils/collectionPlay.js';
  import { OVERVIEW_SORTS, REASON_LABELS, arrangeCategories, freeColors, overviewInfo } from '../lib/utils/categoryRules.js';
  import PageHeader from '../lib/components/common/PageHeader.svelte';
  import BatchToolbar from '../lib/components/common/BatchToolbar.svelte';
  import ActionMenu from '../lib/components/common/ActionMenu.svelte';
  import ConfirmDialog from '../lib/components/common/ConfirmDialog.svelte';
  import CollectionBar from '../lib/components/collection/CollectionBar.svelte';
  import VideoRow from '../lib/components/collection/VideoRow.svelte';
  import VideoCard from '../lib/components/video/VideoCard.svelte';
  import CategoryCard from '../lib/components/categories/CategoryCard.svelte';
  import RuleChips from '../lib/components/categories/RuleChips.svelte';
  import RulesSheet from '../lib/components/categories/RulesSheet.svelte';
  import TopicSuggestions from '../lib/components/categories/TopicSuggestions.svelte';
  import UnsortedChannels from '../lib/components/categories/UnsortedChannels.svelte';

  const DETAIL_SORTS = [
    { key: 'eigene', label: 'Eigene Reihenfolge', title: 'Neues kommt oben dazu - per Ziehen änderbar' },
    { key: 'neueste', label: 'Neueste', title: 'Nach Erscheinen, neueste zuerst' },
    { key: 'titel', label: 'Titel' }, { key: 'dauer', label: 'Dauer' },
  ];
  const STEP = 150;          // so viele Videos zeigt die Liste je Nachladen mehr

  // ── Übersicht ──
  let data = $state(null);
  let loading = $state(true);
  let search = $state('');
  let sort = $state('groesse');
  let creating = $state(null);         // { name, description, color, rules }
  let showTopics = $state(false);
  let topics = $state(null);
  let topicsTimer = null;

  // ── Eine Kategorie ──
  let openId = $state(null);
  let detail = $state(null);           // Sammlung category:<id>
  let itemSearch = $state('');
  let stateFilter = $state('');
  let itemSort = $state('eigene');
  let view = $state('liste');
  let limit = $state(STEP);
  let selecting = $state(false);
  let selected = $state(new Set());
  let editing = $state(null);          // { name, description }
  let adding = $state(false);
  let addQuery = $state('');
  let addResults = $state([]);
  let addTimer = null;
  let dragFrom = $state(null);
  let dropAt = $state(null);
  let sheet = $state(null);            // { categoryId | null, title, rules, color, name?, suggestion? }
  let menu;
  let confirmRef;

  let cards = $derived(data ? arrangeCategories(data.categories, { search, sort }) : []);
  let meta = $derived(data?.categories.find((c) => c.id === openId) || null);
  let source = $derived(openId ? `category:${openId}` : null);
  let items = $derived(detail?.items || []);
  let shown = $derived(sortItems(filterItems(items, { search: itemSearch, state: stateFilter }), itemSort));
  let visible = $derived(shown.slice(0, limit));
  let canOrder = $derived(itemSort === 'eigene' && !itemSearch && !stateFilter && !selecting);
  let selectedIds = $derived(shown.filter((i) => selected.has(i.id)).map((i) => i.id));
  let queueActive = $derived($playlistQueue.active);
  let detailInfo = $derived(detail ? [
    `${items.length.toLocaleString('de-DE')} ${items.length === 1 ? 'Video' : 'Videos'}`,
    detail.duration ? totalTime(detail.duration) : null,
    detail.counts.finished ? `${detail.counts.finished.toLocaleString('de-DE')} gesehen` : null,
  ].filter(Boolean).join(' · ') : null);

  // ── Laden ──
  async function loadOverview() {
    try { data = await api.getCategoryOverview(); } catch (e) { toast.error(e.message); }
    loading = false;
  }

  async function loadDetail() {
    const id = openId;
    if (!id) return;
    try {
      const collection = await api.getCollection(`category:${id}`);
      if (id === openId) detail = collection;
    } catch (e) { toast.error(e.message); close(); }
  }

  const refresh = () => Promise.all([loadOverview(), loadDetail()]);

  function open(card) { updateParams({ open: card.id }); }
  function close() { updateParams({ open: null }); }

  function openCategory(id) {
    if (openId !== id) {
      openId = id;
      detail = null;
      itemSearch = ''; stateFilter = ''; itemSort = 'eigene'; limit = STEP;
      selecting = false; selected = new Set(); adding = false; editing = null;
      if (sheet && sheet.categoryId !== id) sheet = null;
    }
    loadDetail();
  }

  // ── Abspielen ──
  const titleOf = () => detail?.title || meta?.name || 'Kategorie';
  const playAt = (item) => playCollection(source, titleOf(), shown, shown.indexOf(item), { resume: item.state === 'started' });
  const playAll = () => playCollection(source, titleOf(), shown);
  const playShuffled = () => playCollection(source, titleOf(), shown, 0, { shuffle: true });

  async function quickPlay(card, how) {
    const collection = await api.getCollection(`category:${card.id}`).catch((e) => { toast.error(e.message); return null; });
    if (!collection?.items.length) { if (collection) toast.info('Die Kategorie ist leer'); return; }
    const src = `category:${card.id}`;
    if (how === 'zufall') playCollection(src, collection.title, collection.items, 0, { shuffle: true });
    else if (how === 'weiter') continueCollection(src, collection.title, collection.items);
    else playCollection(src, collection.title, collection.items);
  }

  // ── Anlegen, Ändern, Löschen ──
  function startCreate(channel = null) {
    const used = (data?.categories || []).map((c) => c.color);
    creating = {
      name: channel?.name || '', description: '', color: freeColors(data?.colors || [], used, 1)[0],
      rules: channel ? [{ kind: 'channel', value: channel.channel_id, label: channel.name }] : [],
    };
    showTopics = false;
  }

  async function create() {
    const draft = creating;
    if (!draft?.name.trim()) return;
    try {
      const { id } = await api.createCategory({ name: draft.name.trim(), description: draft.description.trim() || null, color: draft.color });
      creating = null;
      await loadOverview();
      open({ id });
      openRules({ id, name: draft.name.trim(), color: draft.color, rules: draft.rules });
    } catch (e) { toast.error(e.message); }
  }

  async function saveEdit() {
    if (!editing?.name.trim()) return;
    try {
      await api.updateCategory(openId, { name: editing.name.trim(), description: editing.description.trim() || null });
      editing = null;
      await refresh();
    } catch (e) { toast.error(e.message); }
  }

  async function deleteCategory(card) {
    const ok = await confirmRef.ask(`"${card.name}" löschen?`,
      'Die Kategorie und ihre Regeln verschwinden. Die Videos bleiben in der Bibliothek.', { confirmLabel: 'Löschen' });
    if (!ok) return;
    try {
      await api.deleteCategory(card.id);
      if (openId === card.id) close();
      sheet = null;
      toast.info(`"${card.name}" gelöscht`);
      await loadOverview();
    } catch (e) { toast.error(e.message); }
  }

  // ── Regeln ──
  function openRules(card) {
    sheet = { categoryId: card.id, title: `Regeln: ${card.name}`, rules: card.rules || [], color: card.color };
  }

  async function saveRules({ rules, color }) {
    const id = sheet.categoryId;
    const card = data?.categories.find((c) => c.id === id);
    if (color && color !== card?.color) await api.updateCategory(id, { color });
    const result = await api.saveCategoryRules(id, rules);
    sheet = null;
    const changes = [result.added ? `${result.added.toLocaleString('de-DE')} eingeordnet` : null,
                     result.removed ? `${result.removed.toLocaleString('de-DE')} herausgenommen` : null].filter(Boolean);
    toast.success(changes.length ? `Regeln gespeichert: ${changes.join(', ')}` : 'Regeln gespeichert');
    await refresh();
  }

  // Kasten "Videos ohne Kategorie": Kanal einer Kategorie zuordnen (Regel "Kanal ist")
  function channelMenu(event, channel) {
    const list = [...(data?.categories || [])].sort((a, b) => a.name.localeCompare(b.name, 'de'));
    menu.open(event, channel.name, [
      ...list.map((card) => ({ icon: 'fa-folder', label: card.name, hint: card.video_count.toLocaleString('de-DE'),
                                run: () => addChannelRule(card, channel) })),
      ...(list.length ? [{ trenner: true }] : []),
      { icon: 'fa-plus', label: 'Neue Kategorie ...', run: () => startCreate(channel) },
    ]);
  }

  async function addChannelRule(card, channel) {
    const before = card.rules.map(({ kind, value, precision }) => ({ kind, value, precision }));
    const result = await api.saveCategoryRules(card.id, [...before, { kind: 'channel', value: channel.channel_id }]);
    await loadOverview();
    toast.undo(`${result.added.toLocaleString('de-DE')} Videos von "${channel.name}" in "${card.name}"`, async () => {
      await api.saveCategoryRules(card.id, before);
      await refresh();
    });
  }

  // ── Themen erkennen ──
  async function loadTopics() {
    clearTimeout(topicsTimer);
    try { topics = await api.getCategoryTopics(); } catch (e) { toast.error(e.message); return; }
    if (topics.running) topicsTimer = setTimeout(loadTopics, 2000);
  }

  async function startTopics() {
    try { topics = await api.startCategoryTopics(); } catch (e) { toast.error(e.message); return; }
    loadTopics();
  }

  async function toggleTopics() {
    showTopics = !showTopics;
    creating = null;
    if (!showTopics) return;
    await loadTopics();
    if (topics && !topics.running && !topics.suggestions.length && !topics.finished_at) startTopics();
  }

  async function acceptTopic(suggestion, changes = {}) {
    const { id } = await api.acceptCategoryTopic(suggestion.id, changes);
    toast.success(`"${changes.name || suggestion.name}" angelegt`);
    await Promise.all([loadOverview(), loadTopics()]);
    return id;
  }

  async function acceptQuick(suggestion) {
    try { await acceptTopic(suggestion); } catch (e) { toast.error(e.message); }
  }

  function viewTopic(suggestion) {
    sheet = {
      categoryId: null, suggestion, title: `Vorschlag: ${suggestion.name}`, name: suggestion.name,
      rules: [{ kind: 'semantic', value: suggestion.query, precision: suggestion.precision }],
      color: freeColors(data?.colors || [], (data?.categories || []).map((c) => c.color), 1)[0],
    };
  }

  async function saveTopic({ rules, color, name }) {
    await acceptTopic(sheet.suggestion, { name, color, rules });
    sheet = null;
  }

  async function dismissTopic(suggestion) {
    try {
      await api.dismissCategoryTopic(suggestion.id);
      topics = { ...topics, suggestions: topics.suggestions.filter((s) => s.id !== suggestion.id) };
    } catch (e) { toast.error(e.message); }
  }

  // ── Videos der Kategorie ──
  async function saveOrder(ids) {
    detail = { ...detail, items: ids.map((id) => items.find((i) => i.id === id)) };
    try { await api.reorderCategory(openId, ids); } catch { toast.error('Reihenfolge speichern fehlgeschlagen'); loadDetail(); }
  }

  async function removeItems(ids) {
    const id = openId;
    let entries = [];
    try { entries = await api.removeFromCategory(id, ids); } catch (e) { toast.error(e.message); return; }
    selected = new Set();
    await refresh();
    toast.undo(ids.length === 1 ? 'Aus der Kategorie genommen' : `${ids.length} Videos aus der Kategorie genommen`, async () => {
      await api.restoreToCategory(id, entries);
      await refresh();
    });
  }

  async function setWatched(ids, watched) {
    try { await api.setWatched(ids, watched); } catch (e) { toast.error(e.message); }
    selected = new Set();
    await refresh();
  }

  function onAddInput() {
    clearTimeout(addTimer);
    if (!addQuery.trim()) { addResults = []; return; }
    addTimer = setTimeout(async () => {
      try {
        const res = await api.searchLocal(addQuery, { per_page: 30 });
        const present = new Set(items.map((i) => i.id));
        addResults = (res.videos || []).filter((v) => !present.has(v.id));
      } catch { addResults = []; }
    }, 300);
  }

  async function addVideo(video) {
    try {
      await api.addToCategory(openId, [video.id]);
      addResults = addResults.filter((v) => v.id !== video.id);
      await refresh();
    } catch (e) { toast.error(e.message); }
  }

  // ── Menüs ──
  function cardMenu(event, card) {
    menu.open(event, card.name, [
      { icon: 'fa-folder-open', label: 'Öffnen', run: () => open(card) },
      { icon: 'fa-sliders', label: 'Regeln', run: () => openRules(card) },
      ...(card.video_count ? [
        { icon: 'fa-rotate-left', label: 'Weiterschauen', run: () => quickPlay(card, 'weiter') },
        { icon: 'fa-headphones', label: 'Als Ton hören', run: () => listenCollection(`category:${card.id}`) },
      ] : []),
      { trenner: true },
      { icon: 'fa-trash-can', label: 'Kategorie löschen', danger: true, run: () => deleteCategory(card) },
    ]);
  }

  function detailMenu(event) {
    const card = meta || { id: openId, name: titleOf(), rules: [] };
    menu.open(event, titleOf(), [
      { icon: 'fa-pen', label: 'Umbenennen und beschreiben', run: () => { editing = { name: card.name, description: card.description || '' }; } },
      ...(items.length ? [
        { icon: 'fa-rotate-left', label: 'Weiterschauen', run: () => continueCollection(source, titleOf(), items) },
        { icon: 'fa-headphones', label: 'Als Ton hören', run: () => listenCollection(source) },
        { trenner: true },
        { icon: 'fa-eye-slash', label: 'Alles als ungesehen', run: () => setWatched(items.map((i) => i.id), false) },
      ] : []),
      { icon: 'fa-trash-can', label: 'Kategorie löschen', danger: true, run: () => deleteCategory(card) },
    ]);
  }

  function itemMenu(event, item) {
    const ids = [item.id];
    const index = items.indexOf(item);
    menu.open(event, item.title, [
      { icon: item.state === 'started' ? 'fa-rotate-left' : 'fa-play', label: item.state === 'started' ? 'Weiterschauen' : 'Abspielen', run: () => playAt(item) },
      ...(queueActive ? [{ icon: 'fa-forward', label: 'Als Nächstes', run: () => playAfterCurrent(item) }] : []),
      { icon: 'fa-headphones', label: 'Ab hier als Ton hören', run: () => musicPlayer.playSource(`sammlung:${source}`, { start: item.id }) },
      { trenner: true },
      ...(canOrder && index > 0 ? [{ icon: 'fa-arrow-up', label: 'Ganz nach oben', run: () => saveOrder(moveItem(items.map((i) => i.id), index, 0)) }] : []),
      ...(canOrder && index < items.length - 1 ? [{ icon: 'fa-arrow-down', label: 'Ganz nach unten', run: () => saveOrder(moveItem(items.map((i) => i.id), index, items.length)) }] : []),
      item.state === 'finished'
        ? { icon: 'fa-eye-slash', label: 'Als neu markieren', run: () => setWatched(ids, false) }
        : { icon: 'fa-check', label: 'Als gesehen markieren', run: () => setWatched(ids, true) },
      { trenner: true },
      { icon: 'fa-xmark', label: 'Aus der Kategorie nehmen', hint: 'bleibt draußen', danger: true, run: () => removeItems(ids) },
    ]);
  }

  function toggle(item) {
    const next = new Set(selected);
    next.has(item.id) ? next.delete(item.id) : next.add(item.id);
    selected = next;
  }

  function onDrop(index) {
    if (dragFrom !== null && dragFrom !== index) saveOrder(moveItem(items.map((i) => i.id), dragFrom, index));
    dragFrom = null; dropAt = null;
  }

  // Geöffnete Kategorie folgt der Adresse (?open=<id>)
  $effect(() => {
    const id = $route.params.open;
    untrack(() => {
      if (id) openCategory(Number(id));
      else { openId = null; detail = null; if (sheet?.categoryId) sheet = null; }
    });
  });

  // Laden nur beim Öffnen und nach Änderungen an Videos - ein $effect würde
  // sich über die gelesenen Daten selbst neu auslösen
  onMount(() => {
    if ($route.page === 'category' && $route.id) navigate('/categories', { open: $route.id }, true);
    loadOverview();
    const stop = onVideoMutation(() => refresh());
    return () => { stop(); clearTimeout(topicsTimer); };
  });
</script>

<div class="tv-seite kategorien">
  {#if openId}
    <!-- ═══ Eine Kategorie ═══ -->
    <div class="tv-seitenkopf">
      <PageHeader title={detail?.title || meta?.name || 'Kategorie'} info={detailInfo} onBack={close}
                  icon={meta ? 'fa-solid fa-square' : null} iconColor={meta?.color}>
        <button class="tv-knopf" class:aktiv={sheet?.categoryId === openId} onclick={() => meta && openRules(meta)}
                title="Welche Videos von selbst hineinkommen: Kanal, Schlagwort, inhaltlich wie">
          <i class="fa-solid fa-sliders"></i> Regeln</button>
        {#if items.length}
          <button class="tv-knopf" onclick={playShuffled}><i class="fa-solid fa-shuffle"></i> Zufällig</button>
          <button class="tv-knopf haupt" onclick={playAll}><i class="fa-solid fa-play"></i> Abspielen</button>
        {/if}
        <button class="tv-knopf symbol" onclick={detailMenu} title="Mehr: Umbenennen, Weiterschauen, Als Ton hören, Löschen">
          <i class="fa-solid fa-ellipsis"></i></button>
      </PageHeader>

      {#if editing}
        <form class="tv-filter bearbeiten" onsubmit={(e) => { e.preventDefault(); saveEdit(); }}>
          <input class="tv-eingabe name" bind:value={editing.name} placeholder="Name" maxlength="80" />
          <input class="tv-eingabe beschreibung" bind:value={editing.description} placeholder="Beschreibung (optional)" maxlength="300" />
          <button class="tv-knopf klein haupt" disabled={!editing.name.trim()}>Speichern</button>
          <button type="button" class="tv-knopf klein ohne" onclick={() => editing = null}>Abbrechen</button>
        </form>
      {:else if meta?.description}
        <p class="beschreibung">{meta.description}</p>
      {/if}

      {#if meta?.rules.length}
        <div class="regeln">
          <RuleChips rules={meta.rules} onOpen={() => openRules(meta)} />
          <span class="tv-leise tv-klein">neue Videos ordnen sich von selbst ein</span>
        </div>
      {/if}

      {#if selecting}
        <BatchToolbar selectedCount={selectedIds.length} totalCount={shown.length}
                      onSelectAll={() => selected = new Set(shown.map((i) => i.id))} onDone={() => { selecting = false; selected = new Set(); }}>
          <button class="tv-knopf klein" onclick={() => playCollection(source, titleOf(), shown.filter((i) => selected.has(i.id)))}>
            <i class="fa-solid fa-play"></i> Abspielen</button>
          <button class="tv-knopf klein" onclick={() => setWatched(selectedIds, true)}><i class="fa-solid fa-check"></i> Als gesehen</button>
          <button class="tv-knopf klein" onclick={() => setWatched(selectedIds, false)}><i class="fa-solid fa-eye-slash"></i> Als neu</button>
          <button class="tv-knopf klein gefahr" onclick={() => removeItems(selectedIds)}
                  title="Herausnehmen; keine Regel bringt sie zurück"><i class="fa-solid fa-xmark"></i> Aus der Kategorie</button>
        </BatchToolbar>
      {:else if detail}
        <CollectionBar bind:search={itemSearch} placeholder="In der Kategorie suchen"
                       states={stateChips(detail.counts, items.length)} bind:state={stateFilter}
                       sorts={DETAIL_SORTS} bind:sort={itemSort} bind:view
                       onSelect={items.length ? () => { selecting = true; adding = false; view = 'liste'; } : null}>
          {#snippet rechts()}
            <button class="tv-knopf klein" class:aktiv={adding} onclick={() => { adding = !adding; addQuery = ''; addResults = []; }}
                    title="Videos aus der Bibliothek von Hand hineinlegen">
              <i class="fa-solid fa-plus"></i> Videos hinzufügen</button>
          {/snippet}
        </CollectionBar>
      {/if}
    </div>

    <div class="inhalt" class:tv-spalten={adding}>
      <div class="tv-rollfeld" data-scroll-root>
        {#if !detail}
          <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt ...</div>
        {:else if !items.length}
          <div class="leer-gross">
            <i class="fa-solid fa-folder-open"></i>
            <h2>Noch keine Videos</h2>
            <p>Mit Regeln füllt sich die Kategorie von selbst; einzelne Videos lassen sich auch von Hand hinzufügen.</p>
            <button class="tv-knopf haupt" onclick={() => meta && openRules(meta)}><i class="fa-solid fa-sliders"></i> Regeln festlegen</button>
          </div>
        {:else if !shown.length}
          <div class="tv-leer">Nichts gefunden.</div>
        {:else if view === 'kacheln'}
          <div class="tv-raster">
            {#each visible as item (item.id)}
              <VideoCard video={{ ...item, last_position: item.position }} showArchiveBtn={false} onPlay={() => playAt(item)} />
            {/each}
          </div>
        {:else}
          <div class="zeilen" role="list">
            {#each visible as item, i (item.id)}
              {#if dropAt === i && dragFrom !== null && dragFrom !== i && dragFrom !== i - 1}<div class="einfuegen"></div>{/if}
              <VideoRow {item} nr={i + 1} note={REASON_LABELS[item.reason] || null}
                        mode={selecting ? 'auswahl' : canOrder ? 'ordnen' : null}
                        selected={selected.has(item.id)} lifted={dragFrom === i}
                        playing={queueActive && $playlistQueue.source === source && $playlistQueue.videos[$playlistQueue.currentIndex]?.id === item.id}
                        onPlay={playAt} onNext={queueActive ? playAfterCurrent : null} onMenu={itemMenu} onToggle={toggle}
                        draggable={canOrder}
                        ondragstart={() => dragFrom = i}
                        ondragover={(e) => { if (dragFrom !== null) { e.preventDefault(); dropAt = i; } }}
                        ondrop={() => onDrop(i)}
                        ondragend={() => { dragFrom = null; dropAt = null; }} />
            {/each}
            {#if canOrder && visible.length === shown.length}
              <div class="ende" role="presentation"
                   ondragover={(e) => { if (dragFrom !== null) { e.preventDefault(); dropAt = shown.length; } }}
                   ondrop={() => onDrop(shown.length)}>
                {#if dropAt === shown.length && dragFrom !== null}<div class="einfuegen"></div>{/if}
              </div>
            {/if}
          </div>
        {/if}
        {#if detail && visible.length < shown.length}
          <div class="nachladen tv-schwach tv-klein" use:infiniteScroll={{ onLoadMore: () => { limit += STEP; }, canLoad: () => visible.length < shown.length }}>
            <span class="zahl">{visible.length.toLocaleString('de-DE')}</span> von <span class="zahl">{shown.length.toLocaleString('de-DE')}</span>
          </div>
        {/if}
      </div>

      {#if adding}
        <div class="tv-rollfeld hinzu" data-scroll-root>
          <div class="tv-etikett">Von Hand hinzufügen</div>
          <!-- svelte-ignore a11y_autofocus -->
          <input class="tv-eingabe" type="search" bind:value={addQuery} oninput={onAddInput} placeholder="Titel oder Kanal suchen" autofocus />
          {#each addResults as video (video.id)}
            <div class="treffer">
              <img src={api.thumbnailUrl(video.id)} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
              <div class="text">
                <div class="t">{video.title}</div>
                <div class="tv-leise tv-klein">{video.channel_name || ''}{#if video.duration} · <span class="zahl">{formatDuration(video.duration)}</span>{/if}</div>
              </div>
              <button class="tv-knopf klein haupt symbol" onclick={() => addVideo(video)} title="In die Kategorie legen (bleibt, auch ohne Regel)"><i class="fa-solid fa-plus"></i></button>
            </div>
          {:else}
            <p class="tv-schwach tv-klein">{addQuery.trim() ? 'Keine weiteren Treffer.' : 'Gefundene Videos lassen sich mit + hineinlegen.'}</p>
          {/each}
        </div>
      {/if}
    </div>

  {:else}
    <!-- ═══ Übersicht ═══ -->
    <div class="tv-seitenkopf">
      <PageHeader title="Kategorien" info={loading ? null : overviewInfo(data)}>
        {#if data?.ai.topics}
          <button class="tv-knopf" class:aktiv={showTopics} onclick={toggleTopics}
                  title="Die lokale KI ordnet die Videos ohne Kategorie nach Themen und schlägt Kategorien vor">
            <i class="fa-solid fa-wand-magic-sparkles"></i> Themen erkennen</button>
        {/if}
        <button class="tv-knopf haupt" onclick={() => creating ? creating = null : startCreate()}>
          <i class="fa-solid fa-plus"></i> Neue Kategorie</button>
      </PageHeader>

      {#if creating}
        <form class="tv-filter neu" onsubmit={(e) => { e.preventDefault(); create(); }}>
          <!-- svelte-ignore a11y_autofocus -->
          <input class="tv-eingabe name" bind:value={creating.name} placeholder="Name der Kategorie" maxlength="80" autofocus />
          <input class="tv-eingabe beschreibung" bind:value={creating.description} placeholder="Beschreibung (optional)" maxlength="300" />
          <div class="farben" role="group" aria-label="Farbe">
            {#each freeColors(data?.colors || [], (data?.categories || []).map((c) => c.color)) as c (c)}
              <button type="button" class="farbe" class:an={creating.color === c} style:background={c}
                      onclick={() => creating.color = c} aria-label="Farbe {c}"></button>
            {/each}
          </div>
          <button class="tv-knopf klein haupt" disabled={!creating.name.trim()}>Anlegen und Regeln festlegen</button>
          <button type="button" class="tv-knopf klein ohne" onclick={() => creating = null}>Abbrechen</button>
        </form>
      {:else if data?.categories.length && !showTopics}
        <CollectionBar bind:search placeholder="Kategorien suchen" sorts={OVERVIEW_SORTS} bind:sort />
      {/if}
    </div>

    <div class="tv-rollfeld" data-scroll-root>
      {#if showTopics}
        <TopicSuggestions state={topics} onAccept={acceptQuick} onView={viewTopic} onDismiss={dismissTopic} onRestart={startTopics} />
      {:else if loading}
        <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt ...</div>
      {:else if data}
        {#if data.unassigned && data.unsorted_channels.length}
          <UnsortedChannels unassigned={data.unassigned} channels={data.unsorted_channels} onPick={channelMenu}
                            onTopics={data.ai.topics ? toggleTopics : null} />
        {/if}
        {#if !data.categories.length}
          <div class="leer-gross">
            <i class="fa-solid fa-folder"></i>
            <h2>Noch keine Kategorien</h2>
            <p>Eine Kategorie sammelt Videos von Hand oder per Regel: nach Kanal, Schlagwort oder Inhalt. Neue Videos ordnen sich dann von selbst ein.</p>
            {#if !creating}<button class="tv-knopf haupt" onclick={() => startCreate()}><i class="fa-solid fa-plus"></i> Neue Kategorie</button>{/if}
          </div>
        {:else if !cards.length}
          <div class="tv-leer">Nichts gefunden.</div>
        {:else}
          <div class="kat-raster">
            {#each cards as card (card.id)}
              <CategoryCard {card} onOpen={() => open(card)} onPlay={() => quickPlay(card, 'vorn')} onShuffle={() => quickPlay(card, 'zufall')}
                            onMenu={(e) => cardMenu(e, card)} onRules={() => openRules(card)} />
            {/each}
          </div>
        {/if}
      {/if}
    </div>
  {/if}

  {#if sheet && data}
    {#key sheet}
      <RulesSheet title={sheet.title} categoryId={sheet.categoryId} rules={sheet.rules} color={sheet.color}
                  colors={data.colors} ai={data.ai} name={sheet.categoryId === null ? sheet.name : null}
                  acceptLabel={sheet.categoryId === null ? 'Übernehmen' : null}
                  onSave={sheet.categoryId === null ? saveTopic : saveRules} onClose={() => sheet = null} />
    {/key}
  {/if}
</div>

<ActionMenu bind:this={menu} />
<ConfirmDialog bind:this={confirmRef} />

<style>
  .kategorien { position: relative; }   /* Bezug für das Seitenblatt */

  .neu, .bearbeiten { margin-bottom: var(--tv-a3); }
  .neu .name, .bearbeiten .name { width: 280px; }
  .neu .beschreibung, .bearbeiten .beschreibung { flex: 1; min-width: 220px; }
  .farben { display: flex; gap: 6px; flex-wrap: wrap; }
  .farbe { width: 28px; height: 28px; padding: 0; border: 2px solid transparent; border-radius: var(--tv-ecke-klein); cursor: pointer; }
  .farbe.an { border-color: var(--tv-text); }
  .beschreibung { margin: calc(-1 * var(--tv-a3)) 0 var(--tv-a3); color: var(--tv-text-2); font-size: var(--tv-gr-klein); max-width: 820px; }

  .regeln { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: calc(-1 * var(--tv-a2)) 0 var(--tv-a3); }
  .regeln .tv-leise { margin-left: 6px; }

  .kat-raster { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: var(--tv-a4); }

  .inhalt { flex: 1; min-height: 0; display: flex; flex-direction: column; }
  .inhalt.tv-spalten { display: grid; }
  .zeilen { display: flex; flex-direction: column; gap: 2px; }
  .einfuegen { height: 3px; margin: 0 0 0 30px; background: var(--tv-akzent); border-radius: 1px; }
  .ende { min-height: 40px; }
  .nachladen { padding: var(--tv-a4); text-align: center; }
  .hinzu { display: flex; flex-direction: column; gap: var(--tv-a2); background: var(--tv-flaeche); border-radius: var(--tv-ecke);
           padding: var(--tv-a3); margin: var(--tv-a2) 0 var(--tv-a4); }
  .hinzu > * { flex-shrink: 0; }
  .treffer { display: grid; grid-template-columns: 112px minmax(0, 1fr) auto; gap: var(--tv-a3); align-items: center; padding: 4px;
             border-radius: var(--tv-ecke); }
  .treffer:hover { background: var(--tv-karte); }
  .treffer img { width: 112px; aspect-ratio: 16 / 9; object-fit: cover; border-radius: var(--tv-ecke-klein); background: var(--tv-mulde); }
  .treffer .t { font-weight: 600; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

  .leer-gross { padding: 72px var(--tv-a5); text-align: center; color: var(--tv-text-2); }
  .leer-gross > i { font-size: 44px; color: var(--tv-text-3); margin-bottom: var(--tv-a4); }
  .leer-gross h2 { margin: 0 0 var(--tv-a2); color: var(--tv-text); }
  .leer-gross p { margin: 0 auto var(--tv-a4); max-width: 560px; }
</style>

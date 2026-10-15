<!--
  Kanäle (Entwurf mockups/kanaele.html): Abos als Kacheln oder dichte Liste
  mit haftendem Tabellenkopf, Prüfstand und Drip-Prognose im festen Kopf,
  Hinzufügen einzeln oder als Liste, Filter, Medaillen, Suche, Sortierung,
  Menü je Kanal, Seitenblatt mit allen Einstellungen, Auswahl mit
  Stapelaktionen, Abo beenden mit der Frage nach den Videos.
  Alle Wege (Kachel, Liste, Menü, Seitenblatt, Stapel) ändern einen Kanal
  über dieselben Einzel-Aktionen dieser Seite.
-->
<script>
  import { onMount } from 'svelte';
  import { api } from '../lib/api/client.js';
  import { toast } from '../lib/stores/notifications.js';
  import { navigate } from '../lib/router/router.js';
  import { getFilter, saveFilters } from '../lib/stores/filterPersist.js';
  import { formatSize } from '../lib/utils/format.js';
  import PageHeader from '../lib/components/common/PageHeader.svelte';
  import BatchToolbar from '../lib/components/common/BatchToolbar.svelte';
  import ActionMenu from '../lib/components/common/ActionMenu.svelte';
  import ConfirmDialog from '../lib/components/common/ConfirmDialog.svelte';
  import CollectionBar from '../lib/components/collection/CollectionBar.svelte';
  import ChannelSettingsSheet from '../lib/components/channel/ChannelSettingsSheet.svelte';
  import { MISSING_BATCH, createChannelActions } from '../lib/components/channel/channelActions.js';
  import LanguageChips from '../lib/components/common/LanguageChips.svelte';
  import LanguageLabel from '../lib/components/common/LanguageLabel.svelte';
  import {
    FILTERS, MEDAL_FILTERS, SORTS, channelBadges, channelName, coveragePercent, coverageShare, coverageTitle,
    dayText, dripCount, filterChannels, filterCounts, medalOf, medalStyle, missingCount, momentText, num,
    qualityItems, qualityShort, sortChannels,
  } from '../lib/components/channel/channelView.js';

  const PAGE = 'subscriptions';                  // Merker für Ansicht und Sortierung
  const REFRESH_AFTER_ADD_MS = 8000;             // Kanalbild und erste Videos kommen nach
  const DISK_LOW_BYTES = 50 * 1024 ** 3;
  const CHANNEL_ID = /UC[0-9A-Za-z_-]{22}/;
  const COLUMNS = [
    { cls: 'sp-kanal', label: 'Kanal', sort: 'name' },
    { cls: 'sp-abdeckung', label: 'Abdeckung', sort: 'abdeckung' },
    { cls: 'sp-neu', label: 'Neu', sort: 'neu' },
    { cls: 'sp-video', label: 'Neuestes Video', sort: 'hochgeladen' },
    { cls: 'sp-geprueft', label: 'Geprüft' },
    { cls: 'sp-merkmale', label: 'Merkmale' },
    { cls: 'sp-mehr', label: '' },
  ];
  const plural = (count, one, many) => (count === 1 ? one : many);
  const onOff = (on) => (on ? 'an' : 'aus');

  // ── Daten ──
  let subs = $state([]);
  let total = $state(0);
  let loaded = $state(false);          // bis zur ersten Antwort "Lädt", nie "Noch keine Kanäle"
  let rssStats = $state(null);
  let scheduler = $state(null);
  let prognosis = $state(null);

  // ── Ansicht ──
  let search = $state('');
  let filter = $state('');
  let languages = $state([]);          // Kanalsprache: Kürzel, "mul" gemischt, "und" unbekannt
  let languageCounts = $state([]);     // Zähler je Kanalsprache (vom Backend)
  let sort = $state(savedChoice('sort', SORTS.map((s) => s.key), 'name'));
  let view = $state(savedChoice('view', ['kacheln', 'liste'], 'kacheln'));
  let selecting = $state(false);
  let selected = $state(new Set());    // Abo-IDs
  let batchBusy = $state(false);
  let sheet = $state(null);            // { id, problems } des offenen Seitenblatts
  let checking = $state({});           // Abo-ID -> Prüfung läuft

  // ── Hinzufügen ──
  let adding = $state(false);
  let listOpen = $state(false);
  let channelInput = $state('');
  let batchInput = $state('');
  let autoDownload = $state(false);
  let newQuality = $state('');         // leer = Qualität aus den Einstellungen
  let subscribing = $state(false);
  let importing = $state(false);

  let menu, confirmRef;

  let counts = $derived(filterCounts(subs));
  let shown = $derived(sortChannels(filterChannels(subs, { filter, search, languages }), sort));
  let visibleFilters = $derived(FILTERS.filter((f) => !f.optional || counts[f.key] > 0 || filter === f.key));
  let selectedSubs = $derived(shown.filter((s) => selected.has(s.id)));
  let batchAll = $derived({
    auto: selectedSubs.length > 0 && selectedSubs.every((s) => s.auto_download),
    drip: selectedSubs.length > 0 && selectedSubs.every((s) => s.drip_enabled),
    music: selectedSubs.length > 0 && selectedSubs.every((s) => s.music_channel),
  });
  let sheetSub = $derived(sheet ? subs.find((s) => s.id === sheet.id) : null);
  let batchLines = $derived(batchInput.split('\n').filter((line) => line.trim()).length);

  let info = $derived.by(() => {
    if (!loaded) return null;
    const count = shown.length === subs.length
      ? `${num(total)} ${total === 1 ? 'Kanal' : 'Kanäle'}`
      : `${num(shown.length)} von ${num(total)} Kanälen`;
    const medals = MEDAL_FILTERS.filter((f) => counts[f.key]).map((f) => `${num(counts[f.key])} ${f.label}`);
    return [count, ...medals].join(' · ');
  });

  /** Stand der automatischen Prüfung: { icon, warn, parts: [{ before, count, after }] } */
  let schedulerState = $derived.by(() => {
    if (!scheduler) return null;
    if (!scheduler.rss_enabled) {
      return { icon: 'fa-circle-pause', parts: [{ before: 'Die automatische Prüfung ist in den Einstellungen abgeschaltet.' }] };
    }
    if (scheduler.disturbance?.active) {
      const minutes = Math.ceil(scheduler.disturbance.pause_seconds_left / 60);
      return { icon: 'fa-triangle-exclamation', warn: true, parts: [
        { before: 'Quelle gestört: die Prüfung pausiert noch', count: minutes, after: `Min. (${scheduler.disturbance.reason})` }] };
    }
    const pending = scheduler.feeds_pending;
    const parts = scheduler.polling ? [{ before: 'Eine Prüfung läuft gerade' }]
      : [{ count: pending, after: plural(pending, 'Kanal ist fällig', 'Kanäle sind fällig') }];
    if (scheduler.last_tick?.status === 'skipped') parts.push({ before: `letzter Anstoß ausgesetzt: ${scheduler.last_tick.message}` });
    if (scheduler.auto_download?.pending > 0) {
      const marked = scheduler.auto_download.pending;
      parts.push({ count: marked, after: `${plural(marked, 'Video', 'Videos')} für Auto-Download vorgemerkt` });
      if (scheduler.auto_download.daily_limit) parts.push({ before: 'Tageslimit', count: scheduler.auto_download.daily_limit });
    }
    if (counts.ungeprueft) {
      parts.push({ count: counts.ungeprueft, after: plural(counts.ungeprueft, 'Kanal wartet auf seine', 'Kanäle warten auf ihre') + ' erste Prüfung' });
    }
    return { icon: scheduler.polling ? 'fa-rotate fa-spin' : 'fa-circle-check', parts };
  });

  /** Drip-Prognose für alle Kanäle mit Drip, Teile wie oben. */
  let prognosisState = $derived.by(() => {
    const p = prognosis;
    if (!(p?.drip_channels > 0)) return null;
    const parts = [{ before: 'Drip:', count: p.drip_channels, after: plural(p.drip_channels, 'Kanal', 'Kanäle') },
                   { count: p.total_missing, after: plural(p.total_missing, 'Video fehlt', 'Videos fehlen') }];
    if (p.avg_video_size > 0) {
      parts.push({ before: 'etwa', count: formatSize(p.estimated_bytes) }, { before: 'noch etwa', count: remainingText(p.days_remaining) });
    }
    if (p.disk_free > 0) {
      parts.push({ count: formatSize(p.disk_free), after: p.disk_total > 0 ? `frei von ${formatSize(p.disk_total)}` : 'frei',
                   warn: p.disk_free < DISK_LOW_BYTES });
    }
    if (p.unscanned_channels > 0) parts.push({ count: p.unscanned_channels, after: `${plural(p.unscanned_channels, 'Kanal', 'Kanäle')} ohne Scan` });
    return { icon: 'fa-droplet', parts };
  });

  function remainingText(days) {
    if (days > 365) return `${(days / 365).toLocaleString('de-DE', { maximumFractionDigits: 1 })} Jahre`;
    return `${num(days)} ${days === 1 ? 'Tag' : 'Tage'}`;
  }

  function savedChoice(key, allowed, fallback) {
    const value = getFilter(PAGE, key, fallback);
    return allowed.includes(value) ? value : fallback;
  }

  // ── Laden ──

  async function loadSubs() {
    try {
      const result = await api.getSubscriptions({ page: 1, per_page: 1000 });
      subs = result.subscriptions || [];
      total = result.total || 0;
      languageCounts = result.language_counts || [];
      loaded = true;
      [rssStats, scheduler] = await Promise.all([api.getRSSStats(), api.getSchedulerStatus()]);
    } catch (e) { toast.error(e.message); }
  }

  async function loadPrognosis() {
    try { prognosis = await api.getDripPrognosis(); } catch { prognosis = null; }
  }

  // ── Ein Kanal: Einstellungen und Aktionen (gemeinsam mit der Kanalseite) ──

  function replaceSub(id, changes) {
    const i = subs.findIndex((s) => s.id === id);
    if (i >= 0) subs[i] = { ...subs[i], ...changes };
  }

  // Nächster Lauf, Abschluss und Prognose kommen vom Server
  function refreshDrip() {
    loadSubs();
    loadPrognosis();
  }

  const actions = createChannelActions({
    patch: (sub, changes) => replaceSub(sub.id, changes),
    reload: refreshDrip,
    confirm: (...args) => confirmRef.ask(...args),
    removed: (sub) => {
      subs = subs.filter((s) => s.id !== sub.id);
      total--;
      if (sheet?.id === sub.id) sheet = null;
    },
    checking,
  });
  const { save, saveMusic, runCheck, queueMissing, setAuto, setDrip, setMusic, setEnabled, checkNow, refreshSoon } = actions;

  const openChannel = (sub) => navigate(`/channel/${sub.channel_id}`);
  const openNew = (sub) => navigate(`/feed?channels=${encodeURIComponent(sub.channel_id)}`);

  async function removeSubs(list) {
    await actions.removeChannels(list);
    selected = new Set();
  }

  // ── Alle Kanäle ──

  async function pollNow() {
    try {
      const result = await api.triggerRSSPoll();
      if (result.triggered) toast.success(`Prüfung aller ${num(result.feed_count)} Kanäle gestartet, Fortschritt in der Aktivitätenleiste`);
      else toast.info(result.message || 'Keine Prüfung gestartet');
      loadSubs();
    } catch (e) { toast.error(e.message); }
  }

  async function resetAllErrors() {
    try {
      const result = await api.resetAllErrors();
      toast.success(`Fehler von ${num(result.reset)} Kanälen zurückgesetzt`);
      await loadSubs();
    } catch (e) { toast.error(e.message); }
  }

  // ── Hinzufügen ──

  function toggleAdding() {
    adding = !adding;
    listOpen = false;
  }

  async function addSingle() {
    const input = channelInput.trim();
    if (!input) return;
    subscribing = true;
    try {
      // Der Server löst Kanal-ID, Kanal-Adresse, Handle und Video-Adresse auf
      const added = await api.addSubscription({ channel_id: input, auto_download: autoDownload, download_quality: newQuality || null });
      if (added.already_subscribed) toast.info(`"${added.channel_name}" ist bereits abonniert`);
      else toast.success(`"${added.channel_name}" hinzugefügt, Kanalbild und erste Prüfung laufen`);
      channelInput = '';
      await loadSubs();
      refreshSoon(REFRESH_AFTER_ADD_MS);
    } catch (e) { toast.error(e.message); }
    finally { subscribing = false; }
  }

  async function addBatch() {
    // Je Zeile eine Kanal-ID, auch aus einer Kanal-Adresse herausgelesen
    const ids = batchInput.split('\n').map((line) => (line.match(CHANNEL_ID) || [])[0]).filter(Boolean);
    if (!ids.length) { toast.error('Keine Kanal-ID gefunden (beginnt mit UC, 24 Zeichen)'); return; }
    importing = true;
    try {
      const result = await api.addSubscriptionsBatch({ channel_ids: ids, auto_download: autoDownload });
      toast.success(`${num(result.added)} Abos importiert, ${num(result.skipped)} übersprungen`);
      batchInput = '';
      listOpen = false;
      loadSubs();
    } catch (e) { toast.error(e.message); }
    finally { importing = false; }
  }

  // ── Ansicht, Menü, Seitenblatt ──

  function setView(value) { view = value; saveFilters(PAGE, { view: value }); }
  function setSort(key) { sort = key; saveFilters(PAGE, { sort: key }); }
  const chooseFilter = (key) => { filter = filter === key ? '' : key; };
  const showAll = () => { filter = ''; search = ''; languages = []; };

  function openSheet(sub, { problems = false } = {}) { sheet = { id: sub.id, problems }; }

  function channelMenu(event, sub) {
    const missing = Math.min(MISSING_BATCH, missingCount(sub));
    menu.open(event, channelName(sub), [
      { icon: 'fa-folder-open', label: 'Kanal öffnen', run: () => openChannel(sub) },
      { icon: 'fa-rotate', label: 'Jetzt prüfen', run: () => checkNow(sub) },
      ...(missing ? [{ icon: 'fa-download', label: `${missing} fehlende laden`, run: () => queueMissing(sub) }] : []),
      { trenner: true },
      { icon: 'fa-bolt', label: 'Auto-Download', hint: onOff(sub.auto_download), run: () => setAuto(sub, !sub.auto_download) },
      { icon: 'fa-droplet', label: `Drip, ${dripCount(sub)} am Tag`, hint: onOff(sub.drip_enabled), run: () => setDrip(sub, !sub.drip_enabled) },
      { icon: 'fa-music', label: 'Musikkanal', hint: onOff(sub.music_channel), run: () => setMusic(sub, !sub.music_channel) },
      ...(sub.problem_count > 0
        ? [{ icon: 'fa-circle-exclamation', label: 'Problem-Videos', hint: num(sub.problem_count), run: () => openSheet(sub, { problems: true }) }] : []),
      { icon: 'fa-sliders', label: 'Alle Einstellungen ...', run: () => openSheet(sub) },
      { trenner: true },
      { icon: 'fa-power-off', label: sub.enabled ? 'Prüfung abschalten' : 'Prüfung einschalten', run: () => setEnabled(sub, !sub.enabled) },
      { icon: 'fa-xmark', label: 'Abo beenden ...', danger: true, run: () => removeSubs([sub]) },
    ]);
  }

  /** Einzel-Aktionen für das Seitenblatt. */
  const sheetActions = { ...actions, remove: (sub) => removeSubs([sub]) };

  /** Schalter in der Liste: Merkmal, Zustand, Umschalten. */
  const LIST_TOGGLES = [
    { key: 'auto', icon: 'fa-bolt', label: 'Auto-Download', on: (s) => s.auto_download, set: setAuto },
    { key: 'drip', icon: 'fa-droplet', label: 'Drip', on: (s) => s.drip_enabled, set: setDrip },
    { key: 'musik', icon: 'fa-music', label: 'Musikkanal', on: (s) => s.music_channel, set: setMusic, cls: 'musik' },
    { key: 'pruefung', icon: 'fa-power-off', label: 'Prüfung', on: (s) => s.enabled, set: setEnabled },
  ];

  function badgeClick(sub, badge) {
    if (badge.key === 'neu') openNew(sub);
    else openSheet(sub);
  }

  // ── Auswahl und Stapel ──

  function toggle(sub) {
    const next = new Set(selected);
    next.has(sub.id) ? next.delete(sub.id) : next.add(sub.id);
    selected = next;
  }
  function startSelecting() { selecting = true; sheet = null; }
  function stopSelecting() { selecting = false; selected = new Set(); }
  const activate = (sub) => (selecting ? toggle(sub) : openChannel(sub));
  const channelCount = (count, dative = false) => `${num(count)} ${count === 1 ? 'Kanal' : dative ? 'Kanälen' : 'Kanäle'}`;

  /** Die Auswahl nacheinander über die Einzel-Schnittstelle; zählt die Erfolge. */
  async function forEachSelected(run) {
    batchBusy = true;
    let ok = 0;
    try {
      for (const sub of selectedSubs) if (await run(sub)) ok++;
    } finally { batchBusy = false; }
    return ok;
  }

  async function batchSave(changes, what) {
    const ok = await forEachSelected((sub) => save(sub, changes));
    toast.success(`${what} bei ${channelCount(ok, true)}`);
    if ('drip_enabled' in changes) refreshDrip();
  }

  async function batchMusic(on) {
    const ok = await forEachSelected((sub) => saveMusic(sub, on));
    toast.success(`${on ? 'Musikkanal' : 'Kein Musikkanal mehr'} bei ${channelCount(ok, true)}`);
  }

  async function batchCheck() {
    let found = 0;
    const ok = await forEachSelected(async (sub) => {
      const result = await runCheck(sub);
      found += result?.new_videos || 0;
      return !!result;
    });
    toast.success(`${channelCount(ok)} geprüft, ${num(found)} neue Videos`);
    loadSubs();
  }

  function batchQuality(event) {
    menu.open(event, 'Qualität der Auswahl', qualityItems(null, (value) =>
      batchSave({ download_quality: value || null }, value ? `Qualität ${qualityShort(value)}` : 'Qualität aus den Einstellungen')));
  }

  const hideImage = (event) => { event.currentTarget.style.visibility = 'hidden'; };

  // Laden nur beim Öffnen - ein $effect würde sich über die gelesenen Abos selbst neu auslösen
  onMount(() => {
    loadSubs();
    loadPrognosis();
    return actions.dispose;
  });
</script>

{#snippet statusLine(state)}
  <div class="pruefstand" class:warnung={state.warn}>
    <i class="fa-solid {state.icon}"></i>
    <span>{#each state.parts as part, i (i)}{i ? ' · ' : ''}<span class:warnung={part.warn}>{part.before ? `${part.before}${part.count !== undefined ? ' ' : ''}` : ''}{#if part.count !== undefined}<span class="zahl">{typeof part.count === 'number' ? num(part.count) : part.count}</span>{/if}{part.after ? ` ${part.after}` : ''}</span>{/each}</span>
  </div>
{/snippet}

{#snippet avatar(sub)}
  <span class="avatar">
    <span>{channelName(sub)[0]?.toUpperCase()}</span>
    {#if sub.avatar_path}<img src={api.channelAvatarUrl(sub.channel_id)} alt="" loading="lazy" onerror={hideImage} />{/if}
  </span>
{/snippet}

{#snippet medalBadge(sub, withLabel)}
  {@const medal = medalOf(sub)}
  {#if medal}
    <span class="medaille" style={medalStyle(sub)} title={coverageTitle(sub)}><i class="fa-solid fa-medal"></i>{withLabel ? ` ${medal.label}` : ''}</span>
  {/if}
{/snippet}

{#snippet coverageBar(sub)}
  <span class="balken" style={medalStyle(sub)}><b style:width="{coverageShare(sub) * 100}%"></b></span>
{/snippet}

{#snippet filterChip(f, count)}
  <button class="tv-chip" class:aktiv={filter === f.key} style={f.style} title={f.title} onclick={() => chooseFilter(f.key)}>
    {#if f.icon}<i class="fa-solid {f.icon} chip-symbol"></i>{/if}{f.label}{#if count !== null}<span class="tv-zaehler">{num(count)}</span>{/if}
  </button>
{/snippet}

<div class="tv-seite kanaele">
  <div class="tv-seitenkopf">
    <PageHeader title="Kanäle" {info}>
      <button class="tv-knopf ohne" onclick={() => navigate('/feed')} title="Neue Videos der abonnierten Kanäle">
        <i class="fa-solid fa-rss"></i> Neu bei Abos{#if rssStats?.new_videos > 0}<span class="tv-zaehler akzent">{num(rssStats.new_videos)}</span>{/if}</button>
      <button class="tv-knopf" class:aktiv={adding} onclick={toggleAdding} title="Kanäle abonnieren, einzeln oder als Liste">
        <i class="fa-solid fa-plus"></i> Hinzufügen</button>
      <button class="tv-knopf haupt" onclick={pollNow} disabled={scheduler?.polling} title="Alle eingeschalteten Kanäle sofort auf neue Videos prüfen">
        <i class="fa-solid fa-rotate"></i> Alle jetzt prüfen</button>
    </PageHeader>

    {#if schedulerState}{@render statusLine(schedulerState)}{/if}
    {#if prognosisState}{@render statusLine(prognosisState)}{/if}

    {#if adding}
      <form class="tv-filter hinzu" onsubmit={(e) => { e.preventDefault(); addSingle(); }}>
        <!-- svelte-ignore a11y_autofocus -->
        <input class="tv-eingabe adresse" bind:value={channelInput} placeholder="Kanal-Adresse, @Name, Kanal-ID oder Video-Adresse" autofocus />
        <button class="tv-knopf haupt" disabled={subscribing || !channelInput.trim()}>{subscribing ? 'Abonniert ...' : 'Abonnieren'}</button>
        <span class="tv-trenner"></span>
        <button type="button" class="tv-chip" class:aktiv={autoDownload} onclick={() => autoDownload = !autoDownload}
                title="Neue Videos der hinzugefügten Kanäle gleich automatisch laden (gilt auch für die Liste)">
          <i class="fa-solid fa-bolt"></i> Auto-Download</button>
        <button type="button" class="tv-chip" onclick={(e) => menu.open(e, 'Qualität', qualityItems(newQuality, (value) => { newQuality = value; }))}
                title="Qualität für die Downloads des einzeln abonnierten Kanals">
          <i class="fa-solid fa-sliders"></i> {qualityShort(newQuality)}</button>
        <span class="tv-trenner"></span>
        <span class="tv-leise tv-klein">Mehrere auf einmal: eine Kanal-ID je Zeile</span>
        <button type="button" class="tv-knopf klein" class:aktiv={listOpen} onclick={() => listOpen = !listOpen}
                title="Je Zeile eine Kanal-ID (beginnt mit UC) oder eine Kanal-Adresse, die sie enthält">Liste einfügen ...</button>
        <div class="rechts"><button type="button" class="tv-knopf klein ohne" onclick={toggleAdding}><i class="fa-solid fa-xmark"></i> Schließen</button></div>
      </form>
      {#if listOpen}
        <div class="tv-filter liste-einfuegen">
          <textarea class="tv-eingabe" bind:value={batchInput} rows="5" placeholder="Eine Kanal-ID oder Kanal-Adresse je Zeile"></textarea>
          <button class="tv-knopf haupt" onclick={addBatch} disabled={importing || !batchLines}>
            {#if importing}Importiert ...{:else}<span class="zahl">{num(batchLines)}</span> importieren{/if}</button>
        </div>
      {/if}
    {/if}

    {#if selecting}
      <BatchToolbar hint="Kanäle antippen, um sie auszuwählen" selectedCount={selectedSubs.length} totalCount={shown.length}
                    onSelectAll={() => selected = new Set(shown.map((s) => s.id))} onDone={stopSelecting}>
        <button class="tv-knopf klein" disabled={batchBusy} onclick={() => batchSave({ auto_download: !batchAll.auto }, `Auto-Download ${onOff(!batchAll.auto)}`)}>
          <i class="fa-solid fa-bolt"></i> Auto-Download {onOff(!batchAll.auto)}</button>
        <button class="tv-knopf klein" disabled={batchBusy} onclick={() => batchSave({ drip_enabled: !batchAll.drip }, `Drip ${onOff(!batchAll.drip)}`)}>
          <i class="fa-solid fa-droplet"></i> Drip {onOff(!batchAll.drip)}</button>
        <button class="tv-knopf klein" disabled={batchBusy} onclick={() => batchMusic(!batchAll.music)}>
          <i class="fa-solid fa-music"></i> {batchAll.music ? 'Kein Musikkanal' : 'Als Musikkanal'}</button>
        <button class="tv-knopf klein" disabled={batchBusy} onclick={batchQuality}><i class="fa-solid fa-sliders"></i> Qualität ...</button>
        <button class="tv-knopf klein" disabled={batchBusy} onclick={batchCheck}>
          <i class="fa-solid fa-rotate" class:fa-spin={batchBusy}></i> Jetzt prüfen</button>
        <button class="tv-knopf klein gefahr" disabled={batchBusy} onclick={() => removeSubs(selectedSubs)}>
          <i class="fa-solid fa-xmark"></i> Abo beenden</button>
      </BatchToolbar>
    {:else if subs.length}
      <CollectionBar bind:search placeholder="Kanäle suchen" bind:view={() => view, setView} onSelect={startSelecting}>
        <span class="tv-trenner"></span>
        {#each visibleFilters as f (f.key)}{@render filterChip(f, f.noCount ? null : counts[f.key])}{/each}
        <span class="tv-trenner"></span>
        {#each MEDAL_FILTERS as f (f.key)}{@render filterChip(f, counts[f.key])}{/each}
        <span class="tv-trenner"></span>
        <span class="tv-etikett">Sortieren</span>
        {#each SORTS as option (option.key)}
          <button class="tv-chip" class:aktiv={sort === option.key} title={option.title} onclick={() => setSort(option.key)}>{option.label}</button>
        {/each}
        {#snippet rechts()}
          {#if counts.fehler}
            <button class="tv-knopf klein" onclick={resetAllErrors}
                    title="Fehlerzähler löschen und die Kanäle bald wieder prüfen. Abgeschaltete Kanäle bleiben abgeschaltet.">
              <i class="fa-solid fa-rotate-left"></i> Fehler zurücksetzen</button>
          {/if}
        {/snippet}
      </CollectionBar>
      <LanguageChips counts={languageCounts} selected={languages} onchange={(list) => languages = list} />
    {/if}
  </div>

  <div class="tv-rollfeld" data-scroll-root>
    {#if !loaded}
      <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt ...</div>
    {:else if !subs.length}
      <div class="leer-gross">
        <i class="fa-solid fa-user-plus"></i>
        <h2>Noch keine Kanäle</h2>
        <p>Füge Kanäle hinzu, um neue Videos automatisch zu erkennen.</p>
        <button class="tv-knopf haupt" onclick={() => adding = true}><i class="fa-solid fa-plus"></i> Kanäle hinzufügen</button>
      </div>
    {:else if !shown.length}
      <div class="tv-leer">
        <p>Kein Kanal passt zu dieser Auswahl.</p>
        <button class="tv-knopf" onclick={showAll}>Alle Kanäle zeigen</button>
      </div>
    {:else if view === 'kacheln'}
      <div class="k-raster" class:auswahl={selecting}>
        {#each shown as sub (sub.id)}
          {@const isSelected = selected.has(sub.id)}
          <article class="k-kachel" class:aus={!sub.enabled} class:gewaehlt={isSelected || sheet?.id === sub.id}>
            <button class="flaeche" onclick={() => activate(sub)} aria-label="{channelName(sub)} {selecting ? 'auswählen' : 'öffnen'}"></button>
            <div class="banner">
              {#if sub.banner_url}<img src={api.bannerUrl(sub.channel_id)} alt="" loading="lazy" onerror={hideImage} />{/if}
            </div>
            {#if selecting}
              <span class="haken"><i class="fa-{isSelected ? 'solid fa-square-check' : 'regular fa-square'}"></i></span>
            {:else}
              <div class="k-tun">
                <button onclick={() => checkNow(sub)} disabled={checking[sub.id]} title="Jetzt auf neue Videos prüfen">
                  <i class="fa-solid fa-rotate" class:fa-spin={checking[sub.id]}></i></button>
                <button onclick={() => openSheet(sub)} title="Alle Einstellungen"><i class="fa-solid fa-sliders"></i></button>
                <button onclick={(e) => channelMenu(e, sub)} title="Mehr"><i class="fa-solid fa-ellipsis"></i></button>
              </div>
            {/if}
            <div class="k-kopf">
              {@render avatar(sub)}
              <div class="k-name" title={channelName(sub)}>{channelName(sub)}</div>
              <span class="vorn">{@render medalBadge(sub, true)}</span>
            </div>
            <div class="k-inhalt">
              <button class="abdeckung vorn" onclick={() => openSheet(sub)} title={coverageTitle(sub)}>
                {@render coverageBar(sub)}
                <span><span class="zahl">{num(sub.have_count)}</span> von <span class="zahl">{num(sub.wanted_count)}</span></span>
              </button>
              <div class="k-meta">
                {#if sub.last_video_date}<span>neuestes Video <span class="zahl">{dayText(sub.last_video_date)}</span></span>
                {:else}<span>noch kein Video bekannt</span>{/if}
                {#if sub.shorts_count}<span><span class="zahl">{num(sub.shorts_count)}</span> Shorts</span>{/if}
              </div>
              <div class="merkmale">
                <LanguageLabel code={sub.language} channel />
                {#each channelBadges(sub) as badge (badge.key)}
                  <button class="merkmal vorn {badge.cls || ''}" title={badge.title} onclick={() => badgeClick(sub, badge)}>
                    {#if badge.icon}<i class="fa-solid {badge.icon}"></i>{/if}
                    {#if badge.count !== undefined}<span class="zahl">{num(badge.count)}</span>{/if}
                    {badge.text}</button>
                {/each}
                {#if sub.problem_count > 0}
                  <button class="merkmal vorn warnung" onclick={() => openSheet(sub, { problems: true })}
                          title="Videos, die sich dauerhaft nicht laden ließen - zeigt sie mit Erneut versuchen und Verwerfen">
                    <i class="fa-solid fa-circle-exclamation"></i> <span class="zahl">{num(sub.problem_count)}</span> Probleme</button>
                {/if}
              </div>
            </div>
          </article>
        {/each}
      </div>
    {:else}
      <div class="liste">
        <table class="k-tabelle">
          <thead>
            <tr>
              {#if selecting}<th class="sp-haken"></th>{/if}
              {#each COLUMNS as col (col.cls)}
                <th class={col.cls}>
                  {#if col.sort}
                    <button class:sortiert={sort === col.sort} onclick={() => setSort(col.sort)}
                            title={SORTS.find((s) => s.key === col.sort)?.title}>
                      {col.label}{#if sort === col.sort} <i class="fa-solid fa-arrow-down-long"></i>{/if}</button>
                  {:else}{col.label}{/if}
                </th>
              {/each}
            </tr>
          </thead>
          <tbody>
            {#each shown as sub (sub.id)}
              {@const isSelected = selected.has(sub.id)}
              <tr class:aus={!sub.enabled} class:gewaehlt={isSelected || sheet?.id === sub.id}>
                {#if selecting}
                  <td class="sp-haken"><button class="haken-knopf" onclick={() => toggle(sub)} aria-pressed={isSelected} title="Auswählen">
                    <i class="fa-{isSelected ? 'solid fa-square-check' : 'regular fa-square'}"></i></button></td>
                {/if}
                <td class="sp-kanal">
                  <button class="wer" onclick={() => activate(sub)} title={selecting ? 'Auswählen' : 'Kanal öffnen'}>
                    {@render avatar(sub)}<span class="wer-name">{channelName(sub)}</span>{@render medalBadge(sub, false)}<LanguageLabel code={sub.language} channel /></button>
                </td>
                <td class="sp-abdeckung">
                  <button class="abdeckung" onclick={() => openSheet(sub)} title={coverageTitle(sub)}>
                    {@render coverageBar(sub)}<span class="zahl prozent">{sub.wanted_count ? `${coveragePercent(sub)} %` : ''}</span></button>
                </td>
                <td class="sp-neu">
                  {#if sub.new_videos > 0}
                    <button class="neu-zahl zahl" onclick={() => openNew(sub)} title="Neue Videos dieses Kanals bei den Abos zeigen">{num(sub.new_videos)}</button>
                  {/if}
                </td>
                <td class="sp-video zahl">{dayText(sub.last_video_date)}</td>
                <td class="sp-geprueft zahl tv-leise">{momentText(sub.last_checked)}</td>
                <td class="sp-merkmale">
                  <div class="schalter-reihe">
                    {#each LIST_TOGGLES as t (t.key)}
                      {@const on = t.on(sub)}
                      <button class={t.cls} class:an={on} aria-pressed={!!on} onclick={() => t.set(sub, !on)}
                              title="{t.label} {onOff(on)} - Klick schaltet {on ? 'aus' : 'ein'}"><i class="fa-solid {t.icon}"></i></button>
                    {/each}
                  </div>
                </td>
                <td class="sp-mehr">
                  <button class="tv-knopf ohne symbol klein" onclick={(e) => channelMenu(e, sub)} title="Mehr"><i class="fa-solid fa-ellipsis"></i></button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </div>

  {#if sheetSub}
    {#key sheet}
      <ChannelSettingsSheet sub={sheetSub} actions={sheetActions} checking={!!checking[sheetSub.id]}
                            showProblems={sheet.problems} onClose={() => sheet = null} />
    {/key}
  {/if}
</div>

<ActionMenu bind:this={menu} />
<ConfirmDialog bind:this={confirmRef} />

<style>
  .kanaele { position: relative; }   /* Bezug für das Seitenblatt */

  /* Prüfstand und Drip-Prognose unter dem Titel */
  .pruefstand { display: flex; gap: var(--tv-a2); align-items: baseline; margin: -6px 0 var(--tv-a3);
                font-size: var(--tv-gr-klein); color: var(--tv-text-2); }
  .pruefstand + .pruefstand { margin-top: calc(-1 * var(--tv-a2)); }
  .pruefstand > i { color: var(--tv-akzent); }
  .pruefstand.warnung > i, .pruefstand .warnung { color: var(--tv-warnung); }

  /* Hinzufügen */
  .hinzu .adresse { width: 420px; max-width: 100%; }
  .hinzu .rechts { margin-left: auto; }
  .liste-einfuegen { align-items: flex-end; }
  .liste-einfuegen textarea { flex: 1; min-width: 260px; height: auto; min-height: 132px; padding: var(--tv-a2) var(--tv-a3);
                              resize: vertical; font-family: var(--tv-schrift-zahl); line-height: 1.5; }

  .chip-symbol { color: var(--medaille, currentColor); }

  /* Gemeinsame Teile von Kachel und Liste */
  .avatar { position: relative; flex: none; display: grid; place-items: center; overflow: hidden; border-radius: var(--tv-ecke);
            background: var(--tv-mulde); color: var(--tv-akzent); font-weight: 700; }
  .avatar img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
  .medaille { flex: none; display: inline-flex; align-items: center; gap: 5px; height: 26px; padding: 0 8px; border-radius: var(--tv-ecke-klein);
              font-size: var(--tv-gr-marke); font-weight: 700; letter-spacing: 0.04em; background: var(--medaille-grund); color: var(--medaille); }
  .abdeckung { display: flex; align-items: center; gap: var(--tv-a3); width: 100%; padding: 0; border: 0; background: none;
               color: var(--tv-text-2); font: inherit; font-size: var(--tv-gr-klein); text-align: left; cursor: pointer; }
  .abdeckung .zahl { color: var(--tv-text); font-weight: 600; }
  .balken { flex: 1; min-width: 40px; height: 6px; background: var(--tv-mulde); border-radius: 1px; overflow: hidden; }
  .balken b { display: block; height: 100%; background: var(--medaille, var(--tv-akzent)); }

  /* Kacheln: Banner, Bild, Medaille, Abdeckung, nur eingeschaltete Merkmale */
  .k-raster { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: var(--tv-a4); }
  .k-kachel { position: relative; min-width: 0; background: var(--tv-karte); border-radius: var(--tv-ecke); overflow: hidden;
              outline: 1px solid var(--tv-rand); outline-offset: -1px; }
  .k-kachel:hover { outline-color: var(--tv-rand-stark); }
  .k-kachel.aus { opacity: 0.55; }
  .k-kachel.gewaehlt { outline: 2px solid var(--tv-akzent); outline-offset: -2px; }
  .flaeche { position: absolute; inset: 0; z-index: 1; padding: 0; border: 0; background: none; cursor: pointer; }
  .vorn { position: relative; z-index: 2; }
  .auswahl .flaeche { z-index: 3; }     /* in der Auswahl wählt jeder Klick */
  .banner { height: 72px; background: linear-gradient(120deg, var(--tv-karte-2), var(--tv-grund)); }
  .banner img { display: block; width: 100%; height: 100%; object-fit: cover; }
  .k-tun { position: absolute; right: 8px; top: 8px; z-index: 2; display: flex; gap: 4px; opacity: 0; transition: opacity var(--tv-schnell); }
  .k-kachel:hover .k-tun, .k-kachel:focus-within .k-tun { opacity: 1; }
  .k-tun button { width: 34px; height: 34px; border: 0; border-radius: var(--tv-ecke-klein); background: var(--tv-schleier);
                  color: var(--tv-text); cursor: pointer; }
  .k-tun button:hover:not(:disabled) { color: var(--tv-akzent); }
  .haken { position: absolute; left: 8px; top: 8px; z-index: 2; width: 30px; height: 30px; display: grid; place-items: center;
           border-radius: var(--tv-ecke-klein); background: var(--tv-schleier); color: var(--tv-text-2); font-size: 18px; }
  .gewaehlt .haken { color: var(--tv-akzent); }
  .k-kopf { display: flex; gap: var(--tv-a3); align-items: flex-end; padding: 0 var(--tv-a4); margin-top: -28px; }
  .k-kopf .avatar { width: 60px; height: 60px; outline: 3px solid var(--tv-karte); font-size: var(--tv-gr-titel); }
  .k-name { flex: 1; min-width: 0; padding-bottom: 2px; font-weight: 700; font-size: 18px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .k-kopf .vorn { margin-bottom: 4px; }
  .k-inhalt { display: flex; flex-direction: column; gap: var(--tv-a2); padding: var(--tv-a3) var(--tv-a4) var(--tv-a4); }
  .k-meta { display: flex; gap: var(--tv-a3); flex-wrap: wrap; font-size: var(--tv-gr-klein); color: var(--tv-text-3); }
  .merkmale { display: flex; gap: 6px; flex-wrap: wrap; min-height: 24px; }
  /* Sprach-Label über der Klickfläche der Kachel, damit sein Tooltip erscheint */
  .merkmale :global(.sprache) { position: relative; z-index: 2; }
  .tv-seitenkopf :global(.sprachen) { margin-top: var(--tv-a2); }
  .merkmal { display: inline-flex; align-items: center; gap: 5px; height: 24px; padding: 0 8px; border: 0; border-radius: var(--tv-ecke-klein);
             background: var(--tv-karte-2); color: var(--tv-text-2); font: inherit; font-size: var(--tv-gr-marke); font-weight: 700; cursor: pointer; }
  .merkmal:hover { color: var(--tv-text); }
  .merkmal.neu { background: rgba(var(--tv-akzent-rgb), 0.14); color: var(--tv-akzent); }
  .merkmal.musik { color: var(--tv-art-musik); }
  .merkmal.wartet { color: var(--tv-info); }
  .merkmal.fehler { background: rgba(var(--tv-gefahr-rgb), 0.14); color: var(--tv-gefahr); }
  .merkmal.warnung { background: rgba(var(--tv-warnung-rgb), 0.14); color: var(--tv-warnung); }

  /* Dichte Liste: feste Spaltenbreiten, nichts rollt seitlich; schmal entfallen Spalten.
     Die Linien zwischen den Zeilen sind der Zeilenabstand auf der Randfarbe. */
  .liste { container-type: inline-size; }
  .k-tabelle { width: 100%; margin-top: -1px; table-layout: fixed; border-collapse: separate; border-spacing: 0 1px; background: var(--tv-rand); }
  .k-tabelle th { position: sticky; top: 0; z-index: 1; padding: 8px; background: var(--tv-grund); text-align: left; white-space: nowrap; overflow: hidden;
                  font-size: var(--tv-gr-marke); font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--tv-text-3); }
  .k-tabelle th button { padding: 0; border: 0; background: none; color: inherit; font: inherit; letter-spacing: inherit;
                         text-transform: inherit; cursor: pointer; }
  .k-tabelle th button:hover, .k-tabelle th button.sortiert { color: var(--tv-akzent); }
  .k-tabelle td { padding: 8px; background: var(--tv-grund); vertical-align: middle; font-size: var(--tv-gr-klein);
                  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .k-tabelle tr:hover td { background: var(--tv-flaeche); }
  .k-tabelle tr.gewaehlt td { background: var(--tv-karte); }
  .k-tabelle tr.aus td { color: var(--tv-text-3); }
  .k-tabelle tr.aus td > * { opacity: 0.55; }
  .sp-haken { width: 44px; }
  .sp-abdeckung { width: 24%; }
  .sp-neu { width: 72px; }
  .sp-video { width: 140px; }
  .sp-geprueft { width: 130px; }
  .sp-merkmale { width: 156px; }
  .sp-mehr { width: 52px; }
  .haken-knopf { width: 28px; height: 28px; padding: 0; border: 0; background: none; color: var(--tv-text-3); font-size: 18px; cursor: pointer; }
  .gewaehlt .haken-knopf { color: var(--tv-akzent); }
  .wer { display: flex; align-items: center; gap: var(--tv-a3); width: 100%; min-width: 0; padding: 0; border: 0; background: none;
         color: var(--tv-text); font: inherit; font-size: var(--tv-gr-text); font-weight: 600; text-align: left; cursor: pointer; }
  .wer:hover .wer-name { color: var(--tv-akzent); }
  .wer .avatar { width: 36px; height: 36px; border-radius: var(--tv-ecke-klein); font-size: var(--tv-gr-klein); }
  .wer-name { min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .wer .medaille { height: 24px; padding: 0 6px; }
  .prozent { flex: none; min-width: 52px; text-align: right; }
  .neu-zahl { padding: 0; border: 0; background: none; color: var(--tv-text); font-size: var(--tv-gr-klein); cursor: pointer; }
  .neu-zahl:hover { color: var(--tv-akzent); }
  .schalter-reihe { display: flex; gap: 4px; }
  .schalter-reihe button { width: 30px; height: 30px; display: grid; place-items: center; padding: 0; border: 0; border-radius: var(--tv-ecke-klein);
                           background: var(--tv-karte); color: var(--tv-text-3); font-size: var(--tv-gr-klein); cursor: pointer; }
  .schalter-reihe button:hover { color: var(--tv-text); }
  .schalter-reihe button.an { background: rgba(var(--tv-akzent-rgb), 0.12); color: var(--tv-akzent); }
  .schalter-reihe button.an.musik { background: rgba(192, 132, 252, 0.12); color: var(--tv-art-musik); }

  @container (max-width: 980px) { .sp-geprueft { display: none; } }
  @container (max-width: 820px) { .sp-video { display: none; } }
  @container (max-width: 600px) { .sp-merkmale { display: none; } }

  /* Leere Liste */
  .tv-leer p { margin: 0 0 var(--tv-a3); }
  .leer-gross { padding: 72px var(--tv-a5); text-align: center; color: var(--tv-text-2); }
  .leer-gross i { font-size: 44px; color: var(--tv-text-3); margin-bottom: var(--tv-a4); }
  .leer-gross h2 { margin: 0 0 var(--tv-a2); color: var(--tv-text); }
  .leer-gross p { margin: 0 auto var(--tv-a4); max-width: 520px; }
  .leer-gross .tv-knopf i { font-size: inherit; color: inherit; margin: 0; }
</style>

<!--
  TubeVault - Nachvertonung (Entwurf mockups/nachvertonung.html)
  Fester Kopf: Kennzahlen, Zustand des Nachvertoners, Vertonen anhalten
  oder fortsetzen, "Video vertonen" und die Reiter. Links die laufenden
  Aufträge als Karten mit ihren Schritten und darunter die Liste des
  Reiters (seitenweise), rechts Nachvertoner, Stimmen und Ablauf.
  Der laufende Auftrag wird im Takt neu abgefragt; die Liste lädt nur neu,
  wenn sich die Zählungen ändern.
-->
<script>
  import { onDestroy, onMount } from 'svelte';
  import { api } from '../lib/api/client.js';
  import { navigate } from '../lib/router/router.js';
  import { toast } from '../lib/stores/notifications.js';
  import { settings } from '../lib/stores/settings.js';
  import { rememberLanguage } from '../lib/utils/audioTrackSync.js';
  import { createListLoader } from '../lib/utils/listLoader.svelte.js';
  import { infiniteScroll } from '../lib/utils/infiniteScroll.js';
  import { ago, headline, languageName, workerLine } from '../lib/utils/dubbingText.js';
  import PageHeader from '../lib/components/common/PageHeader.svelte';
  import ActionMenu from '../lib/components/common/ActionMenu.svelte';
  import DubDialog from '../lib/components/watch/DubDialog.svelte';
  import RunningDub from '../lib/components/dubbing/RunningDub.svelte';
  import DubRow from '../lib/components/dubbing/DubRow.svelte';
  import DubCompare from '../lib/components/dubbing/DubCompare.svelte';
  import VoiceCard from '../lib/components/dubbing/VoiceCard.svelte';
  import VideoPicker from '../lib/components/dubbing/VideoPicker.svelte';

  const REFRESH_MS = 5000;
  const PAGE = 50;
  const PROCESSING_KEY = 'dub.processing_enabled';
  const SUBTITLES_KEY = 'dub.default_subtitles';
  const VOICE_KEY = 'dub.default_voice';
  const FAILED = ['error', 'skipped', 'cancelled'];
  const TABS = [
    { key: 'all', label: 'Alle', icon: 'fa-layer-group' },
    { key: 'working', label: 'Läuft', icon: 'fa-gears' },
    { key: 'queued', label: 'Wartet', icon: 'fa-hourglass-half' },
    { key: 'done', label: 'Fertig', icon: 'fa-check' },
    { key: 'error', label: 'Fehler', icon: 'fa-triangle-exclamation' },
  ];
  const SECTIONS = { queued: 'Wartet', done: 'Fertig', error: 'Fehler', skipped: 'Übersprungen', cancelled: 'Abgebrochen' };
  const EMPTY_TAB = { queued: 'Es wartet nichts.', done: 'Noch nichts fertig.', error: 'Keine Fehler.' };
  const SUBTITLE_CHOICES = [
    { key: 'manual', label: 'vom Autor', title: 'Nur Untertitel, die der Autor des Videos erstellt hat' },
    { key: 'any', label: 'auch automatische', title: 'Auch automatisch erzeugte Untertitel und KI-Transkripte' },
  ];

  let overview = $state(null);
  let voices = $state(null);
  let tab = $state('all');
  let comparing = $state(null);
  let confirming = $state(null);     // { id, text, label, run }
  let switching = $state(false);
  let menu;
  let dubRef;
  let pickerRef;
  let timer = null;
  let countsSeen = '';

  const list = createListLoader(async (page) => {
    const answer = await api.getDubbingRequests(tab, (page - 1) * PAGE, PAGE);
    return { items: answer.items, total: answer.total };
  });

  let counts = $derived(overview?.counts || {});
  let running = $derived(overview?.running || []);
  let worker = $derived(workerLine(overview?.worker, running.length > 0));
  let enabled = $derived(overview?.enabled !== false);
  let processing = $derived(!!overview?.processing);
  let canRevoice = $derived(enabled && (voices?.voices?.length || 0) > 0);
  let subtitles = $derived($settings[SUBTITLES_KEY] || 'any');
  // Aufeinanderfolgende Aufträge gleichen Zustands bilden einen Abschnitt
  let sections = $derived.by(() => {
    const groups = [];
    for (const item of list.items) {
      const last = groups[groups.length - 1];
      if (last?.status === item.status) last.items.push(item);
      else groups.push({ status: item.status, items: [item] });
    }
    return groups;
  });

  // ── Laden ──
  async function refresh() {
    try {
      const next = await api.getDubbingOverview();
      const signature = JSON.stringify(next.counts);
      const changed = countsSeen && signature !== countsSeen;
      countsSeen = signature;
      overview = next;
      if (changed) { list.load(true); loadVoices(); }
    } catch (e) {
      if (!overview) toast.error(e.message);
    }
  }

  async function loadVoices() {
    try { voices = await api.getDubbingVoices(); } catch { voices = null; }
  }

  function reloadAll() { refresh(); list.load(true); loadVoices(); }

  function chooseTab(key) {
    tab = key;
    confirming = null;
    if (key !== 'working') list.load(true);
  }

  // ── Einstellungen dieser Seite ──
  async function saveSetting(key, value) {
    const answer = await api.updateSetting(key, value);
    settings.update((all) => ({ ...all, [key]: answer.value }));
    return answer.value;
  }

  async function setProcessing(on) {
    switching = true;
    try {
      await saveSetting(PROCESSING_KEY, on ? 'true' : 'false');
      toast.info(on ? 'Vertonen läuft wieder' : 'Vertonen angehalten - ein laufender Auftrag wird noch fertig');
      await refresh();
    } catch (e) { toast.error(e.message); }
    switching = false;
  }

  async function chooseSubtitles(key) {
    try { await saveSetting(SUBTITLES_KEY, key); } catch (e) { toast.error(e.message); }
  }

  async function chooseVoice(name) {
    try {
      await saveSetting(VOICE_KEY, name);
      await loadVoices();
      toast.success(`${name} ist die Vorauswahl`);
    } catch (e) { toast.error(e.message); }
  }

  // ── Aktionen ──
  const openVideo = (item) => navigate(`/watch/${item.video_id}`);

  function playDubbed(item) {
    rememberLanguage(item.target_language);   // die Wiedergabe startet mit dieser Spur
    openVideo(item);
  }

  function compare(item) {
    comparing = comparing?.id === item.id ? null : item;
  }

  async function act(work, done) {
    try { await work(); if (done) toast.success(done); }
    catch (e) { toast.error(e.message); }
    confirming = null;
    reloadAll();
  }

  const cancel = (item) => act(() => api.cancelDubbing(item.id), 'Auftrag abgebrochen');
  const retry = (item) => act(() => api.retryDubbing(item.id), 'Erneut vorgemerkt');

  function remove(item, withTrack) {
    if (comparing?.id === item.id) comparing = null;
    act(() => api.removeDubbing(item.id, withTrack), withTrack ? 'Tonspur gelöscht' : 'Aus der Liste genommen');
  }

  async function revoice(item, voice) {
    try {
      const outcome = await api.revoiceDubbing(item.id, voice);
      if (!outcome.queued) toast.info(`Nicht vorgemerkt: ${outcome.reason}`);
      else toast.success(item.status === 'queued' ? `Stimme ${voice} gewählt` : `Mit ${voice} neu vorgemerkt`);
    } catch (e) { toast.error(e.message); }
    reloadAll();
  }

  function ask(item, text, label, run) {
    confirming = { id: item.id, text, label, run };
  }

  function revoiceMenu(event, item) {
    const names = (voices?.voices || []).filter((name) => name !== item.voice);
    menu.open(event, item.status === 'queued' ? 'Andere Stimme' : 'Mit anderer Stimme neu vertonen',
      names.map((name) => ({ icon: 'fa-microphone', label: name, hint: name === voices.default ? 'Vorauswahl' : '',
                             run: () => revoice(item, name) })));
  }

  function moreMenu(event, item) {
    const target = languageName(item.target_language);
    const entries = [{ icon: 'fa-up-right-from-square', label: 'Video öffnen', run: () => openVideo(item) }];
    if (FAILED.includes(item.status)) entries.push({ icon: 'fa-rotate-right', label: 'Erneut versuchen', run: () => retry(item) });
    entries.push({ trenner: true });
    if (item.status === 'queued') {
      entries.push({ icon: 'fa-ban', label: 'Auftrag abbrechen', danger: true,
                     run: () => ask(item, 'Auftrag abbrechen? Er bleibt als abgebrochen in der Liste.', 'Abbrechen', () => cancel(item)) });
    } else {
      entries.push({ icon: 'fa-xmark', label: 'Aus der Liste nehmen',
                     run: () => ask(item, item.track_id ? 'Aus der Liste nehmen? Die Tonspur bleibt am Video.' : 'Aus der Liste nehmen?',
                                    'Entfernen', () => remove(item, false)) });
      if (item.track_id) {
        entries.push({ icon: 'fa-trash-can', label: `Tonspur ${target} löschen`, danger: true,
                       run: () => ask(item, `Tonspur ${target} löschen? Sie ist danach weg, der Auftrag verschwindet aus der Liste.`,
                                      'Löschen', () => remove(item, true)) });
      }
    }
    menu.open(event, item.title || item.video_id, entries);
  }

  async function pickVideo(video) {
    try { dubRef.open(await api.getVideo(video.id)); }   // mit Sprache des Originals
    catch (e) { toast.error(e.message); }
  }

  // Laden beim Öffnen, danach im Takt - kein $effect, der die eigenen Daten liest
  onMount(() => {
    refresh();
    list.load(true);
    loadVoices();
    timer = setInterval(refresh, REFRESH_MS);
  });
  onDestroy(() => clearInterval(timer));
</script>

<div class="tv-seite">
  <div class="tv-seitenkopf">
    <PageHeader title="Nachvertonung" info={overview ? headline(counts) : null}>
      {#if overview}
        <span class="geraet" class:aus={!worker.online}
              title={overview.worker.last_seen ? 'Letztes Lebenszeichen des Nachvertoners' : 'Der Nachvertoner meldet sich, sobald er läuft'}>
          <span class="punkt"></span>{worker.text}</span>
        {#if enabled && processing}
          <button class="tv-knopf" onclick={() => setProcessing(false)} disabled={switching}
                  title="Keine neuen Aufträge an den Nachvertoner; ein laufender wird noch fertig">
            <i class="fa-solid fa-pause"></i> Anhalten</button>
        {/if}
      {/if}
      {#if enabled}
        <button class="tv-knopf haupt" onclick={() => pickerRef.open()} title="Ein geladenes Video zum Vertonen vormerken">
          <i class="fa-solid fa-plus"></i> Video vertonen</button>
      {/if}
    </PageHeader>

    {#if overview && !enabled}
      <div class="hinweis">
        <i class="fa-solid fa-power-off"></i>
        <span>Die Nachvertonung ist ausgeschaltet. Einschalten unter Einstellungen, Erweiterungen.</span>
        <button class="tv-knopf klein" onclick={() => navigate('/settings')}>Zu den Einstellungen</button>
      </div>
    {:else if overview && !processing}
      <div class="hinweis pause">
        <i class="fa-solid fa-circle-pause"></i>
        <span>Vertonen ist angehalten. Wartende Aufträge bleiben liegen, bis du fortsetzt.</span>
        <button class="tv-knopf klein haupt" onclick={() => setProcessing(true)} disabled={switching}
                title="Der Nachvertoner bekommt wieder neue Aufträge"><i class="fa-solid fa-play"></i> Fortsetzen</button>
      </div>
    {/if}

    <div class="tv-reiter">
      {#each TABS as entry (entry.key)}
        {@const n = overview?.tabs?.[entry.key] || 0}
        <button class:aktiv={tab === entry.key} onclick={() => chooseTab(entry.key)}>
          <i class="fa-solid {entry.icon}"></i> {entry.label}{#if n}<span class="tv-zaehler">{n}</span>{/if}</button>
      {/each}
    </div>
  </div>

  <div class="tv-spalten">
    <div class="tv-rollfeld" data-scroll-root>
      <div class="liste">
        {#if !overview}
          <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt ...</div>
        {:else if overview.tabs.all === 0}
          <div class="leer-gross">
            <i class="fa-solid fa-language"></i>
            <h2>Noch keine Aufträge</h2>
            <p>Ein Video vertonen: im Video das Sprach-Symbol wählen oder hier "Video vertonen".</p>
          </div>
        {:else}
          {#if comparing}
            {#key comparing.id}<DubCompare request={comparing} onClose={() => comparing = null} />{/key}
          {/if}

          {#if tab === 'all' || tab === 'working'}
            {#each running as job (job.request.id)}
              <RunningDub {job} onCancel={cancel} onOpen={openVideo} />
            {/each}
          {/if}

          {#if tab === 'working'}
            {#if !running.length}
              <div class="tv-leer">
                Gerade läuft nichts.
                {#if !processing}Vertonen ist angehalten.{:else if !worker.online}Der Nachvertoner meldet sich nicht.{:else if counts.queued}Der Nachvertoner holt den nächsten Auftrag, sobald er frei ist.{/if}
              </div>
            {/if}
          {:else if list.loading && !list.items.length}
            <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt ...</div>
          {:else if !list.items.length}
            {#if tab !== 'all'}<div class="tv-leer">{EMPTY_TAB[tab]}</div>{/if}
          {:else}
            {#each sections as section (section.status)}
              <div class="tag-kopf"><h2>{SECTIONS[section.status]}</h2><span class="zahl">{counts[section.status] ?? section.items.length}</span></div>
              <div class="zeilen" role="list">
                {#each section.items as item (item.id)}
                  <DubRow {item} {canRevoice} comparing={comparing?.id === item.id}
                          confirm={confirming?.id === item.id ? confirming : null}
                          onOpen={openVideo} onPlay={playDubbed} onCompare={compare} onRevoice={revoiceMenu}
                          onRetry={retry} onMenu={moreMenu} onConfirmClose={() => confirming = null} />
                {/each}
              </div>
            {/each}
            <div use:infiniteScroll={{ onLoadMore: list.loadMore, canLoad: list.canLoad }}></div>
            {#if list.total > list.items.length}
              <div class="fuss tv-schwach tv-klein"><span class="zahl">{list.items.length}</span> von <span class="zahl">{list.total}</span> Aufträgen</div>
            {/if}
          {/if}
        {/if}
      </div>
    </div>

    <div class="tv-rollfeld" data-scroll-root>
      <div class="karte">
        <h3 class="tv-etikett">Nachvertoner</h3>
        {#if overview && !worker.online}
          <div class="hinweis aus">
            <i class="fa-solid fa-plug-circle-xmark"></i>
            <span>Der Rechner mit dem Nachvertoner meldet sich nicht. Wartende Aufträge bleiben liegen, bis er wieder läuft.</span>
          </div>
        {/if}
        <div class="einstellung">
          <div class="name">Zuletzt gemeldet</div>
          <div class="wert">{overview?.worker?.last_seen ? ago(overview.worker.seconds_ago) : 'noch nie'}</div>
        </div>
        <div class="einstellung">
          <div class="name" title="Vorauswahl beim Vormerken: welche Untertitel der Quelle das Transkribieren ersparen dürfen. Je Video änderbar.">Untertitel</div>
          <div class="wechsel" role="group" aria-label="Untertitel als Transkript">
            {#each SUBTITLE_CHOICES as choice (choice.key)}
              <button class:an={subtitles === choice.key} onclick={() => chooseSubtitles(choice.key)} title={choice.title}>{choice.label}</button>
            {/each}
          </div>
        </div>
      </div>

      <VoiceCard choice={voices} onChoose={chooseVoice} />

      <div class="karte">
        <h3 class="tv-etikett">So läuft es</h3>
        <p class="tv-leise tv-klein">Im Video das Sprach-Symbol wählen oder hier "Video vertonen": Zielsprache und Stimme. Ein Rechner mit dem Nachvertoner holt den Auftrag, die fertige Tonspur ist in der Wiedergabe umschaltbar; das Video bleibt unverändert.</p>
      </div>
    </div>
  </div>
</div>

<ActionMenu bind:this={menu} />
<DubDialog bind:this={dubRef} onQueued={reloadAll} />
<VideoPicker bind:this={pickerRef} onPick={pickVideo} />

<style>
  .tv-reiter { margin: 0; }
  .geraet { display: inline-flex; align-items: center; gap: var(--tv-a2); height: 36px; padding: 0 var(--tv-a3);
            border-radius: var(--tv-ecke); background: var(--tv-karte); font-size: var(--tv-gr-klein); white-space: nowrap; }
  .geraet .punkt { width: 10px; height: 10px; border-radius: 50%; background: var(--tv-erfolg); flex: none; }
  .geraet.aus .punkt { background: var(--tv-warnung); }

  .hinweis { display: flex; gap: var(--tv-a3); align-items: center; flex-wrap: wrap; padding: var(--tv-a2) var(--tv-a4);
             margin: calc(-1 * var(--tv-a2)) 0 var(--tv-a3); border-radius: var(--tv-ecke); font-size: var(--tv-gr-klein);
             background: rgba(var(--tv-info-rgb), 0.1); border: 1px solid rgba(var(--tv-info-rgb), 0.3); }
  .hinweis > i { color: var(--tv-info); }
  .hinweis > span { flex: 1 1 280px; min-width: 0; }
  .hinweis.pause { background: rgba(var(--tv-warnung-rgb), 0.1); border-color: rgba(var(--tv-warnung-rgb), 0.35); }
  .hinweis.pause > i { color: var(--tv-warnung); }
  .karte .hinweis.aus { margin: 0 0 var(--tv-a3); align-items: flex-start; padding: var(--tv-a3); }
  .karte .hinweis.aus > i { margin-top: 3px; }

  .liste { container: liste / inline-size; }
  .tag-kopf { display: flex; align-items: baseline; gap: var(--tv-a3); margin: var(--tv-a5) 0 var(--tv-a2); }
  .tag-kopf:first-child { margin-top: var(--tv-a2); }
  .tag-kopf h2 { margin: 0; font-size: var(--tv-gr-titel); }
  .tag-kopf .zahl { color: var(--tv-text-3); font-size: var(--tv-gr-klein); }
  .zeilen { display: flex; flex-direction: column; gap: 2px; }
  .fuss { padding: var(--tv-a3) var(--tv-a2); }

  .leer-gross { padding: 72px var(--tv-a5); text-align: center; color: var(--tv-text-2); }
  .leer-gross i { font-size: 44px; color: var(--tv-text-3); margin-bottom: var(--tv-a4); }
  .leer-gross h2 { margin: 0 0 var(--tv-a2); color: var(--tv-text); }
  .leer-gross p { margin: 0 auto; max-width: 520px; }

  .karte { background: var(--tv-karte); border-radius: var(--tv-ecke); padding: var(--tv-a4); margin-bottom: var(--tv-a3); }
  .karte h3 { margin: 0 0 var(--tv-a3); }
  .karte p { margin: 0; }
  .einstellung { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: var(--tv-a2) var(--tv-a3);
                 padding: var(--tv-a3) var(--tv-a2); }
  .einstellung + .einstellung { border-top: 1px solid var(--tv-rand); }
  .einstellung .name { font-weight: 600; }
  .wechsel { display: inline-flex; background: var(--tv-mulde); border-radius: var(--tv-ecke); padding: 2px; }
  .wechsel button { height: 32px; padding: 0 10px; border: 0; background: none; color: var(--tv-text-2); border-radius: var(--tv-ecke-klein);
                    font: inherit; font-size: var(--tv-gr-klein); cursor: pointer; white-space: nowrap; }
  .wechsel button:hover { color: var(--tv-text); }
  .wechsel button.an { background: var(--tv-karte-3); color: var(--tv-akzent); font-weight: 700; }
</style>

<!--
  Seitenblatt "Alle Einstellungen" eines Kanals (Entwurf mockups/kanaele.html,
  Zustand Einstellungen): Abdeckung mit Medaille und Weg zur nächsten,
  Laden (Auto-Download, Drip mit Menge, Archiv, Qualität, Nur Ton),
  Einordnen (Musikkanal, nie Shorts, Vorschläge), Prüfen, Problem-Videos zum Aufklappen,
  im Fuß Jetzt prüfen, Ganz scannen und Abo beenden.
  Gespeichert wird über die Aktionen der Seite (eine Stelle für alle Wege);
  die Problem-Videos verwaltet das Blatt selbst.
-->
<script>
  import { onMount } from 'svelte';
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';
  import ActionMenu from '../common/ActionMenu.svelte';
  import {
    DRIP_CHOICES, QUICK_QUALITIES, channelName, coverageNote, coverageShare, coverageTitle, dripCount,
    intervalText, medalOf, medalStyle, momentText, num, qualityItems, qualityShort, runText,
  } from './channelView.js';

  let {
    sub,                    // Abo wie aus api.getSubscriptions
    actions,                // Einzel-Aktionen der Seite: setAuto, setDrip, setDripCount, setArchive,
                            // setQuality, setAudioOnly, setMusic, setShortExempt, setSuggest, setEnabled,
                            // checkNow, scanFully, remove, refreshSoon
    checking = false,       // Prüfung dieses Kanals läuft
    showProblems = false,   // Problem-Videos gleich aufgeklappt
    onClose,
  } = $props();

  let menu;
  let problems = $state({ open: false, loading: false, videos: [] });

  let medal = $derived(medalOf(sub));
  let dripChoices = $derived(withCurrent(DRIP_CHOICES, dripCount(sub)).sort((a, b) => a - b));
  let qualityChoices = $derived(withCurrent(QUICK_QUALITIES, sub.download_quality || ''));
  let dripNote = $derived(!sub.drip_enabled ? 'Den Bestand nach und nach laden, nachts'
    : sub.drip_completed_at ? 'Fertig: alles geladen'
    : `Lädt nachts ${dripCount(sub)} Videos${sub.drip_next_run ? `, nächster Lauf ${runText(sub.drip_next_run)}` : ''}`);

  /** Feste Wahl, ergänzt um einen abweichenden aktuellen Wert. */
  function withCurrent(choices, current) {
    return choices.includes(current) ? [...choices] : [...choices, current];
  }

  function moreQualities(event) {
    menu.open(event, 'Qualität', qualityItems(sub.download_quality || '', (value) => actions.setQuality(sub, value)));
  }

  // ── Problem-Videos: dauerhaft gescheiterte Downloads des Kanals ──

  async function toggleProblems() {
    if (problems.open) { problems.open = false; return; }
    problems = { open: true, loading: true, videos: problems.videos };
    try {
      const result = await api.getChannelProblemVideos(sub.channel_id);
      problems = { open: true, loading: false, videos: result.videos || [] };
    } catch (e) {
      toast.error(`Problem-Videos laden fehlgeschlagen: ${e.message}`);
      problems = { open: true, loading: false, videos: [] };
    }
  }

  function forgetProblems(jobIds) {
    problems.videos = problems.videos.filter((v) => !jobIds.includes(v.job_id));
    actions.refreshSoon();
  }

  async function retryProblem(video) {
    try {
      await api.retryDownload(video.job_id);
      toast.success(`"${video.title}" zurück in der Warteschlange`);
      forgetProblems([video.job_id]);
    } catch (e) { toast.error(`Zurück in die Warteschlange fehlgeschlagen: ${e.message}`); }
  }

  async function dismissProblem(video) {
    try {
      await api.cancelDownload(video.job_id);
      toast.info('Problem-Video entfernt');
      forgetProblems([video.job_id]);
    } catch (e) { toast.error(`Entfernen fehlgeschlagen: ${e.message}`); }
  }

  async function retryAllProblems() {
    const done = [];
    try {
      for (const video of problems.videos) {
        await api.retryDownload(video.job_id);
        done.push(video.job_id);
      }
      toast.success(`${num(done.length)} Videos zurück in der Warteschlange`);
    } catch (e) { toast.error(`Erneut versuchen fehlgeschlagen: ${e.message}`); }
    if (done.length) forgetProblems(done);
  }

  /** Fehlertext der Quelle in einem kurzen deutschen Grund. */
  function problemReason(message) {
    if (!message) return 'Unbekannter Fehler';
    const m = message.toLowerCase();
    if (m.includes('members-only') || m.includes('members only')) return 'Nur für Mitglieder';
    if (m.includes('age-restricted') || m.includes('sign in to confirm your age')) return 'Altersbeschränkt';
    if (m.includes('private')) return 'Privat';
    if (m.includes('removed') || m.includes('terminated')) return 'Entfernt';
    if (m.includes('copyright')) return 'Urheberrecht';
    if (m.includes('unavailable')) return 'Nicht verfügbar';
    if (m.includes('retries') || m.includes('retry')) return 'Versuche erschöpft';
    if (m.includes('bot')) return 'Bot-Erkennung';
    return message.substring(0, 80);
  }

  const hideImage = (event) => { event.currentTarget.style.visibility = 'hidden'; };

  onMount(() => {
    if (showProblems && sub.problem_count > 0) toggleProblems();
  });
</script>

{#snippet toggle(on, title, set)}
  <button class="tv-schalter" class:an={on} aria-pressed={!!on} {title} onclick={() => set(!on)}></button>
{/snippet}

<aside class="blatt" aria-label="Einstellungen von {channelName(sub)}">
  <div class="kopf">
    <span class="avatar">
      <span>{channelName(sub)[0]?.toUpperCase()}</span>
      {#if sub.avatar_path}<img src={api.channelAvatarUrl(sub.channel_id)} alt="" onerror={hideImage} />{/if}
    </span>
    <div class="name" title={channelName(sub)}>{channelName(sub)}</div>
    {#if medal}
      <span class="medaille" style={medalStyle(sub)} title={coverageTitle(sub)}><i class="fa-solid fa-medal"></i> {medal.label}</span>
    {/if}
    <button class="tv-knopf ohne symbol klein" onclick={onClose} title="Schließen"><i class="fa-solid fa-xmark"></i></button>
  </div>

  <div class="inhalt">
    <div class="abdeckung" title={coverageTitle(sub)}>
      <div class="balken" style={medalStyle(sub)}><b style:width="{coverageShare(sub) * 100}%"></b></div>
      <span><span class="zahl">{num(sub.have_count)}</span> von <span class="zahl">{num(sub.wanted_count)}</span> geladen</span>
    </div>
    <p class="tv-leise tv-klein">{coverageNote(sub)}</p>

    <h3 class="tv-etikett">Laden</h3>
    <div class="zeilen">
      <div class="zeile">
        <div class="t">Auto-Download<div class="e">Neue Videos sofort laden</div></div>
        {@render toggle(sub.auto_download, 'Neue Videos dieses Kanals automatisch laden', (on) => actions.setAuto(sub, on))}
      </div>
      <div class="zeile">
        <div class="t">Drip<div class="e">{dripNote}</div></div>
        <div class="wahl" role="group" aria-label="Videos je Nacht">
          {#each dripChoices as count (count)}
            <button class:an={dripCount(sub) === count} title="{count} Videos je Nacht" onclick={() => actions.setDripCount(sub, count)}>
              <span class="zahl">{count}</span></button>
          {/each}
        </div>
        {@render toggle(sub.drip_enabled, 'Den vorhandenen Bestand des Kanals nach und nach laden, je Nacht die gewählte Menge', (on) => actions.setDrip(sub, on))}
      </div>
      <div class="zeile">
        <div class="t">Direkt ins Archiv<div class="e">Neu geladene Videos gleich ins Archiv statt in die Bibliothek</div></div>
        {@render toggle(sub.drip_auto_archive, 'Erstmals geladene Videos dieses Kanals landen gleich im Archiv', (on) => actions.setArchive(sub, on))}
      </div>
      <div class="zeile">
        <div class="t">Qualität</div>
        <div class="wahl" role="group" aria-label="Qualität">
          {#each qualityChoices as value (value)}
            <button class:an={(sub.download_quality || '') === value} onclick={() => actions.setQuality(sub, value)}
                    title={value ? `Downloads dieses Kanals in ${qualityShort(value)}` : 'Qualität aus den Einstellungen'}>{qualityShort(value)}</button>
          {/each}
          <button onclick={moreQualities} title="Alle Qualitäten"><i class="fa-solid fa-ellipsis"></i></button>
        </div>
      </div>
      <div class="zeile">
        <div class="t">Nur Ton</div>
        {@render toggle(sub.audio_only, 'Von diesem Kanal nur den Ton laden', (on) => actions.setAudioOnly(sub, on))}
      </div>
    </div>

    <h3 class="tv-etikett">Einordnen</h3>
    <div class="zeilen">
      <div class="zeile">
        <div class="t">Musikkanal<div class="e">Alle Videos zählen als Musik, Ausnahmen einzeln</div></div>
        {@render toggle(sub.music_channel, 'Alle Videos dieses Kanals als Musik führen', (on) => actions.setMusic(sub, on))}
      </div>
      <div class="zeile">
        <div class="t">Nie als Short führen<div class="e">Kurze, aber vollwertige Videos bleiben Videos</div></div>
        {@render toggle(sub.short_exempt, 'Videos dieses Kanals nie als Short führen; beim Abschalten bleiben bestehende Videos Videos', (on) => actions.setShortExempt(sub, on))}
      </div>
      <div class="zeile">
        <div class="t">In Vorschlägen<div class="e">Videos tauchen im Zufallsvorschlag auf</div></div>
        {@render toggle(!sub.suggest_exclude, 'Videos dieses Kanals im Zufallsvorschlag zeigen; beim Einschalten entfallen die Ausnahmen einzelner Videos', (on) => actions.setSuggest(sub, on))}
      </div>
    </div>

    <h3 class="tv-etikett">Prüfen</h3>
    <div class="zeilen">
      <div class="zeile">
        <div class="t">Prüfung an
          <div class="e" title="Der Prüfabstand richtet sich nach dem Alter des neuesten Videos">
            {#if sub.last_checked}Zuletzt geprüft <span class="zahl">{momentText(sub.last_checked)}</span>{:else}Noch nie geprüft{/if}{#if sub.check_interval}, alle <span class="zahl">{intervalText(sub.check_interval)}</span>{/if}
          </div>
        </div>
        {@render toggle(sub.enabled, 'Kanal auf neue Videos prüfen; abgeschaltet lädt er auch nichts', (on) => actions.setEnabled(sub, on))}
      </div>
    </div>
    {#if sub.error_count > 0}
      <p class="tv-fehlertext" title={sub.last_error || ''}>
        <i class="fa-solid fa-triangle-exclamation"></i>
        <span><span class="zahl">{num(sub.error_count)}</span> Fehler in Folge{#if sub.last_error}: {sub.last_error}{/if}</span>
      </p>
    {/if}

    {#if sub.problem_count > 0}
      <h3 class="tv-etikett">Probleme</h3>
      <button class="aufklappen" onclick={toggleProblems} aria-expanded={problems.open}
              title="Videos, die wegen dauerhafter Fehler nicht geladen wurden">
        <i class="fa-solid {problems.open ? 'fa-chevron-down' : 'fa-chevron-right'}"></i>
        <span><span class="zahl">{num(sub.problem_count)}</span> {sub.problem_count === 1 ? 'Video ließ' : 'Videos ließen'} sich nicht laden</span>
      </button>
      {#if problems.open}
        {#if problems.loading}
          <p class="tv-schwach"><i class="fa-solid fa-spinner fa-spin"></i> Lädt ...</p>
        {:else if !problems.videos.length}
          <p class="tv-schwach">Keine Problem-Videos mehr.</p>
        {:else}
          <button class="tv-knopf klein alle" onclick={retryAllProblems} title="Alle Problem-Videos zurück in die Warteschlange">
            <i class="fa-solid fa-rotate-right"></i> Alle erneut versuchen</button>
          <ul class="probleme">
            {#each problems.videos as video (video.job_id)}
              <li>
                <img src={api.rssThumbUrl(video.video_id)} alt="" loading="lazy" onerror={hideImage} />
                <div class="p-text">
                  <a href={video.url} target="_blank" rel="noopener" title={video.title}>{video.title || video.video_id}</a>
                  <span class="grund" title={video.error_message || ''}>{problemReason(video.error_message)}</span>
                </div>
                <button class="tv-knopf ohne symbol klein" onclick={() => retryProblem(video)} title="Erneut versuchen">
                  <i class="fa-solid fa-rotate-right"></i></button>
                <button class="tv-knopf ohne symbol klein" onclick={() => dismissProblem(video)} title="Aus der Warteschlange entfernen">
                  <i class="fa-solid fa-xmark"></i></button>
              </li>
            {/each}
          </ul>
        {/if}
      {/if}
    {/if}
  </div>

  <div class="fuss">
    <button class="tv-knopf" onclick={() => actions.checkNow(sub)} disabled={checking} title="Diesen Kanal jetzt auf neue Videos prüfen">
      <i class="fa-solid fa-rotate" class:fa-spin={checking}></i> Jetzt prüfen</button>
    <button class="tv-knopf" onclick={() => actions.scanFully(sub)}
            title="Alle Videos des Kanals einlesen, nicht nur die neuesten. Erst danach gibt es eine Medaille.">
      <i class="fa-solid fa-satellite-dish"></i> Ganz scannen</button>
    <button class="tv-knopf ohne gefahr beenden" onclick={() => actions.remove(sub)}>
      <i class="fa-solid fa-xmark"></i> Abo beenden</button>
  </div>
</aside>

<ActionMenu bind:this={menu} />

<style>
  /* Linien zwischen Kopf, Inhalt und Fuß entstehen aus dem Abstand auf der Randfarbe */
  .blatt { position: absolute; top: 0; right: 0; bottom: 0; z-index: 8; width: min(420px, 100%);
           display: flex; flex-direction: column; gap: 1px; background: var(--tv-rand-stark);
           border: 1px solid var(--tv-rand-stark); box-shadow: var(--tv-schatten); }
  .kopf, .inhalt, .fuss { background: var(--tv-karte); }

  .kopf { display: flex; gap: var(--tv-a3); align-items: center; padding: var(--tv-a4); }
  .avatar { position: relative; flex: none; width: 48px; height: 48px; display: grid; place-items: center; overflow: hidden;
            border-radius: var(--tv-ecke); background: var(--tv-mulde); color: var(--tv-akzent); font-weight: 700; font-size: var(--tv-gr-titel); }
  .avatar img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
  .name { flex: 1; min-width: 0; font-weight: 700; font-size: 19px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .medaille { flex: none; display: inline-flex; align-items: center; gap: 5px; height: 26px; padding: 0 8px; border-radius: var(--tv-ecke-klein);
              font-size: var(--tv-gr-marke); font-weight: 700; letter-spacing: 0.04em; background: var(--medaille-grund); color: var(--medaille); }

  .inhalt { flex: 1; min-height: 0; overflow-y: auto; overflow-x: hidden; padding: var(--tv-a3) var(--tv-a4) var(--tv-a4); }
  .inhalt > p { margin: var(--tv-a2) 0 0; }
  .abdeckung { display: flex; align-items: center; gap: var(--tv-a3); font-size: var(--tv-gr-klein); color: var(--tv-text-2); }
  .abdeckung .zahl { color: var(--tv-text); font-weight: 600; }
  .balken { flex: 1; height: 6px; background: var(--tv-mulde); border-radius: 1px; overflow: hidden; }
  .balken b { display: block; height: 100%; background: var(--medaille, var(--tv-akzent)); }

  h3.tv-etikett { margin: var(--tv-a5) 0 var(--tv-a2); }
  /* Trennlinien zwischen den Zeilen: 1 px Abstand auf der Randfarbe */
  .zeilen { display: flex; flex-direction: column; gap: 1px; background: var(--tv-rand); }
  .zeile { display: flex; align-items: center; gap: var(--tv-a3); padding: 10px 0; background: var(--tv-karte); }
  .zeile .t { flex: 1; min-width: 0; }
  .zeile .e { font-size: var(--tv-gr-klein); color: var(--tv-text-3); }
  .wahl { display: inline-flex; flex-wrap: wrap; justify-content: flex-end; padding: 2px; background: var(--tv-mulde); border-radius: var(--tv-ecke); }
  .wahl button { height: 30px; min-width: 30px; padding: 0 10px; border: 0; background: none; color: var(--tv-text-2); border-radius: var(--tv-ecke-klein);
                 cursor: pointer; font: inherit; font-size: var(--tv-gr-klein); }
  .wahl button:hover { color: var(--tv-text); }
  .wahl button.an { background: var(--tv-karte-3); color: var(--tv-akzent); font-weight: 700; }
  .tv-fehlertext { margin-top: var(--tv-a2); }
  .tv-fehlertext span { display: -webkit-box; -webkit-line-clamp: 3; line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }

  .aufklappen { display: flex; align-items: center; gap: var(--tv-a2); width: 100%; padding: var(--tv-a2); border: 0; border-radius: var(--tv-ecke);
                background: rgba(var(--tv-warnung-rgb), 0.1); color: var(--tv-warnung); font: inherit; text-align: left; cursor: pointer; }
  .aufklappen:hover { background: rgba(var(--tv-warnung-rgb), 0.16); }
  .alle { margin: var(--tv-a2) 0; }
  .probleme { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
  .probleme li { display: flex; align-items: center; gap: var(--tv-a2); padding: 4px; border-radius: var(--tv-ecke); }
  .probleme li:hover { background: var(--tv-karte-2); }
  .probleme img { width: 64px; aspect-ratio: 16 / 9; flex: none; object-fit: cover; border-radius: var(--tv-ecke-klein); background: var(--tv-mulde); }
  .p-text { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .p-text a { color: var(--tv-text); font-size: var(--tv-gr-klein); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .p-text a:hover { color: var(--tv-akzent); }
  .grund { font-size: var(--tv-gr-marke); color: var(--tv-warnung); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  .fuss { display: flex; flex-wrap: wrap; gap: var(--tv-a2); padding: var(--tv-a3) var(--tv-a4); }
  .beenden { margin-left: auto; }
</style>

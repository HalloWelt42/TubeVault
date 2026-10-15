<!--
  Eigene Videos: die gewählte Datei im Vergleich mit ihrem Treffer und was
  damit geschehen soll (Gestaltung nach mockups/eigene-videos.html).
  Tasten: 1 löschen, 2 zuordnen, 3 eigenem Kanal, 4 überspringen.
-->
<script>
  import { untrack } from 'svelte';
  import { api } from '../../api/client.js';
  import { navigate } from '../../router/router.js';
  import { formatDuration, formatSize } from '../../utils/format.js';
  import { FINDING, DECISIONS, reasonText } from './ownStatus.js';

  let {
    file,
    channels = [],
    working = false,
    onDelete = () => {},
    onAdopt = () => {},        // (videoId | null)
    onAssign = () => {},       // (channelName, channelId, title)
    onReplace = () => {},
    onSkip = () => {},
    onReopen = () => {},
  } = $props();

  let m = $derived(file.match);
  let finding = $derived(FINDING[file.finding] || FINDING.unknown);
  let decided = $derived(file.decision !== 'open');
  let inLibrary = $derived(Boolean(m?.in_library));
  let sourceKnown = $derived(Boolean(m && !m.in_library));

  // Unterformulare: eigenem Kanal zuordnen, anderem Video zuordnen
  let mode = $state(null);           // null | 'kanal' | 'suche'
  let channelName = $state('');
  let title = $state('');
  let query = $state('');
  let results = $state([]);
  let searching = $state(false);
  let playing = $state(false);

  $effect(() => {
    // Nur eine andere Datei setzt die Formulare zurück - nicht das Nachladen
    // derselben Datei oder der Kanalliste (sonst ginge Getipptes verloren)
    file.id;
    untrack(() => {
      mode = null;
      playing = false;
      results = [];
      query = '';
      title = file.title || '';
      channelName = channels.find(c => c.channel_id === file.channel_id_hint)?.channel_name || file.channel_hint || '';
    });
  });

  let suggestions = $derived.by(() => {
    const typed = channelName.trim().toLowerCase();
    const list = typed ? channels.filter(c => (c.channel_name || '').toLowerCase().includes(typed)) : channels;
    return list.slice(0, 8);
  });
  let exact = $derived(channels.find(c => (c.channel_name || '').toLowerCase() === channelName.trim().toLowerCase()));

  function assign() {
    if (!channelName.trim()) return;
    onAssign(exact?.channel_name || channelName.trim(), exact?.channel_id || null, title.trim() || null);
  }

  let timer;
  function search() {
    clearTimeout(timer);
    if (query.trim().length < 2) { results = []; return; }
    timer = setTimeout(async () => {
      searching = true;
      try { results = await api.ownLookup(query.trim()); } catch { results = []; }
      searching = false;
    }, 300);
  }

  function openMode(next) {
    mode = mode === next ? null : next;
    if (mode === 'suche' && !query) { query = title; search(); }
  }

  /** Tasten 1-4 aus der Seite */
  export function press(key) {
    if (decided || working) return;
    if (key === '1') onDelete();
    else if (key === '2') sourceKnown ? onAdopt(null) : openMode('suche');
    else if (key === '3') openMode('kanal');
    else if (key === '4') onSkip();
  }

  const facts = (d, size, w, h) => [d ? formatDuration(d) : null, size ? formatSize(size) : null, h ? `${h}p` : null]
    .filter(Boolean).join(' · ');
  let sameDuration = $derived(m?.duration && file.duration && Math.abs(m.duration - file.duration) <= 2);
  let sameSize = $derived(m?.size && file.size && m.size === file.size);
</script>

<section class="tv-karte">
  <h3><i class="fa-solid {inLibrary ? 'fa-copy' : sourceKnown ? 'fa-circle-check' : 'fa-circle-question'}"
         style:color={finding.farbe}></i> {decided ? `Erledigt: ${DECISIONS[file.decision]}` : finding.label}</h3>
  <div class="vergleich">
    <div class="haelfte">
      <span class="tv-etikett">Alte Datei</span>
      <div class="bild">
        {#if playing}
          <!-- svelte-ignore a11y_media_has_caption -->
          <video src={api.ownFileMediaUrl(file.id)} controls autoplay></video>
        {:else}
          <button class="abspielen" onclick={() => playing = true} title="Datei ansehen">
            {#if file.has_thumbnail}<img src={api.ownFileThumbUrl(file.id)} alt="" />{:else}<i class="fa-solid fa-film fa-2x"></i>{/if}
            <i class="fa-solid fa-play spielen"></i>
          </button>
        {/if}
      </div>
      <span class="titel">{file.title || file.name}</span>
      <span class="tv-schwach tv-klein ort" title={file.rel_path}>{file.folder || 'Sammlung'}</span>
      <span class="zahl tv-klein" class:gleich={sameDuration}>{facts(file.duration, file.size, file.width, file.height)}</span>
    </div>
    <div class="haelfte">
      <span class="tv-etikett">{inLibrary ? 'In der Bibliothek' : sourceKnown ? 'Bei der Quelle bekannt' : 'Treffer'}</span>
      {#if m}
        <div class="bild"><img src={inLibrary ? api.thumbnailUrl(m.video_id) : api.rssThumbUrl(m.video_id)} alt=""
                               onerror={(e) => e.target.style.visibility = 'hidden'} /></div>
        <span class="titel">{m.title || m.video_id}</span>
        <span class="tv-schwach tv-klein">{m.channel_name || ''}</span>
        <span class="zahl tv-klein" class:gleich={sameDuration}>{facts(m.duration, m.size)}{#if sameSize}{' · '}gleiche Größe{/if}</span>
      {:else}
        <div class="bild leer"><i class="fa-solid fa-magnifying-glass fa-2x"></i></div>
        <span class="tv-leise tv-klein">{file.finding === 'pending' ? 'Wird gerade geprüft.' : 'Kein passendes Video gefunden.'}</span>
      {/if}
    </div>
  </div>
  {#if reasonText(file)}<p class="tv-leise tv-klein grund">{reasonText(file)}</p>{/if}
</section>

<section class="tv-karte">
  <h3><i class="fa-solid fa-hand-pointer"></i> Was tun?</h3>
  {#if decided}
    {#if file.decision === 'skipped'}
      <button class="tv-knopf" onclick={onReopen} disabled={working}><i class="fa-solid fa-rotate-left"></i> Wieder zum Einordnen anbieten</button>
    {:else if file.result_video_id}
      <button class="tv-knopf" onclick={() => navigate(`/watch/${file.result_video_id}`)}><i class="fa-solid fa-play"></i> Video ansehen</button>
    {/if}
  {:else}
    <div class="wahl">
      {#if inLibrary}
        <button class="tv-knopf haupt" onclick={onDelete} disabled={working}><i class="fa-solid fa-trash-can"></i> Alte Datei löschen <kbd>1</kbd></button>
        <button class="tv-knopf" onclick={onReplace} disabled={working}
                title="Die alte Datei kommt in die Bibliothek, die bisherige Datei dort wird gelöscht">
          <i class="fa-solid fa-right-left"></i> Datei in der Bibliothek ersetzen</button>
        <button class="tv-knopf" onclick={() => openMode('suche')} disabled={working}><i class="fa-solid fa-link"></i> Anderem Video zuordnen <kbd>2</kbd></button>
      {:else if sourceKnown}
        <button class="tv-knopf" class:haupt={file.finding === 'certain'} onclick={() => onAdopt(null)} disabled={working}>
          <i class="fa-solid fa-file-import"></i> In die Bibliothek übernehmen <kbd>2</kbd></button>
        <button class="tv-knopf" onclick={() => openMode('suche')} disabled={working}><i class="fa-solid fa-link"></i> Anderem Video zuordnen</button>
        <button class="tv-knopf" onclick={onDelete} disabled={working}><i class="fa-solid fa-trash-can"></i> Alte Datei löschen <kbd>1</kbd></button>
      {:else}
        <button class="tv-knopf" onclick={() => openMode('suche')} disabled={working}><i class="fa-solid fa-link"></i> Einem Video zuordnen <kbd>2</kbd></button>
        <button class="tv-knopf" onclick={onDelete} disabled={working}><i class="fa-solid fa-trash-can"></i> Alte Datei löschen <kbd>1</kbd></button>
      {/if}
      <button class="tv-knopf" class:haupt={!m} onclick={() => openMode('kanal')} disabled={working}>
        <i class="fa-solid fa-user-plus"></i> Eigenem Kanal zuordnen <kbd>3</kbd></button>
      <button class="tv-knopf ohne" onclick={onSkip} disabled={working}><i class="fa-solid fa-forward"></i> Überspringen <kbd>4</kbd></button>
    </div>

    {#if mode === 'kanal'}
      <div class="formular">
        <label class="tv-klein tv-leise" for="eigen-kanal">Kanal wählen oder neu anlegen</label>
        <input id="eigen-kanal" class="tv-eingabe" bind:value={channelName} placeholder="z.B. Werbespots"
               onkeydown={(e) => e.key === 'Enter' && assign()} />
        {#if suggestions.length && !exact}
          <div class="vorschlaege">
            {#each suggestions as c (c.channel_id)}
              <button class="tv-chip" onclick={() => channelName = c.channel_name}>
                <i class="fa-solid {c.kind === 'abo' ? 'fa-satellite-dish' : 'fa-folder'}"></i> {c.channel_name}</button>
            {/each}
          </div>
        {/if}
        <label class="tv-klein tv-leise" for="eigen-titel">Titel</label>
        <input id="eigen-titel" class="tv-eingabe" bind:value={title} onkeydown={(e) => e.key === 'Enter' && assign()} />
        <button class="tv-knopf haupt" onclick={assign} disabled={working || !channelName.trim()}>
          <i class="fa-solid fa-check"></i> {exact ? `Zu ${exact.channel_name}` : `Neuer Kanal ${channelName.trim() || ''}`}</button>
      </div>
    {:else if mode === 'suche'}
      <div class="formular">
        <input class="tv-eingabe" bind:value={query} oninput={search} placeholder="Titel in Bibliothek und Feed suchen" />
        {#if searching}<span class="tv-schwach tv-klein"><i class="fa-solid fa-spinner fa-spin"></i> sucht ...</span>{/if}
        {#each results as r (r.id)}
          <button class="treffer" onclick={() => r.in_library ? null : onAdopt(r.id)} disabled={working || r.in_library}
                  title={r.in_library ? 'Liegt schon in der Bibliothek - dann ist die alte Datei doppelt' : 'Als dieses Video übernehmen'}>
            <span class="t">{r.title}</span>
            <span class="tv-schwach tv-klein">{r.channel_name || ''}{r.duration ? ' · ' + formatDuration(r.duration) : ''}{r.in_library ? ' · in der Bibliothek' : ''}</span>
          </button>
        {:else}
          {#if query.trim().length >= 2 && !searching}<span class="tv-schwach tv-klein">Nichts gefunden.</span>{/if}
        {/each}
      </div>
    {/if}
  {/if}
</section>

<style>
  .vergleich { display: grid; grid-template-columns: 1fr 1fr; gap: var(--tv-a3); }
  .haelfte { display: flex; flex-direction: column; gap: 6px; min-width: 0; font-size: var(--tv-gr-klein); }
  .bild { aspect-ratio: 16 / 9; background: var(--tv-mulde); border-radius: var(--tv-ecke-klein); overflow: hidden;
          display: grid; place-items: center; color: var(--tv-text-3); }
  .bild img, .bild video { width: 100%; height: 100%; object-fit: cover; display: block; }
  .bild video { object-fit: contain; background: #000; }
  .abspielen { position: relative; width: 100%; height: 100%; padding: 0; border: 0; background: none; cursor: pointer;
               display: grid; place-items: center; color: var(--tv-text-3); }
  .abspielen .spielen { position: absolute; opacity: 0; color: var(--tv-text); font-size: 26px; transition: opacity var(--tv-schnell); }
  .abspielen:hover .spielen { opacity: 0.9; }
  .titel { font-weight: 600; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; }
  .ort { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .gleich { color: var(--tv-erfolg); }
  .grund { margin: var(--tv-a3) 0 0; }
  .wahl { display: flex; flex-direction: column; gap: var(--tv-a2); }
  .wahl .tv-knopf { justify-content: flex-start; width: 100%; height: 46px; }
  .wahl kbd { margin-left: auto; }
  kbd { font-family: var(--tv-schrift-zahl); font-size: 13px; background: var(--tv-karte-2); border-radius: var(--tv-ecke-klein);
        padding: 1px 6px; color: var(--tv-text); }
  .formular { display: flex; flex-direction: column; gap: var(--tv-a2); margin-top: var(--tv-a3); }
  .vorschlaege { display: flex; gap: var(--tv-a1); flex-wrap: wrap; }
  .treffer { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; padding: var(--tv-a2) var(--tv-a3);
             background: var(--tv-karte); border: 1px solid var(--tv-rand); border-radius: var(--tv-ecke);
             color: var(--tv-text); font: inherit; text-align: left; cursor: pointer; }
  .treffer:hover:not(:disabled) { border-color: rgba(var(--tv-akzent-rgb), 0.55); }
  .treffer:disabled { opacity: 0.6; cursor: default; }
  .treffer .t { font-weight: 600; }
</style>

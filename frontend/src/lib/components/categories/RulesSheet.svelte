<!--
  Seitenblatt "Regeln" einer Kategorie (Entwurf mockups/kategorien.html,
  Zustand regeln): Regeln "Kanal ist", "Schlagwort enthält", "Inhaltlich wie"
  (mit Genauigkeit), Vorschau mit Zahl der passenden und neuen Videos samt
  Beispielen, Farbe aus festen Feldern. Auch für einen Vorschlag aus
  "Themen erkennen" (ohne Kategorie, Name änderbar, Knopf "Übernehmen").
  Gespeichert wird über onSave der Seite.
-->
<script>
  import { tick, untrack } from 'svelte';
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';
  import { RULE_KINDS, kindOf, rulesForSave, saveLabel } from '../../utils/categoryRules.js';
  import ActionMenu from '../common/ActionMenu.svelte';

  let {
    title,
    categoryId = null,       // null: Entwurf einer neuen Kategorie
    rules = [],              // [{ kind, value, label?, precision? }]
    color,
    colors = [],
    ai,                      // { semantic, precisions: [{ key, label }], default_precision }
    name = null,             // Entwurf: Name änderbar
    acceptLabel = null,      // statt "Speichern ..."
    onSave,                  // async ({ rules, color, name }) => void
    onClose,
  } = $props();

  let seq = 0;
  const draftOf = (rule) => ({
    key: ++seq, kind: rule.kind, value: rule.value || '', label: rule.label || '',
    query: rule.kind === 'channel' ? (rule.label || '') : '', precision: rule.precision || null,
  });

  let drafts = $state(untrack(() => rules.map(draftOf)));
  let chosenColor = $state(untrack(() => color));
  let draftName = $state(untrack(() => name || ''));
  let preview = $state(null);
  let previewError = $state('');
  let previewing = $state(false);
  let saving = $state(false);
  let choices = $state({ key: null, items: [] });   // Kanäle zur Eingabe einer Regel
  let menu;
  let content;
  let previewTimer = null;
  let channelTimer = null;
  let ticket = 0;

  let payload = $derived(rulesForSave(drafts));
  let kinds = $derived(RULE_KINDS.filter((k) => k.kind !== 'semantic' || ai?.semantic));
  let isDraft = $derived(categoryId === null);
  // Treffer je Regel (Hover): die Vorschau zählt nur ausgefüllte Regeln
  let filled = $derived(drafts.filter((d) => String(d.value).trim()).map((d) => d.key));

  // Vorschau neu, sobald sich die Regeln ändern (verzögert, nur die letzte Antwort zählt)
  $effect(() => {
    const body = JSON.stringify(payload);
    untrack(() => {
      clearTimeout(previewTimer);
      previewTimer = setTimeout(() => loadPreview(JSON.parse(body)), 350);
    });
  });

  async function loadPreview(list) {
    const mine = ++ticket;
    previewing = true;
    try {
      const result = await api.previewCategoryRules(categoryId, list);
      if (mine === ticket) { preview = result; previewError = ''; }
    } catch (e) {
      if (mine === ticket) { preview = null; previewError = e.message; }
    } finally {
      if (mine === ticket) previewing = false;
    }
  }

  function countOf(draft) {
    const index = filled.indexOf(draft.key);
    const counts = preview?.per_rule;
    if (index < 0 || !counts || counts.length !== filled.length) return '';
    return `Passt auf ${counts[index].toLocaleString('de-DE')} Videos`;
  }

  // ── Regeln ändern ──
  async function addRule(kind) {
    const draft = draftOf({ kind, precision: kind === 'semantic' ? ai?.default_precision : null });
    drafts.push(draft);
    await tick();
    content?.querySelector(`[data-regel="${draft.key}"]`)?.focus();
    if (kind === 'channel') loadChannels(drafts[drafts.length - 1], '');
  }

  function changeKind(draft, kind) {
    if (draft.kind === kind) return;
    Object.assign(draft, { kind, value: '', label: '', query: '',
                           precision: kind === 'semantic' ? (draft.precision || ai?.default_precision) : null });
  }

  function kindMenu(event, draft = null) {
    menu.open(event, draft ? 'Regel ändern' : 'Regel hinzufügen', kinds.map((k) => ({
      icon: k.icon, label: k.label, run: () => (draft ? changeKind(draft, k.kind) : addRule(k.kind)),
    })));
  }

  function removeRule(draft) {
    drafts = drafts.filter((d) => d.key !== draft.key);
  }

  // ── Kanal wählen ──
  function onChannelInput(draft, text) {
    draft.query = text;
    draft.value = '';
    draft.label = '';
    clearTimeout(channelTimer);
    channelTimer = setTimeout(() => loadChannels(draft, text), 250);
  }

  async function loadChannels(draft, text) {
    try {
      const items = await api.getCategoryChannels(text.trim());
      choices = { key: draft.key, items };
    } catch { choices = { key: null, items: [] }; }
  }

  function pickChannel(draft, channel) {
    Object.assign(draft, { value: channel.channel_id, label: channel.name, query: channel.name });
    choices = { key: null, items: [] };
  }

  // ── Speichern ──
  async function save() {
    saving = true;
    try {
      await onSave({ rules: payload, color: chosenColor, name: draftName.trim() });
    } catch (e) {
      toast.error(e.message);
    } finally {
      saving = false;
    }
  }

  const hideImage = (event) => { event.currentTarget.style.visibility = 'hidden'; };
</script>

<aside class="blatt" aria-label={title}>
  <div class="kopf">
    <span class="n">{title}</span>
    <button class="tv-knopf ohne symbol klein" onclick={onClose} title="Schließen"><i class="fa-solid fa-xmark"></i></button>
  </div>

  <div class="inhalt" bind:this={content}>
    {#if isDraft}
      <h3 class="tv-etikett">Name</h3>
      <input class="tv-eingabe" bind:value={draftName} maxlength="80" placeholder="Name der Kategorie" />
    {/if}
    <p class="tv-leise tv-klein">Ein Video kommt hinein, wenn eine Regel passt. Von Hand Hinzugefügtes und Entferntes bleibt so.</p>

    <h3 class="tv-etikett">Regeln</h3>
    {#each drafts as draft (draft.key)}
      {@const kind = kindOf(draft.kind)}
      <div class="regel-zeile" title={countOf(draft)}>
        <button class="art" class:bedeutung={draft.kind === 'semantic'} onclick={(e) => kindMenu(e, draft)} title="{kind.hint} - Art ändern">
          <i class="fa-solid {kind.icon}"></i> <span>{kind.label}</span> <i class="fa-solid fa-chevron-down pfeil"></i></button>
        {#if draft.kind === 'channel'}
          <input class="tv-eingabe" data-regel={draft.key} value={draft.query} placeholder={kind.placeholder}
                 oninput={(e) => onChannelInput(draft, e.currentTarget.value)}
                 onfocus={() => { if (!draft.value) loadChannels(draft, draft.query); }}
                 class:offen={!draft.value} title={draft.value ? countOf(draft) : 'Kanal aus der Liste wählen'} />
        {:else}
          <input class="tv-eingabe" data-regel={draft.key} bind:value={draft.value} placeholder={kind.placeholder}
                 maxlength={draft.kind === 'tag' ? 60 : 200} title={draft.kind === 'semantic' ? draft.value : null} />
        {/if}
        <button class="tv-knopf ohne symbol klein" onclick={() => removeRule(draft)} title="Regel entfernen"><i class="fa-solid fa-xmark"></i></button>

        {#if draft.kind === 'channel' && choices.key === draft.key && !draft.value}
          <div class="treffer">
            {#each choices.items as channel (channel.channel_id)}
              <button onclick={() => pickChannel(draft, channel)}>
                <span class="t">{channel.name}</span><span class="zahl tv-schwach">{channel.count.toLocaleString('de-DE')}</span></button>
            {:else}
              <span class="tv-schwach tv-klein">Kein Kanal gefunden</span>
            {/each}
          </div>
        {/if}
        {#if draft.kind === 'semantic' && ai?.precisions?.length}
          <div class="genau" title="Wie eng &quot;Inhaltlich wie&quot; fasst: Weit nimmt auch lose Verwandtes auf, Sehr genau nur eng Passendes">
            {#each ai.precisions as level (level.key)}
              <button class:an={(draft.precision || ai.default_precision) === level.key} onclick={() => draft.precision = level.key}>{level.label}</button>
            {/each}
          </div>
        {/if}
      </div>
    {/each}
    <button class="tv-knopf klein ohne hinzu" onclick={(e) => kindMenu(e)}><i class="fa-solid fa-plus"></i> Regel hinzufügen</button>

    <h3 class="tv-etikett">Vorschau</h3>
    <div class="vorschau">
      {#if previewError}
        <div class="tv-fehlertext"><i class="fa-solid fa-circle-exclamation"></i> <span>{previewError}</span></div>
      {:else if !payload.length}
        <span class="tv-leise">Ohne Regel kommt nur hinein, was von Hand hineingelegt wird.</span>
      {:else if preview}
        <div class:veraltet={previewing}>
          <b class="zahl">{preview.matching.toLocaleString('de-DE')}</b> {preview.matching === 1 ? 'Video passt' : 'Videos passen'}{#if !isDraft},
            davon <b class="zahl">{preview.new.toLocaleString('de-DE')}</b> neu für diese Kategorie{/if}{#if preview.leaving};
            <b class="zahl">{preview.leaving.toLocaleString('de-DE')}</b> {preview.leaving === 1 ? 'fällt' : 'fallen'} heraus{/if}
        </div>
        {#if preview.semantic_missing}
          <div class="tv-fehlertext"><i class="fa-solid fa-circle-exclamation"></i> <span>"Inhaltlich wie" trifft gerade nichts Neues: die Bedeutungssuche ist nicht erreichbar. Bisher Eingeordnetes bleibt.</span></div>
        {/if}
        {#if preview.samples.length}
          <div class="beispiele">
            {#each preview.samples as video (video.id)}
              <div class="mini">
                <img src={api.thumbnailUrl(video.id)} alt="" loading="lazy" onerror={hideImage} />
                <span><span class="t">{video.title}</span><span class="tv-schwach tv-klein">{video.channel_name || ''}</span></span>
              </div>
            {/each}
          </div>
        {/if}
      {:else}
        <span class="tv-leise"><i class="fa-solid fa-spinner fa-spin"></i> Wird gezählt ...</span>
      {/if}
    </div>

    <h3 class="tv-etikett">Aussehen</h3>
    <div class="farben" role="group" aria-label="Farbe">
      {#each colors as c (c)}
        <button class="farbe" class:an={chosenColor === c} style:background={c} onclick={() => chosenColor = c} aria-label="Farbe {c}"></button>
      {/each}
    </div>
  </div>

  <div class="fuss">
    <button class="tv-knopf haupt" onclick={save} disabled={saving || (isDraft && !draftName.trim())}>
      <i class="fa-solid {saving ? 'fa-spinner fa-spin' : 'fa-check'}"></i> {acceptLabel || saveLabel(preview)}</button>
    <button class="tv-knopf ohne" onclick={onClose}>Abbrechen</button>
  </div>
</aside>

<ActionMenu bind:this={menu} />

<style>
  /* Linien zwischen Kopf, Inhalt und Fuß entstehen aus dem Abstand auf der Randfarbe */
  .blatt { position: absolute; top: 0; right: 0; bottom: 0; z-index: 8; width: min(470px, 100%);
           display: flex; flex-direction: column; gap: 1px; background: var(--tv-rand-stark);
           border: 1px solid var(--tv-rand-stark); box-shadow: var(--tv-schatten); }
  .kopf, .inhalt, .fuss { background: var(--tv-karte); }
  .kopf { display: flex; gap: var(--tv-a3); align-items: center; padding: var(--tv-a4); background: var(--tv-karte-2); }
  .kopf .n { flex: 1; min-width: 0; font-weight: 700; font-size: 19px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .inhalt { flex: 1; min-height: 0; overflow-y: auto; overflow-x: hidden; padding: var(--tv-a3) var(--tv-a4) var(--tv-a4);
            display: flex; flex-direction: column; gap: var(--tv-a3); }
  .inhalt > * { flex-shrink: 0; }
  .inhalt p { margin: 0; }
  h3.tv-etikett { margin: var(--tv-a2) 0 0; }

  .regel-zeile { display: grid; grid-template-columns: 190px minmax(0, 1fr) 34px; gap: var(--tv-a2); align-items: center; }
  .art { display: flex; align-items: center; gap: 8px; height: 40px; padding: 0 10px; min-width: 0; cursor: pointer;
         background: var(--tv-mulde); color: var(--tv-text); border: 1px solid var(--tv-rand); border-radius: var(--tv-ecke);
         font: inherit; font-size: var(--tv-gr-klein); text-align: left; }
  .art:hover { border-color: var(--tv-rand-stark); }
  .art span { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .art i { color: var(--tv-text-3); }
  .art.bedeutung i:first-child { color: var(--tv-bedeutung); }
  .art .pfeil { font-size: 13px; }
  .regel-zeile .tv-eingabe { width: 100%; min-width: 0; background: var(--tv-mulde); }
  .regel-zeile .tv-eingabe.offen { border-color: rgba(var(--tv-warnung-rgb), 0.5); }
  .treffer { grid-column: 2 / 4; }
  .genau { grid-column: 1 / -1; justify-self: end; }
  .treffer { display: flex; flex-direction: column; gap: 1px; max-height: 260px; overflow-y: auto; padding: 4px;
             background: var(--tv-mulde); border-radius: var(--tv-ecke); }
  .treffer button { display: flex; align-items: center; gap: var(--tv-a2); padding: 7px 8px; border: 0; background: none; cursor: pointer;
                    color: var(--tv-text); font: inherit; font-size: var(--tv-gr-klein); text-align: left; border-radius: var(--tv-ecke-klein); }
  .treffer button:hover { background: var(--tv-karte-2); }
  .treffer .t { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .treffer > span { padding: 6px 8px; }
  .genau { display: inline-flex; flex-wrap: wrap; padding: 2px; background: var(--tv-mulde); border-radius: var(--tv-ecke); }
  .genau button { height: 30px; padding: 0 10px; border: 0; background: none; color: var(--tv-text-2); border-radius: var(--tv-ecke-klein);
                  cursor: pointer; font: inherit; font-size: var(--tv-gr-klein); }
  .genau button:hover { color: var(--tv-text); }
  .genau button.an { background: var(--tv-karte-3); color: var(--tv-bedeutung); font-weight: 700; }
  .hinzu { align-self: flex-start; }

  .vorschau { padding: var(--tv-a3); background: rgba(var(--tv-akzent-rgb), 0.07); border: 1px solid rgba(var(--tv-akzent-rgb), 0.35);
              border-radius: var(--tv-ecke); font-size: var(--tv-gr-klein); display: flex; flex-direction: column; gap: var(--tv-a2); }
  .veraltet { opacity: 0.6; }
  .beispiele { display: flex; flex-direction: column; gap: 4px; }
  .mini { display: grid; grid-template-columns: 96px minmax(0, 1fr); gap: var(--tv-a2); align-items: center; }
  .mini img { width: 96px; aspect-ratio: 16 / 9; object-fit: cover; border-radius: var(--tv-ecke-klein); background: var(--tv-mulde); }
  .mini > span { display: flex; flex-direction: column; min-width: 0; }
  .mini .t { display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; color: var(--tv-text); }

  .farben { display: flex; gap: 6px; flex-wrap: wrap; }
  .farbe { width: 30px; height: 30px; padding: 0; border: 2px solid transparent; border-radius: var(--tv-ecke-klein); cursor: pointer; }
  .farbe.an { border-color: var(--tv-text); }
  .fuss { display: flex; flex-wrap: wrap; gap: var(--tv-a2); padding: var(--tv-a3) var(--tv-a4); background: var(--tv-karte-2); }
</style>

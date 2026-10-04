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

<div class="cleanup">
  <header class="head">
    <h1><i class="fa-solid fa-broom"></i> Aufräumen</h1>
    <div class="views">
      {#each VIEWS as v}
        <button class="view" class:on={view === v.id} onclick={() => chooseView(v.id)}>
          <i class={v.icon}></i> {v.label}
        </button>
      {/each}
    </div>
  </header>

  <p class="hint">{currentView.hint}</p>

  {#if view === 'shorts' && exempt.length > 0}
    <div class="exempt">
      <span class="exempt-label"><i class="fa-solid fa-shield-halved"></i> Geschützte Kanäle (nie Shorts):</span>
      {#each exempt as channel (channel.channel_id)}
        <span class="exempt-chip">{channel.channel_name || channel.channel_id}
          <button title="Schutz aufheben" onclick={() => unprotectChannel(channel)}><i class="fa-solid fa-xmark"></i></button>
        </span>
      {/each}
    </div>
  {/if}

  {#if view === 'channel'}
    <div class="channel-pick">
      {#if currentChannel}
        <span class="current"><i class="fa-solid fa-tv"></i> {currentChannel.channel_name || currentChannel.channel_id}
          · {currentChannel.videos} Videos · {formatSize(currentChannel.bytes)}</span>
      {/if}
      <input type="text" placeholder="Kanal suchen…" bind:value={channelFilter} />
      <div class="channel-list">
        {#each channelMatches as c (c.channel_id)}
          <button class="channel" class:on={c.channel_id === channelId} onclick={() => chooseChannel(c)}>
            <span class="cname">{c.channel_name || c.channel_id}</span>
            <span class="cmeta">{c.videos} · {formatSize(c.bytes)}</span>
          </button>
        {/each}
      </div>
    </div>
  {/if}

  <div class="bar">
    <span class="sum">{list.total} Videos · {formatSize(totalBytes)}</span>
    <span class="spacer"></span>
    {#if selectedCount > 0}
      <span class="sel">{selectedCount} ausgewählt · {formatSize(selectedBytes)}</span>
      <button class="btn" onclick={resetSelection}>Auswahl aufheben</button>
    {/if}
    <button class="btn" onclick={selectLoaded} disabled={!list.items.length}>Geladene auswählen</button>
    <button class="btn" onclick={selectAll} disabled={!list.total}>Alle {list.total} auswählen</button>
    <button class="btn danger" onclick={deleteSelected} disabled={!selectedCount || !!busy}>
      <i class="fa-regular fa-trash-can"></i> {busy || 'Restlos löschen'}
    </button>
  </div>

  {#if list.loading}
    <div class="empty"><i class="fa-solid fa-spinner fa-spin"></i> Laden…</div>
  {:else if view === 'channel' && !channelId}
    <div class="empty">Oben einen Kanal wählen.</div>
  {:else if list.items.length === 0}
    <div class="empty">Nichts mehr da.</div>
  {:else}
    <div class="grid">
      {#each list.items as video (video.id)}
        {@const isSelected = selected.has(video.id)}
        <div class="tile" class:selected={isSelected} role="button" tabindex="0"
             onclick={(e) => toggle(video, e)} onkeydown={(e) => e.key === ' ' && (e.preventDefault(), toggle(video, e))}>
          <div class="thumb">
            <img src={api.thumbnailUrl(video.id)} alt="" loading="lazy" />
            <span class="check"><i class="fa-solid {isSelected ? 'fa-square-check' : 'fa-square'}"></i></span>
            {#if video.duration}<span class="dur">{formatDuration(video.duration)}</span>{/if}
            <button class="open" title="In neuem Tab ansehen" onclick={(e) => openVideo(video, e)}>
              <i class="fa-solid fa-up-right-from-square"></i>
            </button>
          </div>
          <div class="info">
            <span class="title" title={video.title}>{video.title || video.id}</span>
            <span class="meta">{video.channel_name || 'Unbekannt'}</span>
            <span class="meta">{formatSize(video.file_size || 0)} · {lastSeen(video)}{#if video.is_archived} · Archiv{/if}</span>
          </div>
          {#if view === 'shorts'}
            <div class="tile-actions">
              {#if !video.type_verified}<span class="unsure" title="Von der Quelle noch nicht bestätigt">ungeprüft</span>{/if}
              <button class="not-short push" onclick={(e) => { e.stopPropagation(); protectChannel(video); }}
                      title="Alle Videos dieses Kanals dauerhaft nie als Short führen">
                <i class="fa-solid fa-shield-halved"></i> Kanal schützen
              </button>
              <button class="not-short" onclick={(e) => { e.stopPropagation(); notAShort(video); }}
                      title="Ist kein Short: als normales Video führen und aus dieser Liste nehmen">
                <i class="fa-solid fa-rotate-left"></i> Kein Short
              </button>
            </div>
          {/if}
        </div>
      {/each}
    </div>
    <div use:infiniteScroll={{ onLoadMore: list.loadMore, canLoad: list.canLoad }}></div>
    {#if list.loadingMore}<div class="empty small"><i class="fa-solid fa-spinner fa-spin"></i></div>{/if}
  {/if}
</div>

<ConfirmDialog bind:this={confirmRef} />

<style>
  .cleanup { padding: 24px 32px; }
  .head { display: flex; align-items: center; gap: 18px; flex-wrap: wrap; margin-bottom: 8px; }
  .head h1 { margin: 0; font-size: 1.4rem; display: flex; gap: 10px; align-items: center; }
  .head h1 i { color: var(--accent-primary); }
  .views { display: flex; gap: 4px; flex-wrap: wrap; }
  .view { display: inline-flex; align-items: center; gap: 7px; padding: 7px 13px; border-radius: 999px; border: 1px solid transparent;
          background: none; color: var(--text-secondary); font-size: 0.8rem; font-weight: 600; cursor: pointer; }
  .view:hover { background: var(--bg-hover); color: var(--text-primary); }
  .view.on { background: var(--accent-muted); color: var(--accent-primary); border-color: color-mix(in srgb, var(--accent-primary) 35%, transparent); }
  .hint { color: var(--text-tertiary); font-size: 0.82rem; margin: 0 0 14px; }

  .channel-pick { margin-bottom: 14px; }
  .channel-pick .current { display: inline-block; margin-bottom: 8px; font-weight: 600; font-size: 0.86rem; }
  .channel-pick input { width: min(420px, 100%); padding: 8px 12px; border-radius: 8px; border: 1px solid var(--border-primary);
                        background: var(--bg-secondary); color: var(--text-primary); font: inherit; font-size: 0.85rem; }
  .channel-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  .channel { display: inline-flex; gap: 8px; align-items: baseline; padding: 5px 10px; border-radius: 8px; border: 1px solid var(--border-primary);
             background: var(--bg-secondary); color: var(--text-primary); font-size: 0.78rem; cursor: pointer; }
  .channel.on { border-color: var(--accent-primary); color: var(--accent-primary); }
  .cmeta { color: var(--text-tertiary); }

  .bar { position: sticky; top: 0; z-index: 2; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
         padding: 10px 12px; margin: 0 -12px 14px; background: var(--bg-primary); border-bottom: 1px solid var(--border-primary); }
  .sum { font-size: 0.82rem; color: var(--text-secondary); }
  .sel { font-size: 0.82rem; font-weight: 700; color: var(--accent-primary); }
  .spacer { flex: 1; }
  .btn { padding: 6px 11px; border-radius: 8px; border: 1px solid var(--border-primary); background: var(--bg-tertiary);
         color: var(--text-primary); font-size: 0.78rem; font-weight: 600; cursor: pointer; display: inline-flex; gap: 6px; align-items: center; }
  .btn:disabled { opacity: 0.45; cursor: default; }
  .btn.danger { color: var(--status-error); border-color: color-mix(in srgb, var(--status-error) 40%, transparent); }
  .btn.danger:hover:not(:disabled) { background: color-mix(in srgb, var(--status-error) 12%, transparent); }

  .empty { padding: 50px 20px; text-align: center; color: var(--text-tertiary); }
  .empty.small { padding: 16px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 12px; }
  .tile { border-radius: 10px; background: var(--bg-secondary); overflow: hidden; cursor: pointer; outline: 2px solid transparent;
          display: flex; flex-direction: column; user-select: none; }
  .tile:hover { outline-color: var(--border-secondary, var(--border-primary)); }
  .tile.selected { outline-color: var(--status-error); background: color-mix(in srgb, var(--status-error) 8%, var(--bg-secondary)); }
  .thumb { position: relative; aspect-ratio: 16 / 9; background: var(--bg-tertiary); }
  .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .check { position: absolute; top: 6px; left: 8px; font-size: 1.1rem; color: #fff; text-shadow: 0 1px 3px rgba(0,0,0,0.8); }
  .tile.selected .check { color: var(--status-error); }
  .dur { position: absolute; right: 6px; bottom: 6px; padding: 1px 5px; border-radius: 4px; background: rgba(0,0,0,0.8);
         color: #fff; font-size: 0.7rem; font-family: monospace; }
  .open { position: absolute; top: 6px; right: 6px; width: 28px; height: 28px; border: none; border-radius: 6px;
          background: rgba(0,0,0,0.6); color: #fff; cursor: pointer; opacity: 0; }
  .tile:hover .open { opacity: 1; }
  .info { padding: 8px 10px; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .title { font-size: 0.82rem; font-weight: 600; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .meta { font-size: 0.72rem; color: var(--text-tertiary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tile-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 0 10px 9px; margin-top: auto; }
  .unsure { font-size: 0.68rem; color: var(--status-warning); font-weight: 600; }
  .exempt { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: -4px 0 12px; font-size: 0.78rem; }
  .exempt-label { color: var(--text-secondary); font-weight: 600; }
  .exempt-chip { display: inline-flex; align-items: center; gap: 6px; padding: 3px 4px 3px 10px; border-radius: 999px;
                 background: color-mix(in srgb, var(--status-success) 14%, transparent); color: var(--status-success); }
  .exempt-chip button { border: none; background: none; color: inherit; cursor: pointer; padding: 0 4px; }
  .not-short.push { margin-left: auto; }
  .not-short { padding: 4px 9px; border-radius: 6px; border: 1px solid var(--border-primary); background: var(--bg-tertiary);
               color: var(--text-secondary); font-size: 0.72rem; font-weight: 600; cursor: pointer; display: inline-flex; gap: 5px; align-items: center; }
  .not-short:hover { color: var(--status-success); border-color: var(--status-success); }
</style>

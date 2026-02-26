<!--
  EditPanel v1.8.51 – Bearbeiten-Tab für Watch-Seite.
  Titel, Beschreibung, Video-Typ, Kategorien, Tags, Werkzeuge.
  Notizen → NotesSidebar (rechts), Kanalname → readonly.
  Qualität-Upgrade zeigt aktuelle Streams + Zielauswahl.
  © HalloWelt42
-->
<script>
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';

  let {
    video,
    onVideoUpdate = () => {},
    getCurrentTime = () => 0,
  } = $props();

  let editTitle = $state('');
  let editDescription = $state('');
  let editTags = $state('');
  let editCategory = $state([]);
  let editVideoType = $state('video');
  let saving = $state(false);
  let enriching = $state(false);
  let thumbLoading = $state(false);
  let upgrading = $state(false);
  let upgradeQuality = $state('');
  let categories = $state([]);
  let activeEditTab = $state('meta');

  // Stream-Info für Qualität-Upgrade
  let currentVideoStream = $state(null);
  let currentAudioStream = $state(null);
  let streamsLoaded = $state(false);

  let currentQualityLabel = $derived(
    currentVideoStream ? `${currentVideoStream.quality || '?'} ${currentVideoStream.codec || ''}`.trim() : 'Unbekannt'
  );

  let currentAudioLabel = $derived(
    currentAudioStream ? `${currentAudioStream.quality || '?'} ${currentAudioStream.codec || ''}`.trim() : 'Kein Audio'
  );

  // Upgrade-Button nur aktiv wenn andere Qualität gewählt
  let canUpgrade = $derived.by(() => {
    if (!upgradeQuality || upgrading) return false;
    if (upgradeQuality === 'best') return true;
    const cur = currentVideoStream?.quality?.replace('p', '') || '';
    const target = upgradeQuality.replace('p', '');
    return cur !== target;
  });

  $effect(() => {
    if (video) {
      editTitle = video.title || '';
      editDescription = video.description || '';
      editTags = (video.tags || []).join(', ');
      editCategory = video.category_ids || [];
      editVideoType = video.video_type || 'video';
      loadCategories();
      loadStreams();
    }
  });

  async function loadCategories() {
    try { categories = await api.getCategoriesFlat(); } catch { categories = []; }
  }

  async function loadStreams() {
    if (!video?.id) return;
    streamsLoaded = false;
    try {
      const res = await api.getStreams(video.id);
      const streams = res?.streams || [];
      const videoStreams = streams.filter(s => s.stream_type === 'video');
      const audioStreams = streams.filter(s => s.stream_type === 'audio');
      currentVideoStream = videoStreams.find(s => s.is_default) || videoStreams[0] || null;
      currentAudioStream = audioStreams.find(s => s.is_default) || audioStreams[0] || null;
      // Aktuelle Qualität als Default vorbelegen
      if (currentVideoStream?.quality) {
        upgradeQuality = currentVideoStream.quality;
      } else {
        upgradeQuality = 'best';
      }
    } catch {
      currentVideoStream = null;
      currentAudioStream = null;
      upgradeQuality = 'best';
    }
    streamsLoaded = true;
  }

  async function save() {
    if (!video) return;
    saving = true;
    try {
      const tags = editTags.split(',').map(t => t.trim()).filter(Boolean);
      await api.updateVideo(video.id, {
        title: editTitle !== video.title ? editTitle : undefined,
        description: editDescription !== video.description ? editDescription : undefined,
        tags,
        category_ids: editCategory,
        video_type: editVideoType !== (video.video_type || 'video') ? editVideoType : undefined,
      });
      toast.success('Gespeichert');
      onVideoUpdate();
    } catch (e) { toast.error(e.message); }
    saving = false;
  }

  async function enrichWithYT() {
    if (!video) return;
    enriching = true;
    try {
      const res = await api.enrichFromYoutube(video.id);
      if (res.status === 'ok') {
        toast.success(`YT-Daten: ${res.updated_fields.join(', ')}`);
        onVideoUpdate();
      } else { toast.error(res.message); }
    } catch (e) { toast.error(e.message); }
    enriching = false;
  }

  async function fetchYtThumb() {
    if (!video || thumbLoading) return;
    thumbLoading = true;
    try {
      const res = await api.fetchYtThumbnail(video.id);
      if (res.status === 'ok') {
        toast.success(`YT-Thumbnail geladen (${res.quality})`);
        onVideoUpdate();
      } else { toast.error(res.message || 'Kein YT-Thumbnail verfügbar'); }
    } catch (e) { toast.error(e.message); }
    thumbLoading = false;
  }

  async function setThumbnailFromPosition() {
    if (!video || thumbLoading) return;
    thumbLoading = true;
    const pos = Math.floor(getCurrentTime());
    try {
      const res = await api.thumbnailAtPosition(video.id, pos);
      if (res.status === 'ok') { toast.success(`Thumbnail bei ${pos}s gesetzt`); onVideoUpdate(); }
      else { toast.error(res.message); }
    } catch (e) { toast.error(e.message); }
    thumbLoading = false;
  }

  async function repairThumb() {
    if (!video || thumbLoading) return;
    thumbLoading = true;
    try {
      const res = await api.scanRepairThumbnail(video.id);
      if (res.status === 'ok') { toast.success('Thumbnail repariert'); onVideoUpdate(); }
      else { toast.error(res.message); }
    } catch (e) { toast.error(e.message); }
    thumbLoading = false;
  }

  async function upgradeVideo() {
    if (!video || video.id?.startsWith('local_') || !canUpgrade) return;
    upgrading = true;
    try {
      const res = await api.upgradeVideo(video.id, upgradeQuality);
      if (res.status === 'ok') toast.success(`Upgrade auf ${upgradeQuality} gestartet`);
    } catch (e) { toast.error(e.message); }
    upgrading = false;
  }
</script>

<div class="edit-section">
  <!-- Sub-Tabs (ohne Notizen – die sind jetzt in der Sidebar) -->
  <div class="edit-tabs">
    <button class="etab" class:active={activeEditTab === 'meta'} onclick={() => activeEditTab = 'meta'}>
      <i class="fa-solid fa-pen"></i> Metadaten
    </button>
    <button class="etab" class:active={activeEditTab === 'desc'} onclick={() => activeEditTab = 'desc'}>
      <i class="fa-solid fa-file-lines"></i> Beschreibung
    </button>
    <button class="etab" class:active={activeEditTab === 'tools'} onclick={() => activeEditTab = 'tools'}>
      <i class="fa-solid fa-wrench"></i> Werkzeuge
    </button>
  </div>

  <!-- Tab: Metadaten -->
  {#if activeEditTab === 'meta'}
    <div class="edit-group">
      <label for="edit-title"><i class="fa-solid fa-heading"></i> Titel</label>
      <input type="text" id="edit-title" bind:value={editTitle} />
    </div>
    <div class="edit-group">
      <label><i class="fa-solid fa-user"></i> Kanal</label>
      <span class="readonly-field">{video?.channel_name || 'Unbekannt'}</span>
    </div>
    <div class="edit-group">
      <span class="edit-label"><i class="fa-solid fa-tag"></i> Video-Typ</span>
      <div class="type-pills">
        {#each [['video', 'fa-solid fa-play', 'Video'], ['short', 'fa-solid fa-bolt', 'Short'], ['live', 'fa-solid fa-tower-broadcast', 'Live']] as [val, icon, label]}
          <button class="type-pill" class:active={editVideoType === val}
                  class:pill-video={val === 'video'} class:pill-short={val === 'short'} class:pill-live={val === 'live'}
                  onclick={() => editVideoType = val}>
            <i class={icon}></i> {label}
          </button>
        {/each}
      </div>
    </div>
    <div class="edit-group">
      <span class="edit-label">Kategorien</span>
      {#if categories.length > 0}
        <div class="cat-checks">
          {#each categories as cat}
            <label class="cat-check" style="--cat-color: {cat.color || 'var(--accent-primary)'}">
              <input type="checkbox" value={cat.id}
                checked={editCategory.includes(cat.id)}
                onchange={(e) => {
                  if (e.target.checked) editCategory = [...editCategory, cat.id];
                  else editCategory = editCategory.filter(id => id !== cat.id);
                }} />
              <span class="cat-dot-sm" style="background: {cat.color}"></span>
              {cat.name}
            </label>
          {/each}
        </div>
      {:else}
        <span class="no-cats">Keine Kategorien vorhanden</span>
      {/if}
    </div>
    <div class="edit-group">
      <label for="edit-tags">Tags <span class="hint">(kommagetrennt)</span></label>
      <input type="text" id="edit-tags" bind:value={editTags} placeholder="z.B. Tutorial, Python, 2024" />
    </div>

  <!-- Tab: Beschreibung -->
  {:else if activeEditTab === 'desc'}
    <div class="edit-group">
      <label for="edit-desc"><i class="fa-solid fa-file-lines"></i> YouTube-Beschreibung <span class="hint">(editierbar)</span></label>
      <textarea id="edit-desc" bind:value={editDescription} rows="12" placeholder="Video-Beschreibung…"></textarea>
    </div>

  <!-- Tab: Werkzeuge -->
  {:else if activeEditTab === 'tools'}
    <div class="edit-tools">
      <span class="edit-label">Thumbnail {#if thumbLoading}<i class="fa-solid fa-spinner fa-spin" style="margin-left:6px;font-size:0.8rem"></i>{/if}</span>
      <div class="tool-btns">
        {#if video && !video.id?.startsWith('local_')}
          <button class="btn-tool" onclick={fetchYtThumb} disabled={thumbLoading}><i class="fa-solid fa-image"></i> {thumbLoading ? 'Lädt…' : 'YT-Thumbnail laden'}</button>
        {/if}
        <button class="btn-tool" onclick={setThumbnailFromPosition} disabled={thumbLoading}><i class="fa-solid fa-camera"></i> Thumbnail von Position</button>
        <button class="btn-tool" onclick={repairThumb} disabled={thumbLoading}><i class="fa-solid fa-film"></i> Thumbnail aus Video</button>
      </div>

      {#if video && !video.id?.startsWith('local_')}
        <span class="edit-label" style="margin-top:12px">Daten</span>
        <div class="tool-btns">
          <button class="btn-tool" onclick={enrichWithYT} disabled={enriching}>
            <i class="fa-solid fa-cloud-arrow-down"></i> {enriching ? 'Laden…' : 'YT-Daten anreichern'}
          </button>
        </div>
      {/if}

      {#if video && !video.id?.startsWith('local_') && video.source !== 'local' && video.source !== 'imported'}
        <div class="upgrade-section">
          <span class="edit-label"><i class="fa-solid fa-arrow-up-right-dots"></i> Qualität wechseln</span>

          <!-- Aktuelle Qualität anzeigen -->
          <div class="current-quality">
            <div class="cq-row">
              <span class="cq-label">Video:</span>
              {#if streamsLoaded}
                {#if currentVideoStream}
                  <span class="cq-value">{currentVideoStream.quality || '?'}</span>
                  <span class="cq-codec">{currentVideoStream.codec || ''}</span>
                {:else}
                  <span class="cq-none">Kein Video-Stream</span>
                {/if}
              {:else}
                <span class="cq-loading"><i class="fa-solid fa-spinner fa-spin"></i></span>
              {/if}
            </div>
            <div class="cq-row">
              <span class="cq-label">Audio:</span>
              {#if streamsLoaded}
                {#if currentAudioStream}
                  <span class="cq-value">{currentAudioStream.quality || '?'}</span>
                  <span class="cq-codec">{currentAudioStream.codec || ''}</span>
                {:else}
                  <span class="cq-none">Kein Audio-Stream</span>
                {/if}
              {:else}
                <span class="cq-loading"><i class="fa-solid fa-spinner fa-spin"></i></span>
              {/if}
            </div>
          </div>

          <!-- Ziel-Qualität wählen -->
          <div class="upgrade-ctrl">
            <label class="upgrade-target-label" for="upgrade-sel">Ziel:</label>
            <select id="upgrade-sel" class="upgrade-sel" bind:value={upgradeQuality}>
              <option value="best">Beste verfügbar</option>
              <option value="2160p">
                4K (2160p){currentVideoStream?.quality === '2160p' ? ' ← aktuell' : ''}
              </option>
              <option value="1440p">
                1440p{currentVideoStream?.quality === '1440p' ? ' ← aktuell' : ''}
              </option>
              <option value="1080p">
                1080p{currentVideoStream?.quality === '1080p' ? ' ← aktuell' : ''}
              </option>
              <option value="720p">
                720p{currentVideoStream?.quality === '720p' ? ' ← aktuell' : ''}
              </option>
              <option value="480p">
                480p{currentVideoStream?.quality === '480p' ? ' ← aktuell' : ''}
              </option>
            </select>
            <button class="btn-tool btn-upgrade" onclick={upgradeVideo} disabled={!canUpgrade}>
              <i class="fa-solid fa-download"></i>
              {#if upgrading}
                Läuft…
              {:else if !canUpgrade && upgradeQuality !== 'best'}
                Bereits {upgradeQuality}
              {:else}
                Neu laden
              {/if}
            </button>
          </div>
          <span class="upgrade-hint">Video wird neu heruntergeladen, DB-Daten bleiben erhalten</span>
        </div>
      {/if}
    </div>
  {/if}

  <!-- Save Button (nur bei Metadaten + Beschreibung) -->
  {#if activeEditTab !== 'tools'}
    <button class="btn-save" onclick={save} disabled={saving}>
      {#if saving}Speichern…{:else}<i class="fa-solid fa-floppy-disk"></i> Speichern{/if}
    </button>
  {/if}
</div>

<style>
  .edit-section { display: flex; flex-direction: column; gap: 14px; }
  .edit-tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--border-primary); padding-bottom: 0; margin-bottom: 4px; }
  .etab {
    padding: 6px 12px; border: none; border-bottom: 2px solid transparent;
    background: none; color: var(--text-tertiary); font-size: 0.78rem; cursor: pointer;
    display: flex; align-items: center; gap: 5px; transition: all 0.15s;
  }
  .etab:hover { color: var(--text-secondary); }
  .etab.active { color: var(--accent-primary); border-bottom-color: var(--accent-primary); font-weight: 600; }
  .edit-group { display: flex; flex-direction: column; gap: 6px; }
  .edit-label { font-size: 0.78rem; font-weight: 600; color: var(--text-secondary); }
  .readonly-field {
    padding: 8px 12px; border: 1px solid var(--border-primary); border-radius: 8px;
    background: var(--bg-tertiary); color: var(--text-tertiary); font-size: 0.85rem;
    cursor: not-allowed; user-select: text;
  }
  .cat-checks { display: flex; flex-wrap: wrap; gap: 6px; }
  .cat-check { display: flex; align-items: center; gap: 4px; font-size: 0.8rem; cursor: pointer; padding: 3px 8px; border-radius: 6px; border: 1px solid var(--border-primary); }
  .cat-check:hover { border-color: var(--cat-color); }
  .cat-check input { display: none; }
  .cat-check:has(input:checked) { background: color-mix(in srgb, var(--cat-color) 10%, transparent); border-color: var(--cat-color); }
  .cat-dot-sm { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .no-cats { font-size: 0.8rem; color: var(--text-tertiary); }
  .hint { font-size: 0.7rem; color: var(--text-tertiary); font-weight: 400; }
  label { font-size: 0.85rem; color: var(--text-secondary); }
  input[type="text"], textarea { padding: 8px 12px; border: 1px solid var(--border-primary); border-radius: 8px; background: var(--bg-secondary); color: var(--text-primary); font-size: 0.85rem; font-family: inherit; }
  textarea { resize: vertical; }
  .btn-save { align-self: flex-start; padding: 8px 20px; font-size: 0.85rem; background: var(--accent-primary); color: #fff; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; }
  .btn-save:disabled { opacity: 0.5; }
  .edit-tools { display: flex; flex-direction: column; gap: 8px; }
  .tool-btns { display: flex; flex-wrap: wrap; gap: 6px; }
  .btn-tool { padding: 6px 12px; font-size: 0.78rem; border: 1px solid var(--border-primary); border-radius: 6px; background: var(--bg-secondary); color: var(--text-secondary); cursor: pointer; display: flex; align-items: center; gap: 6px; }
  .btn-tool:hover:not(:disabled) { border-color: var(--accent-primary); color: var(--accent-primary); }
  .btn-tool:disabled { opacity: 0.4; cursor: not-allowed; }

  /* ─── Qualität wechseln ─── */
  .upgrade-section { display: flex; flex-direction: column; gap: 8px; margin-top: 4px; padding-top: 12px; border-top: 1px dashed var(--border-secondary); }
  .current-quality {
    display: flex; flex-direction: column; gap: 4px;
    padding: 8px 12px; border-radius: 8px; background: var(--bg-tertiary);
    border: 1px solid var(--border-primary);
  }
  .cq-row { display: flex; align-items: center; gap: 6px; font-size: 0.8rem; }
  .cq-label { color: var(--text-tertiary); width: 48px; flex-shrink: 0; }
  .cq-value { color: var(--text-primary); font-weight: 600; }
  .cq-codec { color: var(--text-tertiary); font-size: 0.72rem; }
  .cq-none { color: var(--text-tertiary); font-style: italic; font-size: 0.75rem; }
  .cq-loading { color: var(--text-tertiary); font-size: 0.75rem; }
  .upgrade-ctrl { display: flex; gap: 8px; align-items: center; }
  .upgrade-target-label { font-size: 0.78rem; color: var(--text-tertiary); font-weight: 600; flex-shrink: 0; }
  .upgrade-sel { padding: 6px 10px; border: 1px solid var(--border-primary); border-radius: 6px; background: var(--bg-secondary); color: var(--text-primary); font-size: 0.8rem; flex: 1; }
  .btn-upgrade { background: var(--bg-tertiary); border-color: var(--accent-primary); color: var(--accent-primary); white-space: nowrap; }
  .btn-upgrade:hover:not(:disabled) { background: var(--accent-primary); color: #fff; }
  .upgrade-hint { font-size: 0.7rem; color: var(--text-tertiary); }

  /* Video-Typ Pills */
  .type-pills { display: flex; gap: 6px; }
  .type-pill {
    padding: 5px 14px; border: 1px solid var(--border-primary); border-radius: 20px;
    background: var(--bg-secondary); color: var(--text-secondary); font-size: 0.78rem;
    cursor: pointer; display: flex; align-items: center; gap: 5px; transition: all 0.15s;
  }
  .type-pill:hover { border-color: var(--text-tertiary); }
  .type-pill.active.pill-video { background: rgba(34,197,94,0.12); border-color: #22c55e; color: #22c55e; }
  .type-pill.active.pill-short { background: rgba(225,29,72,0.12); border-color: #e11d48; color: #e11d48; }
  .type-pill.active.pill-live { background: rgba(239,68,68,0.12); border-color: #ef4444; color: #ef4444; }
</style>

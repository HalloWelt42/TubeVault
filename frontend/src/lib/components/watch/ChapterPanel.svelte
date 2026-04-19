<!--
  ChapterPanel – Kapitel-Verwaltung für Watch-Seite.
  Liste, hinzufügen, löschen, YouTube-Import, Vorschaubilder.
  © HalloWelt42
-->
<script>
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';
  import { formatDuration } from '../../utils/format.js';

  let {
    videoId,
    chapters = $bindable([]),
    getCurrentTime = () => 0,
    onSeek = () => {},
  } = $props();

  let newTitle = $state('');
  let newTime = $state('');
  let loadingYT = $state(false);
  let generatingThumbs = $state(false);
  let hoverThumb = $state(null);
  let hoverRect = $state(null);

  function parseTimeInput(val) {
    if (!val || val.trim() === '') return null;
    val = val.trim();
    if (/^\d+$/.test(val)) return Number(val);
    const parts = val.split(':').map(Number);
    if (parts.length === 2) return parts[0] * 60 + parts[1];
    if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
    return null;
  }

  async function loadChapters() {
    try {
      const res = await api.getChapters(videoId);
      chapters = res.chapters || [];
    } catch { chapters = []; }
  }

  async function addChapter() {
    if (!newTitle.trim()) return;
    const t = parseTimeInput(newTime);
    const startTime = t !== null ? t : Math.floor(getCurrentTime());
    try {
      await api.addChapter(videoId, { title: newTitle.trim(), start_time: startTime });
      toast.success(`Kapitel bei ${formatDuration(startTime)} gesetzt`);
      newTitle = ''; newTime = '';
      await loadChapters();
    } catch (e) { toast.error(e.message); }
  }

  async function removeChapter(id) {
    try {
      await api.deleteChapter(id);
      toast.success('Kapitel entfernt');
      await loadChapters();
    } catch (e) { toast.error(e.message); }
  }

  async function fetchFromYT() {
    loadingYT = true;
    try {
      const res = await api.fetchYTChapters(videoId);
      if (res.count > 0) {
        toast.success(`${res.count} Kapitel geladen`);
        await loadChapters();
      } else {
        toast.info('Keine Kapitel auf YouTube vorhanden');
      }
    } catch (e) { toast.error(e.message); }
    loadingYT = false;
  }

  async function generateThumbs() {
    generatingThumbs = true;
    try {
      const res = await api.generateChapterThumbnails(videoId);
      toast.success(`${res.generated}/${res.total} Vorschaubilder generiert`);
      await loadChapters();
    } catch (e) { toast.error(e.message); }
    generatingThumbs = false;
  }
</script>

<!-- Kapitel-Liste -->
{#if chapters.length > 0}
  <div class="chapter-list">
    {#each chapters as ch}
      <div class="ch-row">
        <button class="ch-item" onclick={() => onSeek(ch.start_time)}>
          {#if ch.thumbnail_url}
            <div class="ch-thumb-wrap"
              onmouseenter={(e) => { hoverThumb = ch.thumbnail_url; hoverRect = e.currentTarget.getBoundingClientRect(); }}
              onmouseleave={() => hoverThumb = null}>
              <img class="ch-thumb" src={ch.thumbnail_url} alt="" loading="lazy"
                onerror={(e) => e.target.style.display='none'}>
            </div>
          {:else}
            <span class="ch-thumb-ph"><i class="fa-solid fa-image"></i></span>
          {/if}
          <div class="ch-info">
            <span class="ch-title">{ch.title}</span>
            <div class="ch-meta">
              <span class="ch-time">{formatDuration(ch.start_time)}</span>
              {#if ch.source === 'manual'}<span class="ch-src">manuell</span>{/if}
              {#if ch.end_time}<span class="ch-dur">{formatDuration(ch.end_time - ch.start_time)}</span>{/if}
            </div>
          </div>
        </button>
        <button class="ch-del" title="Kapitel entfernen" onclick={() => removeChapter(ch.id)}>
          <i class="fa-solid fa-xmark"></i>
        </button>
      </div>
    {/each}
  </div>
{:else}
  <p class="tab-hint">Keine Kapitel vorhanden.</p>
{/if}

<!-- Kapitel hinzufügen -->
<div class="add-form">
  <div class="form-row">
    <input type="text" class="input flex-2" placeholder="Kapitelname"
           bind:value={newTitle} onkeydown={(e) => e.key === 'Enter' && addChapter()} />
    <input type="text" class="input flex-1" placeholder={`Zeit (${formatDuration(getCurrentTime())})`}
           bind:value={newTime} onkeydown={(e) => e.key === 'Enter' && addChapter()} />
    <button class="btn-sm accent" onclick={addChapter} disabled={!newTitle.trim()}>
      <i class="fa-solid fa-plus"></i> Setzen
    </button>
  </div>
  <span class="hint">Leer = aktuelle Player-Position. Format: mm:ss oder hh:mm:ss</span>
</div>

<!-- Aktionen -->
<div class="ch-actions">
  <button class="btn-sm" disabled={loadingYT} onclick={fetchFromYT}>
    {#if loadingYT}<i class="fa-solid fa-spinner fa-spin"></i> Laden…{:else}<i class="fa-brands fa-youtube"></i> Von YouTube laden{/if}
  </button>
  {#if chapters.length > 0}
    <button class="btn-sm" disabled={generatingThumbs} onclick={generateThumbs}>
      {#if generatingThumbs}<i class="fa-solid fa-spinner fa-spin"></i> Generiere…{:else}<i class="fa-solid fa-images"></i> Vorschaubilder{/if}
    </button>
  {/if}
</div>

<!-- Floating Preview -->
{#if hoverThumb && hoverRect}
  {@const rightSpace = typeof window !== 'undefined' ? window.innerWidth - hoverRect.right - 24 : 500}
  {@const showRight = rightSpace >= 480}
  <div class="ch-preview"
    style="top: {Math.min(Math.max(8, hoverRect.top), (typeof window !== 'undefined' ? window.innerHeight : 800) - 300)}px; {showRight ? `left: ${hoverRect.right + 16}px` : `right: ${(typeof window !== 'undefined' ? window.innerWidth : 1000) - hoverRect.left + 16}px`};"
    onmouseenter={() => hoverThumb = null}>
    <img src={hoverThumb} alt="">
  </div>
{/if}

<style>
  .chapter-list { display: flex; flex-direction: column; gap: 2px; }
  .ch-row { display: flex; align-items: center; gap: 0; }
  .ch-row .ch-item { flex: 1; }
  .ch-item {
    display: flex; align-items: center; gap: 10px; padding: 6px 8px;
    background: none; border: none; cursor: pointer; text-align: left;
    border-radius: 8px; width: 100%; transition: background 0.15s;
  }
  .ch-item:hover { background: var(--bg-secondary); }
  .ch-thumb-wrap { position: relative; flex-shrink: 0; }
  .ch-thumb { width: 64px; height: 36px; border-radius: 4px; object-fit: cover; border: 1px solid var(--border-secondary); display: block; }
  .ch-thumb-ph { width: 64px; height: 36px; border-radius: 4px; flex-shrink: 0; background: var(--bg-tertiary); display: flex; align-items: center; justify-content: center; color: var(--text-tertiary); font-size: 0.7rem; border: 1px solid var(--border-secondary); }
  .ch-info { flex: 1; min-width: 0; }
  .ch-title { font-size: 0.82rem; font-weight: 500; color: var(--text-primary); display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .ch-meta { display: flex; gap: 8px; font-size: 0.72rem; color: var(--text-tertiary); margin-top: 1px; }
  .ch-time { font-family: monospace; color: var(--accent-primary); font-weight: 600; }
  .ch-src { color: var(--text-tertiary); font-style: italic; }
  .ch-dur { color: var(--text-tertiary); }
  .ch-del { background: none; border: none; color: var(--text-tertiary); cursor: pointer; padding: 4px 6px; border-radius: 4px; font-size: 0.7rem; opacity: 0.3; }
  .ch-del:hover { opacity: 1; color: var(--status-error); }
  .ch-actions { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
  .add-form { margin-top: 14px; }
  .form-row { display: flex; gap: 6px; align-items: center; }
  .input { padding: 6px 10px; border: 1px solid var(--border-primary); border-radius: 6px; background: var(--bg-secondary); color: var(--text-primary); font-size: 0.82rem; }
  .flex-1 { flex: 1; } .flex-2 { flex: 2; }
  .hint { font-size: 0.68rem; color: var(--text-tertiary); display: block; margin-top: 4px; }
  .tab-hint { color: var(--text-tertiary); font-size: 0.85rem; }
  .ch-preview {
    position: fixed; z-index: 9999; pointer-events: none;
    transform: translateY(-50%); filter: drop-shadow(0 8px 24px rgba(0,0,0,0.6));
  }
  .ch-preview img {
    display: block; max-width: 480px; width: auto; height: auto;
    border-radius: 8px; border: 2px solid var(--accent-primary);
  }
</style>

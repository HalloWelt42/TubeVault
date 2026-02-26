<!--
  TubeVault – SubtitleLiveSidebar v1.8.49
  Mitlaufende Untertitel-Anzeige (wie Lyrics)
  Synchronisiert mit Videozeit, VTT-Parser
  © HalloWelt42 – Private Nutzung
-->
<script>
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';
  import { formatSize } from '../../utils/format.js';

  let {
    videoId,
    videoEl = null,
    subtitles = $bindable([]),
  } = $props();

  let activeSub = $state(null);
  let cues = $state([]);
  let currentIdx = $state(-1);
  let cueListEl = $state(null);
  let rafId = null;

  // VTT-Parser
  function parseVTT(text) {
    const result = [];
    const blocks = text.split(/\n\n+/);
    for (const block of blocks) {
      const lines = block.trim().split('\n');
      let timeLine = null;
      let textLines = [];
      for (const line of lines) {
        if (line.includes('-->')) {
          timeLine = line;
        } else if (timeLine) {
          textLines.push(line);
        }
      }
      if (timeLine && textLines.length) {
        const [startStr, endStr] = timeLine.split('-->').map(s => s.trim());
        const start = parseTime(startStr);
        const end = parseTime(endStr);
        if (!isNaN(start) && !isNaN(end)) {
          // HTML-Tags und VTT-Markup entfernen
          const txt = textLines.join(' ').replace(/<[^>]+>/g, '').trim();
          if (txt) result.push({ start, end, text: txt });
        }
      }
    }
    return result;
  }

  function parseTime(str) {
    const parts = str.split(':');
    if (parts.length === 3) {
      return (+parts[0]) * 3600 + (+parts[1]) * 60 + parseFloat(parts[2]);
    }
    if (parts.length === 2) {
      return (+parts[0]) * 60 + parseFloat(parts[1]);
    }
    return NaN;
  }

  function formatTime(sec) {
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  async function loadCues(sub) {
    if (activeSub === sub.code) {
      activeSub = null;
      cues = [];
      stopSync();
      return;
    }
    try {
      const url = api.subtitleUrl(videoId, sub.code + '.vtt');
      const resp = await fetch(url);
      if (!resp.ok) {
        // Fallback: ohne .vtt Extension
        const resp2 = await fetch(api.subtitleUrl(videoId, sub.code));
        if (!resp2.ok) throw new Error('Nicht gefunden');
        const text = await resp2.text();
        cues = parseVTT(text);
      } else {
        const text = await resp.text();
        cues = parseVTT(text);
      }
      activeSub = sub.code;
      startSync();
    } catch (e) {
      toast.error('Untertitel laden fehlgeschlagen');
    }
  }

  function startSync() {
    stopSync();
    function tick() {
      if (!videoEl) return;
      const t = videoEl.currentTime;
      let idx = -1;
      for (let i = 0; i < cues.length; i++) {
        if (t >= cues[i].start - 0.3 && t < cues[i].end + 0.3) {
          idx = i;
          break;
        }
      }
      if (idx !== currentIdx) {
        currentIdx = idx;
        scrollToCurrent();
      }
      rafId = requestAnimationFrame(tick);
    }
    rafId = requestAnimationFrame(tick);
  }

  function stopSync() {
    if (rafId) cancelAnimationFrame(rafId);
    rafId = null;
  }

  function scrollToCurrent() {
    if (!cueListEl || currentIdx < 0) return;
    const el = cueListEl.children[currentIdx];
    if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }

  function seekTo(sec) {
    if (videoEl) videoEl.currentTime = sec;
  }

  async function download(lang) {
    try {
      const res = await api.downloadSubtitles(videoId, lang);
      if (res.count > 0) {
        toast.success(`${res.count} Untertitel geladen (${lang.toUpperCase()})`);
        const r2 = await api.getSubtitles(videoId);
        subtitles = r2.subtitles || [];
      } else {
        toast.info(`Keine ${lang.toUpperCase()} Untertitel`);
      }
    } catch (e) { toast.error(e.message); }
  }

  // Cleanup
  $effect(() => {
    return () => stopSync();
  });
</script>

<div class="stl">
  <!-- Subtitle-Auswahl -->
  <div class="stl-picker">
    {#if subtitles.length === 0}
      <div class="stl-empty">
        <span>Keine Untertitel</span>
        <div class="stl-dl">
          <button onclick={() => download('de')}>🇩🇪</button>
          <button onclick={() => download('en')}>🇬🇧</button>
          <button onclick={() => download('all')}>🌐</button>
        </div>
      </div>
    {:else}
      <div class="stl-tabs">
        {#each subtitles as sub}
          <button class="stl-tab" class:active={activeSub === sub.code} onclick={() => loadCues(sub)}>
            {sub.code.includes('de') ? '🇩🇪' : sub.code.includes('en') ? '🇬🇧' : '🌐'}
            {sub.name || sub.code}
            {#if sub.code.startsWith('a.')}<span class="auto-tag">auto</span>{/if}
          </button>
        {/each}
        <button class="stl-tab stl-add" onclick={() => download('all')} title="Weitere laden">
          <i class="fa-solid fa-plus"></i>
        </button>
      </div>
    {/if}
  </div>

  <!-- Cue-Liste (mitlaufend) -->
  {#if cues.length > 0}
    <div class="stl-cues" bind:this={cueListEl}>
      {#each cues as cue, i}
        <button
          class="stl-cue"
          class:active={i === currentIdx}
          class:past={i < currentIdx}
          onclick={() => seekTo(cue.start)}
        >
          <span class="stl-time">{formatTime(cue.start)}</span>
          <span class="stl-text">{cue.text}</span>
        </button>
      {/each}
    </div>
    <div class="stl-info">{cues.length} Zeilen · {activeSub}</div>
  {:else if activeSub}
    <div class="stl-loading">Lade…</div>
  {/if}
</div>

<style>
  .stl { display: flex; flex-direction: column; height: 100%; overflow: hidden; }

  .stl-picker { padding: 6px 8px; border-bottom: 1px solid var(--border-secondary); flex-shrink: 0; }
  .stl-empty { text-align: center; padding: 8px; color: var(--text-tertiary); font-size: 0.75rem; }
  .stl-dl { display: flex; gap: 4px; justify-content: center; margin-top: 6px; }
  .stl-dl button {
    background: var(--bg-tertiary); border: 1px solid var(--border-secondary);
    border-radius: 4px; cursor: pointer; padding: 3px 8px; font-size: 0.75rem;
  }
  .stl-dl button:hover { border-color: var(--accent-primary); }

  .stl-tabs { display: flex; flex-wrap: wrap; gap: 3px; }
  .stl-tab {
    background: var(--bg-tertiary); border: 1px solid var(--border-secondary);
    border-radius: 4px; cursor: pointer; padding: 3px 8px;
    font-size: 0.68rem; color: var(--text-secondary);
    display: flex; align-items: center; gap: 3px;
  }
  .stl-tab:hover { border-color: var(--accent-primary); color: var(--text-primary); }
  .stl-tab.active { border-color: var(--accent-primary); background: rgba(var(--accent-rgb, 59,130,246), 0.1); color: var(--accent-primary); }
  .stl-add { padding: 3px 6px; }
  .auto-tag { font-size: 0.5rem; background: var(--bg-tertiary); padding: 0 3px; border-radius: 2px; color: var(--text-tertiary); }

  .stl-cues { flex: 1; overflow-y: auto; padding: 4px; }
  .stl-cue {
    display: flex; gap: 8px; padding: 4px 8px; border: none; background: none;
    width: 100%; text-align: left; cursor: pointer; border-radius: 4px;
    font-size: 0.78rem; line-height: 1.4; color: var(--text-tertiary);
    transition: all 0.15s;
  }
  .stl-cue:hover { background: var(--bg-tertiary); color: var(--text-primary); }
  .stl-cue.active {
    background: rgba(var(--accent-rgb, 59,130,246), 0.12);
    color: var(--text-primary); font-weight: 500;
  }
  .stl-cue.past { color: var(--text-tertiary); opacity: 0.6; }
  .stl-time {
    flex-shrink: 0; width: 36px; font-size: 0.62rem; font-family: monospace;
    color: var(--text-tertiary); padding-top: 2px;
  }
  .stl-cue.active .stl-time { color: var(--accent-primary); }
  .stl-text { flex: 1; }

  .stl-info {
    padding: 3px 8px; font-size: 0.6rem; color: var(--text-tertiary);
    border-top: 1px solid var(--border-secondary); text-align: center; flex-shrink: 0;
  }
  .stl-loading { padding: 20px; text-align: center; color: var(--text-tertiary); font-size: 0.8rem; }
</style>

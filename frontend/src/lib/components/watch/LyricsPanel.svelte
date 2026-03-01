<!--
  LyricsPanel -  Songtext-Verwaltung für Watch-Seite.
  Musik-Erkennung, LRCLIB-Suche, synced/plain Lyrics.
  © HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
  SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
-->
<script>
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';

  let {
    videoId,
    videoTitle = '',
    getCurrentTime = () => 0,
    videoEl = null,
    autoSearch = false,
  } = $props();

  let loading = $state(false);
  let info = $state({ is_music: false, artist: '', title: '', album: '', has_lyrics: false, lyrics_source: '', lrclib_id: null });
  let infoCollapsed = $state(localStorage.getItem('tv-lyrics-collapsed') === '1');
  let plain = $state('');
  let synced = $state('');
  let searchResults = $state([]);
  let showResults = $state(false);
  let timeOffset = $state(0);
  let offsetSaved = $state(true);  // diskette indicator
  let subtitles = $state([]);  // available YouTube subtitles
  let editMode = $state(false);
  let editText = $state('');
  let showSynced = $state(true);
  let autoScroll = $state(true);
  let activeLine = $state(-1);
  let lyricsEl = $state(null);
  let fileInput = $state(null);
  let syncEditMode = $state(false);
  let editLines = $state([]);

  // Parsed synced lyrics: [{time: seconds, text: string}]
  let parsedLines = $derived.by(() => {
    if (!synced) return [];
    const lines = [];
    for (const line of synced.split('\n')) {
      const m = line.match(/^\[(\d+):(\d+)\.(\d+)\]\s*(.*)/);
      if (m) {
        const raw = parseInt(m[1]) * 60 + parseInt(m[2]) + parseInt(m[3]) / 100;
        lines.push({ raw, text: m[4] });
      }
    }
    return lines;
  });

  // Auto-scroll synced lyrics
  $effect(() => {
    if (!showSynced || !parsedLines.length || !videoEl) return;
    const offset = timeOffset;  // track reactively
    const interval = setInterval(() => {
      const t = getCurrentTime();
      let idx = -1;
      for (let i = parsedLines.length - 1; i >= 0; i--) {
        if (parsedLines[i].raw + offset <= t) { idx = i; break; }
      }
      if (idx !== activeLine) {
        activeLine = idx;
        if (autoScroll && lyricsEl) {
          const el = lyricsEl.querySelector(`[data-line="${idx}"]`);
          if (el) {
            const container = lyricsEl;
            const elTop = el.offsetTop - container.offsetTop;
            const elH = el.offsetHeight;
            const cH = container.clientHeight;
            const toolbarH = container.querySelector('.lyrics-toolbar')?.offsetHeight || 0;
            const target = elTop - toolbarH - (cH - toolbarH) / 3;
            container.scrollTo({ top: Math.max(0, target), behavior: 'smooth' });
          }
        }
      }
    }, 200);
    return () => clearInterval(interval);
  });

  async function load() {
    loading = true;
    plain = '';
    synced = '';
    try {
      const res = await api.getLyrics(videoId);
      info = {
        is_music: res.is_music || false,
        artist: res.artist || '',
        title: res.title || '',
        album: res.album || '',
        has_lyrics: res.has_lyrics || false,
        lyrics_source: res.lyrics_source || '',
        lrclib_id: res.lrclib_id || null,
      };
      plain = res.plain || '';
      synced = res.synced || '';
      timeOffset = res.offset || 0;
      offsetSaved = true;
    } catch (e) {
      info = { is_music: false, artist: '', title: '', album: '', has_lyrics: false, lyrics_source: '', lrclib_id: null };
    }
    loading = false;
    loadSubtitleList();

    // Auto-Detect + Suche wenn fixiert und noch keine Lyrics
    if (autoSearch && !plain && !synced) {
      if (!info.is_music) {
        await detectMusic();
      }
      if (info.is_music && info.artist && info.title) {
        await searchLyrics();
      }
    }
  }

  async function detectMusic() {
    loading = true;
    try {
      const res = await api.detectMusic(videoId);
      if (res.is_music) {
        toast.success(`Erkannt: ${res.artist} -  ${res.song_title}`);
        info.is_music = true;
        info.artist = res.artist || '';
        info.title = res.song_title || '';
      } else {
        toast.info('Kein Musik-Muster im Titel erkannt');
        info.is_music = false;
      }
    } catch (e) {
      toast.error('Erkennung fehlgeschlagen');
    }
    loading = false;
  }

  async function searchLyrics(provider = 'auto') {
    if (!info?.artist || !info?.title) {
      toast.warning('Artist und Titel benötigt');
      return;
    }
    loading = true;
    try {
      const res = await api.searchLyrics(videoId, provider);
      if (res.status === 'ok') {
        const src = res.source || provider;
        toast.success(`Lyrics gefunden (${src})${res.has_synced ? ' ♫' : ''}`);
        await load();
      } else {
        toast.warning(res.message || 'Keine Lyrics gefunden');
      }
    } catch (e) {
      toast.error('Lyrics-Suche fehlgeschlagen');
    }
    loading = false;
  }

  async function searchAll() {
    if (!info?.artist || !info?.title) { toast.warning('Artist und Titel benötigt'); return; }
    loading = true;
    try {
      const res = await api.searchLyricsAll(videoId);
      searchResults = res.results || [];
      showResults = true;
      if (!searchResults.length) toast.info('Keine Ergebnisse');
    } catch { toast.error('Suche fehlgeschlagen'); }
    loading = false;
  }

  async function pickResult(r) {
    loading = true;
    try {
      await api.pickLyrics(videoId, {
        lrclib_id: r.lrclib_id,
        plain: r.plain || '',
        synced: r.synced || '',
        artist: r.artist,
        title: r.title,
        album: r.album,
      });
      showResults = false;
      toast.success('Lyrics übernommen');
      await load();
    } catch { toast.error('Übernahme fehlgeschlagen'); }
    loading = false;
  }

  function formatDur(sec) {
    if (!sec) return '';
    const m = Math.floor(sec / 60), s = Math.floor(sec % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  let saveOffsetTimer = null;

  function setOffset(val) {
    timeOffset = Math.round(val * 10) / 10;
    offsetSaved = false;
    clearTimeout(saveOffsetTimer);
  }

  async function saveOffset() {
    clearTimeout(saveOffsetTimer);
    try {
      await api.saveLyricsOffset(videoId, timeOffset);
      offsetSaved = true;
    } catch { toast.error('Offset speichern fehlgeschlagen'); }
  }

  async function loadSubtitleList() {
    try {
      const res = await api.getSubtitles(videoId);
      subtitles = res.subtitles || [];
    } catch { subtitles = []; }
  }

  async function importSubtitle(code) {
    loading = true;
    try {
      const res = await api.lyricsFromSubtitle(videoId, code);
      if (res.status === 'ok') {
        toast.success(`Untertitel importiert (${res.synced_lines} Zeilen)`);
        await load();
      } else {
        toast.warning(res.message || 'Import fehlgeschlagen');
      }
    } catch { toast.error('Subtitle-Import fehlgeschlagen'); }
    loading = false;
  }

  function setStartHere() {
    if (!videoEl || !synced) return;
    const m = synced.match(/^\[(\d+):(\d+)\.(\d+)\]/m);
    if (!m) return;
    const rawFirst = parseInt(m[1]) * 60 + parseInt(m[2]) + parseInt(m[3]) / 100;
    const current = getCurrentTime();
    setOffset(current - rawFirst);
  }

  async function saveMusicInfo() {
    try {
      await api.saveMusicInfo(videoId, {
        is_music: info.is_music,
        artist: info.artist,
        title: info.title,
        album: info.album,
      });
      toast.success('Musik-Info gespeichert');
    } catch (e) {
      toast.error('Speichern fehlgeschlagen');
    }
  }

  async function saveManualLyrics() {
    try {
      await api.saveLyricsManual(videoId, { plain: editText });
      plain = editText;
      editMode = false;
      toast.success('Lyrics gespeichert');
    } catch (e) {
      toast.error('Speichern fehlgeschlagen');
    }
  }

  async function deleteLyrics() {
    try {
      await api.deleteLyrics(videoId);
      plain = '';
      synced = '';
      info.has_lyrics = false;
      toast.success('Lyrics gelöscht');
    } catch (e) {
      toast.error('Löschen fehlgeschlagen');
    }
  }

  function seekTo(time) {
    if (videoEl) videoEl.currentTime = time;
  }

  function startEdit() {
    editText = plain;
    editMode = true;
  }

  function startSyncEdit() {
    if (parsedLines.length) {
      editLines = parsedLines.map(l => ({ time: l.raw, text: l.text }));
    } else if (synced) {
      editLines = [{ time: 0, text: '' }];
    } else {
      editLines = [{ time: 0, text: '' }];
    }
    syncEditMode = true;
  }

  function fmtTs(s) {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    const cs = Math.round((s % 1) * 100);
    return `${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}.${String(cs).padStart(2,'0')}`;
  }

  function parseTs(str) {
    const m = str.match(/^(\d+):(\d+)\.(\d+)$/);
    if (!m) return null;
    return parseInt(m[1]) * 60 + parseInt(m[2]) + parseInt(m[3]) / 100;
  }

  function editLineTime(idx, delta) {
    editLines[idx].time = Math.max(0, Math.round((editLines[idx].time + delta) * 100) / 100);
    editLines = [...editLines];
  }

  function editLineSetTime(idx) {
    if (videoEl) {
      editLines[idx].time = Math.round(videoEl.currentTime * 100) / 100;
      editLines = [...editLines];
    }
  }

  function editLineText(idx, text) {
    editLines[idx].text = text;
    editLines = [...editLines];
  }

  function editLineDelete(idx) {
    editLines = editLines.filter((_, i) => i !== idx);
  }

  function editLineInsert(idx) {
    const prevTime = idx > 0 ? editLines[idx - 1].time : 0;
    const nextTime = editLines[idx]?.time ?? prevTime + 5;
    const newTime = Math.round(((prevTime + nextTime) / 2) * 100) / 100;
    editLines = [...editLines.slice(0, idx), { time: newTime, text: '' }, ...editLines.slice(idx)];
  }

  function editLineAppend() {
    const lastTime = editLines.length ? editLines[editLines.length - 1].time + 5 : 0;
    editLines = [...editLines, { time: lastTime, text: '' }];
  }

  function editLineMoveUp(idx) {
    if (idx <= 0) return;
    [editLines[idx - 1], editLines[idx]] = [editLines[idx], editLines[idx - 1]];
    editLines = [...editLines];
  }

  function editLineMoveDown(idx) {
    if (idx >= editLines.length - 1) return;
    [editLines[idx], editLines[idx + 1]] = [editLines[idx + 1], editLines[idx]];
    editLines = [...editLines];
  }

  function editSortByTime() {
    editLines = [...editLines].sort((a, b) => a.time - b.time);
  }

  async function saveSyncEdit() {
    const sorted = [...editLines].sort((a, b) => a.time - b.time);
    const lrc = sorted.map(l => `[${fmtTs(l.time)}]${l.text}`).join('\n');
    const plainText = sorted.map(l => l.text).filter(t => t.trim()).join('\n');
    try {
      await api.uploadLrc(videoId, { synced: lrc, plain: plainText });
      synced = lrc;
      plain = plainText;
      syncEditMode = false;
      timeOffset = 0;
      toast.success('Synced Lyrics gespeichert');
    } catch (e) {
      toast.error('Speichern fehlgeschlagen');
    }
  }

  function toggleInfo() {
    infoCollapsed = !infoCollapsed;
    localStorage.setItem('tv-lyrics-collapsed', infoCollapsed ? '1' : '0');
  }

  async function handleFileUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    const isLrc = file.name.endsWith('.lrc') || text.match(/^\[\d+:\d+\.\d+\]/m);
    try {
      await api.uploadLrc(videoId, {
        plain: isLrc ? '' : text,
        synced: isLrc ? text : '',
      });
      toast.success(`${isLrc ? 'LRC' : 'Text'} hochgeladen`);
      await load();
    } catch { toast.error('Upload fehlgeschlagen'); }
    e.target.value = '';
  }

  // Initial load
  $effect(() => {
    if (videoId) {
      activeLine = -1;
      lyricsEl = null;
      timeOffset = 0;
      offsetSaved = true;
      showResults = false;
      subtitles = [];
      load();
    }
  });
</script>

{#if loading && !info.artist && !info.has_lyrics}
  <div class="lyrics-loading"><i class="fa-solid fa-spinner fa-spin"></i> Lade…</div>
{:else}
<div class="lyrics-panel">

  <!-- Musik-Info (einklappbar) -->
  <div class="music-info-box" class:collapsed={infoCollapsed}>
    <button class="info-toggle" onclick={toggleInfo}>
      <i class="fa-solid {infoCollapsed ? 'fa-chevron-right' : 'fa-chevron-down'}"></i>
      {#if infoCollapsed && info.is_music}
        <span class="info-summary">{info.artist} -  {info.title}</span>
      {:else}
        <span>Musik-Info</span>
      {/if}
    </button>

    {#if !infoCollapsed}
      <div class="info-content">
        <div class="info-header">
          <label class="music-toggle">
            <input type="checkbox" bind:checked={info.is_music} onchange={saveMusicInfo} />
            <span>Ist Musik</span>
          </label>
          <button class="btn-detect" onclick={detectMusic} disabled={loading}>
            <i class="fa-solid fa-wand-magic-sparkles"></i> Erkennen
          </button>
        </div>

        {#if info?.is_music}
          <div class="info-fields">
            <div class="field-row">
              <label>Artist</label>
              <input type="text" bind:value={info.artist} onblur={saveMusicInfo} placeholder="Interpret" />
            </div>
            <div class="field-row">
              <label>Titel</label>
              <input type="text" bind:value={info.title} onblur={saveMusicInfo} placeholder="Songtitel" />
            </div>
            <div class="field-row">
              <label>Album</label>
              <input type="text" bind:value={info.album} onblur={saveMusicInfo} placeholder="Album (optional)" />
            </div>
          </div>

          <div class="lyrics-actions">
            <button class="btn-search" onclick={() => searchLyrics('auto')} disabled={loading || !info.artist || !info.title}>
              {#if loading}<i class="fa-solid fa-spinner fa-spin"></i>{:else}<i class="fa-solid fa-magnifying-glass"></i>{/if}
              Auto
            </button>
            <div class="provider-btns">
              <button class="btn-provider" onclick={() => searchLyrics('ytmusic')} disabled={loading || !info.artist || !info.title} title="YouTube Music Lyrics">
                <i class="fa-brands fa-youtube"></i> YTM
              </button>
              <button class="btn-provider" onclick={() => searchLyrics('lrclib')} disabled={loading || !info.artist || !info.title} title="LRCLIB Community Lyrics">
                <i class="fa-solid fa-database"></i> LRC
              </button>
            </div>
            <button class="btn-ghost" onclick={searchAll} disabled={loading || !info.artist || !info.title} title="Alle LRCLIB-Versionen anzeigen">
              <i class="fa-solid fa-list"></i>
            </button>
            {#if subtitles.length > 0}
              <div class="sub-dropdown">
                <button class="btn-ghost btn-sub" title="YouTube-Untertitel als Lyrics">
                  <i class="fa-solid fa-closed-captioning"></i>
                </button>
                <div class="sub-menu">
                  {#each subtitles as sub}
                    <button onclick={() => importSubtitle(sub.code)}>{sub.code}</button>
                  {/each}
                </div>
              </div>
            {/if}
            {#if plain || synced}
              <button class="btn-ghost" onclick={startEdit} title="Text bearbeiten"><i class="fa-solid fa-pen"></i></button>
              {#if synced}
                <button class="btn-ghost" onclick={startSyncEdit} title="Sync-Editor"><i class="fa-solid fa-timeline"></i></button>
              {/if}
              <button class="btn-ghost" onclick={() => fileInput?.click()} title="LRC/TXT importieren"><i class="fa-solid fa-file-import"></i></button>
              <button class="btn-ghost btn-danger" onclick={deleteLyrics}><i class="fa-solid fa-trash"></i></button>
            {:else}
              <button class="btn-ghost" onclick={startEdit}><i class="fa-solid fa-pen"></i> Manuell</button>
              <button class="btn-ghost" onclick={() => fileInput?.click()} title="LRC/TXT importieren"><i class="fa-solid fa-file-import"></i> Import</button>
            {/if}
          </div>
          {#if info.lyrics_source || info.lrclib_id}
            <div class="lyrics-meta">
              {#if info.lyrics_source}<span class="lyrics-source">{info.lyrics_source}</span>{/if}
              {#if info.lrclib_id}
                <a class="lrclib-link" href="https://lrclib.net/api/get/{info.lrclib_id}" target="_blank" rel="noopener">
                  <i class="fa-solid fa-arrow-up-right-from-square"></i> LRCLIB #{info.lrclib_id}
                </a>
              {/if}
            </div>
          {/if}
          <input type="file" accept=".lrc,.txt" bind:this={fileInput} onchange={handleFileUpload} style="display:none" />
        {/if}
      </div>
    {/if}
  </div>

  <!-- Lyrics-Anzeige (füllt restlichen Platz) -->
  <div class="lyrics-area">
    {#if showResults}
      <div class="search-results">
        <div class="results-header">
          <span class="results-title">LRCLIB Ergebnisse ({searchResults.length})</span>
          <button class="btn-ghost" onclick={() => showResults = false}><i class="fa-solid fa-xmark"></i></button>
        </div>
        {#each searchResults as r}
          <button class="result-item" onclick={() => pickResult(r)}>
            <div class="result-main">
              <span class="result-name">{r.artist} -  {r.title}</span>
              {#if r.album}<span class="result-album">{r.album}</span>{/if}
            </div>
            <div class="result-tags">
              {#if r.duration}<span class="result-tag">{formatDur(r.duration)}</span>{/if}
              {#if r.has_synced}<span class="result-tag synced">Sync</span>{/if}
            </div>
          </button>
        {/each}
      </div>
    {:else if syncEditMode}
      <div class="sync-editor">
        <div class="sync-editor-toolbar">
          <span class="sync-editor-title"><i class="fa-solid fa-timeline"></i> Sync-Editor ({editLines.length} Zeilen)</span>
          <div class="sync-editor-btns">
            <button class="btn-ghost btn-sm" onclick={editSortByTime} title="Nach Zeit sortieren"><i class="fa-solid fa-arrow-down-1-9"></i></button>
            <button class="btn-ghost btn-sm" onclick={editLineAppend} title="Zeile anhängen"><i class="fa-solid fa-plus"></i></button>
          </div>
        </div>
        <div class="sync-editor-list">
          {#each editLines as line, i}
            <div class="sync-edit-row" class:playing={parsedLines[i] && i === activeLine}>
              <div class="sync-edit-time">
                <button class="time-adj" onclick={() => editLineTime(i, -0.1)} title="−0.1s">−</button>
                <input
                  class="time-input"
                  value={fmtTs(line.time)}
                  onchange={(e) => {
                    const t = parseTs(e.target.value);
                    if (t !== null) { editLines[i].time = t; editLines = [...editLines]; }
                    else e.target.value = fmtTs(line.time);
                  }}
                />
                <button class="time-adj" onclick={() => editLineTime(i, 0.1)} title="+0.1s">+</button>
                <button class="time-set" onclick={() => editLineSetTime(i)} title="Aktuelle Position setzen"><i class="fa-solid fa-crosshairs"></i></button>
              </div>
              <input
                class="sync-edit-text"
                value={line.text}
                oninput={(e) => editLineText(i, e.target.value)}
                placeholder="♪"
              />
              <div class="sync-edit-actions">
                <button class="act-btn" onclick={() => editLineMoveUp(i)} disabled={i===0} title="Nach oben"><i class="fa-solid fa-chevron-up"></i></button>
                <button class="act-btn" onclick={() => editLineMoveDown(i)} disabled={i===editLines.length-1} title="Nach unten"><i class="fa-solid fa-chevron-down"></i></button>
                <button class="act-btn" onclick={() => editLineInsert(i)} title="Zeile einfügen"><i class="fa-solid fa-plus"></i></button>
                <button class="act-btn danger" onclick={() => editLineDelete(i)} title="Löschen"><i class="fa-solid fa-xmark"></i></button>
              </div>
            </div>
          {/each}
        </div>
        <div class="sync-editor-footer">
          <button class="btn-save" onclick={saveSyncEdit}><i class="fa-solid fa-check"></i> Speichern</button>
          <button class="btn-ghost" onclick={() => syncEditMode = false}>Abbrechen</button>
          <span class="sync-hint">Tipp: <i class="fa-solid fa-crosshairs"></i> setzt Timestamp auf aktuelle Videoposition</span>
        </div>
      </div>
    {:else if editMode}
      <div class="lyrics-editor">
        <textarea bind:value={editText} placeholder="Songtext eingeben…"></textarea>
        <div class="editor-actions">
          <button class="btn-save" onclick={saveManualLyrics}><i class="fa-solid fa-check"></i> Speichern</button>
          <button class="btn-ghost" onclick={() => editMode = false}>Abbrechen</button>
        </div>
      </div>
    {:else if synced && showSynced && parsedLines.length}
      <div class="lyrics-display synced" bind:this={lyricsEl}>
        <div class="lyrics-toolbar">
          <div class="lyrics-mode-toggle">
            <button class:active={showSynced} onclick={() => showSynced = true}>Synced</button>
            <button class:active={!showSynced} onclick={() => showSynced = false}>Text</button>
          </div>
          <div class="toolbar-right">
            <button class="sync-btn" onclick={setStartHere} title="Erste Zeile = aktuelle Position">
              <i class="fa-solid fa-crosshairs"></i>
            </button>
            <div class="offset-ctrl" title="Zeitversatz (±0.1s)">
              <button onclick={() => setOffset(timeOffset - 0.1)}>−</button>
              <span class="offset-val" class:nonzero={timeOffset !== 0} onclick={() => setOffset(0)} title="Klick = Reset">{timeOffset > 0 ? '+' : ''}{timeOffset.toFixed(1)}s</span>
              <button onclick={() => setOffset(timeOffset + 0.1)}>+</button>
              {#if timeOffset !== 0}
                <button class="save-btn" class:saved={offsetSaved} class:unsaved={!offsetSaved} onclick={saveOffset} title={offsetSaved ? 'Gespeichert' : 'Klick = Speichern'}>
                  <i class="fa-solid fa-floppy-disk"></i>
                </button>
              {/if}
            </div>
            <button class="scroll-toggle" class:active={autoScroll} onclick={() => autoScroll = !autoScroll} title={autoScroll ? 'Auto-Scroll aus' : 'Auto-Scroll an'}>
              <i class="fa-solid {autoScroll ? 'fa-arrows-up-down' : 'fa-pause'}"></i>
            </button>
          </div>
        </div>
        {#each parsedLines as line, i}
          <button
            class="lyric-line"
            class:active={i === activeLine}
            data-line={i}
            onclick={() => seekTo(line.raw + timeOffset)}
          >
            {line.text || '♪'}
          </button>
        {/each}
      </div>
    {:else if plain}
      <div class="lyrics-display plain" bind:this={lyricsEl}>
        {#if synced}
          <div class="lyrics-mode-toggle sticky">
            <button class:active={showSynced} onclick={() => showSynced = true}>Synced</button>
            <button class:active={!showSynced} onclick={() => showSynced = false}>Text</button>
          </div>
        {/if}
        <pre class="lyrics-text">{plain}</pre>
      </div>
    {:else if info?.is_music}
      <div class="lyrics-empty">
        <i class="fa-solid fa-music"></i>
        <p>Keine Lyrics vorhanden</p>
      </div>
    {/if}
  </div>

</div>
{/if}

<style>
  .lyrics-loading { text-align: center; padding: 24px; color: var(--text-tertiary); }

  /* Panel fills parent completely */
  .lyrics-panel { display: flex; flex-direction: column; height: 100%; min-height: 0; }

  /* Collapsible Info Box */
  .music-info-box {
    background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 10px; margin-bottom: 8px; flex-shrink: 0; overflow: hidden;
  }

  .info-toggle {
    display: flex; align-items: center; gap: 6px; width: 100%; padding: 8px 12px;
    background: none; border: none; color: var(--text-primary); cursor: pointer;
    font-size: 0.8rem; font-weight: 600; text-align: left;
  }
  .info-toggle:hover { background: var(--bg-tertiary); }
  .info-toggle i { font-size: 0.65rem; color: var(--text-tertiary); width: 10px; }
  .info-summary { color: var(--text-secondary); font-weight: 400; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  .info-content { padding: 0 12px 10px; }

  .info-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }

  .music-toggle {
    display: flex; align-items: center; gap: 6px; cursor: pointer;
    font-size: 0.82rem; font-weight: 600; color: var(--text-primary);
  }
  .music-toggle input { accent-color: var(--accent-primary); width: 14px; height: 14px; }

  .btn-detect {
    background: var(--bg-tertiary); border: 1px solid var(--border-secondary);
    color: var(--text-secondary); padding: 3px 8px; border-radius: 6px;
    font-size: 0.72rem; cursor: pointer; display: flex; align-items: center; gap: 4px;
  }
  .btn-detect:hover { color: var(--accent-primary); border-color: var(--accent-primary); }
  .btn-detect:disabled { opacity: 0.5; pointer-events: none; }

  .info-fields { display: flex; flex-direction: column; gap: 5px; margin-bottom: 8px; }
  .field-row { display: flex; align-items: center; gap: 6px; }
  .field-row label {
    min-width: 42px; font-size: 0.68rem; color: var(--text-tertiary);
    text-transform: uppercase; font-weight: 600;
  }
  .field-row input {
    flex: 1; background: var(--bg-primary); border: 1px solid var(--border-primary);
    border-radius: 5px; padding: 3px 8px; font-size: 0.8rem; color: var(--text-primary);
  }
  .field-row input:focus { border-color: var(--accent-primary); outline: none; }

  .lyrics-actions { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }

  .btn-search {
    background: var(--accent-primary); color: #fff; border: none; border-radius: 5px;
    padding: 4px 10px; font-size: 0.76rem; font-weight: 600; cursor: pointer;
    display: flex; align-items: center; gap: 5px;
  }
  .btn-search:hover { filter: brightness(1.1); }
  .btn-search:disabled { opacity: 0.5; pointer-events: none; }

  .provider-btns { display: flex; gap: 2px; }
  .btn-provider {
    background: var(--bg-tertiary); border: 1px solid var(--border-secondary); color: var(--text-tertiary);
    padding: 3px 7px; border-radius: 5px; cursor: pointer; font-size: 0.68rem;
    display: flex; align-items: center; gap: 3px; white-space: nowrap;
  }
  .btn-provider:hover { color: var(--text-primary); border-color: var(--accent-primary); }
  .btn-provider:disabled { opacity: 0.4; pointer-events: none; }

  .btn-ghost {
    background: none; border: 1px solid var(--border-secondary); color: var(--text-secondary);
    padding: 3px 8px; border-radius: 5px; font-size: 0.72rem; cursor: pointer;
    display: flex; align-items: center; gap: 4px;
  }
  .btn-ghost:hover { color: var(--text-primary); border-color: var(--text-secondary); }
  .btn-ghost.btn-danger:hover { color: var(--status-error); border-color: var(--status-error); }

  .lyrics-source { font-size: 0.68rem; color: var(--text-tertiary); }

  /* Meta line with source + LRCLIB link */
  .lyrics-meta { display: flex; gap: 8px; align-items: center; margin-top: 4px; }
  .lrclib-link {
    font-size: 0.68rem; color: var(--accent-primary); text-decoration: none;
    display: flex; align-items: center; gap: 3px;
  }
  .lrclib-link:hover { text-decoration: underline; }
  .lrclib-link i { font-size: 0.58rem; }

  /* Toolbar right group */
  .toolbar-right { display: flex; align-items: center; gap: 6px; }

  /* Offset controls */
  .offset-ctrl {
    display: flex; align-items: center; gap: 2px;
    background: var(--bg-tertiary); border-radius: 5px; padding: 1px 2px;
  }
  .offset-ctrl button {
    background: none; border: none; color: var(--text-tertiary); cursor: pointer;
    width: 22px; height: 22px; font-size: 0.72rem; border-radius: 3px;
    display: flex; align-items: center; justify-content: center;
  }
  .offset-ctrl button:hover { background: var(--bg-primary); color: var(--text-primary); }
  .offset-val {
    font-size: 0.64rem; color: var(--text-tertiary); min-width: 36px; text-align: center;
    font-variant-numeric: tabular-nums; cursor: pointer;
  }
  .offset-val.nonzero { color: var(--accent-primary); font-weight: 600; }

  .save-btn {
    background: none; border: none; cursor: pointer; font-size: 0.68rem;
    margin-left: 2px; padding: 2px 4px; border-radius: 3px; transition: all 0.3s;
  }
  .save-btn.saved { color: #4caf50; }
  .save-btn.unsaved { color: #ff9800; animation: pulse-save 1s ease-in-out infinite; }
  .save-btn.unsaved:hover { color: #ff5722; animation: none; }
  @keyframes pulse-save { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

  /* Subtitle dropdown */
  .sub-dropdown { position: relative; }
  .sub-dropdown:hover .sub-menu { display: flex; }
  .btn-sub { font-size: 0.78rem !important; }
  .sub-menu {
    display: none; position: absolute; top: 100%; left: 0; z-index: 50;
    flex-direction: column; background: var(--bg-primary); border: 1px solid var(--border-primary);
    border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); overflow: hidden;
    min-width: 60px;
  }
  .sub-menu button {
    background: none; border: none; padding: 6px 12px; color: var(--text-secondary);
    cursor: pointer; font-size: 0.75rem; text-align: left; white-space: nowrap;
  }
  .sub-menu button:hover { background: var(--bg-tertiary); color: var(--text-primary); }

  /* Search results */
  .search-results { flex: 1; min-height: 0; overflow-y: auto; }
  .results-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 6px 8px; border-bottom: 1px solid var(--border-primary);
    position: sticky; top: 0; background: var(--bg-secondary); z-index: 1;
  }
  .results-title { font-size: 0.78rem; font-weight: 600; color: var(--text-primary); }
  .result-item {
    display: flex; align-items: center; justify-content: space-between; gap: 8px;
    width: 100%; padding: 8px 10px; background: none; border: none;
    border-bottom: 1px solid var(--border-primary); cursor: pointer;
    text-align: left; color: var(--text-secondary);
  }
  .result-item:hover { background: var(--bg-tertiary); }
  .result-main { display: flex; flex-direction: column; gap: 1px; flex: 1; min-width: 0; }
  .result-name { font-size: 0.8rem; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .result-album { font-size: 0.68rem; color: var(--text-tertiary); }
  .result-tags { display: flex; gap: 4px; flex-shrink: 0; }
  .result-tag {
    font-size: 0.62rem; padding: 1px 5px; border-radius: 3px;
    background: var(--bg-tertiary); color: var(--text-tertiary);
  }
  .result-tag.synced { background: rgba(var(--accent-primary-rgb, 0,188,212), 0.15); color: var(--accent-primary); }

  /* Lyrics Area fills remaining space */
  .lyrics-area { flex: 1; min-height: 0; display: flex; flex-direction: column; }

  .lyrics-display {
    flex: 1; min-height: 0; overflow-y: auto;
    background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 10px; padding: 12px;
  }

  .lyrics-toolbar {
    display: flex; align-items: center; justify-content: space-between;
    position: sticky; top: 0; z-index: 2;
    background: var(--bg-secondary); border-bottom: 1px solid var(--border-primary);
    margin: -12px -12px 8px; padding: 8px 12px;
  }

  .lyrics-mode-toggle {
    display: flex; gap: 4px;
    background: var(--bg-tertiary); border-radius: 6px; padding: 2px; width: fit-content;
  }
  .lyrics-mode-toggle button {
    background: none; border: none; padding: 2px 8px; border-radius: 4px;
    font-size: 0.68rem; font-weight: 600; color: var(--text-tertiary); cursor: pointer;
  }
  .lyrics-mode-toggle button.active {
    background: var(--accent-primary); color: #fff;
  }
  .lyrics-mode-toggle.sticky {
    position: sticky; top: 0; z-index: 2;
    background: var(--bg-secondary); padding: 6px 0 8px; margin: -12px 0 4px;
  }

  .scroll-toggle {
    background: none; border: 1px solid var(--border-secondary); color: var(--text-tertiary);
    width: 26px; height: 26px; border-radius: 6px; cursor: pointer;
    display: flex; align-items: center; justify-content: center; font-size: 0.68rem;
  }
  .scroll-toggle:hover { color: var(--text-primary); border-color: var(--text-secondary); }
  .scroll-toggle.active { color: var(--accent-primary); border-color: var(--accent-primary); }

  .sync-btn {
    background: none; border: 1px solid var(--border-secondary); color: var(--text-tertiary);
    width: 26px; height: 26px; border-radius: 6px; cursor: pointer;
    display: flex; align-items: center; justify-content: center; font-size: 0.68rem;
  }
  .sync-btn:hover { color: var(--accent-primary); border-color: var(--accent-primary); }

  /* Synced lyrics */
  .lyrics-display.synced { display: flex; flex-direction: column; gap: 0; }
  .lyric-line {
    background: none; border: none; text-align: left; padding: 4px 8px;
    font-size: 0.95rem; color: var(--text-tertiary); cursor: pointer;
    border-radius: 4px; transition: all 0.2s; line-height: 1.55;
    font-family: inherit;
  }
  .lyric-line:hover { background: var(--bg-tertiary); color: var(--text-secondary); }
  .lyric-line.active {
    color: var(--accent-primary); font-weight: 600;
    background: rgba(var(--accent-primary-rgb, 0,188,212), 0.08);
  }

  /* Plain lyrics */
  .lyrics-text {
    font-size: 0.92rem; color: var(--text-secondary); line-height: 1.65;
    white-space: pre-wrap; word-break: break-word; margin: 0;
    font-family: inherit;
  }

  /* Editor */
  .lyrics-editor { flex: 1; display: flex; flex-direction: column; min-height: 0; }
  .lyrics-editor textarea {
    flex: 1; min-height: 0;
    width: 100%; background: var(--bg-primary); border: 1px solid var(--border-primary);
    border-radius: 8px; padding: 10px; font-size: 0.84rem; color: var(--text-primary);
    resize: none; font-family: inherit; line-height: 1.5;
  }
  .lyrics-editor textarea:focus { border-color: var(--accent-primary); outline: none; }
  .editor-actions { display: flex; gap: 6px; margin-top: 6px; flex-shrink: 0; }

  /* ─── Sync Editor ─── */
  .sync-editor { flex: 1; display: flex; flex-direction: column; min-height: 0; }
  .sync-editor-toolbar {
    display: flex; align-items: center; justify-content: space-between;
    padding: 6px 8px; border-bottom: 1px solid var(--border-primary); flex-shrink: 0;
  }
  .sync-editor-title { font-size: 0.72rem; color: var(--text-secondary); display: flex; align-items: center; gap: 5px; }
  .sync-editor-btns { display: flex; gap: 4px; }
  .sync-editor-list { flex: 1; overflow-y: auto; padding: 4px 0; }
  .sync-edit-row {
    display: flex; align-items: center; gap: 4px; padding: 3px 6px;
    border-bottom: 1px solid var(--border-secondary);
  }
  .sync-edit-row:hover { background: var(--bg-secondary); }
  .sync-edit-row.playing { background: rgba(99,102,241,0.08); }
  .sync-edit-time { display: flex; align-items: center; gap: 2px; flex-shrink: 0; }
  .time-adj {
    width: 20px; height: 22px; border: none; background: var(--bg-tertiary);
    color: var(--text-secondary); cursor: pointer; border-radius: 3px;
    font-size: 0.7rem; display: flex; align-items: center; justify-content: center;
  }
  .time-adj:hover { background: var(--accent-muted); color: var(--accent-primary); }
  .time-input {
    width: 68px; text-align: center; font-family: monospace; font-size: 0.68rem;
    background: var(--bg-primary); border: 1px solid var(--border-primary);
    color: var(--text-primary); border-radius: 3px; padding: 2px 3px;
  }
  .time-input:focus { border-color: var(--accent-primary); outline: none; }
  .time-set {
    width: 22px; height: 22px; border: none; background: var(--bg-tertiary);
    color: var(--accent-primary); cursor: pointer; border-radius: 3px;
    font-size: 0.6rem; display: flex; align-items: center; justify-content: center;
  }
  .time-set:hover { background: var(--accent-muted); }
  .sync-edit-text {
    flex: 1; min-width: 0; background: var(--bg-primary);
    border: 1px solid var(--border-secondary); color: var(--text-primary);
    border-radius: 3px; padding: 3px 6px; font-size: 0.72rem;
  }
  .sync-edit-text:focus { border-color: var(--accent-primary); outline: none; }
  .sync-edit-actions { display: flex; gap: 2px; flex-shrink: 0; }
  .act-btn {
    width: 20px; height: 20px; border: none; background: none;
    color: var(--text-tertiary); cursor: pointer; border-radius: 3px;
    font-size: 0.58rem; display: flex; align-items: center; justify-content: center;
  }
  .act-btn:hover { background: var(--bg-tertiary); color: var(--text-primary); }
  .act-btn.danger:hover { color: var(--status-error); }
  .act-btn:disabled { opacity: 0.3; cursor: not-allowed; }
  .sync-editor-footer {
    display: flex; align-items: center; gap: 6px; padding: 6px 8px;
    border-top: 1px solid var(--border-primary); flex-shrink: 0;
  }
  .sync-hint { font-size: 0.62rem; color: var(--text-quaternary, #64748b); margin-left: auto; }

  .btn-save {
    background: var(--accent-primary); color: #fff; border: none; border-radius: 6px;
    padding: 5px 12px; font-size: 0.78rem; font-weight: 600; cursor: pointer;
    display: flex; align-items: center; gap: 5px;
  }
  .btn-save:hover { filter: brightness(1.1); }

  .lyrics-empty {
    text-align: center; padding: 24px 12px; color: var(--text-tertiary);
  }
  .lyrics-empty i { font-size: 1.8rem; margin-bottom: 6px; opacity: 0.4; }
  .lyrics-empty p { margin: 2px 0; font-size: 0.82rem; }
</style>

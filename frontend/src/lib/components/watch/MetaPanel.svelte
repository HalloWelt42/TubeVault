<!--
  MetaPanel -  Technische Metadaten eines Videos.
  DB-Daten + ffprobe Analyse (Codec, Bitrate, Auflösung, etc.)
  © HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
  SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
-->
<script>
  import { api } from '../../api/client.js';
  import { formatDuration, formatSize, formatDate } from '../../utils/format.js';

  let { video } = $props();
  let meta = $state(null);
  let loading = $state(false);

  $effect(() => {
    if (video?.id) loadMeta();
  });

  async function loadMeta() {
    loading = true;
    try {
      meta = await api.getVideoMetadata(video.id);
    } catch { meta = null; }
    loading = false;
  }

  function fmtBitrate(bps) {
    if (!bps) return '–';
    if (bps > 1_000_000) return `${(bps / 1_000_000).toFixed(1)} Mbps`;
    return `${Math.round(bps / 1000)} kbps`;
  }

  function fmtFps(raw) {
    if (!raw) return '–';
    const parts = raw.split('/');
    if (parts.length === 2) return `${(Number(parts[0]) / Number(parts[1])).toFixed(2)} fps`;
    return raw;
  }

  function copyId() {
    navigator.clipboard.writeText(video.id);
  }
</script>

{#if loading}
  <div class="mp-loading"><i class="fa-solid fa-spinner fa-spin"></i> Metadaten laden…</div>
{:else if meta}
  <div class="mp">
    <!-- Identifikation -->
    <div class="mp-section">
      <h4><i class="fa-solid fa-fingerprint"></i> Identifikation</h4>
      <div class="mp-grid">
        <span class="mp-label">Video-ID</span>
        <span class="mp-val"><code>{video.id}</code> <button class="mp-copy" onclick={copyId} title="Kopieren"><i class="fa-solid fa-copy"></i></button></span>
        <span class="mp-label">Quelle</span>
        <span class="mp-val">{meta.db.source || '–'}</span>
        {#if meta.db.source_url}
          <span class="mp-label">Source-URL</span>
          <span class="mp-val mp-url"><a href={meta.db.source_url} target="_blank" rel="noopener">{meta.db.source_url}</a></span>
        {/if}
        <span class="mp-label">Typ</span>
        <span class="mp-val">{meta.db.video_type || 'video'}</span>
      </div>
    </div>

    <!-- Datei -->
    <div class="mp-section">
      <h4><i class="fa-solid fa-hard-drive"></i> Datei</h4>
      <div class="mp-grid">
        <span class="mp-label">Pfad</span>
        <span class="mp-val mp-path"><code>{meta.db.file_path || '–'}</code></span>
        <span class="mp-label">Dateigröße</span>
        <span class="mp-val">{meta.file.file_exists ? formatSize(meta.file.file_size_actual) : 'Datei nicht gefunden'}</span>
        <span class="mp-label">Status</span>
        <span class="mp-val">{meta.db.status}</span>
        {#if meta.probe.container}
          <span class="mp-label">Container</span>
          <span class="mp-val">{meta.probe.container}</span>
        {/if}
        {#if meta.probe.bitrate}
          <span class="mp-label">Gesamt-Bitrate</span>
          <span class="mp-val">{fmtBitrate(meta.probe.bitrate)}</span>
        {/if}
      </div>
    </div>

    <!-- Video-Stream -->
    {#if meta.probe.video}
      <div class="mp-section">
        <h4><i class="fa-solid fa-film"></i> Video</h4>
        <div class="mp-grid">
          <span class="mp-label">Codec</span>
          <span class="mp-val">{meta.probe.video.codec}{meta.probe.video.profile ? ` (${meta.probe.video.profile})` : ''}</span>
          <span class="mp-label">Auflösung</span>
          <span class="mp-val">{meta.probe.video.width}×{meta.probe.video.height}</span>
          <span class="mp-label">FPS</span>
          <span class="mp-val">{fmtFps(meta.probe.video.fps)}</span>
          {#if meta.probe.video.bitrate}
            <span class="mp-label">Bitrate</span>
            <span class="mp-val">{fmtBitrate(meta.probe.video.bitrate)}</span>
          {/if}
          {#if meta.probe.video.pix_fmt}
            <span class="mp-label">Pixel-Format</span>
            <span class="mp-val">{meta.probe.video.pix_fmt}</span>
          {/if}
        </div>
      </div>
    {/if}

    <!-- Audio-Stream -->
    {#if meta.probe.audio}
      <div class="mp-section">
        <h4><i class="fa-solid fa-volume-high"></i> Audio</h4>
        <div class="mp-grid">
          <span class="mp-label">Codec</span>
          <span class="mp-val">{meta.probe.audio.codec}</span>
          {#if meta.probe.audio.sample_rate}
            <span class="mp-label">Samplerate</span>
            <span class="mp-val">{Number(meta.probe.audio.sample_rate).toLocaleString()} Hz</span>
          {/if}
          <span class="mp-label">Kanäle</span>
          <span class="mp-val">{meta.probe.audio.channels === 2 ? 'Stereo' : meta.probe.audio.channels === 1 ? 'Mono' : `${meta.probe.audio.channels} Kanäle`}</span>
          {#if meta.probe.audio.bitrate}
            <span class="mp-label">Bitrate</span>
            <span class="mp-val">{fmtBitrate(meta.probe.audio.bitrate)}</span>
          {/if}
        </div>
      </div>
    {/if}

    <!-- Zeitstempel -->
    <div class="mp-section">
      <h4><i class="fa-solid fa-clock"></i> Zeitstempel</h4>
      <div class="mp-grid">
        <span class="mp-label">Upload-Datum</span>
        <span class="mp-val">{meta.db.upload_date ? formatDate(meta.db.upload_date) : '–'}</span>
        <span class="mp-label">Download-Datum</span>
        <span class="mp-val">{meta.db.download_date ? formatDate(meta.db.download_date) : '–'}</span>
        <span class="mp-label">Erstellt (DB)</span>
        <span class="mp-val">{meta.db.created_at ? formatDate(meta.db.created_at) : '–'}</span>
        <span class="mp-label">Aktualisiert</span>
        <span class="mp-val">{meta.db.updated_at ? formatDate(meta.db.updated_at) : '–'}</span>
      </div>
    </div>

    <!-- Statistiken -->
    <div class="mp-section">
      <h4><i class="fa-solid fa-chart-bar"></i> Statistiken</h4>
      <div class="mp-grid">
        <span class="mp-label">Wiedergaben</span>
        <span class="mp-val">{meta.db.play_count || 0}</span>
        {#if meta.db.last_played}
          <span class="mp-label">Zuletzt gespielt</span>
          <span class="mp-val">{formatDate(meta.db.last_played)}</span>
        {/if}
        <span class="mp-label">Bewertung</span>
        <span class="mp-val">{meta.db.rating || 0} / 5</span>
        <span class="mp-label">Kapitel</span>
        <span class="mp-val">{meta.chapter_count}</span>
        <span class="mp-label">Verknüpfungen</span>
        <span class="mp-val">{meta.link_count}</span>
        {#if meta.db.view_count}
          <span class="mp-label">YT-Aufrufe</span>
          <span class="mp-val">{Number(meta.db.view_count).toLocaleString()}</span>
        {/if}
        {#if meta.db.like_count}
          <span class="mp-label">YT-Likes</span>
          <span class="mp-val">{Number(meta.db.like_count).toLocaleString()}</span>
        {/if}
      </div>
    </div>
  </div>
{:else}
  <div class="mp-loading">Keine Metadaten verfügbar</div>
{/if}

<style>
  .mp { display: flex; flex-direction: column; gap: 16px; }
  .mp-section { background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 10px; padding: 14px; }
  .mp-section h4 { margin: 0 0 10px 0; font-size: 0.82rem; color: var(--text-tertiary); display: flex; align-items: center; gap: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
  .mp-grid { display: grid; grid-template-columns: 130px 1fr; gap: 6px 12px; }
  .mp-label { font-size: 0.78rem; color: var(--text-tertiary); padding: 2px 0; }
  .mp-val { font-size: 0.82rem; color: var(--text-primary); padding: 2px 0; word-break: break-all; }
  .mp-val code { font-size: 0.78rem; background: var(--bg-tertiary); padding: 2px 6px; border-radius: 4px; }
  .mp-path { max-width: 100%; overflow: hidden; }
  .mp-path code { font-size: 0.72rem; }
  .mp-url { max-width: 100%; overflow: hidden; text-overflow: ellipsis; }
  .mp-url a { color: var(--accent-primary); text-decoration: none; font-size: 0.78rem; }
  .mp-url a:hover { text-decoration: underline; }
  .mp-copy { background: none; border: none; color: var(--text-tertiary); cursor: pointer; padding: 2px 4px; font-size: 0.72rem; }
  .mp-copy:hover { color: var(--accent-primary); }
  .mp-loading { text-align: center; padding: 24px; color: var(--text-tertiary); font-size: 0.85rem; }
</style>

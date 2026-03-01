<!--
  SubtitlePanel -  Untertitel laden, aktivieren, herunterladen.
  © HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
  SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
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

  async function loadSubs() {
    try {
      const res = await api.getSubtitles(videoId);
      subtitles = res.subtitles || [];
    } catch { subtitles = []; }
  }

  function toggle(sub) {
    if (!videoEl) return;
    const tracks = videoEl.textTracks;
    if (activeSub === sub.code) {
      for (let i = 0; i < tracks.length; i++) tracks[i].mode = 'hidden';
      activeSub = null;
      return;
    }
    // Bestehenden Track entfernen
    for (let i = 0; i < tracks.length; i++) tracks[i].mode = 'hidden';
    // Neuen Track hinzufügen
    const track = videoEl.addTextTrack('subtitles', sub.name, sub.code);
    track.mode = 'showing';
    fetch(api.subtitleUrl(videoId, sub.code))
      .then(r => r.text())
      .then(vtt => {
        const blob = new Blob([vtt], { type: 'text/vtt' });
        const url = URL.createObjectURL(blob);
        const trackEl = document.createElement('track');
        trackEl.kind = 'subtitles'; trackEl.srclang = sub.code;
        trackEl.label = sub.name; trackEl.src = url; trackEl.default = true;
        videoEl.appendChild(trackEl);
        trackEl.track.mode = 'showing';
      })
      .catch(() => toast.error('Untertitel laden fehlgeschlagen'));
    activeSub = sub.code;
  }

  async function download(lang) {
    try {
      const res = await api.downloadSubtitles(videoId, lang);
      if (res.count > 0) {
        toast.success(`${res.count} Untertitel geladen (${lang.toUpperCase()})`);
        await loadSubs();
      } else {
        toast.info(`Keine ${lang.toUpperCase()} Untertitel verfügbar`);
      }
    } catch (e) { toast.error(e.message); }
  }
</script>

{#if subtitles.length === 0}
  <div class="tab-empty">
    <p>Keine Untertitel vorhanden.</p>
    <div class="dl-row">
      <button class="btn-sm" onclick={() => download('de')}>🇩🇪 Deutsch laden</button>
      <button class="btn-sm" onclick={() => download('en')}>🇬🇧 English laden</button>
      <button class="btn-sm" onclick={() => download('all')}>🌐 Alle laden</button>
    </div>
  </div>
{:else}
  <div class="sub-list">
    {#each subtitles as sub}
      <button class="sub-item" class:active={activeSub === sub.code} onclick={() => toggle(sub)}>
        <span class="sub-flag">{sub.code.includes('de') ? '🇩🇪' : sub.code.includes('en') ? '🇬🇧' : sub.code.includes('fr') ? '🇫🇷' : sub.code.includes('es') ? '🇪🇸' : '🌐'}</span>
        <span class="sub-name">
          {sub.name}
          {#if sub.code.startsWith('a.')}<span class="sub-auto">(auto)</span>{/if}
        </span>
        <span class="sub-size">{formatSize(sub.size)}</span>
        {#if activeSub === sub.code}
          <span class="sub-active">Aktiv</span>
        {/if}
      </button>
    {/each}
  </div>
  <div class="dl-row" style="margin-top:10px">
    <button class="btn-sm" onclick={() => download('de')}>+ Deutsch</button>
    <button class="btn-sm" onclick={() => download('en')}>+ English</button>
    <button class="btn-sm" onclick={() => download('all')}>+ Alle</button>
  </div>
{/if}

<style>
  .tab-empty { text-align: center; padding: 20px; color: var(--text-tertiary); }
  .tab-empty p { margin-bottom: 12px; }
  .dl-row { display: flex; gap: 8px; flex-wrap: wrap; }
  .sub-list { display: flex; flex-direction: column; gap: 4px; }
  .sub-item { display: flex; align-items: center; gap: 10px; padding: 8px 12px; background: var(--bg-secondary); border: 1px solid var(--border-secondary); border-radius: 8px; cursor: pointer; font-size: 0.82rem; color: var(--text-primary); }
  .sub-item:hover { border-color: var(--accent-primary); }
  .sub-item.active { border-color: var(--accent-primary); background: rgba(var(--accent-rgb, 59,130,246), 0.08); }
  .sub-name { font-weight: 500; flex: 1; }
  .sub-flag { font-size: 1rem; flex-shrink: 0; }
  .sub-auto { font-size: 0.65rem; color: var(--text-tertiary); font-weight: 400; margin-left: 4px; }
  .sub-size { font-size: 0.72rem; color: var(--text-tertiary); }
  .sub-active { font-size: 0.7rem; font-weight: 600; color: var(--accent-primary); }
</style>

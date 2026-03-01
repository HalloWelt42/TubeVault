<!--
  AdMarkerPanel -  Werbemarker-Verwaltung (manuell + SponsorBlock).
  © HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
  SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
-->
<script>
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';
  import { formatDuration } from '../../utils/format.js';

  let {
    videoId,
    adMarkers = $bindable([]),
    onSeek = () => {},
  } = $props();

  let newStart = $state('');
  let newEnd = $state('');
  let loadingSB = $state(false);

  function parseTime(val) {
    if (!val?.trim()) return null;
    val = val.trim();
    if (/^\d+$/.test(val)) return Number(val);
    const p = val.split(':').map(Number);
    if (p.length === 2) return p[0] * 60 + p[1];
    if (p.length === 3) return p[0] * 3600 + p[1] * 60 + p[2];
    return null;
  }

  async function loadMarkers() {
    try {
      const res = await api.getAdMarkers(videoId);
      adMarkers = res.ad_markers || [];
    } catch { adMarkers = []; }
  }

  async function addMarker() {
    const s = parseTime(newStart), e = parseTime(newEnd);
    if (s == null || e == null || e <= s) {
      toast.error('Ungültige Zeiten'); return;
    }
    try {
      await api.addAdMarker(videoId, { start_time: s, end_time: e, label: 'Werbung', source: 'manual' });
      toast.success(`Werbemarke ${formatDuration(s)}–${formatDuration(e)}`);
      newStart = ''; newEnd = '';
      await loadMarkers();
    } catch (err) { toast.error(err.message); }
  }

  async function removeMarker(id) {
    try {
      await api.deleteAdMarker(id);
      toast.success('Marker entfernt');
      await loadMarkers();
    } catch (err) { toast.error(err.message); }
  }

  async function fetchSB(replace = false) {
    loadingSB = true;
    try {
      const res = await api.fetchSponsorBlock(videoId, replace);
      if (res.imported > 0) {
        toast.success(`${res.imported} SponsorBlock-Segmente geladen`);
        await loadMarkers();
      } else { toast.info('Keine SponsorBlock-Daten verfügbar'); }
    } catch (err) { toast.error(err.message); }
    loadingSB = false;
  }

  async function clearSB() {
    try {
      const res = await api.clearSponsorBlock(videoId);
      toast.success(`${res.removed} SB-Marker entfernt`);
      await loadMarkers();
    } catch (err) { toast.error(err.message); }
  }
</script>

{#if adMarkers.length > 0}
  <div class="marker-list">
    {#each adMarkers as m}
      <div class="marker-item">
        <span class="src-badge" class:sb={m.source === 'sponsorblock'}
              title={m.source === 'sponsorblock' ? `SB: ${m.category || 'sponsor'}${m.votes != null ? ' · ' + m.votes + ' Votes' : ''}` : 'Eigene Marke'}>
          <i class={m.source === 'sponsorblock' ? 'fa-solid fa-shield-halved' : 'fa-solid fa-user'}></i>
        </span>
        <span class="range">{formatDuration(m.start_time)} -  {formatDuration(m.end_time)}</span>
        <span class="dur">{formatDuration(m.end_time - m.start_time)}</span>
        <span class="label" class:sb-cat={m.source === 'sponsorblock'}>{m.label || 'Werbung'}</span>
        <button class="seek-btn" title="Zum Start" onclick={() => onSeek(m.start_time)}>
          <i class="fa-solid fa-play"></i>
        </button>
        <button class="del-btn" title="Entfernen" onclick={() => removeMarker(m.id)}>
          <i class="fa-solid fa-xmark"></i>
        </button>
      </div>
    {/each}
  </div>
{:else}
  <p class="hint">Keine Werbemarken gesetzt. Markierte Abschnitte werden automatisch übersprungen.</p>
{/if}

<div class="sb-actions">
  <button class="btn-sm" onclick={() => fetchSB(false)} disabled={loadingSB}>
    {#if loadingSB}<i class="fa-solid fa-spinner fa-spin"></i> Laden…{:else}<i class="fa-solid fa-shield-halved"></i> SponsorBlock laden{/if}
  </button>
  {#if adMarkers.some(m => m.source === 'sponsorblock')}
    <button class="btn-sm" onclick={() => fetchSB(true)} disabled={loadingSB} title="SB-Marker ersetzen">
      <i class="fa-solid fa-rotate"></i> SB neu laden
    </button>
    <button class="btn-sm btn-danger-ghost" onclick={clearSB} title="Alle SB-Marker entfernen">
      <i class="fa-solid fa-trash"></i> SB entfernen
    </button>
  {/if}
</div>

<div class="add-form">
  <div class="form-row">
    <input type="text" class="input flex-1" placeholder="Start (mm:ss)" bind:value={newStart} />
    <input type="text" class="input flex-1" placeholder="Ende (mm:ss)" bind:value={newEnd}
           onkeydown={(e) => e.key === 'Enter' && addMarker()} />
    <button class="btn-sm accent" onclick={addMarker}>
      <i class="fa-solid fa-plus"></i> Setzen
    </button>
  </div>
  <span class="form-hint">Zeitformat: mm:ss oder hh:mm:ss oder Sekunden</span>
</div>

<style>
  .marker-list { display: flex; flex-direction: column; gap: 4px; }
  .marker-item { display: flex; align-items: center; gap: 8px; padding: 5px 8px; border-radius: 6px; font-size: 0.8rem; }
  .marker-item:hover { background: var(--bg-secondary); }
  .src-badge { width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.6rem; background: var(--bg-tertiary); color: var(--text-tertiary); }
  .src-badge.sb { background: rgba(255,140,0,0.12); color: #ff8c00; }
  .range { font-family: monospace; color: var(--accent-primary); font-weight: 600; font-size: 0.78rem; }
  .dur { font-size: 0.72rem; color: var(--text-tertiary); }
  .label { font-size: 0.76rem; color: var(--text-secondary); flex: 1; }
  .label.sb-cat { font-style: italic; }
  .seek-btn, .del-btn { background: none; border: none; cursor: pointer; color: var(--text-tertiary); padding: 3px 5px; border-radius: 4px; font-size: 0.68rem; opacity: 0.3; }
  .seek-btn:hover { opacity: 1; color: var(--accent-primary); }
  .del-btn:hover { opacity: 1; color: var(--status-error); }
  .sb-actions { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
  .btn-danger-ghost { color: var(--status-error) !important; border-color: var(--status-error) !important; }
  .add-form { margin-top: 14px; }
  .form-row { display: flex; gap: 6px; align-items: center; }
  .input { padding: 6px 10px; border: 1px solid var(--border-primary); border-radius: 6px; background: var(--bg-secondary); color: var(--text-primary); font-size: 0.82rem; }
  .flex-1 { flex: 1; }
  .form-hint { font-size: 0.68rem; color: var(--text-tertiary); display: block; margin-top: 4px; }
  .hint { color: var(--text-tertiary); font-size: 0.85rem; }
</style>

<!--
  AdMarkerPanel – Werbestellen eines Videos: eigene Marken und die des
  Werbemarken-Dienstes. Werbestellen werden beim Abspielen übersprungen,
  fehlen im Transkript und in Downloads. Die Marken des Dienstes gleicht das
  Backend beim Öffnen selbst ab; hier lässt sich das sofort anstoßen.
  © HalloWelt42
-->
<script>
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';
  import { formatDuration, formatDateRelative } from '../../utils/format.js';

  let {
    videoId,
    adMarkers = $bindable([]),
    skipRanges = $bindable([]),
    checkedAt = $bindable(null),   // zuletzt beim Dienst abgeglichen
  } = $props();

  let newStart = $state('');
  let newEnd = $state('');
  let refreshing = $state(false);

  function parseTime(val) {
    if (!val?.trim()) return null;
    val = val.trim();
    if (/^\d+$/.test(val)) return Number(val);
    const p = val.split(':').map(Number);
    if (p.length === 2) return p[0] * 60 + p[1];
    if (p.length === 3) return p[0] * 3600 + p[1] * 60 + p[2];
    return null;
  }

  function take(res) {
    adMarkers = res.ad_markers || [];
    skipRanges = res.skip_ranges || [];
    checkedAt = res.checked_at || null;
  }

  async function loadMarkers() {
    try { take(await api.getAdMarkers(videoId)); } catch { /* Stand bleibt */ }
  }

  async function addMarker() {
    const s = parseTime(newStart), e = parseTime(newEnd);
    if (s == null || e == null || e <= s) {
      toast.error('Ungültige Zeiten'); return;
    }
    try {
      await api.addAdMarker(videoId, { start_time: s, end_time: e, label: 'Werbung' });
      toast.success(`Werbestelle ${formatDuration(s)} - ${formatDuration(e)} gesetzt`);
      newStart = ''; newEnd = '';
      await loadMarkers();
    } catch (err) { toast.error(err.message); }
  }

  async function removeMarker(id) {
    try {
      await api.deleteAdMarker(id);
      toast.success('Werbestelle entfernt');
      await loadMarkers();
    } catch (err) { toast.error(err.message); }
  }

  async function refresh() {
    refreshing = true;
    try {
      const res = await api.refreshAdMarkers(videoId);
      take(res);
      toast.success(res.changed ? `Abgeglichen: ${res.found} Stellen vom Dienst` : 'Abgeglichen: unverändert');
    } catch (err) { toast.error(err.message); }
    refreshing = false;
  }
</script>

{#if adMarkers.length > 0}
  <div class="marker-list">
    {#each adMarkers as m}
      {@const own = (m.source || 'manual') === 'manual'}
      <div class="marker-item" class:inactive={!m.hidden}>
        <span class="src-badge" class:service={!own}
              title={own ? 'Eigene Werbestelle' : `Vom Werbemarken-Dienst${m.votes != null ? ' · ' + m.votes + ' Stimmen' : ''}`}>
          <i class={own ? 'fa-solid fa-user' : 'fa-solid fa-shield-halved'}></i>
        </span>
        <span class="range">{formatDuration(m.start_time)} - {formatDuration(m.end_time)}</span>
        <span class="dur">{formatDuration(m.end_time - m.start_time)}</span>
        <span class="label">{m.label || 'Werbung'}</span>
        {#if own}
          <button class="del-btn" title="Eigene Werbestelle entfernen" onclick={() => removeMarker(m.id)}>
            <i class="fa-solid fa-xmark"></i>
          </button>
        {/if}
      </div>
    {/each}
  </div>
{:else}
  <p class="hint">Keine Werbestellen bekannt.</p>
{/if}

<p class="hint">
  Werbestellen werden übersprungen und fehlen in Transkript und Downloads; die Datei bleibt vollständig.
</p>

<div class="actions">
  <button class="btn-sm" onclick={refresh} disabled={refreshing}
          title="Der Dienst wird mit der Zeit vollständiger; beim Öffnen wird regelmäßig selbst nachgefragt">
    {#if refreshing}<i class="fa-solid fa-spinner fa-spin"></i> Gleiche ab...{:else}<i class="fa-solid fa-rotate"></i> Jetzt abgleichen{/if}
  </button>
  <span class="checked">{checkedAt ? `zuletzt abgeglichen ${formatDateRelative(checkedAt)}` : 'noch nicht abgeglichen'}</span>
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
  .marker-item.inactive { opacity: 0.5; }
  .src-badge { width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.6rem; background: var(--bg-tertiary); color: var(--text-tertiary); }
  .src-badge.service { background: rgba(255,140,0,0.12); color: #ff8c00; }
  .range { font-family: monospace; color: var(--accent-primary); font-weight: 600; font-size: 0.78rem; }
  .dur { font-size: 0.72rem; color: var(--text-tertiary); }
  .label { font-size: 0.76rem; color: var(--text-secondary); flex: 1; }
  .del-btn { background: none; border: none; cursor: pointer; color: var(--text-tertiary); padding: 3px 5px; border-radius: 4px; font-size: 0.68rem; opacity: 0.3; }
  .del-btn:hover { opacity: 1; color: var(--status-error); }
  .actions { display: flex; gap: 10px; margin-top: 12px; align-items: center; flex-wrap: wrap; }
  .checked { font-size: 0.72rem; color: var(--text-tertiary); }
  .add-form { margin-top: 14px; }
  .form-row { display: flex; gap: 6px; align-items: center; }
  .input { padding: 6px 10px; border: 1px solid var(--border-primary); border-radius: 6px; background: var(--bg-secondary); color: var(--text-primary); font-size: 0.82rem; }
  .flex-1 { flex: 1; }
  .form-hint { font-size: 0.68rem; color: var(--text-tertiary); display: block; margin-top: 4px; }
  .hint { color: var(--text-tertiary); font-size: 0.85rem; }
</style>

<!--
  StreamPanel – Stream-Analyse, Audio-Switching, Offset, Kombinationen.
  © HalloWelt42
-->
<script>
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';

  let {
    videoId,
    videoEl = null,
  } = $props();

  let streams = $state([]);
  let combos = $state([]);
  let analyzing = $state(false);
  let selectedAudio = $state(null);
  let audioOffset = $state(0);
  let newComboName = $state('');

  async function loadStreams() {
    analyzing = true;
    try {
      const res = await api.analyzeStreams(videoId);
      streams = res.streams || [];
      if (streams.length > 0) toast.success(`${streams.length} Streams erkannt`);
      await loadCombos();
    } catch (e) { toast.error(e.message); }
    analyzing = false;
  }

  async function loadCombos() {
    try {
      const res = await api.getStreamCombos(videoId);
      combos = res.combos || [];
    } catch { combos = []; }
  }

  function switchAudio(s) {
    if (!videoEl) return;
    selectedAudio = s.id;
    const pos = videoEl.currentTime;
    const playing = !videoEl.paused;
    videoEl.src = api.streamUrl(videoId, { audio_stream: s.stream_index });
    videoEl.currentTime = pos;
    if (playing) videoEl.play();
    toast.success(`Audio: ${s.language || s.codec} (${s.channels || '?'}ch)`);
  }

  function adjustOffset(delta) { audioOffset += delta; applyOffset(); }

  function applyOffset() {
    if (!videoEl) return;
    // AudioContext delay simulation via playbackRate nudge
    // In practice this is a visual indicator; real offset requires server-side
  }

  async function saveCombo() {
    if (!newComboName.trim()) return;
    try {
      const audioStream = streams.find(s => s.id === selectedAudio);
      await api.saveStreamCombo(videoId, {
        name: newComboName.trim(),
        audio_stream_index: audioStream?.stream_index,
        audio_codec: audioStream?.codec,
        audio_lang: audioStream?.language,
        audio_offset_ms: audioOffset,
        video_quality: streams.find(s => s.stream_type === 'video')?.resolution,
      });
      toast.success('Kombination gespeichert');
      newComboName = '';
      await loadCombos();
    } catch (e) { toast.error(e.message); }
  }

  async function deleteCombo(id) {
    try {
      await api.deleteStreamCombo(id);
      toast.success('Kombination gelöscht');
      await loadCombos();
    } catch (e) { toast.error(e.message); }
  }

  function applyCombo(c) {
    if (!videoEl) return;
    const pos = videoEl.currentTime;
    const playing = !videoEl.paused;
    if (c.audio_stream_index != null) {
      videoEl.src = api.streamUrl(videoId, { audio_stream: c.audio_stream_index });
    }
    audioOffset = c.audio_offset_ms || 0;
    videoEl.currentTime = pos;
    if (playing) videoEl.play();
    toast.success(`Kombination "${c.name}" geladen`);
  }
</script>

{#if streams.length === 0}
  <div class="tab-empty">
    <p>Streams noch nicht analysiert.</p>
    <button class="btn-sm" onclick={loadStreams} disabled={analyzing}>
      {analyzing ? 'Analysiere…' : 'FFprobe Analyse starten'}
    </button>
  </div>
{:else}
  <div class="stream-sections">
    <!-- Video-Streams -->
    <div class="stream-group">
      <h3 class="group-title"><i class="fa-solid fa-video"></i> Video-Streams</h3>
      {#each streams.filter(s => s.stream_type === 'video') as s}
        <div class="stream-item">
          <span class="codec">{s.codec}</span>
          {#if s.resolution}<span class="tag">{s.resolution}</span>{/if}
          {#if s.fps}<span class="tag">{s.fps} fps</span>{/if}
          {#if s.bitrate}<span class="tag">{Math.round(s.bitrate / 1000)} kbps</span>{/if}
          {#if s.is_default}<span class="default-badge">Standard</span>{/if}
        </div>
      {/each}
    </div>

    <!-- Audio-Streams -->
    <div class="stream-group">
      <h3 class="group-title"><i class="fa-solid fa-headphones"></i> Audio-Streams</h3>
      {#each streams.filter(s => s.stream_type === 'audio') as s}
        <button class="stream-item selectable" class:selected={selectedAudio === s.id}
                onclick={() => switchAudio(s)}>
          <span class="codec">{s.codec}</span>
          {#if s.language}<span class="tag"><i class="fa-solid fa-globe"></i> {s.language}</span>{/if}
          {#if s.channels}<span class="tag">{s.channels}ch</span>{/if}
          {#if s.sample_rate}<span class="tag">{s.sample_rate} Hz</span>{/if}
          {#if s.bitrate}<span class="tag">{Math.round(s.bitrate / 1000)} kbps</span>{/if}
          {#if s.is_default}<span class="default-badge">Standard</span>{/if}
          {#if selectedAudio === s.id}<span class="active-badge"><i class="fa-solid fa-play"></i> Aktiv</span>{/if}
        </button>
      {/each}
    </div>
  </div>

  <!-- Audio-Offset -->
  <div class="offset-section">
    <label class="offset-label">
      Audio-Offset: <strong>{audioOffset > 0 ? '+' : ''}{audioOffset}ms</strong>
    </label>
    <div class="offset-controls">
      <button class="btn-xs" onclick={() => adjustOffset(-100)}>-100</button>
      <button class="btn-xs" onclick={() => adjustOffset(-10)}>-10</button>
      <input type="range" min="-2000" max="2000" step="10" bind:value={audioOffset}
             oninput={applyOffset} class="offset-slider" />
      <button class="btn-xs" onclick={() => adjustOffset(10)}>+10</button>
      <button class="btn-xs" onclick={() => adjustOffset(100)}>+100</button>
      <button class="btn-xs" onclick={() => { audioOffset = 0; applyOffset(); }}>Reset</button>
    </div>
  </div>

  <!-- Kombinationen -->
  <div class="combos-section">
    <h3 class="group-title"><i class="fa-solid fa-floppy-disk"></i> Gespeicherte Kombinationen</h3>
    {#if combos.length > 0}
      <div class="combo-list">
        {#each combos as c}
          <div class="combo-item">
            <span class="combo-name">{c.name}</span>
            <span class="combo-detail">{c.video_quality || '?'} + {c.audio_codec || '?'}{c.audio_lang ? ` (${c.audio_lang})` : ''}</span>
            {#if c.audio_offset_ms !== 0}<span class="combo-offset">{c.audio_offset_ms}ms</span>{/if}
            {#if c.is_default}<span class="default-badge">Standard</span>{/if}
            <button class="btn-xs" onclick={() => applyCombo(c)}>Laden</button>
            <button class="btn-xs danger" title="Löschen" onclick={() => deleteCombo(c.id)}><i class="fa-solid fa-xmark"></i></button>
          </div>
        {/each}
      </div>
    {:else}
      <p class="combo-empty">Noch keine Kombinationen gespeichert.</p>
    {/if}
    <div class="combo-save">
      <input type="text" bind:value={newComboName} placeholder="Kombination benennen…" class="combo-input" />
      <button class="btn-sm" onclick={saveCombo} disabled={!newComboName.trim()}><i class="fa-solid fa-floppy-disk"></i> Speichern</button>
    </div>
  </div>

  <button class="btn-sm" onclick={loadStreams} style="margin-top:10px" disabled={analyzing}>
    <i class="fa-solid fa-rotate-right"></i> Neu analysieren
  </button>
{/if}

<style>
  .tab-empty { text-align: center; padding: 20px; color: var(--text-tertiary); }
  .tab-empty p { margin-bottom: 12px; }
  .stream-sections { display: flex; flex-direction: column; gap: 16px; }
  .stream-group { display: flex; flex-direction: column; gap: 4px; }
  .group-title { font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); display: flex; align-items: center; gap: 6px; margin: 0 0 4px; }
  .stream-item { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-radius: 6px; font-size: 0.8rem; border: 1px solid transparent; }
  .stream-item:hover { background: var(--bg-secondary); }
  .stream-item.selectable { cursor: pointer; background: var(--bg-secondary); border: 1px solid var(--border-secondary); }
  .stream-item.selectable:hover { border-color: var(--accent-primary); }
  .stream-item.selected { border-color: var(--accent-primary); background: rgba(var(--accent-rgb, 59,130,246), 0.06); }
  .codec { font-weight: 600; color: var(--text-primary); }
  .tag { font-size: 0.72rem; background: var(--bg-tertiary); padding: 2px 6px; border-radius: 4px; color: var(--text-secondary); }
  .default-badge { font-size: 0.68rem; color: var(--accent-primary); font-weight: 600; }
  .active-badge { font-size: 0.7rem; font-weight: 600; color: var(--status-success); display: flex; align-items: center; gap: 3px; }
  .offset-section { margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--border-secondary); }
  .offset-label { font-size: 0.82rem; color: var(--text-secondary); margin-bottom: 6px; display: block; }
  .offset-controls { display: flex; align-items: center; gap: 4px; }
  .offset-slider { flex: 1; accent-color: var(--accent-primary); }
  .btn-xs { padding: 3px 8px; font-size: 0.72rem; border: 1px solid var(--border-primary); border-radius: 4px; background: var(--bg-secondary); color: var(--text-secondary); cursor: pointer; }
  .btn-xs:hover { border-color: var(--accent-primary); color: var(--accent-primary); }
  .btn-xs.danger:hover { border-color: var(--status-error); color: var(--status-error); }
  .combos-section { margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--border-secondary); }
  .combo-list { display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; }
  .combo-item { display: flex; align-items: center; gap: 8px; padding: 5px 8px; font-size: 0.8rem; border-radius: 6px; }
  .combo-item:hover { background: var(--bg-secondary); }
  .combo-name { font-weight: 500; color: var(--text-primary); }
  .combo-detail { font-size: 0.72rem; color: var(--text-tertiary); flex: 1; }
  .combo-offset { font-size: 0.7rem; color: var(--accent-primary); font-family: monospace; }
  .combo-empty { font-size: 0.82rem; color: var(--text-tertiary); }
  .combo-save { display: flex; gap: 6px; margin-top: 8px; }
  .combo-input { flex: 1; padding: 6px 10px; border: 1px solid var(--border-primary); border-radius: 6px; background: var(--bg-secondary); color: var(--text-primary); font-size: 0.82rem; }
</style>

<!--
  TubeVault -  StreamDialog v1.5.83
  Zentrale Download-Optionen: Video + Audio separat wählbar.
  Progressive Streams (V+A) deaktivieren Audio-Auswahl automatisch.
  © HalloWelt42 -  Private Nutzung
-->
<script>
  let {
    dialog = null,
    showAudioOnly = true,
    forceAudioOnly = false,
    onclose = () => {},
    ondownload = () => {},
  } = $props();

  function fmtSize(bytes) {
    if (!bytes) return '?';
    if (bytes > 1073741824) return (bytes / 1073741824).toFixed(1) + ' GB';
    return (bytes / 1048576).toFixed(0) + ' MB';
  }

  function handleKeydown(e) {
    if (e.key === 'Escape') onclose();
  }

  let selectedVideo = $derived(
    dialog?.videoStreams?.find(s => s.itag === dialog.selectedVideoItag) || null
  );

  let isProgressive = $derived(selectedVideo?.is_progressive ?? false);

  let selectedAudio = $derived(
    dialog?.audioStreams?.find(s => s.itag === dialog.selectedAudioItag) || null
  );

  // Gesamtgröße Schätzung
  let estimatedSize = $derived(() => {
    let total = 0;
    if (selectedVideo?.file_size) total += selectedVideo.file_size;
    if (!isProgressive && selectedAudio?.file_size) total += selectedAudio.file_size;
    return total > 0 ? fmtSize(total) : null;
  });
</script>

{#if dialog}
  <div class="sd-backdrop" onclick={onclose} role="presentation">
    <div class="sd-dialog" onclick={(e) => e.stopPropagation()} onkeydown={handleKeydown} role="dialog" tabindex="-1">
      <div class="sd-header">
        <h2>Download-Optionen</h2>
        <button class="sd-close" title="Schließen" onclick={onclose}><i class="fa-solid fa-xmark"></i></button>
      </div>

      {#if dialog.title}
        <p class="sd-subtitle">{dialog.title}</p>
      {/if}

      {#if dialog.loading}
        <div class="sd-loading"><i class="fa-solid fa-spinner fa-spin"></i> Streams werden geladen…</div>
      {:else}
        {#if dialog.alreadyDownloaded}
          <div class="sd-warn"><i class="fa-solid fa-triangle-exclamation"></i> Bereits heruntergeladen.</div>
        {/if}

        {#if forceAudioOnly}
          <!-- AUDIO-ONLY KANAL -->
          <div class="sd-audio-only-banner">
            <i class="fa-solid fa-podcast"></i> Audio-Only Kanal -  nur Audiospuren verfügbar
          </div>

          <div class="sd-section">
            <h3><i class="fa-solid fa-music"></i> Audio-Stream wählen</h3>
            <div class="sd-list">
              {#each dialog.audioStreams || [] as s}
                <label class="sd-option" class:selected={dialog.selectedAudioItag === s.itag}>
                  <input type="radio" name="sd-audio-stream" value={s.itag}
                    checked={dialog.selectedAudioItag === s.itag}
                    onchange={() => dialog.selectedAudioItag = s.itag} />
                  <span class="sd-quality">{s.quality}</span>
                  <span class="sd-codec">{s.codec}</span>
                  <span class="sd-size">{fmtSize(s.file_size)}</span>
                </label>
              {/each}
            </div>
          </div>

          <div class="sd-actions">
            <div class="sd-buttons">
              <button class="sd-btn-ghost" onclick={onclose}>Abbrechen</button>
              <button class="sd-btn-queue" onclick={() => ondownload({
                audioItag: dialog.selectedAudioItag,
                audioOnly: true, priority: 0
              })}>
                <i class="fa-solid fa-list"></i> In Queue
              </button>
              <button class="sd-btn-primary" onclick={() => ondownload({
                audioItag: dialog.selectedAudioItag,
                audioOnly: true, priority: 10
              })}>
                <i class="fa-solid fa-bolt"></i> Sofort laden
              </button>
            </div>
          </div>
        {:else}

        <!-- Video-Streams -->
        <div class="sd-section">
          <h3><i class="fa-solid fa-video"></i> Video-Stream wählen</h3>
          <div class="sd-list">
            {#each dialog.videoStreams || [] as s}
              <label class="sd-option" class:selected={dialog.selectedVideoItag === s.itag}>
                <input type="radio" name="sd-video-stream" value={s.itag}
                  checked={dialog.selectedVideoItag === s.itag}
                  onchange={() => {
                    dialog.selectedVideoItag = s.itag;
                    if (s.is_progressive) dialog.selectedAudioItag = null;
                  }} />
                <span class="sd-quality">{s.quality}</span>
                <span class="sd-codec">{s.codec}</span>
                <span class="sd-size">{fmtSize(s.file_size)}</span>
                {#if s.fps && s.fps > 30}<span class="sd-fps">{s.fps}fps</span>{/if}
                {#if s.is_progressive}
                  <span class="sd-tag prog">V+A</span>
                {:else}
                  <span class="sd-tag adaptive">nur Video</span>
                {/if}
              </label>
            {/each}
          </div>
        </div>

        <!-- Audio-Streams -->
        <div class="sd-section" class:sd-disabled={isProgressive}>
          <h3>
            <i class="fa-solid fa-music"></i> Audio-Stream
            {#if isProgressive}
              <span class="sd-hint-inline">– bereits im Video enthalten</span>
            {/if}
          </h3>
          {#if !isProgressive}
            <div class="sd-list">
              {#each dialog.audioStreams || [] as s}
                <label class="sd-option" class:selected={dialog.selectedAudioItag === s.itag}>
                  <input type="radio" name="sd-audio-stream" value={s.itag}
                    checked={dialog.selectedAudioItag === s.itag}
                    onchange={() => dialog.selectedAudioItag = s.itag} />
                  <span class="sd-quality">{s.quality}</span>
                  <span class="sd-codec">{s.codec}</span>
                  <span class="sd-size">{fmtSize(s.file_size)}</span>
                </label>
              {/each}
            </div>
          {/if}
        </div>

        <!-- Optionen -->
        <div class="sd-options">
          {#if !isProgressive && !dialog.selectedAudioItag}
            <label class="sd-check">
              <input type="checkbox" bind:checked={dialog.mergeAudio} />
              Bestes Audio automatisch einmischen
            </label>
          {/if}
          {#if !isProgressive && dialog.selectedVideoItag && !dialog.selectedAudioItag && !dialog.mergeAudio}
            <p class="sd-hint"><i class="fa-solid fa-triangle-exclamation"></i> Kein Audio gewählt -  Video wird stumm sein!</p>
          {/if}
          {#if isProgressive}
            <p class="sd-hint sd-hint-ok"><i class="fa-solid fa-circle-check"></i> Progressiver Stream -  Audio ist enthalten.</p>
          {/if}
        </div>

        <!-- Untertitel -->
        {#if (dialog.captions || []).length > 0}
          <div class="sd-section small">
            <h3><i class="fa-solid fa-closed-captioning"></i> Untertitel verfügbar</h3>
            <span class="sd-captions">{dialog.captions.map(c => c.name || c.code).join(', ')}</span>
          </div>
        {/if}

        <!-- Zusammenfassung + Buttons -->
        <div class="sd-actions">
          {#if dialog.selectedVideoItag}
            <div class="sd-summary">
              <span class="sd-sum-item">🎬 {selectedVideo?.quality} {selectedVideo?.codec}</span>
              {#if isProgressive}
                <span class="sd-sum-item sd-sum-ok">✓ Audio enthalten</span>
              {:else if selectedAudio}
                <span class="sd-sum-item">🎵 {selectedAudio.quality} {selectedAudio.codec}</span>
              {:else if dialog.mergeAudio}
                <span class="sd-sum-item">🎵 Auto (bestes Audio)</span>
              {:else}
                <span class="sd-sum-item sd-sum-warn">⚠ Kein Audio</span>
              {/if}
              {#if estimatedSize()}
                <span class="sd-sum-item">≈ {estimatedSize()}</span>
              {/if}
            </div>
          {/if}
          <div class="sd-buttons">
            <button class="sd-btn-ghost" onclick={onclose}>Abbrechen</button>
            {#if showAudioOnly}
              <button class="sd-btn-audio" onclick={() => ondownload({ audioOnly: true, priority: 0 })}>
                <i class="fa-solid fa-music"></i> Nur Audio
              </button>
            {/if}
            <button class="sd-btn-queue" onclick={() => ondownload({
              itag: dialog.selectedVideoItag,
              audioItag: dialog.selectedAudioItag,
              mergeAudio: dialog.mergeAudio ?? true,
              priority: 0
            })} disabled={!dialog.selectedVideoItag}>
              <i class="fa-solid fa-list"></i> In Queue
            </button>
            <button class="sd-btn-primary" onclick={() => ondownload({
              itag: dialog.selectedVideoItag,
              audioItag: dialog.selectedAudioItag,
              mergeAudio: dialog.mergeAudio ?? true,
              priority: 10
            })} disabled={!dialog.selectedVideoItag}>
              <i class="fa-solid fa-bolt"></i> Sofort laden
            </button>
          </div>
        </div>
        {/if}
      {/if}
    </div>
  </div>
{/if}

<style>
  .sd-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 1000; display: flex; align-items: center; justify-content: center; padding: 20px; }
  .sd-dialog { background: var(--bg-primary); border-radius: 16px; max-width: 600px; width: 100%; max-height: 85vh; overflow-y: auto; padding: 24px; }
  .sd-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
  .sd-header h2 { font-size: 1.15rem; color: var(--text-primary); margin: 0; }
  .sd-close { background: none; border: none; font-size: 1.2rem; cursor: pointer; color: var(--text-tertiary); padding: 4px 8px; }
  .sd-close:hover { color: var(--text-primary); }
  .sd-subtitle { font-size: 0.82rem; color: var(--text-secondary); margin: 0 0 16px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .sd-loading { text-align: center; padding: 40px; color: var(--text-tertiary); display: flex; align-items: center; justify-content: center; gap: 10px; }
  .sd-warn { background: rgba(239,168,68,0.1); color: #d97706; padding: 8px 12px; border-radius: 8px; font-size: 0.82rem; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
  .sd-audio-only-banner { background: rgba(99,179,237,0.12); color: #63b3ed; padding: 10px 14px; border-radius: 8px; font-size: 0.85rem; margin-bottom: 14px; display: flex; align-items: center; gap: 8px; font-weight: 600; }
  .sd-section { margin-bottom: 16px; }
  .sd-section h3 { font-size: 0.82rem; color: var(--text-secondary); margin: 0 0 8px; display: flex; align-items: center; gap: 6px; }
  .sd-section.small h3 { font-size: 0.75rem; }
  .sd-disabled { opacity: 0.4; pointer-events: none; }
  .sd-hint-inline { font-size: 0.72rem; color: var(--text-tertiary); font-weight: 400; }
  .sd-list { display: flex; flex-direction: column; gap: 4px; max-height: 200px; overflow-y: auto; }
  .sd-option { display: flex; align-items: center; gap: 10px; padding: 6px 10px; border-radius: 8px; cursor: pointer; font-size: 0.82rem; transition: background 0.1s; border: 1px solid transparent; }
  .sd-option:hover { background: var(--bg-hover); }
  .sd-option.selected { background: var(--accent-muted); border-color: var(--accent-primary); }
  .sd-option input[type="radio"] { accent-color: var(--accent-primary); margin: 0; }
  .sd-quality { font-weight: 700; color: var(--text-primary); min-width: 55px; }
  .sd-codec { color: var(--text-tertiary); min-width: 50px; }
  .sd-size { color: var(--text-tertiary); min-width: 55px; text-align: right; }
  .sd-fps { color: var(--accent-primary); font-weight: 600; font-size: 0.72rem; }
  .sd-tag { font-size: 0.65rem; padding: 1px 6px; border-radius: 4px; font-weight: 600; }
  .sd-tag.prog { background: var(--status-success); color: #fff; }
  .sd-tag.adaptive { background: var(--bg-tertiary); color: var(--text-tertiary); }
  .sd-captions { font-size: 0.78rem; color: var(--text-tertiary); }
  .sd-options { margin-bottom: 16px; }
  .sd-check { display: flex; align-items: center; gap: 8px; font-size: 0.82rem; color: var(--text-secondary); cursor: pointer; }
  .sd-hint { font-size: 0.78rem; color: var(--status-warning); margin: 8px 0 0; display: flex; align-items: center; gap: 6px; }
  .sd-hint-ok { color: var(--status-success); }
  .sd-actions { padding-top: 16px; border-top: 1px solid var(--border-primary); }
  .sd-summary { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; padding: 6px 10px; background: var(--bg-secondary); border-radius: 8px; }
  .sd-sum-item { font-size: 0.78rem; padding: 3px 10px; background: var(--bg-tertiary); border-radius: 6px; color: var(--text-secondary); }
  .sd-sum-ok { color: var(--status-success); }
  .sd-sum-warn { color: var(--status-warning); }
  .sd-buttons { display: flex; gap: 8px; justify-content: flex-end; flex-wrap: wrap; }
  .sd-btn-ghost { padding: 8px 18px; background: transparent; color: var(--text-secondary); border: 1px solid var(--border-primary); border-radius: 8px; font-size: 0.82rem; cursor: pointer; }
  .sd-btn-ghost:hover { border-color: var(--accent-primary); color: var(--text-primary); }
  .sd-btn-audio { padding: 8px 18px; background: var(--bg-secondary); border: 1px solid var(--status-info); border-radius: 8px; color: var(--status-info); font-size: 0.85rem; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 6px; }
  .sd-btn-audio:hover { background: var(--bg-tertiary); }
  .sd-btn-queue { padding: 8px 18px; background: var(--bg-tertiary); border: 1px solid var(--border-primary); border-radius: 8px; color: var(--text-primary); font-size: 0.85rem; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 6px; }
  .sd-btn-queue:hover { border-color: var(--accent-primary); }
  .sd-btn-queue:disabled, .sd-btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
  .sd-btn-primary { display: flex; align-items: center; gap: 6px; padding: 8px 18px; background: var(--accent-primary); color: #fff; border: none; border-radius: 8px; font-size: 0.85rem; font-weight: 600; cursor: pointer; }
  .sd-btn-primary:hover { background: var(--accent-hover); }
</style>

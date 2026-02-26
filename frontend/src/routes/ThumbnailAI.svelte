<!--
  ThumbnailAI v1.6.24 -  AI-Thumbnail-Analyse Dashboard
  Verbindung zu LM Studio, Konfiguration, Queue, Live-Log.
  © HalloWelt42
-->
<script>
  import { onMount } from 'svelte';
  import { api } from '../lib/api/client.js';
  import { toast } from '../lib/stores/notifications.js';

  let status = $state(null);
  let config = $state({});
  let queue = $state(null);
  let log = $state([]);
  let models = $state([]);
  let initialLoad = $state(true);
  let testing = $state(false);
  let testUrl = $state('');
  let pollTimer = null;
  let prompt = $state('');
  let defaultPrompt = $state('');
  let isDefaultPrompt = $state(true);
  let promptDirty = $state(false);
  let savingPrompt = $state(false);
  let testRunning = $state(false);
  let testResult = $state(null);

  // Initiales Laden (einmalig, mit Spinner)
  async function init() {
    await refresh();
    await loadPrompt();
    initialLoad = false;
  }

  // Daten aktualisieren OHNE Spinner
  async function refresh() {
    try {
      const s = await api.thumbnailAiStatus();
      status = s.status;
      config = s.config;
      models = s.status?.available_models || [];
      if (!testUrl) testUrl = config.lm_studio_url || '';
    } catch (e) { if (initialLoad) toast.error(e.message); }
    try { queue = await api.thumbnailAiQueue(); } catch { /* silent */ }
    try { const l = await api.thumbnailAiLog(100); log = l.log || []; } catch { /* silent */ }
  }

  async function loadPrompt() {
    try {
      const p = await api.thumbnailAiPrompt();
      prompt = p.prompt || '';
      defaultPrompt = p.default_prompt || '';
      isDefaultPrompt = p.is_default;
      promptDirty = false;
    } catch { /* silent */ }
  }

  async function saveConfig(key, value) {
    try {
      const res = await api.thumbnailAiUpdateConfig({ [key]: value });
      config = res.config;
      toast.success('Gespeichert');
    } catch (e) { toast.error(e.message); }
  }

  async function testConnection() {
    testing = true;
    try {
      const res = await api.thumbnailAiTestConnection(testUrl);
      if (res.connected) {
        toast.success(`Verbunden: ${res.model}`);
        if (testUrl !== config.lm_studio_url) {
          await saveConfig('lm_studio_url', testUrl);
        }
      } else {
        toast.error(`Nicht erreichbar: ${res.error || 'Unbekannter Fehler'}`);
      }
      await refresh();
    } catch (e) { toast.error(e.message); }
    testing = false;
  }

  let confirmResetAll = $state(false);
  async function resetQueueAll() {
    if (!confirmResetAll) {
      confirmResetAll = true;
      setTimeout(() => confirmResetAll = false, 5000);
      return;
    }
    confirmResetAll = false;
    try {
      const res = await api.thumbnailAiResetAll();
      toast.success(res.message);
      await refresh();
    } catch (e) { toast.error(e.message); }
  }

  async function resetQueueErrors() {
    try {
      const res = await api.thumbnailAiResetErrors();
      toast.success(res.message);
      await refresh();
    } catch (e) { toast.error(e.message); }
  }

  let resetRecentN = $state(100);
  async function resetQueueRecent() {
    try {
      const res = await api.thumbnailAiResetRecent(resetRecentN);
      toast.success(res.message);
      await refresh();
    } catch (e) { toast.error(e.message); }
  }

  let running = $derived(status?.running || status?.processing || false);
  let batchProgress = $derived(status?.batch_total > 0 ? Math.round(status.batch_done / status.batch_total * 100) : 0);

  async function runQueue() {
    try {
      const res = await api.thumbnailAiRun();
      toast.success(res.message || 'Gestartet');
      await refresh();
    } catch (e) { toast.error(e.message); }
  }

  async function stopQueue() {
    try {
      await api.thumbnailAiStop();
      toast.info('Gestoppt');
      await refresh();
    } catch (e) { toast.error(e.message); }
  }

  async function testSingle() {
    testRunning = true;
    testResult = null;
    try {
      const q = await api.thumbnailAiQueue();
      if (!q?.next?.length) { toast.error('Queue leer'); testRunning = false; return; }
      const vid = q.next[0].id;
      toast.info(`Teste: ${vid}…`);
      const res = await api.thumbnailAiAnalyze(vid);
      testResult = res;
      if (res.ok) {
        toast.success(`✓ ${vid} → ${res.result?.video_type} (${res.result?.category}) — ${res.elapsed}s`);
      } else {
        toast.error(`✗ ${res.error || 'Unbekannter Fehler'}`);
      }
      await refresh();
    } catch (e) { toast.error(e.message); testResult = { error: e.message }; }
    testRunning = false;
  }

  async function savePrompt() {
    savingPrompt = true;
    try {
      const res = await api.thumbnailAiSavePrompt(prompt);
      isDefaultPrompt = res.is_default;
      promptDirty = false;
      toast.success('Prompt gespeichert');
    } catch (e) { toast.error(e.message); }
    savingPrompt = false;
  }

  async function resetPrompt() {
    savingPrompt = true;
    try {
      const res = await api.thumbnailAiResetPrompt();
      prompt = res.prompt;
      isDefaultPrompt = true;
      promptDirty = false;
      toast.success('Prompt auf Default zurückgesetzt');
    } catch (e) { toast.error(e.message); }
    savingPrompt = false;
  }

  function onPromptInput(e) {
    prompt = e.target.value;
    promptDirty = prompt.trim() !== defaultPrompt.trim() && prompt.trim() !== '';
  }

  onMount(() => {
    init();
    // Festes 5s Polling — kein reaktiver Zustand im Intervall
    pollTimer = setInterval(() => refresh(), 5000);
    return () => { if (pollTimer) clearInterval(pollTimer); };
  });
</script>

<div class="page">
  <h1 class="page-title"><i class="fa-solid fa-robot"></i> Thumbnail AI</h1>
  <p class="page-desc">Klassifiziert Videos per Vision-LLM (LM Studio) — erkennt Shorts vs. normale Videos.</p>

  {#if initialLoad}
    <div class="loading"><i class="fa-solid fa-spinner fa-spin"></i> Laden…</div>
  {:else}

    <!-- Status-Karte -->
    <div class="status-card" class:connected={status?.connected} class:processing={status?.processing}>
      <div class="status-row">
        <span class="status-dot" class:dot-green={status?.connected && !status?.processing}
              class:dot-orange={status?.processing} class:dot-red={!status?.connected}></span>
        <span class="status-label">
          {#if status?.processing}
            Analysiert: <strong>{status.current_title || status.current_video_id}</strong>
          {:else if status?.connected}
            Verbunden
          {:else}
            Nicht verbunden
          {/if}
        </span>
        {#if status?.model}
          <span class="status-model"><i class="fa-solid fa-microchip"></i> {status.model}</span>
        {/if}
        {#if status?.tokens_per_second > 0}
          <span class="status-tok">{status.tokens_per_second} tok/s</span>
        {/if}
      </div>
      <div class="status-stats">
        <span><i class="fa-solid fa-images"></i> {status?.total_analyzed || 0} analysiert</span>
        <span><i class="fa-solid fa-arrows-rotate"></i> {status?.total_type_changes || 0} Typ-Korrekturen</span>
        <span><i class="fa-solid fa-triangle-exclamation"></i> {status?.total_errors || 0} Fehler</span>
        <span><i class="fa-solid fa-list-ol"></i> {status?.queue_count || 0} in Queue</span>
      </div>
      {#if status?.last_error}
        <div class="status-error"><i class="fa-solid fa-xmark"></i> {status.last_error}</div>
      {/if}
    </div>

    <!-- Config -->
    <div class="config-card">
      <h2><i class="fa-solid fa-gear"></i> Konfiguration</h2>

      <div class="config-row">
        <label>LM Studio URL</label>
        <div class="url-row">
          <input type="text" bind:value={testUrl} placeholder="http://192.168.178.65:1234" />
          <button class="btn-sm" onclick={testConnection} disabled={testing}>
            <i class="fa-solid {testing ? 'fa-spinner fa-spin' : 'fa-plug'}"></i>
            {testing ? 'Teste…' : 'Testen'}
          </button>
        </div>
      </div>

      <div class="config-row">
        <label>Modell</label>
        {#if models.length > 0}
          <select class="config-select"
            value={config.model || status?.model || ''}
            onchange={(e) => saveConfig('model', e.target.value)}>
            <option value="">(automatisch — erstes Modell)</option>
            {#each models as m}
              <option value={m} selected={m === (config.model || status?.model)}>{m}</option>
            {/each}
          </select>
        {:else if status?.model}
          <span class="config-value">{status.model}</span>
        {:else}
          <span class="config-value dim">Nicht verbunden</span>
        {/if}
      </div>

      <div class="config-row">
        <label>Max Bildbreite (px)</label>
        <input type="number" min="128" max="1920" step="64" value={config.max_image_size || 512}
          onchange={(e) => saveConfig('max_image_size', parseInt(e.target.value))} />
        <span class="config-hint">Thumbnails vor Analyse skalieren</span>
      </div>

      <div class="config-row">
        <label>Max Tokens</label>
        <input type="number" min="256" max="8192" value={config.max_tokens || 2048}
          onchange={(e) => saveConfig('max_tokens', parseInt(e.target.value))} />
      </div>

      <div class="config-row">
        <label>Temperatur</label>
        <input type="number" min="0" max="1" step="0.1" value={config.temperature || 0.2}
          onchange={(e) => saveConfig('temperature', parseFloat(e.target.value))} />
      </div>
    </div>

    <!-- Prompt Editor -->
    <div class="prompt-card">
      <details>
        <summary class="prompt-summary">
          <i class="fa-solid fa-message"></i> Analyse-Prompt
          {#if !isDefaultPrompt}<span class="prompt-custom-badge">angepasst</span>{/if}
          <span class="prompt-chars">{prompt.length} Zeichen</span>
        </summary>
        <div class="prompt-body">
          <textarea class="prompt-editor"
            value={prompt}
            oninput={onPromptInput}
            rows="18"
            spellcheck="false"
          ></textarea>
          <div class="prompt-actions">
            <button class="btn-action btn-primary" onclick={savePrompt} disabled={savingPrompt || !promptDirty}>
              <i class="fa-solid {savingPrompt ? 'fa-spinner fa-spin' : 'fa-floppy-disk'}"></i>
              {savingPrompt ? 'Speichert…' : 'Prompt speichern'}
            </button>
            <button class="btn-action" onclick={resetPrompt} disabled={savingPrompt || isDefaultPrompt}>
              <i class="fa-solid fa-rotate-left"></i> Default wiederherstellen
            </button>
            {#if promptDirty}
              <span class="prompt-dirty-hint"><i class="fa-solid fa-pen"></i> Ungespeicherte Änderungen</span>
            {/if}
          </div>
        </div>
      </details>
    </div>

    <!-- Aktionen -->
    <div class="actions-card">
      <h2><i class="fa-solid fa-bolt"></i> Analyse</h2>

      <!-- Fortschrittsbalken (wenn aktiv) -->
      {#if status?.batch_total > 0 && (status?.processing || status?.batch_done < status?.batch_total)}
        <div class="progress-wrap">
          <div class="progress-bar">
            <div class="progress-fill" style="width: {batchProgress}%"></div>
          </div>
          <div class="progress-info">
            <span class="progress-count">{status.batch_done} / {status.batch_total}</span>
            <span class="progress-pct">{batchProgress}%</span>
            {#if status?.current_title}
              <span class="progress-current">→ {status.current_title}</span>
            {/if}
          </div>
        </div>
      {/if}

      <div class="action-btns">
        {#if status?.processing}
          <button class="btn-action btn-stop" onclick={stopQueue}>
            <i class="fa-solid fa-stop"></i> Stoppen
          </button>
        {:else}
          <button class="btn-action btn-primary" onclick={runQueue} disabled={!status?.connected || status?.queue_count === 0}>
            <i class="fa-solid fa-play"></i> Queue abarbeiten ({status?.queue_count || 0} Videos)
          </button>
        {/if}
        <button class="btn-action btn-test" onclick={testSingle} disabled={testRunning || !status?.connected || status?.processing}>
          <i class="fa-solid {testRunning ? 'fa-spinner fa-spin' : 'fa-flask'}"></i>
          {testRunning ? 'Teste…' : 'Test: 1 Video'}
        </button>
      </div>

      {#if testResult}
        <div class="test-result" class:test-ok={testResult.ok} class:test-err={testResult.error}>
          {#if testResult.ok}
            <div class="test-header"><i class="fa-solid fa-check-circle"></i> {testResult.title}: {testResult.result?.video_type} ({testResult.elapsed}s)</div>
            <pre class="test-json">{JSON.stringify(testResult.result, null, 2)}</pre>
          {:else}
            <div class="test-header"><i class="fa-solid fa-xmark-circle"></i> Fehler</div>
            <pre class="test-json">{testResult.error || JSON.stringify(testResult, null, 2)}</pre>
          {/if}
        </div>
      {/if}
    </div>

    <!-- Queue-Verwaltung -->
    <div class="queue-card">
      <h2><i class="fa-solid fa-list-ol"></i> Queue</h2>
      <div class="queue-stats">
        <span class="queue-stat"><i class="fa-solid fa-hourglass-half"></i> {queue?.queue_count || 0} ausstehend</span>
        <span class="queue-stat"><i class="fa-solid fa-check-circle"></i> {queue?.analyzed_count || 0} analysiert</span>
        <span class="queue-stat"><i class="fa-solid fa-triangle-exclamation"></i> {queue?.error_count || 0} fehlerhaft</span>
      </div>

      <div class="queue-reset-btns">
        {#if queue?.error_count > 0}
          <button class="btn-sm btn-reset" onclick={resetQueueErrors} disabled={running}>
            <i class="fa-solid fa-rotate-left"></i> Fehlerhafte wiederholen ({queue.error_count})
          </button>
        {/if}
        <button class="btn-sm btn-reset" onclick={resetQueueRecent} disabled={running}>
          <i class="fa-solid fa-rotate-left"></i> Letzte
          <input type="number" class="reset-n-input" min="10" max="10000" step="10"
            bind:value={resetRecentN} onclick={(e) => e.stopPropagation()} />
          wiederholen
        </button>
        <button class="btn-sm btn-reset-all" class:btn-confirm={confirmResetAll} onclick={resetQueueAll} disabled={running}>
          <i class="fa-solid {confirmResetAll ? 'fa-exclamation-triangle' : 'fa-trash-can'}"></i>
          {confirmResetAll ? 'Wirklich alles löschen?' : 'Alles zurücksetzen'}
        </button>
      </div>

      {#if queue?.next?.length > 0}
        <div class="queue-list">
          {#each queue.next as v}
            <div class="queue-item">
              <img src={v.source === 'rss' ? api.rssThumbUrl(v.id) : api.thumbnailUrl(v.id)} alt="" loading="lazy"
                onerror={(e) => { if(!e.target.dataset.fallback) { e.target.dataset.fallback='1'; e.target.src=api.rssThumbUrl(v.id); } else e.target.style.display='none'; }} />
              <div class="queue-info">
                <span class="queue-title">{v.title || v.id}</span>
                <span class="queue-channel">{v.channel_name || ''}</span>
              </div>
              <span class="queue-type badge-{v.video_type || 'video'}">{v.video_type || 'video'}</span>
            </div>
          {/each}
        </div>
      {/if}
    </div>

    <!-- Live-Log -->
    <div class="log-card">
      <h2><i class="fa-solid fa-terminal"></i> Analyse-Log ({log.length})</h2>
      <div class="log-list">
        {#each [...log].reverse().slice(0, 50) as entry}
          <div class="log-entry" class:log-error={entry.level === 'error'}>
            <span class="log-ts">{new Date(entry.ts).toLocaleTimeString('de')}</span>
            <span class="log-msg">{entry.msg}</span>
            {#if entry.details?.tok_s}
              <span class="log-tok">{entry.details.tok_s} tok/s</span>
            {/if}
            {#if entry.details?.elapsed}
              <span class="log-elapsed">{entry.details.elapsed}s</span>
            {/if}
          </div>
        {/each}
        {#if log.length === 0}
          <div class="log-empty">Noch keine Einträge — starte eine Analyse.</div>
        {/if}
      </div>
    </div>

  {/if}
</div>

<style>
  .page { max-width: 900px; margin: 0 auto; padding: 24px 16px; }
  .page-title { font-size: 1.4rem; font-weight: 700; color: var(--text-primary); display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
  .page-desc { font-size: 0.85rem; color: var(--text-tertiary); margin-bottom: 20px; }
  .loading { padding: 40px; text-align: center; color: var(--text-secondary); }

  /* Status */
  .status-card {
    background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 12px; padding: 16px; margin-bottom: 16px;
  }
  .status-card.connected { border-color: var(--status-success); }
  .status-card.processing { border-color: var(--status-pending); }
  .status-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .status-dot {
    width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
  }
  .dot-green { background: var(--status-success); }
  .dot-orange { background: var(--status-pending); animation: pulse 1.5s infinite; }
  .dot-red { background: var(--status-error); }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
  .status-label { font-weight: 600; color: var(--text-primary); }
  .status-model { font-size: 0.78rem; color: var(--accent-primary); background: var(--bg-tertiary); padding: 2px 8px; border-radius: 6px; }
  .status-tok { font-size: 0.75rem; color: var(--text-tertiary); font-family: monospace; }
  .status-stats {
    display: flex; gap: 16px; flex-wrap: wrap; margin-top: 10px;
    font-size: 0.82rem; color: var(--text-secondary);
  }
  .status-error {
    margin-top: 8px; padding: 6px 10px; background: rgba(244,67,54,0.1);
    border-radius: 6px; font-size: 0.78rem; color: var(--status-error);
  }

  /* Config */
  .config-card, .actions-card, .queue-card, .log-card, .prompt-card {
    background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 12px; padding: 16px; margin-bottom: 16px;
  }
  .config-card h2, .actions-card h2, .queue-card h2, .log-card h2, .prompt-card h2 {
    font-size: 1rem; font-weight: 600; color: var(--text-primary);
    margin: 0 0 14px; display: flex; align-items: center; gap: 8px;
  }
  .config-row { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
  .config-row label { width: 160px; font-size: 0.85rem; color: var(--text-secondary); flex-shrink: 0; }
  .config-row input[type="text"], .config-row input[type="number"] {
    flex: 1; max-width: 300px; padding: 6px 10px; background: var(--bg-tertiary);
    border: 1px solid var(--border-primary); border-radius: 6px;
    color: var(--text-primary); font-size: 0.85rem;
  }
  .url-row { display: flex; gap: 8px; flex: 1; }
  .url-row input { flex: 1; }
  .config-select {
    flex: 1; max-width: 400px; padding: 6px 10px; background: var(--bg-tertiary);
    border: 1px solid var(--border-primary); border-radius: 6px;
    color: var(--text-primary); font-size: 0.82rem;
  }
  .config-value { font-size: 0.82rem; color: var(--text-primary); font-family: monospace; }
  .config-value.dim { color: var(--text-tertiary); font-family: inherit; }

  /* Buttons */
  .btn-sm {
    padding: 6px 12px; border-radius: 6px; border: 1px solid var(--border-primary);
    background: var(--bg-tertiary); color: var(--text-secondary); cursor: pointer;
    font-size: 0.8rem; display: flex; align-items: center; gap: 5px;
  }
  .btn-sm:hover { border-color: var(--accent-primary); color: var(--text-primary); }
  .action-btns { display: flex; gap: 10px; flex-wrap: wrap; }
  .btn-action {
    padding: 8px 16px; border-radius: 8px; border: 1px solid var(--border-primary);
    background: var(--bg-tertiary); color: var(--text-secondary); cursor: pointer;
    font-size: 0.85rem; display: flex; align-items: center; gap: 6px;
  }
  .btn-action:hover { border-color: var(--accent-primary); color: var(--text-primary); }
  .btn-action:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-primary { background: var(--accent-primary); color: #fff; border-color: var(--accent-primary); }
  .btn-primary:hover { filter: brightness(1.1); }
  .btn-test { border-color: var(--status-pending); color: var(--status-pending); }
  .btn-test:hover { background: rgba(255,152,0,0.08); }
  .btn-stop { background: var(--status-error); color: #fff; border-color: var(--status-error); }
  .btn-stop:hover { filter: brightness(1.1); }

  /* Progress Bar */
  .progress-wrap { margin-bottom: 14px; }
  .progress-bar {
    height: 8px; background: var(--bg-tertiary); border-radius: 4px; overflow: hidden;
  }
  .progress-fill {
    height: 100%; background: var(--accent-primary); border-radius: 4px;
    transition: width 0.3s ease;
  }
  .progress-info {
    display: flex; align-items: center; gap: 10px; margin-top: 6px;
    font-size: 0.8rem; color: var(--text-secondary);
  }
  .progress-count { font-weight: 700; color: var(--text-primary); font-family: monospace; }
  .progress-pct { color: var(--accent-primary); font-weight: 600; }
  .progress-current {
    flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    color: var(--text-tertiary); font-size: 0.75rem;
  }

  /* Prompt Editor */
  .prompt-summary {
    cursor: pointer; font-size: 0.95rem; font-weight: 600; color: var(--text-primary);
    display: flex; align-items: center; gap: 8px; padding: 4px 0;
    list-style: none;
  }
  .prompt-summary::-webkit-details-marker { display: none; }
  .prompt-summary::before {
    content: '▸'; font-size: 0.8rem; color: var(--text-tertiary); transition: transform 0.15s;
  }
  details[open] > .prompt-summary::before { transform: rotate(90deg); }
  .prompt-custom-badge {
    font-size: 0.65rem; font-weight: 700; text-transform: uppercase;
    background: var(--accent-primary); color: #fff; padding: 1px 6px; border-radius: 4px;
  }
  .prompt-chars { font-size: 0.7rem; color: var(--text-tertiary); font-weight: 400; margin-left: auto; }
  .prompt-body { margin-top: 10px; }
  .prompt-editor {
    width: 100%; min-height: 280px; padding: 10px 12px; font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 0.78rem; line-height: 1.5; color: var(--text-primary); background: var(--bg-tertiary);
    border: 1px solid var(--border-primary); border-radius: 8px; resize: vertical;
    tab-size: 2; white-space: pre-wrap;
  }
  .prompt-editor:focus { border-color: var(--accent-primary); outline: none; }
  .prompt-actions { display: flex; align-items: center; gap: 10px; margin-top: 10px; flex-wrap: wrap; }
  .prompt-dirty-hint { font-size: 0.75rem; color: var(--status-pending); display: flex; align-items: center; gap: 4px; }

  /* Test Result */
  .test-result { margin-top: 12px; padding: 10px 12px; border-radius: 8px; border: 1px solid var(--border-primary); }
  .test-ok { border-color: var(--status-success); background: rgba(76,175,80,0.05); }
  .test-err { border-color: var(--status-error); background: rgba(244,67,54,0.05); }
  .test-header { font-size: 0.85rem; font-weight: 600; margin-bottom: 6px; display: flex; align-items: center; gap: 6px; }
  .test-ok .test-header { color: var(--status-success); }
  .test-err .test-header { color: var(--status-error); }
  .test-json { font-size: 0.72rem; background: var(--bg-tertiary); padding: 8px; border-radius: 6px; overflow-x: auto; max-height: 200px; white-space: pre-wrap; word-break: break-all; color: var(--text-secondary); margin: 0; }

  /* Queue */
  .queue-stats {
    display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 12px;
    font-size: 0.82rem; color: var(--text-secondary);
  }
  .queue-stat { display: flex; align-items: center; gap: 5px; }
  .queue-reset-btns { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
  .btn-reset {
    padding: 5px 10px; border-radius: 6px; border: 1px solid var(--border-primary);
    background: var(--bg-tertiary); color: var(--text-secondary); cursor: pointer;
    font-size: 0.78rem; display: flex; align-items: center; gap: 5px;
  }
  .btn-reset:hover { border-color: var(--accent-primary); color: var(--text-primary); }
  .btn-reset:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-reset-all {
    padding: 5px 10px; border-radius: 6px; border: 1px solid var(--status-error);
    background: transparent; color: var(--status-error); cursor: pointer;
    font-size: 0.78rem; display: flex; align-items: center; gap: 5px;
  }
  .btn-reset-all:hover { background: rgba(244,67,54,0.08); }
  .btn-reset-all.btn-confirm { background: var(--status-error); color: #fff; animation: pulse 1s infinite; }
  .btn-reset-all:disabled { opacity: 0.5; cursor: not-allowed; }
  .reset-n-input {
    width: 60px; padding: 2px 4px; border: 1px solid var(--border-primary);
    border-radius: 4px; background: var(--bg-tertiary); color: var(--text-primary);
    font-size: 0.78rem; text-align: center;
  }
  .config-hint { font-size: 0.72rem; color: var(--text-tertiary); }
  .queue-list { display: flex; flex-direction: column; gap: 6px; }
  .queue-item {
    display: flex; align-items: center; gap: 10px; padding: 6px 8px;
    background: var(--bg-tertiary); border-radius: 8px;
  }
  .queue-item img { width: 60px; height: 34px; object-fit: cover; border-radius: 4px; }
  .queue-info { flex: 1; min-width: 0; }
  .queue-title { font-size: 0.82rem; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block; }
  .queue-channel { font-size: 0.72rem; color: var(--text-tertiary); }
  .queue-type { font-size: 0.68rem; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; font-weight: 600; }
  .badge-video { background: rgba(100,100,100,0.3); color: var(--text-tertiary); }
  .badge-short { background: rgba(171,71,188,0.2); color: #ab47bc; }
  .badge-live { background: rgba(244,67,54,0.2); color: #f44336; }

  /* Log */
  .log-list { max-height: 400px; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
  .log-entry {
    display: flex; align-items: center; gap: 8px; padding: 4px 8px;
    font-size: 0.78rem; border-radius: 4px;
  }
  .log-entry:hover { background: var(--bg-tertiary); }
  .log-error { color: var(--status-error); }
  .log-ts { color: var(--text-tertiary); font-family: monospace; font-size: 0.72rem; flex-shrink: 0; }
  .log-msg { flex: 1; color: var(--text-secondary); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .log-error .log-msg { color: var(--status-error); }
  .log-tok { font-family: monospace; font-size: 0.7rem; color: var(--accent-primary); }
  .log-elapsed { font-family: monospace; font-size: 0.7rem; color: var(--text-tertiary); }
  .log-empty { padding: 20px; text-align: center; color: var(--text-tertiary); font-size: 0.85rem; }
</style>

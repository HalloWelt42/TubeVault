<!--
  TubeVault -  LogTerminal v1.9.1
  Live-Log + Job-Monitor. Jobs-Tab zeigt aktive Jobs mit Kill-Button.
  © HalloWelt42 -  Private Nutzung
-->
<script>
  import { onMount, onDestroy } from 'svelte';

  let { visible = $bindable(false) } = $props();

  let logs = $state([]);
  let ws = null;
  let reconnectTimer = null;
  let autoScroll = $state(true);
  let logContainer = $state(null);
  let filterLevel = $state('ALL');
  let activeTab = $state('tasks');
  let searchQuery = $state('');
  let wsConnected = $state(false);
  let useRegex = $state(false);
  let paused = $state(false);
  let pauseBuffer = [];

  // Window Position & Size
  let winX = $state(60);
  let winY = $state(60);
  let winW = $state(900);
  let winH = $state(520);
  let minimized = $state(false);

  // Drag State
  let dragging = false;
  let dragOffX = 0;
  let dragOffY = 0;

  // Resize State
  let resizing = false;
  let resizeStartX = 0;
  let resizeStartY = 0;
  let resizeStartW = 0;
  let resizeStartH = 0;

  // Frontend Console-Capture
  let origConsole = {};
  let frontendBuffer = [];
  let flushTimer = null;

  // Jobs & Cron-Tasks
  let tasks = $state([]);
  let jobs = $state([]);
  let jobStats = $state(null);
  let tasksLoading = $state(false);
  let tasksTimer = null;

  // ─── Tabs ───
  const TABS = [
    { id: 'tasks',    label: 'Jobs',       icon: 'fa-gears',          cats: null, special: true },
    { id: 'all',      label: 'Alle',       icon: 'fa-layer-group',    cats: null },
    { id: 'api',      label: 'API',        icon: 'fa-exchange-alt',   cats: ['api'] },
    { id: 'system',   label: 'System',     icon: 'fa-server',         cats: ['backend', 'system', 'meta', 'scan', 'download', 'rss', 'queue', 'rate', 'lyrics', 'import', 'stream', 'playlist'] },
    { id: 'frontend', label: 'Frontend',   icon: 'fa-display',        cats: ['frontend'] },
  ];

  const LEVELS = ['ALL', 'DEBUG', 'INFO', 'WARNING', 'ERROR'];

  const levelColors = {
    DEBUG: '#6b7280', INFO: '#a3d9a5', WARNING: '#f5c542',
    ERROR: '#f87171', CRITICAL: '#ef4444',
  };

  const catColors = {
    backend: '#8b949e', api: '#c084fc', frontend: '#34d399',
    download: '#42A5F5', rss: '#FF9800', queue: '#AB47BC',
    rate: '#EF5350', scan: '#26C6DA', system: '#78909C',
    meta: '#90A4AE', lyrics: '#CE93D8', import: '#78909C',
    stream: '#4DB6AC', playlist: '#66BB6A',
  };

  const catLabels = {
    backend: 'BE', api: 'API', frontend: 'FE', download: 'DL',
    rss: 'RSS', queue: 'QUE', rate: 'RTE', scan: 'SCN',
    system: 'SYS', meta: 'MTA', lyrics: 'LRC', import: 'IMP',
    stream: 'STR', playlist: 'PL',
  };

  // ─── Derived ───
  let errorCount = $derived(logs.filter(l => l.level === 'ERROR' || l.level === 'CRITICAL').length);

  let filteredLogs = $derived(() => {
    return logs.filter(l => {
      if (filterLevel !== 'ALL') {
        const order = { DEBUG: 0, INFO: 1, WARNING: 2, ERROR: 3, CRITICAL: 4 };
        if ((order[l.level] ?? 0) < (order[filterLevel] ?? 0)) return false;
      }
      const tab = TABS.find(t => t.id === activeTab);
      if (tab?.cats && !tab.cats.includes(l.cat)) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.trim();
        if (useRegex) {
          try {
            const re = new RegExp(q, 'i');
            if (!re.test(l.msg || '') && !re.test(l.name || '') && !re.test(l.cat || '')) return false;
          } catch { return false; }
        } else {
          const ql = q.toLowerCase();
          if (!(l.msg || '').toLowerCase().includes(ql) &&
              !(l.name || '').toLowerCase().includes(ql) &&
              !(l.cat || '').toLowerCase().includes(ql)) return false;
        }
      }
      return true;
    });
  });

  let displayLogs = $derived(filteredLogs());

  // ─── Jobs & Tasks ───
  async function fetchTasks() {
    try {
      const [tRes, jRes, sRes] = await Promise.all([
        fetch('/api/system/tasks'),
        fetch('/api/jobs/active'),
        fetch('/api/jobs/stats'),
      ]);
      if (tRes.ok) tasks = await tRes.json();
      if (jRes.ok) jobs = await jRes.json();
      if (sRes.ok) jobStats = await sRes.json();
    } catch (e) { /* ignore */ }
  }

  async function cancelJob(jobId) {
    tasksLoading = true;
    try {
      await fetch(`/api/jobs/${jobId}/cancel`, { method: 'POST' });
      await new Promise(r => setTimeout(r, 500));
      await fetchTasks();
    } catch (e) { /* ignore */ }
    tasksLoading = false;
  }

  async function taskAction(name, action) {
    tasksLoading = true;
    try {
      await fetch(`/api/system/tasks/${name}/${action}`, { method: 'POST' });
      await new Promise(r => setTimeout(r, 300));
      await fetchTasks();
    } catch (e) { /* ignore */ }
    tasksLoading = false;
  }

  async function toggleQueuePause() {
    tasksLoading = true;
    const action = jobStats?.paused ? 'resume' : 'pause';
    try {
      await fetch(`/api/jobs/queue/${action}`, { method: 'POST' });
      await new Promise(r => setTimeout(r, 300));
      await fetchTasks();
    } catch (e) { /* ignore */ }
    tasksLoading = false;
  }

  function fmtProgress(p) {
    return p != null ? `${Math.round(p * 100)}%` : '';
  }

  // ─── WebSocket ───
  function connect() {
    if (ws) return;
    const port = window.location.port;
    const isProxy = (port === '8032' || port === '5173' || port === '');
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsBase = isProxy
      ? `${proto}://${window.location.host}`
      : `${proto}://${window.location.hostname}:8031`;
    ws = new WebSocket(`${wsBase}/api/system/ws/logs`);

    ws.onopen = () => { wsConnected = true; };
    ws.onmessage = (e) => {
      if (e.data === 'pong') return;
      try {
        const entry = JSON.parse(e.data);
        if (!entry.cat) entry.cat = 'backend';
        if (paused) {
          pauseBuffer.push(entry);
          if (pauseBuffer.length > 500) pauseBuffer.shift();
          return;
        }
        logs = [...logs.slice(-2499), entry];
        scrollIfNeeded();
      } catch {}
    };
    ws.onclose = () => {
      ws = null;
      wsConnected = false;
      if (visible) reconnectTimer = setTimeout(connect, 3000);
    };
    ws.onerror = () => ws?.close();
  }

  function disconnect() {
    clearTimeout(reconnectTimer);
    if (ws) { ws.close(); ws = null; }
    wsConnected = false;
  }

  function scrollIfNeeded() {
    if (autoScroll && logContainer) {
      requestAnimationFrame(() => {
        if (logContainer) logContainer.scrollTop = logContainer.scrollHeight;
      });
    }
  }

  function togglePause() {
    paused = !paused;
    if (!paused && pauseBuffer.length > 0) {
      logs = [...logs.slice(-(2500 - pauseBuffer.length)), ...pauseBuffer];
      pauseBuffer = [];
      scrollIfNeeded();
    }
  }

  // ─── Frontend Console Capture ───
  function startConsoleCapture() {
    if (origConsole.log) return;
    ['log', 'warn', 'error', 'info'].forEach(method => {
      origConsole[method] = console[method];
      console[method] = (...args) => {
        origConsole[method]?.apply(console, args);
        const msg = args.map(a =>
          typeof a === 'object' ? JSON.stringify(a) : String(a)
        ).join(' ');
        if (msg.includes('[LogTerminal]')) return;
        const levelMap = { log: 'INFO', info: 'INFO', warn: 'WARNING', error: 'ERROR' };
        const entry = {
          ts: new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
          level: levelMap[method] || 'INFO',
          name: 'console',
          msg: msg.substring(0, 500),
          cat: 'frontend',
        };
        if (!paused) {
          logs = [...logs.slice(-2499), entry];
          scrollIfNeeded();
        }
        frontendBuffer.push({ ts: entry.ts, level: entry.level, source: 'console', msg: entry.msg });
        scheduleFlush();
      };
    });
    window.addEventListener('error', onWindowError);
    window.addEventListener('unhandledrejection', onUnhandledRejection);
  }

  function stopConsoleCapture() {
    Object.entries(origConsole).forEach(([method, fn]) => {
      if (fn) console[method] = fn;
    });
    origConsole = {};
    window.removeEventListener('error', onWindowError);
    window.removeEventListener('unhandledrejection', onUnhandledRejection);
    clearTimeout(flushTimer);
  }

  function onWindowError(e) {
    const entry = {
      ts: new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      level: 'ERROR', name: 'window', cat: 'frontend',
      msg: `${e.message} (${e.filename}:${e.lineno})`,
    };
    logs = [...logs.slice(-2499), entry];
    scrollIfNeeded();
  }

  function onUnhandledRejection(e) {
    const entry = {
      ts: new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      level: 'ERROR', name: 'promise', cat: 'frontend',
      msg: `Unhandled: ${e.reason?.message || e.reason || 'unknown'}`,
    };
    logs = [...logs.slice(-2499), entry];
    scrollIfNeeded();
  }

  function scheduleFlush() {
    if (flushTimer) return;
    flushTimer = setTimeout(flushFrontendLogs, 2000);
  }

  async function flushFrontendLogs() {
    flushTimer = null;
    if (frontendBuffer.length === 0) return;
    const batch = frontendBuffer.splice(0, 50);
    try {
      const port = window.location.port;
      const isProxy = (port === '8032' || port === '5173' || port === '');
      const base = isProxy ? '' : `http://${window.location.hostname}:8031`;
      await fetch(`${base}/api/system/logs/frontend`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(batch),
      });
    } catch { /* silent */ }
  }

  // ─── Drag/Resize ───
  function onDragStart(e) {
    if (e.target.closest('.lt-btn, .lt-filter, .lt-tab, .lt-search, select')) return;
    dragging = true;
    dragOffX = e.clientX - winX;
    dragOffY = e.clientY - winY;
    e.preventDefault();
  }

  function onDragMove(e) {
    if (dragging) {
      winX = Math.max(0, e.clientX - dragOffX);
      winY = Math.max(0, e.clientY - dragOffY);
    }
    if (resizing) {
      winW = Math.max(600, resizeStartW + (e.clientX - resizeStartX));
      winH = Math.max(300, resizeStartH + (e.clientY - resizeStartY));
    }
  }

  function onDragEnd() { dragging = false; resizing = false; }

  function onResizeStart(e) {
    resizing = true;
    resizeStartX = e.clientX;
    resizeStartY = e.clientY;
    resizeStartW = winW;
    resizeStartH = winH;
    e.preventDefault();
    e.stopPropagation();
  }

  function toggleAutoScroll() {
    autoScroll = !autoScroll;
    if (autoScroll && logContainer) logContainer.scrollTop = logContainer.scrollHeight;
  }

  function handleScroll() {
    if (!logContainer) return;
    const { scrollTop, scrollHeight, clientHeight } = logContainer;
    if (scrollHeight - scrollTop - clientHeight > 50) autoScroll = false;
  }

  function clearLogs() { logs = []; }

  function exportLogs() {
    const text = displayLogs.map(l =>
      `${l.ts} [${l.level}] [${l.cat}] ${l.name}: ${l.msg}`
    ).join('\n');
    const blob = new Blob([text], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `tubevault-logs-${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  // ─── Effects ───
  $effect(() => {
    if (visible) {
      connect();
      startConsoleCapture();
      fetch('/api/jobs/active').then(r => r.ok ? r.json() : []).then(j => jobs = j).catch(() => {});
    } else {
      disconnect();
      stopConsoleCapture();
    }
  });

  $effect(() => {
    if (visible && activeTab === 'tasks') {
      fetchTasks();
      tasksTimer = setInterval(fetchTasks, 2000);
    } else {
      if (tasksTimer) { clearInterval(tasksTimer); tasksTimer = null; }
    }
    return () => { if (tasksTimer) { clearInterval(tasksTimer); tasksTimer = null; } };
  });

  onMount(() => {
    document.addEventListener('mousemove', onDragMove);
    document.addEventListener('mouseup', onDragEnd);
  });

  onDestroy(() => {
    disconnect();
    stopConsoleCapture();
    document.removeEventListener('mousemove', onDragMove);
    document.removeEventListener('mouseup', onDragEnd);
  });
</script>

{#if visible}
<div
  class="lt-window"
  style="left:{winX}px; top:{winY}px; width:{winW}px; height:{minimized ? 'auto' : winH + 'px'};"
>
  <!-- Titlebar -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="lt-titlebar" onmousedown={onDragStart}>
    <div class="lt-title">
      <i class="fa-solid fa-terminal"></i>
      <span>TubeVault</span>
      <span class="lt-ws-dot" class:connected={wsConnected} title={wsConnected ? 'Verbunden' : 'Getrennt'}></span>
      {#if paused}
        <span class="lt-paused-badge">PAUSED ({pauseBuffer.length})</span>
      {/if}
    </div>
    <div class="lt-controls">
      <button class="lt-btn" class:active={paused} title={paused ? 'Fortsetzen' : 'Pausieren'} onclick={togglePause}>
        <i class="fa-solid {paused ? 'fa-play' : 'fa-pause'}"></i>
      </button>
      <button class="lt-btn" title={minimized ? 'Maximieren' : 'Minimieren'} onclick={() => minimized = !minimized}>
        <i class="fa-solid {minimized ? 'fa-window-maximize' : 'fa-window-minimize'}"></i>
      </button>
      <button class="lt-btn lt-close" title="Schliessen" onclick={() => visible = false}>
        <i class="fa-solid fa-xmark"></i>
      </button>
    </div>
  </div>

  {#if !minimized}
    <!-- Tabs -->
    <div class="lt-tabs">
      {#each TABS as tab (tab.id)}
        <button
          class="lt-tab"
          class:active={activeTab === tab.id}
          onclick={() => activeTab = tab.id}
        >
          <i class="fa-solid {tab.icon}"></i>
          {tab.label}
          {#if tab.id === 'tasks' && jobs.length > 0}
            <span class="lt-tab-count lt-count-active">{jobs.length}</span>
          {/if}
        </button>
      {/each}
      {#if errorCount > 0}
        <span class="lt-error-badge" title="{errorCount} Fehler">
          <i class="fa-solid fa-triangle-exclamation"></i> {errorCount}
        </span>
      {/if}

      <!-- Log-Tools rechts -->
      <div class="lt-tab-tools">
        <input
          class="lt-search"
          type="text"
          placeholder="Suche{useRegex ? ' (RegEx)' : ''}…"
          bind:value={searchQuery}
        />
        <button class="lt-btn lt-btn-sm" class:active={useRegex} title="RegEx" onclick={() => useRegex = !useRegex}>
          <span style="font-size:9px;font-weight:700">.*</span>
        </button>
        <select class="lt-filter" bind:value={filterLevel}>
          {#each LEVELS as lvl}
            <option value={lvl}>{lvl}</option>
          {/each}
        </select>
        <button class="lt-btn lt-btn-sm" title="Exportieren" onclick={exportLogs}>
          <i class="fa-solid fa-file-export"></i>
        </button>
        <button class="lt-btn lt-btn-sm" title="Leeren" onclick={clearLogs}>
          <i class="fa-solid fa-trash-can"></i>
        </button>
      </div>
    </div>

    {#if activeTab === 'tasks'}
    <!-- ═══ JOBS & TASKS ═══ -->
    <div class="lt-body lt-tasks-body">
      <div class="lt-tasks-header">
        <div class="lt-tasks-title">
          {#if jobStats}
            <span class="lt-stat"><i class="fa-solid fa-circle lt-dot-green"></i> {jobStats.active || 0} aktiv</span>
            <span class="lt-stat"><i class="fa-solid fa-clock lt-dot-gray"></i> {jobStats.queued || 0} wartend</span>
            {#if jobStats.errors > 0}
              <span class="lt-stat lt-stat-err"><i class="fa-solid fa-xmark"></i> {jobStats.errors} Fehler</span>
            {/if}
          {/if}
        </div>
        <div class="lt-tasks-actions">
          {#if jobStats}
            <button class="lt-tbtn" class:lt-tbtn-warn={!jobStats.paused} class:lt-tbtn-ok={jobStats.paused}
                    onclick={toggleQueuePause} disabled={tasksLoading}>
              <i class="fa-solid {jobStats.paused ? 'fa-play' : 'fa-pause'}"></i>
              {jobStats.paused ? 'Fortsetzen' : 'Pausieren'}
            </button>
          {/if}
          <button class="lt-tbtn" onclick={fetchTasks} disabled={tasksLoading}>
            <i class="fa-solid fa-arrows-rotate" class:fa-spin={tasksLoading}></i>
          </button>
        </div>
      </div>

      <!-- Aktive Jobs -->
      {#if jobs.length > 0}
        {#each jobs as job (job.id)}
          <div class="lt-job" class:is-active={job.status === 'active'}>
            <div class="lt-job-head">
              <i class="fa-solid {job.type === 'download' ? 'fa-download' : job.type === 'channel_scan' ? 'fa-satellite-dish' : job.type === 'scan' ? 'fa-magnifying-glass' : 'fa-gear'} lt-job-icon"></i>
              <span class="lt-job-title">{job.title || job.type}</span>
              <span class="lt-tag" class:tag-active={job.status === 'active'} class:tag-queued={job.status === 'queued'}>
                {job.status === 'active' ? 'aktiv' : 'wartend'}
              </span>
              <button class="lt-kill" onclick={() => cancelJob(job.id)} disabled={tasksLoading} title="Job abbrechen">
                <i class="fa-solid fa-xmark"></i>
              </button>
            </div>
            {#if job.status === 'active' && job.progress > 0}
              <div class="lt-progress">
                <div class="lt-bar"><div class="lt-fill" style="width:{Math.round(job.progress * 100)}%"></div></div>
                <span class="lt-pct">{fmtProgress(job.progress)}</span>
              </div>
            {/if}
            {#if job.description}
              <div class="lt-job-info">{job.description}</div>
            {/if}
          </div>
        {/each}
      {:else}
        <div class="lt-empty-jobs">
          <i class="fa-solid fa-inbox"></i> Keine aktiven Jobs
        </div>
      {/if}

      <!-- Cron-Tasks -->
      {#if tasks.length > 0}
        <div class="lt-cron-section">
          <div class="lt-cron-title">Hintergrund-Dienste</div>
          {#each tasks as t (t.name)}
            <div class="lt-cron">
              <i class="fa-solid fa-circle lt-cron-dot"
                 style="color:{t.status === 'running' ? '#3fb950' : t.status === 'crashed' ? '#f85149' : '#484f58'}"></i>
              <span class="lt-cron-name">{t.label}</span>
              {#if t.status === 'running'}
                <button class="lt-cron-btn" onclick={() => taskAction(t.name, 'stop')} disabled={tasksLoading} title="Stoppen">
                  <i class="fa-solid fa-stop"></i>
                </button>
              {:else}
                <button class="lt-cron-btn lt-cron-start" onclick={() => taskAction(t.name, 'start')} disabled={tasksLoading} title="Starten">
                  <i class="fa-solid fa-play"></i>
                </button>
              {/if}
            </div>
          {/each}
        </div>
      {/if}
    </div>

    {:else}
    <!-- ═══ LOG CONTENT ═══ -->
    <div class="lt-body" bind:this={logContainer} onscroll={handleScroll}>
      {#each displayLogs as entry, i (i)}
        <div class="lt-line" class:is-error={entry.level === 'ERROR' || entry.level === 'CRITICAL'}
             class:is-warn={entry.level === 'WARNING'}
             class:is-debug={entry.level === 'DEBUG'}>
          <span class="lt-ts">{entry.ts}</span>
          <span class="lt-cat" style="color: {catColors[entry.cat] || '#8b949e'}"
                title="{entry.cat}">{catLabels[entry.cat] || entry.cat?.substring(0,3).toUpperCase()}</span>
          <span class="lt-level" style="color: {levelColors[entry.level] || '#a3d9a5'}">{(entry.level || '').padEnd(5).substring(0, 5)}</span>
          <span class="lt-name">{entry.name}</span>
          <span class="lt-msg">{entry.msg}</span>
        </div>
      {/each}
      {#if displayLogs.length === 0}
        <div class="lt-empty">
          {#if !wsConnected}
            <i class="fa-solid fa-plug-circle-xmark" style="font-size:1.5rem; color:#f87171"></i>
            <p>WebSocket nicht verbunden</p>
          {:else}
            <i class="fa-solid fa-inbox" style="font-size:1.5rem; color:#484f58"></i>
            <p>Warte auf Log-Einträge…</p>
          {/if}
        </div>
      {/if}
    </div>
    {/if}

    <!-- Status Bar -->
    <div class="lt-statusbar">
      <span>{displayLogs.length} Einträge</span>
      <span class="lt-status-icons">
        {#if activeTab !== 'tasks'}
          {#if paused}<i class="fa-solid fa-pause" style="color:#f0883e"></i>{/if}
          {#if autoScroll}<i class="fa-solid fa-lock" style="color:#3fb950" title="Auto-Scroll an" onclick={toggleAutoScroll}></i>{:else}<i class="fa-solid fa-lock-open" title="Auto-Scroll aus" onclick={toggleAutoScroll}></i>{/if}
        {/if}
      </span>
    </div>

    <!-- Resize Handle -->
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="lt-resize" onmousedown={onResizeStart}></div>
  {/if}
</div>
{/if}

<style>
  .lt-window {
    position: fixed; z-index: 9999;
    display: flex; flex-direction: column;
    border-radius: 8px; overflow: hidden;
    box-shadow: 0 8px 32px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.06);
    background: #0d1117;
    font-family: 'JetBrains Mono', 'Fira Code', 'SF Mono', 'Consolas', monospace;
  }

  /* ─── Titlebar ─── */
  .lt-titlebar {
    display: flex; align-items: center; justify-content: space-between;
    padding: 6px 10px; background: #161b22;
    cursor: grab; user-select: none; border-bottom: 1px solid #21262d;
  }
  .lt-titlebar:active { cursor: grabbing; }
  .lt-title {
    display: flex; align-items: center; gap: 8px;
    color: #8b949e; font-size: 12px; font-weight: 600;
  }
  .lt-title i { color: #58a6ff; }
  .lt-ws-dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: #f87171; display: inline-block;
  }
  .lt-ws-dot.connected { background: #34d399; }
  .lt-paused-badge {
    font-size: 9px; background: #da3633; color: #fff;
    padding: 1px 6px; border-radius: 8px; font-weight: 700;
    animation: blink 1s ease-in-out infinite;
  }
  @keyframes blink { 50% { opacity: 0.5; } }
  .lt-controls { display: flex; align-items: center; gap: 3px; }

  .lt-btn {
    background: none; border: none; color: #8b949e;
    cursor: pointer; padding: 3px 6px; border-radius: 4px;
    font-size: 12px; line-height: 1; transition: all 0.15s;
  }
  .lt-btn:hover { background: #21262d; color: #c9d1d9; }
  .lt-btn.active { color: #58a6ff; background: rgba(88,166,255,0.1); }
  .lt-btn-sm { font-size: 10px; padding: 2px 5px; }
  .lt-close:hover { background: #da3633; color: #fff; }

  /* ─── Tabs ─── */
  .lt-tabs {
    display: flex; align-items: center;
    background: #161b22; border-bottom: 1px solid #21262d;
    padding: 0 8px; gap: 0;
  }
  .lt-tab {
    background: none; border: none; color: #8b949e;
    padding: 5px 8px; font-size: 10px; font-family: inherit;
    cursor: pointer; border-bottom: 2px solid transparent;
    display: flex; align-items: center; gap: 4px;
    transition: all 0.15s; white-space: nowrap; flex-shrink: 0;
  }
  .lt-tab:hover { color: #c9d1d9; background: rgba(255,255,255,0.03); }
  .lt-tab.active { color: #58a6ff; border-bottom-color: #58a6ff; }
  .lt-tab-count {
    padding: 0 5px; border-radius: 8px; font-size: 9px;
    min-width: 16px; text-align: center;
  }
  .lt-count-active { background: rgba(63,185,80,0.2); color: #3fb950; }
  .lt-error-badge {
    font-size: 9px; color: #f87171;
    display: flex; align-items: center; gap: 3px;
    padding: 2px 8px; flex-shrink: 0;
  }
  .lt-tab-tools {
    margin-left: auto; display: flex; align-items: center; gap: 3px;
    flex-shrink: 0; padding-left: 12px;
  }
  .lt-search {
    background: #21262d; color: #c9d1d9; border: 1px solid #30363d;
    border-radius: 4px; padding: 2px 6px; font-size: 10px;
    font-family: inherit; outline: none; width: 100px;
    transition: width 0.2s;
  }
  .lt-search:focus { width: 160px; border-color: #58a6ff; }
  .lt-filter {
    background: #21262d; color: #c9d1d9; border: 1px solid #30363d;
    border-radius: 4px; padding: 2px 4px; font-size: 10px;
    font-family: inherit; cursor: pointer; outline: none;
  }

  /* ─── Log Body ─── */
  .lt-body {
    flex: 1; overflow-y: auto; overflow-x: hidden;
    padding: 4px 10px; font-size: 11px; line-height: 1.55;
    scrollbar-width: thin; scrollbar-color: #30363d #0d1117;
  }
  .lt-body::-webkit-scrollbar { width: 6px; }
  .lt-body::-webkit-scrollbar-track { background: #0d1117; }
  .lt-body::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }

  .lt-line {
    display: flex; gap: 0; white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis;
    padding: 0 0 0 2px; border-left: 2px solid transparent;
  }
  .lt-line:hover { background: rgba(136,198,255,0.04); }
  .lt-line.is-error { border-left-color: #f87171; background: rgba(248,113,113,0.04); }
  .lt-line.is-warn { border-left-color: #f5c542; }
  .lt-line.is-debug { opacity: 0.6; }

  .lt-ts { color: #484f58; min-width: 58px; margin-right: 6px; }
  .lt-cat { min-width: 28px; margin-right: 5px; font-weight: 600; font-size: 9px; }
  .lt-level { min-width: 40px; margin-right: 4px; font-weight: 600; }
  .lt-name {
    color: #58a6ff; min-width: 60px; max-width: 120px;
    overflow: hidden; text-overflow: ellipsis; margin-right: 6px;
  }
  .lt-msg { color: #b1bac4; overflow: hidden; text-overflow: ellipsis; flex: 1; }

  .lt-empty {
    color: #484f58; text-align: center; padding: 30px;
    display: flex; flex-direction: column; align-items: center; gap: 6px;
  }
  .lt-empty p { margin: 0; font-size: 11px; }

  /* ─── Status Bar ─── */
  .lt-statusbar {
    display: flex; justify-content: space-between; align-items: center;
    padding: 3px 10px; font-size: 9.5px; color: #484f58;
    background: #161b22; border-top: 1px solid #21262d;
  }
  .lt-status-icons { display: flex; gap: 6px; align-items: center; }
  .lt-status-icons i { font-size: 8px; cursor: pointer; }

  .lt-resize {
    position: absolute; bottom: 0; right: 0;
    width: 16px; height: 16px; cursor: nwse-resize;
    background: linear-gradient(135deg, transparent 50%, #30363d 50%);
    border-radius: 0 0 8px 0;
  }

  /* ═══ JOBS & TASKS PANEL ═══ */
  .lt-tasks-body { padding: 8px 10px; gap: 6px; display: flex; flex-direction: column; }

  .lt-tasks-header {
    display: flex; justify-content: space-between; align-items: center;
    padding-bottom: 6px; border-bottom: 1px solid #21262d;
  }
  .lt-tasks-title { display: flex; align-items: center; gap: 10px; }
  .lt-stat { font-size: 10px; color: #8b949e; display: flex; align-items: center; gap: 4px; }
  .lt-stat-err { color: #f85149; }
  .lt-dot-green { font-size: 6px; color: #3fb950; }
  .lt-dot-gray { font-size: 8px; color: #8b949e; }
  .lt-tasks-actions { display: flex; gap: 4px; }

  .lt-tbtn {
    font-size: 10px; padding: 2px 8px; border-radius: 4px;
    border: 1px solid #30363d; background: #21262d; color: #c9d1d9;
    cursor: pointer; display: flex; align-items: center; gap: 4px;
    transition: all 0.15s;
  }
  .lt-tbtn:hover { background: #30363d; }
  .lt-tbtn:disabled { opacity: 0.4; cursor: default; }
  .lt-tbtn-warn { border-color: #f0883e50; color: #f0883e; }
  .lt-tbtn-warn:hover { background: #f0883e20; }
  .lt-tbtn-ok { border-color: #3fb95060; color: #3fb950; }
  .lt-tbtn-ok:hover { background: #3fb95020; }

  /* Job Cards */
  .lt-job {
    background: #161b22; border: 1px solid #21262d; border-radius: 6px;
    padding: 7px 10px; display: flex; flex-direction: column; gap: 4px;
  }
  .lt-job.is-active { border-left: 3px solid #3fb950; }

  .lt-job-head { display: flex; align-items: center; gap: 6px; font-size: 11px; }
  .lt-job-icon { color: #8b949e; font-size: 10px; width: 14px; text-align: center; }
  .lt-job-title {
    font-weight: 600; color: #c9d1d9; flex: 1;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }

  .lt-tag {
    font-size: 8px; font-weight: 700; padding: 1px 5px;
    border-radius: 3px; text-transform: uppercase; letter-spacing: 0.3px;
  }
  .tag-active { background: rgba(63,185,80,0.15); color: #3fb950; }
  .tag-queued { background: rgba(139,148,158,0.15); color: #8b949e; }

  .lt-kill {
    background: none; border: 1px solid #f8514940; color: #f85149;
    width: 20px; height: 20px; border-radius: 4px;
    cursor: pointer; display: flex; align-items: center; justify-content: center;
    font-size: 10px; transition: all 0.15s; flex-shrink: 0;
  }
  .lt-kill:hover { background: #f8514930; border-color: #f85149; }
  .lt-kill:disabled { opacity: 0.3; cursor: default; }

  .lt-progress { display: flex; align-items: center; gap: 6px; }
  .lt-bar { flex: 1; height: 3px; background: #21262d; border-radius: 2px; overflow: hidden; }
  .lt-fill { height: 100%; background: #3fb950; border-radius: 2px; transition: width 0.3s; }
  .lt-pct { font-size: 9px; color: #8b949e; min-width: 28px; text-align: right; }
  .lt-job-info { font-size: 9px; color: #6e7681; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .lt-empty-jobs {
    font-size: 11px; color: #484f58; padding: 16px 0; text-align: center;
    display: flex; align-items: center; justify-content: center; gap: 6px;
  }

  /* Cron Section */
  .lt-cron-section {
    margin-top: 6px; padding-top: 6px; border-top: 1px solid #21262d;
  }
  .lt-cron-title {
    font-size: 9px; font-weight: 700; color: #484f58;
    text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;
  }
  .lt-cron {
    display: flex; align-items: center; gap: 6px;
    padding: 2px 0; font-size: 10px; color: #8b949e;
  }
  .lt-cron-dot { font-size: 5px; }
  .lt-cron-name { flex: 1; }
  .lt-cron-btn {
    font-size: 8px; padding: 1px 4px; border-radius: 3px;
    border: 1px solid #30363d; background: #21262d; color: #8b949e;
    cursor: pointer; transition: all 0.15s;
  }
  .lt-cron-btn:hover { background: #30363d; color: #c9d1d9; }
  .lt-cron-btn:disabled { opacity: 0.4; }
  .lt-cron-start { color: #3fb950; border-color: #3fb95040; }
  .lt-cron-start:hover { background: #3fb95020; }
</style>

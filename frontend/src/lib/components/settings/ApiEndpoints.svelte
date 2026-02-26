<!--
  TubeVault – ApiEndpoints v1.8.38
  Externe Dienste verwalten: URLs bearbeiten, testen, aktivieren/deaktivieren.
  © HalloWelt42 – Private Nutzung
-->
<script>
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';
  import { onMount } from 'svelte';

  let endpoints = $state([]);
  let mounts = $state([]);
  let loading = $state(true);
  let testing = $state({});
  let editing = $state({});

  onMount(load);

  async function load() {
    loading = true;
    try {
      const [eps, mp] = await Promise.all([api.getApiEndpoints(), api.getMountpoints()]);
      endpoints = eps;
      mounts = mp.mounts || [];
    } catch (e) { toast.error(e.message); }
    loading = false;
  }

  async function testEndpoint(ep) {
    testing = { ...testing, [ep.id]: true };
    try {
      const res = await api.testApiEndpoint(ep.id);
      const ep2 = endpoints.find(e => e.id === ep.id);
      if (ep2) { ep2.last_tested = res.tested_at; ep2.last_status = res.status_text; ep2._testResult = res; }
      endpoints = [...endpoints];
      if (res.status === 'ok') toast.success(`${ep.label}: ${res.status_text}`);
      else toast.error(`${ep.label}: ${res.status_text}`);
    } catch (e) { toast.error(e.message); }
    testing = { ...testing, [ep.id]: false };
  }

  async function testAll() {
    for (const ep of endpoints) { if (ep.enabled) await testEndpoint(ep); }
  }

  async function toggleEnabled(ep) {
    try {
      await api.updateApiEndpoint(ep.id, { enabled: !ep.enabled });
      ep.enabled = !ep.enabled;
      endpoints = [...endpoints];
      toast.success(ep.enabled ? `${ep.label} aktiviert` : `${ep.label} deaktiviert`);
    } catch (e) { toast.error(e.message); }
  }

  function startEdit(ep, field) {
    editing = { ...editing, [ep.id]: { field, value: ep[field] || '' } };
  }

  function cancelEdit(epId) {
    const { [epId]: _, ...rest } = editing;
    editing = rest;
  }

  async function saveEdit(ep) {
    const edit = editing[ep.id];
    if (!edit) return;
    try {
      await api.updateApiEndpoint(ep.id, { [edit.field]: edit.value });
      ep[edit.field] = edit.value;
      endpoints = [...endpoints];
      cancelEdit(ep.id);
      toast.success('Gespeichert');
    } catch (e) { toast.error(e.message); }
  }

  function statusIcon(ep) {
    if (!ep.last_status) return '⚪';
    if (ep.last_status.startsWith('2')) return '🟢';
    if (ep.last_status.startsWith('3')) return '🟡';
    return '🔴';
  }

  function fmtDate(iso) {
    if (!iso) return '';
    try { return new Date(iso).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }); }
    catch(e) { return iso; }
  }
</script>

{#if loading}
  <p style="color: var(--text-tertiary); padding: 20px">Laden…</p>
{:else}
  <div class="ep-section">
    <div class="ep-header">
      <h4 class="ep-title"><i class="fa-solid fa-plug"></i> Externe Dienste & APIs</h4>
      <button class="btn-sm" onclick={testAll}><i class="fa-solid fa-vials"></i> Alle testen</button>
    </div>

    <div class="ep-list">
      {#each endpoints as ep (ep.id)}
        <div class="ep-card" class:disabled={!ep.enabled}>
          <div class="ep-top">
            <span class="ep-status">{statusIcon(ep)}</span>
            <div class="ep-info">
              <div class="ep-name-row">
                <span class="ep-label">{ep.label}</span>
                <span class="ep-badge" class:internal={ep.category === 'internal'}>{ep.category}</span>
                <span class="ep-name-tag">{ep.name}</span>
              </div>
              {#if ep.description}<span class="ep-desc">{ep.description}</span>{/if}
            </div>
            <div class="ep-actions">
              <button class="ep-toggle" class:on={ep.enabled} onclick={() => toggleEnabled(ep)} title={ep.enabled ? 'Deaktivieren' : 'Aktivieren'}>
                <i class="fa-solid {ep.enabled ? 'fa-toggle-on' : 'fa-toggle-off'}"></i>
              </button>
              <button class="ep-btn" onclick={() => testEndpoint(ep)} disabled={testing[ep.id]} title="Testen">
                {#if testing[ep.id]}<i class="fa-solid fa-spinner fa-spin"></i>{:else}<i class="fa-solid fa-flask-vial"></i>{/if}
              </button>
            </div>
          </div>

          <!-- URL -->
          <div class="ep-url-row">
            <span class="ep-url-label">URL</span>
            {#if editing[ep.id]?.field === 'url'}
              <input
                class="ep-url-edit"
                value={editing[ep.id].value}
                oninput={(e) => editing[ep.id].value = e.target.value}
                onkeydown={(e) => { if (e.key === 'Enter') saveEdit(ep); if (e.key === 'Escape') cancelEdit(ep.id); }}
              />
              <button class="ep-btn tiny save" onclick={() => saveEdit(ep)}><i class="fa-solid fa-check"></i></button>
              <button class="ep-btn tiny" onclick={() => cancelEdit(ep.id)}><i class="fa-solid fa-xmark"></i></button>
            {:else}
              <code class="ep-url" onclick={() => startEdit(ep, 'url')} title="Klick zum Bearbeiten">{ep.url}</code>
              <button class="ep-btn tiny edit" onclick={() => startEdit(ep, 'url')} title="URL bearbeiten"><i class="fa-solid fa-pen"></i></button>
            {/if}
          </div>

          <!-- Test-Pfad -->
          {#if ep.test_path || editing[ep.id]?.field === 'test_path'}
            <div class="ep-url-row sub">
              <span class="ep-url-label">Test</span>
              {#if editing[ep.id]?.field === 'test_path'}
                <input
                  class="ep-url-edit"
                  value={editing[ep.id].value}
                  oninput={(e) => editing[ep.id].value = e.target.value}
                  onkeydown={(e) => { if (e.key === 'Enter') saveEdit(ep); if (e.key === 'Escape') cancelEdit(ep.id); }}
                />
                <button class="ep-btn tiny save" onclick={() => saveEdit(ep)}><i class="fa-solid fa-check"></i></button>
                <button class="ep-btn tiny" onclick={() => cancelEdit(ep.id)}><i class="fa-solid fa-xmark"></i></button>
              {:else}
                <code class="ep-test-path" onclick={() => startEdit(ep, 'test_path')} title="Klick zum Bearbeiten">{ep.test_path}</code>
                <button class="ep-btn tiny edit" onclick={() => startEdit(ep, 'test_path')} title="Test-Pfad bearbeiten"><i class="fa-solid fa-pen"></i></button>
              {/if}
            </div>
          {/if}

          <!-- Testergebnis -->
          {#if ep.last_tested}
            <div class="ep-result">
              <span class="ep-result-status">{ep.last_status}</span>
              <span class="ep-result-date">{fmtDate(ep.last_tested)}</span>
              {#if ep._testResult?.response_size != null}<span class="ep-result-size">{ep._testResult.response_size} Bytes</span>{/if}
            </div>
          {/if}
        </div>
      {/each}
    </div>
  </div>

  <!-- Mountpoints -->
  {#if mounts.length > 0}
    <div class="ep-section mt-section">
      <h4 class="ep-title"><i class="fa-solid fa-hard-drive"></i> Docker Volumes & Mountpoints</h4>
      <div class="mount-grid">
        {#each mounts as m}
          <div class="mount-card">
            <div class="mount-header">
              <i class="fa-solid {m.type === 'db' ? 'fa-database' : m.type === 'videos' ? 'fa-film' : 'fa-folder'}"></i>
              <span>{m.label}</span>
            </div>
            <div class="mount-paths">
              <div class="mount-row"><span class="mount-key">Container:</span><code>{m.container_path}</code></div>
              {#if m.host_mount}<div class="mount-row"><span class="mount-key">Mount:</span><code>{m.host_mount}</code></div>{/if}
              {#if m.device}<div class="mount-row"><span class="mount-key">Device:</span><code>{m.device}</code></div>{/if}
            </div>
            {#if m.total}
              <div class="mount-usage">
                <div class="mount-bar"><div class="mount-bar-fill" style="width:{m.percent}%"></div></div>
                <span class="mount-stats">{m.free_human} frei von {m.total_human} ({m.percent}%)</span>
              </div>
            {/if}
          </div>
        {/each}
      </div>
    </div>
  {/if}
{/if}

<style>
  .ep-section { margin-bottom: 20px; }
  .mt-section { margin-top: 24px; padding-top: 20px; border-top: 1px solid var(--border-primary); }
  .ep-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
  .ep-title { font-size: 0.9rem; font-weight: 600; color: var(--text-primary); display: flex; align-items: center; gap: 8px; margin: 0 0 12px; }
  .btn-sm {
    padding: 5px 10px; background: var(--bg-tertiary); color: var(--text-secondary);
    border: 1px solid var(--border-primary); border-radius: 5px; font-size: 0.72rem;
    cursor: pointer; display: flex; align-items: center; gap: 4px;
  }
  .btn-sm:hover { border-color: var(--accent-primary); color: var(--accent-primary); }

  .ep-list { display: flex; flex-direction: column; gap: 8px; }
  .ep-card {
    background: var(--bg-primary); border: 1px solid var(--border-primary);
    border-radius: 8px; padding: 10px 14px;
  }
  .ep-card.disabled { opacity: 0.45; }
  .ep-top { display: flex; align-items: center; gap: 10px; }
  .ep-status { font-size: 0.9rem; flex-shrink: 0; }
  .ep-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .ep-name-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .ep-label { font-size: 0.82rem; font-weight: 600; color: var(--text-primary); }
  .ep-badge {
    font-size: 0.6rem; padding: 1px 5px; border-radius: 3px;
    background: var(--bg-tertiary); color: var(--text-tertiary);
    text-transform: uppercase; font-weight: 600;
  }
  .ep-badge.internal { background: var(--accent-muted); color: var(--accent-primary); }
  .ep-name-tag { font-size: 0.62rem; color: var(--text-quaternary, #64748b); font-family: monospace; }
  .ep-desc { font-size: 0.7rem; color: var(--text-tertiary); }

  .ep-actions { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
  .ep-toggle { background: none; border: none; font-size: 1.1rem; cursor: pointer; color: var(--text-tertiary); }
  .ep-toggle.on { color: var(--status-success); }
  .ep-btn {
    width: 26px; height: 26px; border-radius: 5px; border: 1px solid var(--border-primary);
    background: var(--bg-secondary); color: var(--text-secondary); cursor: pointer;
    display: flex; align-items: center; justify-content: center; font-size: 0.65rem;
  }
  .ep-btn:hover { border-color: var(--accent-primary); color: var(--accent-primary); }
  .ep-btn.tiny { width: 22px; height: 22px; font-size: 0.58rem; }
  .ep-btn.tiny.save { background: var(--status-success); color: #fff; border-color: var(--status-success); }
  .ep-btn.tiny.edit { opacity: 0.3; border: none; background: none; }
  .ep-btn.tiny.edit:hover { opacity: 1; color: var(--accent-primary); }

  .ep-url-row {
    display: flex; align-items: center; gap: 6px; margin-top: 6px;
    padding-top: 6px; border-top: 1px dashed var(--border-secondary);
  }
  .ep-url-row.sub { border-top: none; margin-top: 2px; padding-top: 0; }
  .ep-url-label {
    font-size: 0.62rem; color: var(--text-tertiary); font-weight: 600;
    text-transform: uppercase; min-width: 32px; flex-shrink: 0;
  }
  .ep-url {
    font-size: 0.72rem; color: var(--text-secondary); font-family: monospace;
    cursor: pointer; padding: 2px 6px; border-radius: 3px; flex: 1; min-width: 0;
    overflow-wrap: break-word; word-break: break-all;
  }
  .ep-url:hover { background: var(--bg-tertiary); color: var(--accent-primary); }
  .ep-test-path {
    font-size: 0.68rem; color: var(--text-tertiary); font-family: monospace;
    cursor: pointer; padding: 2px 6px; border-radius: 3px; flex: 1; min-width: 0;
    overflow-wrap: break-word; word-break: break-all;
  }
  .ep-test-path:hover { background: var(--bg-tertiary); color: var(--accent-primary); }
  .ep-url-edit {
    flex: 1; min-width: 0; padding: 3px 6px; background: var(--bg-primary);
    border: 1px solid var(--accent-primary); border-radius: 3px;
    color: var(--text-primary); font-family: monospace; font-size: 0.72rem;
  }
  .ep-url-edit:focus { outline: none; box-shadow: 0 0 0 2px var(--accent-muted); }

  .ep-result {
    margin-top: 4px; display: flex; gap: 10px; font-size: 0.68rem;
    color: var(--text-tertiary); flex-wrap: wrap;
  }
  .ep-result-status { font-weight: 600; }

  .mount-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px; }
  .mount-card { background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 8px; padding: 12px 14px; }
  .mount-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 0.82rem; font-weight: 600; color: var(--text-primary); }
  .mount-header i { color: var(--accent-primary); font-size: 0.9rem; }
  .mount-paths { display: flex; flex-direction: column; gap: 3px; }
  .mount-row { display: flex; gap: 6px; font-size: 0.72rem; align-items: baseline; }
  .mount-key { color: var(--text-tertiary); min-width: 65px; flex-shrink: 0; }
  .mount-row code { color: var(--text-secondary); font-size: 0.7rem; word-break: break-all; }
  .mount-usage { margin-top: 8px; }
  .mount-bar { height: 4px; background: var(--bg-tertiary); border-radius: 2px; overflow: hidden; }
  .mount-bar-fill { height: 100%; background: var(--accent-primary); border-radius: 2px; }
  .mount-stats { font-size: 0.68rem; color: var(--text-tertiary); margin-top: 3px; display: block; }
</style>

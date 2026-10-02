<!--
  TubeVault – Serien erkennen
  Zeigt Serien, die an Folgennummern in den Titeln erkannt wurden (je Kanal
  und Serie getrennt), und legt daraus Playlists in Folgenreihenfolge an.
  Schon angelegte Serien lassen sich auffrischen, wenn Folgen dazugekommen
  sind.
-->
<script>
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';

  let { onchange = () => {} } = $props();

  let series = $state([]);
  let loading = $state(true);
  let filter = $state('');
  let busy = $state(new Set());
  let creatingAll = $state(false);

  let visible = $derived(
    filter.trim()
      ? series.filter(s => `${s.name} ${s.channel_name || ''}`.toLowerCase().includes(filter.trim().toLowerCase()))
      : series
  );
  let open = $derived(visible.filter(s => !s.playlist_id));

  async function load() {
    loading = true;
    try { series = (await api.getSeriesProposals()).series || []; }
    catch (e) { toast.error(e.message); }
    loading = false;
  }

  async function create(item, quiet = false) {
    busy = new Set([...busy, item.key]);
    try {
      const result = await api.createPlaylistFromSeries(item.key);
      item.playlist_id = result.playlist_id;
      series = [...series];
      if (!quiet) toast.success(`Playlist "${result.name}" mit ${result.video_count} Folgen`);
      onchange();
    } catch (e) { toast.error(e.message); }
    busy = new Set([...busy].filter(k => k !== item.key));
  }

  async function createAll() {
    creatingAll = true;
    const todo = [...open];
    for (const item of todo) await create(item, true);
    creatingAll = false;
    toast.success(`${todo.length} Playlists angelegt`);
  }

  function range(item) {
    const gaps = item.missing.length;
    return `Folge ${item.first} bis ${item.last}` + (gaps ? `, ${gaps} ${gaps === 1 ? 'fehlt' : 'fehlen'}` : '');
  }

  load();
</script>

<div class="series">
  <div class="head">
    <div class="filter">
      <i class="fa-solid fa-magnifying-glass"></i>
      <input type="text" placeholder="Serie oder Kanal…" bind:value={filter} />
    </div>
    <span class="count">{visible.length} Serien erkannt</span>
    {#if open.length > 1}
      <button class="btn" onclick={createAll} disabled={creatingAll}>
        <i class="fa-solid {creatingAll ? 'fa-spinner fa-spin' : 'fa-layer-group'}"></i>
        Alle {open.length} als Playlists anlegen
      </button>
    {/if}
  </div>

  {#if loading}
    <div class="note"><i class="fa-solid fa-spinner fa-spin"></i> Titel werden durchgesehen…</div>
  {:else if visible.length === 0}
    <div class="note">Keine Serien mit mindestens drei nummerierten Folgen gefunden.</div>
  {:else}
    <div class="list">
      {#each visible as item (item.key)}
        <div class="row">
          <div class="info">
            <span class="name">{item.name}</span>
            <span class="meta">{item.channel_name || 'Unbekannt'} · {item.episode_count} Folgen · {range(item)}</span>
            <span class="sample">{item.sample.join(' · ')}</span>
          </div>
          {#if item.playlist_id}
            <button class="btn ghost" onclick={() => create(item)} disabled={busy.has(item.key)}
                    title="Neue Folgen in die vorhandene Playlist einsortieren">
              <i class="fa-solid {busy.has(item.key) ? 'fa-spinner fa-spin' : 'fa-rotate'}"></i> Auffrischen
            </button>
          {:else}
            <button class="btn" onclick={() => create(item)} disabled={busy.has(item.key)}>
              <i class="fa-solid {busy.has(item.key) ? 'fa-spinner fa-spin' : 'fa-plus'}"></i> Playlist anlegen
            </button>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .series { margin-bottom: 22px; padding: 14px; background: var(--bg-secondary); border-radius: 12px; }
  .head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
  .filter { display: flex; align-items: center; gap: 8px; padding: 0 10px; min-width: 220px;
            background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 8px; color: var(--text-tertiary); }
  .filter:focus-within { border-color: var(--accent-primary); }
  .filter input { flex: 1; border: none; background: none; outline: none; color: var(--text-primary); font: inherit; font-size: 0.84rem; padding: 7px 0; }
  .count { color: var(--text-tertiary); font-size: 0.8rem; margin-right: auto; }
  .note { padding: 28px; text-align: center; color: var(--text-tertiary); }
  .list { display: flex; flex-direction: column; gap: 4px; max-height: 52vh; overflow-y: auto; }
  .row { display: flex; align-items: center; gap: 14px; padding: 9px 10px; border-radius: 8px; }
  .row:hover { background: var(--bg-tertiary); }
  .info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .name { color: var(--text-primary); font-weight: 600; font-size: 0.92rem; }
  .meta { color: var(--text-secondary); font-size: 0.78rem; }
  .sample { color: var(--text-tertiary); font-size: 0.74rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .btn { display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; border: none; border-radius: 8px; cursor: pointer;
         background: var(--accent-primary); color: #fff; font: inherit; font-size: 0.8rem; font-weight: 600; white-space: nowrap; }
  .btn:disabled { opacity: 0.6; cursor: default; }
  .btn.ghost { background: var(--bg-tertiary); color: var(--text-secondary); }
  .btn.ghost:hover:not(:disabled) { color: var(--text-primary); }
</style>

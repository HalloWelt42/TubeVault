<!--
  TubeVault – Nachvertonung (Warteliste)
  Zeigt, welche Videos auf ihre Nachvertonung warten, was gerade läuft und
  was fertig ist. Vorgemerkt wird am Video in der Wiedergabe; die Arbeit
  erledigt der Nachvertoner auf einem anderen Rechner.
-->
<script>
  import { api } from '../lib/api/client.js';
  import { navigate } from '../lib/router/router.js';
  import { toast } from '../lib/stores/notifications.js';
  import { formatDuration, formatDateRelative } from '../lib/utils/format.js';
  import PageHeader from '../lib/components/common/PageHeader.svelte';

  const REFRESH_MS = 5000;
  const STATUS = {
    working: { label: 'In Arbeit', icon: 'fa-solid fa-gear fa-spin', tone: 'accent' },
    queued: { label: 'Wartet', icon: 'fa-solid fa-clock', tone: 'muted' },
    done: { label: 'Fertig', icon: 'fa-solid fa-circle-check', tone: 'ok' },
    error: { label: 'Fehlgeschlagen', icon: 'fa-solid fa-triangle-exclamation', tone: 'error' },
    skipped: { label: 'Übersprungen', icon: 'fa-solid fa-forward', tone: 'muted' },
    cancelled: { label: 'Abgebrochen', icon: 'fa-solid fa-ban', tone: 'muted' },
  };
  const LANGUAGE_NAMES = { de: 'Deutsch', en: 'Englisch', fr: 'Französisch', es: 'Spanisch', it: 'Italienisch' };

  const TABS = [['all', 'Alle'], ['working', 'Läuft'], ['queued', 'Wartet'], ['done', 'Fertig'],
                ['error', 'Fehler'], ['cancelled', 'Abgebrochen']];

  let requests = $state([]);
  let tab = $state('all');
  let voices = $state(null);       // vom Nachvertoner gemeldete Stimmen
  let visible = $derived(tab === 'all' ? requests : requests.filter(r => r.status === tab));
  // Letztes Lebenszeichen eines Nachvertoners: der jüngste Auftrag, der abgeholt wurde
  let lastWorker = $derived(requests.find(r => r.worker) || null);
  let counts = $state({ queued: 0, working: 0, done: 0, error: 0, skipped: 0, cancelled: 0 });
  const isOpen = (request) => request.status === 'queued' || request.status === 'working';
  let loading = $state(true);

  const SUBTITLE_USE = {
    any: 'Untertitel der Quelle als Transkript',
    manual: 'nur vom Autor erstellte Untertitel',
    never: 'aus dem Ton transkribiert',
  };

  const languageName = (code) => LANGUAGE_NAMES[code] || (code || '').toUpperCase();

  // "Englisch → Deutsch"; ist die Sprache des Originals noch nicht bekannt, nur das Ziel
  function direction(request) {
    const target = languageName(request.target_language);
    if (request.source_language === request.target_language) return `${target}, neu gesprochen`;
    return request.source_language ? `${languageName(request.source_language)} → ${target}` : `nach ${target}`;
  }

  function timing(request) {
    if (request.status === 'working' && request.claimed_at) return `läuft seit ${formatDateRelative(request.claimed_at).replace(/^vor /, '')}`;
    if (request.status === 'done' && request.finished_at) return `fertig ${formatDateRelative(request.finished_at)}`;
    if (request.status === 'cancelled' && request.finished_at) return `abgebrochen ${formatDateRelative(request.finished_at)}`;
    return `vorgemerkt ${formatDateRelative(request.created_at)}`;
  }

  async function load() {
    try {
      const data = await api.getDubbingRequests();
      requests = data.requests || [];
      counts = data.counts || counts;
    } catch (e) { toast.error(e.message); }
    loading = false;
  }

  async function loadVoices() {
    try { voices = await api.getDubbingVoices(); } catch { voices = null; }
  }

  async function retry(request) {
    try { await api.retryDubbing(request.id); toast.success('Erneut vorgemerkt'); load(); }
    catch (e) { toast.error(e.message); }
  }

  // Offene Aufträge werden abgebrochen und bleiben sichtbar; abgeschlossene
  // lassen sich aus der Liste nehmen.
  async function remove(request) {
    try {
      if (isOpen(request)) { await api.cancelDubbing(request.id); toast.info('Auftrag abgebrochen'); }
      else await api.removeDubbing(request.id);
      load();
    } catch (e) { toast.error(e.message); }
  }

  $effect(() => {
    load();
    loadVoices();
    const timer = setInterval(load, REFRESH_MS);
    return () => clearInterval(timer);
  });
</script>

<div class="dubbing">
  <PageHeader title="Nachvertonung" icon="fa-solid fa-language" count={counts.queued + counts.working}
              unit="offener Auftrag" unitPlural="offene Aufträge" />

  <div class="dstats">
    <div class="dstat act"><span><span class="k num">{counts.working}</span><span class="l">läuft</span></span></div>
    <div class="dstat wait"><span><span class="k num">{counts.queued}</span><span class="l">wartet</span></span></div>
    <div class="dstat done"><span><span class="k num">{counts.done}</span><span class="l">fertig</span></span></div>
    {#if counts.error > 0}<div class="dstat err"><span><span class="k num">{counts.error}</span><span class="l">Fehler</span></span></div>{/if}
    {#if counts.cancelled > 0}<div class="dstat canc"><span><span class="k num">{counts.cancelled}</span><span class="l">abgebrochen</span></span></div>{/if}
    {#if counts.skipped > 0}<div class="dstat canc"><span><span class="k num">{counts.skipped}</span><span class="l">übersprungen</span></span></div>{/if}
  </div>

  <div class="dgrid">
    <main class="panel">
      <div class="panel-h">
        <h2>Aufträge</h2>
        <span class="panel-sub">· {visible.length} sichtbar</span>
      </div>
      <div class="tabs">
        {#each TABS as [id, label]}
          {@const n = id === 'all' ? requests.length : counts[id] || 0}
          <button class="tab" class:on={tab === id} onclick={() => tab = id}>{label}{#if n > 0}<span class="c">{n}</span>{/if}</button>
        {/each}
      </div>

      {#if loading}
        <div class="empty"><i class="fa-solid fa-spinner fa-spin"></i> Laden…</div>
      {:else if visible.length === 0}
        <div class="empty">
          {#if requests.length === 0}Noch kein Auftrag. Vormerken geht am Video in der Wiedergabe über das Sprach-Symbol.
          {:else}Nichts in dieser Gruppe.{/if}
        </div>
      {:else}
        <div class="list">
          {#each visible as request (request.id)}
            {@const state = STATUS[request.status] || STATUS.queued}
            <div class="item {state.tone}">
              <button class="thumb" onclick={() => navigate(`/watch/${request.video_id}`)} title="Video öffnen">
                <img src={api.thumbnailUrl(request.video_id)} alt="" loading="lazy" />
              </button>
              <div class="body">
                <button class="title" onclick={() => navigate(`/watch/${request.video_id}`)}>
                  {request.title || request.video_id}
                </button>
                <div class="meta">
                  {request.channel_name || 'Unbekannt'}
                  {#if request.duration} · {formatDuration(request.duration)}{/if}
                  · {direction(request)} · {timing(request)}
                </div>
                <div class="meta">
                  Stimme: {request.voice || 'Vorauswahl'} · {SUBTITLE_USE[request.subtitles] || ''}
                </div>
                {#if request.status === 'working'}
                  <div class="progress"><span style="width: {Math.round((request.progress || 0) * 100)}%"></span></div>
                {/if}
                {#if request.note || request.status === 'working'}
                  <div class="note">
                    {#if request.status === 'working'}{Math.round((request.progress || 0) * 100)} %{#if request.note} · {/if}{/if}{request.note || ''}
                  </div>
                {/if}
              </div>
              <div class="state">
                <span class="chip {state.tone}"><i class={state.icon}></i> {state.label}</span>
                {#if request.status === 'working' && request.worker}<span class="worker">{request.worker}</span>{/if}
              </div>
              <div class="actions">
                {#if request.status === 'done'}
                  <button class="icon-btn" title="Video mit der neuen Tonspur öffnen"
                          onclick={() => navigate(`/watch/${request.video_id}`)}>
                    <i class="fa-solid fa-play"></i>
                  </button>
                {/if}
                {#if ['error', 'skipped', 'cancelled'].includes(request.status)}
                  <button class="icon-btn" title="Erneut vormerken" onclick={() => retry(request)}>
                    <i class="fa-solid fa-rotate-right"></i>
                  </button>
                {/if}
                <button class="icon-btn" onclick={() => remove(request)}
                        title={isOpen(request) ? 'Auftrag abbrechen'
                               : request.status === 'done' ? 'Aus der Liste nehmen (die Tonspur bleibt)' : 'Aus der Liste nehmen'}>
                  <i class="fa-solid {isOpen(request) ? 'fa-stop' : 'fa-xmark'}"></i>
                </button>
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </main>

    <aside class="daside">
      <section class="panel">
        <div class="panel-h"><h2>Nachvertoner</h2></div>
        <div class="side-body">
          <div class="srow"><span class="sk">Zuletzt gemeldet</span>
            <span class="sv">{lastWorker ? `${lastWorker.worker}, ${formatDateRelative(lastWorker.claimed_at || lastWorker.created_at)}` : 'noch nie'}</span></div>
          <div class="srow"><span class="sk">Stimmen</span>
            <span class="sv">{voices?.voices?.length ? `${voices.voices.length} verfügbar, gemeldet ${formatDateRelative(voices.reported_at)}` : 'noch keine gemeldet'}</span></div>
          {#if voices?.default}
            <div class="srow"><span class="sk">Vorauswahl</span><span class="sv">{voices.default}</span></div>
          {/if}
          {#if voices?.voices?.length}
            <div class="voices">
              {#each voices.voices as name}<span class="voice" class:default={name === voices.default}>{name}</span>{/each}
            </div>
          {/if}
        </div>
      </section>

      <section class="panel">
        <div class="panel-h"><h2>So läuft es</h2></div>
        <div class="side-body steps">
          <p><b>1.</b> Am Video in der Wiedergabe das Sprach-Symbol wählen: Zielsprache, Stimme, Untertitel-Nutzung.</p>
          <p><b>2.</b> Der Nachvertoner auf einem anderen Rechner holt den Auftrag, sobald dort Kapazität frei ist. Läuft er nicht, bleibt der Auftrag hier liegen.</p>
          <p><b>3.</b> Die fertige Tonspur kommt zurück und ist in der Wiedergabe umschaltbar; das Video bleibt unverändert. Ist die Zielsprache die des Originals, wird nur mit anderer Stimme neu gesprochen.</p>
        </div>
      </section>
    </aside>
  </div>
</div>

<style>
  .dubbing { padding: 24px; }
  .dstats { display:flex; gap:10px; flex-wrap:wrap; margin-bottom:18px; }
  .dstat { display:flex; align-items:center; gap:10px; padding:10px 14px; min-width:112px; background:var(--bg-secondary); border:1px solid var(--border-primary); border-radius:12px; }
  .dstat .k { font-size:22px; font-weight:700; letter-spacing:-0.02em; line-height:1; display:block; }
  .dstat .l { font-size:11px; color:var(--text-tertiary); font-weight:600; text-transform:uppercase; letter-spacing:.04em; }
  .dstat.act .k { color:var(--accent-primary); }
  .dstat.done .k { color:var(--status-success); }
  .dstat.err .k { color:var(--status-error); }
  .dstat.wait .k { color:var(--text-secondary); }
  .dstat.canc .k { color:var(--text-tertiary); }
  .num { font-variant-numeric: tabular-nums; }

  .dgrid { display:grid; grid-template-columns: minmax(0,1.618fr) minmax(280px,1fr); gap:24px; align-items:start; }
  @media (max-width: 1024px) { .dgrid { grid-template-columns:1fr; } }
  .daside { display:flex; flex-direction:column; gap:18px; }
  .panel { background:var(--bg-secondary); border:1px solid var(--border-primary); border-radius:14px; }
  .panel-h { display:flex; align-items:center; gap:10px; padding:14px 16px; border-bottom:1px solid var(--border-primary); }
  .panel-h h2 { margin:0; font-size:14px; font-weight:700; color:var(--text-primary); }
  .panel-sub { font-size:12px; color:var(--text-tertiary); }
  .tabs { display:flex; gap:3px; padding:10px 12px; border-bottom:1px solid var(--border-primary); flex-wrap:wrap; }
  .tab { display:inline-flex; align-items:center; gap:7px; padding:7px 13px; border-radius:999px; border:1px solid transparent; background:none; color:var(--text-secondary); font-size:12.5px; font-weight:600; cursor:pointer; }
  .tab:hover { background:var(--bg-hover); color:var(--text-primary); }
  .tab.on { background:var(--accent-muted); color:var(--accent-primary); border-color:color-mix(in srgb, var(--accent-primary) 35%, transparent); }
  .tab .c { font-size:11px; padding:0 6px; border-radius:999px; background:var(--bg-primary); color:var(--text-secondary); font-weight:700; min-width:18px; text-align:center; }
  .tab.on .c { background:var(--accent-primary); color:#fff; }

  .empty { padding: 48px 20px; text-align: center; color: var(--text-tertiary); font-size: 0.88rem; line-height: 1.5; }
  .list { display: flex; flex-direction: column; }
  .item {
    display: grid; grid-template-columns: 112px minmax(0, 1fr) auto auto; gap: 14px; align-items: center;
    padding: 12px 14px; border-bottom: 1px solid var(--border-primary);
  }
  .item:last-child { border-bottom: none; }
  .thumb { padding: 0; border: none; background: var(--bg-tertiary); border-radius: 6px; overflow: hidden; aspect-ratio: 16 / 9; cursor: pointer; }
  .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .title { display: block; max-width: 100%; padding: 0; border: none; background: none; text-align: left; cursor: pointer;
           color: var(--text-primary); font-size: 0.92rem; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .title:hover { color: var(--accent-primary); }
  .meta { margin-top: 3px; color: var(--text-tertiary); font-size: 0.78rem; }
  .note { margin-top: 5px; color: var(--text-secondary); font-size: 0.78rem; }
  .item.error .note { color: var(--status-error); }
  .progress { margin-top: 7px; height: 4px; background: var(--bg-tertiary); border-radius: 2px; overflow: hidden; }
  .progress span { display: block; height: 100%; background: var(--accent-primary); transition: width 0.4s; }
  .state { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }
  .chip { display:inline-flex; align-items:center; gap:5px; font-size:11px; font-weight:700; padding:3px 9px; border-radius:999px; white-space:nowrap; background: var(--bg-tertiary); color: var(--text-secondary); }
  .chip i { font-size:10px; }
  .chip.accent { background: var(--accent-muted); color: var(--accent-primary); }
  .chip.ok { background: color-mix(in srgb, var(--status-success) 15%, transparent); color: var(--status-success); }
  .chip.error { background: color-mix(in srgb, var(--status-error) 15%, transparent); color: var(--status-error); }
  .worker { font-size: 0.7rem; color: var(--text-tertiary); }
  .actions { display: flex; gap: 4px; }
  .icon-btn { width: 32px; height: 32px; border: none; border-radius: 6px; background: none; color: var(--text-tertiary); cursor: pointer; }
  .icon-btn:hover { background: var(--bg-tertiary); color: var(--text-primary); }

  .side-body { padding: 12px 16px 14px; font-size: 0.82rem; }
  .srow { display: flex; gap: 10px; padding: 5px 0; }
  .sk { flex: 0 0 120px; color: var(--text-tertiary); }
  .sv { color: var(--text-primary); }
  .voices { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
  .voice { padding: 3px 9px; border-radius: 999px; background: var(--bg-tertiary); color: var(--text-secondary); font-size: 0.74rem; }
  .voice.default { color: var(--accent-primary); background: var(--accent-muted); }
  .steps p { margin: 0 0 10px; color: var(--text-secondary); line-height: 1.5; }
  .steps p:last-child { margin: 0; }
  .steps b { color: var(--text-primary); }
</style>

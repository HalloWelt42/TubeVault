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
  };
  const LANGUAGE_NAMES = { de: 'Deutsch', en: 'Englisch', fr: 'Französisch', es: 'Spanisch', it: 'Italienisch' };

  let requests = $state([]);
  let counts = $state({ queued: 0, working: 0, done: 0, error: 0, skipped: 0 });
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
    return request.source_language ? `${languageName(request.source_language)} → ${target}` : `nach ${target}`;
  }

  function timing(request) {
    if (request.status === 'working' && request.claimed_at) return `läuft seit ${formatDateRelative(request.claimed_at).replace(/^vor /, '')}`;
    if (request.status === 'done' && request.finished_at) return `fertig ${formatDateRelative(request.finished_at)}`;
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

  async function retry(request) {
    try { await api.retryDubbing(request.id); toast.success('Erneut vorgemerkt'); load(); }
    catch (e) { toast.error(e.message); }
  }

  async function remove(request) {
    try { await api.removeDubbing(request.id); load(); }
    catch (e) { toast.error(e.message); }
  }

  $effect(() => {
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => clearInterval(timer);
  });
</script>

<div class="dubbing">
  <PageHeader title="Nachvertonung" icon="fa-solid fa-language" count={counts.queued + counts.working}
              unit="offener Auftrag" unitPlural="offene Aufträge" />

  <p class="intro">
    Vormerken: am Video in der Wiedergabe über das Sprach-Symbol - dort wählst du Stimme und Zielsprache.
    Vertont wird, sobald auf dem Rechner des Nachvertoners Kapazität frei ist. Die fertige Tonspur lässt
    sich in der Wiedergabe umschalten; das Video bleibt unverändert.
  </p>

  <div class="pills">
    <span class="pill accent">{counts.working} in Arbeit</span>
    <span class="pill">{counts.queued} warten</span>
    <span class="pill ok">{counts.done} fertig</span>
    {#if counts.error > 0}<span class="pill error">{counts.error} fehlgeschlagen</span>{/if}
    {#if counts.skipped > 0}<span class="pill">{counts.skipped} übersprungen</span>{/if}
  </div>

  {#if loading}
    <div class="empty"><i class="fa-solid fa-spinner fa-spin"></i> Laden…</div>
  {:else if requests.length === 0}
    <div class="empty">Die Warteliste ist leer.</div>
  {:else}
    <div class="list">
      {#each requests as request (request.id)}
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
            <span class="badge"><i class={state.icon}></i> {state.label}</span>
            {#if request.status === 'working' && request.worker}<span class="worker">{request.worker}</span>{/if}
          </div>
          <div class="actions">
            {#if request.status === 'error' || request.status === 'skipped'}
              <button class="icon-btn" title="Erneut vormerken" onclick={() => retry(request)}>
                <i class="fa-solid fa-rotate-right"></i>
              </button>
            {/if}
            <button class="icon-btn" onclick={() => remove(request)}
                    title={request.status === 'done' ? 'Aus der Liste nehmen (die Tonspur bleibt)' : 'Auftrag entfernen'}>
              <i class="fa-solid fa-xmark"></i>
            </button>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .dubbing { padding: 24px; }
  .intro { max-width: 880px; color: var(--text-secondary); font-size: 0.86rem; line-height: 1.5; margin-bottom: 14px; }
  .pills { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 18px; }
  .pill { padding: 4px 12px; border-radius: 999px; background: var(--bg-secondary); color: var(--text-secondary); font-size: 0.78rem; font-weight: 600; }
  .pill.accent { color: var(--accent-primary); }
  .pill.ok { color: var(--status-success); }
  .pill.error { color: var(--status-error); }
  .empty { padding: 60px 20px; text-align: center; color: var(--text-tertiary); }
  .list { display: flex; flex-direction: column; gap: 8px; }
  .item {
    display: grid; grid-template-columns: 128px minmax(0, 1fr) auto auto; gap: 14px; align-items: center;
    padding: 10px 14px 10px 10px; background: var(--bg-secondary); border-radius: 10px;
  }
  .thumb { padding: 0; border: none; background: var(--bg-tertiary); border-radius: 6px; overflow: hidden; aspect-ratio: 16 / 9; cursor: pointer; }
  .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .title { display: block; max-width: 100%; padding: 0; border: none; background: none; text-align: left; cursor: pointer;
           color: var(--text-primary); font-size: 0.92rem; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .title:hover { color: var(--accent-primary); }
  .meta { margin-top: 3px; color: var(--text-tertiary); font-size: 0.78rem; }
  .note { margin-top: 5px; color: var(--text-secondary); font-size: 0.78rem; }
  .item.error .note { color: var(--status-error); }
  .progress { margin-top: 7px; height: 4px; max-width: 420px; background: var(--bg-tertiary); border-radius: 2px; overflow: hidden; }
  .progress span { display: block; height: 100%; background: var(--accent-primary); transition: width 0.4s; }
  .state { display: flex; flex-direction: column; align-items: flex-end; gap: 3px; }
  .badge { font-size: 0.78rem; font-weight: 600; color: var(--text-secondary); white-space: nowrap; }
  .item.accent .badge { color: var(--accent-primary); }
  .item.ok .badge { color: var(--status-success); }
  .item.error .badge { color: var(--status-error); }
  .worker { font-size: 0.7rem; color: var(--text-tertiary); }
  .actions { display: flex; gap: 4px; }
  .icon-btn { width: 32px; height: 32px; border: none; border-radius: 6px; background: none; color: var(--text-tertiary); cursor: pointer; }
  .icon-btn:hover { background: var(--bg-tertiary); color: var(--text-primary); }
</style>

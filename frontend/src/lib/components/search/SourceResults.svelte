<!--
  Bei der Quelle gesucht (nur auf Wunsch): Videos und Kanäle der Quelle,
  seitenweise beim Rollen. Je Video: schon geladen abspielen, sonst schnell
  laden oder Stream wählen, in die Schnell-Playlist, Kanal abonnieren oder
  aus der Quelle-Suche sperren.
-->
<script>
  import { api } from '../../api/client.js';
  import { navigate } from '../../router/router.js';
  import { toast } from '../../stores/notifications.js';
  import { formatDuration, formatViews } from '../../utils/format.js';
  import { createListLoader } from '../../utils/listLoader.svelte.js';
  import { infiniteScroll } from '../../utils/infiniteScroll.js';
  import ConfirmDialog from '../common/ConfirmDialog.svelte';
  import QuickPlaylistBtn from '../common/QuickPlaylistBtn.svelte';
  import StreamDialog from '../common/StreamDialog.svelte';
  import Marked from './Marked.svelte';

  const PER_PAGE = 20;

  let { q, terms = [] } = $props();

  let channels = $state([]);
  let subscribed = $state(new Set());
  let busy = $state(new Set());
  let streamDialog = $state(null);
  let confirmRef;

  const source = createListLoader(async (page) => {
    const result = await api.searchYouTubePaged(q, page, PER_PAGE);
    if (page === 1) channels = (result.channels || []).filter((c) => c?.id);
    return { items: result.videos || [], hasMore: !!result.has_more };
  });

  async function loadSubscriptions() {
    try {
      const res = await api.getSubscriptions();
      subscribed = new Set((res.subscriptions || res || []).map((s) => s.channel_id));
    } catch { /* ohne Abo-Stand bleibt nur der Knopf */ }
  }

  $effect(() => { q; source.load(true); });
  $effect(() => { loadSubscriptions(); });

  function mark(id, change) {
    source.items = source.items.map((v) => (v.id === id ? { ...v, ...change } : v));
  }

  async function quickLoad(video) {
    busy = new Set([...busy, video.id]);
    try {
      await api.addDownload({ url: `https://www.youtube.com/watch?v=${video.id}` });
      mark(video.id, { already_in_queue: true });
      toast.success(`In der Warteschlange: ${video.title}`);
    } catch (e) { toast.error(e.message); }
    busy = new Set([...busy].filter((id) => id !== video.id));
  }

  async function openStreams(video) {
    streamDialog = { video, loading: true, streams: [], videoStreams: [], audioStreams: [], captions: [],
                     selectedVideoItag: null, selectedAudioItag: null, mergeAudio: true };
    try {
      const info = await api.getVideoInfo(`https://www.youtube.com/watch?v=${video.id}`);
      const byQuality = (a, b) => (parseInt(b.quality) || 0) - (parseInt(a.quality) || 0);
      const videoStreams = (info.streams || []).filter((s) => s.type === 'video').sort(byQuality);
      const audioStreams = (info.streams || []).filter((s) => s.type === 'audio').sort(byQuality);
      streamDialog = { ...streamDialog, streams: info.streams || [], videoStreams, audioStreams, captions: info.captions || [],
                       loading: false, alreadyDownloaded: info.already_downloaded, unavailableReason: info.unavailable_reason || null,
                       selectedVideoItag: videoStreams[0]?.itag || null,
                       selectedAudioItag: videoStreams[0]?.is_progressive ? null : (audioStreams[0]?.itag || null) };
    } catch (e) {
      toast.error(`Streams nicht abrufbar: ${e.message}`);
      streamDialog = null;
    }
  }

  async function loadStream({ itag = null, audioItag = null, mergeAudio = true, audioOnly = false, priority = 0 } = {}) {
    const video = streamDialog?.video;
    if (!video) return;
    try {
      await api.addDownload({ url: `https://www.youtube.com/watch?v=${video.id}`, audio_only: audioOnly, itag,
                              audio_itag: audioItag, merge_audio: mergeAudio, priority });
      mark(video.id, { already_in_queue: true });
      toast.success(priority >= 10 ? 'Sofort-Download gestartet' : 'In die Warteschlange gelegt');
      streamDialog = null;
    } catch (e) { toast.error(e.message); }
  }

  async function subscribe(video) {
    try {
      await api.addSubscription({ channel_id: video.channel_id, channel_name: video.channel_name });
      subscribed = new Set([...subscribed, video.channel_id]);
      toast.success(`Abonniert: ${video.channel_name}`);
    } catch (e) { toast.error(e.message); }
  }

  async function block(video) {
    if (!await confirmRef.ask(`Kanal "${video.channel_name}" sperren?`, 'Seine Videos erscheinen nicht mehr in der Suche bei der Quelle.',
                              { confirmLabel: 'Sperren' })) return;
    try {
      await api.blockChannel(video.channel_id, video.channel_name);
      source.items = source.items.filter((v) => v.channel_id !== video.channel_id);
      toast.success(`Gesperrt: ${video.channel_name}`);
    } catch (e) { toast.error(e.message); }
  }
</script>

{#if channels.length}
  <div class="kanaele">
    {#each channels.slice(0, 6) as channel (channel.id)}
      <button class="kanal" onclick={() => navigate(`/channel/${channel.id}`)}>
        <i class="fa-solid fa-tv"></i> <Marked text={channel.name} {terms} />
      </button>
    {/each}
  </div>
{/if}

{#if source.loading && !source.items.length}
  <div class="hinweis"><i class="fa-solid fa-spinner fa-spin"></i> Die Quelle wird gefragt</div>
{:else if !source.items.length}
  <div class="hinweis">Die Quelle kennt dazu nichts.</div>
{/if}

{#each source.items as video (video.id)}
  <div class="treffer" class:geladen={video.already_downloaded}>
    <div class="bild">
      <img src={video.already_downloaded ? api.thumbnailUrl(video.id) : api.rssThumbUrl(video.id)} alt="" loading="lazy"
           onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
      {#if video.duration}<span class="dauer zahl">{formatDuration(video.duration)}</span>{/if}
    </div>
    <div class="text">
      <div class="titel"><Marked text={video.title} {terms} /></div>
      <div class="zeile">
        <button class="kanalname" onclick={() => navigate(`/channel/${video.channel_id}`)}>{video.channel_name || ''}</button>
        {#if video.view_count}<span><span class="zahl">{formatViews(video.view_count)}</span> Aufrufe</span>{/if}
        {#if video.already_downloaded}<span class="marke ok"><i class="fa-solid fa-check"></i> geladen</span>
        {:else if video.already_in_queue}<span class="marke"><i class="fa-solid fa-clock"></i> wartet</span>{/if}
        {#if video.channel_id && subscribed.has(video.channel_id)}<span class="marke"><i class="fa-solid fa-rss"></i> abonniert</span>{/if}
      </div>
    </div>
    <div class="aktionen">
      {#if video.already_downloaded}
        <button class="tv-knopf klein haupt" onclick={() => navigate(`/watch/${video.id}`)}><i class="fa-solid fa-play"></i> Abspielen</button>
      {:else}
        <button class="tv-knopf klein" onclick={() => navigate(`/watch/${video.id}`)} title="Von der Quelle abspielen, ohne zu laden">
          <i class="fa-solid fa-play"></i> Ansehen</button>
        <button class="tv-knopf klein haupt" onclick={() => quickLoad(video)} disabled={busy.has(video.id) || video.already_in_queue}
                title="In Standard-Qualität laden"><i class="fa-solid fa-download"></i> Laden</button>
        <button class="tv-knopf klein symbol" onclick={() => openStreams(video)} title="Qualität und Tonspur wählen" aria-label="Stream wählen">
          <i class="fa-solid fa-sliders"></i></button>
      {/if}
      <QuickPlaylistBtn videoId={video.id} title={video.title} channelName={video.channel_name} channelId={video.channel_id} />
      {#if video.channel_id && !subscribed.has(video.channel_id)}
        <button class="tv-knopf klein symbol" onclick={() => subscribe(video)} title="Kanal abonnieren" aria-label="Abonnieren">
          <i class="fa-solid fa-rss"></i></button>
      {/if}
      <button class="tv-knopf klein symbol ohne" onclick={() => block(video)} title="Kanal für die Suche bei der Quelle sperren" aria-label="Kanal sperren">
        <i class="fa-solid fa-ban"></i></button>
    </div>
  </div>
{/each}
<div use:infiniteScroll={{ onLoadMore: source.loadMore, canLoad: source.canLoad }}></div>
{#if source.loadingMore}<div class="hinweis"><i class="fa-solid fa-spinner fa-spin"></i> Weitere Treffer werden geholt</div>{/if}

<StreamDialog dialog={streamDialog} showAudioOnly={true} ondownload={loadStream} onclose={() => streamDialog = null} />
<ConfirmDialog bind:this={confirmRef} />

<style>
  .kanaele { display: flex; flex-wrap: wrap; gap: var(--tv-a2); margin-bottom: var(--tv-a3); }
  .kanal { display: inline-flex; align-items: center; gap: 8px; height: 36px; padding: 0 var(--tv-a3); border: 0;
           border-radius: var(--tv-ecke); background: var(--tv-flaeche); color: var(--tv-text); font: inherit; cursor: pointer; }
  .kanal:hover { background: var(--tv-karte); }
  .kanal i { color: var(--tv-text-3); }
  .treffer { display: grid; grid-template-columns: 168px minmax(0, 1fr) auto; gap: var(--tv-a3); align-items: start;
             padding: var(--tv-a2); border-radius: var(--tv-ecke); }
  .treffer:hover { background: var(--tv-flaeche); }
  .bild { position: relative; aspect-ratio: 16 / 9; border-radius: var(--tv-ecke); overflow: hidden; background: var(--tv-mulde); }
  .bild img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .dauer { position: absolute; right: 5px; bottom: 6px; padding: 1px 6px; border-radius: var(--tv-ecke-klein);
           background: var(--tv-schleier); font-size: var(--tv-gr-marke); }
  .text { min-width: 0; }
  .titel { font-weight: 600; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2;
           -webkit-box-orient: vertical; overflow: hidden; }
  .zeile { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; margin-top: 3px;
           font-size: var(--tv-gr-klein); color: var(--tv-text-2); }
  .kanalname { padding: 0; border: 0; background: none; color: inherit; font: inherit; cursor: pointer; }
  .kanalname:hover { color: var(--tv-akzent); }
  .marke { display: inline-flex; align-items: center; gap: 4px; height: 22px; padding: 0 6px; border-radius: var(--tv-ecke-klein);
           background: var(--tv-karte-2); font-size: var(--tv-gr-marke); }
  .marke.ok { color: var(--tv-erfolg); }
  .aktionen { display: flex; flex-wrap: wrap; gap: 6px; justify-content: flex-end; max-width: 330px; }
  .hinweis { padding: var(--tv-a4); color: var(--tv-text-3); font-size: var(--tv-gr-klein); }
</style>

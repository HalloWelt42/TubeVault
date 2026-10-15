<!--
  Reiter "Playlists" der Kanalseite (Entwurf mockups/kanal.html): je
  Playlist der Quelle eine Karte mit Stand und dem nächsten Schritt
  (Inhalt abrufen, lokal speichern, abspielen, fehlende laden, abgleichen),
  dazu lokale Playlists dieses Kanals ohne Gegenstück bei der Quelle.
  Abrufe laufen als Hintergrundaufträge; die Karte zeigt, was gerade läuft.
-->
<script>
  import { onDestroy } from 'svelte';
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';
  import { navigate } from '../../router/router.js';
  import { followJob } from '../../utils/followJob.js';
  import { num } from './channelView.js';

  const BATCH = 20;          // so viele fehlende Videos je Klick in die Warteschlange

  /** playlists/localPlaylists: aus api.getChannelPlaylists; onreload(): neu laden */
  let { channelId, playlists = [], localPlaylists = [], onreload } = $props();

  let busy = $state({});     // Playlist-Kennung (oder 'liste') -> was gerade läuft
  let stops = [];

  let linked = $derived(new Map(localPlaylists.map((lp) => [lp.id, lp])));
  let localOnly = $derived(localPlaylists.filter((lp) => !playlists.some((pl) => pl.local_playlist_id === lp.id)));

  /** Hintergrundauftrag starten und ihm folgen; danach neu laden. */
  async function runJob(key, label, start, done) {
    busy[key] = label;
    try {
      const { job_id: jobId } = await start();
      stops.push(followJob(jobId, {
        onEnd: (job) => {
          delete busy[key];
          if (job?.status === 'error') toast.error(job.error_message || `${label} fehlgeschlagen`);
          else if (done) toast.success(done);
          onreload();
        },
      }));
    } catch (e) { delete busy[key]; toast.error(e.message); }
  }

  const fetchList = () => runJob('liste', 'Liste wird abgerufen', () => api.fetchChannelPlaylists(channelId), 'Playlists der Quelle abgerufen');
  const fetchContent = (pl) => runJob(pl.playlist_id, 'Inhalt wird abgerufen', () => api.fetchPlaylistVideos(pl.playlist_id));
  const saveLocal = (pl) => runJob(pl.playlist_id, pl.local_playlist_id ? 'Wird abgeglichen' : 'Wird gespeichert',
    () => api.importPlaylistToLocal(pl.playlist_id));

  async function queueMissing(pl) {
    busy[pl.playlist_id] = 'Wird eingereiht';
    try {
      const { queued, remaining } = await api.queueMissingPlaylistVideos(pl.playlist_id, BATCH);
      if (queued) toast.success(`${num(queued)} Videos in die Warteschlange${remaining ? `, ${num(remaining)} weitere ladbar` : ''}`);
      else toast.info('Nichts mehr ladbar: alles geladen, gesperrt oder schon in der Warteschlange');
      onreload();
    } catch (e) { toast.error(e.message); }
    delete busy[pl.playlist_id];
  }

  async function toggleVisibility(lp) {
    const next = lp.visibility === 'channel' ? 'global' : 'channel';
    try {
      await api.togglePlaylistVisibility(lp.id, next);
      toast.success(next === 'global' ? 'Playlist überall sichtbar' : 'Playlist nur auf der Kanalseite');
      onreload();
    } catch (e) { toast.error(e.message); }
  }

  const share = (have, total) => (total ? Math.min(100, (have / total) * 100) : 0);
  onDestroy(() => stops.forEach((stop) => stop()));
</script>

<div class="tv-filter">
  <button class="tv-knopf klein" onclick={fetchList} disabled={!!busy.liste}>
    <i class="fa-solid {busy.liste ? 'fa-spinner fa-spin' : 'fa-rotate'}"></i> Playlists der Quelle abrufen</button>
  <span class="tv-schwach tv-klein">Holt Namen und Beschreibungen, lädt keine Videos</span>
</div>

{#snippet visibility(lp)}
  <button class="tv-knopf ohne klein" onclick={() => toggleVisibility(lp)}
          title={lp.visibility === 'channel' ? 'Nur auf der Kanalseite sichtbar - Klick zeigt sie überall' : 'Überall sichtbar - Klick zeigt sie nur auf der Kanalseite'}>
    <i class="fa-solid {lp.visibility === 'channel' ? 'fa-eye-slash' : 'fa-eye'}"></i> {lp.visibility === 'channel' ? 'Nur hier' : 'Überall'}</button>
{/snippet}

{#if !playlists.length && !localOnly.length}
  <div class="tv-leer">Keine Playlists gespeichert. "Playlists der Quelle abrufen" zeigt die öffentlichen Playlists dieses Kanals.</div>
{:else}
  <div class="raster">
    {#each playlists as pl (pl.playlist_id)}
      {@const known = pl.video_ids?.length > 0}
      {@const missing = Math.max(0, pl.video_count - pl.have_count)}
      {@const local = linked.get(pl.local_playlist_id)}
      <div class="karte">
        <div class="titel">{pl.title}</div>
        <div class="stand">
          <span><span class="zahl">{num(pl.video_count)}</span> Videos</span>
          {#if known}
            <span><span class="zahl">{num(pl.have_count)}</span> lokal</span>
            {#if missing}<span><span class="zahl">{num(missing)}</span> nicht geladen</span>
            {:else}<span class="tv-zustand fertig"><i class="fa-solid fa-check"></i> vollständig</span>{/if}
          {:else}
            <span>Inhalt noch nicht abgerufen</span>
          {/if}
        </div>
        {#if known}<div class="balken"><b style:width="{share(pl.have_count, pl.video_count)}%"></b></div>{/if}
        {#if busy[pl.playlist_id]}
          <div class="laeuft tv-klein"><i class="fa-solid fa-spinner fa-spin"></i> {busy[pl.playlist_id]}</div>
        {:else}
          <div class="tun">
            {#if !known}
              <button class="tv-knopf haupt klein" onclick={() => fetchContent(pl)} title="Liest, welche Videos in der Playlist sind; lädt keine Videos">
                <i class="fa-solid fa-list-check"></i> Inhalt abrufen</button>
            {:else}
              {#if pl.local_playlist_id && pl.have_count > 0}
                <button class="tv-knopf haupt klein" onclick={() => navigate(`/playlists?open=${pl.local_playlist_id}&play=1`)}>
                  <i class="fa-solid fa-play"></i> Abspielen</button>
                <button class="tv-knopf klein" onclick={() => navigate(`/playlists?open=${pl.local_playlist_id}`)}>
                  <i class="fa-solid fa-arrow-up-right-from-square"></i> Öffnen</button>
              {/if}
              {#if missing}
                <button class="tv-knopf klein" onclick={() => queueMissing(pl)} title="Die nächsten {BATCH} ladbaren Videos in Playlist-Reihenfolge laden">
                  <i class="fa-solid fa-download"></i> {num(Math.min(missing, BATCH))} laden</button>
              {/if}
              <button class="tv-knopf ohne klein" onclick={() => saveLocal(pl)}
                      title={pl.local_playlist_id ? 'Mit der Quelle abgleichen: neue Videos und Reihenfolge' : 'Als lokale Playlist anlegen; geladene Videos werden verknüpft'}>
                <i class="fa-solid {pl.local_playlist_id ? 'fa-arrows-rotate' : 'fa-bookmark'}"></i> {pl.local_playlist_id ? 'Abgleichen' : 'Lokal speichern'}</button>
              {#if local}{@render visibility(local)}{/if}
            {/if}
          </div>
        {/if}
      </div>
    {/each}
    {#each localOnly as lp (lp.id)}
      <div class="karte">
        <div class="titel">{lp.name}</div>
        <div class="stand"><span><span class="zahl">{num(lp.ready_count || 0)}</span> von <span class="zahl">{num(lp.actual_count || 0)}</span> Videos lokal</span>
          <span class="tv-zustand">Eigene Playlist</span></div>
        {#if lp.actual_count > 0}<div class="balken"><b style:width="{share(lp.ready_count || 0, lp.actual_count)}%"></b></div>{/if}
        <div class="tun">
          {#if lp.ready_count > 0}
            <button class="tv-knopf haupt klein" onclick={() => navigate(`/playlists?open=${lp.id}&play=1`)}><i class="fa-solid fa-play"></i> Abspielen</button>
          {/if}
          <button class="tv-knopf klein" onclick={() => navigate(`/playlists?open=${lp.id}`)}><i class="fa-solid fa-arrow-up-right-from-square"></i> Öffnen</button>
          {@render visibility(lp)}
        </div>
      </div>
    {/each}
  </div>
{/if}

<style>
  .raster { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: var(--tv-a3); }
  .karte { display: flex; flex-direction: column; gap: var(--tv-a2); padding: var(--tv-a4); background: var(--tv-flaeche); border-radius: var(--tv-ecke); }
  .titel { font-weight: 700; overflow-wrap: anywhere; }
  .stand { display: flex; flex-wrap: wrap; align-items: center; gap: var(--tv-a1) var(--tv-a3); font-size: var(--tv-gr-klein); color: var(--tv-text-2); }
  .balken { height: 6px; background: var(--tv-mulde); border-radius: 1px; overflow: hidden; }
  .balken b { display: block; height: 100%; background: var(--tv-akzent); }
  .tun { display: flex; flex-wrap: wrap; gap: var(--tv-a2); margin-top: var(--tv-a1); }
  .laeuft { color: var(--tv-akzent); margin-top: var(--tv-a1); }
</style>

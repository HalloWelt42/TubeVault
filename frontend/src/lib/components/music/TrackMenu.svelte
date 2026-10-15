<!--
  Menü eines Musiktitels: als Nächstes, hinten anstellen, ähnliche Titel,
  Interpret, Video, Lieblingssong, keine Musik, bei Dateien der Sammlung ausblenden. Erscheint an der Klickstelle.
  Nutzung: <TrackMenu bind:this={menu} onChanged={...} />, menu.open(event, track)
-->
<script>
  import { api } from '../../api/client.js';
  import { downloadUrl, isFile } from '../../utils/musicTrack.js';
  import { navigate } from '../../router/router.js';
  import { toast } from '../../stores/notifications.js';
  import { musicPlayer as player } from '../../stores/musicPlayer.svelte.js';

  // onChanged(track, change): change = { favorite }, { removed: true } oder { restored: true }
  let { onChanged = () => {} } = $props();

  let track = $state(null);
  let x = $state(0);
  let y = $state(0);

  export function open(event, item) {
    event.preventDefault();
    event.stopPropagation();
    track = item;
    const width = 270, height = 340;
    x = Math.min(event.clientX, window.innerWidth - width - 8);
    y = Math.min(event.clientY, window.innerHeight - height - 8);
  }

  function close() { track = null; }

  async function act(work) {
    const item = track;
    close();
    try { await work(item); } catch (e) { toast.error(e.message); }
  }

  const actions = [
    { icon: 'fa-forward', label: 'Als Nächstes', run: (t) => { player.playNext(t); toast.info('Läuft als Nächstes'); } },
    { icon: 'fa-list', label: 'Hinten anstellen', run: (t) => { player.enqueue(t); toast.info('Hinten angestellt'); } },
    { icon: 'fa-wand-magic-sparkles', label: 'Ähnliche Titel abspielen', run: (t) => player.playSource(`similar:${t.id}`) },
    { icon: 'fa-shuffle', label: 'Interpret zufällig', run: (t) => player.playSource(t.artist_source, { shuffle: true }) },
    { icon: 'fa-microphone', label: 'Zum Interpreten', run: (t) => navigate('/music', { quelle: t.artist_source }) },
    { trenner: true },
    { icon: 'fa-heart', label: 'Lieblingssong an/aus', run: async (t) => {
        const favorite = await player.toggleFavorite(t);
        onChanged(t, { favorite });
        toast.success(favorite ? 'Zu den Lieblingssongs' : 'Aus den Lieblingssongs entfernt');
      } },
    { icon: 'fa-download', label: 'Ton herunterladen', run: (t) => {
        const link = document.createElement('a');
        link.href = downloadUrl(t);
        link.download = '';
        link.click();
      } },
    { icon: 'fa-display', label: 'Als Video ansehen', video: true, run: (t) => { player.pause(); navigate(`/watch/${t.id}`); } },
    { icon: 'fa-eye-slash', label: 'Ausblenden', file: true, run: async (t) => {
        await api.musicFileHidden(t.id, true);
        onChanged(t, { removed: true });
        toast.undo(`Ausgeblendet: ${t.title}`, async () => {
          await api.musicFileHidden(t.id, false);
          onChanged(t, { restored: true });
        });
      } },
    { icon: 'fa-ban', label: 'Keine Musik', video: true, run: async (t) => {
        await api.setMusicBatch([t.id], false);
        onChanged(t, { removed: true });
        toast.success('Aus der Musik genommen (von Hand, bleibt so)');
      } },
  ];
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && close()} />

{#if track}
  <div class="hintergrund" role="presentation" onclick={close} oncontextmenu={(e) => { e.preventDefault(); close(); }}></div>
  <div class="menue" style:left="{x}px" style:top="{y}px" role="menu">
    <div class="kopf"><div class="t">{track.title}</div><div class="tv-leise tv-klein">{track.artist}</div></div>
    <!-- Was nur ein Video kann, fehlt bei Dateien der eigenen Sammlung -->
    {#each actions.filter(a => (!a.video || !isFile(track)) && (!a.file || isFile(track))) as action}
      {#if action.trenner}<hr />
      {:else}
        <button role="menuitem" onclick={() => act(action.run)}>
          <i class="fa-solid {action.icon}"></i> {action.label}</button>
      {/if}
    {/each}
  </div>
{/if}

<style>
  .hintergrund { position: fixed; inset: 0; z-index: 90; }
  .menue { position: fixed; z-index: 91; width: 270px; padding: 6px; background: var(--tv-karte-2);
           border: 1px solid var(--tv-rand-stark); border-radius: var(--tv-ecke); box-shadow: var(--tv-schatten); }
  .kopf { padding: 6px 10px 8px; border-bottom: 1px solid var(--tv-rand); margin-bottom: 4px; }
  .kopf .t { font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  button { display: flex; align-items: center; gap: var(--tv-a3); width: 100%; padding: 9px 10px; border: 0; background: none;
           color: var(--tv-text); font: inherit; text-align: left; border-radius: var(--tv-ecke-klein); cursor: pointer; }
  button:hover { background: var(--tv-karte-3); }
  button i { width: 18px; color: var(--tv-text-2); }
  hr { border: 0; border-top: 1px solid var(--tv-rand); margin: 6px 4px; }
</style>

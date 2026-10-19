<!--
  Menü eines Musiktitels: als Nächstes, hinten anstellen, ähnliche Titel,
  Interpret (nennt der Titel mehrere, je Genanntem "Zu ..."), Video,
  Lieblingssong, keine Musik, überall in der Musik ausblenden, das ganze Album
  ausschließen. Erscheint an der Klickstelle. Herausnehmen meldet
  sich über utils/musicChanges.js; onChanged bekommt nur den Lieblingssong.
  Nutzung: <TrackMenu bind:this={menu} onChanged={...} />, menu.open(event, track)
-->
<script>
  import { downloadUrl, isFile } from '../../utils/musicTrack.js';
  import { navigate } from '../../router/router.js';
  import { toast } from '../../stores/notifications.js';
  import { musicPlayer as player } from '../../stores/musicPlayer.svelte.js';
  import { excludeAlbum, hideTrack } from '../../utils/musicHiding.js';
  import { artistRefs } from '../../utils/trackArtists.js';
  import { setVideoMusic } from '../../utils/videoMusic.js';

  // onChanged(track, { favorite })
  let { onChanged = () => {} } = $props();

  const WIDTH = 270, EDGE = 8;

  let track = $state(null);
  let x = $state(0);
  let y = $state(0);
  let menuHeight = $state(0);       // gemessen: je nach Titel mehr oder weniger Einträge

  // Ganz im Fenster: ragt das Menü unten hinaus, rückt es nach oben
  let top = $derived(Math.max(EDGE, Math.min(y, window.innerHeight - menuHeight - EDGE)));

  export function open(event, item) {
    event.preventDefault();
    event.stopPropagation();
    track = item;
    x = Math.min(event.clientX, window.innerWidth - WIDTH - EDGE);
    y = event.clientY;
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
    { icon: 'fa-shuffle', label: 'Interpret zufällig', artist: true,
      run: (t) => player.playSource(artistRefs(t)[0].source, { shuffle: true }) },
    { artists: true },
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
    { icon: 'fa-circle-minus', label: 'Ausblenden', run: (t) => hideTrack(t) },
    { icon: 'fa-compact-disc', label: 'Album ausschließen', album: true, run: (t) => excludeAlbum(t.album_source) },
    { icon: 'fa-ban', label: 'Keine Musik', video: true, run: (t) => setVideoMusic(t.id, false) },
  ];
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && close()} />

{#if track}
  <div class="hintergrund" role="presentation" onclick={close} oncontextmenu={(e) => { e.preventDefault(); close(); }}></div>
  <div class="menue" style:left="{x}px" style:top="{top}px" role="menu" bind:offsetHeight={menuHeight}>
    <div class="kopf"><div class="t">{track.title}</div><div class="tv-leise tv-klein">{track.artist}</div></div>
    <!-- Was nur ein Video kann, fehlt bei Dateien der eigenen Sammlung -->
    {#each actions.filter(a => (!a.video || !isFile(track)) && (!a.album || track.album_source)
                               && (!(a.artist || a.artists) || artistRefs(track).length)) as action}
      {#if action.trenner}<hr />
      {:else if action.artists}
        {@const refs = artistRefs(track)}
        <!-- Zum Interpreten: nennt der Titel mehrere, für jeden einen Eintrag -->
        {#each refs as ref (ref.source)}
          <button role="menuitem" onclick={() => act(() => navigate('/music', { quelle: ref.source }))}>
            <i class="fa-solid fa-microphone"></i> <span class="name">{refs.length > 1 ? `Zu ${ref.name}` : 'Zum Interpreten'}</span></button>
        {/each}
      {:else}
        <button role="menuitem" onclick={() => act(action.run)}>
          <i class="fa-solid {action.icon}"></i> {action.label}</button>
      {/if}
    {/each}
  </div>
{/if}

<style>
  .hintergrund { position: fixed; inset: 0; z-index: 90; }
  .menue { position: fixed; z-index: 91; width: 270px; max-height: calc(100vh - 16px); overflow-y: auto; padding: 6px; background: var(--tv-karte-2);
           border: 1px solid var(--tv-rand-stark); border-radius: var(--tv-ecke); box-shadow: var(--tv-schatten); }
  .kopf { padding: 6px 10px 8px; border-bottom: 1px solid var(--tv-rand); margin-bottom: 4px; }
  .kopf .t { font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  button { display: flex; align-items: center; gap: var(--tv-a3); width: 100%; padding: 9px 10px; border: 0; background: none;
           color: var(--tv-text); font: inherit; text-align: left; border-radius: var(--tv-ecke-klein); cursor: pointer; }
  button:hover { background: var(--tv-karte-3); }
  button i { width: 18px; color: var(--tv-text-2); }
  .name { min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  hr { border: 0; border-top: 1px solid var(--tv-rand); margin: 6px 4px; }
</style>

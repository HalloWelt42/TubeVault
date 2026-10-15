<!--
  Läuft gerade (Musik): großes Cover (Wischen nach links oder rechts: weiter
  oder zurück), Titel mit Herz, woher der Ton kommt und in welcher Güte,
  Spur und Tasten; unten Liedtext und Warteschlange. Gestaltung nach
  mockups/mobil-musik.html. Gesteuert wird nur der Musikspieler.
-->
<script>
  import { musicPlayer as player, UNDO_MS } from '../../../lib/stores/musicPlayer.svelte.js';
  import { coverUrl, downloadUrl, isFile } from '../../../lib/utils/musicTrack.js';
  import { audioDetails, codecName, trackOrigin } from '../../../lib/utils/audioTech.js';
  import { toast } from '../../../lib/stores/notifications.js';
  import { back, go } from '../../router.js';
  import Spur from '../../parts/Spur.svelte';
  import SpielerKopf from '../../parts/SpielerKopf.svelte';
  import { wischen } from '../../parts/wischen.js';

  const SWIPE_PX = 64;              // ab so weit gilt ein Wischen am Cover
  const REPEAT_LABELS = { off: 'Wiederholen aus', all: 'Alle wiederholen', one: 'Diesen Titel wiederholen' };

  // extra: ein dritter Knopf unten (Snippet), z.B. "Abspielen auf" eines anderen Geräts
  let { extra = null } = $props();

  let track = $derived(player.current);
  let origin = $derived(trackOrigin(track));
  let codec = $derived(codecName(player.audioInfo));
  let details = $derived(audioDetails(player.audioInfo));
  let hasPrev = $derived(player.index > 0);
  let hasNext = $derived(player.index + 1 < player.queue.length || (player.repeat === 'all' && player.queue.length > 1)
                         || (!!player.segment && player.segment.index + 1 < player.segment.count));
  let menu = $state(false);

  // ─── Wischen am Cover (parts/wischen.js): nach links weiter, nach rechts zurück ───
  let swipeDx = $state(null);       // Versatz, solange gewischt wird

  const coverSwipe = {
    onMove: (dx) => { swipeDx = dx; },
    onEnd: (dx) => {
      swipeDx = null;
      if (dx <= -SWIPE_PX && hasNext) player.next();
      else if (dx >= SWIPE_PX && hasPrev) player.previousTrack();
    },
  };

  async function favorite() {
    try { await player.toggleFavorite(); } catch (e) { toast.error(e.message); }
  }

  // ─── Mehr zum Titel ───
  function similar() {
    menu = false;
    player.playSource(`similar:${track.id}`).catch((e) => toast.error(e.message));
  }

  function asVideo() {
    menu = false;
    player.pause();
    go(`/video/${track.id}`);
  }

  async function removeFromList() {
    menu = false;
    const fromPlaylist = !!player.playlistId;
    try {
      await player.removeFromList();
      toast.info(fromPlaylist ? 'Aus der Wiedergabeliste genommen' : 'Aus der Warteschlange genommen');
    } catch (e) { toast.error(e.message); }
  }

  // Gefällt nicht: Videos werden gelöscht, Dateien der Sammlung nur ausgeblendet
  function discardTrack() {
    menu = false;
    const title = track.title;
    const file = isFile(track);
    player.deleteTrack();
    toast.undo(`"${title}" wird ${file ? 'ausgeblendet' : 'gelöscht'}`, () => player.undoDelete(), UNDO_MS);
  }
</script>

<div class="m-spieler">
  <SpielerKopf oben="Spielt aus" name={player.title || 'Auswahl'} onclose={back}>
    {#snippet rechts()}
      <button class="m-rund" onclick={() => menu = true} aria-label="Mehr zum Titel"><i class="fa-solid fa-ellipsis-vertical"></i></button>
    {/snippet}
  </SpielerKopf>

  <div class="m-cover-feld">
    {#key track.id}
      <img src={coverUrl(track)} alt="" draggable="false" class="cover" class:wischt={swipeDx !== null} use:wischen={coverSwipe}
           style:transform={swipeDx !== null ? `translateX(${swipeDx * 0.6}px)` : null}
           onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
    {/key}
  </div>
  <div class="punkte" aria-hidden="true">
    <span class:da={hasPrev}></span><span class="an"></span><span class:da={hasNext}></span>
  </div>

  <div class="m-titelzeile">
    <div class="texte"><div class="t">{track.title}</div><div class="w">{track.artist}</div></div>
    <button class="m-rund herz" class:an={track.favorite} onclick={favorite}
            aria-label={track.favorite ? 'Aus den Lieblingssongs nehmen' : 'Zu den Lieblingssongs'} aria-pressed={!!track.favorite}>
      <i class="fa-{track.favorite ? 'solid' : 'regular'} fa-heart"></i></button>
  </div>
  <div class="technik">
    <i class="fa-solid {origin.icon}"></i>
    <span>{origin.label}{#if codec}{' · '}<b>{codec}</b>{/if}{#each details as detail}{' · '}<span class="zahl">{detail}</span>{/each}</span>
  </div>

  {#if player.segment}
    <button class="abschnitt" onclick={() => go('/jetzt', { ansicht: 'schlange' })} title="Alle Abschnitte">
      <span class="zahl">{player.segment.index + 1}/{player.segment.count}</span> {player.segment.title}</button>
  {/if}

  <div class="spur"><Spur time={player.time} duration={player.duration} onseek={(s) => player.seek(s)}
                          marks={player.segments.slice(1).map((segment) => segment.start)} /></div>

  <div class="m-tasten">
    <button class="klein" class:an={player.shuffle} onclick={() => player.toggleShuffle()} aria-label="Zufall" aria-pressed={player.shuffle}>
      <i class="fa-solid fa-shuffle"></i></button>
    <button onclick={() => player.prev()} aria-label="Zurück"><i class="fa-solid fa-backward-step"></i></button>
    <button class="mitte" onclick={() => player.toggle()} aria-label={player.playing ? 'Pause' : 'Abspielen'}>
      <i class="fa-solid {player.loading ? 'fa-spinner fa-spin' : player.playing ? 'fa-pause' : 'fa-play'}"></i></button>
    <button onclick={() => player.next()} aria-label="Weiter"><i class="fa-solid fa-forward-step"></i></button>
    <button class="klein" class:an={player.repeat !== 'off'} onclick={() => player.cycleRepeat()} aria-label={REPEAT_LABELS[player.repeat]}>
      <i class="fa-solid fa-repeat"></i>{#if player.repeat === 'one'}<b class="eins zahl">1</b>{/if}</button>
  </div>

  <div class="unten">
    {#if track.has_lyrics}
      <button onclick={() => go('/jetzt', { ansicht: 'liedtext' })}><i class="fa-solid fa-align-left"></i>Liedtext</button>
    {/if}
    <button onclick={() => go('/jetzt', { ansicht: 'schlange' })}><i class="fa-solid fa-list-ol"></i>Warteschlange</button>
    {@render extra?.()}
  </div>

  {#if menu}
    <div class="schleier" role="presentation" onclick={() => menu = false}></div>
    <div class="blatt" role="menu" aria-label="Mehr zum Titel">
      <button role="menuitem" onclick={similar}><i class="fa-solid fa-wand-magic-sparkles"></i> Ähnliche Titel spielen</button>
      {#if !isFile(track)}
        <button role="menuitem" onclick={asVideo}><i class="fa-solid fa-display"></i> Als Video ansehen</button>
      {/if}
      <a role="menuitem" href={downloadUrl(track)} download onclick={() => menu = false}><i class="fa-solid fa-download"></i> Ton herunterladen</a>
      <button role="menuitem" onclick={removeFromList}><i class="fa-solid fa-circle-minus"></i>
        {player.playlistId ? 'Aus der Wiedergabeliste nehmen' : 'Aus der Warteschlange nehmen'}</button>
      {#if isFile(track)}
        <button role="menuitem" class="gefahr" onclick={discardTrack}><i class="fa-solid fa-eye-slash"></i> Gefällt nicht: ausblenden</button>
      {:else}
        <button role="menuitem" class="gefahr" onclick={discardTrack}><i class="fa-solid fa-trash-can"></i> Gefällt nicht: Video löschen</button>
      {/if}
    </div>
  {/if}
</div>

<style>
  .cover { touch-action: pan-y; transition: transform 0.2s ease; }
  .cover.wischt { transition: none; }
  .punkte { display: flex; justify-content: center; gap: 6px; margin-top: 8px; flex: none; }
  .punkte span { width: 6px; height: 6px; border-radius: 50%; background: var(--m-faint); opacity: 0; }
  .punkte span.da { opacity: 0.5; }
  .punkte span.an { opacity: 1; background: var(--m-text); }
  .herz.an { color: var(--tv-symbol-rot); }
  .technik { margin-top: 6px; flex: none; font-size: 13px; font-weight: 700; color: var(--m-faint);
             white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .technik > i { margin-right: 4px; }
  .abschnitt { margin-top: 8px; flex: none; min-height: 32px; text-align: left; font-size: 15px; color: var(--m-dim);
               white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .abschnitt .zahl { color: var(--m-accent); font-weight: 700; margin-right: 4px; }
  .technik b { color: var(--tv-erfolg); }
  .spur { margin-top: 10px; flex: none; }
  .eins { position: absolute; right: 8px; bottom: 8px; font-size: 13px; }
  .unten { display: grid; grid-auto-flow: column; grid-auto-columns: 1fr; margin-top: auto; padding-top: 12px; flex: none; }
  .unten > :global(button) { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px;
                             height: 56px; color: var(--m-dim); font-size: 13px; font-weight: 600; }
  .unten > :global(button i) { font-size: 19px; }
  .unten > :global(button.an) { color: var(--m-accent); }
  .schleier { position: absolute; inset: 0; z-index: 3; background: var(--tv-schleier); }
  .blatt { position: absolute; left: 0; right: 0; bottom: 0; z-index: 4; display: flex; flex-direction: column;
           padding: 8px 8px calc(var(--m-safe-bottom) + 12px); background: var(--tv-karte-2); border-radius: var(--m-radius) var(--m-radius) 0 0; }
  .blatt button, .blatt a { display: flex; align-items: center; gap: 14px; min-height: 52px; padding: 0 14px; color: var(--m-text);
                            text-decoration: none; text-align: left; border-radius: var(--m-radius); font-weight: 600; }
  .blatt i { width: 22px; text-align: center; color: var(--m-dim); }
  .blatt :is(button, a):active { background: var(--tv-karte-3); }
  .blatt .gefahr, .blatt .gefahr i { color: var(--tv-gefahr); }
</style>

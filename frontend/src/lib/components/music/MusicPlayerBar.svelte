<!--
  Abspielleiste der Musik (Gestaltung nach mockups/musik.html). Steht unten
  über allen Seiten, solange etwas in der Warteschlange ist; steuert nur den
  Musikspieler (lib/stores/musicPlayer.svelte.js). Das Minus blendet den Titel
  überall in der Musik aus (utils/musicHiding.js), der Papierkorb löscht ein Video.
-->
<script>
  import { coverUrl, downloadUrl, isFile } from '../../utils/musicTrack.js';
  import { hideTrack } from '../../utils/musicHiding.js';
  import { navigate } from '../../router/router.js';
  import { toast } from '../../stores/notifications.js';
  import { musicPlayer as player } from '../../stores/musicPlayer.svelte.js';
  import { formatDuration } from '../../utils/format.js';
  import { audioQuality } from '../../utils/audioTech.js';
  import { dragValue, playerBarHeight } from '../../utils/playerBar.js';
  import { remote } from '../../stores/remote.svelte.js';
  import DeviceButton from '../remote/DeviceButton.svelte';
  import ArtistLink from './ArtistLink.svelte';
  import { playerBar } from '../../stores/playerBar.svelte.js';

  let track = $derived(player.current);
  let progress = $derived(player.duration ? player.time / player.duration : 0);
  const REPEAT_TITLES = { off: 'Wiederholen aus', all: 'Alle wiederholen', one: 'Diesen Titel wiederholen' };

  // "OPUS · 160 kbit/s · 48 kHz" oder "FLAC · 16 Bit · 44,1 kHz" - was die Datei hergibt
  let quality = $derived(audioQuality(player.audioInfo));

  async function hide() {
    try { await hideTrack(track); } catch (e) { toast.error(e.message); }
  }

  async function favorite() {
    try {
      const on = await player.toggleFavorite();
      toast.success(on ? 'Zu den Lieblingssongs' : 'Aus den Lieblingssongs entfernt');
    } catch (e) { toast.error(e.message); }
  }
</script>

<!-- Eingeklappt steht die Steuerung schlank in der Fußleiste (CompactPlayer) -->
{#if track && !playerBar.compact}
  <div class="spieler" use:playerBarHeight>
    <div class="links">
      <button class="cover" onclick={() => navigate('/music', { tab: 'jetzt' })} title="Läuft gerade">
        <img src={coverUrl(track)} alt="" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
      </button>
      <div class="text">
        <div class="t" title={track.title}>{track.title}</div>
        <div class="tv-leise tv-klein w"><ArtistLink {track} />{#if player.title}{' · '}{player.title}{/if}</div>
      </div>
      <button class="taste" class:an={track.favorite} onclick={favorite} title="Lieblingssong">
        <i class="fa-{track.favorite ? 'solid' : 'regular'} fa-heart"></i></button>
      <!-- Hörbücher haben ihre Teile fest: dort kein Ausblenden -->
      {#if !player.audiobook}
        <button class="taste weg" onclick={hide} title="Überall in der Musik ausblenden und weiter (nichts wird gelöscht)">
          <i class="fa-solid fa-circle-minus"></i></button>
      {/if}
      {#if !isFile(track)}
        <button class="taste weg" onclick={() => player.deleteTrack()}
                title="Gefällt nicht: Video löschen und weiter. Kurz rückgängig zu machen; kommt nie automatisch zurück">
          <i class="fa-solid fa-trash-can"></i></button>
      {/if}
    </div>

    <div class="mitte">
      <div class="tasten">
        <button class="taste" class:an={player.shuffle} onclick={() => player.toggleShuffle()} disabled={!!player.audiobook}
                title={player.audiobook ? 'Hörbücher laufen in ihrer Reihenfolge' : 'Zufällige Reihenfolge'}>
          <i class="fa-solid fa-shuffle"></i></button>
        <button class="taste" onclick={() => player.prev()} title="Zurück"><i class="fa-solid fa-backward-step"></i></button>
        <button class="taste gross" onclick={() => player.toggle()} title={player.playing ? 'Pause' : 'Abspielen'}>
          <i class="fa-solid {player.loading ? 'fa-spinner fa-spin' : player.playing ? 'fa-pause' : 'fa-play'}"></i></button>
        <button class="taste" onclick={() => player.next()} title="Weiter"><i class="fa-solid fa-forward-step"></i></button>
        <button class="taste wiederholen" class:an={player.repeat !== 'off'} onclick={() => player.cycleRepeat()}
                title={REPEAT_TITLES[player.repeat]}>
          <i class="fa-solid fa-repeat"></i>{#if player.repeat === 'one'}<b>1</b>{/if}</button>
      </div>
      <div class="zeitleiste">
        <span class="zahl">{formatDuration(Math.floor(player.time))}</span>
        <div class="spur" use:dragValue={(v) => player.seek(v * player.duration)} role="slider" tabindex="0"
             aria-label="Stelle im Titel" aria-valuemin="0" aria-valuemax={Math.round(player.duration)} aria-valuenow={Math.round(player.time)}>
          <b style:width="{progress * 100}%"></b>
          {#each player.segments.slice(1).filter((segment) => segment.start < player.duration) as segment (segment.start)}
            <i class="marke" style:left="{(segment.start / (player.duration || 1)) * 100}%" title={segment.title}></i>
          {/each}
        </div>
        <span class="zahl">{formatDuration(Math.floor(player.duration))}</span>
      </div>
      <!-- Feste Zeile: Rückgängig nach dem Löschen, sonst die Tonqualität -->
      <div class="info">
        {#if player.pendingDelete}
          <div class="rueckgaengig">
            <i class="fa-solid fa-trash-can"></i>
            <span class="was" title={player.pendingDelete.track.title}>Gelöscht: {player.pendingDelete.track.title}</span>
            <button onclick={() => player.undoDelete()}>Rückgängig</button>
          </div>
        {:else if player.segment}
          <div class="abschnitt-zeile" title={player.segment.title}>
            <span class="zahl">{player.segment.index + 1}/{player.segment.count}</span> {player.segment.title}</div>
        {:else if remote.steering}
          <div class="gesteuert"><i class="fa-solid fa-tower-broadcast"></i> {remote.steering} steuert mit</div>
        {:else if quality}
          <div class="qualitaet zahl" title="Tonspur der Datei">{quality}</div>
        {/if}
      </div>
    </div>

    <div class="rechts">
      <button class="taste" onclick={() => navigate('/music', { tab: 'jetzt', ansicht: 'liedtext' })} title="Liedtext">
        <i class="fa-solid fa-align-left"></i></button>
      <button class="taste" onclick={() => navigate('/music', { tab: 'jetzt' })} title="Warteschlange">
        <i class="fa-solid fa-list-ol"></i></button>
      <a class="taste" href={downloadUrl(track)} download title="Ton herunterladen (wie geladen, ohne Neukodierung)">
        <i class="fa-solid fa-download"></i></a>
      <button class="taste" onclick={() => { player.pause(); navigate(`/watch/${track.id}`); }} title="Als Video ansehen">
        <i class="fa-solid fa-display"></i></button>
      <button class="taste" onclick={() => player.toggleMute()} title={player.muted ? 'Ton an' : 'Stumm'}>
        <i class="fa-solid {player.muted || player.volume === 0 ? 'fa-volume-xmark' : 'fa-volume-high'}"></i></button>
      <div class="lautstaerke" use:dragValue={(v) => player.setVolume(v)} role="slider" tabindex="0" aria-label="Lautstärke"
           aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(player.volume * 100)}>
        <b style:width="{player.volume * 100}%"></b>
      </div>
      <DeviceButton up />
      <button class="taste" onclick={() => playerBar.setCompact(true)} title="Leiste verkleinern: nur die Steuerung, unten in der Fußleiste">
        <i class="fa-solid fa-chevron-down"></i></button>
      <button class="taste" onclick={() => player.stop()} title="Musik beenden"><i class="fa-solid fa-xmark"></i></button>
    </div>
  </div>
{/if}

<style>
  .spieler { flex: none; display: grid; grid-template-columns: minmax(0, 320px) minmax(0, 1fr) minmax(0, 320px);
             align-items: center; gap: var(--tv-a5); height: 108px; padding: 0 var(--tv-a4);
             background: var(--tv-karte); border-top: 1px solid var(--tv-rand-stark); }
  .links { display: flex; align-items: center; gap: var(--tv-a3); min-width: 0; }
  .cover { flex: none; width: 56px; height: 56px; padding: 0; border: 0; border-radius: var(--tv-ecke-klein); overflow: hidden;
           cursor: pointer; background: var(--tv-mulde); }
  .cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .text { min-width: 0; }
  .t { font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .w { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .mitte { display: flex; flex-direction: column; align-items: center; gap: 5px; min-width: 0; }
  .tasten { display: flex; align-items: center; gap: var(--tv-a2); }
  .taste { position: relative; width: 38px; height: 38px; flex: none; display: grid; place-items: center; border: 0; background: none;
           color: var(--tv-text-2); border-radius: var(--tv-ecke); cursor: pointer; font-size: 16px; }
  .taste:hover { color: var(--tv-text); background: var(--tv-karte-2); }
  .taste.an { color: var(--tv-akzent); }
  .taste.gross { width: 46px; height: 46px; background: var(--tv-text); color: var(--tv-grund); font-size: 18px; }
  .taste.gross:hover { background: var(--tv-akzent); color: var(--tv-akzent-text); }
  .taste.weg:hover { color: var(--tv-gefahr); }
  .info { height: 20px; line-height: 20px; max-width: 100%; min-width: 0; }
  .qualitaet { font-size: 13px; color: var(--tv-text-3); letter-spacing: 0.03em; }
  .gesteuert { font-size: var(--tv-gr-klein); color: var(--tv-info); white-space: nowrap; }
  .abschnitt-zeile { font-size: var(--tv-gr-klein); color: var(--tv-text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .abschnitt-zeile .zahl { color: var(--tv-akzent); margin-right: 4px; }
  .spur .marke { position: absolute; top: 3px; width: 2px; height: 9px; margin-left: -1px; background: var(--tv-text-2);
                 border-radius: 1px; pointer-events: none; }
  .rueckgaengig { display: flex; align-items: center; gap: var(--tv-a2); font-size: var(--tv-gr-klein); color: var(--tv-text-2); }
  .rueckgaengig i { color: var(--tv-gefahr); }
  .rueckgaengig .was { min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .rueckgaengig button { flex: none; border: 0; background: none; color: var(--tv-akzent); font: inherit; font-weight: 700;
                         white-space: nowrap; cursor: pointer; }
  .wiederholen b { position: absolute; right: 5px; bottom: 4px; font-size: 13px; font-family: var(--tv-schrift-zahl); }
  .zeitleiste { display: flex; align-items: center; gap: var(--tv-a3); width: 100%; max-width: 620px;
                font-size: var(--tv-gr-klein); color: var(--tv-text-3); }
  .spur, .lautstaerke { position: relative; height: 14px; cursor: pointer; touch-action: none; }
  .spur { flex: 1; }
  .lautstaerke { width: 96px; margin-left: 4px; }
  .spur::before, .lautstaerke::before { content: ''; position: absolute; left: 0; right: 0; top: 5px; height: 5px;
                                        background: var(--tv-karte-3); border-radius: 1px; }
  .spur b, .lautstaerke b { position: absolute; left: 0; top: 5px; height: 5px; border-radius: 1px; background: var(--tv-akzent); }
  .lautstaerke b { background: var(--tv-text-2); }
  .rechts { display: flex; align-items: center; justify-content: flex-end; gap: 2px; min-width: 0; }

  @media (max-width: 900px) {
    .spieler { grid-template-columns: minmax(0, 1fr) auto; height: auto; padding: var(--tv-a2) var(--tv-a3); gap: var(--tv-a2); }
    .zeitleiste, .rechts .lautstaerke { display: none; }
    .rechts { grid-column: 1 / -1; justify-content: space-between; }
  }
</style>

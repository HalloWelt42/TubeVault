<!--
  Hörbuch läuft: Teil X von Y, Cover, Titel und Autor, "von vorn", Spur des
  Teils, Sprünge um 30 Sekunden und von Teil zu Teil, Tempo, Schlaf-
  Zeitgeber und der Stand über das ganze Buch. Nie zufällig; die Stelle
  merkt der Musikspieler beim Server. Gestaltung nach mockups/mobil-musik.html.
-->
<script>
  import { musicPlayer as player } from '../../../lib/stores/musicPlayer.svelte.js';
  import { coverUrl } from '../../../lib/utils/musicTrack.js';
  import { toast } from '../../../lib/stores/notifications.js';
  import { formatDurationLong } from '../../../lib/utils/format.js';
  import { PLAYBACK_RATES, formatRate } from '../../../lib/utils/playbackRate.js';
  import { SLEEP_MINUTES, sleepLabel } from '../../../lib/utils/sleepTimer.js';
  import { bookProgress } from '../../../lib/utils/bookProgress.js';
  import { back, go } from '../../router.js';
  import Spur from '../../parts/Spur.svelte';
  import SpielerKopf from '../../parts/SpielerKopf.svelte';

  const SKIP_S = 30;

  let track = $derived(player.current);
  let part = $derived(player.index + 1);
  let parts = $derived(player.queue.length);
  let total = $derived(bookProgress(player.queue, player.index, player.time, player.rate));
  // extra: ein weiterer Knopf neben Tempo und Schlaf (Snippet), z.B. Geräte
  let { extra = null } = $props();
  let panel = $state(null);        // null | 'tempo' | 'schlaf': Auswahl unter den Knöpfen

  const toggle = (name) => { panel = panel === name ? null : name; };
  const choose = (action) => { action(); panel = null; };
  // Ganze Minuten wie in der Bücherliste; unter einer Minute zählt als eine
  const minutes = (seconds) => formatDurationLong(Math.max(60, Math.round(seconds)));

  function restart() {
    const before = player.restartBook();
    if (before) toast.undo('Das Hörbuch beginnt von vorn', () => player.jump(before.index, before.time));
  }
</script>

<div class="m-spieler">
  <SpielerKopf oben="Hörbuch" name="Teil {part} von {parts}" onclose={back}>
    {#snippet rechts()}
      <button class="m-rund" onclick={() => go('/jetzt', { ansicht: 'schlange' })} aria-label="Teile"><i class="fa-solid fa-list-ol"></i></button>
    {/snippet}
  </SpielerKopf>

  <div class="m-cover-feld">
    <img src={coverUrl(track)} alt="" draggable="false" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
  </div>

  <div class="m-titelzeile">
    <div class="texte"><div class="t">{player.title}</div><div class="w">{track.artist}</div></div>
    <button class="m-rund" onclick={restart} aria-label="Von vorn"><i class="fa-solid fa-rotate-left"></i></button>
  </div>

  <div class="spur"><Spur time={player.time} duration={player.duration} onseek={(s) => player.seek(s)} mitte="Teil {part}" /></div>

  <div class="m-tasten">
    <button class="klein" onclick={() => player.previousTrack()} aria-label="Voriger Teil"><i class="fa-solid fa-backward-step"></i></button>
    <button onclick={() => player.skipBy(-SKIP_S)} aria-label="{SKIP_S} Sekunden zurück">
      <span class="sprung"><i class="fa-solid fa-rotate-left"></i><span class="zahl">{SKIP_S}</span></span></button>
    <button class="mitte" onclick={() => player.toggle()} aria-label={player.playing ? 'Pause' : 'Abspielen'}>
      <i class="fa-solid {player.loading ? 'fa-spinner fa-spin' : player.playing ? 'fa-pause' : 'fa-play'}"></i></button>
    <button onclick={() => player.skipBy(SKIP_S)} aria-label="{SKIP_S} Sekunden vor">
      <span class="sprung"><i class="fa-solid fa-rotate-right"></i><span class="zahl">{SKIP_S}</span></span></button>
    <button class="klein" onclick={() => player.next()} disabled={part >= parts} aria-label="Nächster Teil"><i class="fa-solid fa-forward-step"></i></button>
  </div>

  <div class="optionen">
    <button class:an={player.rate !== 1} aria-expanded={panel === 'tempo'} onclick={() => toggle('tempo')}>
      Tempo <span class="zahl">{formatRate(player.rate)}</span></button>
    <button class:an={!!player.sleep} aria-expanded={panel === 'schlaf'} onclick={() => toggle('schlaf')}>
      <i class="fa-solid fa-moon"></i> {sleepLabel(player.sleep, player.sleepLeft, part)}</button>
    {@render extra?.()}
  </div>
  {#if panel === 'tempo'}
    <div class="wahl" role="group" aria-label="Tempo" style:--spalten={PLAYBACK_RATES.length}>
      {#each PLAYBACK_RATES as rate (rate)}
        <button class="zahl" class:an={rate === player.rate} onclick={() => choose(() => player.setRate(rate))}>{formatRate(rate)}</button>
      {/each}
    </div>
  {:else if panel === 'schlaf'}
    <div class="wahl" role="group" aria-label="Ausschalten nach" style:--spalten="3">
      <button class:an={player.sleep?.kind === 'track'} onclick={() => choose(() => player.sleepAfterTrack())}>
        Ende Teil <span class="zahl">{part}</span></button>
      {#each SLEEP_MINUTES as m (m)}
        <button class:an={player.sleep?.minutes === m} onclick={() => choose(() => player.sleepAfterMinutes(m))}>
          <span class="zahl">{m}</span> Min.</button>
      {/each}
      {#if player.sleep}
        <button onclick={() => choose(() => player.cancelSleep())}>Zeitgeber aus</button>
      {/if}
    </div>
  {/if}

  <div class="gesamt">
    <span class="zahl">{minutes(total.heard)}</span>
    <span class="balken" role="progressbar" aria-label="Stand im ganzen Buch" aria-valuemin="0" aria-valuemax="100"
          aria-valuenow={Math.round(total.fraction * 100)}><b style:width="{total.fraction * 100}%"></b></span>
    <span>noch <span class="zahl">{minutes(total.left)}</span></span>
  </div>
  <p class="hinweis">Immer in der Reihenfolge, nie zufällig. Die Stelle wird gemerkt.</p>
</div>

<style>
  .spur { margin-top: 10px; flex: none; }
  .sprung { display: flex; flex-direction: column; align-items: center; line-height: 1; gap: 3px; }
  .sprung .zahl { font-size: 13px; font-weight: 700; }
  .optionen { display: flex; justify-content: center; gap: 8px; margin-top: 12px; flex: none; }
  .optionen > :global(button), .wahl button { min-height: 44px; padding: 0 14px; border-radius: var(--m-radius); background: var(--tv-karte);
                                   color: var(--m-dim); font-size: 15px; font-weight: 600; white-space: nowrap; }
  .optionen > :global(button[aria-expanded="true"]) { background: var(--tv-karte-3); color: var(--m-text); }
  .optionen > :global(button.an), .wahl button.an { color: var(--m-accent); }
  .optionen :global(i) { margin-right: 4px; }
  .wahl { display: grid; grid-template-columns: repeat(var(--spalten), minmax(0, 1fr)); gap: 6px; margin-top: 8px; padding: 6px;
          background: var(--tv-mulde); border-radius: var(--m-radius); flex: none; }
  .wahl button { min-width: 0; padding: 0 4px; }
  .wahl button.an { background: rgba(var(--tv-akzent-rgb), 0.14); }
  .gesamt { display: flex; align-items: center; gap: 8px; margin-top: 10px; font-size: 14px; color: var(--m-faint); flex: none; }
  .balken { flex: 1; height: 4px; border-radius: 2px; background: var(--tv-mulde); overflow: hidden; }
  .balken b { display: block; height: 100%; background: var(--m-accent); }
  .hinweis { margin-top: auto; padding-top: 8px; text-align: center; font-size: 15px; color: var(--m-faint); flex: none; }
</style>

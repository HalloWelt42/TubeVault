<!--
  Liedtext am Handy: läuft mit, die aktuelle Zeile steht hell in der Mitte;
  Antippen springt dorthin. Die Schrift lässt sich in drei Stufen
  umschalten (im Browser gemerkt). Unten eine schlanke Steuerung.
  Den Text liefert lib/utils/trackLyrics.svelte.js (wie am Rechner).
-->
<script>
  import { untrack } from 'svelte';
  import { musicPlayer as player } from '../../../lib/stores/musicPlayer.svelte.js';
  import { coverUrl, isFile } from '../../../lib/utils/musicTrack.js';
  import { TrackLyrics } from '../../../lib/utils/trackLyrics.svelte.js';
  import { scrollWithin } from '../../../lib/utils/scrollRoot.js';
  import { back } from '../../router.js';
  import Spur from '../../parts/Spur.svelte';

  const SIZES = [19, 23, 28];            // Schriftstufen in px
  const DEFAULT_SIZE = 1;
  const SIZE_KEY = 'musik.liedtext.schrift';
  const HOLD_MS = 4000;                  // so lange folgt die Ansicht nicht, nachdem selbst gerollt wurde

  const lyrics = new TrackLyrics();
  let track = $derived(player.current);
  let active = $derived(lyrics.lineAt(player.time));
  let box = $state(null);
  let size = $state(readSize());
  let heldUntil = 0;

  // Liedtext des laufenden Titels (nur der Titel wird verfolgt)
  $effect(() => {
    const current = track;
    untrack(() => lyrics.load(current));
  });

  // Mitlaufen: die aktuelle Zeile in die Mitte, außer gerade wird selbst gerollt
  $effect(() => {
    const line = active;
    size;
    if (line < 0 || !box || Date.now() < heldUntil) return;
    const el = box.querySelector(`[data-zeile="${line}"]`);
    if (el) scrollWithin(box, el, 'center');
  });

  function readSize() {
    try {
      const saved = localStorage.getItem(SIZE_KEY);
      return saved !== null && SIZES[Number(saved)] ? Number(saved) : DEFAULT_SIZE;
    } catch { return DEFAULT_SIZE; }
  }

  function nextSize() {
    size = (size + 1) % SIZES.length;
    try { localStorage.setItem(SIZE_KEY, String(size)); } catch { /* Speicher gesperrt */ }
  }

  const hold = () => { heldUntil = Date.now() + HOLD_MS; };

  // Selbst gerollt? Dann eine Weile nicht nachführen (passiv, rollt flüssig)
  function ownScroll(node) {
    const options = { passive: true };
    for (const type of ['touchstart', 'wheel']) node.addEventListener(type, hold, options);
    return { destroy: () => { for (const type of ['touchstart', 'wheel']) node.removeEventListener(type, hold, options); } };
  }
  const hasText = $derived(lyrics.synced.length > 0 || !!lyrics.plain);
</script>

<div class="liedtext">
  <header class="kopf">
    <button class="m-rund" onclick={back} aria-label="Schließen"><i class="fa-solid fa-chevron-down"></i></button>
    <img src={coverUrl(track)} alt="" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
    <div class="texte"><div class="t">{track.title}</div><div class="w">{track.artist}</div></div>
    {#if hasText}
      <button class="m-rund" onclick={nextSize} aria-label="Schriftgröße umschalten"><i class="fa-solid fa-text-height"></i></button>
    {:else}<span></span>{/if}
  </header>

  <div class="zeilen" bind:this={box} style:--groesse="{SIZES[size]}px" use:ownScroll>
    {#if lyrics.synced.length}
      {#each lyrics.synced as line, i}
        <button class="zeile" class:jetzt={i === active} class:vorbei={i < active} data-zeile={i}
                onclick={() => player.seek(lyrics.timeOf(i))}>{line.text || '♪'}</button>
      {/each}
    {:else if lyrics.plain}
      <p class="frei">{lyrics.plain}</p>
    {:else if lyrics.loading}
      <div class="m-spin"><i class="fa-solid fa-spinner fa-spin"></i></div>
    {:else}
      <p class="leer">{isFile(track) ? 'Kein Liedtext in der Datei und keine .lrc daneben.'
        : 'Kein Liedtext. Suchen und festlegen lässt er sich am Rechner in der Videoansicht.'}</p>
    {/if}
  </div>
  {#if lyrics.synced.length}<p class="hinweis">Zeile antippen springt dorthin</p>{/if}

  <div class="steuer">
    <Spur schmal time={player.time} duration={player.duration} onseek={(s) => player.seek(s)} />
    <div class="knoepfe">
      <button class="m-rund gross" onclick={() => player.prev()} aria-label="Zurück"><i class="fa-solid fa-backward-step"></i></button>
      <button class="spiel" onclick={() => player.toggle()} aria-label={player.playing ? 'Pause' : 'Abspielen'}>
        <i class="fa-solid {player.loading ? 'fa-spinner fa-spin' : player.playing ? 'fa-pause' : 'fa-play'}"></i></button>
      <button class="m-rund gross" onclick={() => player.next()} aria-label="Weiter"><i class="fa-solid fa-forward-step"></i></button>
    </div>
  </div>
</div>

<style>
  .liedtext { --ton: var(--m-farbton, var(--tv-karte)); --ton-dunkel: color-mix(in srgb, var(--ton) 62%, #000);
              height: 100%; display: flex; flex-direction: column; overflow: hidden;
              background: linear-gradient(180deg, var(--ton), var(--ton-dunkel)); }
  .kopf { display: grid; grid-template-columns: 44px 48px minmax(0, 1fr) 44px; gap: 8px; align-items: center; flex: none;
          height: calc(var(--m-safe-top) + 72px); padding: var(--m-safe-top) calc(var(--m-safe-right) + 12px) 0 calc(var(--m-safe-left) + 12px);
          background: var(--ton); }
  .kopf img { width: 48px; height: 48px; object-fit: cover; border-radius: var(--tv-ecke-klein); background: var(--m-surface); }
  .texte { min-width: 0; }
  .texte .t { font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .texte .w { font-size: 15px; color: var(--m-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .zeilen { flex: 1; min-height: 0; overflow-y: auto; overscroll-behavior: contain;
            padding: 24px calc(var(--m-safe-right) + 24px) 40vh calc(var(--m-safe-left) + 24px); }
  .zeile { display: block; width: 100%; padding: 8px 0; text-align: left; font-size: var(--groesse); font-weight: 600;
           line-height: 1.3; color: rgba(255, 255, 255, 0.38); transition: color 0.2s ease; }
  .zeile.vorbei { color: rgba(255, 255, 255, 0.6); }
  .zeile.jetzt { color: var(--m-text); font-weight: 700; }
  .frei { white-space: pre-wrap; font-size: var(--groesse); font-weight: 600; line-height: 1.45; color: var(--m-dim); }
  .leer { padding-top: 24px; font-size: 17px; color: var(--m-dim); text-align: center; }
  .hinweis { flex: none; padding: 8px 16px; font-size: 14px; color: var(--m-faint); text-align: center; }
  .steuer { flex: none; padding: 0 calc(var(--m-safe-right) + 24px) calc(var(--m-safe-bottom) + 12px) calc(var(--m-safe-left) + 24px);
            background: var(--ton-dunkel); }
  .knoepfe { display: grid; grid-template-columns: 1fr 64px 1fr; align-items: center; justify-items: center; height: 72px; }
  .gross { width: 52px; height: 52px; font-size: 24px; color: var(--m-text); }
  .spiel { width: 64px; height: 64px; border-radius: 50%; background: var(--m-accent); color: var(--m-accent-ink); font-size: 24px; }
</style>

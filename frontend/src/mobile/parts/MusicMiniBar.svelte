<!--
  Kleiner Abspieler über der unteren Leiste der Mobil-Ansicht, oben mit dem
  Stand als Linie. Tippen öffnet "Läuft gerade" (oder, was onopen sagt).
  Derselbe Musikspieler wie am Rechner (lib/stores/musicPlayer.svelte.js),
  samt Sperrbildschirm-Steuerung. Spielt hier nichts, aber auf einem anderen
  Gerät, zeigt und steuert sie jenes (Fernsteuerung, Kennfarbe Blau); Tippen
  öffnet dann die Fernbedienung.
-->
<script>
  import { onDestroy, onMount } from 'svelte';
  import { coverUrl } from '../../lib/utils/musicTrack.js';
  import { musicPlayer as player } from '../../lib/stores/musicPlayer.svelte.js';
  import { remote } from '../../lib/stores/remote.svelte.js';
  import { videoSession } from '../../lib/stores/videoSession.svelte.js';
  import { KIND_ICONS } from '../../lib/utils/remoteDevices.js';
  import { go } from '../router.js';

  let { onopen = () => go('/jetzt') } = $props();

  let now = $state(performance.now());
  let ticker;
  onMount(() => { ticker = setInterval(() => { now = performance.now(); }, 1000); });
  onDestroy(() => clearInterval(ticker));

  let track = $derived(player.current);
  let progress = $derived(player.duration ? Math.min(1, player.time / player.duration) : 0);
  let elsewhere = $derived(!player.playing && !videoSession.playing ? remote.elsewhere : null);
  let farState = $derived(elsewhere?.zustand || null);
  let farProgress = $derived(farState?.dauer ? Math.min(1, remote.positionOf(elsewhere, now) / farState.dauer) : 0);
</script>

{#if farState}
  <div class="mini fern">
    <span class="lauf" style:width="{farProgress * 100}%"></span>
    <button class="info" onclick={() => go('/fern', { id: elsewhere.id })}>
      <img src={coverUrl(farState.kennung)} alt="" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
      <span class="text"><span class="t">{farState.titel}</span>
        <span class="w woanders"><i class="fa-solid {KIND_ICONS[elsewhere.art]}"></i> {elsewhere.name}</span></span>
    </button>
    <button class="taste" onclick={() => remote.send(elsewhere.id, 'umschalten')} aria-label={farState.laeuft ? 'Pause' : 'Abspielen'}>
      <i class="fa-solid {farState.laeuft ? 'fa-pause' : 'fa-play'}"></i></button>
    <button class="taste" disabled={!farState.kann?.includes('weiter')} onclick={() => remote.send(elsewhere.id, 'weiter')} aria-label="Weiter">
      <i class="fa-solid fa-forward-step"></i></button>
  </div>
{:else if track}
  <div class="mini">
    <span class="lauf" style:width="{progress * 100}%"></span>
    <button class="info" onclick={onopen}>
      <img src={coverUrl(track)} alt="" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
      <span class="text"><span class="t">{track.title}</span><span class="w">{track.artist}</span></span>
    </button>
    <button class="taste" onclick={() => player.toggle()} aria-label={player.playing ? 'Pause' : 'Abspielen'}>
      <i class="fa-solid {player.loading ? 'fa-spinner fa-spin' : player.playing ? 'fa-pause' : 'fa-play'}"></i></button>
    <button class="taste" onclick={() => player.next()} aria-label={player.audiobook ? 'Nächster Teil' : 'Weiter'}>
      <i class="fa-solid fa-forward-step"></i></button>
  </div>
{/if}

<style>
  .mini { position: relative; flex: none; display: grid; grid-template-columns: minmax(0, 1fr) 48px 48px; gap: 4px;
          align-items: center; height: 64px; padding: 0 8px 0 12px; background: var(--tv-karte-2); }
  .mini.fern { background: rgba(var(--tv-info-rgb), 0.16); }
  .lauf { position: absolute; left: 0; top: 0; height: 3px; background: var(--m-accent); }
  .fern .lauf { background: var(--tv-info); }
  .info { min-width: 0; height: 100%; display: flex; align-items: center; gap: 12px; text-align: left; }
  img { width: 48px; height: 48px; flex: none; object-fit: cover; border-radius: var(--tv-ecke-klein); background: var(--m-surface); }
  .text { min-width: 0; display: flex; flex-direction: column; }
  .t { font-weight: 600; font-size: 16px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .w { font-size: 14px; color: var(--m-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .woanders { color: var(--tv-info); font-weight: 600; }
  .taste { width: 48px; height: 48px; display: grid; place-items: center; font-size: 20px; }
  .taste:disabled { opacity: 0.35; }
</style>

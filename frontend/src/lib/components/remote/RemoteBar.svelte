<!--
  Leiste unten am Rechner, wenn ein anderes Gerät spielt und hier nichts
  läuft: zeigt, was dort spielt, steuert es und holt es auf Wunsch hierher.
  Gleiche Gestalt wie die Musikleiste (MusicPlayerBar), Kennfarbe Blau für
  "läuft woanders" wie in mockups/fernsteuerung.html.
-->
<script>
  import { onDestroy, onMount } from 'svelte';
  import { remote } from '../../stores/remote.svelte.js';
  import { coverUrl } from '../../utils/musicTrack.js';
  import { formatDuration } from '../../utils/format.js';
  import { KIND_ICONS } from '../../utils/remoteDevices.js';
  import { dragValue, playerBarHeight } from '../../utils/playerBar.js';
  import DeviceButton from './DeviceButton.svelte';

  let { device } = $props();

  let now = $state(performance.now());
  let ticker;
  onMount(() => { ticker = setInterval(() => { now = performance.now(); }, 500); });
  onDestroy(() => clearInterval(ticker));

  let state = $derived(device.zustand);
  let position = $derived(remote.positionOf(device, now));
  let progress = $derived(state.dauer ? position / state.dauer : 0);
  let step = $derived(state.art === 'video' ? 10 : 30);
  let can = $derived(new Set(state.kann || []));

  const send = (aktion, wert = null) => remote.send(device.id, aktion, wert);
</script>

<div class="spieler" use:playerBarHeight>
  <div class="links">
    <img class="cover" class:breit={state.art === 'video'} src={coverUrl(state.kennung)} alt=""
         onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
    <div class="text">
      <div class="t" title={state.titel}>{state.titel}</div>
      <div class="tv-leise tv-klein w">{state.untertitel}{#if state.quelle}{' · '}{state.quelle}{/if}</div>
      <div class="woanders"><i class="fa-solid {KIND_ICONS[device.art]}"></i> Läuft auf {device.name}</div>
    </div>
  </div>

  <div class="mitte">
    <div class="tasten">
      {#if state.zufall !== null && state.zufall !== undefined}
        <button class="taste" class:an={state.zufall} onclick={() => send('zufall')} title="Zufällige Reihenfolge">
          <i class="fa-solid fa-shuffle"></i></button>
      {/if}
      {#if can.has('zurueck')}
        <button class="taste" onclick={() => send('zurueck')} title="Zurück"><i class="fa-solid fa-backward-step"></i></button>
      {/if}
      <button class="taste sprung" onclick={() => send('sprung', -step)} title="{step} Sekunden zurück">
        <i class="fa-solid fa-rotate-left"></i><span class="zahl">{step}</span></button>
      <button class="taste gross" onclick={() => send('umschalten')} title={state.laeuft ? 'Pause' : 'Abspielen'}>
        <i class="fa-solid {state.laeuft ? 'fa-pause' : 'fa-play'}"></i></button>
      <button class="taste sprung" onclick={() => send('sprung', step)} title="{step} Sekunden vor">
        <i class="fa-solid fa-rotate-right"></i><span class="zahl">{step}</span></button>
      {#if can.has('weiter')}
        <button class="taste" onclick={() => send('weiter')} title="Weiter"><i class="fa-solid fa-forward-step"></i></button>
      {/if}
      {#if state.wiederholen}
        <button class="taste" class:an={state.wiederholen !== 'off'} onclick={() => send('wiederholen')} title="Wiederholen">
          <i class="fa-solid fa-repeat"></i></button>
      {/if}
    </div>
    <div class="zeitleiste">
      <span class="zahl">{formatDuration(Math.floor(position))}</span>
      <div class="spur" use:dragValue={(v) => send('stelle', v * state.dauer)} role="slider" tabindex="0"
           aria-label="Stelle" aria-valuemin="0" aria-valuemax={Math.round(state.dauer)} aria-valuenow={Math.round(position)}>
        <b style:width="{progress * 100}%"></b>
      </div>
      <span class="zahl">{formatDuration(Math.floor(state.dauer))}</span>
    </div>
  </div>

  <div class="rechts">
    {#if state.tonspuren?.length}
      <div class="tonspur" role="group" aria-label="Tonspur">
        <button class:an={!state.tonspur} onclick={() => send('tonspur', null)}>Original</button>
        {#each state.tonspuren as track (track.id)}
          <button class:an={state.tonspur === track.id} onclick={() => send('tonspur', track.id)}>{track.label}</button>
        {/each}
      </div>
    {/if}
    {#if state.lautstaerke !== null && state.lautstaerke !== undefined}
      <i class="fa-solid fa-volume-high tv-leise" title="Lautstärke dort"></i>
      <div class="lautstaerke" use:dragValue={(v) => send('lautstaerke', v)} role="slider" tabindex="0"
           aria-label="Lautstärke dort" aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(state.lautstaerke * 100)}>
        <b style:width="{state.lautstaerke * 100}%"></b>
      </div>
    {/if}
    <button class="holen" onclick={() => remote.fetch(device.id)} title="Wiedergabe hierher holen, an derselben Stelle">
      <i class="fa-solid fa-arrow-down"></i> Holen</button>
    <DeviceButton up />
  </div>
</div>

<style>
  .spieler { flex: none; display: grid; grid-template-columns: minmax(0, 340px) minmax(0, 1fr) minmax(0, 360px);
             align-items: center; gap: var(--tv-a5); min-height: 108px; padding: var(--tv-a2) var(--tv-a4);
             background: var(--tv-karte); }
  .links { display: flex; align-items: center; gap: var(--tv-a3); min-width: 0; }
  .cover { flex: none; width: 56px; height: 56px; object-fit: cover; border-radius: var(--tv-ecke-klein); background: var(--tv-mulde); }
  .cover.breit { width: 96px; }
  .text { min-width: 0; }
  .t { font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .w { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .woanders { font-size: var(--tv-gr-klein); color: var(--tv-info); font-weight: 600; white-space: nowrap; }
  .mitte { display: flex; flex-direction: column; align-items: center; gap: 6px; min-width: 0; }
  .tasten { display: flex; align-items: center; gap: var(--tv-a2); }
  .taste { position: relative; width: 40px; height: 40px; display: grid; place-items: center; border: 0; background: none;
           color: var(--tv-text-2); border-radius: var(--tv-ecke); cursor: pointer; font-size: 16px; }
  .taste:hover { color: var(--tv-text); background: var(--tv-karte-2); }
  .taste.an { color: var(--tv-akzent); }
  .taste.gross { width: 46px; height: 46px; border-radius: 50%; background: var(--tv-info); color: #0b1a22; font-size: 18px; }
  .taste.sprung { grid-template-rows: auto auto; gap: 0; }
  .taste.sprung span { font-size: 13px; line-height: 1; }
  .zeitleiste { display: flex; align-items: center; gap: var(--tv-a3); width: 100%; max-width: 620px;
                font-size: var(--tv-gr-klein); color: var(--tv-text-3); }
  .spur, .lautstaerke { position: relative; height: 14px; cursor: pointer; touch-action: none; }
  .spur { flex: 1; }
  .lautstaerke { width: 90px; }
  .spur::before, .lautstaerke::before { content: ''; position: absolute; left: 0; right: 0; top: 5px; height: 5px;
                                        background: var(--tv-karte-3); border-radius: 1px; }
  .spur b, .lautstaerke b { position: absolute; left: 0; top: 5px; height: 5px; border-radius: 1px; background: var(--tv-info); }
  .rechts { display: flex; align-items: center; justify-content: flex-end; gap: var(--tv-a2); min-width: 0; flex-wrap: wrap; }
  .tonspur { display: inline-flex; padding: 2px; border-radius: var(--tv-ecke); background: var(--tv-mulde); }
  .tonspur button { height: 32px; padding: 0 10px; border: 0; border-radius: var(--tv-ecke-klein); background: none;
                    color: var(--tv-text-2); font: inherit; font-size: var(--tv-gr-klein); font-weight: 600; cursor: pointer; }
  .tonspur button.an { background: var(--tv-karte-3); color: var(--tv-info); }
  .holen { height: 40px; padding: 0 var(--tv-a3); border: 0; border-radius: var(--tv-ecke); background: var(--tv-info);
           color: #0b1a22; font: inherit; font-weight: 700; cursor: pointer; white-space: nowrap; }

  @media (max-width: 900px) {
    .spieler { grid-template-columns: minmax(0, 1fr) auto; gap: var(--tv-a2); padding: var(--tv-a2) var(--tv-a3); }
    .zeitleiste, .lautstaerke, .rechts .tv-leise { display: none; }
    .rechts { grid-column: 1 / -1; justify-content: space-between; }
  }
</style>

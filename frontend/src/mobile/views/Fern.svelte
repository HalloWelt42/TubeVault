<!--
  Fernbedienung am Handy: steuert, was auf einem anderen Gerät läuft (Musik,
  Hörbuch oder Video), und holt es auf Wunsch hierher. Gestaltung nach
  mockups/fernsteuerung.html; Kennfarbe Blau für "läuft woanders".
-->
<script>
  import { onDestroy, onMount } from 'svelte';
  import { remote } from '../../lib/stores/remote.svelte.js';
  import { coverUrl } from '../../lib/utils/musicTrack.js';
  import { formatDuration } from '../../lib/utils/format.js';
  import { KIND_ICONS } from '../../lib/utils/remoteDevices.js';
  import { dragValue } from '../../lib/utils/playerBar.js';
  import { api } from '../../lib/api/client.js';
  import { back } from '../router.js';

  let { id = null } = $props();

  let now = $state(performance.now());
  let ticker;
  onMount(() => { ticker = setInterval(() => { now = performance.now(); }, 500); });
  onDestroy(() => clearInterval(ticker));

  // Das gewählte Gerät; ist es weg, das, was sonst gerade woanders spielt
  let device = $derived(remote.devices.find((d) => d.id === id && d.zustand) || remote.elsewhere);
  let state = $derived(device?.zustand || null);
  let position = $derived(device ? remote.positionOf(device, now) : 0);
  let progress = $derived(state?.dauer ? position / state.dauer : 0);
  let video = $derived(state?.art === 'video');
  let book = $derived(state?.art === 'hoerbuch');
  let can = $derived(new Set(state?.kann || []));
  let trackLabel = $derived(state?.tonspuren?.find((t) => t.id === state.tonspur)?.label || null);

  const send = (aktion, wert = null) => remote.send(device.id, aktion, wert);
</script>

<div class="fern m-view">
  {#if !device || !state}
    <header class="band">
      <button class="zurueck" onclick={back} aria-label="Schließen"><i class="fa-solid fa-chevron-down"></i></button>
      <div class="text"><div class="t">Fernbedienung</div></div>
    </header>
    <div class="m-note"><p>Auf keinem anderen Gerät läuft gerade etwas.</p>
      <button class="m-btn" onclick={back}><i class="fa-solid fa-chevron-left"></i> Zurück</button></div>
  {:else}
    <header class="band">
      <button class="zurueck" onclick={back} aria-label="Schließen"><i class="fa-solid fa-chevron-down"></i></button>
      <i class="fa-solid {KIND_ICONS[device.art]} art"></i>
      <div class="text">
        <div class="t">Läuft auf {device.name}</div>
        <div class="w">{video ? (trackLabel ? `Video · ${trackLabel}` : 'Video') : 'Du steuerst von hier'}</div>
      </div>
      <button class="holen" onclick={() => remote.fetch(device.id)}><i class="fa-solid fa-mobile-screen"></i> Holen</button>
    </header>

    <div class="koerper">
      {#if video}
        <div class="vbild">
          <img src={api.thumbnailUrl(state.kennung)} alt="" />
          <span class="auf"><i class="fa-solid {KIND_ICONS[device.art]}"></i> Bild läuft auf {device.name}</span>
        </div>
        <h1 class="vtitel">{state.titel}</h1>
        {#if state.untertitel}<div class="leise">{state.untertitel}</div>{/if}
      {:else}
        <img class="cover" src={coverUrl(state.kennung)} alt="" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
        <div class="titelzeile">
          <div class="text">
            <h1 class="titel">{state.titel}</h1>
            <div class="leise">{state.untertitel}{#if state.quelle}{' · '}{state.quelle}{/if}</div>
          </div>
          {#if state.liebling !== null && state.liebling !== undefined}
            <button class="herz" class:an={state.liebling} onclick={() => send('liebling')} aria-label="Lieblingssong">
              <i class="fa-{state.liebling ? 'solid' : 'regular'} fa-heart"></i></button>
          {/if}
        </div>
      {/if}

      <div>
        <div class="spur" use:dragValue={(v) => send('stelle', v * state.dauer)} role="slider" tabindex="0"
             aria-label="Stelle" aria-valuemin="0" aria-valuemax={Math.round(state.dauer)} aria-valuenow={Math.round(position)}>
          <b style:width="{progress * 100}%"></b>
        </div>
        <div class="zeiten"><span>{formatDuration(Math.floor(position))}</span><span>{formatDuration(Math.floor(state.dauer))}</span></div>
      </div>

      <div class="tasten">
        {#if video || book}
          <button class="klein" disabled={!can.has('zurueck')} onclick={() => send('zurueck')} aria-label="Zurück">
            <i class="fa-solid fa-backward-step"></i></button>
          <button onclick={() => send('sprung', video ? -10 : -30)} aria-label="Zurückspringen">
            <i class="fa-solid fa-rotate-left"></i><span class="sek">{video ? 10 : 30}</span></button>
        {:else}
          <button class="klein" class:an={state.zufall} onclick={() => send('zufall')} aria-label="Zufall">
            <i class="fa-solid fa-shuffle"></i></button>
          <button onclick={() => send('zurueck')} aria-label="Zurück"><i class="fa-solid fa-backward-step"></i></button>
        {/if}
        <button class="mitte" onclick={() => send('umschalten')} aria-label={state.laeuft ? 'Pause' : 'Abspielen'}>
          <i class="fa-solid {state.laeuft ? 'fa-pause' : 'fa-play'}"></i></button>
        {#if video || book}
          <button onclick={() => send('sprung', video ? 10 : 30)} aria-label="Vorspringen">
            <i class="fa-solid fa-rotate-right"></i><span class="sek">{video ? 10 : 30}</span></button>
          <button class="klein" disabled={!can.has('weiter')} onclick={() => send('weiter')} aria-label="Weiter">
            <i class="fa-solid fa-forward-step"></i></button>
        {:else}
          <button disabled={!can.has('weiter')} onclick={() => send('weiter')} aria-label="Weiter"><i class="fa-solid fa-forward-step"></i></button>
          <button class="klein" class:an={state.wiederholen && state.wiederholen !== 'off'} onclick={() => send('wiederholen')} aria-label="Wiederholen">
            <i class="fa-solid fa-repeat"></i></button>
        {/if}
      </div>

      {#if state.tonspuren?.length}
        <div class="wahl" role="group" aria-label="Tonspur">
          <button class:an={!state.tonspur} onclick={() => send('tonspur', null)}>Original</button>
          {#each state.tonspuren as track (track.id)}
            <button class:an={state.tonspur === track.id} onclick={() => send('tonspur', track.id)}>{track.label}</button>
          {/each}
        </div>
      {/if}

      {#if state.lautstaerke !== null && state.lautstaerke !== undefined}
        <div class="laut">
          <i class="fa-solid fa-volume-low"></i>
          <div class="spur" use:dragValue={(v) => send('lautstaerke', v)} role="slider" tabindex="0" aria-label="Lautstärke dort"
               aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(state.lautstaerke * 100)}>
            <b style:width="{state.lautstaerke * 100}%"></b>
          </div>
          <i class="fa-solid fa-volume-high"></i>
        </div>
        <div class="leise mitte-text">Lautstärke auf {device.name}</div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .fern { display: flex; flex-direction: column; }
  .band { display: grid; grid-template-columns: var(--m-touch) auto minmax(0, 1fr) auto; gap: 8px; align-items: center;
          padding: calc(var(--m-safe-top) + 8px) 12px 10px 4px; background: rgba(var(--tv-info-rgb), 0.16); color: var(--tv-info); }
  .zurueck { width: var(--m-touch); height: var(--m-touch); font-size: 1.2rem; color: var(--m-dim); }
  .art { font-size: 1.3rem; }
  .text { min-width: 0; }
  .t { font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .w { font-size: var(--tv-gr-klein); color: var(--m-dim); }
  .holen { height: 44px; padding: 0 14px; border-radius: var(--m-radius); background: var(--tv-info); color: #0b1a22; font-weight: 700; }
  .koerper { flex: 1; display: flex; flex-direction: column; gap: 14px; padding: 16px 20px calc(var(--m-safe-bottom) + 20px); }
  .cover { width: 100%; max-width: 420px; aspect-ratio: 1; object-fit: cover; border-radius: var(--m-radius); align-self: center; background: var(--m-surface); }
  .vbild { position: relative; aspect-ratio: 16 / 9; border-radius: var(--m-radius); overflow: hidden; background: #000; }
  .vbild img { width: 100%; height: 100%; object-fit: cover; display: block; opacity: 0.55; }
  .auf { position: absolute; inset: 0; display: grid; place-items: center; font-weight: 700; color: #fff; text-align: center; }
  .vtitel { font-size: 1.05rem; font-weight: 700; line-height: 1.25; }
  .titelzeile { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 8px; }
  .titel { font-size: 1.2rem; font-weight: 700; line-height: 1.2; }
  .leise { color: var(--m-dim); font-size: var(--tv-gr-klein); }
  .herz { width: var(--m-touch); height: var(--m-touch); font-size: 1.3rem; color: var(--m-dim); }
  .herz.an { color: #EF5350; }
  .spur { position: relative; height: 26px; touch-action: none; }
  .spur::before { content: ''; position: absolute; left: 0; right: 0; top: 11px; height: 4px; background: var(--m-line); border-radius: 2px; }
  .spur b { position: absolute; left: 0; top: 11px; height: 4px; background: var(--tv-info); border-radius: 2px; }
  .zeiten { display: flex; justify-content: space-between; font-family: var(--tv-schrift-zahl); font-size: var(--tv-gr-klein); color: var(--m-dim); }
  .tasten { display: grid; grid-template-columns: 1fr 1fr 84px 1fr 1fr; align-items: center; justify-items: center; }
  .tasten button { position: relative; width: 56px; height: 56px; display: grid; place-items: center; font-size: 1.35rem; color: var(--m-text); }
  .tasten button.klein { color: var(--m-dim); font-size: 1.1rem; }
  .tasten button.an { color: var(--m-accent); }
  .tasten button:disabled { opacity: 0.35; }
  .tasten button.mitte { width: 76px; height: 76px; border-radius: 50%; background: var(--tv-info); color: #0b1a22; font-size: 1.7rem; }
  .sek { font-family: var(--tv-schrift-zahl); font-size: 13px; font-weight: 700; line-height: 1; }
  .wahl { display: grid; grid-auto-flow: column; grid-auto-columns: 1fr; padding: 3px; border-radius: var(--m-radius); background: var(--m-surface); }
  .wahl button { height: 44px; border-radius: var(--tv-ecke-klein); color: var(--m-dim); font-weight: 600; }
  .wahl button.an { background: var(--tv-karte-3); color: var(--tv-info); }
  .laut { display: grid; grid-template-columns: 24px 1fr 24px; gap: 10px; align-items: center; color: var(--m-faint); }
  .mitte-text { text-align: center; }
</style>

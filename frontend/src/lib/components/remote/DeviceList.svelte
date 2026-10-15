<!--
  Geräte, auf denen TubeVault gerade offen ist: wer spielt was, und je Gerät
  Holen (Wiedergabe hierher), Dorthin (eigene Wiedergabe abgeben) und, wo
  die Ansicht es anbietet, Steuern. Genutzt am Rechner im Geräte-Knopf und
  am Handy im Blatt "Abspielen auf". Gestaltung nach mockups/fernsteuerung.html.
-->
<script>
  import { onDestroy, onMount } from 'svelte';
  import { remote } from '../../stores/remote.svelte.js';
  import { musicPlayer } from '../../stores/musicPlayer.svelte.js';
  import { videoSession } from '../../stores/videoSession.svelte.js';
  import { KIND_ICONS } from '../../utils/remoteDevices.js';
  import { formatDuration } from '../../utils/format.js';

  /** onControl(device): Fernbedienung öffnen (nur wo es eine gibt); onDone: nach einer Aktion */
  let { onControl = null, onDone = () => {} } = $props();

  let now = $state(performance.now());
  let renaming = $state(false);
  let draft = $state('');
  let ticker;
  onMount(() => { ticker = setInterval(() => { now = performance.now(); }, 1000); });
  onDestroy(() => clearInterval(ticker));

  let devices = $derived(remote.visible);
  let others = $derived(devices.filter((d) => d.id !== remote.me?.id));

  function localLine() {
    const media = remote.localMedia;
    if (media === 'video' && videoSession.video) return `${videoSession.playing ? 'spielt' : 'pausiert'}: ${videoSession.video.title}`;
    if (media === 'musik' && musicPlayer.current) return `${musicPlayer.playing ? 'spielt' : 'pausiert'}: ${musicPlayer.current.title}`;
    return 'bereit';
  }

  function line(device) {
    const state = device.zustand;
    if (!state) return 'bereit';
    return `${state.laeuft ? 'spielt' : 'pausiert'}: ${state.titel} · ${formatDuration(Math.floor(remote.positionOf(device, now)))}`;
  }

  function startRename() {
    draft = remote.me?.name || '';
    renaming = true;
  }

  function saveName() {
    remote.rename(draft);
    renaming = false;
  }

  function act(run) {
    run();
    onDone();
  }
</script>

<div class="geraete">
  <div class="kopf">
    <div class="titel">Abspielen auf</div>
    <div class="tv-leise tv-klein">Wechseln nimmt Stelle und Warteschlange mit, das andere Gerät hält an.</div>
  </div>

  {#if remote.me}
    <div class="geraet hier">
      <i class="fa-solid {KIND_ICONS[remote.me.art]} gross"></i>
      <div class="text">
        {#if renaming}
          <!-- svelte-ignore a11y_autofocus -->
          <input class="name-feld" bind:value={draft} maxlength="40" autofocus aria-label="Name dieses Geräts"
                 onfocus={(e) => e.currentTarget.select()}
                 onkeydown={(e) => { if (e.key === 'Enter') saveName(); if (e.key === 'Escape') renaming = false; }}
                 onblur={saveName} />
        {:else}
          <div class="name">{remote.me.name} <span class="tv-leise">(dieses Gerät)</span></div>
        {/if}
        <div class="zeile">{localLine()}</div>
      </div>
      {#if !renaming}
        <button class="symbol" onclick={startRename} title="Namen dieses Geräts ändern" aria-label="Umbenennen">
          <i class="fa-solid fa-pen"></i></button>
      {/if}
    </div>
  {/if}

  {#each others as device (device.id)}
    <div class="geraet" class:spielt={device.zustand?.laeuft}>
      <i class="fa-solid {KIND_ICONS[device.art]} gross"></i>
      <div class="text">
        <div class="name">{device.name}</div>
        <div class="zeile">
          {#if device.zustand?.laeuft}<i class="fa-solid fa-volume-high welle"></i>{/if}
          {line(device)}
        </div>
      </div>
      <div class="aktionen">
        {#if device.zustand}
          {#if onControl}
            <button class="knopf" onclick={() => act(() => onControl(device))} title="Von hier aus steuern">Steuern</button>
          {/if}
          <button class="knopf haupt" onclick={() => act(() => remote.fetch(device.id))}
                  title="Wiedergabe hierher holen, an derselben Stelle">Holen</button>
        {:else if remote.localMedia}
          <button class="knopf" onclick={() => act(() => remote.handTo(device.id))}
                  title="Eigene Wiedergabe dorthin schicken, hier hält sie an">Dorthin</button>
        {/if}
      </div>
    </div>
  {/each}

  {#if !remote.connected}
    <div class="hinweis"><i class="fa-solid fa-plug-circle-xmark"></i> Keine Verbindung zum Server, ein neuer Versuch läuft.</div>
  {:else if !others.length}
    <div class="hinweis"><i class="fa-solid fa-circle-info"></i> Kein anderes Gerät offen. Sobald TubeVault auf dem Handy oder einem anderen Rechner offen ist, steht es hier.</div>
  {/if}
</div>

<style>
  .geraete { display: flex; flex-direction: column; gap: 4px; }
  .kopf { padding: 0 var(--tv-a2) var(--tv-a2); }
  .titel { font-weight: 700; font-size: 18px; margin-bottom: 2px; }
  .geraet { display: grid; grid-template-columns: 40px minmax(0, 1fr) auto; gap: var(--tv-a3); align-items: center;
            padding: var(--tv-a2) var(--tv-a2); border-radius: var(--tv-ecke); }
  .geraet.hier { background: rgba(var(--tv-akzent-rgb), 0.08); }
  .gross { font-size: 22px; text-align: center; color: var(--tv-text-2); }
  .hier .gross { color: var(--tv-akzent); }
  .spielt .gross, .welle { color: var(--tv-info); }
  .text { min-width: 0; }
  .name { font-weight: 700; font-size: 17px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .zeile { font-size: var(--tv-gr-klein); color: var(--tv-text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .aktionen { display: flex; gap: var(--tv-a2); }
  .knopf { height: 38px; padding: 0 var(--tv-a3); border: 0; border-radius: var(--tv-ecke); background: var(--tv-karte-3);
           color: var(--tv-text); font: inherit; font-weight: 600; font-size: var(--tv-gr-klein); cursor: pointer; white-space: nowrap; }
  .knopf:hover { filter: brightness(1.15); }
  .knopf.haupt { background: var(--tv-akzent); color: var(--tv-akzent-text); }
  .symbol { width: 38px; height: 38px; border: 0; border-radius: var(--tv-ecke); background: none; color: var(--tv-text-3); cursor: pointer; }
  .symbol:hover { color: var(--tv-text); background: var(--tv-karte-2); }
  .name-feld { width: 100%; height: 34px; padding: 0 8px; border: 0; border-radius: var(--tv-ecke-klein); background: var(--tv-mulde);
               color: var(--tv-text); font: inherit; font-size: 17px; outline: 1px solid rgba(var(--tv-akzent-rgb), 0.5); }
  .hinweis { display: flex; gap: var(--tv-a2); align-items: baseline; margin-top: var(--tv-a2); padding: var(--tv-a3);
             border-radius: var(--tv-ecke); background: rgba(var(--tv-info-rgb), 0.1); color: var(--tv-text-2); font-size: var(--tv-gr-klein); }
  .hinweis i { color: var(--tv-info); }
</style>

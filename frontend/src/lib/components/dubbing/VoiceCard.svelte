<!--
  TubeVault - Karte Stimmen (Entwurf mockups/nachvertonung.html)
  Die Stimmen, die der Nachvertoner gemeldet hat. Hörprobe: ein Stück aus
  der jüngsten fertigen Tonspur mit dieser Stimme - ohne fertige Tonspur
  gibt es keine. Der Stern setzt die Vorauswahl beim Vormerken.
-->
<script>
  import { onDestroy } from 'svelte';
  import { api } from '../../api/client.js';

  let { choice, onChoose } = $props();

  // So lange spielt eine Hörprobe
  const SAMPLE_SECONDS = 12;

  let playing = $state(null);      // Name der Stimme, deren Hörprobe gerade läuft
  let player = null;

  function stop() {
    player?.pause();
    player = null;
    playing = null;
  }

  function listen(voice) {
    if (playing === voice.name) return stop();
    stop();
    const { video_id, track_id, start } = voice.sample;
    // Zeitangabe in der Adresse: der Browser spielt genau dieses Stück
    const audio = new Audio(`${api.audioTrackUrl(video_id, track_id)}#t=${start},${start + SAMPLE_SECONDS}`);
    audio.addEventListener('pause', () => { if (player === audio) stop(); });
    audio.addEventListener('ended', () => { if (player === audio) stop(); });
    player = audio;
    playing = voice.name;
    audio.play().catch(() => { if (player === audio) stop(); });
  }

  onDestroy(stop);
</script>

<div class="karte">
  <h3 class="tv-etikett">Stimmen</h3>
  {#if !choice?.details?.length}
    <div class="tv-schwach tv-klein">Noch keine Stimmen gemeldet. Sie erscheinen, sobald der Nachvertoner läuft.</div>
  {:else}
    {#each choice.details as voice (voice.name)}
      {@const chosen = voice.name === choice.default}
      <div class="stimme" class:gewaehlt={chosen}>
        {#if voice.sample}
          <button class="probe" class:an={playing === voice.name} onclick={() => listen(voice)}
                  title={playing === voice.name ? 'Hörprobe anhalten' : 'Hörprobe aus der jüngsten Vertonung mit dieser Stimme'}>
            <i class="fa-solid {playing === voice.name ? 'fa-stop' : 'fa-play'}"></i></button>
        {:else}<span></span>{/if}
        <div class="name">
          <div class="text">{voice.name}</div>
          <div class="nutzung">
            {#if voice.dubs}<span class="zahl">{voice.dubs}</span> {voice.dubs === 1 ? 'Vertonung' : 'Vertonungen'}{:else}noch keine Vertonung{/if}
          </div>
        </div>
        {#if chosen}
          <span class="stern" title="Vorauswahl beim Vormerken"><i class="fa-solid fa-star"></i></span>
        {:else}
          <button class="stern-knopf" onclick={() => onChoose(voice.name)} title="Als Vorauswahl beim Vormerken">
            <i class="fa-regular fa-star"></i></button>
        {/if}
      </div>
    {/each}
  {/if}
</div>

<style>
  .karte { background: var(--tv-karte); border-radius: var(--tv-ecke); padding: var(--tv-a4); margin-bottom: var(--tv-a3); }
  h3 { margin: 0 0 var(--tv-a3); }
  .stimme { display: grid; grid-template-columns: 34px minmax(0, 1fr) 34px; gap: var(--tv-a2); align-items: center;
            padding: 6px 4px; border-radius: var(--tv-ecke-klein); }
  .stimme:hover { background: var(--tv-flaeche); }
  .stimme.gewaehlt { background: rgba(var(--tv-akzent-rgb), 0.08); }
  button { width: 34px; height: 34px; border: 0; border-radius: var(--tv-ecke-klein); cursor: pointer; }
  .probe { background: var(--tv-karte-2); color: var(--tv-text-2); }
  .probe:hover, .probe.an { background: var(--tv-karte-3); color: var(--tv-akzent); }
  .name { min-width: 0; }
  .text { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .nutzung { font-size: var(--tv-gr-marke); color: var(--tv-text-3); }
  .stern { width: 34px; text-align: center; color: var(--tv-akzent); }
  .stern-knopf { background: none; color: var(--tv-text-3); }
  .stern-knopf:hover { background: var(--tv-karte-2); color: var(--tv-akzent); }
</style>

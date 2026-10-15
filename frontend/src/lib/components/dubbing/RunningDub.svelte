<!--
  TubeVault - Laufende Nachvertonung als Karte (Entwurf mockups/nachvertonung.html)
  Bild, Titel, Kanal, Dauer, Sprachen und Stimme; die fünf Schritte als
  Balken, der laufende mit Prozent; was der Nachvertoner gerade meldet,
  seit wann es läuft, die geschätzte Restzeit des Schritts und Abbrechen
  mit eigener Bestätigung. Die Schritte leitet der Dienst ab.
-->
<script>
  import { api } from '../../api/client.js';
  import { formatDuration } from '../../utils/format.js';
  import { about, direction, secondsSince, since } from '../../utils/dubbingText.js';
  import InlineConfirm from './InlineConfirm.svelte';

  let { job, onCancel, onOpen } = $props();

  let asking = $state(false);
  let request = $derived(job.request);
  let lang = $derived(direction(request));
  let current = $derived(job.steps.find((s) => s.state === 'current'));
  let running = $derived(secondsSince(request.claimed_at));

  const width = (step) => (step.state === 'done' ? 100 : step.state === 'current' ? step.percent : 0);
</script>

<article class="laeuft">
  <button class="bild" onclick={() => onOpen(request)} title="Video öffnen">
    <img src={api.thumbnailUrl(request.video_id)} alt="" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
  </button>
  <div class="inhalt">
    <button class="titel" onclick={() => onOpen(request)} title="Video öffnen">{request.title || request.video_id}</button>
    <div class="meta">
      {#if request.channel_name}<span>{request.channel_name}</span>{/if}
      {#if request.duration}<span class="zahl">{formatDuration(request.duration)}</span>{/if}
      <span class="sprachen">
        {#if lang.revoice}{lang.target}, neu gesprochen
        {:else if lang.source}{lang.source} <i class="fa-solid fa-arrow-right"></i> {lang.target}
        {:else}nach {lang.target}{/if}
      </span>
      {#if request.voice}<span>Stimme {request.voice}</span>{/if}
    </div>

    <div class="schritte">
      {#each job.steps as step (step.key)}
        <div class="schritt {step.state}">
          <span>{step.label}{#if step.state === 'current'}{' '}<span class="zahl">{step.percent} %</span>{/if}</span>
          <div class="balken"><b style:width="{width(step)}%"></b></div>
        </div>
      {/each}
    </div>

    {#if job.activity}<div class="taetigkeit" title="Letzte Meldung des Nachvertoners">{job.activity}</div>{/if}

    <div class="fuss">
      <span>{running < 60 ? 'gerade gestartet' : `läuft ${since(running)}`}</span>
      {#if current && job.step_remaining_seconds !== null && job.step_remaining_seconds !== undefined}
        <span title="Geschätzt aus dem bisherigen Tempo dieses Schritts">{current.label} fertig in <span class="zahl">{about(job.step_remaining_seconds)}</span></span>
      {/if}
      {#if !asking}
        <button class="tv-knopf klein ohne gefahr" onclick={() => asking = true} title="Vertonung abbrechen">Abbrechen</button>
      {/if}
    </div>

    {#if asking}
      <InlineConfirm text="Vertonung abbrechen? Die bisherige Arbeit geht verloren." confirmLabel="Abbrechen"
                     cancelLabel="Weiter vertonen" onConfirm={() => { asking = false; onCancel(request); }}
                     onCancel={() => asking = false} />
    {/if}
  </div>
</article>

<style>
  .laeuft {
    display: grid; grid-template-columns: 240px minmax(0, 1fr); gap: var(--tv-a4); padding: var(--tv-a4);
    background: var(--tv-karte); border-radius: var(--tv-ecke); margin-bottom: var(--tv-a4);
    outline: 1px solid rgba(var(--tv-akzent-rgb), 0.45); outline-offset: -1px;
  }
  .bild { padding: 0; border: 0; background: var(--tv-mulde); border-radius: var(--tv-ecke-klein); overflow: hidden;
          aspect-ratio: 16 / 9; cursor: pointer; align-self: start; }
  .bild img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .inhalt { min-width: 0; }
  .titel { display: block; max-width: 100%; padding: 0; border: 0; background: none; color: var(--tv-text); font: inherit;
           font-weight: 700; font-size: 18px; text-align: left; cursor: pointer;
           overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .titel:hover { color: var(--tv-akzent); }
  .meta { display: flex; flex-wrap: wrap; gap: 2px var(--tv-a3); font-size: var(--tv-gr-klein); color: var(--tv-text-2); }
  .sprachen { display: inline-flex; align-items: center; gap: 6px; font-weight: 700; color: var(--tv-text); }
  .sprachen i { font-size: var(--tv-gr-marke); }

  .schritte { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 4px; margin: var(--tv-a3) 0 var(--tv-a2); }
  .schritt { display: flex; flex-direction: column; gap: 4px; min-width: 0; font-size: var(--tv-gr-marke); font-weight: 700; color: var(--tv-text-3); }
  .schritt > span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .schritt.done { color: var(--tv-text-2); }
  .schritt.done .balken b { background: var(--tv-erfolg); }
  .schritt.current { color: var(--tv-akzent); }
  .balken { height: 6px; background: var(--tv-mulde); border-radius: 1px; overflow: hidden; }
  .balken b { display: block; height: 100%; background: var(--tv-akzent); transition: width 0.4s; }

  .taetigkeit { font-size: var(--tv-gr-klein); color: var(--tv-text-2); padding: var(--tv-a2) var(--tv-a3);
                background: var(--tv-mulde); border-radius: var(--tv-ecke-klein);
                white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .fuss { display: flex; flex-wrap: wrap; align-items: center; gap: var(--tv-a1) var(--tv-a3); margin-top: var(--tv-a2);
          font-size: var(--tv-gr-klein); color: var(--tv-text-2); }


  @container liste (max-width: 640px) {
    .laeuft { grid-template-columns: minmax(0, 1fr); }
    .bild { max-width: 240px; }
    .schritte { grid-template-columns: repeat(3, minmax(0, 1fr)); row-gap: var(--tv-a2); }
  }
</style>

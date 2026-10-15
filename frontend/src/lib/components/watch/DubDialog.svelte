<!--
  TubeVault - Nachvertonung vormerken
  Für genau ein Video: Zielsprache, Stimme (aus den Stimmen, die der
  Vertonungsdienst gerade hat) und ob Untertitel der Quelle als Transkript
  dienen dürfen. Stimme und Untertitel sind mit der Vorauswahl der Seite
  Nachvertonung vorbelegt.
  Usage: <DubDialog bind:this={dubRef} onQueued={...} />  dubRef.open(video)
-->
<script>
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';
  import { getSetting } from '../../stores/settings.js';
  import { ago, secondsSince } from '../../utils/dubbingText.js';

  let { onQueued = null } = $props();

  const LANGUAGES = [['de', 'Deutsch'], ['en', 'Englisch']];
  const SUBTITLE_USES = [
    ['any', 'Ja, auch automatische Untertitel'],
    ['manual', 'Nur vom Autor erstellte Untertitel'],
    ['never', 'Nein, aus dem Ton transkribieren'],
  ];

  let video = $state(null);
  let voices = $state([]);
  let reportedAt = $state(null);
  let voice = $state('');
  let language = $state('de');
  let subtitles = $state('any');
  let busy = $state(false);
  let sameLanguage = $derived(!!video && (video.language || '').toLowerCase() === language);

  export async function open(target) {
    video = target;
    language = 'de';
    subtitles = getSetting('dub.default_subtitles', 'any');
    try {
      const choice = await api.getDubbingVoices();
      voices = choice.voices;
      reportedAt = choice.reported_at;
      voice = choice.default || '';
    } catch (e) { toast.error(e.message); voices = []; }
  }

  function close() { video = null; }

  async function submit() {
    busy = true;
    try {
      const outcome = await api.enqueueDubbing({
        video_id: video.id, target_language: language, voice: voice || null, subtitles,
      });
      if (outcome.queued) {
        toast.success(sameLanguage ? 'Zum Neu-Sprechen vorgemerkt' : 'Zur Nachvertonung vorgemerkt');
        onQueued?.(outcome.request);
      } else toast.info(`Nicht vorgemerkt: ${outcome.reason}`);
      close();
    } catch (e) { toast.error(e.message); }
    busy = false;
  }
</script>

{#if video}
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="schleier" onclick={close} onkeydown={(e) => e.key === 'Escape' && close()}>
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <div class="fenster" role="dialog" aria-label="Nachvertonen" tabindex="-1" onclick={(e) => e.stopPropagation()}>
      <h3><i class="fa-solid fa-language"></i> Nachvertonen</h3>
      <p class="video" title={video.title}>{video.title}</p>

      <label class="zeile">
        <span>Zielsprache</span>
        <select class="tv-eingabe" bind:value={language}>
          {#each LANGUAGES as [code, label]}<option value={code}>{label}</option>{/each}
        </select>
      </label>

      {#if sameLanguage}
        <p class="hinweis">Das Video ist bereits {LANGUAGES.find(([code]) => code === language)?.[1]}: es wird ohne Übersetzung mit der gewählten Stimme neu gesprochen.</p>
      {/if}

      <label class="zeile">
        <span>Stimme</span>
        {#if voices.length > 0}
          <select class="tv-eingabe" bind:value={voice}>
            {#each voices as name}<option value={name}>{name}</option>{/each}
          </select>
        {:else}
          <span class="tv-schwach" title="Die Stimmen meldet der Nachvertoner, sobald er läuft">Vorauswahl des Nachvertoners</span>
        {/if}
      </label>

      <label class="zeile">
        <span title="Untertitel in der Originalsprache ersparen das Transkribieren">Untertitel nutzen</span>
        <select class="tv-eingabe" bind:value={subtitles}>
          {#each SUBTITLE_USES as [value, label]}<option {value}>{label}</option>{/each}
        </select>
      </label>

      {#if reportedAt}
        <p class="hinweis">Stimmen gemeldet {ago(secondsSince(reportedAt))}</p>
      {/if}

      <div class="knoepfe">
        <button class="tv-knopf ohne" onclick={close}>Abbrechen</button>
        <button class="tv-knopf haupt" onclick={submit} disabled={busy}><i class="fa-solid fa-plus"></i> Vormerken</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .schleier {
    position: fixed; inset: 0; z-index: 1000; display: flex; align-items: center;
    justify-content: center; background: var(--tv-schleier);
  }
  .fenster {
    width: min(500px, calc(100vw - 32px)); padding: var(--tv-a5); border-radius: var(--tv-ecke);
    background: var(--tv-karte); border: 1px solid var(--tv-rand-stark); color: var(--tv-text);
    box-shadow: var(--tv-schatten); outline: 0;
  }
  h3 { margin: 0 0 var(--tv-a1); font-size: var(--tv-gr-titel); display: flex; gap: var(--tv-a2); align-items: center; }
  h3 i { color: var(--tv-akzent); }
  .video {
    margin: 0 0 var(--tv-a4); font-size: var(--tv-gr-klein); color: var(--tv-text-2);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .zeile {
    display: grid; grid-template-columns: 150px minmax(0, 1fr); align-items: center; gap: var(--tv-a3);
    margin-bottom: var(--tv-a3); font-weight: 600;
  }
  .zeile select { width: 100%; min-width: 0; }
  .hinweis { margin: 0 0 var(--tv-a3); font-size: var(--tv-gr-klein); color: var(--tv-text-3); }
  .knoepfe { display: flex; justify-content: flex-end; gap: var(--tv-a2); margin-top: var(--tv-a4); }
  @media (max-width: 520px) {
    .zeile { grid-template-columns: 1fr; gap: var(--tv-a1); }
  }
</style>

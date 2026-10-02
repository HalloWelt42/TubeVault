<!--
  TubeVault – Nachvertonung vormerken
  Für genau ein Video: Zielsprache, Stimme (aus den Stimmen, die der
  Vertonungsdienst gerade hat) und ob Untertitel der Quelle als Transkript
  dienen dürfen.
  Usage: <DubDialog bind:this={dubRef} />  dubRef.open(video)
-->
<script>
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';
  import { formatDateRelative } from '../../utils/format.js';

  const LANGUAGES = [['de', 'Deutsch'], ['en', 'Englisch']];
  const SUBTITLE_USES = [
    ['any', 'Ja - Untertitel der Quelle verwenden'],
    ['manual', 'Nur vom Autor erstellte Untertitel'],
    ['never', 'Nein - aus dem Ton transkribieren'],
  ];

  let video = $state(null);
  let voices = $state([]);
  let reportedAt = $state(null);
  let voice = $state('');
  let language = $state('de');
  let subtitles = $state('any');
  let busy = $state(false);

  export async function open(target) {
    video = target;
    language = (target.language || '').toLowerCase() === 'de' ? 'en' : 'de';
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
      if (outcome.queued) toast.success('Zur Nachvertonung vorgemerkt');
      else toast.info(`Nicht vorgemerkt: ${outcome.reason}`);
      close();
    } catch (e) { toast.error(e.message); }
    busy = false;
  }
</script>

{#if video}
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="dub-overlay" onclick={close} onkeydown={(e) => e.key === 'Escape' && close()}>
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="dub-dialog" onclick={(e) => e.stopPropagation()}>
      <h3><i class="fa-solid fa-language"></i> Nachvertonen</h3>
      <p class="dub-video" title={video.title}>{video.title}</p>

      <label class="dub-row">
        <span>Zielsprache</span>
        <select bind:value={language}>
          {#each LANGUAGES as [code, label]}<option value={code}>{label}</option>{/each}
        </select>
      </label>

      <label class="dub-row">
        <span>Stimme</span>
        {#if voices.length > 0}
          <select bind:value={voice}>
            {#each voices as name}<option value={name}>{name}</option>{/each}
          </select>
        {:else}
          <span class="dub-hint">Zeit (Stimmenliste folgt, sobald der Nachvertoner läuft)</span>
        {/if}
      </label>

      <label class="dub-row">
        <span title="Untertitel in der Originalsprache ersparen das Transkribieren">Untertitel nutzen</span>
        <select bind:value={subtitles}>
          {#each SUBTITLE_USES as [value, label]}<option {value}>{label}</option>{/each}
        </select>
      </label>

      {#if reportedAt}
        <p class="dub-note">Stimmen gemeldet {formatDateRelative(reportedAt)}</p>
      {/if}

      <div class="dub-actions">
        <button class="dub-btn" onclick={close}>Abbrechen</button>
        <button class="dub-btn dub-primary" onclick={submit} disabled={busy}>Vormerken</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .dub-overlay {
    position: fixed; inset: 0; z-index: 1000; display: flex; align-items: center;
    justify-content: center; background: rgba(0, 0, 0, 0.55);
  }
  .dub-dialog {
    width: min(420px, calc(100vw - 32px)); padding: 20px; border-radius: 12px;
    background: var(--bg-secondary); color: var(--text-primary);
    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.45);
  }
  h3 { margin: 0 0 4px; font-size: 1rem; display: flex; gap: 8px; align-items: center; }
  .dub-video {
    margin: 0 0 14px; font-size: 0.8rem; color: var(--text-secondary);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .dub-row {
    display: grid; grid-template-columns: 120px 1fr; align-items: center; gap: 10px;
    margin-bottom: 10px; font-size: 0.82rem;
  }
  .dub-row select {
    padding: 6px 8px; border-radius: 6px; border: 1px solid var(--border-primary);
    background: var(--bg-tertiary); color: var(--text-primary); font: inherit; min-width: 0;
  }
  .dub-hint, .dub-note { font-size: 0.74rem; color: var(--text-tertiary); }
  .dub-note { margin: 0 0 4px; }
  .dub-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
  .dub-btn {
    padding: 7px 14px; border-radius: 6px; border: 1px solid var(--border-primary);
    background: var(--bg-tertiary); color: var(--text-primary); font: inherit; font-size: 0.82rem; cursor: pointer;
  }
  .dub-primary { background: var(--accent-primary); border-color: var(--accent-primary); color: var(--bg-primary); }
  .dub-btn:disabled { opacity: 0.5; cursor: default; }
</style>

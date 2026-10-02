<!--
  TubeVault – Tonspur-Umschalter
  Zeigt sich nur, wenn ein Video zusätzliche Tonspuren hat. Umschalten
  zwischen Original und z.B. der deutschen Nachvertonung, ohne dass das
  Video doppelt gespeichert ist. Die Wahl gilt als Vorliebe für alle Videos.
-->
<script>
  import { api } from '../../api/client.js';
  import { followVideo, preferredLanguage, rememberLanguage } from '../../utils/audioTrackSync.js';

  let { videoId, videoEl, originalLanguage = null, mediaKey = 0 } = $props();

  const LANGUAGE_NAMES = { de: 'Deutsch', en: 'Englisch', fr: 'Französisch', es: 'Spanisch', it: 'Italienisch' };

  let tracks = $state([]);
  let activeId = $state(null);     // null = Original-Ton
  let audioEl = $state(null);
  let sync = null;

  let activeTrack = $derived(tracks.find(t => t.id === activeId) || null);
  let originalLabel = $derived(
    originalLanguage ? `Original (${LANGUAGE_NAMES[originalLanguage] || originalLanguage.toUpperCase()})` : 'Original'
  );

  async function load() {
    try {
      tracks = (await api.getAudioTracks(videoId)).tracks || [];
    } catch { tracks = []; }
    const wanted = tracks.find(t => t.language === preferredLanguage());
    activeId = wanted ? wanted.id : null;
  }

  function choose(track) {
    activeId = track ? track.id : null;
    rememberLanguage(track ? track.language : '');
  }

  // Video oder Datei gewechselt → Spuren neu lesen
  $effect(() => { videoId; mediaKey; load(); });

  // Gleichlauf an- und abkoppeln, sobald Spur, Player und Audio-Element stehen
  $effect(() => {
    if (!activeTrack || !videoEl || !audioEl) return;
    sync = followVideo(videoEl, audioEl);
    return () => { sync?.stop(); sync = null; };
  });
</script>

{#if tracks.length > 0}
  <div class="tracks" role="group" aria-label="Tonspur">
    <i class="fa-solid fa-volume-high tracks-icon" title="Tonspur"></i>
    <button class="track" class:on={activeId === null} onclick={() => choose(null)}>{originalLabel}</button>
    {#each tracks as track (track.id)}
      <button class="track" class:on={activeId === track.id} onclick={() => choose(track)}
              title={track.voice ? `Nachvertonung, Stimme: ${track.voice}` : 'Zusätzliche Tonspur'}>
        {track.label}
      </button>
    {/each}
  </div>
  {#if activeTrack}
    <audio bind:this={audioEl} src={api.audioTrackUrl(videoId, activeTrack.id)} preload="auto"></audio>
  {/if}
{/if}

<style>
  .tracks {
    margin: 2px 0 10px;
    display: inline-flex; align-items: center; gap: 2px; padding: 3px;
    background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 9px;
  }
  .tracks-icon { color: var(--text-tertiary); font-size: 0.78rem; padding: 0 8px 0 6px; }
  .track {
    padding: 5px 12px; border: none; border-radius: 6px; background: none;
    color: var(--text-secondary); font-size: 0.8rem; font-weight: 600; cursor: pointer;
  }
  .track:hover { color: var(--text-primary); }
  .track.on { background: var(--accent-primary); color: #fff; }
</style>

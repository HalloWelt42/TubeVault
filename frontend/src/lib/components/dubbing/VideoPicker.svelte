<!--
  TubeVault - Video zum Vertonen wählen (Knopf "Video vertonen")
  Sucht unter den geladenen Videos; ohne Suchwort stehen die zuletzt
  geladenen oben. Die Wahl öffnet das Vormerken (DubDialog).
  Usage: <VideoPicker bind:this={pickerRef} onPick={(video) => ...} />  pickerRef.open()
-->
<script>
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';
  import { formatDuration } from '../../utils/format.js';

  let { onPick } = $props();

  const RESULTS = 12;
  const TYPE_PAUSE_MS = 250;

  let visible = $state(false);
  let query = $state('');
  let results = $state([]);
  let loading = $state(false);
  let timer = null;
  let run = 0;

  export function open() {
    visible = true;
    query = '';
    search();
  }

  function close() {
    visible = false;
    clearTimeout(timer);
  }

  async function search() {
    const mine = ++run;
    loading = true;
    try {
      const params = { status: 'ready', per_page: RESULTS, sort_by: 'download_date', sort_order: 'desc' };
      if (query.trim()) params.search = query.trim();
      const answer = await api.getVideos(params);
      if (mine === run) results = answer.videos || [];
    } catch (e) { toast.error(e.message); }
    if (mine === run) loading = false;
  }

  function typed() {
    clearTimeout(timer);
    timer = setTimeout(search, TYPE_PAUSE_MS);
  }

  function pick(video) {
    close();
    onPick(video);
  }
</script>

{#if visible}
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="schleier" onclick={close} onkeydown={(e) => e.key === 'Escape' && close()}>
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <div class="fenster" role="dialog" aria-label="Video vertonen" tabindex="-1" onclick={(e) => e.stopPropagation()}>
      <div class="kopf">
        <h3><i class="fa-solid fa-language"></i> Video vertonen</h3>
        <button class="tv-knopf symbol klein ohne" onclick={close} title="Schließen"><i class="fa-solid fa-xmark"></i></button>
      </div>
      <!-- svelte-ignore a11y_autofocus -->
      <input class="tv-eingabe" type="search" placeholder="Titel oder Kanal suchen" bind:value={query} oninput={typed} autofocus />
      <div class="treffer">
        {#if loading && !results.length}
          <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Sucht ...</div>
        {:else if !results.length}
          <div class="tv-leer">Kein geladenes Video gefunden.</div>
        {:else}
          {#if !query.trim()}<div class="tv-etikett hinweis">Zuletzt geladen</div>{/if}
          {#each results as video (video.id)}
            <button class="video" onclick={() => pick(video)} title="Dieses Video vertonen">
              <img src={api.thumbnailUrl(video.id)} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
              <span class="text">
                <span class="titel">{video.title}</span>
                <span class="meta">
                  {#if video.channel_name}<span>{video.channel_name}</span>{/if}
                  {#if video.duration}<span class="zahl">{formatDuration(video.duration)}</span>{/if}
                  {#if video.extra_audio?.length}<span class="tv-zustand fertig" title="Hat schon eine zusätzliche Tonspur">vertont</span>{/if}
                </span>
              </span>
            </button>
          {/each}
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .schleier { position: fixed; inset: 0; z-index: 1000; display: flex; align-items: flex-start; justify-content: center;
              padding-top: 10vh; background: var(--tv-schleier); }
  .fenster { width: min(640px, calc(100vw - 32px)); max-height: 76vh; display: flex; flex-direction: column; gap: var(--tv-a3);
             padding: var(--tv-a4) var(--tv-a5) var(--tv-a5); border-radius: var(--tv-ecke); background: var(--tv-karte);
             border: 1px solid var(--tv-rand-stark); box-shadow: var(--tv-schatten); outline: 0; }
  .kopf { display: flex; align-items: center; justify-content: space-between; }
  h3 { margin: 0; font-size: var(--tv-gr-titel); display: flex; gap: var(--tv-a2); align-items: center; }
  h3 i { color: var(--tv-akzent); }
  .tv-eingabe { width: 100%; }
  .treffer { flex: 1; min-height: 0; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
  .hinweis { padding: var(--tv-a1) var(--tv-a2); }
  .video { display: grid; grid-template-columns: 112px minmax(0, 1fr); gap: var(--tv-a3); align-items: center; width: 100%;
           padding: 6px var(--tv-a2); border: 0; background: none; color: var(--tv-text); font: inherit; text-align: left;
           border-radius: var(--tv-ecke); cursor: pointer; }
  .video:hover { background: var(--tv-karte-2); }
  .video img { width: 112px; aspect-ratio: 16 / 9; object-fit: cover; border-radius: var(--tv-ecke-klein); background: var(--tv-mulde); }
  .text { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .titel { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .meta { display: flex; align-items: center; gap: var(--tv-a2); font-size: var(--tv-gr-klein); color: var(--tv-text-2);
          white-space: nowrap; overflow: hidden; }
</style>

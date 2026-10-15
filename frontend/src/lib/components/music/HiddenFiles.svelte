<!--
  Ausgeblendete Titel der eigenen Sammlung: Knopf mit Anzahl (nur, wenn es
  welche gibt), darunter die Liste mit "Einblenden" je Titel. Die Sammlung ist
  lesend eingebunden; ausblenden ersetzt dort das Löschen.
-->
<script>
  import { onMount } from 'svelte';
  import { api } from '../../api/client.js';
  import { coverUrl } from '../../utils/musicTrack.js';
  import { formatDuration } from '../../utils/format.js';
  import { toast } from '../../stores/notifications.js';

  let { onRestored = () => {} } = $props();

  let count = $state(0);
  let items = $state(null);
  let open = $state(false);
  let box = $state(null);

  async function loadCount() {
    try { count = (await api.musicFilesStatus()).hidden || 0; } catch { count = 0; }
  }

  async function toggle() {
    open = !open;
    if (open) {
      try { items = await api.musicHiddenFiles(); } catch (e) { toast.error(e.message); open = false; }
    }
  }

  async function restore(file) {
    try {
      await api.musicFileHidden(file.id, false);
      items = items.filter((f) => f.id !== file.id);
      count = Math.max(0, count - 1);
      if (!items.length) open = false;
      toast.success(`Wieder eingeblendet: ${file.title}`);
      onRestored(file);
    } catch (e) { toast.error(e.message); }
  }

  function outside(e) {
    if (open && box && !box.contains(e.target)) open = false;
  }

  onMount(loadCount);
</script>

<svelte:window onpointerdown={outside} onkeydown={(e) => { if (e.key === 'Escape') open = false; }} />

{#if count}
  <span class="ausgeblendet" bind:this={box}>
    <button class:an={open} onclick={toggle} title="Ausgeblendete Titel der eigenen Sammlung anzeigen und wieder einblenden">
      <i class="fa-solid fa-eye-slash"></i> Ausgeblendet <span class="zahl">{count}</span></button>
    {#if open && items}
      <div class="feld" role="list">
        {#each items as file (file.id)}
          <div class="zeile" role="listitem">
            <img src={coverUrl(file.id)} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
            <span class="text"><span class="t">{file.title}</span><span class="w">{file.artist || ''}</span></span>
            <span class="zahl dauer">{formatDuration(Math.floor(file.duration || 0))}</span>
            <button class="einblenden" onclick={() => restore(file)} title="Wieder in Listen und Mixen zeigen">
              <i class="fa-solid fa-eye"></i> Einblenden</button>
          </div>
        {/each}
      </div>
    {/if}
  </span>
{/if}

<style>
  .ausgeblendet { position: relative; }
  .ausgeblendet > button { height: 34px; padding: 0 10px; border: 0; border-radius: var(--tv-ecke); background: none;
                           color: var(--tv-text-2); font: inherit; font-size: var(--tv-gr-klein); cursor: pointer; white-space: nowrap; }
  .ausgeblendet > button:hover, .ausgeblendet > button.an { color: var(--tv-text); background: var(--tv-karte-2); }
  .feld { position: absolute; left: 0; top: calc(100% + 6px); z-index: 40; width: 460px; max-height: 60vh; overflow-y: auto;
          padding: var(--tv-a2); background: var(--tv-karte); border-radius: var(--tv-ecke); box-shadow: var(--tv-schatten); }
  .zeile { display: grid; grid-template-columns: 40px minmax(0, 1fr) auto auto; gap: var(--tv-a2); align-items: center; padding: 4px; }
  .zeile img { width: 40px; height: 40px; object-fit: cover; border-radius: var(--tv-ecke-klein); background: var(--tv-mulde); }
  .text { min-width: 0; display: flex; flex-direction: column; }
  .t { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .w, .dauer { font-size: var(--tv-gr-klein); color: var(--tv-text-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .einblenden { height: 34px; padding: 0 10px; border: 0; border-radius: var(--tv-ecke); background: var(--tv-karte-3);
                color: var(--tv-text); font: inherit; font-size: var(--tv-gr-klein); cursor: pointer; white-space: nowrap; }
  .einblenden:hover { background: var(--tv-akzent); color: var(--tv-akzent-text); }
</style>

<!--
  Eigene Videos: welcher Ordner der Sammlung, sein Stand und das Einlesen
  (starten, anhalten, fortsetzen). Während des Einlesens steht hier der
  Fortschritt; Geprüftes erscheint parallel schon in der Liste.
-->
<script>
  import { formatDateRelative } from '../../utils/format.js';

  let {
    folders = [],
    candidates = [],
    selectedId = null,
    busy = false,
    onSelect = () => {},      // (folderId)
    onAdd = () => {},         // (path) - neuen Ordner einlesen
    onScan = () => {},        // (folderId)
    onPause = () => {},       // (folderId)
  } = $props();

  let current = $derived(folders.find(f => f.id === selectedId) || null);
  let newCandidates = $derived(candidates.filter(c => !folders.some(f => f.path === c)));
  let adding = $state('');

  const label = (f) => f.path || 'Ganze Sammlung';
  const running = (f) => f && (f.state === 'running' || f.state === 'queued');

  function pick(e) {
    const value = e.target.value;
    if (value.startsWith('neu:')) {
      onAdd(value.slice(4));
      e.target.value = String(selectedId ?? '');
    } else if (value) {
      onSelect(Number(value));
    }
  }
</script>

<div class="leiste">
  <select class="tv-eingabe wahl" value={String(selectedId ?? '')} onchange={pick} disabled={busy}
          title="Ordner der Sammlung">
    {#each folders as f (f.id)}
      <option value={String(f.id)}>{label(f)} ({f.files.toLocaleString('de-DE')} Dateien)</option>
    {/each}
    {#if newCandidates.length}
      <optgroup label="Anderen Ordner einlesen">
        {#each newCandidates as c}<option value={'neu:' + c}>{c}</option>{/each}
        {#if !folders.some(f => f.path === '')}<option value="neu:">Ganze Sammlung</option>{/if}
      </optgroup>
    {/if}
  </select>

  {#if current}
    {#if running(current)}
      <button class="tv-knopf" onclick={() => onPause(current.id)} title="Einlesen anhalten - Geprüftes bleibt">
        <i class="fa-solid fa-pause"></i> Anhalten</button>
    {:else if current.state === 'paused'}
      <button class="tv-knopf haupt" onclick={() => onScan(current.id)}><i class="fa-solid fa-play"></i> Fortsetzen</button>
    {:else}
      <button class="tv-knopf" onclick={() => onScan(current.id)}
              title="Neue und geänderte Dateien einlesen, alle offenen neu abgleichen">
        <i class="fa-solid fa-rotate"></i> Neu einlesen</button>
    {/if}

    <span class="stand tv-klein">
      {#if !current.present}
        <span class="tv-zustand warnung"><i class="fa-solid fa-plug-circle-xmark"></i> Ordner nicht erreichbar</span>
        <span class="tv-leise">Der gespeicherte Stand bleibt sichtbar.</span>
      {:else if current.state === 'running' && current.phase === 'listing'}
        <span class="tv-zustand laeuft"><i class="fa-solid fa-magnifying-glass"></i> Dateien werden gesucht</span>
        <span class="zahl">{(current.found_so_far || 0).toLocaleString('de-DE')} gefunden</span>
      {:else if running(current)}
        <span class="tv-zustand laeuft"><i class="fa-solid fa-spinner fa-spin"></i>
          {current.state === 'queued' ? 'Wartet auf den Einleser' : 'Wird eingelesen'}</span>
        <span class="zahl">{current.checked.toLocaleString('de-DE')} von {current.files.toLocaleString('de-DE')} geprüft</span>
        <span class="balken"><b style:width="{current.files ? (current.checked / current.files * 100).toFixed(1) : 0}%"></b></span>
      {:else if current.state === 'paused'}
        <span class="tv-zustand"><i class="fa-solid fa-pause"></i> Angehalten</span>
        <span class="zahl">{current.checked.toLocaleString('de-DE')} von {current.files.toLocaleString('de-DE')} geprüft</span>
      {:else if current.scan_finished_at}
        <span class="tv-leise">eingelesen {formatDateRelative(current.scan_finished_at)}</span>
      {/if}
    </span>
  {/if}
</div>

<style>
  .leiste { display: flex; align-items: center; gap: var(--tv-a2); flex-wrap: wrap; margin-top: var(--tv-a4); }
  .wahl { min-width: 280px; max-width: 100%; }
  .stand { display: flex; align-items: center; gap: var(--tv-a3); flex-wrap: wrap; color: var(--tv-text-2); }
  .balken { width: 160px; height: 6px; background: var(--tv-mulde); border-radius: 1px; overflow: hidden; }
  .balken b { display: block; height: 100%; background: var(--tv-akzent); transition: width 0.5s; }
</style>

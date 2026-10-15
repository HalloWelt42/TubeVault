<!--
  Eigene Videos: eine Datei in der Liste (Gestaltung nach mockups/eigene-videos.html: .datei).
-->
<script>
  import { formatDuration, formatSize } from '../../utils/format.js';
  import { FINDING, DECISIONS, matchSummary } from './ownStatus.js';

  let { file, selected = false, onSelect = () => {} } = $props();

  let finding = $derived(FINDING[file.finding] || FINDING.unknown);
  let decided = $derived(file.decision !== 'open');
</script>

<div class="datei" class:gewaehlt={selected} role="button" tabindex="0"
     onclick={onSelect} onkeydown={(e) => e.key === 'Enter' && onSelect()}>
  <span class="farbe" style:background={finding.farbe}></span>
  <div class="text">
    <div class="name" title={file.rel_path}>{file.name}</div>
    <div class="unter">
      <span class="zahl">{file.duration ? formatDuration(file.duration) : '-'}{' · '}{formatSize(file.size)}</span>
      <span class="treffer">{decided ? DECISIONS[file.decision] : matchSummary(file)}</span>
    </div>
  </div>
  <span class="tv-zustand {decided ? '' : finding.zustand}">{decided ? 'erledigt' : finding.kurz}</span>
</div>

<style>
  .datei {
    display: grid; grid-template-columns: 10px minmax(0, 1fr) auto; gap: var(--tv-a3); align-items: center;
    padding: var(--tv-a2) var(--tv-a3); border-radius: var(--tv-ecke); cursor: pointer;
  }
  .datei:hover { background: var(--tv-flaeche); }
  .datei.gewaehlt { background: var(--tv-karte); outline: 1px solid rgba(var(--tv-akzent-rgb), 0.5); }
  .datei:focus-visible { outline: 2px solid var(--tv-akzent); }
  .farbe { width: 10px; height: 36px; border-radius: 2px; }
  .text { min-width: 0; }
  .name { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .unter { display: flex; gap: var(--tv-a3); margin-top: 2px; font-size: var(--tv-gr-klein); color: var(--tv-text-2); min-width: 0; }
  .treffer { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .unter .zahl { white-space: nowrap; flex: none; }
</style>

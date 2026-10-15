<!--
  Speicher in der Übersicht: belegt und frei je Platte (Medien und System,
  bei nur einer Platte diese eine), darunter was Bibliothek und Datenbank
  selbst belegen. Zahlen aus /api/system/stats.
-->
<script>
  import OverviewCard from './OverviewCard.svelte';
  import { formatSize } from '../../utils/format.js';

  const FULL_FROM = 90;   // ab so viel Prozent Belegung warnt der Balken

  let { stats } = $props();

  let disks = $derived(stats.storage_split
    ? [{ name: 'Medien', disk: stats.disk_media }, { name: 'System und Index', disk: stats.disk_meta }]
    : [{ name: 'Speicher', disk: stats.disk }]);
</script>

<OverviewCard title="Speicher">
  {#each disks as { name, disk } (name)}
    {#if disk}
      <div class="platte">
        <div class="oben">
          <span>{name}</span>
          <span class="zahl">{formatSize(disk.used)} von {formatSize(disk.total)}</span>
        </div>
        <div class="balken" class:voll={disk.percent >= FULL_FROM}><b style:width="{disk.percent}%"></b></div>
        <div class="frei"><span class="zahl">{formatSize(disk.free)}</span> frei</div>
      </div>
    {/if}
  {/each}
  <div class="eigen">Bibliothek <span class="zahl">{formatSize(stats.total_size_bytes)}</span> · Datenbank <span class="zahl">{formatSize(stats.db_size_bytes)}</span></div>
</OverviewCard>

<style>
  .platte + .platte { margin-top: var(--tv-a3); }
  .oben { display: flex; justify-content: space-between; gap: var(--tv-a2); font-size: var(--tv-gr-klein); }
  .balken { position: relative; height: 8px; margin-top: 6px; border-radius: var(--tv-ecke-klein); background: var(--tv-karte-3); overflow: hidden; }
  .balken b { position: absolute; left: 0; top: 0; bottom: 0; background: var(--tv-akzent); }
  .balken.voll b { background: var(--tv-gefahr); }
  .frei { margin-top: 4px; font-size: var(--tv-gr-klein); color: var(--tv-text-3); }
  .eigen { margin-top: var(--tv-a3); font-size: var(--tv-gr-klein); color: var(--tv-text-2); }
</style>

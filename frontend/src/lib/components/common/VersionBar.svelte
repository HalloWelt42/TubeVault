<!--
  Leiste "Neue Version ist da" (Versionswache, lib/utils/versionWatch.js).
  Erscheint nur, wenn ein Update ausgeliefert ist und die Seite noch nicht
  selbst neu geladen hat (das tut sie beim nächsten Seitenwechsel).
-->
<script>
  import { newVersion, reloadNow } from '../../utils/versionWatch.js';
</script>

{#if $newVersion}
  <div class="versionsleiste" role="status">
    <i class="fa-solid fa-arrows-rotate"></i>
    <span>Neue Version <span class="zahl">{$newVersion}</span> ist da, sie lädt beim nächsten Seitenwechsel.</span>
    <button class="tv-knopf klein haupt" onclick={reloadNow}>Jetzt laden</button>
  </div>
{/if}

<style>
  .versionsleiste {
    display: flex; align-items: center; justify-content: center; gap: var(--tv-a3);
    padding: 6px var(--tv-a4); flex: none;
    background: rgba(var(--tv-akzent-rgb), 0.12); color: var(--tv-text);
    border-bottom: 1px solid rgba(var(--tv-akzent-rgb), 0.35); font-size: var(--tv-gr-klein);
  }
  .versionsleiste i { color: var(--tv-akzent); }
</style>

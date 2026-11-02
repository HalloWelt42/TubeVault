<script>
  // Archiv: die archivierten Videos (VideoListPage), dazu Dearchivieren für die Auswahl
  import { api } from '../lib/api/client.js';
  import { toast } from '../lib/stores/notifications.js';
  import VideoListPage from '../lib/components/video/VideoListPage.svelte';

  async function unarchiveSelected(ids, done) {
    if (ids.length === 0) return;
    try {
      await api.archiveBatch(ids, true);
      toast.success(`${ids.length} Video(s) dearchiviert`);
      done();
    } catch (e) { toast.error(e.message); }
  }
</script>

<VideoListPage routeKey="archives" title="Archiv" icon="fa-solid fa-box-archive" archived={true} showMusic={true}
               emptyText="Keine archivierten Videos. Archivieren geht an jeder Kachel und in der Wiedergabe.">
  {#snippet batch({ ids, done })}
    <button class="tv-knopf klein" onclick={() => unarchiveSelected(ids, done)}>
      <i class="fa-solid fa-box-open"></i> Dearchivieren</button>
  {/snippet}
</VideoListPage>

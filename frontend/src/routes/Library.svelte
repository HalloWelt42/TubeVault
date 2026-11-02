<script>
  // Bibliothek: die nicht archivierten Videos (VideoListPage), dazu die Aktionen für die Auswahl
  import { api } from '../lib/api/client.js';
  import { toast } from '../lib/stores/notifications.js';
  import VideoListPage from '../lib/components/video/VideoListPage.svelte';
  import ConfirmDialog from '../lib/components/common/ConfirmDialog.svelte';

  let confirmRef;

  const TYPE_LABELS = { video: 'Video', short: 'Short', live: 'Live' };

  // Eine Aktion auf der Auswahl: ausführen, melden, danach Auswahl leeren und neu laden
  async function run(ids, done, action, message) {
    if (ids.length === 0) return;
    try {
      toast.success(message(await action(ids), ids.length));
      done();
    } catch (e) { toast.error(e.message); }
  }

  async function deleteSelected(ids, done) {
    if (ids.length === 0) return;
    const ok = await confirmRef.ask(`${ids.length} Videos löschen?`, 'Alle ausgewählten Videos werden unwiderruflich gelöscht.');
    if (!ok) return;
    let deleted = 0;
    for (const id of ids) { try { await api.deleteVideo(id); deleted++; } catch {} }
    toast.success(`${deleted} Video(s) gelöscht`);
    done();
  }
</script>

<VideoListPage routeKey="library" title="Bibliothek" archived={false} showMusic={true}
               emptyText="Noch keine Videos in der Bibliothek.">
  {#snippet batch({ ids, done })}
    {#each Object.entries(TYPE_LABELS) as [type, label]}
      <button class="tv-knopf klein" onclick={() => run(ids, done, (x) => api.setTypeBatch(x, type),
                                                          (r) => `${r.updated} Video(s) → ${label}`)}>
        <i class="fa-solid {type === 'video' ? 'fa-play' : type === 'short' ? 'fa-mobile-screen' : 'fa-tower-broadcast'}"></i> Als {label}
      </button>
    {/each}
    <span class="tv-trenner"></span>
    <button class="tv-knopf klein" title="Von Hand als Musik festlegen - keine Automatik ändert das"
            onclick={() => run(ids, done, (x) => api.setMusicBatch(x, true), (r) => `${r.updated} Video(s) als Musik festgelegt`)}>
      <i class="fa-solid fa-music"></i> Musik</button>
    <button class="tv-knopf klein" title="Von Hand als keine Musik festlegen"
            onclick={() => run(ids, done, (x) => api.setMusicBatch(x, false), (r) => `${r.updated} Video(s) als keine Musik festgelegt`)}>
      <i class="fa-solid fa-microphone-slash"></i> Keine Musik</button>
    <button class="tv-knopf klein" title="Hörbuch oder Hörspiel: nie in der Musik, eigener Bereich in fester Reihenfolge"
            onclick={() => run(ids, done, (x) => api.setAudiobookBatch(x, true), (r) => `${r.updated} Video(s) als Hörbuch festgelegt`)}>
      <i class="fa-solid fa-book-open"></i> Hörbuch</button>
    <button class="tv-knopf klein" title="Kein Hörbuch"
            onclick={() => run(ids, done, (x) => api.setAudiobookBatch(x, false), (r) => `${r.updated} Video(s) als kein Hörbuch festgelegt`)}>
      <i class="fa-solid fa-book"></i> Kein Hörbuch</button>
    <span class="tv-trenner"></span>
    <button class="tv-knopf klein" onclick={() => run(ids, done, (x) => api.archiveBatch(x, false), (_, n) => `${n} Video(s) archiviert`)}>
      <i class="fa-solid fa-box-archive"></i> Archivieren</button>
    <button class="tv-knopf klein gefahr" onclick={() => deleteSelected(ids, done)}>
      <i class="fa-regular fa-trash-can"></i> Löschen</button>
  {/snippet}
</VideoListPage>

<ConfirmDialog bind:this={confirmRef} />

<!--
  Eigene Videos, Reiter "Eingeordnet": eigene und übernommene Videos nach
  Kanal (Gestaltung nach mockups/eigene-videos-bestand.html). Lädt seitenweise.
-->
<script>
  import { api } from '../../api/client.js';
  import { navigate } from '../../router/router.js';
  import { formatDuration, formatSize } from '../../utils/format.js';
  import { createListLoader } from '../../utils/listLoader.svelte.js';
  import { infiniteScroll } from '../../utils/infiniteScroll.js';

  let { onTotals = () => {} } = $props();   // (anzahl, bytes) für den Seitenkopf

  const PAGE = 60;
  let folderNamed = $state(0);
  const list = createListLoader(async (page) => {
    const r = await api.ownLibrary((page - 1) * PAGE, PAGE);
    folderNamed = r.folder_named_channels;
    onTotals(r.total, r.total_bytes);
    return { items: r.items, total: r.total };
  });
  $effect(() => { list.load(true); });

  // Aufeinanderfolgende Videos desselben Kanals bilden eine Gruppe
  let groups = $derived.by(() => {
    const out = [];
    for (const v of list.items) {
      const name = v.channel_name || 'Ohne Kanal';
      if (!out.length || out[out.length - 1].name !== name) out.push({ name, items: [] });
      out[out.length - 1].items.push(v);
    }
    return out;
  });
</script>

<div class="tv-rollfeld" data-scroll-root>
  {#if folderNamed > 0}
    <div class="hinweis tv-klein">
      <i class="fa-solid fa-triangle-exclamation"></i>
      <span>{folderNamed} {folderNamed === 1 ? 'Video trägt' : 'Videos tragen'} einen Ordnerpfad als Kanalnamen
        (aus dem früheren Einlesen). Kanal und Titel lassen sich am Video unter Bearbeiten ändern.</span>
    </div>
  {/if}

  {#if list.loading}
    <div class="tv-leer"><i class="fa-solid fa-spinner fa-spin"></i> Lädt ...</div>
  {:else if !list.items.length}
    <div class="tv-leer"><i class="fa-solid fa-folder-open"></i> Noch nichts eingeordnet.</div>
  {:else}
    {#each groups as group, i (group.name + i)}
      <section class="gruppe">
        <h2>{group.name}</h2>
        <div class="tv-raster">
          {#each group.items as v (v.id)}
            <button class="kachel" onclick={() => navigate(`/watch/${v.id}`)} title={v.import_path || v.title}>
              <span class="bild"><img src={api.thumbnailUrl(v.id)} alt="" loading="lazy"
                                      onerror={(e) => e.target.style.visibility = 'hidden'} /></span>
              <span class="titel">{v.title}</span>
              <span class="zahl tv-klein tv-leise">{formatDuration(v.duration)}{' · '}{formatSize(v.file_size)}
                {#if v.source === 'imported'}{' · '}aus der Quelle{/if}</span>
            </button>
          {/each}
        </div>
      </section>
    {/each}
    <div use:infiniteScroll={{ onLoadMore: list.loadMore, canLoad: list.canLoad }}></div>
  {/if}
</div>

<style>
  .hinweis { display: flex; gap: var(--tv-a2); align-items: flex-start; padding: var(--tv-a3) var(--tv-a4); margin-bottom: var(--tv-a4);
             background: rgba(var(--tv-warnung-rgb), 0.1); border-radius: var(--tv-ecke); color: var(--tv-text-2); }
  .hinweis i { color: var(--tv-warnung); margin-top: 3px; }
  .gruppe + .gruppe { margin-top: var(--tv-a5); }
  .gruppe h2 { margin: 0 0 var(--tv-a3); font-size: var(--tv-gr-titel); }
  .kachel { display: flex; flex-direction: column; gap: 6px; padding: 0; border: 0; background: none; color: var(--tv-text);
            font: inherit; text-align: left; cursor: pointer; }
  .bild { aspect-ratio: 16 / 9; background: var(--tv-mulde); border-radius: var(--tv-ecke); overflow: hidden; display: block; }
  .bild img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .kachel:hover .titel { color: var(--tv-akzent); }
  .titel { font-weight: 600; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; }
</style>

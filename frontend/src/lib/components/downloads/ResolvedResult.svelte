<!--
  Karte "Gefunden" in der rechten Spalte: was hinter einer geprüften Adresse
  steckt - ein Video (mit Auswahl der Qualität), eine Playlist (einzeln oder
  alle fehlenden laden) oder ein Kanal (abonnieren).
-->
<script>
  import { api } from '../../api/client.js';
  import { formatDuration, formatSize } from '../../utils/format.js';

  let {
    video = null, playlist = null, channel = null,
    quality = $bindable(''),
    loadingIds = new Set(),
    onStart = () => {}, onPlaylistOne = () => {}, onPlaylistAll = () => {},
    onSubscribe = () => {}, onClose = () => {},
  } = $props();

  // Video und Ton in einer Datei (progressiv) bzw. nur Bild (wird mit Ton zusammengefügt)
  const byQuality = (a, b) => (parseInt(b.quality) || 0) - (parseInt(a.quality) || 0);
  let progressive = $derived(video?.streams?.filter(s => s.is_progressive && s.type === 'video').sort(byQuality) || []);
  let adaptive = $derived(video?.streams?.filter(s => s.is_adaptive && s.type === 'video').sort(byQuality).slice(0, 5) || []);
  let missing = $derived(playlist ? playlist.videos.filter(v => !v.already_downloaded) : []);
</script>

<section class="tv-karte">
  {#if video}
    <h3><i class="fa-solid fa-film"></i> Gefunden: Video
      <button class="tv-knopf ohne symbol klein schliessen" onclick={onClose} title="Schließen"><i class="fa-solid fa-xmark"></i></button></h3>
    {#if video.id}<div class="vorschau"><img src={api.rssThumbUrl(video.id)} alt="" /></div>{/if}
    <div class="titel">{video.title}</div>
    <div class="tv-leise tv-klein">{video.channel_name} · <span class="zahl">{formatDuration(video.duration)}</span>
      {#if video.already_downloaded} · <span class="tv-zustand fertig">schon vorhanden</span>{/if}</div>

    <div class="tv-etikett abschnitt">Qualität</div>
    <div class="qualitaeten">
      <button class="tv-chip" class:aktiv={!quality} onclick={() => quality = ''}>Standard</button>
      {#each progressive as s}
        <button class="tv-chip" class:aktiv={quality === s.quality} onclick={() => quality = s.quality}
                title="Bild und Ton in einer Datei · {s.codec}">{s.quality} <span class="zahl tv-leise">{formatSize(s.file_size)}</span></button>
      {/each}
      {#each adaptive as s}
        <button class="tv-chip" class:aktiv={quality === s.quality} onclick={() => quality = s.quality}
                title="Bild, wird mit dem Ton zusammengefügt · {s.codec}">{s.quality}{s.fps ? ` ${s.fps}` : ''} <span class="zahl tv-leise">{formatSize(s.file_size)} + Ton</span></button>
      {/each}
    </div>
    <button class="tv-knopf haupt breit" onclick={onStart}><i class="fa-solid fa-download"></i> Laden ({quality || 'Standard-Qualität'})</button>

  {:else if playlist}
    <h3><i class="fa-solid fa-list-ul"></i> Gefunden: Playlist
      <button class="tv-knopf ohne symbol klein schliessen" onclick={onClose} title="Schließen"><i class="fa-solid fa-xmark"></i></button></h3>
    <div class="titel">{playlist.title}</div>
    <div class="tv-leise tv-klein">{playlist.owner || 'Unbekannt'} · <span class="zahl">{playlist.videos.length} Videos, {playlist.videos.length - missing.length} schon vorhanden</span></div>
    <button class="tv-knopf haupt breit" onclick={onPlaylistAll} disabled={missing.length === 0}>
      <i class="fa-solid fa-download"></i> {missing.length} fehlende laden
    </button>
    <div class="liste">
      {#each playlist.videos as v, idx (v.id)}
        <div class="eintrag" class:vorhanden={v.already_downloaded}>
          <span class="zahl tv-leise">{idx + 1}</span>
          <div class="text"><div class="eintrag-titel">{v.title}</div>
            <div class="tv-leise tv-klein">{v.channel_name || ''}{#if v.duration} · <span class="zahl">{formatDuration(v.duration)}</span>{/if}</div></div>
          {#if v.already_downloaded}<i class="fa-solid fa-check" style="color: var(--tv-erfolg)" title="schon vorhanden"></i>
          {:else if loadingIds.has(v.id)}<i class="fa-solid fa-spinner fa-spin"></i>
          {:else}<button class="tv-knopf ohne symbol klein" onclick={() => onPlaylistOne(v.id)} title="Laden"><i class="fa-solid fa-download"></i></button>{/if}
        </div>
      {/each}
    </div>

  {:else if channel}
    <h3><i class="fa-solid fa-tv"></i> Gefunden: Kanal
      <button class="tv-knopf ohne symbol klein schliessen" onclick={onClose} title="Schließen"><i class="fa-solid fa-xmark"></i></button></h3>
    <div class="titel">{channel.channel_name}</div>
    {#if channel.already_subscribed}
      <button class="tv-knopf breit" disabled><i class="fa-solid fa-check"></i> Schon abonniert</button>
    {:else}
      <button class="tv-knopf haupt breit" onclick={onSubscribe}><i class="fa-solid fa-rss"></i> Abonnieren</button>
    {/if}
  {/if}
</section>

<style>
  h3 .schliessen { margin-left: auto; }
  .vorschau { aspect-ratio: 16 / 9; overflow: hidden; background: var(--tv-mulde); border-radius: var(--tv-ecke-klein); margin-bottom: var(--tv-a3); }
  .vorschau img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .titel { font-weight: 600; margin-bottom: 4px; }
  .abschnitt { display: block; margin: var(--tv-a4) 0 var(--tv-a2); }
  .qualitaeten { display: flex; flex-wrap: wrap; gap: var(--tv-a2); margin-bottom: var(--tv-a3); }
  .breit { width: 100%; margin-top: var(--tv-a3); }
  .liste { margin-top: var(--tv-a3); display: flex; flex-direction: column; gap: 2px; }
  .eintrag { display: grid; grid-template-columns: 28px minmax(0, 1fr) auto; gap: var(--tv-a2); align-items: center; padding: 6px var(--tv-a2); border-radius: var(--tv-ecke-klein); }
  .eintrag:hover { background: var(--tv-karte); }
  .eintrag.vorhanden { opacity: 0.6; }
  .eintrag .text { min-width: 0; }
  .eintrag-titel { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: var(--tv-gr-klein); }
</style>

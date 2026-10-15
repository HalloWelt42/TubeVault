<!--
  Ein noch nicht geladenes Video eines Abos: Ansehen (Wiedergabe von der
  Quelle) oder Laden in die Warteschlange.
-->
<script>
  import { api } from '../../api/client.js';
  import { navigate } from '../../router/router.js';
  import { toast } from '../../stores/notifications.js';
  import { formatDate, formatDuration } from '../../utils/format.js';
  import LanguageLabel from '../common/LanguageLabel.svelte';
  import Marked from './Marked.svelte';

  /** hit: FeedHit (services/search/models) */
  let { hit, terms = [] } = $props();
  let queued = $state(false);
  let busy = $state(false);

  async function load() {
    busy = true;
    try {
      await api.addDownload({ url: `https://www.youtube.com/watch?v=${hit.video_id}` });
      queued = true;
      toast.success(`In der Warteschlange: ${hit.title}`);
    } catch (e) { toast.error(e.message); }
    busy = false;
  }
</script>

<div class="treffer">
  <div class="bild">
    <img src={api.rssThumbUrl(hit.video_id)} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
    {#if hit.duration}<span class="dauer zahl">{formatDuration(hit.duration)}</span>{/if}
  </div>
  <div class="text">
    <div class="titel"><Marked text={hit.title} {terms} /></div>
    <div class="zeile">
      <span class="kanal">{hit.channel_name || ''}</span>
      {#if hit.published}<span class="zahl">{formatDate(hit.published)}</span>{/if}
      <LanguageLabel code={hit.language} source={hit.language_source} />
      {#if hit.meaning}<span class="marke sinn" title="Kein Suchwort im Text - inhaltlich verwandt"><i class="fa-solid fa-wand-magic-sparkles"></i> sinngemäß</span>{/if}
      <span class="leise">noch nicht geladen</span>
    </div>
  </div>
  <div class="aktionen">
    <button class="tv-knopf klein" onclick={() => navigate(`/watch/${hit.video_id}`)} title="Von der Quelle abspielen, ohne zu laden">
      <i class="fa-solid fa-play"></i> Ansehen</button>
    <button class="tv-knopf klein haupt" onclick={load} disabled={busy || queued || hit.in_queue}
            title={queued || hit.in_queue ? 'Liegt schon in der Warteschlange' : 'In die Warteschlange legen'}>
      <i class="fa-solid {queued || hit.in_queue ? 'fa-clock' : busy ? 'fa-spinner fa-spin' : 'fa-download'}"></i>
      {queued || hit.in_queue ? 'Wartet' : 'Laden'}</button>
  </div>
</div>

<style>
  .treffer { display: grid; grid-template-columns: 168px minmax(0, 1fr) auto; gap: var(--tv-a3); align-items: start;
             padding: var(--tv-a2); border-radius: var(--tv-ecke); }
  .treffer:hover { background: var(--tv-flaeche); }
  .bild { position: relative; aspect-ratio: 16 / 9; border-radius: var(--tv-ecke); overflow: hidden; background: var(--tv-mulde); }
  .bild img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .dauer { position: absolute; right: 5px; bottom: 6px; padding: 1px 6px; border-radius: var(--tv-ecke-klein);
           background: var(--tv-schleier); font-size: var(--tv-gr-marke); }
  .text { min-width: 0; }
  .titel { font-weight: 600; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2;
           -webkit-box-orient: vertical; overflow: hidden; }
  .zeile { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; margin-top: 3px;
           font-size: var(--tv-gr-klein); color: var(--tv-text-2); }
  .leise { color: var(--tv-text-3); }
  .marke { display: inline-flex; align-items: center; gap: 4px; height: 22px; padding: 0 6px; border-radius: var(--tv-ecke-klein);
           background: var(--tv-karte-2); font-size: var(--tv-gr-marke); }
  .marke.sinn { color: var(--tv-info); }
  .aktionen { display: flex; gap: 6px; }
</style>

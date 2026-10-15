<!--
  Vorschau des gewählten Treffers (rechte Spalte der Suche): Bild, Angaben,
  Abspielen, in eine Playlist, Kanal; darunter alle Fundstellen mit Zeit
  (Kapitel, Gesagtes) und ein Ausschnitt der Beschreibung.
-->
<script>
  import { api } from '../../api/client.js';
  import { navigate } from '../../router/router.js';
  import { formatDate, formatDuration } from '../../utils/format.js';
  import { ORIGINS } from '../../constants/searchChoices.js';
  import AddToPlaylistDialog from '../common/AddToPlaylistDialog.svelte';
  import LanguageLabel from '../common/LanguageLabel.svelte';
  import Marked from './Marked.svelte';

  /** hit: VideoHit; onplay(hit, start?) */
  let { hit, q, terms = [], onplay } = $props();

  let detail = $state(null);
  let playlistVideo = $state(null);
  let run = 0;

  async function load(videoId, text) {
    const mine = ++run;
    detail = null;
    try {
      const spots = await api.searchSpots(videoId, text);
      if (mine === run) detail = spots;
    } catch { if (mine === run) detail = { spots: [], description: null, title_hit: false }; }
  }

  $effect(() => { load(hit.id, q); });
</script>

<div class="vorschau">
  <button class="bild" onclick={() => onplay(hit)} title="Abspielen">
    <img src={api.thumbnailUrl(hit.id)} alt="" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
    <span class="spiel"><i class="fa-solid fa-play"></i></span>
  </button>
  <h3><Marked text={hit.title} {terms} /></h3>
  <div class="meta">
    <span>{hit.channel_name || ''}</span>
    {#if hit.duration}<span class="zahl">{formatDuration(hit.duration)}</span>{/if}
    {#if hit.upload_date}<span class="zahl">{formatDate(hit.upload_date)}</span>{/if}
    <LanguageLabel code={hit.language} source={hit.language_source} />
    {#if hit.is_archived}<span><i class="fa-solid fa-box-archive"></i> Archiv</span>{/if}
  </div>
  <div class="knoepfe">
    <button class="tv-knopf haupt" onclick={() => onplay(hit)}><i class="fa-solid fa-play"></i> Abspielen</button>
    <button class="tv-knopf" onclick={() => playlistVideo = hit.id}><i class="fa-solid fa-list"></i> In Playlist</button>
    {#if hit.channel_id}
      <button class="tv-knopf symbol" onclick={() => navigate(`/channel/${hit.channel_id}`)} title="Kanal öffnen" aria-label="Kanal öffnen">
        <i class="fa-solid fa-tv"></i></button>
    {/if}
  </div>

  {#if detail}
    {#if detail.spots.length || detail.title_hit}
      <div class="etikett">Fundstellen <span class="zahl">{detail.spots.length + (detail.title_hit ? 1 : 0)}</span></div>
      {#if detail.title_hit}
        <div class="fundstelle"><span class="zeit">Titel</span><span><Marked text={hit.title} {terms} /></span><span></span></div>
      {/if}
      {#each detail.spots as spot (spot.kind + spot.start)}
        <div class="fundstelle">
          <span class="zeit zahl">{formatDuration(Math.floor(spot.start))}</span>
          <span><Marked text={spot.text} {terms} />
            <span class="art">{spot.kind === 'kapitel' ? 'Kapitel' : ORIGINS[spot.origin] || 'Gesagtes'}</span></span>
          <button onclick={() => onplay(hit, spot.start)} title="Ab hier abspielen" aria-label="Ab hier abspielen">
            <i class="fa-solid fa-play"></i></button>
        </div>
      {/each}
    {/if}
    {#if detail.description}
      <div class="etikett">Beschreibung</div>
      <div class="beschreibung"><Marked text={detail.description} {terms} /></div>
    {/if}
  {:else}
    <div class="laedt"><i class="fa-solid fa-spinner fa-spin"></i> Fundstellen werden gesucht</div>
  {/if}
</div>

<AddToPlaylistDialog bind:videoId={playlistVideo} />

<style>
  .vorschau { padding: var(--tv-a4); border-radius: var(--tv-ecke); background: var(--tv-flaeche); }
  .bild { position: relative; display: block; width: 100%; padding: 0; border: 0; aspect-ratio: 16 / 9; border-radius: var(--tv-ecke);
          overflow: hidden; background: var(--tv-mulde); cursor: pointer; }
  .bild img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .spiel { position: absolute; inset: 0; display: grid; place-items: center; font-size: 30px; color: var(--tv-text);
           background: rgba(0, 0, 0, 0.35); opacity: 0; transition: opacity var(--tv-schnell); }
  .bild:hover .spiel { opacity: 1; }
  h3 { margin: var(--tv-a3) 0 4px; font-size: 19px; line-height: 1.3; }
  .meta { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; font-size: var(--tv-gr-klein); color: var(--tv-text-2); }
  .knoepfe { display: flex; gap: var(--tv-a2); margin: var(--tv-a3) 0; }
  .etikett { margin: var(--tv-a4) 0 var(--tv-a2); font-size: var(--tv-gr-marke); font-weight: 700; letter-spacing: 0.1em;
             text-transform: uppercase; color: var(--tv-text-3); }
  .fundstelle { display: grid; grid-template-columns: 64px minmax(0, 1fr) 34px; gap: var(--tv-a2); align-items: center;
                padding: 6px 0; font-size: var(--tv-gr-klein); }
  .zeit { color: var(--tv-akzent); font-weight: 600; }
  .art { display: block; font-size: var(--tv-gr-marke); color: var(--tv-text-3); }
  .fundstelle button { width: 34px; height: 34px; border: 0; border-radius: var(--tv-ecke); background: var(--tv-karte-3);
                       color: var(--tv-text); cursor: pointer; }
  .fundstelle button:hover { background: var(--tv-akzent); color: var(--tv-akzent-text); }
  .beschreibung { font-size: var(--tv-gr-klein); color: var(--tv-text-2); line-height: 1.5; }
  .laedt { margin-top: var(--tv-a4); font-size: var(--tv-gr-klein); color: var(--tv-text-3); }
</style>

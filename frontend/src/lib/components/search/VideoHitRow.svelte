<!--
  Ein Video in der Trefferliste: Bild mit Dauer und Stand, Titel mit
  Hervorhebung, Kanal und Datum, Marken wo getroffen (Titel, Kapitel ...),
  darunter die Fundstellen mit Zeit (Gesagtes, Kapitel). Ein Klick wählt den
  Treffer für die Vorschau, der Abspielknopf startet ihn, eine Fundstelle
  startet an ihrer Zeit.
-->
<script>
  import { api } from '../../api/client.js';
  import { formatDate, formatDuration } from '../../utils/format.js';
  import { FOUND, ORIGINS } from '../../constants/searchChoices.js';
  import LanguageLabel from '../common/LanguageLabel.svelte';
  import Marked from './Marked.svelte';

  /** hit: VideoHit (services/search/models); onplay(hit, start?) */
  let { hit, terms = [], selected = false, onselect = () => {}, onplay } = $props();

  const SEEN_FROM_S = 5;
  let seen = $derived(hit.duration && hit.last_position > SEEN_FROM_S ? Math.min(1, hit.last_position / hit.duration) : 0);
</script>

<div class="treffer" class:gewaehlt={selected} role="option" aria-selected={selected} tabindex="-1"
     onclick={() => onselect(hit)} onkeydown={(e) => e.key === 'Enter' && onplay(hit)}
     ondblclick={() => onplay(hit)} data-treffer={hit.id}>
  <div class="bild">
    <img src={api.thumbnailUrl(hit.id)} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
    {#if hit.duration}<span class="dauer zahl">{formatDuration(hit.duration)}</span>{/if}
    {#if seen}<span class="stand"><b style:width="{Math.round(seen * 100)}%"></b></span>{/if}
  </div>
  <div class="text">
    <div class="titel"><Marked text={hit.title} {terms} /></div>
    <div class="zeile">
      <span class="kanal">{hit.channel_name || 'Unbekannt'}</span>
      {#if hit.upload_date}<span class="zahl">{formatDate(hit.upload_date)}</span>{/if}
      <LanguageLabel code={hit.language} source={hit.language_source} />
      {#if hit.is_archived}<span class="marke"><i class="fa-solid fa-box-archive"></i> Archiv</span>{/if}
      {#if hit.source === 'local' || hit.source === 'imported'}<span class="marke"><i class="fa-solid fa-film"></i> Eigenes</span>{/if}
      {#if hit.meaning}<span class="marke sinn" title="Kein Suchwort im Text - inhaltlich verwandt"><i class="fa-solid fa-wand-magic-sparkles"></i> sinngemäß</span>{/if}
    </div>
    {#if hit.found.length && !hit.spots.length}
      <div class="fund">
        {#each hit.found as place (place.where)}
          <span title="Gefunden in: {FOUND[place.where]?.label}">
            <i class="fa-solid {FOUND[place.where]?.icon}"></i>{place.count ? `${place.count} ` : ''}{FOUND[place.where]?.label}</span>
        {/each}
      </div>
    {/if}
    {#if hit.spots.length}
      <div class="stellen">
        {#each hit.spots as spot (spot.kind + spot.start)}
          <button class="stelle" onclick={(e) => { e.stopPropagation(); onplay(hit, spot.start); }}
                  title="Ab {formatDuration(Math.floor(spot.start))} abspielen">
            <span class="zeit zahl">{formatDuration(Math.floor(spot.start))}</span>
            <span><Marked text={spot.text} {terms} />
              {#if spot.origin}<span class="herkunft"> · {ORIGINS[spot.origin] || spot.origin}</span>{/if}</span>
          </button>
        {/each}
        {#if hit.spot_count > hit.spots.length}
          <span class="weitere">und <span class="zahl">{hit.spot_count - hit.spots.length}</span> weitere Stellen</span>
        {/if}
      </div>
    {/if}
  </div>
  <button class="spiel" onclick={(e) => { e.stopPropagation(); onplay(hit); }} title="Abspielen" aria-label="Abspielen">
    <i class="fa-solid fa-play"></i></button>
</div>

<style>
  .treffer { display: grid; grid-template-columns: 168px minmax(0, 1fr) 44px; gap: var(--tv-a3); align-items: start;
             padding: var(--tv-a2); border-radius: var(--tv-ecke); cursor: pointer; outline: 0; }
  .treffer:hover { background: var(--tv-flaeche); }
  .treffer.gewaehlt { background: var(--tv-karte); box-shadow: inset 0 0 0 1px rgba(var(--tv-akzent-rgb), 0.45); }
  .bild { position: relative; aspect-ratio: 16 / 9; border-radius: var(--tv-ecke); overflow: hidden; background: var(--tv-mulde); }
  .bild img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .dauer { position: absolute; right: 5px; bottom: 6px; padding: 1px 6px; border-radius: var(--tv-ecke-klein);
           background: var(--tv-schleier); font-size: var(--tv-gr-marke); }
  .stand { position: absolute; left: 0; right: 0; bottom: 0; height: 4px; background: rgba(255, 255, 255, 0.2); }
  .stand b { position: absolute; left: 0; top: 0; bottom: 0; background: var(--tv-akzent); }
  .text { min-width: 0; }
  .titel { font-weight: 600; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2;
           -webkit-box-orient: vertical; overflow: hidden; }
  .zeile { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; margin-top: 3px;
           font-size: var(--tv-gr-klein); color: var(--tv-text-2); }
  .kanal { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 260px; }
  .marke { display: inline-flex; align-items: center; gap: 4px; height: 22px; padding: 0 6px; border-radius: var(--tv-ecke-klein);
           background: var(--tv-karte-2); font-size: var(--tv-gr-marke); }
  .marke.sinn { color: var(--tv-info); }
  .fund { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 6px; }
  .fund span { display: inline-flex; align-items: center; gap: 5px; height: 24px; padding: 0 7px; border-radius: var(--tv-ecke-klein);
               background: var(--tv-karte-2); font-size: var(--tv-gr-marke); color: var(--tv-text-2); }
  .fund i { color: var(--tv-akzent); font-size: 12px; }
  .stellen { display: flex; flex-direction: column; gap: 4px; margin-top: 6px; }
  .stelle { display: grid; grid-template-columns: 64px minmax(0, 1fr); gap: var(--tv-a2); align-items: baseline; padding: 6px 8px;
            border: 0; border-radius: var(--tv-ecke-klein); background: var(--tv-flaeche); color: var(--tv-text-2);
            font: inherit; font-size: var(--tv-gr-klein); text-align: left; cursor: pointer; }
  .stelle:hover { background: var(--tv-karte-2); color: var(--tv-text); }
  .zeit { color: var(--tv-akzent); font-weight: 600; }
  .herkunft, .weitere { font-size: var(--tv-gr-marke); color: var(--tv-text-3); }
  .weitere { padding-left: 8px; }
  .spiel { width: 44px; height: 44px; border: 0; border-radius: var(--tv-ecke); background: var(--tv-akzent);
           color: var(--tv-akzent-text); font-size: 16px; cursor: pointer; }
  .spiel:hover { background: var(--tv-akzent-hell); }
</style>

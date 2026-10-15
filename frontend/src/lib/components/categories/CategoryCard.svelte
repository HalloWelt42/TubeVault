<!--
  Kachel einer Kategorie (Entwurf mockups/kategorien.html): Farbstreifen,
  Bildcollage aus den ersten Videos, beim Überfahren Abspielen, Zufällig und
  Menü; Name mit Farbe, Kennzahlen, Beschreibung und die Regeln als Chips.
-->
<script>
  import { api } from '../../api/client.js';
  import { totalTime } from '../../utils/collection.js';
  import RuleChips from './RuleChips.svelte';

  let { card, onOpen, onPlay, onShuffle, onMenu, onRules } = $props();

  const hideImage = (event) => { event.currentTarget.style.visibility = 'hidden'; };
</script>

<div class="kat">
  <div class="streifen" style:background={card.color}></div>
  <div class="collage">
    <button class="flaeche" onclick={onOpen} aria-label="{card.name} öffnen"></button>
    {#each card.cover_ids.slice(0, 3) as id, i (id)}
      <img class:gross={i === 0} src={api.thumbnailUrl(id)} alt="" loading="lazy" onerror={hideImage} />
    {/each}
    {#if !card.cover_ids.length}<i class="fa-solid fa-folder-open platzhalter"></i>{/if}
  </div>
  <div class="los">
    {#if card.video_count}
      <button class="spielen" onclick={onPlay}><i class="fa-solid fa-play"></i> Abspielen</button>
      <button onclick={onShuffle} title="Zufällig abspielen"><i class="fa-solid fa-shuffle"></i></button>
    {/if}
    <button onclick={onMenu} title="Mehr: Regeln, Als Ton hören, Umbenennen, Löschen"><i class="fa-solid fa-ellipsis"></i></button>
  </div>
  <button class="text" onclick={onOpen}>
    <span class="name"><span class="punkt" style:background={card.color}></span><span class="n">{card.name}</span></span>
    <span class="meta">
      <span class="zahl">{card.video_count.toLocaleString('de-DE')}</span> {card.video_count === 1 ? 'Video' : 'Videos'}
      {#if card.duration} · <span class="zahl">{totalTime(card.duration)}</span>{/if}
      {#if card.finished_count} · <span class="zahl">{card.finished_count.toLocaleString('de-DE')}</span> gesehen{/if}
      {#if card.description} · {card.description}{/if}
    </span>
  </button>
  {#if card.rules.length}
    <div class="regeln"><RuleChips rules={card.rules} onOpen={onRules} /></div>
  {/if}
</div>

<style>
  .kat { position: relative; min-width: 0; background: var(--tv-karte); border-radius: var(--tv-ecke); overflow: hidden;
         outline: 1px solid var(--tv-rand); outline-offset: -1px; }
  .streifen { height: 6px; }
  .collage { position: relative; display: grid; grid-template-columns: 2fr 1fr; grid-template-rows: 1fr 1fr; gap: 2px;
             aspect-ratio: 16 / 7; background: var(--tv-mulde); }
  .collage img { width: 100%; height: 100%; min-height: 0; object-fit: cover; display: block; }
  .collage img.gross { grid-row: 1 / 3; }
  .flaeche { position: absolute; inset: 0; z-index: 1; border: 0; padding: 0; background: none; cursor: pointer; }
  .platzhalter { grid-row: 1 / 3; grid-column: 1 / 3; align-self: center; justify-self: center; font-size: 34px; color: var(--tv-text-3); }
  .los { position: absolute; right: 10px; top: 16px; z-index: 2; display: flex; gap: 6px; opacity: 0;
         transition: opacity var(--tv-schnell); }
  .kat:hover .los, .kat:focus-within .los { opacity: 1; }
  .los button { height: 36px; min-width: 36px; padding: 0 10px; border: 0; border-radius: var(--tv-ecke); background: var(--tv-schleier);
                color: var(--tv-text); font: inherit; font-weight: 700; cursor: pointer; display: inline-flex; align-items: center;
                justify-content: center; gap: 6px; }
  .los button.spielen { background: var(--tv-akzent); color: var(--tv-akzent-text); }
  .text { display: block; width: 100%; padding: var(--tv-a3) var(--tv-a4) 0; border: 0; background: none; color: var(--tv-text);
          font: inherit; text-align: left; cursor: pointer; }
  .text:last-child { padding-bottom: var(--tv-a4); }
  .name { display: flex; align-items: center; gap: var(--tv-a2); font-weight: 700; font-size: 18px; min-width: 0; }
  .name .n { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .text:hover .n { color: var(--tv-akzent); }
  .punkt { width: 12px; height: 12px; border-radius: var(--tv-ecke); flex: none; }
  .meta { display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
          margin-top: 2px; font-size: var(--tv-gr-klein); color: var(--tv-text-2); }
  .regeln { display: flex; flex-wrap: wrap; gap: 6px; padding: var(--tv-a2) var(--tv-a4) var(--tv-a4); }
</style>

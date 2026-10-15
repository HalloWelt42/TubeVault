<!--
  Kleine Videokachel der Übersicht: Bild mit Dauer und, wo es einen gibt,
  dem Stand (wie weit gesehen); darunter Titel und Kanal mit Sprach-Label.
  Für Bibliothek, Verlauf und Feed gleichermaßen; was ein Klick öffnet,
  entscheidet der Aufrufer.
-->
<script>
  import LanguageLabel from '../common/LanguageLabel.svelte';
  import { formatDuration } from '../../utils/format.js';

  /** progress: Anteil 0..1 oder null (kein Stand) */
  let { image, title, subtitle = '', duration = 0, progress = null, language = null, languageSource = null, onopen } = $props();
</script>

<button class="kachel" onclick={onopen} title={title}>
  <span class="bild">
    <img src={image} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
    <span class="spiel"><i class="fa-solid fa-play"></i></span>
    {#if duration}<span class="dauer zahl">{formatDuration(Math.floor(duration))}</span>{/if}
    {#if progress !== null}<span class="stand"><b style:width="{Math.round(Math.min(1, progress) * 100)}%"></b></span>{/if}
  </span>
  <span class="titel">{title}</span>
  <span class="unter"><span class="kanal">{subtitle}</span><LanguageLabel code={language} source={languageSource} /></span>
</button>

<style>
  .kachel { display: flex; flex-direction: column; gap: 6px; min-width: 0; padding: 0; border: 0; background: none;
            color: var(--tv-text); font: inherit; text-align: left; cursor: pointer; }
  .bild { position: relative; display: block; aspect-ratio: 16 / 9; border-radius: var(--tv-ecke); overflow: hidden; background: var(--tv-mulde); }
  .bild img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .spiel { position: absolute; inset: 0; display: grid; place-items: center; font-size: 26px; color: var(--tv-text);
           background: rgba(0, 0, 0, 0.35); opacity: 0; transition: opacity var(--tv-schnell); }
  .kachel:hover .spiel, .kachel:focus-visible .spiel { opacity: 1; }
  .dauer { position: absolute; right: 6px; bottom: 8px; padding: 1px 6px; border-radius: var(--tv-ecke-klein);
           background: var(--tv-schleier); font-size: var(--tv-gr-marke); }
  .stand { position: absolute; left: 0; right: 0; bottom: 0; height: 4px; background: rgba(255, 255, 255, 0.2); }
  .stand b { position: absolute; left: 0; top: 0; bottom: 0; background: var(--tv-akzent); }
  .titel { font-weight: 600; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2;
           -webkit-box-orient: vertical; overflow: hidden; }
  .unter { display: flex; align-items: center; gap: 6px; min-width: 0; font-size: var(--tv-gr-klein); color: var(--tv-text-2); }
  .kanal { min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>

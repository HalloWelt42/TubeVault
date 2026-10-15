<!--
  TubeVault - Sprach-Label: Flagge und Kürzel ("🇬🇧 EN"), Herkunft im Tooltip.
  Erscheint nur bei Sprachen außer der Hauptsprache (Einstellung), bei
  unbekannter Sprache gar nicht. Regeln und Texte: lib/utils/language.js.
  art: "bild" auf Vorschaubildern (wie die übrigen Marken dort), "zeile" in
  Textzeilen und auf Kanälen.
-->
<script>
  import { settings } from '../../stores/settings.js';
  import { languageCatalog, languageLabel, loadLanguages, mainLanguage } from '../../utils/language.js';

  // channel: Sprache eines Kanals (Mehrheit seiner Videos) statt eines Videos
  let { code = null, source = null, art = 'zeile', channel = false } = $props();

  loadLanguages();   // einmal für alle Labels
  const label = $derived(languageLabel($languageCatalog, code, source, mainLanguage($settings), channel));
</script>

{#if label}
  <span class="sprache {art}" class:gemischt={label.mixed} title={label.title}>
    {#if label.flag}<span class="flagge" aria-hidden="true">{label.flag}</span>{/if}
    {#if label.mixed}<i class="fa-solid fa-language" aria-hidden="true"></i>{/if}
    <span class:zahl={!label.mixed}>{label.short}</span>
  </span>
{/if}

<style>
  .sprache {
    display: inline-flex; align-items: center; gap: 5px; height: 22px; padding: 0 7px; flex: none;
    border-radius: var(--tv-ecke); font-size: var(--tv-gr-marke); font-weight: 600; line-height: 1;
    white-space: nowrap; cursor: default;
  }
  .sprache .zahl { letter-spacing: 0.06em; }
  .flagge { font-size: 14px; line-height: 1; }

  /* Auf dem Vorschaubild: wie Short, Live, Tonspur (VideoCard .art) */
  .sprache.bild { height: 24px; background: var(--tv-schleier); color: var(--tv-text); }
  /* In Zeilen und auf Kanälen: zurückhaltend */
  .sprache.zeile { background: var(--tv-karte-2); color: var(--tv-text-2); }
  .sprache.gemischt { font-weight: 500; }
</style>

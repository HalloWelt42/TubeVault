/**
 * TubeVault - Sekundenangaben von Medienelementen
 *
 * HTMLMediaElement.duration ist vor den Metadaten NaN und, je nach Format
 * und Browser, Infinity, solange die Länge unbekannt ist (z.B. FLAC ohne
 * Längenangabe, Ogg oder Opus ohne Index). Infinity rutscht durch
 * jedes `||`, und JSON macht aus beiden null. Wer Stelle oder Dauer
 * übernimmt oder weitergibt, nimmt sie deshalb nur über diese Hilfe.
 */

/** Die erste brauchbare Angabe (endlich und größer als null), sonst 0 */
export function knownSeconds(...candidates) {
  for (const value of candidates) {
    if (Number.isFinite(value) && value > 0) return value;
  }
  return 0;
}

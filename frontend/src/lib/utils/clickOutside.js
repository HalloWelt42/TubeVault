/**
 * TubeVault - Lag ein Klick innerhalb eines Bereichs?
 *
 * Für alles, was sich bei einem Klick daneben schließt (Auswahlkarten,
 * Aufklapplisten). Geprüft wird der Weg des Ereignisses zum Klickzeitpunkt
 * (composedPath), nicht der heutige Ort des Ziels: Ersetzt die Oberfläche
 * das geklickte Element noch während des Klicks (ein Knopf wird zum Spieler,
 * ein Eintrag verschwindet aus der Liste), hängt e.target nicht mehr im
 * Dokument, und closest() oder contains() melden "daneben".
 * © HalloWelt42 - Private Nutzung
 */

/**
 * @param {Event} event
 * @param {...(Element|string|null)} areas Elemente oder CSS-Auswahl
 */
export function clickedInside(event, ...areas) {
  return event.composedPath().some((node) => areas.some((area) =>
    typeof area === 'string' ? node instanceof Element && node.matches(area) : area != null && node === area));
}

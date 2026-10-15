// Farbton eines Covers für den dunklen Verlauf hinter dem Spieler: die
// mittlere Farbe des Bildes, so weit abgedunkelt, dass heller Text darauf
// gut lesbar bleibt.

const SAMPLE = 12;        // Kantenlänge der verkleinerten Probe in Bildpunkten
const LEVEL = 58;         // hellster Farbanteil des Ergebnisses (0..255)

/** Mittlere Farbe aus RGBA-Bildpunkten, abgedunkelt: "rgb(r, g, b)"; ohne deckende Punkte null */
export function tintFromPixels(data, level = LEVEL) {
  let r = 0, g = 0, b = 0, n = 0;
  for (let i = 0; i + 3 < data.length; i += 4) {
    if (data[i + 3] < 128) continue;   // durchsichtige Punkte zählen nicht
    r += data[i]; g += data[i + 1]; b += data[i + 2]; n += 1;
  }
  if (!n) return null;
  const mean = [r / n, g / n, b / n];
  const scale = level / Math.max(1, ...mean);
  const [cr, cg, cb] = mean.map((value) => Math.round(Math.min(level, value * scale)));
  return `rgb(${cr}, ${cg}, ${cb})`;
}

/** Farbton eines Bildes laden; null, wenn es nicht lesbar ist */
export function loadTint(url) {
  return new Promise((resolve) => {
    if (!url || typeof Image === 'undefined') return resolve(null);
    const image = new Image();
    image.crossOrigin = 'anonymous';
    image.onload = () => {
      try {
        const canvas = document.createElement('canvas');
        canvas.width = canvas.height = SAMPLE;
        const context = canvas.getContext('2d', { willReadFrequently: true });
        context.drawImage(image, 0, 0, SAMPLE, SAMPLE);
        resolve(tintFromPixels(context.getImageData(0, 0, SAMPLE, SAMPLE).data));
      } catch { resolve(null); }   // fremdes Bild ohne Freigabe
    };
    image.onerror = () => resolve(null);
    image.src = url;
  });
}

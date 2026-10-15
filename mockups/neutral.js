// Entwürfe ohne fremde Bilder: Mit ?neutral in der Adresse ersetzt diese Datei
// alle Vorschaubilder vom Pi durch erzeugte Farbflächen. So entstehen die Bilder
// für die README und für mockups/bilder (das Repo ist öffentlich).
const AKTIV = new URLSearchParams(location.search).has('neutral');
const QUELLE = '192.168.178.49';

function farbton(text) {
  let h = 7;
  for (const zeichen of text) h = (h * 31 + zeichen.charCodeAt(0)) % 360;
  return h;
}

export function flaeche(schluessel) {
  const h = farbton(schluessel);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 90" preserveAspectRatio="xMidYMid slice">`
    + `<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">`
    + `<stop offset="0" stop-color="hsl(${h},42%,34%)"/><stop offset="1" stop-color="hsl(${(h + 50) % 360},48%,14%)"/>`
    + `</linearGradient></defs><rect width="160" height="90" fill="url(#g)"/>`
    + `<circle cx="${30 + (h % 100)}" cy="${30 + (h % 40)}" r="34" fill="hsl(${(h + 180) % 360},55%,62%)" opacity=".16"/>`
    + `<rect x="${10 + (h % 60)}" y="58" width="70" height="8" rx="2" fill="#fff" opacity=".12"/></svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function tausche(bild) {
  const src = bild.getAttribute('src') || '';
  if (bild.dataset.neutral || !src.includes(QUELLE)) return;
  bild.dataset.neutral = '1';
  bild.src = flaeche(src);
}

if (AKTIV) {
  const alle = () => document.querySelectorAll('img').forEach(tausche);
  new MutationObserver(alle).observe(document.documentElement,
    { subtree: true, childList: true, attributes: true, attributeFilter: ['src'] });
  alle();
}

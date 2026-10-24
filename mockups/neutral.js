// Herkunft der Vorschaubilder in den Entwürfen. Die Entwürfe nennen nur die
// Beispieladresse BEISPIEL (das Repo ist öffentlich). Mit ?quelle=http://<rechner>:8031
// in der Adresse kommen die Bilder vom eigenen TubeVault (der Browser merkt sich
// die Quelle); ohne Quelle oder mit ?neutral ersetzt diese Datei sie durch
// erzeugte Farbflächen. So entstehen die Bilder für die README und mockups/bilder.
export const BEISPIEL = 'http://tubevault.local:8031';
const MERKER = 'tubevault-entwurf-quelle';

function quelle() {
  const angabe = new URLSearchParams(location.search).get('quelle');
  try {
    if (angabe) localStorage.setItem(MERKER, angabe.replace(/\/+$/, ''));
    return localStorage.getItem(MERKER);
  } catch {
    return angabe ? angabe.replace(/\/+$/, '') : null;
  }
}

const ECHT = new URLSearchParams(location.search).has('neutral') ? null : quelle();
// Anfang der Bildadressen für Entwürfe, die sie selbst zusammensetzen
export const QUELLE = ECHT || BEISPIEL;

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
  if (!src.startsWith(BEISPIEL)) return;
  bild.src = ECHT ? ECHT + src.slice(BEISPIEL.length) : flaeche(src);
}

const alle = () => document.querySelectorAll('img').forEach(tausche);
new MutationObserver(alle).observe(document.documentElement,
  { subtree: true, childList: true, attributes: true, attributeFilter: ['src'] });
alle();

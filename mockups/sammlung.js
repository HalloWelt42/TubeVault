// TubeVault – Sammlungen: gemeinsame Bausteine der Entwürfe Favoriten,
// Playlists und Verlauf. Echte Beispieldaten vom TubeVault (Stand 15.10.2026).
import { vorschau, dauer } from './gemeinsam.js';

// Favoriten "Standard" (Ausschnitt, Reihenfolge wie gespeichert)
export const FAVORITEN = [
  { id: 'dQw4w9WgXcQ', titel: 'Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster)', kanal: 'Rick Astley', dauer: 213, stand: 1, wann: 'vor 8 Monaten' },
  { id: 'noYNGxNKoR0', titel: "And One - M'era Luna 2025 - ARTE Concert", kanal: 'ARTE Concert', dauer: 4400, stand: 0.42, wann: 'vor 8 Monaten' },
  { id: '-CdsynN6jqU', titel: 'Build a COLOUR E-INK DASHBOARD - Weather, Calendar, Photos, News', kanal: 'DIY Machines', dauer: 1008, stand: 0, wann: 'vor 8 Monaten' },
  { id: '22RWm0sUvt8', titel: 'DietPi als Plattform für Heimdienste (CC2tv Folge 419)', kanal: 'Computer:Club2', dauer: 1890, stand: 1, wann: 'vor 8 Monaten' },
  { id: 'UNorxwlZlFk', titel: 'Atlas Airborne', kanal: 'Boston Dynamics', dauer: 98, stand: 0, wann: 'vor 8 Monaten' },
  { id: '0anQJXwJ01o', titel: 'Militärmacht Europa, Distanz zu USA: Das ist Deutschlands Strategie!', kanal: 'Konstantin Flemig - Kriegsreporter', dauer: 3712, stand: 0.18, wann: 'vor 8 Monaten' },
  { id: 'RgQPxs2ioF0', titel: 'ARD-Interview mit Selenskyj: "Ich bin bereit zu einem Treffen mit Putin"', kanal: 'tagesschau', dauer: 3430, stand: 0, wann: 'vor 7 Monaten' },
  { id: 'T-NOBKJA2to', titel: 'Pokémon mit Python simulieren - Intermediate OOP in Python (Pykemon)', kanal: 'Coding Crashkurse', dauer: 1764, stand: 0.66, wann: 'vor 7 Monaten' },
  { id: 'IX610ZJGslE', titel: 'mqmE#2 - morf quatscht nen bissel mehr - ihr könnt auch mitquatschen', kanal: 'morf', dauer: 9105, stand: 0, wann: 'vor 7 Monaten' },
  { id: 'tN8hTsJt6BU', titel: 'ALLE können programmieren! (kein Clickbait)', kanal: "c't 3003", dauer: 8849, stand: 1, wann: 'vor 7 Monaten' },
  { id: 'bRYkcW694So', titel: 'tagesshit: lebensfeindliches KI-Marketing bei der ARD', kanal: 'morf', dauer: 1164, stand: 0, wann: 'vor 7 Monaten' },
  { id: 'XdU8gaAki2c', titel: '#207 AGI, Gesellschaft und Kontrolle - mit Morf', kanal: 'Ali Hackalife', dauer: 5743, stand: 0, wann: 'vor 7 Monaten' },
];

// Playlist "Java Tutorials" (Ausschnitt)
export const JAVA = [
  { id: 'b1pDj1gx9zs', titel: 'Java Tutorial 1 - Installation vom JDK und eclipse', kanal: 'Brotcrunsher', dauer: 462, stand: 1, wann: 'vor 3 Monaten' },
  { id: 'ghDEieyOr8o', titel: 'Java Tutorial 2 - System.out.println("Abonnieren!")', kanal: 'Brotcrunsher', dauer: 531, stand: 1, wann: 'vor 3 Monaten' },
  { id: '0N5Xc3oQ2-U', titel: 'Java Tutorial 3 - Einführung von Int', kanal: 'Brotcrunsher', dauer: 636, stand: 1, wann: 'vor 3 Monaten' },
  { id: 'w3jMpo6QMJc', titel: 'Java Tutorial 4 - Noch mehr Datentypen', kanal: 'Brotcrunsher', dauer: 384, stand: 0.55, wann: 'vor 3 Monaten' },
  { id: 'K_Zdph2fT8Q', titel: 'Java Tutorial 5 - If Else oder auch... Was ist wenn?', kanal: 'Brotcrunsher', dauer: 633, stand: 0, wann: 'vor 3 Monaten' },
  { id: 'wDzz4fZQGUo', titel: 'Java Tutorial 6 - Schleifen', kanal: 'Brotcrunsher', dauer: 824, stand: 0, wann: 'vor 3 Monaten' },
];

// Playlists der Übersicht: Name, Videos, Dauer in Sekunden, gesehen, die ersten Bilder
export const PLAYLISTS = [
  { name: 'Java Tutorials', anzahl: 99, dauer: 43323, gesehen: 3, angeheftet: true, bilder: ['b1pDj1gx9zs', 'ghDEieyOr8o', '0N5Xc3oQ2-U'] },
  { name: 'Alles rund ums MATHE ABI', anzahl: 111, dauer: 76044, gesehen: 24, angeheftet: true, bilder: ['jBNuY_tEj7I', 'GtVWdeevZpw', 'sXxK-JATrc0'] },
  { name: 'UNI Mathe', anzahl: 81, dauer: 52383, gesehen: 0, bilder: ['83n4qp7nz9M', 'XEY9K6YdmBI', 'F0kvOezvS84'] },
  { name: 'Dies das', anzahl: 21, dauer: 5961, gesehen: 21, bilder: ['u5AnVeslEjE', 'gb_mpe9Ll9c', 'xrKhzXXlBU8'] },
  { name: 'Ableitung alle Regeln - Mathe', anzahl: 46, dauer: 20950, gesehen: 9, bilder: ['GtVWdeevZpw', 'tFk_dKN6Szw', '0F0CeyAbpmA'] },
  { name: 'Mehrdimensionale Analysis - Mathe', anzahl: 21, dauer: 11090, gesehen: 0, bilder: ['oWYk_g3-a4E', 'MI93ZGBb9zE', 'fF7JBjmYRSY'] },
  { name: 'TERME vereinfachen - Mathe', anzahl: 64, dauer: 29411, gesehen: 0, bilder: ['_L6wmTzod_I', 'sXxK-JATrc0', 'jBNuY_tEj7I'] },
  { name: 'Nullstellen berechnen - Mathe', anzahl: 18, dauer: 6315, gesehen: 2, bilder: ['tFk_dKN6Szw', '83n4qp7nz9M', 'XEY9K6YdmBI'] },
];

// Verlauf (letzte Einträge mit echter Uhrzeit und Stand)
export const VERLAUF = [
  { tag: 'Heute, 15.10.', eintraege: [
    { id: 'Bn4D6tnjqKY', titel: "Can AI robots turn the tide for Ukraine against Russia's $12 drones?", kanal: 'The Sun', dauer: 902, pos: 16, uhr: '03:19' },
    { id: 'rHh4JyIvHJ0', titel: 'Mind Games mit Maya: Was merkt sie sich? | Lass dich überwachen!', kanal: 'ZDF MAGAZIN ROYALE', dauer: 694, pos: 194, uhr: '01:32' },
    { id: '7fqg9-SIWfU', titel: 'OVERWERK - The Nth º [Piano] - INDEX : 01/14', kanal: 'OVERWERK', dauer: 1031, pos: 63, uhr: '01:30' },
  ] },
  { tag: 'Gestern, 14.10.', eintraege: [
    { id: 'JZKdej7uHLA', titel: 'Indien: Kindheit unter Einfluss | Doku HD | ARTE', kanal: 'ARTEde', dauer: 3321, pos: 30, uhr: '23:52' },
    { id: 'U7OUacSjohw', titel: '"Die Intelligenz-Explosion hat begonnen", OpenAI schockt Mathematiker', kanal: 'Everlast AI', dauer: 8390, pos: 520, uhr: '21:25' },
    { id: 'OT4TNJSn83c', titel: '50.000 russische VERLUSTE - und Ukraine rückt vor! Was nun?', kanal: 'Konstantin Flemig - Kriegsreporter', dauer: 1062, pos: 1062, uhr: '21:16' },
    { id: 'pvaVVmo-sao', titel: 'Kein Vibe-Coding: Wie der Open-Source Photoshop Nachbau Photopea entstand', kanal: 'predic8', dauer: 836, pos: 621, uhr: '00:09' },
  ] },
  { tag: 'Dienstag, 13.10.', eintraege: [
    { id: 'UPpDtgep9z8', titel: 'Iran’s masterclass has seen UK embarrassed and US frightened', kanal: 'The Sun', dauer: 663, pos: 159, uhr: '23:58' },
    { id: '-NhxILGhvt8', titel: 'Britain has a huge gap in its air defences, an Iron Dome would fix it', kanal: 'The Sun', dauer: 682, pos: 681, uhr: '23:48' },
    { id: '0snlFMRTgko', titel: "The droids being built to kill Russian troops, but that's not all", kanal: 'The Sun', dauer: 811, pos: 810, uhr: '22:52' },
    { id: '-gfgQfw2g_E', titel: 'Build & Train a GLM-5.3-Flash Model From Scratch with Python', kanal: 'freeCodeCamp.org', dauer: 2666, pos: 109, uhr: '21:10' },
    { id: 'e_9zm6GxclQ', titel: 'Wirtschaft - Deutsch Übersetzer gesucht | tagesshit', kanal: 'morf', dauer: 1620, pos: 558, uhr: '19:48' },
    { id: 'utYEqbWiByI', titel: 'Jan + Jan: Wann ist nie wieder? | ZDF Magazin Royale', kanal: 'ZDF MAGAZIN ROYALE', dauer: 227, pos: 227, uhr: '19:38' },
  ] },
];

// Wie weit gesehen, als Text für die Spalte "Stand"
export function standText(anteil, laenge) {
  if (anteil >= 0.97) return '<span class="zustand fertig"><i class="fa-solid fa-check"></i> Gesehen</span>';
  if (anteil > 0) return `<span class="zahl">${Math.round(anteil * 100)} %</span> · noch <span class="zahl">${dauer(Math.round(laenge * (1 - anteil)))}</span>`;
  return '<span class="schwach">Neu</span>';
}

function fort(anteil) {
  if (!anteil) return '';
  return `<div class="fort${anteil >= 0.97 ? ' fertig' : ''}"><b style="width:${Math.min(100, anteil * 100)}%"></b></div>`;
}

// Eine Zeile einer Sammlung; vorne Griff (Reihenfolge) oder Haken (Auswahl)
export function zeile(v, nr, { modus = 'normal', gewaehlt = false, klasse = '' } = {}) {
  const vorne = modus === 'auswahl'
    ? `<button class="haken" title="Auswählen"><i class="fa-${gewaehlt ? 'solid fa-square-check' : 'regular fa-square'}"></i></button>`
    : '<span class="griff" title="Ziehen zum Umordnen"><i class="fa-solid fa-grip-vertical"></i></span>';
  return `<div class="vzeile${gewaehlt ? ' gewaehlt' : ''} ${klasse}">
    ${vorne}
    <span class="nr">${nr}</span>
    <div class="vbild"><img src="${vorschau(v.id)}" alt="" loading="lazy"><span class="d">${dauer(v.dauer)}</span>${fort(v.stand)}</div>
    <div class="vtext"><div class="vtitel">${v.titel}</div>
      <div class="vmeta"><span>${v.kanal}</span><span class="zahl">${v.wann}</span></div></div>
    <div class="stand">${standText(v.stand, v.dauer)}</div>
    <div class="tun">
      <button class="spielen" title="${v.stand > 0 && v.stand < 0.97 ? 'Weiterschauen' : 'Abspielen'}"><i class="fa-solid fa-play"></i></button>
      <button title="Als Nächstes abspielen"><i class="fa-solid fa-forward"></i></button>
      <button title="Mehr"><i class="fa-solid fa-ellipsis"></i></button>
    </div>
  </div>`;
}

export function kachel(v, nr) {
  return `<div class="vkachel">
    <div class="vbild"><img src="${vorschau(v.id)}" alt="" loading="lazy"><span class="nr">${nr}</span><span class="d">${dauer(v.dauer)}</span>${fort(v.stand)}</div>
    <div class="vtitel">${v.titel}</div>
    <div class="vmeta">${v.kanal} · ${v.stand >= 0.97 ? 'gesehen' : v.stand > 0 ? `${Math.round(v.stand * 100)} % gesehen` : 'neu'}</div>
  </div>`;
}

// Umschalter für die Zustände eines Entwurfs (nicht Teil der App)
export function zustaende(liste, zeigen) {
  const box = document.createElement('div');
  box.className = 'zustaende';
  box.innerHTML = '<span>Zustand</span>';
  for (const [wert, name] of liste) {
    const b = document.createElement('button');
    b.textContent = name;
    b.onclick = () => { zeigen(wert); box.querySelectorAll('button').forEach(x => x.classList.toggle('an', x === b)); };
    box.append(b);
  }
  document.body.append(box);
  // ?zustand=auswahl öffnet einen Zustand direkt (auch für Bilder der Entwürfe)
  const suche = new URLSearchParams(location.search);
  const gewuenscht = suche.get('zustand');
  if (suche.has('bild')) box.style.display = 'none';   // ?bild: Bild ohne Umschalter (README)
  const index = Math.max(0, liste.findIndex(([wert]) => wert === gewuenscht));
  box.querySelectorAll('button')[index].click();
}

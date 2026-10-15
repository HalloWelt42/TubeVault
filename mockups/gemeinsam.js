// TubeVault – gemeinsame Blöcke der Entwürfe (Kopf, Seitenleiste, Fußleiste)
// und echte Beispieldaten aus dem Archiv. Jede Seite hat dieselbe Schale -
// geändert wird sie nur hier, damit die Entwürfe nicht auseinanderlaufen.
// Vorschaubilder kommen direkt vom TubeVault im Heimnetz (nicht im Repo).

const QUELLE = 'http://192.168.178.49:8031';
export const vorschau = (id) => `${QUELLE}/api/player/${id}/thumbnail`;

// Neueste Videos der Bibliothek (Stand 15.10.2026)
export const VIDEOS = [
  { id: 'g7br5GVYxbI', titel: 'Kurzurlaub || Ludovico Einaudi, Impulskäufe??', kanal: 'Fee', dauer: 823, groesse: 241613351, aufrufe: 236, hochgeladen: '2025-02-23', arten: ['vertont'], gesehen: 0.35 },
  { id: 'gE-ldAnPBBw', titel: 'JavaScript - Funktionen und anonyme Funktionen (Lambda-Funktionen)', kanal: 'Weitz / HAW Hamburg', dauer: 1538, groesse: 41474210, aufrufe: 2857, hochgeladen: '2017-05-13', arten: ['ki'] },
  { id: 'SGXyVJcP_Ak', titel: 'Lösung der Stundenübung zu Funktionen (JavaScript)', kanal: 'Weitz / HAW Hamburg', dauer: 665, groesse: 15595737, aufrufe: 1342, hochgeladen: '2017-05-13', arten: [] },
  { id: '_CbZMm8rOF4', titel: 'Das Buffonsche Nadelproblem', kanal: 'Weitz / HAW Hamburg', dauer: 1000, groesse: 23422895, aufrufe: 14150, hochgeladen: '2017-05-12', arten: [], gesehen: 1 },
  { id: '_-kYLnc5dWU', titel: 'CODE (Kurzfilm)', kanal: 'Alex', dauer: 658, groesse: 100240690, aufrufe: 363481, hochgeladen: '2017-06-11', arten: [] },
  { id: 'K8-o_4kue40', titel: 'Es gibt jetzt "Papier-Tablets"?! - Huawei MatePad Paper', kanal: 'Alex', dauer: 742, groesse: 73547181, aufrufe: 642660, hochgeladen: '2022-07-10', arten: [] },
  { id: 'mQU7J5CJFSI', titel: 'Mailcow Update 2025.03', kanal: 'SemperVideo', dauer: 301, groesse: 7872191, aufrufe: 8447, hochgeladen: '2025-04-10', arten: [] },
  { id: 'f-5eRfpVj-0', titel: 'Rapidshare leicht gemacht (Teil 2 von 3)', kanal: 'SemperVideo', dauer: 487, groesse: 18977880, aufrufe: 7788, hochgeladen: '2008-12-05', arten: [] },
  { id: 'EHFmCkcz8vs', titel: 'Rapidshare leicht gemacht (Teil 3 von 3)', kanal: 'SemperVideo', dauer: 449, groesse: 10179467, aufrufe: 4138, hochgeladen: '2008-12-05', arten: [] },
  { id: '9AjbEz950QQ', titel: 'Japanoschlampen #27 - Chao ist (schon wieder) krank', kanal: 'coldmirror', dauer: 182, groesse: 19113467, aufrufe: 1513459, hochgeladen: '2015-03-17', arten: [] },
  { id: 'i4yepZpTjqA', titel: 'Kunstwissenschaftliche Analyse - Daniele Negroni', kanal: 'coldmirror', dauer: 93, groesse: 19564500, aufrufe: 923829, hochgeladen: '2012-12-07', arten: [] },
  { id: 'WPcxhRC8y7U', titel: 'fett geil.', kanal: 'coldmirror', dauer: 19, groesse: 5197227, aufrufe: 445078, hochgeladen: '2012-12-18', arten: ['short'] },
];

// Entwurfsseiten je Eintrag der Seitenleiste
const SEITEN = { bibliothek: 'bibliothek.html', musik: 'musik.html', downloads: 'downloads.html', eigene: 'eigene-videos.html', einstellungen: 'einstellungen.html',
                 favoriten: 'favoriten.html', playlists: 'playlists.html', verlauf: 'verlauf.html' };

// Wie in der App (Sidebar.svelte): Symbolfarben einzelner Einträge bleiben
const NAVI = [
  ['Übersicht', 'fa-house', 'start', null],
  ['Neu bei Abos', 'fa-rss', 'feed', '95.047'],
  ['Kanäle', 'fa-tv', 'kanaele', '385'],
  ['Bibliothek', 'fa-photo-film', 'bibliothek', '32.479'],
  ['Musik', 'fa-music', 'musik', '198', '#C084FC'],
  ['Downloads', 'fa-bolt', 'downloads', null, '#FFCA28'],
  ['Playlists', 'fa-list-ul', 'playlists', '54'],
  ['Favoriten', 'fa-heart', 'favoriten', '41', '#EF5350'],
  ['Verlauf', 'fa-clock-rotate-left', 'verlauf', '963'],
  ['Kategorien', 'fa-folder', 'kategorien', '3'],
  ['Archiv', 'fa-box-archive', 'archiv', '29.355', '#A1887F'],
  ['Nachvertonung', 'fa-language', 'vertonung', null],
  ['Eigene Videos', 'fa-film', 'eigene', '14'],
  ['Suche', 'fa-magnifying-glass', 'suche', null],
];
const SYSTEM = [
  ['Statistik', 'fa-chart-simple', 'statistik', null, '#26C6DA'],
  ['Einstellungen', 'fa-gear', 'einstellungen'],
  ['Protokoll', 'fa-terminal', 'protokoll'],
  ['Verwaltung', 'fa-screwdriver-wrench', 'verwaltung'],
];

export function dauer(sekunden) {
  const h = Math.floor(sekunden / 3600), m = Math.floor(sekunden % 3600 / 60), s = sekunden % 60;
  const zwei = (n) => String(n).padStart(2, '0');
  return h ? `${h}:${zwei(m)}:${zwei(s)}` : `${m}:${zwei(s)}`;
}
export const groesse = (b) => b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${Math.round(b / 1e6)} MB`;
export const aufrufe = (n) => n >= 1e6 ? `${(n / 1e6).toFixed(1).replace('.', ',')} Mio. Aufrufe`
  : n >= 1e3 ? `${Math.round(n / 1e3)} Tsd. Aufrufe` : `${n} Aufrufe`;
export const datum = (iso) => iso.split('-').reverse().join('.');
const ART_NAME = { short: 'Short', live: 'Live', musik: 'Musik', vertont: 'Deutsch', ki: 'KI-Text' };

export function kachel(v) {
  return `<a class="kachel" href="wiedergabe.html">
    <div class="bild">
      <img src="${vorschau(v.id)}" alt="" loading="lazy">
      ${v.arten.length ? `<div class="arten">${v.arten.map(a => `<span class="art ${a}">${ART_NAME[a]}</span>`).join('')}</div>` : ''}
      <span class="dauer">${dauer(v.dauer)}</span>
      ${v.gesehen ? `<div class="gesehen"><b style="width:${v.gesehen * 100}%"></b></div>` : ''}
    </div>
    <div class="kachel-text">
      <div class="kachel-titel">${v.titel}</div>
      <div class="kachel-meta"><span class="kanal">${v.kanal}</span><span class="zahl">${aufrufe(v.aufrufe)}</span><span class="zahl">${datum(v.hochgeladen)}</span></div>
    </div>
  </a>`;
}

function schale(aktiv) {
  const navi = ([name, symbol, schluessel, zahl, farbe]) =>
    `<a class="navi${schluessel === aktiv ? ' aktiv' : ''}" href="${SEITEN[schluessel] || '#'}">
      <i class="fa-solid ${symbol}"${farbe ? ` style="--symbolfarbe: ${farbe}"` : ''}></i>${name}${zahl ? `<span class="zaehler">${zahl}</span>` : ''}</a>`;
  document.querySelector('[data-block="kopf"]').outerHTML = `
    <header class="kopf">
      <div class="marke"><span class="marke-zeichen"><i class="fa-solid fa-play"></i></span>TubeVault</div>
      <label class="suche"><i class="fa-solid fa-magnifying-glass"></i><input placeholder="Bibliothek, Transkripte und Kanäle durchsuchen"></label>
      <div class="kopf-aktionen">
        <button class="knopf ohne symbol" title="Neuer Download"><i class="fa-solid fa-plus"></i></button>
        <button class="knopf ohne symbol" title="Einstellungen"><i class="fa-solid fa-sliders"></i></button>
      </div>
    </header>`;
  document.querySelector('[data-block="seite"]').outerHTML = `
    <nav class="seite">
      ${NAVI.map(navi).join('')}
      <div class="etikett">System</div>
      ${SYSTEM.map(navi).join('')}
    </nav>`;
  document.querySelector('[data-block="fuss"]').outerHTML = `
    <footer class="fuss">
      <span><i class="fa-solid fa-download"></i>&nbsp; 1 Download läuft · <span class="zahl">38 %</span></span>
      <span><i class="fa-solid fa-closed-captioning"></i>&nbsp; KI-Transkript: Juice Shop Level 3</span>
      <div class="rechts">
        <span><span class="punkt"></span>Quelle</span>
        <span><span class="punkt"></span>Kanalprüfung</span>
        <span class="schwach zahl">2.37.1</span>
      </div>
    </footer>`;
}

// Umschalter zum Vergleichen: Ecken und Akzentfarbe, gemerkt über alle Entwürfe
function entwurfSchalter() {
  const merken = (k, v) => { try { localStorage.setItem('tv-entwurf-' + k, v); } catch {} };
  const lesen = (k, s) => { try { return localStorage.getItem('tv-entwurf-' + k) || s; } catch { return s; } };
  const gruppen = {
    ecken: [['scharf', 'scharf'], ['kantig', 'kantig'], ['weich', 'weich']],
    akzent: [['minze', 'Minze'], ['blau', 'Blau'], ['violett', 'Violett'], ['orange', 'Orange']],
  };
  const standard = { ecken: 'kantig', akzent: 'minze' };
  const box = document.createElement('div');
  box.className = 'entwurf-schalter';
  for (const [gruppe, werte] of Object.entries(gruppen)) {
    const zeile = document.createElement('div');
    zeile.innerHTML = `<span>${gruppe === 'ecken' ? 'Ecken' : 'Akzent'}</span>`;
    for (const [wert, name] of werte) {
      const b = document.createElement('button');
      b.textContent = name;
      b.onclick = () => { setze(gruppe, wert); merken(gruppe, wert); };
      b.dataset.gruppe = gruppe; b.dataset.wert = wert;
      zeile.append(b);
    }
    box.append(zeile);
  }
  function setze(gruppe, wert) {
    document.documentElement.dataset[gruppe] = wert;
    box.querySelectorAll(`[data-gruppe="${gruppe}"]`).forEach(b => b.classList.toggle('an', b.dataset.wert === wert));
  }
  document.body.append(box);
  for (const gruppe of Object.keys(gruppen)) setze(gruppe, lesen(gruppe, standard[gruppe]));
}

export function seite(aktiv) {
  if (document.querySelector('[data-block="kopf"]')) schale(aktiv);
  entwurfSchalter();
}

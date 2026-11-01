// App-Symbol nach dem Bau einbetten (Abschrift des Werkzeugs im Appkern, oberflaeche/werkzeuge/symbol-einbetten.mjs,
// WIKI-35): In jeder gebauten Seite wird das apple-touch-icon, in jedem Manifest jedes Symbol außer "maskable" zur
// data:-Adresse. Über HTTPS mit dem Zertifikat der Hausstelle holt das iPhone ein verlinktes Symbol für den
// Home-Bildschirm nicht und zeigt nur den Anfangsbuchstaben; eingebettet braucht es keinen Abruf (gemessen an der
// Wetterwarte 0.49.6). Quelle bleiben die PNG im Ausgabeordner.
//   node symbol-einbetten.mjs <ausgabeordner>      (im Bau nach "vite build")
import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const ordner = process.argv[2] ?? "";
if (!ordner) throw new Error("Ausgabeordner fehlt");

/** @param {string} wurzel @returns {string[]} */
function dateien(wurzel) {
  return readdirSync(wurzel).flatMap((n) => (statSync(join(wurzel, n)).isDirectory() ? dateien(join(wurzel, n)) : [join(wurzel, n)]));
}

/** @param {string} adresse @returns {string} */
function daten(adresse) {
  const pfad = join(ordner, decodeURIComponent((adresse.replace(/^(\.\/|\/)+/, "").split(/[?#]/)[0] ?? "")));
  return `data:image/png;base64,${readFileSync(pfad).toString("base64")}`;
}

let seiten = 0;
let manifeste = 0;
for (const datei of dateien(ordner)) {
  if (datei.endsWith(".html")) {
    const html = readFileSync(datei, "utf-8");
    const neu = html.replace(/(<link\b[^>]*\brel="apple-touch-icon"[^>]*\bhref=")([^"]+\.png)(")/g, (/** @type {string} */ _, /** @type {string} */ a, /** @type {string} */ adresse, /** @type {string} */ z) => `${a}${daten(adresse)}${z}`);
    if (neu !== html) {
      writeFileSync(datei, neu);
      seiten++;
    }
  } else if (datei.endsWith(".webmanifest")) {
    /** @type {{ icons?: { src?: string, purpose?: string }[] }} */
    const manifest = JSON.parse(readFileSync(datei, "utf-8"));
    for (const symbol of manifest.icons ?? []) {
      if (!(symbol.purpose ?? "").includes("maskable") && symbol.src && symbol.src.endsWith(".png")) symbol.src = daten(symbol.src);
    }
    writeFileSync(datei, JSON.stringify(manifest));
    manifeste++;
  }
}
console.log(`Symbol eingebettet: ${seiten} Seiten, ${manifeste} Manifeste`);

/**
 * TubeVault - Symbolsatz: jede Seite verweist nur auf vorhandene Symbole, jedes Manifest taugt für den
 * Startbildschirm, und Nginx liefert die Manifeste mit ihrem Typ aus (scripts/symbole.py erzeugt die Bilder)
 */
import { describe, it, expect } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontend = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const lesen = (pfad) => readFileSync(join(frontend, pfad), 'utf-8');
const oeffentlich = (href) => join(frontend, 'public', href);

function kopf(seite) {
  return new DOMParser().parseFromString(lesen(seite), 'text/html').head;
}

describe.each(['index.html', 'mobile.html'])('Symbolsatz in %s', (seite) => {
  const links = [...kopf(seite).querySelectorAll('link[rel~="icon"], link[rel="apple-touch-icon"], link[rel="manifest"]')];

  it('verweist auf ico, PNG, SVG, apple-touch-icon und Manifest, alle vorhanden', () => {
    const hrefs = links.map((l) => l.getAttribute('href'));
    for (const href of ['/favicon.ico', '/favicon-32.png', '/icon-192.png', '/favicon.svg', '/apple-touch-icon.png']) {
      expect(hrefs).toContain(href);
    }
    expect(links.some((l) => l.rel === 'manifest')).toBe(true);
    for (const href of hrefs) expect(existsSync(oeffentlich(href)), href).toBe(true);
  });

  it('Manifest mit 192 und 512, maskierbar, eigenständig und mit Farben', () => {
    const manifest = JSON.parse(lesen(`public${links.find((l) => l.rel === 'manifest').getAttribute('href')}`));
    expect(manifest.display).toBe('standalone');
    expect(manifest.start_url).toBeTruthy();
    expect(manifest.theme_color).toMatch(/^#[0-9a-f]{6}$/i);
    expect(manifest.background_color).toMatch(/^#[0-9a-f]{6}$/i);
    for (const purpose of ['any', 'maskable']) {
      for (const sizes of ['192x192', '512x512']) {
        expect(manifest.icons.some((i) => i.purpose === purpose && i.sizes === sizes), `${purpose} ${sizes}`).toBe(true);
      }
    }
    for (const icon of manifest.icons) expect(existsSync(oeffentlich(icon.src)), icon.src).toBe(true);
  });
});

describe('Nginx', () => {
  it('kennt .webmanifest auf http-Ebene, ohne die Typtabelle in server zu ersetzen', () => {
    const konfiguration = lesen('nginx.conf');
    const typ = konfiguration.indexOf('application/manifest+json webmanifest;');
    expect(typ).toBeGreaterThan(-1);
    expect(typ).toBeLessThan(konfiguration.indexOf('server {'));
  });
});

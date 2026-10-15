import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { readFileSync } from 'node:fs';
import pkg from './package.json';

// Ziel des Entwicklungs-Proxys. Für Tests gegen ein lokales Backend mit
// Testdaten: TUBEVAULT_API=http://localhost:8033 npm run dev
const API_TARGET = process.env.TUBEVAULT_API || 'http://192.168.178.49:8031';

// Die Mobil-Ansicht ist eine zweite, eigenständige Seite (mobile.html) unter
// /m. Im Betrieb liefert Nginx sie aus; für die Entwicklung leitet dieses
// kleine Plugin alle /m-Adressen auf mobile.html.
const mobileEntry = {
  name: 'tubevault-mobile-entry',
  configureServer(server) {
    server.middlewares.use((req, _res, next) => {
      const path = (req.url || '').split('?')[0];
      if (path === '/m' || path.startsWith('/m/')) req.url = '/mobile.html';
      next();
    });
  },
};

// Versionsdatei der Oberfläche: offene Seiten fragen sie regelmäßig ab und
// laden nach einem Update selbst neu (lib/utils/versionWatch.js). Sie kommt
// aus demselben Build wie die Seite - zeigt sie eine neue Version, ist die
// neue Oberfläche wirklich ausgeliefert.
const appVersionFile = {
  name: 'tubevault-app-version',
  generateBundle() {
    this.emitFile({ type: 'asset', fileName: 'app-version.json', source: JSON.stringify({ version: pkg.version }) });
  },
  configureServer(server) {
    server.middlewares.use('/app-version.json', (_req, res) => {
      // Entwicklung: package.json frisch lesen, damit ein Versionssprung sofort wirkt
      const version = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf-8')).version;
      res.setHeader('Content-Type', 'application/json');
      res.setHeader('Cache-Control', 'no-store');
      res.end(JSON.stringify({ version }));
    });
  },
};

export default defineConfig({
  plugins: [svelte(), mobileEntry, appVersionFile],
  // Frontend-Version aus package.json in den Build inlinen.
  // Nutzung im Code: __APP_VERSION__ (Vite ersetzt beim Build durch den String).
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: API_TARGET,
        ws: true,
        changeOrigin: true,
      },
      '/thumbnails': {
        target: API_TARGET,
        changeOrigin: true,
      },
      '/avatars': {
        target: API_TARGET,
        changeOrigin: true,
      },
      '/subtitles': {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    rollupOptions: {
      input: { main: 'index.html', mobile: 'mobile.html' },
    },
  },
});

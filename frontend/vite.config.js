import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import pkg from './package.json';

// Ziel des Entwicklungs-Proxys. Für Tests gegen ein lokales Backend mit
// Testdaten: TUBEVAULT_API=http://localhost:8033 npm run dev
const API_TARGET = process.env.TUBEVAULT_API || 'http://192.168.178.49:8031';

export default defineConfig({
  plugins: [svelte()],
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
  },
});

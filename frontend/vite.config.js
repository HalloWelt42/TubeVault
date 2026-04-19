import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import pkg from './package.json';

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
        target: 'http://192.168.178.49:8031',
        changeOrigin: true,
      },
      '/thumbnails': {
        target: 'http://192.168.178.49:8031',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  },
});

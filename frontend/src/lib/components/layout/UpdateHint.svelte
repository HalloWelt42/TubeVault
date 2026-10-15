<!--
  TubeVault - Hinweis auf eine neue Version (Entwurf mockups/kanal.html, Kopf)
  Erscheint nur, wenn das Backend eine neuere Version des Projekts gelesen hat
  (services/update_check, in den Einstellungen abschaltbar). Das Wort Update
  leuchtet ruhig und führt zur Projektseite.
-->
<script>
  import { onMount } from 'svelte';
  import { api } from '../../api/client.js';

  const REFRESH_MS = 30 * 60 * 1000;   // das Backend fragt selbst nur alle 6 Stunden

  let update = $state(null);

  async function load() {
    try { update = await api.getUpdateStatus(); } catch { /* ohne Antwort kein Hinweis */ }
  }

  onMount(() => {
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => clearInterval(timer);
  });
</script>

{#if update?.available}
  <span class="update" title="Neue Version {update.latest} verfügbar, hier läuft {update.current}. Öffnet die Projektseite mit allen Neuerungen.">
    <i class="fa-solid fa-circle-arrow-up"></i><a href={update.url} target="_blank" rel="noopener">Update</a><span class="zahl">{update.latest}</span>
  </span>
{/if}

<style>
  /* Das Wort leuchtet ruhig (Schrift, keine Kante) */
  .update {
    display: inline-flex; align-items: center; gap: var(--tv-a2); height: 40px; padding: 0 var(--tv-a3); margin-right: var(--tv-a2);
    border-radius: var(--tv-ecke); background: rgba(var(--tv-akzent-rgb), 0.08); color: var(--tv-text-2); font-size: var(--tv-gr-klein);
  }
  .update i { color: var(--tv-akzent); }
  .update a {
    font-weight: 700; font-size: var(--tv-gr-text); letter-spacing: 0.02em; color: var(--tv-akzent); text-decoration: none;
    text-shadow: 0 0 8px rgba(var(--tv-akzent-rgb), 0.55); animation: leuchten 2.8s ease-in-out infinite;
  }
  .update a:hover { text-decoration: underline; text-underline-offset: 3px; }
  @keyframes leuchten {
    50% { text-shadow: 0 0 14px rgba(var(--tv-akzent-rgb), 0.95), 0 0 28px rgba(var(--tv-akzent-rgb), 0.4); }
  }
  @media (prefers-reduced-motion: reduce) { .update a { animation: none; } }
</style>

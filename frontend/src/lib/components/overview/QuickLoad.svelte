<!--
  Laden-Zeile der Übersicht: Adresse einfügen, Qualität wählen, Nur Ton,
  Laden. Ein einzelnes Video geht direkt in die Warteschlange; Playlists und
  Kanäle brauchen die Auswahl auf der Seite Downloads und werden dorthin
  weitergereicht. Gestaltung nach mockups/uebersicht.html.
-->
<script>
  import { api } from '../../api/client.js';
  import { navigate } from '../../router/router.js';
  import { pendingDownloadUrl } from '../../stores/app.js';
  import { toast } from '../../stores/notifications.js';
  import { getSetting } from '../../stores/settings.js';
  import { VIDEO_QUALITIES } from '../../constants/qualities.js';
  import ActionMenu from '../common/ActionMenu.svelte';

  // Adressen, die erst aufgelöst werden müssen (Auswahl der Videos)
  const NEEDS_CHOICE = [/[?&]list=/, /\/playlist\?/, /\/@[a-zA-Z0-9_.-]+/, /\/channel\//, /\/c\//];

  /** onQueued: nach dem Einreihen, z.B. um Zahlen neu zu laden */
  let { onQueued = () => {} } = $props();

  let url = $state('');
  let quality = $state(getSetting('download.quality', '720p'));
  let audioOnly = $state(false);
  let busy = $state(false);
  let menu;
  let field;

  const qualityName = (value) => (value === 'best' ? 'Beste' : value);

  export function focus() { field?.focus(); }

  function chooseQuality(event) {
    menu.open(event, 'Qualität', VIDEO_QUALITIES.map((q) => ({
      icon: q.value === quality ? 'fa-check' : 'fa-film',
      label: q.label,
      run: () => { quality = q.value; },
    })));
  }

  async function load() {
    const address = url.trim();
    if (!address || busy) return;
    if (NEEDS_CHOICE.some((pattern) => pattern.test(address))) {
      pendingDownloadUrl.set(address);
      url = '';
      navigate('/downloads');
      return;
    }
    busy = true;
    try {
      const result = await api.addDownload({ url: address, quality: audioOnly ? 'audio_only' : quality, audio_only: audioOnly });
      toast.success(`In der Warteschlange: ${result.title || result.video_id}`);
      url = '';
      onQueued();
    } catch (e) {
      toast.error(`Laden nicht möglich: ${e.message}`);
    }
    busy = false;
  }
</script>

<div class="laden">
  <label class="feld">
    <i class="fa-solid fa-link"></i>
    <input bind:this={field} bind:value={url} disabled={busy} aria-label="Adresse zum Laden"
           placeholder="Adresse eines Videos, einer Playlist oder eines Kanals einfügen"
           onkeydown={(e) => e.key === 'Enter' && load()} />
  </label>
  <button class="tv-knopf wahl" onclick={chooseQuality} disabled={audioOnly}
          title={audioOnly ? 'Bei Nur Ton wird kein Bild geladen' : 'Qualität des Videos wählen'}>
    <span class="zahl">{qualityName(quality)}</span> <i class="fa-solid fa-chevron-down"></i></button>
  <button class="tv-knopf wahl" class:aktiv={audioOnly} onclick={() => audioOnly = !audioOnly}
          title={audioOnly ? 'Nur der Ton wird geladen; Klick lädt wieder Bild und Ton' : 'Nur den Ton laden, ohne Bild'}>
    <i class="fa-solid fa-music"></i> Nur Ton</button>
  <button class="tv-knopf haupt wahl" onclick={load} disabled={busy || !url.trim()}>
    <i class="fa-solid {busy ? 'fa-spinner fa-spin' : 'fa-download'}"></i> Laden</button>
</div>

<ActionMenu bind:this={menu} />

<style>
  .laden { display: grid; grid-template-columns: minmax(0, 1fr) auto auto auto; gap: var(--tv-a2); margin-top: var(--tv-a3); }
  .feld { display: flex; align-items: center; gap: var(--tv-a2); height: 44px; padding: 0 var(--tv-a3);
          border-radius: var(--tv-ecke); background: var(--tv-mulde); color: var(--tv-text-3); cursor: text; }
  .feld:focus-within { outline: 1px solid rgba(var(--tv-akzent-rgb), 0.6); }
  .feld input { flex: 1; min-width: 0; height: 100%; border: 0; background: none; color: var(--tv-text);
                font: inherit; font-size: var(--tv-gr-text); outline: 0; }
  .feld input::placeholder { color: var(--tv-text-3); }
  .wahl { height: 44px; }
</style>

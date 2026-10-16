<!--
  Ausgeblendet (Handy): ausgeschlossene Alben und ausgeblendete Titel der
  Sammlung. Antippen setzt oder nimmt den Haken, "Zurückholen" holt die
  gewählten zurück (ohne Haken: alle). Gleiche Wege wie am Rechner
  (lib/utils/musicHiding.js).
-->
<script>
  import { onMount } from 'svelte';
  import { api } from '../../lib/api/client.js';
  import { coverUrl } from '../../lib/utils/musicTrack.js';
  import { restoreHidden } from '../../lib/utils/musicHiding.js';
  import { onMusicChange } from '../../lib/utils/musicChanges.js';
  import { toast } from '../../lib/stores/notifications.js';

  let area = $state(null);
  let chosen = $state(new Set());         // Kennungen der Titel und Gruppen der Alben

  let rows = $derived(area ? [
    ...area.albums.map((a) => ({ key: a.source, album: true, title: a.name, line: `${a.subtitle || ''} · ${a.count} Titel` })),
    ...area.tracks.map((t) => ({ key: t.id, album: false, title: t.title, line: t.artist, track: t })),
  ] : []);

  async function load() {
    try {
      area = await api.musicHidden();
      chosen = new Set([...chosen].filter((key) => rows.some((r) => r.key === key)));
    } catch (e) { toast.error(e.message); }
  }

  function flip(key) {
    const next = new Set(chosen);
    if (!next.delete(key)) next.add(key);
    chosen = next;
  }

  async function restore() {
    const picked = chosen.size ? rows.filter((r) => chosen.has(r.key)) : rows;
    try {
      const result = await restoreHidden({ tracks: picked.filter((r) => !r.album).map((r) => r.key),
                                           albums: picked.filter((r) => r.album).map((r) => r.key) });
      const count = result.tracks + result.albums;
      toast.success(count === 1 ? 'Zurückgeholt' : `${count} zurückgeholt`);
    } catch (e) { toast.error(e.message); }
  }

  onMount(() => {
    load();
    return onMusicChange((change) => { if (change.reload) load(); });
  });
</script>

{#if !area}
  <div class="m-spin"><i class="fa-solid fa-spinner fa-spin"></i></div>
{:else if !rows.length}
  <p class="m-note">Nichts ausgeblendet.</p>
{:else}
  <div class="knoepfe">
    <button class="m-btn primary" onclick={restore}><i class="fa-solid fa-rotate-left"></i>
      {chosen.size ? `${chosen.size} zurückholen` : 'Alle zurückholen'}</button>
  </div>
  <div class="liste">
    {#each rows as row (row.key)}
      <button class="zeile" class:an={chosen.has(row.key)} aria-pressed={chosen.has(row.key)} onclick={() => flip(row.key)}>
        <i class="fa-{chosen.has(row.key) ? 'solid fa-square-check' : 'regular fa-square'} haken"></i>
        {#if row.album}<span class="bild"><i class="fa-solid fa-compact-disc"></i></span>
        {:else}<img class="bild" src={coverUrl(row.track)} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />{/if}
        <span class="text"><span class="t">{row.title}</span><span class="w">{row.album ? 'Album · ' : ''}{row.line}</span></span>
      </button>
    {/each}
  </div>
  <p class="m-hinweis">Antippen wählt aus. Zurückgeholtes steht sofort wieder in allen Listen und Mixen.</p>
{/if}

<style>
  .knoepfe { display: flex; padding: 16px calc(var(--m-safe-right) + 16px) 8px calc(var(--m-safe-left) + 16px); }
  .knoepfe .m-btn { flex: 1; }
  .liste { padding: 4px 0 8px; }
  .zeile { width: 100%; display: grid; grid-template-columns: 28px 52px minmax(0, 1fr); gap: 12px; align-items: center; min-height: 64px;
           padding: 6px calc(var(--m-safe-right) + 16px) 6px calc(var(--m-safe-left) + 16px); text-align: left; }
  .zeile:active { background: var(--m-surface); }
  .haken { font-size: 20px; color: var(--m-faint); }
  .zeile.an .haken { color: var(--m-accent); }
  .bild { width: 52px; height: 52px; object-fit: cover; border-radius: var(--tv-ecke-klein); background: var(--m-surface);
          display: grid; place-items: center; color: var(--m-faint); font-size: 22px; }
  .text { min-width: 0; display: flex; flex-direction: column; }
  .t { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .w { font-size: 15px; color: var(--m-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .m-hinweis { margin: 0 16px 24px; padding: 12px 14px; border-radius: var(--m-radius); background: var(--tv-flaeche);
               font-size: 15px; color: var(--m-dim); }
</style>

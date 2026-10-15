<!--
  Musik (Mobil): Mixe, Interpreten, Musikkanäle und Neues. Jede Gruppe
  spielt der Reihe nach oder zufällig; ein Tipp auf einen Titel spielt ihn
  sofort. Derselbe Musikspieler wie am Rechner (auch auf dem Sperrbildschirm).
-->
<script>
  import { api } from '../../lib/api/client.js';
  import { coverUrl } from '../../lib/utils/musicTrack.js';
  import { musicPlayer as player } from '../../lib/stores/musicPlayer.svelte.js';
  import { formatDuration } from '../../lib/utils/format.js';

  const MIXES = [
    { key: 'all', name: 'Alles zufällig', icon: 'fa-shuffle', shuffle: true },
    { key: 'favorites', name: 'Lieblingssongs', icon: 'fa-heart', shuffle: true },
    { key: 'forgotten', name: 'Lange nicht gehört', icon: 'fa-hourglass-half', shuffle: true },
    { key: 'often', name: 'Oft gehört', icon: 'fa-fire', shuffle: false },
  ];

  let overview = $state(null);
  let artists = $state([]);
  let opened = $state(null);      // { key, title, tracks }
  let failed = $state(false);

  async function load() {
    failed = false;
    try {
      [overview, artists] = await Promise.all([api.musicOverview(), api.musicArtists()]);
    } catch { failed = true; }
  }

  async function open(key) {
    try { opened = await api.musicPlay(key); } catch { failed = true; }
  }

  const play = (key, shuffle = false, start = null) => player.playSource(key, { shuffle, start }).catch(() => {});

  load();
</script>

<div class="m-view">
  {#if opened}
    <header class="top">
      <button class="zurueck" onclick={() => opened = null} aria-label="Zurück"><i class="fa-solid fa-chevron-left"></i></button>
      <h1 class="m-h1 titel">{opened.title}</h1>
    </header>
    <div class="knoepfe">
      <button class="m-btn primary" onclick={() => play(opened.source)}><i class="fa-solid fa-play"></i> Abspielen</button>
      <button class="m-btn" onclick={() => play(opened.source, true)}><i class="fa-solid fa-shuffle"></i> Zufällig</button>
    </div>
    {#each opened.tracks as track (track.id)}
      {@render titelZeile(track, () => play(opened.source, false, track.id))}
    {/each}
  {:else}
    <header class="top">
      <h1 class="m-h1">Musik</h1>
      {#if overview}<span class="zahl leise">{overview.counts.tracks} Titel</span>{/if}
    </header>

    {#if failed}
      <div class="m-note"><p>Der Server ist gerade nicht erreichbar.</p>
        <button class="m-btn" onclick={load}><i class="fa-solid fa-rotate"></i> Erneut versuchen</button></div>
    {:else if !overview}
      <div class="m-spin"><i class="fa-solid fa-spinner fa-spin"></i></div>
    {:else if !overview.counts.tracks}
      <div class="m-note"><p>Noch keine Musik. Am Rechner auf der Kanalseite "Musikkanal" wählen oder Videos in der
        Bibliothek als Musik festlegen.</p></div>
    {:else}
      <div class="mixe">
        {#each MIXES as mix (mix.key)}
          <button class="mix" onclick={() => play(mix.key, mix.shuffle)}><i class="fa-solid {mix.icon}"></i> {mix.name}</button>
        {/each}
      </div>

      <h2 class="m-h2">Interpreten</h2>
      {#each artists as group (group.key)}
        <div class="gruppe">
          <button class="oeffnen" onclick={() => open(group.key)}>
            <img src={coverUrl(group.covers[0])} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
            <span class="text"><span class="t">{group.name}</span><span class="w zahl">{group.count} Titel</span></span>
          </button>
          <button class="taste" onclick={() => play(group.key, true)} aria-label="Zufällig"><i class="fa-solid fa-shuffle"></i></button>
        </div>
      {/each}

      {#if overview.channels.length}
        <h2 class="m-h2">Musikkanäle</h2>
        {#each overview.channels as group (group.key)}
          <div class="gruppe">
            <button class="oeffnen" onclick={() => open(group.key)}>
              <img src={coverUrl(group.covers[0])} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
              <span class="text"><span class="t">{group.name}</span><span class="w zahl">{group.count} Titel</span></span>
            </button>
            <button class="taste" onclick={() => play(group.key, true)} aria-label="Zufällig"><i class="fa-solid fa-shuffle"></i></button>
          </div>
        {/each}
      {/if}

      <h2 class="m-h2">Neu in der Sammlung</h2>
      {#each overview.new as track (track.id)}
        {@render titelZeile(track, () => play('new', false, track.id))}
      {/each}
    {/if}
  {/if}
</div>

{#snippet titelZeile(track, onplay)}
  <button class="zeile" class:laeuft={player.current?.id === track.id} onclick={onplay}>
    <img src={coverUrl(track)} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
    <span class="text"><span class="t">{track.title}</span><span class="w">{track.artist}</span></span>
    <span class="zahl w">{formatDuration(track.duration || 0)}</span>
  </button>
{/snippet}

<style>
  .top { display: flex; align-items: baseline; gap: 10px; padding: calc(var(--m-safe-top) + 18px) 16px 8px; }
  .titel { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .zurueck { width: var(--m-touch); height: var(--m-touch); margin-left: -12px; font-size: 1.2rem; align-self: center; }
  .leise { color: var(--m-dim); }
  .knoepfe { display: flex; gap: 10px; padding: 4px 16px 12px; }
  .knoepfe .m-btn { flex: 1; }
  .mixe { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; padding: 4px 16px 8px; }
  .mix { min-height: 64px; padding: 10px 12px; border-radius: var(--m-radius); text-align: left; font-weight: 700;
         display: flex; align-items: center; gap: 10px;
         background: linear-gradient(135deg, rgba(192, 132, 252, 0.35), rgba(var(--tv-akzent-rgb), 0.15)); }
  .mix i { color: var(--tv-art-musik); font-size: 1.2rem; }
  .m-h2 { padding: 18px 16px 6px; }
  .gruppe { display: flex; align-items: center; padding: 0 8px 0 16px; }
  .oeffnen, .zeile { flex: 1; min-width: 0; display: flex; align-items: center; gap: 12px; padding: 6px 0; text-align: left; }
  .zeile { width: 100%; padding: 6px 16px; }
  .zeile.laeuft .t { color: var(--m-accent); }
  img { width: 52px; height: 52px; flex: none; object-fit: cover; border-radius: 3px; background: var(--m-surface); }
  .text { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .t { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .w { font-size: 0.85rem; color: var(--m-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .taste { width: var(--m-touch); height: var(--m-touch); flex: none; display: grid; place-items: center; color: var(--m-dim); font-size: 1.1rem; }
</style>

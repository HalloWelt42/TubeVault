<!--
  Kachel einer dynamischen Wiedergabeliste (Interpret, Album, Kanal, Mix):
  Collage aus vier Titelbildern. Klick öffnet die Liste, die Tasten spielen
  sie ab - der Reihe nach oder zufällig.
-->
<script>
  import { api } from '../../api/client.js';
  import { coverUrl } from '../../utils/musicTrack.js';
  import { musicPlayer as player } from '../../stores/musicPlayer.svelte.js';
  import { formatDurationLong } from '../../utils/format.js';

  // group: { key, name, subtitle, count, duration, covers }
  let { group, onOpen = () => {} } = $props();

  let covers = $derived(group.covers?.length ? [0, 1, 2, 3].map(i => group.covers[i % group.covers.length]) : []);
  let current = $derived(player.source === group.key);
</script>

<div class="gruppe" class:laeuft={current} role="button" tabindex="0" onclick={onOpen}
     onkeydown={(e) => e.key === 'Enter' && onOpen()} title="{group.name} - öffnen">
  <div class="cover" class:collage={covers.length}>
    {#each covers as id, i (i)}<img src={coverUrl(id)} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />{/each}
    {#if !covers.length}<i class="fa-solid fa-music zeichen"></i>{/if}
    <div class="tasten">
      <button class="taste" onclick={(e) => { e.stopPropagation(); player.playSource(group.key); }} title="Abspielen">
        <i class="fa-solid fa-play"></i></button>
      <button class="taste" onclick={(e) => { e.stopPropagation(); player.playSource(group.key, { shuffle: true }); }} title="Zufällig abspielen">
        <i class="fa-solid fa-shuffle"></i></button>
    </div>
  </div>
  <div class="name">{group.name}</div>
  <div class="unter zahl">{group.subtitle ? `${group.subtitle} · ` : ''}{group.count} Titel{#if group.duration}{' · '}{formatDurationLong(group.duration)}{/if}</div>
</div>

<style>
  .gruppe { cursor: pointer; min-width: 0; }
  .gruppe:focus-visible { outline: 2px solid var(--tv-akzent); outline-offset: 3px; }
  .cover { position: relative; aspect-ratio: 1; border-radius: var(--tv-ecke); overflow: hidden; background: var(--tv-karte-2);
           display: grid; place-items: center; }
  .cover.collage { grid-template-columns: 1fr 1fr; }
  .cover img { width: 100%; height: 100%; aspect-ratio: 1; object-fit: cover; display: block; }
  .zeichen { font-size: 46px; color: var(--tv-art-musik); }
  .tasten { position: absolute; right: 10px; bottom: 10px; display: flex; gap: 6px; opacity: 0; transform: translateY(6px);
            transition: opacity 0.15s, transform 0.15s; }
  .gruppe:hover .tasten, .gruppe.laeuft .tasten { opacity: 1; transform: none; }
  .taste { width: 44px; height: 44px; display: grid; place-items: center; border: 0; border-radius: var(--tv-ecke); cursor: pointer;
           background: var(--tv-akzent); color: var(--tv-akzent-text); font-size: 16px; box-shadow: 0 6px 18px rgba(0, 0, 0, 0.45); }
  .taste + .taste { background: var(--tv-karte-2); color: var(--tv-text); }
  .name { margin-top: 8px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .laeuft .name { color: var(--tv-akzent); }
  .unter { font-size: var(--tv-gr-klein); color: var(--tv-text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  @media (hover: none) { .tasten { opacity: 1; transform: none; } }
</style>

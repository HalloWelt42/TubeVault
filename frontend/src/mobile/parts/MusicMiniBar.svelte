<!--
  Kleiner Musik-Abspieler über der unteren Leiste der Mobil-Ansicht. Tippen
  öffnet "Läuft gerade". Derselbe Musikspieler wie am Rechner
  (lib/stores/musicPlayer.svelte.js), samt Sperrbildschirm-Steuerung.
-->
<script>
  import { api } from '../../lib/api/client.js';
  import { coverUrl } from '../../lib/utils/musicTrack.js';
  import { musicPlayer as player } from '../../lib/stores/musicPlayer.svelte.js';
  import { go } from '../router.js';

  let track = $derived(player.current);
  let progress = $derived(player.duration ? player.time / player.duration : 0);
</script>

{#if track}
  <div class="mini">
    <span class="fortschritt" style:width="{progress * 100}%"></span>
    <button class="info" onclick={() => go('/jetzt')}>
      <img src={coverUrl(track)} alt="" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
      <span class="text"><span class="t">{track.title}</span><span class="w">{track.artist}</span></span>
    </button>
    <button class="taste" onclick={() => player.toggle()} aria-label={player.playing ? 'Pause' : 'Abspielen'}>
      <i class="fa-solid {player.loading ? 'fa-spinner fa-spin' : player.playing ? 'fa-pause' : 'fa-play'}"></i></button>
    <button class="taste" onclick={() => player.next()} aria-label="Weiter"><i class="fa-solid fa-forward-step"></i></button>
  </div>
{/if}

<style>
  .mini { position: relative; flex: 0 0 auto; display: flex; align-items: center; gap: 6px; padding: 6px 8px 6px 10px;
          background: var(--m-surface-2); border-top: 1px solid var(--m-line); }
  .fortschritt { position: absolute; left: 0; top: -1px; height: 2px; background: var(--m-accent); }
  .info { flex: 1; min-width: 0; display: flex; align-items: center; gap: 10px; text-align: left; }
  img { width: 44px; height: 44px; flex: none; object-fit: cover; border-radius: 3px; background: var(--m-surface); }
  .text { min-width: 0; display: flex; flex-direction: column; }
  .t { font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .w { font-size: 0.85rem; color: var(--m-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .taste { width: var(--m-touch); height: var(--m-touch); flex: none; display: grid; place-items: center; font-size: 1.25rem; }
</style>

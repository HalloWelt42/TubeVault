<!--
  Weiterhören in der Übersicht: die Musik-Warteschlange dieses Geräts und das
  zuletzt gehörte, nicht beendete Hörbuch, je mit Abspielknopf an der
  gemerkten Stelle. Ist beides leer, erscheint nichts.
-->
<script>
  import { onMount } from 'svelte';
  import { api } from '../../api/client.js';
  import { musicPlayer as player } from '../../stores/musicPlayer.svelte.js';
  import { coverUrl } from '../../utils/musicTrack.js';
  import { formatDurationLong } from '../../utils/format.js';
  import { toast } from '../../stores/notifications.js';
  import OverviewSection from './OverviewSection.svelte';

  let books = $state([]);

  // Musik nur, wenn gerade kein Hörbuch in der Warteschlange liegt; das zeigt die Buchkarte
  let music = $derived(player.current && !player.audiobook ? player.current : null);
  let book = $derived(books.find((b) => b.key === player.audiobook)
    || books.filter((b) => b.current_part && !b.finished)
            .sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)))[0]
    || null);
  let bookPlaying = $derived(!!book && player.audiobook === book.key && player.playing);

  onMount(async () => {
    try { books = await api.musicBooks(); } catch { books = []; }
  });

  async function playBook() {
    try {
      if (player.audiobook === book.key) player.toggle();
      else await player.playSource(`hoerbuch:${book.key}`);
    } catch (e) { toast.error(e.message); }
  }

  const bookShare = (b) => (b.duration ? Math.round((b.duration - b.remaining) / b.duration * 100) : 0);
</script>

{#if music || book}
  <OverviewSection title="Weiterhören">
    <div class="hoeren">
      {#if music}
        <div class="hoer">
          <img src={coverUrl(music)} alt="" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
          <div class="text">
            <div class="art musik"><i class="fa-solid fa-music"></i> Musik</div>
            <div class="t">{music.title}</div>
            <div class="w">{music.artist || player.title}{#if player.upcoming.length} · noch <span class="zahl">{player.upcoming.length}</span> Titel in der Warteschlange{/if}</div>
          </div>
          <button class="spiel" onclick={() => player.toggle()} title={player.playing ? 'Anhalten' : 'An der gemerkten Stelle weiterhören'}>
            <i class="fa-solid {player.playing ? 'fa-pause' : 'fa-play'}"></i></button>
        </div>
      {/if}
      {#if book}
        <div class="hoer">
          {#if book.cover_id}<img src={coverUrl(book.cover_id)} alt="" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
          {:else}<span class="ohne-bild"><i class="fa-solid fa-book-open"></i></span>{/if}
          <div class="text">
            <div class="art buch"><i class="fa-solid fa-book-open"></i> Hörbuch</div>
            <div class="t">{book.title}</div>
            <div class="w">{#if book.author}{book.author} · {/if}Teil <span class="zahl">{book.current_part || 1}</span> von <span class="zahl">{book.parts}</span> · noch <span class="zahl">{formatDurationLong(book.remaining)}</span></div>
            <div class="balken"><b style:width="{bookShare(book)}%"></b></div>
          </div>
          <button class="spiel" onclick={playBook} title={bookPlaying ? 'Anhalten' : 'An der gemerkten Stelle weiterhören'}>
            <i class="fa-solid {bookPlaying ? 'fa-pause' : 'fa-play'}"></i></button>
        </div>
      {/if}
    </div>
  </OverviewSection>
{/if}

<style>
  .hoeren { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: var(--tv-a3); }
  .hoer { display: grid; grid-template-columns: 64px minmax(0, 1fr) 44px; gap: var(--tv-a3); align-items: center;
          padding: var(--tv-a3); border-radius: var(--tv-ecke); background: var(--tv-flaeche); }
  .hoer img, .ohne-bild { width: 64px; height: 64px; object-fit: cover; border-radius: var(--tv-ecke-klein); background: var(--tv-mulde); }
  .ohne-bild { display: grid; place-items: center; font-size: 24px; color: var(--tv-text-3); }
  .text { min-width: 0; }
  .art { font-size: var(--tv-gr-marke); font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
  .art.musik { color: var(--tv-art-musik); }
  .art.buch { color: var(--tv-art-vertont); }
  .t { font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .w { font-size: var(--tv-gr-klein); color: var(--tv-text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .balken { position: relative; height: 4px; margin-top: 6px; border-radius: 2px; background: var(--tv-karte-3); overflow: hidden; }
  .balken b { position: absolute; left: 0; top: 0; bottom: 0; background: var(--tv-akzent); }
  .spiel { width: 44px; height: 44px; border: 0; border-radius: var(--tv-ecke); background: var(--tv-akzent);
           color: var(--tv-akzent-text); font-size: 16px; cursor: pointer; }
  .spiel:hover { background: var(--tv-akzent-hell); }
</style>

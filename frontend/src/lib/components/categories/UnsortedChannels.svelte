<!--
  Kasten "Videos ohne Kategorie": die Kanäle mit den meisten unsortierten
  Videos, je Kanal eine Kategorie wählen (legt dort die Regel "Kanal ist"
  an - alle Videos des Kanals kommen hinein, neue auch).
-->
<script>
  let { unassigned, channels, onPick, onTopics = null } = $props();
</script>

<div class="unsortiert">
  <div class="links">
    <h2><span class="zahl">{unassigned.toLocaleString('de-DE')}</span> {unassigned === 1 ? 'Video' : 'Videos'} ohne Kategorie</h2>
    <p class="tv-leise tv-klein">Am schnellsten über ihre Kanäle: eine Kategorie wählen, alle Videos des Kanals kommen hinein, neue auch.</p>
    <div class="kanaele">
      {#each channels as channel (channel.channel_id)}
        <div class="kanal">
          <span class="n" title={channel.name}>{channel.name}</span>
          <span class="zahl tv-schwach">{channel.count.toLocaleString('de-DE')}</span>
          <button class="wahl" onclick={(e) => onPick(e, channel)}
                  title="Regel &quot;Kanal ist {channel.name}&quot; in einer Kategorie anlegen">
            Kategorie wählen <i class="fa-solid fa-chevron-down"></i></button>
        </div>
      {/each}
    </div>
  </div>
  {#if onTopics}
    <button class="tv-knopf" onclick={onTopics} title="Die lokale KI ordnet die Videos ohne Kategorie nach Themen und schlägt Kategorien vor">
      <i class="fa-solid fa-wand-magic-sparkles"></i> Themen erkennen</button>
  {/if}
</div>

<style>
  .unsortiert { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--tv-a4); align-items: start;
                padding: var(--tv-a4); background: var(--tv-flaeche); border-radius: var(--tv-ecke); margin-bottom: var(--tv-a5); }
  h2 { margin: 0 0 4px; font-size: var(--tv-gr-titel); }
  p { margin: 0; }
  .kanaele { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: var(--tv-a2); margin-top: var(--tv-a3); }
  .kanal { display: flex; align-items: center; gap: var(--tv-a2); min-width: 0; padding: 6px 8px; background: var(--tv-karte);
           border-radius: var(--tv-ecke); }
  .n { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .wahl { flex: none; display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 10px; cursor: pointer;
          background: var(--tv-karte-2); color: var(--tv-text); border: 1px solid var(--tv-rand); border-radius: var(--tv-ecke-klein);
          font: inherit; font-size: var(--tv-gr-klein); }
  .wahl:hover { background: var(--tv-karte-3); }
  .wahl i { font-size: 13px; color: var(--tv-text-3); }
  @media (max-width: 720px) { .unsortiert { grid-template-columns: 1fr; } }
</style>

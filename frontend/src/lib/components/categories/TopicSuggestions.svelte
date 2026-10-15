<!--
  "Themen erkennen" (Entwurf mockups/kategorien.html, Zustand themen): Die
  lokale KI schlägt Kategorien samt Regel "inhaltlich wie" vor. Übernehmen,
  Ansehen (im Seitenblatt, änderbar) oder Verwerfen - nichts geschieht ohne Klick.
-->
<script>
  let { state, onAccept, onView, onDismiss, onRestart } = $props();

  let suggestions = $derived(state?.suggestions || []);
</script>

<div class="hinweis">
  <i class="fa-solid fa-wand-magic-sparkles"></i>
  <span>Die lokale KI ordnet die Videos ohne Kategorie nach Themen. Übernehmen legt die Kategorie samt Regel "inhaltlich wie" an - nichts geschieht ohne Klick.</span>
  {#if !state?.running}
    <button class="tv-knopf klein" onclick={onRestart} title="Die Videos ohne Kategorie neu nach Themen ordnen; ersetzt die Vorschläge">
      <i class="fa-solid fa-rotate"></i> Neu erkennen</button>
  {/if}
</div>

{#if state?.running}
  <div class="lauf">
    <i class="fa-solid fa-spinner fa-spin"></i> {state.phase || 'Läuft'}
    {#if state.total}<span class="zahl tv-schwach">{state.done} / {state.total}</span>{/if}
  </div>
{:else if state?.error}
  <div class="tv-fehlertext lauf"><i class="fa-solid fa-circle-exclamation"></i> <span>{state.error}</span></div>
{/if}

{#if suggestions.length}
  <div class="vorschlaege">
    {#each suggestions as s (s.id)}
      <div class="vorschlag">
        <div class="kopf"><b>{s.name}</b><span class="tv-schwach"><span class="zahl">{s.match_count.toLocaleString('de-DE')}</span> Videos</span></div>
        <div class="beispiele" title={`Regel: inhaltlich wie "${s.query}"`}>
          {#if s.channels.length}vor allem {s.channels.join(', ')}{:else}{s.query}{/if}</div>
        <div class="tasten">
          <button class="tv-knopf klein haupt" onclick={() => onAccept(s)}
                  title="Kategorie &quot;{s.name}&quot; mit der Regel inhaltlich wie anlegen und füllen"><i class="fa-solid fa-check"></i> Übernehmen</button>
          <button class="tv-knopf klein" onclick={() => onView(s)} title="Regel und passende Videos ansehen, vor dem Übernehmen änderbar">Ansehen</button>
          <button class="tv-knopf klein ohne" onclick={() => onDismiss(s)}>Verwerfen</button>
        </div>
      </div>
    {/each}
  </div>
{:else if state && !state.running && !state.error}
  <div class="tv-leer">Keine offenen Vorschläge.</div>
{/if}

<style>
  .hinweis { display: flex; align-items: center; gap: var(--tv-a3); padding: var(--tv-a3) var(--tv-a4); margin-bottom: var(--tv-a3);
             background: rgba(var(--tv-bedeutung-rgb), 0.1); border-radius: var(--tv-ecke); }
  .hinweis > i { color: var(--tv-bedeutung); }
  .hinweis span { flex: 1; }
  .lauf { display: flex; align-items: center; gap: var(--tv-a2); margin-bottom: var(--tv-a3); color: var(--tv-text-2); }
  .vorschlaege { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: var(--tv-a3); }
  .vorschlag { padding: var(--tv-a3) var(--tv-a4); background: var(--tv-karte); border-radius: var(--tv-ecke);
               outline: 1px dashed rgba(var(--tv-bedeutung-rgb), 0.45); outline-offset: -1px; }
  .kopf { display: flex; align-items: baseline; gap: var(--tv-a2); flex-wrap: wrap; }
  .kopf b { font-size: 18px; }
  .beispiele { display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
               font-size: var(--tv-gr-klein); color: var(--tv-text-2); margin: 6px 0 var(--tv-a2); }
  .tasten { display: flex; gap: var(--tv-a2); flex-wrap: wrap; }
</style>

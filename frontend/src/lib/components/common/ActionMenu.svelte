<!--
  Aufklappmenü an der Klickstelle (kein Browser-Dialog). Einträge:
    { icon, label, run, danger?, hint? }   Aktion
    { icon, label, items: [...] }          Untermenü (öffnet an derselben Stelle, mit Zurück)
    { trenner: true }
  Nutzung: <ActionMenu bind:this={menu} />, menu.open(event, 'Titel', eintraege)
-->
<script>
  import { toast } from '../../stores/notifications.js';

  const WIDTH = 300;

  let title = $state('');
  let stack = $state([]);        // Ebenen: [{ title, items }]
  let x = $state(0);
  let y = $state(0);
  let level = $derived(stack[stack.length - 1]);

  export function open(event, heading, items) {
    event.preventDefault();
    event.stopPropagation();
    title = heading;
    stack = [{ title: heading, items }];
    const height = Math.min(440, 52 + items.length * 40);
    x = Math.max(8, Math.min(event.clientX - WIDTH + 40, window.innerWidth - WIDTH - 8));
    y = Math.max(8, Math.min(event.clientY, window.innerHeight - height - 8));
  }

  function close() { stack = []; }

  async function choose(item) {
    if (item.items) {
      stack = [...stack, { title: item.label, items: item.items }];
      return;
    }
    close();
    try { await item.run(); } catch (e) { toast.error(e.message); }
  }
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && close()} />

{#if level}
  <div class="hintergrund" role="presentation" onclick={close} oncontextmenu={(e) => { e.preventDefault(); close(); }}></div>
  <div class="menue" style:left="{x}px" style:top="{y}px" style:width="{WIDTH}px" role="menu">
    <div class="kopf">
      {#if stack.length > 1}
        <button class="zurueck" onclick={() => stack = stack.slice(0, -1)} title="Zurück"><i class="fa-solid fa-chevron-left"></i></button>
      {/if}
      <span class="t">{stack.length > 1 ? level.title : title}</span>
    </div>
    <div class="eintraege">
      {#each level.items as item, i (i)}
        {#if item.trenner}<hr />
        {:else}
          <button role="menuitem" class:gefahr={item.danger} onclick={() => choose(item)}>
            <i class="fa-solid {item.icon || 'fa-angle-right'}"></i> <span class="name">{item.label}</span>
            {#if item.items}<i class="fa-solid fa-chevron-right nach"></i>
            {:else if item.hint}<span class="nach tv-schwach">{item.hint}</span>{/if}
          </button>
        {/if}
      {/each}
      {#if !level.items.length}<div class="tv-schwach leer">Nichts zur Auswahl</div>{/if}
    </div>
  </div>
{/if}

<style>
  .hintergrund { position: fixed; inset: 0; z-index: 90; }
  .menue { position: fixed; z-index: 91; padding: 6px; background: var(--tv-karte-2); border: 1px solid var(--tv-rand-stark);
           border-radius: var(--tv-ecke); box-shadow: var(--tv-schatten); }
  .kopf { display: flex; align-items: center; gap: var(--tv-a2); padding: 6px 10px 8px; border-bottom: 1px solid var(--tv-rand); margin-bottom: 4px; }
  .kopf .t { font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .zurueck { width: 28px; height: 28px; flex: none; border: 0; background: none; color: var(--tv-text-2); cursor: pointer; border-radius: var(--tv-ecke-klein); }
  .zurueck:hover { background: var(--tv-karte-3); color: var(--tv-text); }
  .eintraege { max-height: 380px; overflow-y: auto; }
  button[role="menuitem"] { display: flex; align-items: center; gap: var(--tv-a3); width: 100%; padding: 9px 10px; border: 0; background: none;
                            color: var(--tv-text); font: inherit; text-align: left; border-radius: var(--tv-ecke-klein); cursor: pointer; }
  button[role="menuitem"]:hover { background: var(--tv-karte-3); }
  button[role="menuitem"] > i:first-child { width: 18px; color: var(--tv-text-2); }
  .name { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .nach { margin-left: auto; color: var(--tv-text-3); font-size: var(--tv-gr-klein); }
  .gefahr, .gefahr > i:first-child { color: var(--tv-gefahr); }
  hr { border: 0; border-top: 1px solid var(--tv-rand); margin: 6px 4px; }
  .leer { padding: 9px 10px; }
</style>

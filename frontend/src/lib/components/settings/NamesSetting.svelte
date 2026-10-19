<!--
  Einstellung der Art names: eine Liste von Namen (gespeichert als JSON-Liste,
  Namen dürfen Kommas tragen). Eingetragene stehen als Marken mit x zum
  Entfernen; neue kommen über das Feld (Eingabetaste) oder aus den Vorschlägen,
  die options_from liefert ({ options: [{ value, label, hint }], state }).
  Tippen grenzt die Vorschläge ein. Jede Änderung gilt sofort (onSave); danach
  holen alle Listen dieser Art ihre Vorschläge neu (sie hängen voneinander ab,
  z.B. nie und immer trennen).
-->
<script>
  import { api } from '../../api/client.js';

  const SHOWN = 12;                 // so viele Vorschläge auf einmal
  const CHANGED = 'tubevault:namensliste-geaendert';

  let { def, value, onSave = async () => {} } = $props();

  let typed = $state('');
  let offer = $state({ options: [], state: '' });

  let names = $derived(parse(value));
  let taken = $derived(new Set(names.map((n) => n.toLocaleLowerCase('de'))));
  let matching = $derived(offer.options.filter((o) => !taken.has(o.value.toLocaleLowerCase('de'))
                                                && o.label.toLocaleLowerCase('de').includes(typed.trim().toLocaleLowerCase('de'))));
  let note = $derived([matching.length > SHOWN ? `noch ${(matching.length - SHOWN).toLocaleString('de-DE')} Vorschläge, tippen grenzt ein` : '',
                       offer.state].filter(Boolean).join(' · '));

  function parse(raw) {
    try {
      const list = JSON.parse(raw || '[]');
      return Array.isArray(list) ? list.filter((n) => typeof n === 'string' && n.trim()) : [];
    } catch { return []; }
  }

  async function loadOffer() {
    if (!def.options_from) return;
    try { offer = await api.request(def.options_from); }
    catch { offer = { options: [], state: 'Vorschläge nicht abrufbar' }; }
  }

  async function save(next) {
    await onSave(JSON.stringify(next));
    window.dispatchEvent(new CustomEvent(CHANGED));
  }

  function add(name) {
    const clean = name.trim().replace(/\s+/g, ' ');
    if (!clean || taken.has(clean.toLocaleLowerCase('de'))) return;
    typed = '';
    save([...names, clean]);
  }

  const remove = (name) => save(names.filter((n) => n !== name));

  $effect(() => {
    loadOffer();
    window.addEventListener(CHANGED, loadOffer);
    return () => window.removeEventListener(CHANGED, loadOffer);
  });
</script>

<div class="namen">
  <div class="eingetragen">
    {#each names as name (name)}
      <span class="marke"><span class="text" title={name}>{name}</span>
        <button class="weg" onclick={() => remove(name)} aria-label="{name} entfernen" title="Entfernen"><i class="fa-solid fa-xmark"></i></button></span>
    {:else}
      <span class="leer">Noch keine Einträge</span>
    {/each}
  </div>

  <form class="feld" onsubmit={(e) => { e.preventDefault(); add(typed); }}>
    <input class="tv-eingabe" bind:value={typed} maxlength="200" placeholder="Name eintragen oder Vorschläge suchen" />
    <button class="tv-knopf klein" type="submit" disabled={!typed.trim()}><i class="fa-solid fa-plus"></i> Eintragen</button>
  </form>

  {#if matching.length}
    <div class="vorschlaege" aria-label="Vorschläge">
      {#each matching.slice(0, SHOWN) as option (option.value)}
        <button class="tv-chip" onclick={() => add(option.value)} title={option.hint}>
          <i class="fa-solid fa-plus"></i><span class="text">{option.label}</span><span class="hinweis">{option.hint}</span></button>
      {/each}
    </div>
  {/if}
  {#if note}<div class="stand">{note}</div>{/if}
</div>

<style>
  .namen { display: flex; flex-direction: column; gap: var(--tv-a2); min-width: 0; }
  .eingetragen, .vorschlaege { display: flex; flex-wrap: wrap; gap: var(--tv-a2); min-width: 0; }
  .marke { display: inline-flex; align-items: center; gap: 4px; max-width: 100%; height: 34px; padding: 0 4px 0 var(--tv-a3);
           border-radius: var(--tv-ecke); background: rgba(var(--tv-akzent-rgb), 0.12); color: var(--tv-akzent);
           font-size: var(--tv-gr-klein); font-weight: 600; }
  .text { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .weg { width: 28px; height: 28px; flex: none; border: 0; border-radius: var(--tv-ecke-klein); background: none;
         color: inherit; cursor: pointer; }
  .weg:hover { background: rgba(var(--tv-akzent-rgb), 0.2); }
  .leer { color: var(--tv-text-3); font-size: var(--tv-gr-klein); line-height: 34px; }
  .feld { display: flex; gap: var(--tv-a2); }
  .feld input { flex: 1; min-width: 0; }
  .vorschlaege .tv-chip { max-width: 100%; }
  .hinweis { color: var(--tv-text-3); font-size: var(--tv-gr-marke); white-space: nowrap; }
  .stand { font-size: var(--tv-gr-klein); color: var(--tv-text-3); }
</style>

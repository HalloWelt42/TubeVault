<!--
  Eine Einstellung als Zeile (Gestaltung nach mockups/einstellungen.html):
  Bezeichnung links (Erklärung beim Überfahren), Bedienelement in fester
  Spalte rechts. Art, Grenzen und Auswahl kommen aus dem Einstellungs-Schema.
    toggle    Schalter
    duration  Zahl mit Einheit Stunden oder Tage (gespeichert in Sekunden)
    number    Zahl; mit zero_label zusätzlich "ohne Grenze" (gespeichert als 0)
    select    Auswahl
    text      Textfeld
-->
<script>
  let { def, value, onSave = () => {} } = $props();

  const HOUR = 3600, DAY = 86400;

  // Dauer: in Tagen zeigen, wenn glatt teilbar, sonst in Stunden
  let durationUnit = $derived(Number(value) % DAY === 0 ? DAY : HOUR);
  let durationAmount = $derived(Number(value) / durationUnit);

  function saveDuration(amount, unit) {
    const seconds = Math.round(Number(amount) * unit);
    if (seconds > 0) onSave(seconds);
  }

  let unlimited = $derived(def.zero_label && Number(value) === 0);
  // Was beim Ausschalten von "ohne Grenze" eingetragen wird
  let fallback = $derived(Number(def.default) > 0 ? def.default : (def.min || 1));
</script>

<div class="einstellung">
  <div class="name" title={def.description || ''}>
    {def.label}
    {#if def.description}<i class="fa-solid fa-circle-info info"></i>{/if}
  </div>
  <div class="wert">
    {#if def.kind === 'toggle'}
      <button class="tv-schalter" class:an={value === 'true'} aria-pressed={value === 'true'}
              onclick={() => onSave(value === 'true' ? 'false' : 'true')} title={def.label}></button>

    {:else if def.kind === 'duration'}
      <input class="tv-eingabe zahl kurz" type="number" min="1" value={durationAmount}
             onchange={(e) => saveDuration(e.target.value, durationUnit)} />
      <select class="tv-eingabe einheit" value={durationUnit} onchange={(e) => saveDuration(durationAmount, Number(e.target.value))}>
        <option value={HOUR}>Stunden</option>
        <option value={DAY}>Tage</option>
      </select>

    {:else if def.kind === 'number'}
      {#if !unlimited}
        <input class="tv-eingabe zahl kurz" type="number" min={def.zero_label ? 1 : def.min} max={def.max} step={def.step ?? 1}
               value={value} onchange={(e) => onSave(e.target.value)} />
        {#if def.unit}<span class="einheit-text">{def.unit}</span>{/if}
      {/if}
      {#if def.zero_label}
        <label class="ohne-grenze">
          <button class="tv-schalter" class:an={unlimited} aria-pressed={unlimited}
                  onclick={() => onSave(unlimited ? fallback : 0)} title="{def.zero_label} ein oder aus"></button>
          {def.zero_label}
        </label>
      {/if}

    {:else if def.kind === 'select'}
      <select class="tv-eingabe" value={value} onchange={(e) => onSave(e.target.value)}>
        {#each def.options as option}<option value={option}>{def.option_labels?.[option] || option}</option>{/each}
      </select>

    {:else}
      <input class="tv-eingabe text" type="text" value={value} onchange={(e) => onSave(e.target.value)} />
    {/if}
  </div>
</div>

<style>
  .einstellung {
    display: grid; grid-template-columns: minmax(0, 1fr) 300px; align-items: center; gap: var(--tv-a4);
    min-height: 56px; padding: var(--tv-a2) var(--tv-a4); border-top: 1px solid var(--tv-rand);
  }
  .einstellung:first-of-type { border-top: 0; }
  .name { font-weight: 600; }
  .info { margin-left: 6px; font-size: 14px; color: var(--tv-text-3); cursor: help; }
  .wert { display: flex; gap: var(--tv-a2); justify-content: flex-end; align-items: center; }
  .wert .kurz { width: 100px; text-align: right; }
  .wert .einheit { width: 120px; }
  .wert select.tv-eingabe { width: 140px; }
  .wert .text { width: 100%; }
  .einheit-text { font-size: var(--tv-gr-klein); color: var(--tv-text-2); }
  .ohne-grenze { display: flex; align-items: center; gap: var(--tv-a2); font-size: var(--tv-gr-klein); color: var(--tv-text-2); white-space: nowrap; }
</style>

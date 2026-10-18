<!--
  Name mit Stift zum Umbenennen, an Ort und Stelle: der Stift macht aus dem
  Namen ein Feld; Eingabetaste oder Haken speichert, Escape oder Kreuz
  verwirft (am Handy gibt es kein Escape). Steht in der Überschrift und
  übernimmt deren Schrift; Rechner und Handy. onSave(name) prüft und
  speichert; lehnt es ab (z.B. leerer Name), bleibt das Feld mit Hinweis offen.
-->
<script>
  import { toast } from '../../stores/notifications.js';

  let { name, onSave } = $props();

  let editing = $state(false);
  let value = $state('');
  let busy = $state(false);

  function start() {
    value = name;
    editing = true;
  }

  async function save() {
    if (busy) return;
    if (value === name) { editing = false; return; }
    busy = true;
    try {
      await onSave(value);
      editing = false;
      toast.success('Umbenannt');
    } catch (e) { toast.error(e.message); }
    finally { busy = false; }
  }

  function onKey(e) {
    if (e.key === 'Enter') { e.preventDefault(); save(); }
    else if (e.key === 'Escape') { e.preventDefault(); editing = false; }
  }

  const focus = (node) => { node.focus(); node.select(); };
</script>

{#if editing}
  <span class="feld">
    <input bind:value onkeydown={onKey} use:focus maxlength="120" enterkeyhint="done" aria-label="Neuer Name" disabled={busy} />
    <button class="taste" onclick={save} disabled={busy} title="Speichern (Eingabetaste)" aria-label="Speichern">
      <i class="fa-solid fa-check"></i></button>
    <button class="taste" onclick={() => editing = false} disabled={busy} title="Verwerfen (Escape)" aria-label="Verwerfen">
      <i class="fa-solid fa-xmark"></i></button>
  </span>
{:else}
  <span class="anzeige">
    <span class="name">{name}</span>
    <button class="taste stift" onclick={start} title="Umbenennen" aria-label="Umbenennen"><i class="fa-solid fa-pen"></i></button>
  </span>
{/if}

<style>
  .anzeige, .feld { display: flex; align-items: center; gap: 6px; min-width: 0; }
  .name { min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  input { flex: 1; min-width: 0; height: 1.8em; padding: 0 8px; border: 1px solid rgba(var(--tv-akzent-rgb), 0.6);
          border-radius: var(--tv-ecke-klein); background: var(--tv-mulde); color: var(--tv-text); font: inherit; }
  input:focus { outline: none; }
  .taste { flex: none; width: 36px; height: 36px; display: grid; place-items: center; border: 0; border-radius: var(--tv-ecke);
           background: none; color: var(--tv-text-2); font-size: 15px; cursor: pointer; }
  .taste:hover { color: var(--tv-text); background: var(--tv-karte-2); }
  .stift { color: var(--tv-text-3); }
</style>

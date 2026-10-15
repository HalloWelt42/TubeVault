<!--
  Bestätigung direkt an der Stelle (kein Browser-Dialog), wie in
  mockups/sammlung.css (.bestaetigen): Frage, gefährlicher Knopf, Zurück.
-->
<script>
  let { text, confirmLabel, cancelLabel = 'Zurück', onConfirm, onCancel } = $props();
</script>

<div class="bestaetigen" role="alertdialog" aria-label={text}>
  <i class="fa-solid fa-triangle-exclamation"></i>
  <span>{text}</span>
  <div class="rechts">
    <button class="tv-knopf klein voll" onclick={onConfirm}>{confirmLabel}</button>
    <button class="tv-knopf klein ohne" onclick={onCancel}>{cancelLabel}</button>
  </div>
</div>

<style>
  .bestaetigen { display: flex; align-items: center; gap: var(--tv-a3); flex-wrap: wrap; margin-top: var(--tv-a2);
                 padding: var(--tv-a3) var(--tv-a4); background: rgba(var(--tv-gefahr-rgb), 0.08);
                 border: 1px solid rgba(var(--tv-gefahr-rgb), 0.4); border-radius: var(--tv-ecke); font-size: var(--tv-gr-klein); }
  .bestaetigen > i { color: var(--tv-gefahr); }
  .bestaetigen > span { flex: 1 1 240px; min-width: 0; }
  .rechts { margin-left: auto; display: flex; gap: var(--tv-a2); }
  .tv-knopf.voll { background: var(--tv-gefahr); color: var(--tv-akzent-text); border-color: transparent; }
  .tv-knopf.voll:hover:not(:disabled) { background: var(--tv-gefahr); opacity: 0.88; }
</style>

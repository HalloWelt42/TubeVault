<!--
  TubeVault -  ConfirmDialog v1.6.3
  Wiederverwendbarer Bestätigungsdialog für destruktive Aktionen.
  Usage: <ConfirmDialog bind:this={confirmRef} />
         confirmRef.ask('Video löschen?', 'Unwiderruflich.').then(ok => ...)
  © HalloWelt42 -  Private Nutzung
-->
<script>
  let open = $state(false);
  let title = $state('');
  let message = $state('');
  let confirmLabel = $state('Löschen');
  let danger = $state(true);
  let _resolve = null;

  export function ask(t, msg = '', opts = {}) {
    title = t;
    message = msg;
    confirmLabel = opts.confirmLabel || 'Löschen';
    danger = opts.danger !== false;
    open = true;
    return new Promise(resolve => { _resolve = resolve; });
  }

  function confirm() { open = false; _resolve?.(true); _resolve = null; }
  function cancel() { open = false; _resolve?.(false); _resolve = null; }

  function onKeydown(e) {
    if (e.key === 'Escape') cancel();
    if (e.key === 'Enter') confirm();
  }
</script>

{#if open}
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="cd-overlay" onclick={cancel} onkeydown={onKeydown}>
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="cd-dialog" onclick={(e) => e.stopPropagation()}>
      <div class="cd-icon" class:cd-danger={danger}>
        <i class="fa-solid {danger ? 'fa-triangle-exclamation' : 'fa-circle-question'}"></i>
      </div>
      <h3 class="cd-title">{title}</h3>
      {#if message}<p class="cd-message">{message}</p>{/if}
      <div class="cd-actions">
        <button class="cd-btn cd-cancel" onclick={cancel}>Abbrechen</button>
        <button class="cd-btn" class:cd-btn-danger={danger} class:cd-btn-primary={!danger} onclick={confirm}>
          {confirmLabel}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .cd-overlay {
    position: fixed; inset: 0; background: rgba(0,0,0,0.6);
    z-index: 2000; display: flex; align-items: center; justify-content: center;
    animation: cdFade 0.12s ease;
  }
  @keyframes cdFade { from { opacity: 0; } }

  .cd-dialog {
    background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-radius: 16px; width: 340px; max-width: 90vw; padding: 28px 24px 20px;
    text-align: center; box-shadow: 0 20px 60px rgba(0,0,0,0.35);
  }

  .cd-icon { font-size: 2rem; margin-bottom: 12px; }
  .cd-icon.cd-danger { color: var(--status-error); }
  .cd-icon:not(.cd-danger) { color: var(--accent-primary); }

  .cd-title { font-size: 1rem; font-weight: 700; color: var(--text-primary); margin: 0 0 6px; }
  .cd-message { font-size: 0.82rem; color: var(--text-secondary); margin: 0 0 20px; line-height: 1.4; }

  .cd-actions { display: flex; gap: 8px; justify-content: center; }
  .cd-btn {
    padding: 8px 20px; border-radius: 8px; font-size: 0.82rem; font-weight: 600;
    cursor: pointer; border: none; transition: all 0.12s;
  }
  .cd-cancel { background: var(--bg-tertiary); color: var(--text-secondary); }
  .cd-cancel:hover { background: var(--border-primary); }
  .cd-btn-danger { background: var(--status-error); color: #fff; }
  .cd-btn-danger:hover { filter: brightness(1.1); }
  .cd-btn-primary { background: var(--accent-primary); color: #fff; }
  .cd-btn-primary:hover { filter: brightness(1.1); }
</style>

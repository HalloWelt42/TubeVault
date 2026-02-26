<script>
  import { toast } from '../../stores/notifications.js';

  const icons = {
    success: '<i class="fa-solid fa-check"></i>',
    error: '<i class="fa-solid fa-xmark"></i>',
    warning: '<i class="fa-solid fa-triangle-exclamation"></i>',
    info: '<i class="fa-solid fa-circle-info"></i>',
  };
</script>

<div class="toast-container">
  {#each $toast as t (t.id)}
    <div class="toast toast-{t.type}" role="alert">
      <span class="toast-icon">{@html icons[t.type] || icons.info}</span>
      <span class="toast-message">{t.message}</span>
      <button class="toast-close" title="Schließen" onclick={() => toast.remove(t.id)}><i class="fa-solid fa-xmark"></i></button>
    </div>
  {/each}
</div>

<style>
  .toast-container {
    position: fixed;
    top: 16px;
    right: 16px;
    z-index: 9999;
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-width: 420px;
  }

  .toast {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 16px;
    border-radius: 10px;
    border: 1px solid var(--border-primary);
    background: var(--bg-secondary);
    color: var(--text-primary);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
    animation: slideIn 0.25s ease-out;
    font-size: 0.9rem;
  }

  .toast-icon {
    font-size: 1.1rem;
    flex-shrink: 0;
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
  }

  .toast-success .toast-icon { color: var(--status-success); background: var(--status-success-bg); }
  .toast-error .toast-icon { color: var(--status-error); background: var(--status-error-bg); }
  .toast-warning .toast-icon { color: var(--status-warning); background: var(--status-warning-bg); }
  .toast-info .toast-icon { color: var(--status-info); background: var(--status-info-bg); }

  .toast-message { flex: 1; }

  .toast-close {
    background: none;
    border: none;
    color: var(--text-tertiary);
    cursor: pointer;
    font-size: 0.9rem;
    padding: 2px;
    line-height: 1;
  }
  .toast-close:hover { color: var(--text-primary); }

  @keyframes slideIn {
    from { transform: translateX(100%); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
  }
</style>

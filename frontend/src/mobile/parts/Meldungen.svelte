<!--
  Meldungen der gemeinsamen Benachrichtigungen (lib/stores/notifications.js)
  in der Mobil-Ansicht: unten, groß, mit Knopf für "Rückgängig". So kommen
  auch Meldungen aus gemeinsam genutztem Code am Handy an.
-->
<script>
  import { toast } from '../../lib/stores/notifications.js';

  const ICONS = { success: 'fa-check', error: 'fa-xmark', warning: 'fa-triangle-exclamation', info: 'fa-circle-info' };

  function run(t) {
    toast.remove(t.id);
    t.action.run();
  }
</script>

{#each $toast as t (t.id)}
  <div class="meldung {t.type}" role="status">
    <i class="fa-solid {ICONS[t.type] || ICONS.info}"></i>
    <span class="text">{t.message}</span>
    {#if t.action}
      <button class="aktion" onclick={() => run(t)}>{t.action.label}</button>
    {:else}
      <button class="zu" onclick={() => toast.remove(t.id)} aria-label="Schließen"><i class="fa-solid fa-xmark"></i></button>
    {/if}
  </div>
{/each}

<style>
  .meldung { display: flex; align-items: center; gap: 12px; min-height: 56px; padding: 6px 6px 6px 16px;
             border-radius: var(--m-radius); background: var(--tv-karte-3); box-shadow: var(--tv-schatten);
             font-size: 15px; font-weight: 600; }
  .meldung > i { color: var(--tv-info); }
  .meldung.success > i { color: var(--tv-erfolg); }
  .meldung.error > i { color: var(--tv-gefahr); }
  .meldung.warning > i { color: var(--tv-warnung); }
  .text { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; display: -webkit-box;
          -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; }
  .aktion { flex: none; min-height: 44px; padding: 0 14px; border-radius: var(--m-radius);
            color: var(--m-accent); font-weight: 700; }
  .aktion:active { background: rgba(var(--tv-akzent-rgb), 0.14); }
  .zu { flex: none; width: 44px; height: 44px; color: var(--m-faint); }
</style>

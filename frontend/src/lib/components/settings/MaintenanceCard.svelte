<!--
  Wartung (Einstellungen, Abschnitt System): Datenbank bereinigen mit Protokoll,
  Anmeldedaten der Quelle (cookies.txt), Videos für Telefone umpacken,
  alle Einstellungen zurücksetzen.
-->
<script>
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';
  import { formatSize } from '../../utils/format.js';

  let { confirm, onReset = () => {} } = $props();   // confirm: ConfirmDialog.ask

  let cleaning = $state(false);
  let protocol = $state(null);
  let cookies = $state(null);
  let cookiesBusy = $state(false);

  let repack = $state(null);          // { candidates, size_bytes }: Videos in mkv oder webm
  let repacking = $state(false);

  $effect(() => { api.getCookiesStatus().then(s => cookies = s).catch(() => {}); });
  $effect(() => { api.getRepackPreview().then(r => repack = r).catch(() => {}); });

  const videosText = (count) => (count === 1 ? '1 Video' : `${count} Videos`);

  async function repackAll() {
    if (!await confirm('Für Telefone umpacken?',
      `${videosText(repack.candidates)} in mkv oder webm werden geprüft. Steckt H.264 drin, entsteht ohne Neukodieren `
      + 'eine mp4-Fassung neben dem Original; das Original bleibt. AV1 und VP9 bleiben liegen und lassen sich '
      + 'beim Abspielen einzeln umwandeln.', { confirmLabel: 'Umpacken' })) return;
    repacking = true;
    try {
      await api.repackAll();
      toast.success('Umpacken läuft, Fortschritt unter Aktivitäten');
      repack = await api.getRepackPreview();
    }
    catch (e) { toast.error(e.message); }
    repacking = false;
  }

  async function fullCleanup() {
    cleaning = true;
    protocol = null;
    try {
      protocol = await api.cleanupFull();
      toast.success(`Bereinigt: ${protocol.totals.cleaned} Einträge, ${protocol.totals.freed_human} frei`);
    } catch (e) { toast.error(e.message); }
    cleaning = false;
  }

  async function uploadCookies(e) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    cookiesBusy = true;
    try { cookies = await api.uploadCookies(file); toast.success('Anmeldedaten übernommen'); }
    catch (err) { toast.error(err.message); }
    cookiesBusy = false;
  }

  async function deleteCookies() {
    if (!await confirm('Anmeldedaten entfernen?', 'Die hinterlegte cookies.txt wird gelöscht.', { confirmLabel: 'Entfernen' })) return;
    cookiesBusy = true;
    try { await api.deleteCookies(); cookies = { present: false }; toast.info('Anmeldedaten entfernt'); }
    catch (err) { toast.error(err.message); }
    cookiesBusy = false;
  }

  async function resetAll() {
    if (!await confirm('Alle Einstellungen zurücksetzen?', 'Alle Werte gehen auf ihren Standard.', { confirmLabel: 'Zurücksetzen' })) return;
    try { await api.resetSettings(); toast.success('Zurückgesetzt'); onReset(); }
    catch (e) { toast.error(e.message); }
  }
</script>

<section class="tv-karte">
  <h3><i class="fa-solid fa-key"></i> Anmeldedaten der Quelle <span class="tv-schwach tv-klein">wahlweise</span></h3>
  <p class="tv-leise tv-klein">Eine angemeldete Sitzung (cookies.txt im Netscape-Format) hilft, wenn die Quelle hartnäckig sperrt.</p>
  <div class="zeile">
    {#if cookies?.present}
      <span class="tv-zustand fertig"><i class="fa-solid fa-check"></i> hinterlegt, <span class="zahl">{cookies.cookie_count || 0}</span> Einträge</span>
      <label class="tv-knopf klein"><i class="fa-solid fa-upload"></i> Ersetzen
        <input type="file" accept=".txt" onchange={uploadCookies} hidden /></label>
      <button class="tv-knopf klein gefahr" onclick={deleteCookies} disabled={cookiesBusy}><i class="fa-solid fa-trash-can"></i> Entfernen</button>
    {:else}
      <span class="tv-zustand">nicht hinterlegt</span>
      <label class="tv-knopf klein"><i class="fa-solid {cookiesBusy ? 'fa-spinner fa-spin' : 'fa-upload'}"></i> cookies.txt hochladen
        <input type="file" accept=".txt" onchange={uploadCookies} hidden /></label>
    {/if}
  </div>
</section>

<section class="tv-karte">
  <h3><i class="fa-solid fa-broom"></i> Wartung</h3>
  <div class="zeile">
    <button class="tv-knopf klein" onclick={fullCleanup} disabled={cleaning}>
      <i class="fa-solid {cleaning ? 'fa-spinner fa-spin' : 'fa-broom'}"></i> {cleaning ? 'Bereinigt ...' : 'Datenbank bereinigen'}</button>
    <span class="tv-schwach tv-klein">Einträge ohne Datei, verwaiste Zuordnungen, alte Aufträge, Zwischenablage, Verdichten</span>
  </div>
  {#if repack?.candidates}
    <div class="zeile">
      <button class="tv-knopf klein" onclick={repackAll} disabled={repacking}>
        <i class="fa-solid {repacking ? 'fa-spinner fa-spin' : 'fa-mobile-screen'}"></i> Für Telefone umpacken</button>
      <span class="tv-schwach tv-klein"><span class="zahl">{videosText(repack.candidates)}</span> in mkv oder webm
        (<span class="zahl">{formatSize(repack.size_bytes)}</span>), die manche Telefone nicht abspielen</span>
    </div>
  {/if}
  {#if protocol}
    <div class="protokoll">
      <div class="tv-etikett">Protokoll · <span class="zahl">{protocol.totals.cleaned} bereinigt, {protocol.totals.freed_human} frei</span></div>
      {#each protocol.protocol as step}
        <div class="schritt tv-klein" class:wirkung={step.count > 0 || step.freed > 0}>
          <i class="fa-solid {step.count > 0 || step.freed > 0 ? 'fa-check' : 'fa-minus'}"></i> {step.detail}</div>
      {/each}
    </div>
  {/if}
  <div class="zeile gefahrzone">
    <button class="tv-knopf klein gefahr" onclick={resetAll}><i class="fa-solid fa-rotate-left"></i> Alle Einstellungen zurücksetzen</button>
  </div>
</section>

<style>
  .zeile { display: flex; align-items: center; gap: var(--tv-a2); flex-wrap: wrap; margin-top: var(--tv-a2); }
  .protokoll { margin-top: var(--tv-a3); }
  .schritt { padding: 2px 0; color: var(--tv-text-3); }
  .schritt.wirkung { color: var(--tv-text); }
  .schritt.wirkung i { color: var(--tv-erfolg); }
  .gefahrzone { margin-top: var(--tv-a4); padding-top: var(--tv-a3); border-top: 1px solid var(--tv-rand); }
</style>

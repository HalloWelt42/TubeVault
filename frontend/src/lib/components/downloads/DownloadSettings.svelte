<!--
  Karte "Laden": Drosselung und Pause zwischen Downloads, wirken sofort.
-->
<script>
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';

  let { currentThrottleLive = 0 } = $props();   // Wert der dynamischen Drosselung, live

  const THROTTLE_DEFAULT = 0;
  const COOLDOWN_DEFAULT = 30;
  let throttleKbps = $state(0);
  let throttleRealtime = $state(false);
  let cooldownSec = $state(30);
  let saving = $state(false);

  async function load() {
    const [t, r, c] = await Promise.all([
      api.getSetting('download.throttle_kbps').catch(() => ({ value: 0 })),
      api.getSetting('download.throttle_realtime').catch(() => ({ value: 'false' })),
      api.getSetting('download.cooldown_base_s').catch(() => ({ value: 30 })),
    ]);
    throttleKbps = parseInt(t?.value || 0) || 0;
    throttleRealtime = String(r?.value).toLowerCase() === 'true';
    cooldownSec = parseInt(c?.value || 30) || 30;
  }
  $effect(() => { load(); });

  async function saveThrottle() {
    saving = true;
    try {
      await api.setDownloadThrottle(throttleKbps, throttleRealtime);
      if (throttleRealtime) toast.success('Drosselung: so schnell, wie das Video läuft');
      else if (throttleKbps > 0) toast.success(`Drosselung: ${throttleKbps} KB/s`);
      else toast.success('Drosselung aus');
    } catch (e) { toast.error(e.message); }
    saving = false;
  }

  async function toggleRealtime() {
    throttleRealtime = !throttleRealtime;
    await saveThrottle();
  }

  async function saveCooldown(value) {
    const num = parseInt(value);
    if (isNaN(num) || num < 5 || num > 3600) {
      toast.error('Pause: 5 bis 3600 Sekunden');
      cooldownSec = cooldownSec >= 5 ? cooldownSec : COOLDOWN_DEFAULT;
      return;
    }
    saving = true;
    try {
      cooldownSec = (await api.setDownloadCooldown(num)).cooldown_base_s;   // was gespeichert wurde
      toast.success(`Pause: ${cooldownSec} s zwischen Downloads`);
    } catch (e) { toast.error(e.message); }
    saving = false;
  }

  function resetDefaults() {
    throttleKbps = THROTTLE_DEFAULT;
    throttleRealtime = false;
    saveThrottle();
    saveCooldown(COOLDOWN_DEFAULT);
  }
</script>

<section class="tv-karte">
  <h3><i class="fa-solid fa-sliders"></i> Laden <span class="tv-leise tv-klein">wirkt sofort</span></h3>
  <div class="zeile">
    <div><div class="name">Drosselung</div>
      <div class="erklaerung">{#if throttleRealtime}{currentThrottleLive > 0 ? `gerade ${currentThrottleLive.toLocaleString('de-DE')} KB/s` : 'wartet auf einen Download'}{:else}höchstens so schnell laden; 0 = ohne Grenze{/if}</div></div>
    <div class="wert">
      <input class="tv-eingabe zahl" type="number" min="0" max="100000" step="100"
             value={throttleRealtime ? (currentThrottleLive || '') : throttleKbps}
             disabled={saving || throttleRealtime}
             oninput={(e) => { throttleKbps = parseInt(e.target.value) || 0; }}
             onblur={() => !throttleRealtime && saveThrottle()}
             onkeydown={(e) => e.key === 'Enter' && !throttleRealtime && saveThrottle()} />
      <span class="einheit">KB/s</span>
    </div>
  </div>
  <div class="zeile">
    <div><div class="name">Dynamisch</div><div class="erklaerung">So schnell, wie das Video läuft</div></div>
    <div class="wert"><button class="tv-schalter" class:an={throttleRealtime} onclick={toggleRealtime} disabled={saving}
                              aria-pressed={throttleRealtime} title="Dynamische Drosselung ein oder aus"></button></div>
  </div>
  <div class="zeile">
    <div><div class="name">Pause zwischen Downloads</div><div class="erklaerung">Schont die Quelle, mindestens 5 Sekunden</div></div>
    <div class="wert">
      <input class="tv-eingabe zahl" type="number" min="5" max="3600" step="5" bind:value={cooldownSec} disabled={saving}
             onblur={() => saveCooldown(cooldownSec)} onkeydown={(e) => e.key === 'Enter' && saveCooldown(cooldownSec)} />
      <span class="einheit">s</span>
    </div>
  </div>
  <button class="tv-knopf ohne klein" onclick={resetDefaults} title="Drosselung aus, Pause 30 s"><i class="fa-solid fa-rotate-left"></i> Standardwerte</button>
</section>

<style>
  .zeile { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--tv-a3); align-items: center; padding: var(--tv-a3) 0; border-top: 1px solid var(--tv-rand); }
  .zeile:first-of-type { border-top: 0; padding-top: 0; }
  .name { font-weight: 600; }
  .erklaerung { font-size: var(--tv-gr-klein); color: var(--tv-text-3); }
  .wert { display: flex; gap: 6px; align-items: center; }
  .wert .tv-eingabe { width: 96px; text-align: right; }
  .einheit { font-size: var(--tv-gr-klein); color: var(--tv-text-2); min-width: 36px; }
  h3 .tv-leise { margin-left: auto; font-weight: 500; }
</style>

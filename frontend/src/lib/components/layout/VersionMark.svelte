<!--
  Copyright und laufende Version unten in der Seitenleiste. Ist schon eine
  neuere Version ausgeliefert (utils/versionWatch.js), kommt "neu laden" dazu.
-->
<script>
  import { FE_VERSION } from '../../api/client.js';
  import { newVersion, reloadNow } from '../../utils/versionWatch.js';
</script>

<span class="marke">
  © HalloWelt42 ·
  <span class="led" class:neu={!!$newVersion}></span>
  <span class="zahl" title={$newVersion ? `Version ${FE_VERSION}, ausgeliefert ist ${$newVersion}` : 'Laufende Version'}>{FE_VERSION}</span>
  {#if $newVersion}
    · <button onclick={reloadNow} title="Neue Version {$newVersion} laden">neu laden</button>
  {/if}
</span>

<style>
  .marke { display: inline-flex; align-items: center; gap: 5px; flex-wrap: wrap; }
  .led { width: 7px; height: 7px; border-radius: 50%; background: var(--tv-erfolg); }
  .led.neu { background: var(--tv-warnung); }
  button { border: 0; padding: 0; background: none; color: var(--tv-akzent); font: inherit; font-weight: 700; cursor: pointer; }
</style>

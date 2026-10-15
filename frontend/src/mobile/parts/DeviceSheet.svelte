<!--
  Blatt "Abspielen auf" am Handy: die Geräteliste (lib/components/remote/
  DeviceList.svelte) von unten eingeblendet. Steuern öffnet die Fernbedienung.
-->
<script>
  import DeviceList from '../../lib/components/remote/DeviceList.svelte';
  import { go } from '../router.js';

  let { onClose } = $props();
</script>

<div class="schleier" role="presentation" onclick={onClose}></div>
<div class="blatt" role="dialog" aria-label="Abspielen auf">
  <div class="griff"></div>
  <DeviceList onControl={(device) => go('/fern', { id: device.id })} onDone={onClose} />
</div>

<style>
  .schleier { position: fixed; inset: 0; z-index: 80; background: rgba(0, 0, 0, 0.55); }
  .blatt { position: fixed; left: 0; right: 0; bottom: 0; z-index: 81; max-height: 85vh; overflow-y: auto;
           padding: 10px 14px calc(var(--m-safe-bottom) + 18px); background: var(--m-surface-2);
           border-radius: 14px 14px 0 0; }
  .griff { width: 44px; height: 5px; margin: 0 auto 12px; border-radius: 3px; background: var(--m-line); }
</style>

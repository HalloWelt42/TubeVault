<!--
  Kopf der Kanalseite (Entwurf mockups/kanal.html): Kanalbild, Name mit
  Medaille, Sprache und Merkmalen, darunter Katalog, lokal, Scan und
  Prüfabstand; rechts Ganz scannen (bzw. der laufende Scan) und
  Einstellungen, ohne Abo stattdessen Abonnieren. Darunter die Störung, wenn
  der Kanal gesperrt ist.
-->
<script>
  import { api } from '../../api/client.js';
  import { navigate } from '../../router/router.js';
  import { formatDate } from '../../utils/format.js';
  import LanguageLabel from '../common/LanguageLabel.svelte';
  import { coverageTitle, intervalText, isScanned, medalOf, medalStyle, num } from './channelView.js';

  /** scan: { running, label }; on*: Aktionen der Seite */
  let { channel, scan, subscribing = false, onscan, oncancel, onsettings, onsubscribe, onunlock } = $props();

  let medal = $derived(medalOf(channel));
  let blocked = $derived(channel.subscribed && (!channel.enabled || channel.error_count > 0));
  let sourceUrl = $derived(`https://www.youtube.com/channel/${channel.channel_id}`);
</script>

<div class="kopf">
  <button class="tv-knopf ohne symbol" onclick={() => navigate('/subscriptions')} title="Zurück zu den Kanälen" aria-label="Zurück">
    <i class="fa-solid fa-arrow-left"></i></button>
  {#if channel.avatar_path}
    <img class="bild" src={api.channelAvatarUrl(channel.channel_id)} alt="" />
  {:else}
    <span class="bild ersatz">{(channel.channel_name || '?')[0].toUpperCase()}</span>
  {/if}
  <div class="titel">
    <div class="namezeile">
      <h1>{channel.channel_name || channel.channel_id}</h1>
      {#if medal}
        <span class="medaille" style={medalStyle(channel)} title={coverageTitle(channel)}><i class="fa-solid fa-medal"></i> {medal.label}</span>
      {/if}
      <LanguageLabel code={channel.language} channel />
      {#if channel.auto_download}<span class="merkmal an" title="Neue Videos werden selbst geladen"><i class="fa-solid fa-bolt"></i> Auto-Download</span>{/if}
      {#if channel.music_channel}<span class="merkmal musik" title="Alle Videos gelten als Musik"><i class="fa-solid fa-music"></i> Musikkanal</span>{/if}
      {#if channel.audio_only}<span class="merkmal" title="Lädt nur den Ton"><i class="fa-solid fa-podcast"></i> Nur Ton</span>{/if}
    </div>
    <div class="angaben">
      <span><span class="zahl">{num(channel.rss_entry_count)}</span> im Katalog</span>
      <span><span class="zahl">{num(channel.downloaded_count)}</span> lokal</span>
      {#if !channel.subscribed}
        <span>nicht abonniert</span>
      {:else if isScanned(channel)}
        <span>ganz gescannt <span class="zahl">{formatDate(channel.last_scanned)}</span></span>
      {:else}
        <span>noch nicht ganz gescannt</span>
      {/if}
      {#if channel.subscribed && channel.check_interval}
        <span title="Der Prüfabstand richtet sich nach dem Alter des neuesten Videos">prüft alle <span class="zahl">{intervalText(channel.check_interval)}</span></span>
      {/if}
    </div>
  </div>
  <div class="aktionen">
    {#if !channel.subscribed}
      <button class="tv-knopf haupt" onclick={onsubscribe} disabled={subscribing}><i class="fa-solid fa-rss"></i> Abonnieren</button>
    {:else}
      {#if scan.running}
        <span class="scanstand"><i class="fa-solid fa-satellite-dish fa-fade"></i> {scan.label}
          <button class="tv-knopf ohne klein" onclick={oncancel} title="Abbrechen - schon Gefundenes bleibt erhalten">
            <i class="fa-solid fa-stop"></i> Abbrechen</button></span>
      {:else}
        <button class="tv-knopf" onclick={onscan} title="Alle Videos des Kanals einlesen, nicht nur die neuesten. Erst danach gibt es eine Medaille.">
          <i class="fa-solid fa-satellite-dish"></i> Ganz scannen</button>
      {/if}
      <button class="tv-knopf" onclick={onsettings}><i class="fa-solid fa-sliders"></i> Einstellungen</button>
    {/if}
    <a class="tv-knopf ohne symbol" href={sourceUrl} target="_blank" rel="noopener" title="Kanal bei der Quelle öffnen" aria-label="Kanal bei der Quelle öffnen">
      <i class="fa-solid fa-arrow-up-right-from-square"></i></a>
  </div>
</div>

{#if blocked}
  <div class="stoerung">
    <i class="fa-solid fa-triangle-exclamation"></i>
    <div class="text">
      <b>{channel.enabled ? `${num(channel.error_count)} Fehler beim Prüfen` : channel.error_count > 0 ? `Gesperrt nach ${num(channel.error_count)} Fehlern beim Prüfen` : 'Prüfung abgeschaltet'}</b>
      {#if channel.last_error}<div class="grund">{channel.last_error}</div>{/if}
    </div>
    <button class="tv-knopf klein" onclick={onunlock}>
      <i class="fa-solid fa-lock-open"></i> {channel.enabled ? 'Zurücksetzen' : channel.error_count > 0 ? 'Entsperren' : 'Einschalten'}</button>
  </div>
{/if}

<style>
  .kopf { display: flex; align-items: center; gap: var(--tv-a4); margin-bottom: var(--tv-a4); flex-wrap: wrap; }
  .bild { width: 64px; height: 64px; flex: none; border-radius: var(--tv-ecke); object-fit: cover; background: var(--tv-mulde); }
  .ersatz { display: grid; place-items: center; font-size: 28px; font-weight: 700; color: var(--tv-akzent); background: rgba(var(--tv-akzent-rgb), 0.12); }
  .titel { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
  .namezeile { display: flex; align-items: center; gap: var(--tv-a2) var(--tv-a3); flex-wrap: wrap; }
  h1 { margin: 0; font-size: var(--tv-gr-seite); line-height: 1.15; min-width: 0; overflow-wrap: anywhere; }
  .medaille, .merkmal { display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 10px; border-radius: var(--tv-ecke-klein);
                        font-size: var(--tv-gr-marke); font-weight: 700; white-space: nowrap; }
  .medaille { color: var(--medaille); background: var(--medaille-grund); letter-spacing: 0.06em; text-transform: uppercase; cursor: help; }
  .merkmal { background: var(--tv-karte-2); color: var(--tv-text-2); }
  .merkmal.an { color: var(--tv-akzent); background: rgba(var(--tv-akzent-rgb), 0.12); }
  .merkmal.musik { color: var(--tv-art-musik); }
  .angaben { display: flex; flex-wrap: wrap; gap: var(--tv-a1) var(--tv-a4); font-size: var(--tv-gr-klein); color: var(--tv-text-2); }
  .angaben .zahl { color: var(--tv-text); }
  .aktionen { display: flex; align-items: center; gap: var(--tv-a2); flex-wrap: wrap; }
  .scanstand { display: inline-flex; align-items: center; gap: var(--tv-a3); height: 40px; padding: 0 var(--tv-a1) 0 var(--tv-a3);
               border-radius: var(--tv-ecke); background: rgba(var(--tv-akzent-rgb), 0.1); font-size: var(--tv-gr-klein); }
  .scanstand > i { color: var(--tv-akzent); }
  .stoerung { display: flex; align-items: center; gap: var(--tv-a3); padding: var(--tv-a3) var(--tv-a4); margin-bottom: var(--tv-a4);
              border-radius: var(--tv-ecke); background: rgba(var(--tv-gefahr-rgb), 0.1); border: 1px solid rgba(var(--tv-gefahr-rgb), 0.35); }
  .stoerung > i { color: var(--tv-gefahr); }
  .stoerung .text { flex: 1; min-width: 0; }
  .stoerung .grund { font-size: var(--tv-gr-klein); color: var(--tv-text-2); overflow-wrap: anywhere; }
</style>

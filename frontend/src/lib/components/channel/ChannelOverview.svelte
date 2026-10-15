<!--
  Oberer Teil des Rollfelds der Kanalseite (Entwurf mockups/kanal.html):
  Banner, aufklappbare Kanalbeschreibung, Abdeckung mit Medaille und Weg zur
  nächsten, dazu Belegt, Laufzeit lokal, Aufrufe und Playlists.
-->
<script>
  import { api } from '../../api/client.js';
  import { navigate } from '../../router/router.js';
  import { formatDescription, parseDescClick } from '../../utils/description.js';
  import { formatDurationLong, formatSize, formatViews } from '../../utils/format.js';
  import { coverageNote, coveragePercent, coverageShare, coverageTitle, medalOf, medalStyle, num } from './channelView.js';

  let { channel, playlistCount = 0 } = $props();

  let showBanner = $state(true);
  let showDescription = $state(false);
  let medal = $derived(medalOf(channel));

  // Links in der Beschreibung: verknüpfte Videos öffnen, Schlagwörter und Kennungen suchen
  function descriptionClick(event) {
    const link = parseDescClick(event);
    if (!link) return;
    if (link.type === 'open_video') navigate(`/watch/${link.value}`);
    else if (link.type === 'tag') navigate(`/search?q=${encodeURIComponent('#' + link.value)}`);
    else if (link.type === 'youtube') navigate(`/search?q=${encodeURIComponent(link.value)}`);
  }
</script>

{#if channel.banner_url && showBanner}
  <div class="banner"><img src={api.bannerUrl(channel.channel_id)} alt="" onerror={() => showBanner = false} /></div>
{/if}

{#if channel.channel_description}
  <div class="beschreibung">
    <button class="tv-knopf ohne klein" onclick={() => showDescription = !showDescription} aria-expanded={showDescription}>
      <i class="fa-solid {showDescription ? 'fa-chevron-down' : 'fa-chevron-right'}"></i> Kanalbeschreibung</button>
    {#if showDescription}
      <!-- formatDescription maskiert den Text und baut nur eigene Links -->
      <div class="text" onclick={descriptionClick} role="presentation">{@html formatDescription(channel.channel_description)}</div>
    {/if}
  </div>
{/if}

<div class="zahlen">
  {#if channel.subscribed && channel.wanted_count}
    <div class="abdeckung" title={coverageTitle(channel)}>
      <div class="oben">
        {#if medal}<span class="medaille" style={medalStyle(channel)}><i class="fa-solid fa-medal"></i> {medal.label}</span>{/if}
        <b class="zahl">{coveragePercent(channel)} %</b>
        <span class="tv-schwach tv-klein"><span class="zahl">{num(channel.have_count)}</span> von <span class="zahl">{num(channel.wanted_count)}</span> Videos</span>
      </div>
      <div class="balken" style={medalStyle(channel)}><b style:width="{coverageShare(channel) * 100}%"></b></div>
      <div class="satz">{coverageNote(channel)}</div>
    </div>
  {/if}
  {#if channel.total_downloaded_size > 0}
    <div class="tv-kennzahl"><b>{formatSize(channel.total_downloaded_size)}</b><span>Belegt</span></div>
  {/if}
  {#if channel.total_downloaded_duration > 0}
    <div class="tv-kennzahl"><b>{formatDurationLong(channel.total_downloaded_duration)}</b><span>Laufzeit lokal</span></div>
  {/if}
  {#if channel.total_views > 0}
    <div class="tv-kennzahl" title="Aufrufe aller Videos im Katalog"><b>{formatViews(channel.total_views)}</b><span>Aufrufe</span></div>
  {/if}
  {#if playlistCount > 0}
    <div class="tv-kennzahl"><b>{num(playlistCount)}</b><span>Playlists</span></div>
  {/if}
</div>

<style>
  .banner { height: 150px; border-radius: var(--tv-ecke); overflow: hidden; background: var(--tv-mulde); margin-bottom: var(--tv-a3); }
  .banner img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .beschreibung { margin-bottom: var(--tv-a4); }
  .beschreibung .text { margin-top: var(--tv-a2); padding: var(--tv-a3) var(--tv-a4); max-width: 900px; background: var(--tv-flaeche);
                        border-radius: var(--tv-ecke); color: var(--tv-text-2); overflow-wrap: anywhere; }
  .zahlen { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: var(--tv-a3); margin-bottom: var(--tv-a5); }
  .zahlen .tv-kennzahl { min-width: 0; }
  .abdeckung { grid-column: span 2; display: flex; flex-direction: column; gap: var(--tv-a2); padding: var(--tv-a3) var(--tv-a4);
               background: var(--tv-flaeche); border-radius: var(--tv-ecke); }
  .oben { display: flex; align-items: center; gap: var(--tv-a2) var(--tv-a3); flex-wrap: wrap; white-space: nowrap; }
  .oben b { font-size: 26px; font-weight: 600; line-height: 1.2; }
  .medaille { display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 10px; border-radius: var(--tv-ecke-klein);
              font-size: var(--tv-gr-marke); font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
              color: var(--medaille); background: var(--medaille-grund); }
  .balken { height: 6px; background: var(--tv-mulde); border-radius: 1px; overflow: hidden; }
  .balken b { display: block; height: 100%; background: var(--medaille, var(--tv-akzent)); }
  .satz { font-size: var(--tv-gr-klein); color: var(--tv-text-2); }

  @media (max-width: 700px) {
    .abdeckung { grid-column: auto; }
  }
</style>

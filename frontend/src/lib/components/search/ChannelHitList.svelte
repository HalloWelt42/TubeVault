<!--
  Gefundene Kanäle als Kacheln: Bild, Name (hervorgehoben), Treffer und ob abonniert.
-->
<script>
  import { api } from '../../api/client.js';
  import { navigate } from '../../router/router.js';
  import LanguageLabel from '../common/LanguageLabel.svelte';
  import Marked from './Marked.svelte';

  let { items = [], terms = [] } = $props();
</script>

<div class="kanaele">
  {#each items as channel (channel.channel_id)}
    <button class="kanal" onclick={() => navigate(`/channel/${channel.channel_id}`)} title="Kanal öffnen">
      <img src={api.channelAvatarUrl(channel.channel_id)} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
      <span class="text">
        <span class="name"><Marked text={channel.channel_name} {terms} /></span>
        <span class="zeile">
          {#if channel.videos}<span><span class="zahl">{channel.videos.toLocaleString('de-DE')}</span> Treffer</span>{/if}
          <span>{channel.subscribed ? 'abonniert' : 'in der Bibliothek'}</span>
          {#if channel.meaning}<span class="sinn"><i class="fa-solid fa-wand-magic-sparkles"></i> sinngemäß</span>{/if}
          <LanguageLabel code={channel.language} channel />
        </span>
      </span>
    </button>
  {/each}
</div>

<style>
  .kanaele { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: var(--tv-a3); }
  .kanal { display: grid; grid-template-columns: 48px minmax(0, 1fr); gap: var(--tv-a3); align-items: center; padding: var(--tv-a3);
           border: 0; border-radius: var(--tv-ecke); background: var(--tv-flaeche); color: var(--tv-text); font: inherit;
           text-align: left; cursor: pointer; }
  .kanal:hover { background: var(--tv-karte); }
  img { width: 48px; height: 48px; border-radius: 50%; object-fit: cover; background: var(--tv-karte-3); }
  .text { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .name { font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .zeile { display: flex; flex-wrap: wrap; gap: 4px 10px; align-items: center; font-size: var(--tv-gr-klein); color: var(--tv-text-3); }
  .sinn { color: var(--tv-info); }
</style>

<!--
  Ein Video als Zeile einer Sammlung: vorn Griff (Umordnen) oder Haken
  (Auswahl), Nummer oder Uhrzeit, Bild mit Fortschritt, Titel, Stand und
  beim Überfahren die Aktionen. Nicht angegebene Aktionen entfallen.
  Ziehen: draggable und die drag-Ereignisse gibt die Seite mit (...rest).
-->
<script>
  import { api } from '../../api/client.js';
  import { formatDuration } from '../../utils/format.js';

  let {
    item,                  // { id, title, channel_name, duration, position, progress, state }
    nr = null,
    time = null,           // statt der Nummer, z.B. Uhrzeit im Verlauf
    meta = null,           // weitere Angabe neben dem Kanal
    mode = null,           // 'ordnen' | 'auswahl' | null
    selected = false,
    lifted = false,        // wird gerade gezogen
    playing = false,
    showPosition = false,  // Stand als "bei 3:14 von 11:34" (Verlauf)
    onPlay,
    onNext = null,
    onRemove = null,
    removeTitle = 'Entfernen',
    onLoad = null,         // noch nicht geladen: jetzt laden
    onMenu = null,
    onToggle = null,
    ...rest
  } = $props();

  let rest_seconds = $derived(Math.max(0, (item.duration || 0) - (item.position || 0)));
</script>

<div class="zeile" class:gewaehlt={selected} class:gehoben={lifted} class:laeuft={playing} class:fehlt={item.loaded === false}
     class:mit-zeit={time !== null} role="listitem" {...rest}>
  {#if mode === 'auswahl'}
    <button class="haken" onclick={() => onToggle?.(item)} title={selected ? 'Abwählen' : 'Auswählen'}>
      <i class="fa-{selected ? 'solid fa-square-check' : 'regular fa-square'}"></i></button>
  {:else if mode === 'ordnen'}
    <span class="griff" title="Ziehen zum Umordnen"><i class="fa-solid fa-grip-vertical"></i></span>
  {:else}
    <span></span>
  {/if}

  <span class="nr zahl">{time ?? nr ?? ''}</span>

  <button class="bild" onclick={() => mode === 'auswahl' ? onToggle?.(item) : onPlay(item)} title="Abspielen">
    <img src={api.thumbnailUrl(item.id)} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
    {#if item.duration}<span class="dauer zahl">{formatDuration(item.duration)}</span>{/if}
    {#if item.progress > 0}
      <span class="fort" class:fertig={item.state === 'finished'}><b style:width="{Math.min(100, item.progress * 100)}%"></b></span>
    {/if}
  </button>

  <div class="text">
    <button class="titel" onclick={() => mode === 'auswahl' ? onToggle?.(item) : onPlay(item)}>{item.title}</button>
    <div class="meta"><span>{item.channel_name || ''}</span>{#if meta}<span class="zahl">{meta}</span>{/if}</div>
  </div>

  <div class="stand">
    {#if item.loaded === false}
      <span class="tv-zustand wartet"><i class="fa-solid fa-hourglass-half"></i> Noch nicht geladen</span>
    {:else if item.state === 'finished'}
      <span class="tv-zustand fertig"><i class="fa-solid fa-check"></i> {showPosition ? 'Zu Ende' : 'Gesehen'}</span>
    {:else if item.state === 'started'}
      {#if showPosition}
        bei <span class="zahl">{formatDuration(item.position)}</span> von <span class="zahl">{formatDuration(item.duration)}</span>
      {:else}
        <span class="zahl">{Math.round(item.progress * 100)} %</span> · noch <span class="zahl">{formatDuration(rest_seconds)}</span>
      {/if}
    {:else}
      <span class="tv-schwach">Neu</span>
    {/if}
  </div>

  <div class="tun">
    {#if mode !== 'auswahl' && item.loaded === false}
      {#if onLoad}<button class="spielen" onclick={() => onLoad(item)} title="Jetzt laden"><i class="fa-solid fa-download"></i></button>{/if}
      {#if onRemove}<button class="weg" onclick={() => onRemove(item)} title={removeTitle}><i class="fa-solid fa-xmark"></i></button>{/if}
      {#if onMenu}<button onclick={(e) => onMenu(e, item)} title="Mehr"><i class="fa-solid fa-ellipsis"></i></button>{/if}
    {:else if mode !== 'auswahl'}
      <button class="spielen" onclick={() => onPlay(item)} title={item.state === 'started' ? 'Weiterschauen' : 'Abspielen'}>
        <i class="fa-solid {item.state === 'finished' ? 'fa-rotate-right' : 'fa-play'}"></i></button>
      {#if onNext}
        <button onclick={() => onNext(item)} title="Als Nächstes abspielen"><i class="fa-solid fa-forward"></i></button>
      {/if}
      {#if onRemove}
        <button class="weg" onclick={() => onRemove(item)} title={removeTitle}><i class="fa-solid fa-xmark"></i></button>
      {/if}
      {#if onMenu}
        <button onclick={(e) => onMenu(e, item)} title="Mehr"><i class="fa-solid fa-ellipsis"></i></button>
      {/if}
    {/if}
  </div>
</div>

<style>
  .zeile { position: relative; display: grid; align-items: center; gap: var(--tv-a3);
           grid-template-columns: 22px 34px 160px minmax(0, 1fr) 160px 140px;
           padding: 6px var(--tv-a2); border-radius: var(--tv-ecke); }
  .zeile.mit-zeit { grid-template-columns: 22px 52px 160px minmax(0, 1fr) 180px 140px; }
  .zeile:hover { background: var(--tv-flaeche); }
  .zeile.gewaehlt { background: rgba(var(--tv-akzent-rgb), 0.08); }
  .zeile.gehoben { opacity: 0.45; }
  .zeile.laeuft .titel { color: var(--tv-akzent); }
  .zeile.fehlt .bild, .zeile.fehlt .titel { opacity: 0.6; }
  .griff { color: var(--tv-text-3); cursor: grab; text-align: center; }
  .haken { width: 22px; height: 22px; padding: 0; border: 0; background: none; color: var(--tv-text-3); cursor: pointer; font-size: 18px; }
  .gewaehlt .haken { color: var(--tv-akzent); }
  .nr { text-align: right; color: var(--tv-text-3); font-size: var(--tv-gr-klein); }
  .bild { position: relative; aspect-ratio: 16 / 9; padding: 0; border: 0; border-radius: var(--tv-ecke-klein); overflow: hidden;
          background: var(--tv-mulde); cursor: pointer; }
  .bild img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .dauer { position: absolute; right: 5px; bottom: 7px; padding: 0 5px; height: 20px; display: grid; place-items: center;
           background: var(--tv-schleier); border-radius: var(--tv-ecke-klein); font-size: var(--tv-gr-marke); font-weight: 700; color: var(--tv-text); }
  .fort { position: absolute; left: 0; right: 0; bottom: 0; height: 4px; background: rgba(0, 0, 0, 0.55); }
  .fort b { display: block; height: 100%; background: var(--tv-akzent); }
  .fort.fertig b { background: var(--tv-text-3); }
  .text { min-width: 0; }
  .titel { display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; padding: 0; border: 0;
           background: none; color: var(--tv-text); font: inherit; font-weight: 600; text-align: left; cursor: pointer; }
  .titel:hover { color: var(--tv-akzent); }
  .meta { display: flex; gap: var(--tv-a3); font-size: var(--tv-gr-klein); color: var(--tv-text-2); white-space: nowrap; overflow: hidden; }
  .meta .zahl { color: var(--tv-text-3); }
  .stand { font-size: var(--tv-gr-klein); color: var(--tv-text-2); text-align: right; }
  .tun { display: flex; justify-content: flex-end; gap: 2px; opacity: 0; transition: opacity var(--tv-schnell); }
  .zeile:hover .tun, .zeile:focus-within .tun { opacity: 1; }
  .tun button { width: 38px; height: 38px; border: 0; background: none; color: var(--tv-text-2); border-radius: var(--tv-ecke);
                cursor: pointer; font-size: 15px; }
  .tun button:hover { background: var(--tv-karte-2); color: var(--tv-text); }
  .tun button.spielen { background: var(--tv-akzent); color: var(--tv-akzent-text); }
  .tun button.weg:hover { color: var(--tv-gefahr); }
  @media (max-width: 1100px) {
    .zeile, .zeile.mit-zeit { grid-template-columns: 22px 34px 128px minmax(0, 1fr) 132px; }
    .stand { display: none; }
  }
</style>

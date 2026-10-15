<!--
  Warteschlange am Handy: oben der laufende Titel, darunter, was als
  Nächstes kommt. Am Griff ziehen ordnet um, nach links wischen nimmt
  heraus (mit Rückgängig in der Meldung). Bei Hörbüchern stattdessen die
  Teile in fester Reihenfolge; Antippen spielt einen Teil von vorn.
  Gestaltung nach mockups/mobil-musik.html.
-->
<script>
  import SegmentList from '../../../lib/components/music/SegmentList.svelte';
  import { onDestroy } from 'svelte';
  import { musicPlayer as player } from '../../../lib/stores/musicPlayer.svelte.js';
  import { coverUrl } from '../../../lib/utils/musicTrack.js';
  import { trackFormat } from '../../../lib/utils/audioTech.js';
  import { dragShift, dragTarget } from '../../../lib/utils/queueOps.js';
  import { toast } from '../../../lib/stores/notifications.js';
  import { formatDuration } from '../../../lib/utils/format.js';
  import { back } from '../../router.js';
  import { nearEnd } from '../../parts/nearEnd.js';
  import { wischen } from '../../parts/wischen.js';
  import MusicMiniBar from '../../parts/MusicMiniBar.svelte';

  const STEP = 60;              // so viele Zeilen mehr beim Rollen
  const REMOVE_PX = 96;         // ab so weit nach links nimmt Wischen heraus
  const EDGE_PX = 72;           // Nähe zum Rand, ab der beim Ziehen mitgerollt wird
  const EDGE_SPEED = 10;        // Bildpunkte je Bild beim Mitrollen

  let book = $derived(!!player.audiobook);
  let first = $derived(book ? 0 : player.index + 1);   // erste Zeile der Liste
  let shown = $state(STEP);
  let rows = $derived(player.queue.slice(first, first + shown).map((track, k) => ({ track, at: first + k })));
  let rest = $derived(Math.max(0, player.queue.length - first));
  let current = $derived(player.current);
  // Format des laufenden Titels: aus der Liste oder, wenn sie es nicht kennt, aus den Ton-Angaben
  let currentFormat = $derived(trackFormat({ ...current, codec: current?.codec || player.audioInfo?.codec }));
  let section = $derived(book ? player.title : `Aus ${player.title || 'der Auswahl'}${player.shuffle ? ', zufällig' : ''}`);
  let scroller = $state(null);

  const more = () => { shown += STEP; };
  const canMore = () => first + shown < player.queue.length;

  // ─── Umordnen: am Griff ziehen ───
  let drag = $state(null);      // { from, to, dy, startY, startScroll, rowHeight, y }
  let edgeFrame = 0;

  function grab(e, at) {
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    const row = e.currentTarget.closest('.zeile');
    const gap = parseFloat(getComputedStyle(row.parentElement).rowGap) || 0;
    drag = { from: at, to: at, dy: 0, startY: e.clientY, startScroll: scroller.scrollTop, rowHeight: row.offsetHeight + gap, y: e.clientY };
    edgeFrame = requestAnimationFrame(followEdge);
  }

  function pull(e) {
    if (!drag) return;
    update(e.clientY);
  }

  function update(y) {
    const dy = y - drag.startY + scroller.scrollTop - drag.startScroll;
    const last = Math.min(player.queue.length - 1, first + shown - 1);
    drag = { ...drag, y, dy, to: dragTarget(drag.from, dy, drag.rowHeight, first, last) };
  }

  // Liegt der Finger am oberen oder unteren Rand, rollt die Liste mit
  function followEdge() {
    if (!drag) return;
    const box = scroller.getBoundingClientRect();
    const speed = drag.y < box.top + EDGE_PX ? -EDGE_SPEED : drag.y > box.bottom - EDGE_PX ? EDGE_SPEED : 0;
    if (speed) {
      scroller.scrollTop += speed;
      update(drag.y);
    }
    edgeFrame = requestAnimationFrame(followEdge);
  }

  function release() {
    cancelAnimationFrame(edgeFrame);
    if (!drag) return;
    const { from, to } = drag;
    drag = null;
    player.move(from, to);
  }

  function rowStyle(at) {
    if (!drag) return null;
    if (at === drag.from) return `transform: translateY(${drag.dy}px)`;
    const shift = dragShift(at, drag.from, drag.to);
    return shift ? `transform: translateY(${shift * drag.rowHeight}px)` : null;
  }

  // ─── Herausnehmen: nach links wischen (parts/wischen.js) ───
  let swipe = $state(null);     // { at, dx } solange eine Zeile gewischt wird

  const swipeRow = (at) => ({
    disabled: book || !!drag,
    onMove: (dx) => { swipe = { at, dx: Math.min(0, dx) }; },
    onEnd: (dx) => {
      swipe = null;
      if (dx <= -REMOVE_PX) takeOut(at);
    },
  });

  function takeOut(at) {
    const track = player.queue[at];
    if (!track) return;
    player.remove(at);
    toast.undo(`"${track.title}" herausgenommen`, () => player.insertAt(track, at));
  }

  function play(at) {
    if (!drag) player.jump(at);
  }

  onDestroy(() => cancelAnimationFrame(edgeFrame));
</script>

<div class="schlange">
  <header class="kopf">
    <button class="m-rund" onclick={back} aria-label="Schließen"><i class="fa-solid fa-chevron-down"></i></button>
    <h1>{book ? 'Teile' : 'Warteschlange'}</h1>
  </header>

  <div class="rollfeld" bind:this={scroller} use:nearEnd={{ onNearEnd: more, canLoad: canMore }}>
    <div class="inhalt">
      {#if !book}
        <div class="eintrag jetzt">
          <span class="griff"><i class="fa-solid fa-volume-high"></i></span>
          <span class="spielen">
            <img src={coverUrl(current)} alt="" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
            <span class="text"><span class="t">{current.title}</span><span class="w">{current.artist} · {currentFormat}</span></span>
          </span>
          <span class="zahl dauer">{formatDuration(current.duration || 0)}</span>
        </div>
      {/if}

      <SegmentList />

      <div class="abschnitt"><span class="name">{section}</span><span class="zahl">{rest} {book ? 'Teile' : 'Titel'}</span></div>

      <div class="liste" role="list">
        {#each rows as { track, at } (track.id + ':' + at)}
          {@const laeuft = at === player.index}
          <div class="zeile" class:gezogen={drag?.from === at} class:ziehen={!!drag} style={rowStyle(at)} role="listitem">
            {#if !book}<span class="weg" aria-hidden="true">Entfernen</span>{/if}
            <div class="eintrag" class:jetzt={laeuft} class:wischt={swipe?.at === at} use:wischen={swipeRow(at)}
                 style:transform={swipe?.at === at ? `translateX(${swipe.dx}px)` : null}>
              {#if book}
                <span class="griff">{#if laeuft}<i class="fa-solid fa-volume-high"></i>{:else}<span class="zahl nummer">{at + 1}</span>{/if}</span>
              {:else}
                <button class="griff ziehbar" aria-label="Zum Umordnen ziehen"
                        onpointerdown={(e) => { e.stopPropagation(); grab(e, at); }} onpointermove={pull}
                        onpointerup={release} onpointercancel={release}><i class="fa-solid fa-grip-lines"></i></button>
              {/if}
              <button class="spielen" onclick={() => play(at)} aria-label="{track.title} abspielen">
                <img src={coverUrl(track)} alt="" loading="lazy" onerror={(e) => e.currentTarget.style.visibility = 'hidden'} />
                <span class="text"><span class="t">{track.title}</span>
                  <span class="w">{book ? `Teil ${at + 1}` : `${track.artist} · ${trackFormat(track)}`}</span></span>
              </button>
              <span class="zahl dauer">{formatDuration(track.duration || 0)}</span>
            </div>
          </div>
        {/each}
      </div>

      {#if canMore()}
        <p class="mehr"><span class="zahl">{rows.length}</span> von <span class="zahl">{rest}</span>, weitere beim Rollen</p>
      {:else if !rest}
        <p class="mehr">Danach ist Schluss{player.repeat === 'all' ? ', es geht von vorn los' : ''}.</p>
      {/if}

      <p class="m-hinweis">
        <i class="fa-solid fa-hand-pointer"></i>
        <span>{book ? 'Einen Teil antippen spielt ihn von vorn. Ein Hörbuch läuft immer in seiner Reihenfolge.'
                    : 'Am Griff ziehen ordnet um, nach links wischen nimmt heraus (mit Rückgängig).'}</span>
      </p>
    </div>
  </div>

  <MusicMiniBar onopen={back} />
</div>

<style>
  .schlange { height: 100%; display: flex; flex-direction: column; overflow: hidden; background: var(--m-bg); }
  .kopf { display: flex; align-items: center; gap: 12px; flex: none; height: calc(var(--m-safe-top) + 60px);
          padding: var(--m-safe-top) calc(var(--m-safe-right) + 16px) 0 calc(var(--m-safe-left) + 16px); background: var(--tv-leiste); }
  h1 { font-size: 22px; font-weight: 700; }
  .rollfeld { flex: 1; min-height: 0; overflow-y: auto; overflow-x: hidden; overscroll-behavior: contain; }
  .inhalt { padding: 12px calc(var(--m-safe-right) + 16px) 16px calc(var(--m-safe-left) + 16px); display: flex; flex-direction: column; gap: 8px; }
  .liste { display: flex; flex-direction: column; gap: 4px; }
  .zeile { position: relative; overflow: hidden; border-radius: var(--m-radius); }
  .zeile.ziehen { transition: transform 0.15s ease; }
  .zeile.gezogen { z-index: 2; transition: none; box-shadow: var(--tv-schatten); }
  .weg { position: absolute; inset: 0 0 0 auto; width: 96px; display: grid; place-items: center; background: var(--tv-gefahr);
         color: #fff; font-weight: 700; font-size: 14px; border-radius: var(--m-radius); }
  .eintrag { position: relative; display: grid; grid-template-columns: 44px minmax(0, 1fr) auto; gap: 4px; align-items: center;
             min-height: 64px; padding-right: 4px; background: var(--m-bg); touch-action: pan-y; transition: transform 0.2s ease; }
  .eintrag.wischt { transition: none; }
  .gezogen .eintrag { background: var(--tv-karte-2); }
  .eintrag.jetzt { background: rgba(var(--tv-akzent-rgb), 0.1); border-radius: var(--m-radius); }
  .eintrag.jetzt .t { color: var(--m-accent); }
  .griff { width: 44px; height: 56px; display: grid; place-items: center; color: var(--m-faint); }
  .jetzt .griff { color: var(--m-accent); }
  .ziehbar { touch-action: none; cursor: grab; }
  .nummer { font-size: 15px; }
  .spielen { min-width: 0; display: flex; align-items: center; gap: 10px; min-height: 56px; text-align: left; }
  .eintrag img { width: 48px; height: 48px; flex: none; object-fit: cover; border-radius: var(--tv-ecke-klein); background: var(--m-surface); }
  .text { min-width: 0; display: flex; flex-direction: column; }
  .t { font-weight: 600; font-size: 16px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .w { font-size: 14px; color: var(--m-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .dauer { font-size: 15px; color: var(--m-dim); padding-left: 6px; }
  .abschnitt { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-top: 8px;
               font-size: 13px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: var(--m-faint); }
  .abschnitt .name { min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .abschnitt .zahl { flex: none; letter-spacing: 0.04em; }
  .mehr { padding: 8px 0; font-size: 15px; color: var(--m-faint); text-align: center; }
  .m-hinweis { display: flex; gap: 10px; align-items: flex-start; margin-top: 8px; padding: 12px 14px; border-radius: var(--m-radius);
               background: var(--tv-flaeche); font-size: 15px; color: var(--m-dim); }
  .m-hinweis i { color: var(--tv-info); margin-top: 3px; }
</style>

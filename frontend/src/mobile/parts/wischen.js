/**
 * Waagerechtes Wischen am Handy (Svelte-Aktion). Senkrecht bleibt dem
 * Rollen: erst wenn der Finger deutlich mehr zur Seite als nach oben oder
 * unten wandert, gehört die Bewegung dem Element. Das Tippen, das ein
 * Wischen beendet, wird verschluckt - Wischen spielt also nicht zugleich ab.
 *
 *   <div use:wischen={{ onMove: (dx) => ..., onEnd: (dx) => ... }}>
 *   dx: Bildpunkte nach rechts (negativ = links). Das Element braucht
 *   touch-action: pan-y, damit der Browser senkrecht weiter rollt.
 */
export const SLOP_PX = 10;   // erst ab hier entscheidet sich, ob gewischt oder gerollt wird

/** Wem gehört die Bewegung? 'wischen', 'rollen' oder null (noch offen) */
export function swipeIntent(dx, dy, slop = SLOP_PX) {
  if (Math.abs(dy) > slop && Math.abs(dy) >= Math.abs(dx)) return 'rollen';
  if (Math.abs(dx) > slop && Math.abs(dx) > Math.abs(dy)) return 'wischen';
  return null;
}

export function wischen(node, params) {
  let opts = params || {};
  let start = null;          // { x, y } solange ein Finger liegt
  let active = false;        // die Bewegung gehört dem Element
  let swallow = false;       // das nächste click verschlucken

  function down(e) {
    swallow = false;
    if (opts.disabled || e.button > 0) return;
    start = { x: e.clientX, y: e.clientY };
    active = false;
  }

  function move(e) {
    if (!start) return;
    const dx = e.clientX - start.x;
    if (!active) {
      const intent = swipeIntent(dx, e.clientY - start.y);
      if (intent === 'rollen') { start = null; return; }
      if (intent !== 'wischen') return;
      active = true;
      try { node.setPointerCapture(e.pointerId); } catch { /* Zeiger schon fort */ }
    }
    opts.onMove?.(dx);
  }

  function up(e) {
    if (!start) return;
    const dx = e.clientX - start.x;
    const was = active;
    start = null;
    active = false;
    if (!was) return;
    swallow = true;
    opts.onEnd?.(dx);
  }

  function cancel() {
    if (active) opts.onEnd?.(0);
    start = null;
    active = false;
  }

  function click(e) {
    if (!swallow) return;
    swallow = false;
    e.stopPropagation();
    e.preventDefault();
  }

  const listeners = { pointerdown: down, pointermove: move, pointerup: up, pointercancel: cancel };
  for (const [type, handler] of Object.entries(listeners)) node.addEventListener(type, handler);
  node.addEventListener('click', click, true);

  return {
    update(next) { opts = next || {}; },
    destroy() {
      for (const [type, handler] of Object.entries(listeners)) node.removeEventListener(type, handler);
      node.removeEventListener('click', click, true);
    },
  };
}

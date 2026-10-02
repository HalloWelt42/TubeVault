/**
 * Svelte-Action für einen Rollbereich: ruft onNearEnd, sobald das Ende in
 * Reichweite kommt - beim Rollen und nach jedem Nachladen (kurze Listen
 * füllen den Schirm sonst nie).
 *
 *   <div use:nearEnd={{ onNearEnd: list.loadMore, canLoad: list.canLoad }}>
 */
const REACH_PX = 700;

export function nearEnd(node, params) {
  let opts = params;
  let busy = false;

  async function check() {
    if (busy || !opts?.canLoad?.()) return;
    if (node.scrollTop + node.clientHeight < node.scrollHeight - REACH_PX) return;
    busy = true;
    try { await opts.onNearEnd?.(); } finally { busy = false; }
    requestAnimationFrame(check);
  }

  node.addEventListener('scroll', check, { passive: true });
  const observer = new ResizeObserver(check);
  observer.observe(node);
  if (node.firstElementChild) observer.observe(node.firstElementChild);

  return {
    update(next) { opts = next; check(); },
    destroy() { node.removeEventListener('scroll', check); observer.disconnect(); },
  };
}

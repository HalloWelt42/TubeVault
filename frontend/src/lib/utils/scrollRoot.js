// Das Rollfeld einer Ansicht. Neu gebaute Seiten haben einen festen Kopf und
// darunter ein eigenes Rollfeld (Element mit data-scroll-root, Baustein
// .tv-rollfeld); ältere Seiten rollen noch als Ganzes in .main-content bzw.
// im Verwaltungsbereich in .admin-main. Nachladen, Rollposition merken und
// "nach oben" fragen hier nach, statt fest .main-content anzunehmen.

const PAGE_SCROLLERS = '.main-content, .admin-main';

/** Das Rollfeld, in dem ein Element liegt. */
export function scrollRootOf(node) {
  return node?.closest?.('[data-scroll-root]') || node?.closest?.(PAGE_SCROLLERS)
    || document.querySelector(PAGE_SCROLLERS);
}

/** Das Rollfeld der gerade angezeigten Seite. */
export function activeScrollRoot() {
  const page = document.querySelector(PAGE_SCROLLERS);
  return page?.querySelector('[data-scroll-root]') || page;
}

/**
 * Ein Element in seinem Behälter sichtbar machen, ohne andere Rollfelder zu
 * bewegen. scrollIntoView rollt alle Vorfahren mit - beim Mitlaufen der
 * Untertitel sprang dadurch die ganze Seite.
 *   block: 'center' (mittig) oder 'nearest' (nur so weit wie nötig)
 */
export function scrollWithin(container, el, block = 'center') {
  if (!container || !el) return;
  const box = container.getBoundingClientRect();
  const item = el.getBoundingClientRect();
  const top = item.top - box.top + container.scrollTop;
  let target;
  if (block === 'center') {
    target = top - (container.clientHeight - item.height) / 2;
  } else {
    if (item.top >= box.top && item.bottom <= box.bottom) return;   // schon ganz sichtbar
    target = item.top < box.top ? top : top - container.clientHeight + item.height;
  }
  container.scrollTo({ top: Math.max(0, target), behavior: 'smooth' });
}

// Das Rollfeld einer Ansicht. Jede Seite hat einen festen Kopf und darunter
// ein eigenes Rollfeld (Element mit data-scroll-root, Baustein .tv-rollfeld);
// .main-content bzw. im Verwaltungsbereich .admin-main bleiben die Rückfall-
// ebene. Nachladen, Rollposition merken und "nach oben" fragen hier nach,
// statt fest .main-content anzunehmen.

const PAGE_SCROLLERS = '.main-content, .admin-main';
const SCROLL_ROOTS = `[data-scroll-root], .tv-spalten, ${PAGE_SCROLLERS}`;

const rolls = (el) => ['auto', 'scroll'].includes(getComputedStyle(el).overflowY);

/** Das Rollfeld, in dem ein Element liegt: das nächste als Rollfeld
 * gekennzeichnete Element, das gerade tatsächlich rollt. Ein Rollfeld, das
 * nicht selbst rollt (bei schmalem Fenster rollen untereinander gestellte
 * Spalten gemeinsam), zählt nicht - sonst sähe das Nachladen sein Ende
 * immer als sichtbar an. */
export function scrollRootOf(node) {
  for (let el = node?.parentElement?.closest(SCROLL_ROOTS); el; el = el.parentElement?.closest(SCROLL_ROOTS)) {
    if (rolls(el)) return el;
  }
  return document.querySelector(PAGE_SCROLLERS);
}

/** Das Rollfeld der gerade angezeigten Seite. */
export function activeScrollRoot() {
  const page = document.querySelector(PAGE_SCROLLERS);
  const roots = page ? [...page.querySelectorAll('[data-scroll-root], .tv-spalten')] : [];
  return roots.find(rolls) || page;
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

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

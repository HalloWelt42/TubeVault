/**
 * TubeVault – infiniteScroll Action v1.0.0
 *
 * Zentrale IntersectionObserver-Logik für alle Media-Listen (ersetzt die
 * bisher 3× lokal duplizierten Observer in Library/Feed/History).
 *
 * Nutzung an einem Sentinel-Element am Listenende:
 *   <div use:infiniteScroll={{ onLoadMore, canLoad, rootMargin }}></div>
 *
 * Parameter:
 *   onLoadMore  () => void   – wird gefeuert wenn der Sentinel sichtbar wird
 *   canLoad     () => bool   – optional; Getter (nicht Wert!) verhindert
 *                              Stale-Closure-Bugs und Doppel-Requests
 *                              (z.B. () => hasMore && !loading). Fehlt er,
 *                              wird immer geladen – der Aufrufer muss dann
 *                              selbst guarden.
 *   rootMargin  string       – Vorlauf (Default '400px'), lädt bevor der
 *                              Nutzer das Ende erreicht.
 *   root        Element|null – optionaler Scroll-Container (Default Viewport).
 *
 * Rückgabe: Svelte-Action-Objekt mit update()/destroy(). update() liest die
 * Getter live neu (kein Re-Observe nötig); nur rootMargin/root-Wechsel baut
 * den Observer neu auf.
 */
export function infiniteScroll(node, params = {}) {
  let opts = params;

  function make() {
    const io = new IntersectionObserver(
      (entries) => {
        if (!entries[0]?.isIntersecting) return;
        if (typeof opts.canLoad === 'function' && !opts.canLoad()) return;
        opts.onLoadMore?.();
      },
      { rootMargin: opts.rootMargin || '400px', root: opts.root || null }
    );
    io.observe(node);
    return io;
  }

  let observer = make();

  return {
    update(newParams = {}) {
      const marginChanged = (newParams.rootMargin || '400px') !== (opts.rootMargin || '400px');
      const rootChanged = (newParams.root || null) !== (opts.root || null);
      opts = newParams;
      // Callbacks/Getter werden live gelesen → nur bei Observer-Config neu bauen
      if (marginChanged || rootChanged) {
        observer.disconnect();
        observer = make();
      }
    },
    destroy() {
      observer.disconnect();
    },
  };
}

/**
 * TubeVault – infiniteScroll Action v1.1.0
 *
 * Zentrale IntersectionObserver-Logik für alle Media-Listen (ersetzt die
 * bisher lokal duplizierten Observer). Robust gegen die typischen Fallen:
 *   - beobachtet gegen den ECHTEN Scroll-Container (.main-content), nicht
 *     das Fenster – sonst misst der Observer in dieser App falsch
 *   - interner busy-Guard verhindert Doppel-/Überlappungs-Requests, auch
 *     wenn der Consumer-State (loading) minimal verzögert kippt
 *   - Nachlade-Recheck: bleibt der Sentinel nach dem Laden sichtbar (kurze
 *     Liste / großer Bildschirm), wird weitergeladen bis er verdeckt ist
 *
 * Nutzung an einem Sentinel-Element am Listenende:
 *   <div use:infiniteScroll={{ onLoadMore, canLoad, rootMargin }}></div>
 *
 *   onLoadMore  () => void|Promise  – lädt die nächste Seite (append)
 *   canLoad     () => bool          – Getter (live gelesen): z.B.
 *                                     () => hasMore && !loading && !loadingMore
 *   rootMargin  string              – Vorlauf (Default '300px')
 */
export function infiniteScroll(node, params = {}) {
  let opts = params;
  let visible = false;
  let busy = false;

  function scrollRoot() {
    // Der Scroll-Container dieser App ist .main-content (overflow-y:auto).
    return document.querySelector('.main-content') || null;
  }

  async function fire() {
    if (busy) return;
    if (typeof opts.canLoad === 'function' && !opts.canLoad()) return;
    busy = true;
    try {
      await opts.onLoadMore?.();
    } finally {
      busy = false;
    }
    // Nach dem Laden: wenn Sentinel noch sichtbar und weiter ladbar → nachlegen
    // (verhindert Stillstand bei kurzen Listen; kein Endlos-Loop, weil canLoad
    // spätestens bei hasMore=false stoppt).
    if (visible && typeof opts.canLoad === 'function' && opts.canLoad()) {
      requestAnimationFrame(() => fire());
    }
  }

  function make() {
    const io = new IntersectionObserver(
      (entries) => {
        visible = !!entries[0]?.isIntersecting;
        if (visible) fire();
      },
      { root: opts.root || scrollRoot(), rootMargin: opts.rootMargin || '300px', threshold: 0 }
    );
    io.observe(node);
    return io;
  }

  let observer = make();

  return {
    update(newParams = {}) {
      const marginChanged = (newParams.rootMargin || '300px') !== (opts.rootMargin || '300px');
      opts = newParams;
      if (marginChanged) {
        observer.disconnect();
        observer = make();
      }
    },
    destroy() {
      observer.disconnect();
    },
  };
}

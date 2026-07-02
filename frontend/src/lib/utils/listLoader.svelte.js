/**
 * TubeVault – listLoader v1.0.0
 *
 * DER zentrale Zustand für nachladbare Listen (Infinite Scroll). Ersetzt den
 * fünffach kopierten Boilerplate (items/page/hasMore/loading/loadingMore +
 * loadMore) der Routen — der in zwei Kopien denselben subtilen Bug hatte:
 *
 *   Ein $effect, der load() aufruft, trackt ALLE synchronen State-Reads —
 *   auch das `page`-$state INNERHALB von load(). loadMore() macht page+=1
 *   → der Effect feuert erneut → reset → die Liste springt auf Seite 1
 *   („Nachladen lädt die ganze Ansicht neu").
 *
 * Lösung an der Wurzel: `page` ist hier eine BEWUSST nicht-reaktive Variable.
 * Kein Effect kann sie tracken, egal wie der Loader aufgerufen wird. Reaktiv
 * ist nur, was die UI rendert: items, total, loading, loadingMore, hasMore.
 *
 * Nutzung in einer Route:
 *   const list = createListLoader(async (page) => {
 *     const r = await api.getVideos({ page, per_page: 24, ...filter });
 *     return { items: r.videos || [], total: r.total };
 *   });
 *   $effect(() => { filterA; filterB; list.load(true); });   // Filter tracken OK
 *   <div use:infiniteScroll={{ onLoadMore: list.loadMore, canLoad: list.canLoad }}>
 *
 * fetchPage(page) muss { items, total? , hasMore? } liefern:
 *   - hasMore (bool) gewinnt, sonst wird über total abgeleitet,
 *   - fehlt beides → keine weiteren Seiten (defensiv).
 * Veraltete Antworten (Filterwechsel während ein Request läuft) werden über
 * eine Laufnummer verworfen — kein Durcheinander mehr bei schnellem Filtern.
 */
export function createListLoader(fetchPage) {
  let items = $state([]);
  let total = $state(0);
  let loading = $state(false);
  let loadingMore = $state(false);
  let hasMore = $state(false);

  let page = 1;   // ABSICHTLICH nicht reaktiv (siehe Kopf-Kommentar)
  let runId = 0;  // Stale-Guard: nur die jüngste Antwort zählt

  function applyResult(res, reset) {
    const newItems = res?.items || [];
    items = reset ? newItems : [...items, ...newItems];
    if (typeof res?.total === 'number') total = res.total;
    if (typeof res?.hasMore === 'boolean') hasMore = res.hasMore;
    else if (typeof res?.total === 'number') hasMore = items.length < res.total;
    else hasMore = false;
  }

  async function load(reset = true) {
    const myRun = ++runId;
    if (reset) {
      page = 1;
      loading = true;
    } else {
      loadingMore = true;
    }
    try {
      const res = await fetchPage(page);
      if (myRun !== runId) return; // überholt (Filter wechselte zwischendurch)
      applyResult(res, reset);
    } finally {
      if (myRun === runId) { loading = false; loadingMore = false; }
    }
  }

  function loadMore() {
    if (loading || loadingMore || !hasMore) return;
    page += 1;
    return load(false);
  }

  return {
    get items() { return items; },
    set items(v) { items = v; },   // für lokale Mutationen (Karte entfernen etc.)
    get total() { return total; },
    set total(v) { total = v; },
    get loading() { return loading; },
    get loadingMore() { return loadingMore; },
    get hasMore() { return hasMore; },
    load,
    loadMore,
    canLoad: () => hasMore && !loading && !loadingMore,
  };
}

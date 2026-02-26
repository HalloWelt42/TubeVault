/**
 * TubeVault -  Router Store v1.6.29
 * SPA-Router mit history.pushState, Logging, Fallbacks.
 * URL ist Single Source of Truth.
 * © HalloWelt42 -  Private Nutzung
 */

import { writable, derived, get } from 'svelte/store';
import { routeDefinitions, resolveRouteKey } from './routes.js';

// ─── State ───────────────────────────────────────────────

/** Kompletter Router-State: { page, id, params, path, fullUrl } */
export const route = writable(parseCurrentUrl());

/** Abgeleitete Stores für einfachen Zugriff */
export const currentPage = derived(route, r => r.page);
export const routeId = derived(route, r => r.id);
export const routeParams = derived(route, r => r.params);

/** Navigations-History für Debug/Log (letzte 50) */
const _history = [];
const MAX_HISTORY = 50;

/** Log-Buffer — wird periodisch ans Backend gesendet */
const _logBuffer = [];
let _logTimer = null;

// ─── URL Parsing ─────────────────────────────────────────

/**
 * Aktuelle Browser-URL parsen.
 * @returns {{ page: string, id: string|null, params: Object, path: string, fullUrl: string }}
 */
function parseCurrentUrl() {
  return parseUrl(window.location.pathname, window.location.search);
}

/**
 * URL-String parsen → Route-State.
 * @param {string} pathname - z.B. '/watch/abc123'
 * @param {string} search - z.B. '?t=120&tab=chapters'
 */
function parseUrl(pathname, search = '') {
  const segments = pathname.split('/').filter(Boolean);
  const params = Object.fromEntries(new URLSearchParams(search));
  const fullUrl = pathname + search;

  // / → Dashboard
  if (segments.length === 0) {
    return { page: 'dashboard', id: null, params, path: '/', fullUrl };
  }

  const pageKey = segments[0];
  const routeDef = routeDefinitions[pageKey];

  // Unbekannte Route → Fallback + Loggen
  if (!routeDef) {
    _logRouteError('unknown_route', fullUrl, `Unbekannte Route: /${pageKey}`);
    return { page: 'dashboard', id: null, params: {}, path: '/', fullUrl: '/', _fallback: true };
  }

  // ID extrahieren (Segment 2)
  const id = segments[1] || null;

  // Route erwartet ID aber keine da → Loggen
  if (routeDef.hasId && !id) {
    _logRouteError('missing_id', fullUrl, `Route /${pageKey} erwartet ID, keine gefunden`);
    return { page: 'dashboard', id: null, params: {}, path: '/', fullUrl: '/', _fallback: true };
  }

  return { page: pageKey, id, params, path: pathname, fullUrl };
}

// ─── Navigation ──────────────────────────────────────────

/**
 * Zu einer Route navigieren.
 * @param {string} path - z.B. '/watch/abc123' oder '/library'
 * @param {Object} params - Query-Parameter { sort: 'title', page: 2 }
 * @param {boolean} replace - true = replaceState (kein History-Eintrag)
 *
 * @example
 *   navigate('/watch/dQw4w9WgXcQ')
 *   navigate('/watch/dQw4w9WgXcQ', { t: 120, tab: 'chapters' })
 *   navigate('/library', { type: 'short', sort: 'title' })
 *   navigate('/feed', { tab: 'later' }, true)  // replace
 */
export function navigate(path, params = {}, replace = false) {
  // Query-String aus path extrahieren falls eingebettet
  let cleanPath = path;
  if (path.includes('?')) {
    const [p, qs] = path.split('?', 2);
    cleanPath = p;
    // Eingebettete Query-Parameter mit expliziten params mergen
    const embedded = Object.fromEntries(new URLSearchParams(qs));
    params = { ...embedded, ...params };
  }

  const url = buildUrl(cleanPath, params);
  const search = url.includes('?') ? '?' + url.split('?')[1] : '';
  const parsed = parseUrl(cleanPath, search);

  // History-Tracking
  const prev = get(route);
  _pushHistory(prev.fullUrl, url, replace);

  // URL im Browser setzen
  if (replace) {
    history.replaceState({ page: parsed.page, id: parsed.id }, '', url);
  } else {
    history.pushState({ page: parsed.page, id: parsed.id }, '', url);
  }

  // Store aktualisieren
  route.set(parsed);

  // Scroll nach oben bei Seitenwechsel (nicht bei replace/Filter)
  if (!replace && prev.page !== parsed.page) {
    const mainContent = document.querySelector('.main-content');
    if (mainContent) mainContent.scrollTop = 0;
  }
}

/**
 * Nur Query-Parameter aktualisieren (für Filter).
 * Erzeugt keinen History-Eintrag (replace).
 * Null/undefined/leere Werte werden entfernt.
 *
 * @example
 *   updateParams({ type: 'short', page: 2 })
 *   updateParams({ type: null }) // entfernt 'type'
 */
export function updateParams(newParams) {
  const current = get(route);
  const merged = { ...current.params };

  for (const [k, v] of Object.entries(newParams)) {
    if (v === null || v === undefined || v === '' || v === 'all') {
      delete merged[k];
    } else {
      merged[k] = String(v);
    }
  }

  // Seiten-Reset bei Filter-Änderung
  if ('page' in newParams === false && Object.keys(newParams).some(k => k !== 'page')) {
    delete merged.page;
  }

  navigate(current.path, merged, true);
}

/**
 * Browser-Zurück simulieren.
 */
export function goBack() {
  history.back();
}

// ─── URL-Builder ─────────────────────────────────────────

/**
 * Pfad + Parameter → URL-String.
 * Null/leere Werte werden ignoriert.
 */
function buildUrl(path, params = {}) {
  const query = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== '') {
      query.set(k, String(v));
    }
  }
  const qs = query.toString();
  return qs ? `${path}?${qs}` : path;
}

/**
 * URL für eine Route bauen (public API).
 * @param {string} routeKey - z.B. 'watch', 'library'
 * @param {string|null} id - ID für hasId-Routen
 * @param {Object} params - Query-Parameter
 * @returns {string}
 */
export function buildRouteUrl(routeKey, id = null, params = {}) {
  const def = routeDefinitions[routeKey];
  if (!def) return '/';
  const path = id ? `${def.path}/${id}` : def.path;
  return buildUrl(path, params);
}

// ─── Browser Events ──────────────────────────────────────

/** Back/Forward Buttons */
window.addEventListener('popstate', () => {
  const parsed = parseCurrentUrl();
  const prev = get(route);
  _pushHistory(prev.fullUrl, parsed.fullUrl, false, 'popstate');
  route.set(parsed);
});

// ─── Logging ─────────────────────────────────────────────

/**
 * Route-Fehler loggen (Frontend-Log + Konsole).
 */
function _logRouteError(type, url, message) {
  const entry = {
    ts: new Date().toISOString(),
    level: 'warn',
    cat: 'router',
    type,
    url,
    msg: message,
  };
  console.warn(`[Router] ${message} → ${url}`);
  _logBuffer.push(entry);
  _scheduleLogFlush();
}

/**
 * Navigations-History tracken.
 */
function _pushHistory(from, to, replace, trigger = 'navigate') {
  _history.push({
    ts: new Date().toISOString(),
    from,
    to,
    replace,
    trigger,
  });
  if (_history.length > MAX_HISTORY) _history.shift();
}

/**
 * Log-Buffer ans Backend senden (gebündelt alle 5s).
 */
function _scheduleLogFlush() {
  if (_logTimer) return;
  _logTimer = setTimeout(async () => {
    _logTimer = null;
    if (_logBuffer.length === 0) return;
    const entries = _logBuffer.splice(0, _logBuffer.length);
    try {
      await fetch('/api/system/logs/frontend', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(entries),
      });
    } catch {
      // Silently fail — nicht blockieren
    }
  }, 5000);
}

// ─── Debug / Konsole ─────────────────────────────────────

/**
 * Debug-Info in Browser-Konsole.
 * Aufrufbar: TubeVault.router.debug()
 */
export function debugRouter() {
  const current = get(route);
  console.group('[TubeVault Router]');
  console.log('Aktuelle Route:', current);
  console.log('Navigations-Verlauf (letzte 50):');
  console.table(_history.slice(-20));
  console.log('Ausstehende Log-Einträge:', _logBuffer.length);
  console.groupEnd();
  return { current, history: [..._history] };
}

// ─── Global Debug API ────────────────────────────────────

if (typeof window !== 'undefined') {
  window.TubeVault = window.TubeVault || {};
  window.TubeVault.router = {
    debug: debugRouter,
    navigate,
    get state() { return get(route); },
    get history() { return [..._history]; },
  };
}

// ─── Kompatibilitäts-Bridge (alte Stores) ────────────────
// Diese Stores emulieren die alten app.js Stores.
// Lesen: Wert kommt aus URL (derived).
// Schreiben: Navigiert zur entsprechenden Route.

/** Emuliert alten currentRoute Store (lesend + schreibend). */
export const currentRouteCompat = {
  subscribe: currentPage.subscribe,
  set(value) {
    const def = routeDefinitions[value];
    if (def) {
      navigate(def.path === '/' ? '/' : def.path);
    }
  },
};

/** Emuliert alten currentVideoId Store — liest aus URL /watch/:id */
export const currentVideoIdCompat = {
  subscribe: derived(route, r => r.page === 'watch' ? r.id : null).subscribe,
  set(videoId) {
    if (videoId) navigate(`/watch/${videoId}`);
  },
};

/** Emuliert alten currentChannelId Store — liest aus URL /channel/:id */
export const currentChannelIdCompat = {
  subscribe: derived(route, r => r.page === 'channel' ? r.id : null).subscribe,
  set(channelId) {
    if (channelId) navigate(`/channel/${channelId}`);
  },
};

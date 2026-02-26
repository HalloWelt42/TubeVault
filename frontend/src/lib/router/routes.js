/**
 * TubeVault – Route Registry v1.6.29
 * Zentrale Routen-Definitionen (vergleichbar Symfony debug:router).
 * Alle Pfade, Labels, Icons, Parameter an einer Stelle.
 * © HalloWelt42 – Private Nutzung
 */

/**
 * Route-Definition:
 * @property {string} path      - URL-Pfad (ohne Query)
 * @property {string} label     - Anzeigename (deutsch)
 * @property {string} icon      - FontAwesome Icon-Klasse
 * @property {string} group     - Navigations-Gruppe: 'main' | 'system' | 'hidden'
 * @property {boolean} hasId    - Erwartet /:id Segment
 * @property {string} idParam   - Name des ID-Parameters (z.B. 'videoId', 'channelId')
 * @property {string[]} queryParams - Erlaubte Query-Parameter
 * @property {string} badge     - Badge-Key für Sidebar (aus /api/system/badges)
 * @property {string} description - Kurzbeschreibung der Route
 */
export const routeDefinitions = {
  // ─── Hauptnavigation ───────────────────────────────────
  'dashboard': {
    path: '/',
    label: 'Dashboard',
    icon: 'fa-solid fa-house',
    group: 'main',
    hasId: false,
    queryParams: [],
    description: 'Startseite mit Übersicht',
  },
  'feed': {
    path: '/feed',
    label: 'Feed',
    icon: 'fa-solid fa-rss',
    group: 'main',
    hasId: false,
    badge: 'new_feed',
    queryParams: ['tab', 'types', 'channels', 'q', 'dmin', 'dmax'],
    description: 'RSS-Feed Einträge mit Filtern',
  },
  'subscriptions': {
    path: '/subscriptions',
    label: 'Kanäle',
    icon: 'fa-solid fa-tv',
    group: 'main',
    hasId: false,
    badge: 'subscriptions',
    queryParams: ['filter', 'q'],
    description: 'Kanal-Abonnements verwalten',
  },
  'library': {
    path: '/library',
    label: 'Bibliothek',
    icon: 'fa-solid fa-photo-film',
    group: 'main',
    hasId: false,
    badge: 'videos',
    queryParams: ['sort', 'order', 'types', 'channels', 'categories', 'tags', 'q'],
    description: 'Heruntergeladene Videos mit Filtern',
  },
  'downloads': {
    path: '/downloads',
    label: 'Jobs',
    icon: 'fa-solid fa-bolt',
    group: 'main',
    hasId: false,
    badge: 'active_downloads',
    queryParams: [],
    description: 'Job-Warteschlange (Downloads, Scans, Tasks)',
  },
  'playlists': {
    path: '/playlists',
    label: 'Playlists',
    icon: 'fa-solid fa-list-ul',
    group: 'main',
    hasId: false,
    badge: 'playlists',
    queryParams: ['open'],
    description: 'Playlist-Übersicht',
  },
  'favorites': {
    path: '/favorites',
    label: 'Favoriten',
    icon: 'fa-solid fa-heart',
    group: 'main',
    hasId: false,
    badge: 'favorites',
    queryParams: ['list'],
    description: 'Favoriten-Listen',
  },
  'history': {
    path: '/history',
    label: 'Verlauf',
    icon: 'fa-solid fa-clock-rotate-left',
    group: 'main',
    hasId: false,
    badge: 'history',
    queryParams: ['types', 'channels', 'search'],
    description: 'Wiedergabe-Verlauf',
  },
  'categories': {
    path: '/categories',
    label: 'Kategorien',
    icon: 'fa-solid fa-folder',
    group: 'main',
    hasId: false,
    badge: 'categories',
    queryParams: [],
    description: 'Kategorie-Verwaltung',
  },
  'archives': {
    path: '/archives',
    label: 'Archiv',
    icon: 'fa-solid fa-box-archive',
    group: 'main',
    hasId: false,
    badge: 'archives',
    queryParams: ['sort', 'order', 'type', 'channel', 'category', 'tag', 'q', 'page'],
    description: 'Archivierte Videos',
  },
  'own-videos': {
    path: '/own-videos',
    label: 'Eigene Videos',
    icon: 'fa-solid fa-film',
    group: 'main',
    hasId: false,
    badge: 'own_videos',
    queryParams: ['status', 'folder', 'q'],
    description: 'Lokale/eigene Video-Dateien',
  },

  // ─── System ────────────────────────────────────────────
  'stats': {
    path: '/stats',
    label: 'Statistiken',
    icon: 'fa-solid fa-chart-simple',
    group: 'system',
    hasId: false,
    queryParams: [],
    description: 'System-Statistiken',
  },
  'settings': {
    path: '/settings',
    label: 'Einstellungen',
    icon: 'fa-solid fa-gear',
    group: 'system',
    hasId: false,
    queryParams: ['section'],
    description: 'App-Einstellungen',
  },

  // ─── Versteckte Routen (nicht in Sidebar) ──────────────
  'watch': {
    path: '/watch',
    label: 'Video',
    icon: 'fa-solid fa-play',
    group: 'hidden',
    hasId: true,
    idParam: 'videoId',
    queryParams: ['t', 'tab', 'pl', 'idx', 'lyrics'],
    description: 'Video abspielen',
  },
  'channel': {
    path: '/channel',
    label: 'Kanal',
    icon: 'fa-solid fa-tv',
    group: 'hidden',
    hasId: true,
    idParam: 'channelId',
    queryParams: ['source', 'type', 'sort', 'q', 'tab'],
    description: 'Kanal-Detailseite',
  },
  'playlist': {
    path: '/playlist',
    label: 'Playlist',
    icon: 'fa-solid fa-list-ul',
    group: 'hidden',
    hasId: true,
    idParam: 'playlistId',
    queryParams: ['playing'],
    description: 'Playlist-Detail',
  },
  'category': {
    path: '/category',
    label: 'Kategorie',
    icon: 'fa-solid fa-folder',
    group: 'hidden',
    hasId: true,
    idParam: 'categoryId',
    queryParams: ['sort', 'page'],
    description: 'Videos einer Kategorie',
  },
  'search': {
    path: '/search',
    label: 'Suche',
    icon: 'fa-solid fa-magnifying-glass',
    group: 'hidden',
    hasId: false,
    queryParams: ['q', 'scope'],
    description: 'Globale Suche',
  },
};

/**
 * Alle Routen als Tabelle ausgeben (wie Symfony debug:router).
 * Aufrufbar in der Browser-Konsole: TubeVault.debugRoutes()
 * @returns {Array<Object>}
 */
export function debugRoutes() {
  const rows = Object.entries(routeDefinitions).map(([key, def]) => ({
    key,
    path: def.hasId ? `${def.path}/:${def.idParam || 'id'}` : def.path,
    label: def.label,
    group: def.group,
    params: def.queryParams.join(', ') || '—',
    description: def.description,
  }));
  console.table(rows);
  return rows;
}

/**
 * Nur Sidebar-Routen (main-Gruppe), sortiert wie oben definiert.
 */
export function getMainRoutes() {
  return Object.entries(routeDefinitions)
    .filter(([, def]) => def.group === 'main')
    .map(([key, def]) => ({ key, ...def }));
}

/**
 * Nur System-Routen.
 */
export function getSystemRoutes() {
  return Object.entries(routeDefinitions)
    .filter(([, def]) => def.group === 'system')
    .map(([key, def]) => ({ key, ...def }));
}

/**
 * Route-Definition anhand Key holen.
 * @param {string} key - Route-Key (z.B. 'library')
 * @returns {Object|null}
 */
export function getRoute(key) {
  return routeDefinitions[key] || null;
}

/**
 * Route-Key aus URL-Pfad ermitteln.
 * @param {string} pathname - z.B. '/library' oder '/watch/abc123'
 * @returns {string} - Route-Key oder 'dashboard'
 */
export function resolveRouteKey(pathname) {
  const segments = pathname.split('/').filter(Boolean);
  if (segments.length === 0) return 'dashboard';

  const first = segments[0];

  // Direkte Übereinstimmung
  if (routeDefinitions[first]) return first;

  // Fallback: Dashboard
  return null;
}

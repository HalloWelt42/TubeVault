# TubeVault URL-Routing-Konzept v1.1 (implementiert v1.6.30)
# REST-ähnliche Pfade für SPA-Navigation
# Zentrale Registry: src/lib/router/routes.js
# Router-Store: src/lib/router/router.js
# © HalloWelt42

## Aktueller Stand

Navigation über `currentRoute` Store (String), keine echten URLs.
Kontextdaten über separate Stores: `currentVideoId`, `currentChannelId`, `searchQuery`.
Problem: Kein Deep-Linking, kein Browser-Back, kein Bookmark, keine teilbaren Links.
nginx `try_files` bereits konfiguriert → URL-Routing sofort nutzbar.


## Router-Architektur

### URL → State Mapping

Browser-URL wird beim Laden + bei `popstate` geparst.
State-Änderungen pushen via `history.pushState()` neue URL.
Kein externer Router — eigener Store `src/lib/stores/router.js` (~60 Zeilen).

### Grundprinzip

```
/segment/id?param=value
  ↓
{ page: 'segment', id: 'xxx', params: { param: 'value' } }
```


## URL-Schema — Alle Routen

### Hauptseiten (ohne Parameter)

| URL                  | Page-Key        | Komponente        | Beschreibung                  |
|----------------------|-----------------|-------------------|-------------------------------|
| `/`                  | `dashboard`     | Dashboard.svelte  | Startseite, Übersicht         |
| `/feed`              | `feed`          | Feed.svelte       | RSS-Feed Einträge             |
| `/library`           | `library`       | Library.svelte    | Heruntergeladene Videos       |
| `/downloads`         | `downloads`     | Downloads.svelte  | Download-Warteschlange        |
| `/favorites`         | `favorites`     | Favorites.svelte  | Favoriten-Listen              |
| `/categories`        | `categories`    | Categories.svelte | Kategorie-Verwaltung          |
| `/subscriptions`     | `subscriptions` | Subscriptions.svelte | Kanal-Abos                 |
| `/playlists`         | `playlists`     | Playlists.svelte  | Playlist-Verwaltung           |
| `/archives`          | `archives`      | Archives.svelte   | Archivierte Videos            |
| `/history`           | `history`       | History.svelte    | Wiedergabe-Verlauf            |
| `/own-videos`        | `own-videos`    | OwnVideos.svelte  | Eigene/lokale Videos          |
| `/stats`             | `stats`         | Stats.svelte      | Statistiken                   |
| `/import`            | `import`        | Import.svelte     | Datei-Import                  |
| `/thumbnail-ai`      | `thumbnail-ai`  | ThumbnailAI.svelte| AI-Analyse Dashboard          |
| `/settings`          | `settings`      | Settings.svelte   | Einstellungen                 |


### Seiten mit ID (Ressource)

| URL                          | Beschreibung                             |
|------------------------------|------------------------------------------|
| `/watch/:videoId`            | Video abspielen                          |
| `/channel/:channelId`        | Kanal-Detailseite                        |
| `/playlist/:playlistId`      | Playlist-Detailansicht                   |
| `/category/:categoryId`      | Videos einer Kategorie                   |
| `/archive/:archiveId`        | Archiv-Detailansicht                     |


### Query-Parameter — Feed

```
/feed
/feed?tab=active                    # Tab: active|later|dismissed|archived
/feed?tab=active&type=short         # Typ-Filter: video|short|live (kommasepariert)
/feed?tab=active&channel=UCxxx      # Kanal-Filter (Channel-ID)
/feed?tab=active&type=video&channel=UCxxx,UCyyy
/feed?q=tutorial                    # Keyword-Suche im Feed
/feed?duration=short                # Dauer: short(<5m)|medium(5-20m)|long(>20m)
/feed?dmin=300&dmax=1200            # Dauer exakt in Sekunden
```

Feed-Parameter:
- `tab` — active, later, dismissed, archived (default: active)
- `type` — video, short, live (kommasepariert für mehrere)
- `channel` — Channel-ID(s), kommasepariert
- `q` — Suchbegriff
- `dmin` / `dmax` — Mindest-/Maximaldauer in Sekunden


### Query-Parameter — Library

```
/library
/library?sort=created_at&order=desc
/library?sort=title&order=asc
/library?type=short
/library?channel=UCxxx
/library?category=5
/library?tag=gaming
/library?q=minecraft
/library?page=3
/library?type=video&channel=UCxxx&sort=duration&order=desc&page=2
```

Library-Parameter:
- `sort` — created_at, title, duration, views, download_date (default: created_at)
- `order` — asc, desc (default: desc)
- `type` — video, short, live
- `channel` — Channel-ID(s)
- `category` — Kategorie-ID(s)
- `tag` — Tag(s), kommasepariert
- `q` — Suchbegriff
- `page` — Seitennummer (default: 1)


### Query-Parameter — Archives

```
/archives
/archives?sort=created_at&order=desc
/archives?type=short&tag=musik
/archives?q=react&page=2
```

Archives-Parameter: Identisch mit Library (sort, order, type, channel, category, tag, q, page)


### Query-Parameter — Watch

```
/watch/dQw4w9WgXcQ
/watch/dQw4w9WgXcQ?t=120           # Springe zu Sekunde 120
/watch/dQw4w9WgXcQ?tab=chapters    # Tab direkt öffnen
/watch/dQw4w9WgXcQ?tab=streams     # Stream-Tab
```

Watch-Parameter:
- `t` — Startzeit in Sekunden
- `tab` — info, chapters, ads, subtitles, streams, meta, edit (default: info)


### Query-Parameter — Channel

```
/channel/UCxxx
/channel/UCxxx?source=local         # Nur heruntergeladene
/channel/UCxxx?source=rss           # Nur RSS
/channel/UCxxx?type=short
/channel/UCxxx?sort=newest          # newest, oldest, popular
/channel/UCxxx?q=tutorial           # Suche im Kanal
/channel/UCxxx?tab=playlists        # Kanal-Playlists
```

Channel-Parameter:
- `source` — local, rss, all (default: all)
- `type` — video, short, live
- `sort` — newest, oldest, popular (default: newest)
- `q` — Suche innerhalb Kanal
- `tab` — videos, playlists (default: videos)


### Query-Parameter — Subscriptions

```
/subscriptions
/subscriptions?filter=active
/subscriptions?filter=auto
/subscriptions?filter=errors
/subscriptions?filter=disabled
/subscriptions?q=tech
```

Subscriptions-Parameter:
- `filter` — all, active, auto, errors, unchecked, disabled (default: all)
- `q` — Suche nach Kanalname


### Query-Parameter — Playlists

```
/playlists
/playlist/5                         # Playlist-Detail (mit ID)
/playlist/5?playing=3               # Video an Position 3 abspielen
```

Playlist-Parameter:
- `playing` — Index des aktuell spielenden Videos


### Query-Parameter — History

```
/history
/history?type=video
/history?channel=UCxxx
/history?q=python
/history?page=2
```

History-Parameter:
- `type` — video, short, live
- `channel` — Channel-ID(s)
- `q` — Suchbegriff
- `page` — Seitennummer


### Query-Parameter — Favorites

```
/favorites
/favorites?list=Gaming              # Bestimmte Favoriten-Liste
```


### Query-Parameter — OwnVideos

```
/own-videos
/own-videos?status=discovered       # discovered, registered, all
/own-videos?folder=/mnt/videos
/own-videos?q=urlaubsvideo
```

OwnVideos-Parameter:
- `status` — all, discovered, registered
- `folder` — Ordner-Pfad Filter
- `q` — Suchbegriff


### Query-Parameter — Categories

```
/categories
/category/5                         # Videos einer Kategorie
/category/5?sort=title&page=2
```


### Globale Suche (Header)

```
/search?q=tutorial                  # Suche über alles
/search?q=tutorial&scope=library    # Nur in Library
/search?q=tutorial&scope=feed       # Nur im Feed
/search?q=tutorial&scope=channel    # Nur in Kanälen
```

Search-Parameter:
- `q` — Suchbegriff (required)
- `scope` — all, library, feed, channel (default: all)


### Thumbnail AI

```
/thumbnail-ai
/thumbnail-ai?view=log             # Direkt zum Log scrollen
/thumbnail-ai?view=queue           # Direkt zur Queue
```


## Store-Design: router.js

```javascript
// src/lib/stores/router.js
import { writable, derived } from 'svelte/store';

// Aktueller geparseter Zustand
export const route = writable(parseUrl(window.location));

// Abgeleitete Werte für einfachen Zugriff
export const currentPage = derived(route, r => r.page);
export const routeId = derived(route, r => r.id);
export const routeParams = derived(route, r => r.params);

// Navigation — URL ändern + State updaten
export function navigate(path, params = {}, replace = false) {
  const url = buildUrl(path, params);
  if (replace) {
    history.replaceState({}, '', url);
  } else {
    history.pushState({}, '', url);
  }
  route.set(parseUrl(window.location));
}

// URL parsen → { page, id, params }
function parseUrl(loc) {
  const segments = loc.pathname.split('/').filter(Boolean);
  const params = Object.fromEntries(new URLSearchParams(loc.search));
  
  // / → dashboard
  if (segments.length === 0) return { page: 'dashboard', id: null, params };
  
  const page = segments[0];
  const id = segments[1] || null;
  
  return { page, id, params };
}

// State → URL String bauen
function buildUrl(path, params = {}) {
  const query = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== '') query.set(k, v);
  }
  const qs = query.toString();
  return qs ? `${path}?${qs}` : path;
}

// Browser Back/Forward
window.addEventListener('popstate', () => {
  route.set(parseUrl(window.location));
});
```


## Migration — Bestehende Stores ersetzen

### Vorher (aktuell)

```javascript
// In jeder Komponente:
import { currentRoute, currentVideoId, currentChannelId } from '../lib/stores/app.js';

// Video öffnen:
currentVideoId.set('abc123');
currentRoute.set('watch');

// Kanal öffnen:
currentChannelId.set('UCxxx');
currentRoute.set('channel');
```

### Nachher

```javascript
import { navigate, routeId, routeParams } from '../lib/stores/router.js';

// Video öffnen:
navigate('/watch/abc123');

// Video mit Zeitsprung:
navigate('/watch/abc123', { t: 120 });

// Library mit Filter:
navigate('/library', { type: 'short', channel: 'UCxxx', sort: 'title' });

// Feed-Tab wechseln:
navigate('/feed', { tab: 'later' });

// Suche:
navigate('/search', { q: 'tutorial', scope: 'library' });

// Kanal mit Typ-Filter:
navigate('/channel/UCxxx', { type: 'short', sort: 'popular' });

// Zurück zum Feed ohne History-Eintrag:
navigate('/feed', {}, true);  // replace
```


## Migration — App.svelte

### Vorher

```javascript
const routes = {
  dashboard: Dashboard,
  library: Library,
  watch: Watch,
  // ...
};
let CurrentPage = $derived(routes[$currentRoute] || Dashboard);
```

### Nachher

```javascript
import { currentPage, routeId } from './lib/stores/router.js';

const pages = {
  dashboard: Dashboard,
  library: Library,
  watch: Watch,
  channel: ChannelDetail,
  playlist: Playlists,     // /playlist/:id → Detail, /playlists → Liste
  category: Categories,    // /category/:id → Videos, /categories → Liste
  archive: Archives,       // /archive/:id → Detail
  // ... rest gleich
};
let CurrentPage = $derived(pages[$currentPage] || Dashboard);
```


## Migration — Komponenten-Anpassung

### Watch.svelte

```javascript
// Vorher:
const vid = $currentVideoId;

// Nachher:
const vid = $routeId;  // aus URL /watch/:videoId
const startTime = Number($routeParams.t) || 0;
const initialTab = $routeParams.tab || 'info';
```

### ChannelDetail.svelte

```javascript
// Vorher:
const cid = $currentChannelId;

// Nachher:
const cid = $routeId;  // aus URL /channel/:channelId
const source = $routeParams.source || 'all';
const typeFilter = $routeParams.type || null;
```

### Library.svelte — Filter ↔ URL Sync

```javascript
// Beim Laden: URL-Parameter → lokale Filter
$effect(() => {
  const p = $routeParams;
  if (p.sort) sortBy = p.sort;
  if (p.order) sortOrder = p.order;
  if (p.type) multiFilter.types = p.type;
  if (p.channel) multiFilter.channels = p.channel;
  if (p.page) page = Number(p.page);
  // ... load()
});

// Bei Filter-Änderung: State → URL (replace, kein History-Spam)
function updateFilters() {
  navigate('/library', {
    sort: sortBy !== 'created_at' ? sortBy : null,
    order: sortOrder !== 'desc' ? sortOrder : null,
    type: multiFilter.types || null,
    channel: multiFilter.channels || null,
    page: page > 1 ? page : null,
  }, true);  // replace!
}
```


## Sidebar-Anpassung

```javascript
// Vorher:
function navigate(route) { currentRoute.set(route); }

// Nachher:
import { navigate } from '../stores/router.js';
// onclick → navigate('/library'), navigate('/feed'), etc.
```


## Header-Suche → URL

```javascript
// Suche abschicken:
function onSearch(query) {
  navigate('/search', { q: query });
}

// Suche mit Scope:
function onSearch(query, scope) {
  navigate('/search', { q: query, scope });
}
```


## VideoCard — Klick → URL

```javascript
// Vorher:
onclick={() => { currentVideoId.set(v.id); currentRoute.set('watch'); }}

// Nachher:
onclick={() => navigate(`/watch/${v.id}`)}
```


## Wichtige Regeln

1. **Filter → URL via `replace`** — Kein History-Eintrag pro Filter-Klick
2. **Navigation → URL via `push`** — Seiten-Wechsel = History-Eintrag
3. **Null-Parameter weglassen** — `/library` statt `/library?sort=&type=&page=`
4. **IDs in Pfad, Filter in Query** — REST-Prinzip
5. **Komponenten lesen aus URL** — Nicht aus separaten Stores
6. **URL ist Single Source of Truth** — Refresh = gleicher Zustand


## Implementierungs-Reihenfolge

1. `router.js` Store erstellen
2. `App.svelte` umstellen (route map)
3. `Sidebar.svelte` umstellen (navigate)
4. `Watch.svelte` — Video-ID aus URL
5. `ChannelDetail.svelte` — Channel-ID aus URL
6. `Library.svelte` — Filter ↔ URL Sync
7. `Feed.svelte` — Tab + Filter ↔ URL Sync
8. `Header/SearchDropdown` — Suche → URL
9. Alle VideoCards — onclick → navigate
10. Restliche Seiten (History, Archives, Favorites, etc.)
11. Alte Stores (`currentVideoId`, `currentChannelId`) entfernen


## Kompatibilität

- nginx `try_files $uri /index.html` → bereits konfiguriert ✓
- Alte Bookmarks auf `/` → landen auf Dashboard ✓
- API-Pfade `/api/*` → unverändert, kein Konflikt ✓
- Thumbnails `/thumbnails/*` → unverändert ✓


## Debug (Browser-Konsole)

```javascript
// Alle Routen anzeigen (wie Symfony debug:router)
TubeVault.router.debug()

// Aktuelle Route
TubeVault.router.state

// Navigations-Verlauf
TubeVault.router.history

// Programmatisch navigieren
TubeVault.router.navigate('/watch/dQw4w9WgXcQ')
```

Route-Fehler werden automatisch ins Live-Log gesendet (Kategorie: `router`).
Unbekannte Routen → Fallback auf Dashboard + Warning im Log.

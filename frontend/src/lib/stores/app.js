/**
 * TubeVault -  App Store v1.6.29
 * Kompatibilitäts-Bridge → delegiert an Router.
 * Alte Imports funktionieren weiterhin:
 *   import { currentRoute, currentVideoId } from '../stores/app.js'
 * © HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
 * SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
 */

import { writable } from 'svelte/store';
import {
  currentPage,
  routeId,
  routeParams,
  navigate,
  updateParams,
  currentRouteCompat,
  currentVideoIdCompat,
  currentChannelIdCompat,
} from '../router/router.js';

// ─── Kompatibilitäts-Exports (delegieren an Router) ──────

/** @deprecated — Nutze navigate('/route') stattdessen */
export const currentRoute = currentRouteCompat;

/** @deprecated — Nutze navigate('/watch/videoId') stattdessen */
export const currentVideoId = currentVideoIdCompat;

/** @deprecated — Nutze navigate('/channel/channelId') stattdessen */
export const currentChannelId = currentChannelIdCompat;

// ─── Nicht-Router Stores (bleiben hier) ──────────────────

export const sidebarOpen = writable(true);
export const searchQuery = writable('');

/** Wird inkrementiert wenn Backend neue Feed-Einträge meldet → Feed.svelte reagiert */
export const feedVersion = writable(0);

/** URL die von SearchDropdown → Downloads übergeben wird */
export const pendingDownloadUrl = writable(null);

// ─── Re-Exports für direkten Router-Zugriff ─────────────

export { navigate, updateParams, currentPage, routeId, routeParams };

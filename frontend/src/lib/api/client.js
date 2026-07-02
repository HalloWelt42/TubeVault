/**
 * TubeVault – API Client v1.5.91
 * © HalloWelt42 – Private Nutzung
 */

// Wird zum Build-Zeitpunkt aus package.json gesetzt (siehe vite.config.js → define).
// Fallback falls Build-Step den Wert nicht ersetzt (z.B. im Dev-Modus ohne Define).
export const FE_VERSION = typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : 'dev';

// Über Nginx-Proxy (Port 8032) → relative Pfade, Nginx leitet an Backend weiter
// Im Dev-Modus (vite:5173) → vite proxy in vite.config.js
// Direkt auf Backend → explizite URL
const API_BASE = (window.location.port === '8032' || window.location.port === '5173' || window.location.port === '')
  ? ''
  : `${window.location.protocol}//${window.location.hostname}:8031`;

// Verbindungsstatus (für Offline-Banner)
let _connectionOk = true;
let _connectionListeners = [];

export function onConnectionChange(fn) {
  _connectionListeners.push(fn);
  return () => { _connectionListeners = _connectionListeners.filter(f => f !== fn); };
}

function setConnectionStatus(ok) {
  if (ok !== _connectionOk) {
    _connectionOk = ok;
    _connectionListeners.forEach(fn => fn(ok));
  }
}

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`;
  // Bei FormData KEIN Content-Type setzen (Browser setzt multipart-Boundary selbst)
  const isFormData = options.body instanceof FormData;
  const defaultHeaders = isFormData ? {} : { 'Content-Type': 'application/json' };
  const config = {
    ...options,
    headers: { ...defaultHeaders, ...options.headers },
  };
  // Auto-stringify body if it's an object (aber nicht FormData)
  if (config.body && typeof config.body === 'object' && !isFormData) {
    config.body = JSON.stringify(config.body);
  }

  try {
    const res = await fetch(url, config);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    setConnectionStatus(true);
    return await res.json();
  } catch (e) {
    if (e.name === 'TypeError') {
      setConnectionStatus(false);
      throw new Error('Backend nicht erreichbar');
    }
    throw e;
  }
}

export const api = {
  baseUrl: API_BASE,
  request,
  // Videos
  getVideos: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request(`/api/videos${q ? '?' + q : ''}`);
  },
  getVideo: (id) => request(`/api/videos/${id}`),
  getVideoNeighbors: (id) => request(`/api/videos/${id}/neighbors`),
  getVideoLinks: (id) => request(`/api/videos/${id}/links`),
  createVideoLink: (videoId, linkedVideoId, sourceUrl) => request(`/api/videos/${videoId}/links`, {
    method: 'POST', body: JSON.stringify({ linked_video_id: linkedVideoId, source_url: sourceUrl })
  }),
  autoLinkDescription: (videoId) => request(`/api/videos/${videoId}/auto-link`, { method: 'POST' }),
  getVideoMetadata: (videoId) => request(`/api/videos/${videoId}/metadata`),
  upgradeVideo: (videoId, quality = 'best') =>
    request(`/api/videos/${videoId}/upgrade?quality=${quality}`, { method: 'POST' }),
  getVideoPreview: (id) => request(`/api/videos/preview/${id}`),
  getVideoInfo: (url) => request(`/api/videos/info?url=${encodeURIComponent(url)}`),
  updateVideo: (id, data) => request(`/api/videos/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  setVideoRating: (id, rating) => request(`/api/videos/${id}/rating?rating=${rating}`, { method: 'PATCH' }),
  deleteVideo: (id) => request(`/api/videos/${id}`, { method: 'DELETE' }),
  archiveVideo: (id) => request(`/api/videos/${id}/archive`, { method: 'POST' }),
  unarchiveVideo: (id) => request(`/api/videos/${id}/unarchive`, { method: 'POST' }),
  archiveBatch: (videoIds, unarchive = false) => request(`/api/videos/archive/batch?unarchive=${unarchive}`, { method: 'POST', body: JSON.stringify(videoIds) }),
  setTypeBatch: (videoIds, videoType) => request('/api/videos/type/batch', { method: 'POST', body: JSON.stringify({ video_ids: videoIds, video_type: videoType }) }),

  // Downloads
  addDownload: (data) => request('/api/downloads', { method: 'POST', body: JSON.stringify(data) }),
  addBatchDownload: (data) => request('/api/downloads/batch', { method: 'POST', body: JSON.stringify(data) }),
  getQueue: () => request('/api/downloads'),
  cancelDownload: (id) => request(`/api/downloads/${id}`, { method: 'DELETE' }),
  retryDownload: (id) => request(`/api/downloads/${id}/retry`, { method: 'POST' }),
  retryWithDelay: (id, minutes = 5) => request(`/api/downloads/${id}/retry-delay?minutes=${minutes}`, { method: 'POST' }),
  retryAllFailed: () => request('/api/downloads/retry-all', { method: 'POST' }),
  clearCompleted: () => request('/api/downloads/completed/clear', { method: 'DELETE' }),
  fixStaleDownloads: () => request('/api/downloads/fix-stale', { method: 'POST' }),
  clearAllDownloads: () => request('/api/downloads/clear-all', { method: 'DELETE' }),
  workerHealth: () => request('/api/downloads/worker/health'),
  restartWorker: () => request('/api/downloads/worker/restart', { method: 'POST' }),
  setDownloadCooldown: (seconds) => request(`/api/downloads/cooldown?seconds=${seconds}`, { method: 'PUT' }),
  setDownloadThrottle: (kbps, realtime = false) =>
    request(`/api/downloads/throttle?kbps=${kbps}&realtime=${realtime}`, { method: 'PUT' }),

  // Player
  streamUrl: (videoId) => `${API_BASE}/api/player/${videoId}`,
  thumbnailUrl: (videoId) => `${API_BASE}/api/player/${videoId}/thumbnail`,
  videoDownloadUrl: (videoId) => `${API_BASE}/api/player/${videoId}/download`,
  audioDownloadUrl: (videoId, format = 'mp3') => `${API_BASE}/api/player/${videoId}/audio/download?format=${format}`,

  // Heruntergeladene Streams eines Videos (DB) – für Qualität-Anzeige im Edit-Tab
  getStreams: (videoId) => request(`/api/videos/${videoId}/streams`),

  // Audio-Fix (falsche Tonspur korrigieren)
  audioFixTracks: (id) => request(`/api/player/${id}/audiofix/tracks`),
  audioFixStatus: (id) => request(`/api/player/${id}/audiofix/status`),
  audioFixFetch: (id) => request(`/api/player/${id}/audiofix/fetch`, { method: 'POST' }),
  audioFixAudioUrl: (id) => `${API_BASE}/api/player/${id}/audiofix/audio`,
  audioFixBuild: (id) => request(`/api/player/${id}/audiofix/build`, { method: 'POST' }),
  audioFixPreviewUrl: (id) => `${API_BASE}/api/player/${id}/audiofix/preview`,
  audioFixCommit: (id) => request(`/api/player/${id}/audiofix/commit`, { method: 'POST' }),
  audioFixDiscard: (id) => request(`/api/player/${id}/audiofix/discard`, { method: 'POST' }),
  savePosition: (id, pos) => request(`/api/videos/${id}/position?position=${Math.floor(pos)}`, { method: 'POST' }),
  recordPlay: (id, pos = 0) => request(`/api/videos/${id}/play?position=${Math.floor(pos)}`, { method: 'POST' }),

  // Watch History
  getHistory: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request(`/api/videos/history${q ? '?' + q : ''}`);
  },
  clearHistory: () => request('/api/videos/history', { method: 'DELETE' }),

  // Tags
  getAllTags: (filters = {}) => {
    const p = new URLSearchParams();
    if (filters.video_type) p.set('video_type', filters.video_type);
    if (filters.video_types) p.set('video_types', filters.video_types);
    if (filters.channel_ids) p.set('channel_ids', filters.channel_ids);
    if (filters.category_ids) p.set('category_ids', filters.category_ids);
    if (filters.archived) p.set('archived', 'true');
    const qs = p.toString();
    return request(`/api/videos/tags${qs ? '?' + qs : ''}`);
  },
  getVideoChannels: () => request('/api/videos/channels'),

  // YouTube Search
  searchYouTube: (q, maxResults = 15) => request(`/api/search/youtube?q=${encodeURIComponent(q)}&max_results=${maxResults}`),
  searchYouTubeFull: (q, maxResults = 10) => request(`/api/search/youtube/full?q=${encodeURIComponent(q)}&max_results=${maxResults}`),
  searchYouTubePaged: (q, page = 1, perPage = 20) => request(`/api/search/youtube/full?q=${encodeURIComponent(q)}&page=${page}&per_page=${perPage}`),
  resolveUrl: (url) => request('/api/search/resolve-url', { method: 'POST', body: JSON.stringify({ url }) }),
  searchLocal: (q, params = {}) => {
    const p = new URLSearchParams({ q, ...params }).toString();
    return request(`/api/search/local?${p}`);
  },

  // Playlists
  getPlaylists: () => request('/api/playlists'),
  getPlaylist: (id) => request(`/api/playlists/${id}`),
  createPlaylist: (data) => request('/api/playlists', { method: 'POST', body: JSON.stringify(data) }),
  updatePlaylist: (id, data) => request(`/api/playlists/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deletePlaylist: (id) => request(`/api/playlists/${id}`, { method: 'DELETE' }),
  addToPlaylist: (id, videoId, meta = {}) => request(`/api/playlists/${id}/videos`, { method: 'POST', body: JSON.stringify({ video_id: videoId, ...meta }) }),
  removeFromPlaylist: (id, videoId) => request(`/api/playlists/${id}/videos/${videoId}`, { method: 'DELETE' }),
  reorderPlaylist: (id, videoIds) => request(`/api/playlists/${id}/reorder`, { method: 'PUT', body: JSON.stringify({ video_ids: videoIds }) }),

  // Import

  // Lyrics
  getLyrics: (videoId) => request(`/api/lyrics/${videoId}`),
  detectMusic: (videoId) => request(`/api/lyrics/${videoId}/detect`, { method: 'POST' }),
  searchLyrics: (videoId, provider = 'auto') => request(`/api/lyrics/${videoId}/search`, { method: 'POST', body: JSON.stringify({ provider }) }),
  searchLyricsAll: (videoId) => request(`/api/lyrics/${videoId}/search-all`, { method: 'POST' }),
  pickLyrics: (videoId, data) => request(`/api/lyrics/${videoId}/pick`, { method: 'POST', body: JSON.stringify(data) }),
  saveMusicInfo: (videoId, data) => request(`/api/lyrics/${videoId}/music-info`, { method: 'POST', body: JSON.stringify(data) }),
  saveLyricsManual: (videoId, data) => request(`/api/lyrics/${videoId}/save`, { method: 'POST', body: JSON.stringify(data) }),
  deleteLyrics: (videoId) => request(`/api/lyrics/${videoId}`, { method: 'DELETE' }),
  // Lyrics (Einzelvideo — Batch entfernt v1.8.91)
  uploadLrc: (videoId, data) => request(`/api/lyrics/${videoId}/upload-lrc`, { method: 'POST', body: JSON.stringify(data) }),
  saveLyricsOffset: (videoId, offset) => request(`/api/lyrics/${videoId}/offset`, { method: 'POST', body: JSON.stringify({ offset }) }),
  lyricsFromSubtitle: (videoId, code) => request(`/api/lyrics/${videoId}/from-subtitle`, { method: 'POST', body: JSON.stringify({ subtitle_code: code }) }),

  // Chapters
  getChapters: (videoId) => request(`/api/chapters/${videoId}`),
  fetchYTChapters: (videoId) => request(`/api/chapters/${videoId}/fetch`, { method: 'POST' }),
  generateChapterThumbnails: (videoId) => request(`/api/chapters/${videoId}/generate-thumbnails`, { method: 'POST' }),
  addChapter: (videoId, data) => request(`/api/chapters/${videoId}`, { method: 'POST', body: JSON.stringify(data) }),
  deleteChapter: (chapterId) => request(`/api/chapters/${chapterId}`, { method: 'DELETE' }),

  // Ad-Markers (Werbemarken)
  getAdMarkers: (videoId) => request(`/api/ad-markers/${videoId}`),
  addAdMarker: (videoId, data) => request(`/api/ad-markers/${videoId}`, { method: 'POST', body: JSON.stringify(data) }),
  deleteAdMarker: (markerId) => request(`/api/ad-markers/${markerId}`, { method: 'DELETE' }),
  fetchSponsorBlock: (videoId, categories = null, replace = false) => {
    const q = new URLSearchParams();
    if (categories) q.set('categories', categories);
    if (replace) q.set('replace', 'true');
    return request(`/api/ad-markers/${videoId}/sponsorblock?${q}`, { method: 'POST' });
  },

  // Subtitles
  getSubtitles: (videoId) => request(`/api/player/${videoId}/subtitles`),
  subtitleUrl: (videoId, filename) => `${API_BASE}/api/player/${videoId}/subtitle/${filename}`,
  downloadSubtitles: (videoId, lang = 'de') => request(`/api/player/${videoId}/subtitles/download?lang=${lang}`, { method: 'POST' }),

  // Audio

  // Exports
  getExports: () => request('/api/exports'),
  deleteExport: (filename) => request(`/api/exports/${encodeURIComponent(filename)}`, { method: 'DELETE' }),
  cleanupTemp: () => request('/api/system/cleanup-temp', { method: 'POST' }),
  resetRateLimit: (category) => request(`/api/system/rate-limit/reset${category ? '?category=' + category : ''}`, { method: 'POST' }),
  toggleRateLimit: () => request('/api/system/rate-limit/toggle', { method: 'POST' }),
  cleanupGhosts: () => request('/api/system/cleanup-ghosts', { method: 'POST' }),
  cleanupFull: () => request('/api/system/cleanup-safe', { method: 'POST' }),
  getLogStats: () => request('/api/system/logs/stats'),
  getDockerLogs: (service = 'backend', n = 200) => request(`/api/system/logs/docker?service=${service}&n=${n}`),
  getMountpoints: () => request('/api/system/mountpoints'),

  // Favorites
  getFavorites: (listName) => {
    const q = listName ? `?list_name=${encodeURIComponent(listName)}` : '';
    return request(`/api/favorites${q}`);
  },
  getFavoriteLists: () => request('/api/favorites/lists'),
  addFavorite: (data) => request('/api/favorites', { method: 'POST', body: JSON.stringify(data) }),
  removeFavorite: (videoId) => request(`/api/favorites/video/${videoId}`, { method: 'DELETE' }),
  checkFavorite: (videoId) => request(`/api/favorites/check/${videoId}`),

  // Categories
  getCategories: () => request('/api/categories'),
  getCategoriesFlat: () => request('/api/categories/flat'),
  createCategory: (data) => request('/api/categories', { method: 'POST', body: JSON.stringify(data) }),
  updateCategory: (id, data) => request(`/api/categories/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteCategory: (id) => request(`/api/categories/${id}`, { method: 'DELETE' }),
  getCategoryVideos: (id, params = {}) => {
    const qs = Object.entries(params).filter(([,v]) => v != null).map(([k,v]) => `${k}=${encodeURIComponent(v)}`).join('&');
    return request(`/api/categories/${id}/videos${qs ? '?' + qs : ''}`);
  },
  autoAssignCategory: (catId, { channel, keyword } = {}) => {
    const params = new URLSearchParams();
    if (channel) params.set('channel', channel);
    if (keyword) params.set('keyword', keyword);
    return request(`/api/categories/${catId}/auto-assign?${params}`, { method: 'POST' });
  },
  getUnassignedStats: () => request('/api/categories/stats/unassigned'),
  cleanupCategoryOrphans: () => request('/api/categories/cleanup-orphans', { method: 'POST' }),
  getCategoryDebugStats: () => request('/api/categories/stats/debug'),
  quickChannelAssign: (channelName, categoryId = null) => {
    const params = new URLSearchParams({ channel_name: channelName });
    if (categoryId) params.set('category_id', categoryId);
    return request(`/api/categories/quick-channel-assign?${params}`, { method: 'POST' });
  },
  quickChannelAssignAll: () => request('/api/categories/quick-channel-assign-all', { method: 'POST' }),
  assignVideoCategories: (videoId, catIds) => request(`/api/categories/videos/${videoId}`, { method: 'POST', body: JSON.stringify(catIds) }),
  getVideoCategories: (videoId) => request(`/api/categories/videos/${videoId}`),

  // Settings
  getSettings: () => request('/api/settings'),
  getSetting: (key) => request(`/api/settings/${encodeURIComponent(key)}`),
  updateSetting: (key, value) => request(`/api/settings/${key}`, { method: 'PUT', body: JSON.stringify({ value }) }),
  resetSettings: () => request('/api/settings/reset', { method: 'POST' }),

  // System
  getBadges: () => request('/api/system/badges'),
  getStats: () => request('/api/system/stats'),
  getStatus: () => request('/api/system/status'),
  getStorage: () => request('/api/system/storage'),

  // Jobs (Unified Activity Tracking)
  getJobs: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request(`/api/jobs${q ? '?' + q : ''}`);
  },
  getActiveJobs: () => request('/api/jobs/active'),

  // Blocked Channels (YT-Suche)
  getBlockedChannels: () => request('/api/blocked-channels'),
  blockChannel: (channel_id, channel_name = null, reason = null) =>
    request('/api/blocked-channels', { method: 'POST',
      body: JSON.stringify({ channel_id, channel_name, reason }) }),
  unblockChannel: (channel_id) =>
    request(`/api/blocked-channels/${channel_id}`, { method: 'DELETE' }),

  // Ignored Videos (dauerhaft nicht erneut laden)
  getIgnoredVideos: (channel_id = null) =>
    request(`/api/ignored-videos${channel_id ? '?channel_id=' + channel_id : ''}`),
  ignoreVideo: (video_id, channel_id = null, reason = null) =>
    request('/api/ignored-videos', { method: 'POST',
      body: JSON.stringify({ video_id, channel_id, reason }) }),
  unignoreVideo: (video_id) =>
    request(`/api/ignored-videos/${video_id}`, { method: 'DELETE' }),

  // Cookies (yt-dlp Login-Session, optional)
  getCookiesStatus: () => request('/api/cookies'),
  uploadCookies: (file) => {
    const fd = new FormData();
    fd.append('file', file);
    // Content-Type explizit weglassen, damit fetch den multipart boundary setzt
    return request('/api/cookies', { method: 'POST', body: fd, headers: {} });
  },
  deleteCookies: () => request('/api/cookies', { method: 'DELETE' }),

  // Admin: Meta-Redundanz / Wiederaufbau
  adminRedundancyStatus: () => request('/api/admin/redundancy/status'),
  adminSidecarBackfill: () => request('/api/admin/redundancy/sidecars/backfill', { method: 'POST' }),
  adminUserdataExport: () => request('/api/admin/redundancy/userdata/export', { method: 'POST' }),
  adminUserdataRestore: (folder = null) =>
    request(`/api/admin/redundancy/userdata/restore${folder ? `?folder=${encodeURIComponent(folder)}` : ''}`, { method: 'POST' }),
  adminRebuildStart: (dryRun = false) =>
    request(`/api/admin/redundancy/rebuild?dry_run=${dryRun}`, { method: 'POST' }),

  // Admin: Textexport
  adminTextOverview: () => request('/api/admin/text-export/overview'),
  adminTextSyncAll: () => request('/api/admin/text-export/description/sync-all', { method: 'POST' }),
  adminTextSyncBatch: (limit = 100) =>
    request(`/api/admin/text-export/description/sync-batch?limit=${limit}`, { method: 'POST' }),
  adminTextList: ({ status = 'all', page = 1, per_page = 50, search = '', sort = 'created_at', order = 'desc', channel_id = '' } = {}) => {
    const p = new URLSearchParams({ status, page: String(page), per_page: String(per_page), sort, order });
    if (search) p.set('search', search);
    if (channel_id) p.set('channel_id', channel_id);
    return request(`/api/admin/text-export/description/list?${p.toString()}`);
  },
  adminTextSyncMany: (video_ids) =>
    request('/api/admin/text-export/description/sync-many', { method: 'POST', body: video_ids }),
  adminTextDeleteBulk: (video_ids) =>
    request('/api/admin/text-export/description/bulk', { method: 'DELETE', body: video_ids }),
  adminTextSyncOne: (video_id) =>
    request(`/api/admin/text-export/description/${encodeURIComponent(video_id)}`, { method: 'POST' }),
  adminTextGetFile: async (video_id) => {
    // Response ist text/plain, nicht JSON → direkt fetch
    const url = `${API_BASE}/api/admin/text-export/description/${encodeURIComponent(video_id)}/file`;
    const res = await fetch(url);
    if (!res.ok) {
      const j = await res.json().catch(() => ({ detail: 'Fehler' }));
      throw new Error(j.detail || `HTTP ${res.status}`);
    }
    return await res.text();
  },
  adminTextDelete: (video_id) =>
    request(`/api/admin/text-export/description/${encodeURIComponent(video_id)}`, { method: 'DELETE' }),
  adminChaptersSyncAll: () =>
    request('/api/admin/text-export/chapters/sync-all', { method: 'POST' }),
  adminChaptersSyncBatch: (limit = 100) =>
    request(`/api/admin/text-export/chapters/sync-batch?limit=${limit}`, { method: 'POST' }),
  adminChaptersSyncOne: (video_id) =>
    request(`/api/admin/text-export/chapters/${encodeURIComponent(video_id)}`, { method: 'POST' }),
  adminChaptersDelete: (video_id) =>
    request(`/api/admin/text-export/chapters/${encodeURIComponent(video_id)}`, { method: 'DELETE' }),
  adminTextBackupDescriptions: () =>
    request('/api/admin/text-export/backup/descriptions', { method: 'POST' }),
  adminTextListBackups: () => request('/api/admin/text-export/backup/list'),
  adminTextAudit: () => request('/api/admin/text-export/audit/description'),
  adminFtsRebuild: () => request('/api/admin/fts/rebuild', { method: 'POST' }),
  adminTextPurgeDbDescriptions: () =>
    request('/api/admin/text-export/purge-db-descriptions?confirm=YES', { method: 'POST' }),
  getJobStats: () => request('/api/jobs/stats'),
  getJob: (id) => request(`/api/jobs/${id}`),
  cancelJob: (id) => request(`/api/jobs/${id}/cancel`, { method: 'POST' }),
  unparkJob: (id) => request(`/api/jobs/${id}/unpark`, { method: 'POST' }),
  unparkAllJobs: () => request('/api/jobs/unpark-all', { method: 'POST' }),
  cleanupAllJobs: () => request('/api/jobs/cleanup-all', { method: 'DELETE' }),
  pauseQueue: (reason = 'user') => request(`/api/jobs/queue/pause?reason=${reason}`, { method: 'POST' }),
  resumeQueue: () => request('/api/jobs/queue/resume', { method: 'POST' }),
  getQueueStatus: () => request('/api/jobs/queue/status'),

  // Subscriptions (RSS)
  getSubscriptions: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request(`/api/subscriptions${q ? '?' + q : ''}`);
  },
  addSubscription: (data) => request('/api/subscriptions', { method: 'POST', body: JSON.stringify(data) }),
  addSubscriptionsBatch: (data) => request('/api/subscriptions/batch', { method: 'POST', body: JSON.stringify(data) }),
  updateSubscription: (id, data) => request(`/api/subscriptions/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  resetSuggestOverrides: (id) => request(`/api/subscriptions/${id}/reset-suggest-overrides`, { method: 'POST' }),
  getDripPrognosis: () => request('/api/subscriptions/drip-prognosis'),
  updateVideoSuggest: (videoId, override) => request(`/api/videos/${videoId}`, { method: 'PUT', body: JSON.stringify({ suggest_override: override }) }),
  removeSubscription: (id) => request(`/api/subscriptions/${id}`, { method: 'DELETE' }),
  getFeedVideos: (params = {}) => {
    const { channelId, channelIds, videoType = 'all', videoTypes, keywords, durationMin, durationMax, feedTab = 'active', page = 1, perPage = 40 } = params;
    const q = new URLSearchParams({ video_type: videoType, feed_tab: feedTab, page, per_page: perPage });
    if (channelId) q.set('channel_id', channelId);
    if (channelIds) q.set('channel_ids', channelIds);
    if (videoTypes) q.set('video_types', videoTypes);
    if (keywords) q.set('keywords', keywords);
    if (durationMin != null) q.set('duration_min', durationMin);
    if (durationMax != null) q.set('duration_max', durationMax);
    return request(`/api/subscriptions/feed?${q}`);
  },
  getFeedTags: (feedTab = 'active') =>
    request(`/api/subscriptions/feed/tags?feed_tab=${feedTab}`),
  getFeedChannels: (feedTab = 'active') =>
    request(`/api/subscriptions/feed/channels?feed_tab=${feedTab}`),
  // Feed-Status-Aktionen
  setFeedEntryStatus: (id, status) =>
    request(`/api/subscriptions/feed/${id}/status?status=${status}`, { method: 'POST' }),
  setFeedEntryType: (id, videoType) =>
    request(`/api/subscriptions/feed/${id}/type?video_type=${videoType}`, { method: 'POST' }),
  setFeedBulkType: (entryIds, videoType) =>
    request('/api/subscriptions/feed/bulk-type', {
      method: 'POST', body: JSON.stringify({ entry_ids: entryIds, video_type: videoType }),
    }),
  setVideoType: (videoId, videoType) =>
    request(`/api/subscriptions/feed/type-by-video?video_id=${encodeURIComponent(videoId)}&video_type=${videoType}`, { method: 'POST' }),
  dismissAllFeed: (channelId) => {
    const q = channelId ? `?channel_id=${encodeURIComponent(channelId)}` : '';
    return request(`/api/subscriptions/feed/dismiss-all${q}`, { method: 'POST' });
  },
  moveAllFeedStatus: (from, to, channelId) =>
    request('/api/subscriptions/feed/move-all', {
      method: 'POST', body: JSON.stringify({ from, to, channel_id: channelId || undefined }),
    }),
  triggerRSSPoll: () => request('/api/subscriptions/poll-now', { method: 'POST' }),
  resetAllIntervals: () => request('/api/subscriptions/interval/reset-all', { method: 'POST' }),
  halveInterval: (id) => request(`/api/subscriptions/${id}/interval/halve`, { method: 'POST' }),
  resetInterval: (id) => request(`/api/subscriptions/${id}/interval/reset`, { method: 'POST' }),
  // (reclassifyAll entfernt v1.6.21)
  getRSSStats: () => request('/api/subscriptions/stats'),
  getSchedulerStatus: () => request('/api/subscriptions/scheduler'),
  channelAvatarUrl: (channelId) => `${API_BASE}/api/subscriptions/avatar/${channelId}`,
  rssThumbUrl: (videoId) => `${API_BASE}/api/subscriptions/rss-thumb/${videoId}`,
  bannerUrl: (channelId) => `${API_BASE}/api/subscriptions/banner/${channelId}`,
  getChannelPlaylists: (channelId) => request(`/api/subscriptions/channel/${channelId}/playlists`),
  fetchChannelPlaylists: (channelId) => request(`/api/subscriptions/channel/${channelId}/fetch-playlists`, { method: 'POST' }),
  fetchPlaylistVideos: (playlistId) => request(`/api/subscriptions/playlists/${playlistId}/fetch-videos`, { method: 'POST' }),
  importPlaylistToLocal: (playlistId) => request(`/api/subscriptions/playlists/${playlistId}/import`, { method: 'POST' }),
  togglePlaylistVisibility: (playlistId, visibility) => request(`/api/subscriptions/playlists/local/${playlistId}/visibility`, { method: 'POST', body: JSON.stringify({ visibility }) }),

  // Kanal-Detail
  getChannelDetail: (channelId) => request(`/api/subscriptions/channel/${channelId}`),
  getChannelVideos: (channelId, source = 'all', page = 1, videoType = 'all', sort = 'newest') =>
    request(`/api/subscriptions/channel/${channelId}/videos?source=${source}&page=${page}&video_type=${videoType}&sort=${sort}`),
  getMissingVideos: (channelId, limit = 50, videoType = 'all') =>
    request(`/api/subscriptions/channel/${channelId}/missing-videos?limit=${limit}&video_type=${videoType}`),
  getChannelProblemVideos: (channelId) =>
    request(`/api/subscriptions/channel/${channelId}/problem-videos`),
  retryDownload: (jobId) =>
    request(`/api/downloads/${jobId}/retry`, { method: 'POST' }),
  cancelDownload: (jobId) =>
    request(`/api/downloads/${jobId}`, { method: 'DELETE' }),
  setDownloadPriority: (jobId, priority) =>
    request(`/api/downloads/${jobId}/priority?priority=${priority}`, { method: 'PATCH' }),
  fetchAllChannelVideos: (channelId) =>
    request(`/api/subscriptions/channel/${channelId}/fetch-all`, { method: 'POST' }),
  getChannelDebug: (channelId) =>
    request(`/api/subscriptions/channel/${channelId}/debug`),
  getChannelFilesystem: (channelId) =>
    request(`/api/subscriptions/channel/${channelId}/filesystem`),
  resetAllErrors: () =>
    request('/api/subscriptions/reset-errors', { method: 'POST' }),
  resetChannelError: (channelId) =>
    request(`/api/subscriptions/channel/${channelId}/reset-error`, { method: 'POST' }),

  // Archive
  getArchives: () => request('/api/archives'),
  addArchive: (data) => request('/api/archives', { method: 'POST', body: JSON.stringify(data) }),
  removeArchive: (id) => request(`/api/archives/${id}`, { method: 'DELETE' }),
  scanArchive: (id) => request(`/api/archives/${id}/scan`, { method: 'POST' }),
  checkMounts: () => request('/api/archives/check/mounts'),

  // ── Eigene Videos ──
  getOwnVideos: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request(`/api/own-videos?${q}`);
  },
  searchRss: (q, channel = null) => {
    const params = new URLSearchParams({ q });
    if (channel) params.set('channel', channel);
    return request(`/api/own-videos/search-rss?${params}`);
  },
  previewStreamUrl: (path) => `${API_BASE}/api/own-videos/preview/stream?path=${encodeURIComponent(path)}`,

  // Scan-Index
  scanStart: (path, youtubeArchive = true) =>
    request('/api/scan/start', { method: 'POST', body: JSON.stringify({ path, youtube_archive: youtubeArchive }) }),
  scanStop: () => request('/api/scan/stop', { method: 'POST' }),
  scanProgress: () => request('/api/scan/progress'),
  scanIndex: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request(`/api/scan/index?${q}`);
  },
  scanStats: () => request('/api/scan/stats'),
  scanFolders: () => request('/api/scan/folders'),
  scanRegister: (ids) => request('/api/scan/register', { method: 'POST', body: JSON.stringify({ ids }) }),
  scanRegisterAll: () => request('/api/scan/register-all', { method: 'POST' }),
  scanLink: (id, youtubeId, title = null, channel = null) =>
    request(`/api/scan/${id}/link`, { method: 'POST', body: JSON.stringify({ youtube_id: youtubeId, title, channel }) }),
  scanDeleteOriginal: (id) => request(`/api/scan/${id}/delete-original`, { method: 'POST' }),
  scanDeleteOriginals: (ids) => request('/api/scan/delete-originals', { method: 'POST', body: JSON.stringify({ ids }) }),

  // Sofort-Aktionen für Eigene Videos
  stagingLinkYoutube: (stagingId, youtubeId, categoryId = null) =>
    request(`/api/own-videos/staging/${stagingId}/link-youtube`, { method: 'POST', body: JSON.stringify({ youtube_id: youtubeId, category_id: categoryId }) }),
  stagingImportOwn: (stagingId, categoryId = null, channelName = null) =>
    request(`/api/own-videos/staging/${stagingId}/import-own`, { method: 'POST', body: JSON.stringify({ category_id: categoryId, channel_name: channelName }) }),
  stagingReplace: (stagingId) =>
    request(`/api/own-videos/staging/${stagingId}/replace`, { method: 'POST' }),
  stagingSkip: (stagingId) =>
    request(`/api/own-videos/staging/${stagingId}/skip`, { method: 'POST' }),
  stagingCleanupMissing: () =>
    request('/api/own-videos/staging/cleanup-missing', { method: 'POST' }),
  stagingDeleteFolder: (sessionId, folder) =>
    request(`/api/own-videos/staging/delete-folder?session_id=${sessionId}&folder=${encodeURIComponent(folder)}`, { method: 'POST' }),
  scanPreviewFrames: (id, count = 6) => request(`/api/scan/${id}/preview-frames?count=${count}`),
  scanFrameUrl: (id, index) => `${API_BASE}/api/scan/frame/${id}/${index}`,
  scanThumbUrl: (id) => `${API_BASE}/api/scan/${id}/thumb`,
  scanSetThumbnail: (id, frameIndex) => request(`/api/scan/${id}/set-thumbnail?frame_index=${frameIndex}`, { method: 'POST' }),
  scanRepairThumbnail: (videoId) => request(`/api/scan/repair-thumbnail/${videoId}`, { method: 'POST' }),
  enrichFromYoutube: (videoId) => request(`/api/scan/enrich/${videoId}`, { method: 'POST' }),
  autoEnrich: (videoId) => request(`/api/videos/${videoId}/auto-enrich`, { method: 'POST' }),
  saveNotes: (videoId, notes) => request(`/api/videos/${videoId}/notes`, { method: 'PUT', body: JSON.stringify({ notes }) }),
  searchNotes: (q) => request(`/api/videos/search/notes?q=${encodeURIComponent(q)}`),
  thumbnailAtPosition: (videoId, position) => request(`/api/scan/thumbnail-at-position/${videoId}?position=${position}`, { method: 'POST' }),
  fetchYtThumbnail: (videoId) => request(`/api/scan/fetch-yt-thumbnail/${videoId}`, { method: 'POST' }),
  cleanupRegistered: () => request('/api/scan/cleanup-registered', { method: 'POST' }),
  scanUpdateStatus: (id, status) => request(`/api/scan/${id}/status`, { method: 'PATCH', body: JSON.stringify({ status }) }),
  scanReset: () => request('/api/scan/reset', { method: 'DELETE' }),

  // Like/Dislike (Return YouTube Dislike API)
  getVideoLikes: (videoId, force = false) => request(`/api/videos/${videoId}/likes?force=${force}`),
  getLikesBatch: (videoIds) => request('/api/videos/likes/batch', { method: 'POST', body: JSON.stringify(videoIds) }),

  // API Endpoints
  getApiEndpoints: () => request('/api/endpoints'),
  createApiEndpoint: (data) => request('/api/endpoints', { method: 'POST', body: JSON.stringify(data) }),
  updateApiEndpoint: (id, data) => request(`/api/endpoints/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteApiEndpoint: (id) => request(`/api/endpoints/${id}`, { method: 'DELETE' }),
  testApiEndpoint: (id) => request(`/api/endpoints/${id}/test`, { method: 'POST' }),

  // Backup
  backupCreate: () => request(`/api/backup/create?frontend_version=${FE_VERSION}`, { method: 'POST' }),
  backupList: () => request('/api/backup/list'),
  backupStats: () => request('/api/backup/stats'),
  backupDelete: (filename) => request(`/api/backup/delete/${encodeURIComponent(filename)}`, { method: 'DELETE' }),
  backupRestore: (filename) => request(`/api/backup/restore/${encodeURIComponent(filename)}`, { method: 'POST' }),
  backupDownloadUrl: (filename) => `${API_BASE}/api/backup/download/${encodeURIComponent(filename)}`,
  backupRestoreUpload: async (file) => {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${API_BASE}/api/backup/restore-upload`, { method: 'POST', body: form });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || res.statusText); }
    return res.json();
  },

  // ─── Random Video (Sidebar-Vorschlag) ───
  getRandomVideo: (exclude = null, pool = 'all') => {
    const params = new URLSearchParams();
    if (exclude) params.set('exclude', exclude);
    if (pool && pool !== 'all') params.set('pool', pool);
    const qs = params.toString();
    return request(`/api/videos/random${qs ? `?${qs}` : ''}`);
  },

  // ─── (Batch-Queue entfernt v1.6.16) ───
};

// WebSocket für ALLE Job-/Aktivitäts-Updates
export function createActivitySocket(onMessage) {
  const wsProto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const wsBase = API_BASE
    ? API_BASE.replace(/^http/, 'ws')
    : `${wsProto}://${window.location.host}`;
  const wsUrl = wsBase + '/api/jobs/ws';
  let ws = null;
  let reconnectTimer = null;
  let pingTimer = null;

  function connect() {
    ws = new WebSocket(wsUrl);
    ws.onopen = () => {
      pingTimer = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send('ping');
      }, 25000);
    };
    ws.onmessage = (e) => {
      if (e.data === 'pong') return;
      try {
        onMessage(JSON.parse(e.data));
      } catch {}
    };
    ws.onclose = () => {
      clearInterval(pingTimer);
      reconnectTimer = setTimeout(connect, 3000);
    };
    ws.onerror = () => ws.close();
  }

  connect();

  return {
    close() {
      clearTimeout(reconnectTimer);
      clearInterval(pingTimer);
      if (ws) ws.close();
    },
  };
}

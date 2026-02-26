/**
 * TubeVault -  API Client Tests v1.5.2
 * © HalloWelt42
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { api, createProgressSocket, createActivitySocket } from '../lib/api/client.js';

// ============================================================
// API Base URL
// ============================================================
describe('API Base URL', () => {
  it('api.baseUrl ist leer für Port 8032 (Nginx-Proxy)', () => {
    // Setup setzt port auf 8032
    expect(api.baseUrl).toBe('');
  });
});

// ============================================================
// API Request & Error Handling
// ============================================================
describe('API Requests', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('getHealth sendet GET an /api/system/health', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'ok' }) })
    );
    const result = await api.getHealth();
    expect(fetch).toHaveBeenCalledWith('/api/system/health', expect.objectContaining({
      headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
    }));
    expect(result.status).toBe('ok');
  });

  it('wirft Error bei HTTP 404', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        json: () => Promise.resolve({ detail: 'Video nicht gefunden' }),
      })
    );
    await expect(api.getVideo(999)).rejects.toThrow('Video nicht gefunden');
  });

  it('wirft Error bei HTTP 500 ohne JSON-Body', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: () => Promise.reject(new Error('no json')),
      })
    );
    await expect(api.getHealth()).rejects.toThrow('Internal Server Error');
  });

  it('wirft "Backend nicht erreichbar" bei Netzwerkfehler', async () => {
    global.fetch = vi.fn(() =>
      Promise.reject(new TypeError('Failed to fetch'))
    );
    await expect(api.getHealth()).rejects.toThrow('Backend nicht erreichbar');
  });

  it('wirft originalen Fehler bei non-TypeError', async () => {
    const customErr = new Error('Custom error');
    customErr.name = 'AbortError';
    global.fetch = vi.fn(() => Promise.reject(customErr));
    await expect(api.getHealth()).rejects.toThrow('Custom error');
  });
});

// ============================================================
// Endpoint URL-Konstruktion
// ============================================================
describe('Endpoint URLs', () => {
  let lastUrl;

  beforeEach(() => {
    global.fetch = vi.fn((url) => {
      lastUrl = url;
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });
  });

  // Videos
  it('getVideos ohne Parameter', async () => {
    await api.getVideos();
    expect(lastUrl).toBe('/api/videos');
  });

  it('getVideos mit Parametern', async () => {
    await api.getVideos({ page: 2, per_page: 20 });
    expect(lastUrl).toBe('/api/videos?page=2&per_page=20');
  });

  it('getVideo mit ID', async () => {
    await api.getVideo(42);
    expect(lastUrl).toBe('/api/videos/42');
  });

  it('getVideoInfo encodiert URL', async () => {
    await api.getVideoInfo('https://youtu.be/abc123');
    expect(lastUrl).toContain('/api/videos/info?url=');
    expect(lastUrl).toContain(encodeURIComponent('https://youtu.be/abc123'));
  });

  // Downloads
  it('addDownload sendet POST', async () => {
    await api.addDownload({ url: 'https://youtu.be/test', quality: '720p' });
    expect(fetch).toHaveBeenCalledWith('/api/downloads', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ url: 'https://youtu.be/test', quality: '720p' }),
    }));
  });

  it('cancelDownload sendet DELETE', async () => {
    await api.cancelDownload(5);
    expect(fetch).toHaveBeenCalledWith('/api/downloads/5', expect.objectContaining({
      method: 'DELETE',
    }));
  });

  // Subscriptions
  it('getSubscriptions mit Pagination', async () => {
    await api.getSubscriptions({ page: 1, per_page: 200 });
    expect(lastUrl).toBe('/api/subscriptions?page=1&per_page=200');
  });

  it('getChannelDetail URL', async () => {
    await api.getChannelDetail('UCxxxxxxxx');
    expect(lastUrl).toBe('/api/subscriptions/channel/UCxxxxxxxx');
  });

  it('getChannelVideos mit allen Filtern', async () => {
    await api.getChannelVideos('UC123', 'rss', 2, 'short', 'popular');
    expect(lastUrl).toBe('/api/subscriptions/channel/UC123/videos?source=rss&page=2&video_type=short&sort=popular');
  });

  it('getChannelVideos Default-Werte', async () => {
    await api.getChannelVideos('UC123');
    expect(lastUrl).toBe('/api/subscriptions/channel/UC123/videos?source=all&page=1&video_type=all&sort=newest');
  });

  it('getChannelDebug URL', async () => {
    await api.getChannelDebug('UC123');
    expect(lastUrl).toBe('/api/subscriptions/channel/UC123/debug');
  });

  it('fetchAllChannelVideos sendet POST', async () => {
    await api.fetchAllChannelVideos('UC123');
    expect(fetch).toHaveBeenCalledWith(
      '/api/subscriptions/channel/UC123/fetch-all',
      expect.objectContaining({ method: 'POST' })
    );
  });

  it('channelAvatarUrl gibt korrekte URL', () => {
    const url = api.channelAvatarUrl('UC123');
    expect(url).toBe('/api/subscriptions/avatar/UC123');
  });

  // Feed
  it('getFeedVideos mit Channel-Filter', async () => {
    await api.getFeedVideos('UC123', 30);
    expect(lastUrl).toContain('/api/subscriptions/feed?channel_id=');
    expect(lastUrl).toContain('limit=30');
  });

  it('getFeedVideos ohne Filter', async () => {
    await api.getFeedVideos(null, 50);
    expect(lastUrl).toBe('/api/subscriptions/feed?limit=50');
  });

  it('dismissFeedEntry sendet POST', async () => {
    await api.dismissFeedEntry(7);
    expect(fetch).toHaveBeenCalledWith(
      '/api/subscriptions/feed/7/dismiss',
      expect.objectContaining({ method: 'POST' })
    );
  });

  // Favorites
  it('getFavorites mit Listenname', async () => {
    await api.getFavorites('Meine Liste');
    expect(lastUrl).toContain('list_name=');
    expect(lastUrl).toContain(encodeURIComponent('Meine Liste'));
  });

  it('getFavorites ohne Parameter', async () => {
    await api.getFavorites();
    expect(lastUrl).toBe('/api/favorites');
  });

  // Playlists
  it('addToPlaylist sendet POST mit video_id', async () => {
    await api.addToPlaylist(1, 42);
    expect(fetch).toHaveBeenCalledWith('/api/playlists/1/videos', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ video_id: 42 }),
    }));
  });

  // History
  it('getHistory mit Parametern', async () => {
    await api.getHistory({ page: 1, per_page: 50 });
    expect(lastUrl).toContain('/api/videos/history?');
    expect(lastUrl).toContain('page=1');
    expect(lastUrl).toContain('per_page=50');
  });

  // Search
  it('searchYouTube encodiert Query', async () => {
    await api.searchYouTube('python tutorial', 10);
    expect(lastUrl).toContain('/api/search/youtube?q=');
    expect(lastUrl).toContain('max_results=10');
  });

  // Player
  it('subtitleUrl gibt korrekte URL', () => {
    const url = api.subtitleUrl(42, 'de.vtt');
    expect(url).toBe('/api/player/42/subtitle/de.vtt');
  });

  it('audioUrl gibt korrekte URL', () => {
    const url = api.audioUrl(42);
    expect(url).toBe('/api/player/42/audio');
  });

  // Archives
  it('scanArchive sendet POST', async () => {
    await api.scanArchive(3);
    expect(fetch).toHaveBeenCalledWith(
      '/api/archives/3/scan',
      expect.objectContaining({ method: 'POST' })
    );
  });

  // Settings
  it('updateSetting sendet PUT mit Value', async () => {
    await api.updateSetting('download_quality', '1080p');
    expect(fetch).toHaveBeenCalledWith('/api/settings/download_quality', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ value: '1080p' }),
    }));
  });

  // Exports
  it('deleteExport encodiert Dateiname', async () => {
    await api.deleteExport('backup 2025.zip');
    expect(lastUrl).toBe(`/api/exports/${encodeURIComponent('backup 2025.zip')}`);
  });

  // Jobs
  it('getJobs mit Parametern', async () => {
    await api.getJobs({ status: 'running' });
    expect(lastUrl).toContain('status=running');
  });

  it('cancelJob sendet POST', async () => {
    await api.cancelJob('abc-123');
    expect(fetch).toHaveBeenCalledWith(
      '/api/jobs/abc-123/cancel',
      expect.objectContaining({ method: 'POST' })
    );
  });

  it('cleanupJobs mit Custom-Stunden', async () => {
    await api.cleanupJobs(48);
    expect(lastUrl).toBe('/api/jobs/cleanup?max_age_hours=48');
  });
});

// ============================================================
// API Endpoint Vollständigkeit
// ============================================================
describe('API Endpoint Vollständigkeit', () => {
  const allMethods = Object.keys(api).filter(k => typeof api[k] === 'function' || typeof api[k] === 'string');

  // Prüfen dass alle erwarteten Methoden existieren
  const expectedMethods = [
    // Videos
    'getVideos', 'getVideo', 'getVideoPreview', 'getVideoInfo',
    'updateVideo', 'deleteVideo', 'getVideoStats',
    // Downloads
    'addDownload', 'addBatchDownload', 'getQueue', 'cancelDownload',
    'retryDownload', 'clearCompleted', 'fixStaleDownloads', 'clearAllDownloads',
    // Player
    'savePosition', 'getPosition', 'recordPlay',
    // History
    'getHistory', 'clearHistory',
    // Tags
    'getAllTags',
    // Search
    'searchYouTube', 'searchLocal',
    // Playlists
    'getPlaylists', 'getPlaylist', 'createPlaylist', 'deletePlaylist',
    'addToPlaylist', 'removeFromPlaylist',
    // Import
    'importYTPlaylist', 'downloadSelectedPlaylistVideos',
    // Streams
    'analyzeStreams', 'getStreams', 'getStreamCombos',
    'saveStreamCombo', 'deleteStreamCombo',
    // Chapters
    'getChapters', 'fetchYTChapters',
    // Subtitles
    'getSubtitles', 'subtitleUrl', 'downloadSubtitles',
    // Audio
    'extractAudio', 'audioUrl',
    // Exports
    'getExports', 'createBackup', 'exportVideosJSON', 'exportVideosCSV',
    'exportSubsCSV', 'exportPlaylistsJSON', 'deleteExport', 'cleanupTemp',
    // Favorites
    'getFavorites', 'getFavoriteLists', 'addFavorite',
    'removeFavorite', 'checkFavorite',
    // Categories
    'getCategories', 'getCategoriesFlat', 'createCategory',
    'updateCategory', 'deleteCategory', 'getCategoryVideos',
    'assignVideoCategories', 'getVideoCategories',
    // Settings
    'getSettings', 'updateSetting',
    // System
    'getHealth', 'getStats', 'getStatus', 'getStorage',
    // Jobs
    'getJobs', 'getActiveJobs', 'getJobStats', 'getJob',
    'cancelJob', 'cleanupJobs',
    // Subscriptions
    'getSubscriptions', 'addSubscription', 'addSubscriptionsBatch',
    'updateSubscription', 'removeSubscription',
    'getFeedVideos', 'dismissFeedEntry', 'dismissAllFeed',
    'triggerRSSPoll', 'getRSSStats', 'channelAvatarUrl',
    // Channel Detail
    'getChannelDetail', 'getChannelVideos',
    'fetchAllChannelVideos', 'getChannelDebug',
    // Archives
    'getArchives', 'addArchive', 'removeArchive', 'scanArchive',
    'getArchiveVideos', 'checkMounts', 'resolveVideoPath', 'checkDuplicate',
  ];

  expectedMethods.forEach(method => {
    it(`api.${method} existiert`, () => {
      expect(api).toHaveProperty(method);
    });
  });
});

// ============================================================
// WebSocket Factories
// ============================================================
describe('WebSocket Factories', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    global.WebSocket = vi.fn(() => ({
      close: vi.fn(),
      send: vi.fn(),
      onopen: null,
      onclose: null,
      onmessage: null,
      onerror: null,
      readyState: 1,
    }));
    WebSocket.OPEN = 1;
  });

  it('createProgressSocket erstellt WebSocket Verbindung', () => {
    const onMsg = vi.fn();
    const socket = createProgressSocket(onMsg);
    expect(WebSocket).toHaveBeenCalled();
    const wsUrl = WebSocket.mock.calls[0][0];
    expect(wsUrl).toContain('/api/downloads/ws/progress');
    socket.close();
  });

  it('createActivitySocket erstellt WebSocket Verbindung', () => {
    const onMsg = vi.fn();
    const socket = createActivitySocket(onMsg);
    expect(WebSocket).toHaveBeenCalled();
    const wsUrl = WebSocket.mock.calls[0][0];
    expect(wsUrl).toContain('/api/jobs/ws');
    socket.close();
  });

  it('socket.close() schließt Verbindung', () => {
    const socket = createProgressSocket(vi.fn());
    socket.close();
    // Kein Fehler = OK
  });
});

"""
TubeVault Backend – Datenbank v1.5.1
© HalloWelt42 – Private Nutzung
"""

import aiosqlite
import logging
from pathlib import Path
from app.config import DB_PATH

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 28

SCHEMA_SQL = """
-- Videos (YouTube + lokale eigene Videos)
CREATE TABLE IF NOT EXISTS videos (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    channel_name TEXT,
    channel_id TEXT,
    description TEXT,
    duration INTEGER,
    upload_date TEXT,
    download_date TEXT,
    thumbnail_path TEXT,
    view_count INTEGER,
    like_count INTEGER,
    tags TEXT DEFAULT '[]',
    status TEXT DEFAULT 'pending',
    file_path TEXT,
    file_size INTEGER,
    storage_type TEXT DEFAULT 'local',
    archive_id INTEGER,
    notes TEXT,
    rating INTEGER DEFAULT 0,
    play_count INTEGER DEFAULT 0,
    last_played TEXT,
    last_position INTEGER DEFAULT 0,
    source TEXT DEFAULT 'youtube',
    source_url TEXT,
    video_type TEXT DEFAULT 'video',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    is_archived INTEGER DEFAULT 0,
    is_music INTEGER,
    music_artist TEXT,
    music_title TEXT,
    music_album TEXT,
    has_lyrics INTEGER DEFAULT 0,
    lyrics_source TEXT,
    lrclib_id INTEGER,
    FOREIGN KEY (archive_id) REFERENCES archives(id) ON DELETE SET NULL
);

-- Streams: Separate Audio/Video-Spuren
CREATE TABLE IF NOT EXISTS streams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    stream_type TEXT NOT NULL,
    itag INTEGER,
    mime_type TEXT,
    quality TEXT,
    codec TEXT,
    language TEXT,
    file_path TEXT,
    file_size INTEGER,
    bitrate INTEGER,
    sample_rate INTEGER,
    channels INTEGER,
    fps REAL,
    resolution TEXT,
    is_default BOOLEAN DEFAULT 0,
    is_combined BOOLEAN DEFAULT 0,
    downloaded BOOLEAN DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
);

-- Stream-Kombinationen
CREATE TABLE IF NOT EXISTS stream_combinations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    name TEXT,
    video_stream_id INTEGER,
    audio_stream_id INTEGER,
    audio_offset_ms INTEGER DEFAULT 0,
    is_default BOOLEAN DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE,
    FOREIGN KEY (video_stream_id) REFERENCES streams(id),
    FOREIGN KEY (audio_stream_id) REFERENCES streams(id)
);

-- Kapitel (YouTube-Kapitel + manuell erstellte)
CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    title TEXT NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL,
    thumbnail_url TEXT,
    source TEXT DEFAULT 'youtube',
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
);

-- Werbemarken (automatisch übersprungen beim Abspielen)
CREATE TABLE IF NOT EXISTS ad_markers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    label TEXT DEFAULT 'Werbung',
    source TEXT DEFAULT 'manual',
    category TEXT,
    sb_uuid TEXT,
    votes INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
);

-- Favoriten
CREATE TABLE IF NOT EXISTS favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    list_name TEXT DEFAULT 'Standard',
    position INTEGER DEFAULT 0,
    added_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
);

-- Kategorien (hierarchisch)
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    color TEXT DEFAULT '#6366f1',
    icon TEXT DEFAULT 'folder',
    parent_id INTEGER,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (parent_id) REFERENCES categories(id) ON DELETE SET NULL
);

-- Video <-> Kategorie (M:N)
CREATE TABLE IF NOT EXISTS video_categories (
    video_id TEXT NOT NULL,
    category_id INTEGER NOT NULL,
    PRIMARY KEY (video_id, category_id),
    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
);

-- Playlists (lokal + importierte YouTube-Playlists)
CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    source TEXT DEFAULT 'manual',
    source_url TEXT,
    source_id TEXT,
    thumbnail_path TEXT,
    video_count INTEGER DEFAULT 0,
    channel_id TEXT,
    visibility TEXT DEFAULT 'global',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS playlist_videos (
    playlist_id INTEGER NOT NULL,
    video_id TEXT NOT NULL,
    position INTEGER DEFAULT 0,
    PRIMARY KEY (playlist_id, video_id),
    FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
);

-- Einstellungen
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    description TEXT,
    category TEXT DEFAULT 'general'
);

-- Watch-History
CREATE TABLE IF NOT EXISTS watch_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    watched_at TEXT DEFAULT (datetime('now')),
    position INTEGER DEFAULT 0,
    completed BOOLEAN DEFAULT 0,
    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
);

-- Schema-Version
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now'))
);

-- Abonnements (YouTube-Kanäle)
CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL UNIQUE,
    channel_name TEXT,
    channel_url TEXT,
    thumbnail_url TEXT,
    avatar_path TEXT,
    channel_description TEXT,
    subscriber_count INTEGER,
    auto_download BOOLEAN DEFAULT 0,
    download_quality TEXT DEFAULT '720p',
    audio_only BOOLEAN DEFAULT 0,
    category_id INTEGER,
    last_checked TEXT,
    last_video_date TEXT,
    last_scanned TEXT,
    check_interval INTEGER DEFAULT 3600,
    error_count INTEGER DEFAULT 0,
    last_error TEXT,
    enabled BOOLEAN DEFAULT 1,
    video_count INTEGER DEFAULT 0,
    shorts_count INTEGER DEFAULT 0,
    live_count INTEGER DEFAULT 0,
    banner_url TEXT,
    channel_tags TEXT DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
);

-- RSS-Einträge (erkannte Videos aus Feeds)
CREATE TABLE IF NOT EXISTS rss_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    title TEXT,
    published TEXT,
    thumbnail_url TEXT,
    duration INTEGER,
    views INTEGER,
    description TEXT,
    video_type TEXT DEFAULT 'video',
    keywords TEXT DEFAULT '[]',
    status TEXT DEFAULT 'new',
    auto_queued BOOLEAN DEFAULT 0,
    dismissed BOOLEAN DEFAULT 0,
    feed_status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(video_id, channel_id)
);

-- Unified Job System
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'queued',
    progress REAL DEFAULT 0,
    result TEXT,
    error_message TEXT,
    metadata TEXT DEFAULT '{}',
    parent_id INTEGER,
    priority INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    started_at TEXT,
    completed_at TEXT,
    FOREIGN KEY (parent_id) REFERENCES jobs(id) ON DELETE SET NULL
);

-- Archive-Speicherorte
CREATE TABLE IF NOT EXISTS archives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    mount_path TEXT NOT NULL UNIQUE,
    type TEXT DEFAULT 'external',
    is_default BOOLEAN DEFAULT 0,
    auto_scan BOOLEAN DEFAULT 1,
    scan_pattern TEXT DEFAULT '*.mp4,*.mkv,*.webm',
    last_scan TEXT,
    last_seen TEXT,
    total_videos INTEGER DEFAULT 0,
    total_size INTEGER DEFAULT 0,
    enabled BOOLEAN DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Video-Archiv-Zuordnung
CREATE TABLE IF NOT EXISTS video_archives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    archive_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER,
    file_hash TEXT,
    discovered_at TEXT DEFAULT (datetime('now')),
    UNIQUE(video_id, archive_id),
    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE,
    FOREIGN KEY (archive_id) REFERENCES archives(id) ON DELETE CASCADE
);

-- Kanal-Playlists (YouTube)
CREATE TABLE IF NOT EXISTS channel_playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL,
    playlist_id TEXT NOT NULL UNIQUE,
    title TEXT,
    description TEXT,
    thumbnail_url TEXT,
    video_count INTEGER DEFAULT 0,
    video_ids TEXT DEFAULT '[]',
    fetched_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (channel_id) REFERENCES subscriptions(channel_id) ON DELETE CASCADE
);

"""

# Indizes separat – werden NACH Migration ausgeführt
INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
CREATE INDEX IF NOT EXISTS idx_videos_archived ON videos(is_archived);
CREATE INDEX IF NOT EXISTS idx_videos_channel ON videos(channel_id);
CREATE INDEX IF NOT EXISTS idx_videos_title ON videos(title);
CREATE INDEX IF NOT EXISTS idx_videos_source ON videos(source);
CREATE INDEX IF NOT EXISTS idx_streams_video ON streams(video_id);
CREATE INDEX IF NOT EXISTS idx_chapters_video ON chapters(video_id);
CREATE INDEX IF NOT EXISTS idx_favorites_video ON favorites(video_id);
CREATE INDEX IF NOT EXISTS idx_favorites_list ON favorites(list_name);
CREATE INDEX IF NOT EXISTS idx_watch_history_video ON watch_history(video_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_channel ON subscriptions(channel_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_enabled ON subscriptions(enabled);
CREATE INDEX IF NOT EXISTS idx_rss_entries_status ON rss_entries(status);
CREATE INDEX IF NOT EXISTS idx_rss_entries_channel ON rss_entries(channel_id);
CREATE INDEX IF NOT EXISTS idx_rss_entries_type ON rss_entries(video_type);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs(type);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_archives_mount ON archives(mount_path);
CREATE INDEX IF NOT EXISTS idx_video_archives_video ON video_archives(video_id);
CREATE INDEX IF NOT EXISTS idx_video_archives_archive ON video_archives(archive_id);
CREATE INDEX IF NOT EXISTS idx_channel_playlists_channel ON channel_playlists(channel_id);
"""

DEFAULT_SETTINGS = [
    ("download.quality", "720p", "Standard Download-Qualität", "download"),
    ("download.format", "mp4", "Standard Download-Format", "download"),
    ("download.concurrent", "2", "Gleichzeitige Downloads", "download"),
    ("download.auto_thumbnail", "true", "Thumbnail automatisch herunterladen", "download"),
    ("download.auto_subtitle", "false", "Untertitel automatisch herunterladen", "download"),
    ("download.subtitle_lang", "de,en", "Bevorzugte Untertitel-Sprachen", "download"),
    ("download.auto_chapters", "true", "Kapitel automatisch speichern", "download"),
    ("player.volume", "80", "Standard-Lautstärke (0-100)", "player"),
    ("player.autoplay", "false", "Automatische Wiedergabe", "player"),
    ("player.speed", "1.0", "Standard-Geschwindigkeit", "player"),
    ("player.save_position", "true", "Wiedergabeposition automatisch speichern", "player"),
    ("theme.mode", "dark", "Theme-Modus (dark/light)", "theme"),
    ("theme.accent", "#6366f1", "Accent-Farbe", "theme"),
    ("general.videos_per_page", "24", "Videos pro Seite", "general"),
    ("rss.enabled", "true", "RSS-Feed Polling aktiv", "rss"),
    ("rss.interval", "1800", "Standard Poll-Intervall in Sekunden", "rss"),
    ("rss.batch_size", "50", "Feeds pro Durchlauf", "rss"),
    ("rss.auto_download", "false", "Neue Videos automatisch herunterladen", "rss"),
    ("rss.auto_quality", "720p", "Qualität für Auto-Downloads", "rss"),
    ("rss.auto_dl_daily_limit", "20", "Max Auto-Downloads pro Tag", "rss"),
    ("rss.max_age_days", "90", "Neue Videos nur wenn juenger als X Tage", "rss"),
    ("feed.hide_shorts", "false", "Shorts im Feed ausblenden", "feed"),
    ("feed.auto_classify", "true", "Neue RSS-Videos automatisch als Short erkennen", "feed"),
    ("feed.auto_refresh", "true", "Kanaele periodisch im Hintergrund re-scannen", "feed"),
    ("feed.refresh_interval_days", "7", "Re-Scan Intervall in Tagen", "feed"),
    ("archive.scan_interval", "3600", "Archiv-Scan Intervall in Sekunden", "archive"),
    ("archive.mount_check_interval", "30", "Mount-Prüfung Intervall in Sekunden", "archive"),
    ("archive.auto_scan", "true", "Automatisch nach Videos scannen", "archive"),
    ("archive.scan_patterns", "*.mp4,*.mkv,*.webm,*.avi", "Dateiendungen für Scan", "archive"),
    ("archive.extract_id_from_filename", "true", "Video-ID aus Dateinamen extrahieren", "archive"),
]


class Database:
    """Async SQLite Database Manager."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._connection: aiosqlite.Connection | None = None

    async def connect(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(str(self.db_path))
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA foreign_keys=ON")
        await self._init_schema()
        logger.info(f"Datenbank verbunden: {self.db_path}")

    async def disconnect(self):
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("Datenbank getrennt")

    async def commit(self):
        """Expliziter Commit (für Batch-Operationen)."""
        if self._connection:
            await self._connection.commit()

    async def _init_schema(self):
        # 1. Tabellen erstellen (ohne Indexes auf neue Spalten)
        await self._connection.executescript(SCHEMA_SQL)

        # 2. Version prüfen
        cursor = await self._connection.execute(
            "SELECT MAX(version) FROM schema_version"
        )
        row = await cursor.fetchone()
        current_version = row[0] if row[0] else 0

        # 3. Migration v4: AI raus, neue Felder rein
        if current_version < 4:
            migrations = [
                "ALTER TABLE videos ADD COLUMN last_position INTEGER DEFAULT 0",
                "ALTER TABLE videos ADD COLUMN source TEXT DEFAULT 'youtube'",
                "ALTER TABLE videos ADD COLUMN source_url TEXT",
                "ALTER TABLE playlists ADD COLUMN source_url TEXT",
                "ALTER TABLE playlists ADD COLUMN video_count INTEGER DEFAULT 0",
                "ALTER TABLE subscriptions ADD COLUMN audio_only BOOLEAN DEFAULT 0",
            ]
            for sql in migrations:
                try:
                    await self._connection.execute(sql)
                except Exception:
                    pass
            await self._connection.execute("DELETE FROM settings WHERE category = 'ai'")

        # Migration v5: rss_entries + subscriptions erweitern
        if current_version < 5:
            v5_migrations = [
                "ALTER TABLE rss_entries ADD COLUMN duration INTEGER",
                "ALTER TABLE rss_entries ADD COLUMN views INTEGER",
                "ALTER TABLE rss_entries ADD COLUMN description TEXT",
                "ALTER TABLE subscriptions ADD COLUMN channel_description TEXT",
                "ALTER TABLE subscriptions ADD COLUMN subscriber_count INTEGER",
                "ALTER TABLE subscriptions ADD COLUMN last_scanned TEXT",
            ]
            for sql in v5_migrations:
                try:
                    await self._connection.execute(sql)
                except Exception:
                    pass

        # Migration v6: video_type, keywords, banner, shorts/live counts, tags
        if current_version < 6:
            v6_migrations = [
                "ALTER TABLE rss_entries ADD COLUMN video_type TEXT DEFAULT 'video'",
                "ALTER TABLE rss_entries ADD COLUMN keywords TEXT DEFAULT '[]'",
                "ALTER TABLE subscriptions ADD COLUMN banner_url TEXT",
                "ALTER TABLE subscriptions ADD COLUMN shorts_count INTEGER DEFAULT 0",
                "ALTER TABLE subscriptions ADD COLUMN live_count INTEGER DEFAULT 0",
                "ALTER TABLE subscriptions ADD COLUMN channel_tags TEXT DEFAULT '[]'",
            ]
            for sql in v6_migrations:
                try:
                    await self._connection.execute(sql)
                except Exception:
                    pass

        # Migration v7: video_type in videos-Tabelle + Backfill aus rss_entries
        if current_version < 7:
            v7_migrations = [
                "ALTER TABLE videos ADD COLUMN video_type TEXT DEFAULT 'video'",
                """UPDATE videos SET video_type = (
                    SELECT COALESCE(r.video_type, 'video')
                    FROM rss_entries r
                    WHERE r.video_id = videos.id
                    LIMIT 1
                ) WHERE EXISTS (
                    SELECT 1 FROM rss_entries r WHERE r.video_id = videos.id
                )""",
            ]
            for sql in v7_migrations:
                try:
                    await self._connection.execute(sql)
                except Exception:
                    pass

        # Migration v8: feed_status statt dismissed, background refresh
        if current_version < 8:
            v8_migrations = [
                # Neue Spalte feed_status (active/later/archived/dismissed)
                "ALTER TABLE rss_entries ADD COLUMN feed_status TEXT DEFAULT 'active'",
                # Bestehende dismissed=1 migrieren
                "UPDATE rss_entries SET feed_status = 'dismissed' WHERE dismissed = 1",
                # Bestehende dismissed=0 als active
                "UPDATE rss_entries SET feed_status = 'active' WHERE dismissed = 0 OR dismissed IS NULL",
                # max_age_days von 7 auf 30 erhoehen (mehr Videos im Feed)
                "UPDATE settings SET value = '90' WHERE key = 'rss.max_age_days' AND value = '7'",
            ]
            for sql in v8_migrations:
                try:
                    await self._connection.execute(sql)
                except Exception:
                    pass

        # Migration v9: Download-Queue Auto-Retry
        if current_version < 9:
            v9_migrations = [
                "ALTER TABLE download_queue ADD COLUMN retry_count INTEGER DEFAULT 0",
                "ALTER TABLE download_queue ADD COLUMN retry_after TEXT",
                "ALTER TABLE download_queue ADD COLUMN max_retries INTEGER DEFAULT 3",
            ]
            for sql in v9_migrations:
                try:
                    await self._connection.execute(sql)
                except Exception:
                    pass

        # Migration v10: max_age_days auf 90 erhoehen + Rescan aller Kanaele
        if current_version < 10:
            v10_migrations = [
                "UPDATE settings SET value = '90' WHERE key = 'rss.max_age_days'",
                # Alle Kanaele als 'nie gecheckt' markieren → Rescan mit neuem max_age
                "UPDATE subscriptions SET last_checked = NULL WHERE enabled = 1",
            ]
            for sql in v10_migrations:
                try:
                    await self._connection.execute(sql)
                except Exception:
                    pass

        # Migration v11: check_interval Reset (Bug: wurde bei Fehler verdoppelt, nie zurueckgesetzt)
        if current_version < 11:
            v11_migrations = [
                # Alle aufgeblähten Intervalle auf den rss.interval-Wert zurücksetzen
                """UPDATE subscriptions SET check_interval = COALESCE(
                     (SELECT CAST(value AS INTEGER) FROM settings WHERE key = 'rss.interval'),
                     1800
                   ) WHERE check_interval > 3600 AND error_count = 0""",
                # Fehler-Kanäle: Intervall proportional zum Error-Count, max 24h
                """UPDATE subscriptions SET check_interval = MIN(
                     COALESCE((SELECT CAST(value AS INTEGER) FROM settings WHERE key = 'rss.interval'), 1800)
                     * (1 + error_count),
                     86400
                   ) WHERE error_count > 0""",
            ]
            for sql in v11_migrations:
                try:
                    await self._connection.execute(sql)
                    logger.info(f"Migration v11: {sql[:60]}… OK")
                except Exception as e:
                    logger.warning(f"Migration v11 Fehler: {e}")

        # Migration v12: import_path Spalte fuer eigene Videos
        if current_version < 12:
            v12_migrations = [
                "ALTER TABLE videos ADD COLUMN import_path TEXT",
                # Bestehende lokale Videos: import_path = file_path
                "UPDATE videos SET import_path = file_path WHERE source = 'local'",
            ]
            for sql in v12_migrations:
                try:
                    await self._connection.execute(sql)
                    logger.info(f"Migration v12: {sql[:60]}… OK")
                except Exception as e:
                    logger.warning(f"Migration v12 Fehler: {e}")

        # Migration v13: ad_markers um source/category/sb_uuid erweitern
        if current_version < 13:
            v13_migrations = [
                "ALTER TABLE ad_markers ADD COLUMN source TEXT DEFAULT 'manual'",
                "ALTER TABLE ad_markers ADD COLUMN category TEXT",
                "ALTER TABLE ad_markers ADD COLUMN sb_uuid TEXT",
                "ALTER TABLE ad_markers ADD COLUMN votes INTEGER",
            ]
            for sql in v13_migrations:
                try:
                    await self._connection.execute(sql)
                    logger.info(f"Migration v13: {sql[:60]}… OK")
                except Exception as e:
                    logger.warning(f"Migration v13 Fehler: {e}")

        # Migration v14: channel_playlists Tabelle
        if current_version < 14:
            v14_migrations = [
                """CREATE TABLE IF NOT EXISTS channel_playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT NOT NULL,
                    playlist_id TEXT NOT NULL UNIQUE,
                    title TEXT,
                    description TEXT,
                    thumbnail_url TEXT,
                    video_count INTEGER DEFAULT 0,
                    video_ids TEXT DEFAULT '[]',
                    fetched_at TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (channel_id) REFERENCES subscriptions(channel_id) ON DELETE CASCADE
                )""",
                "CREATE INDEX IF NOT EXISTS idx_channel_playlists_channel ON channel_playlists(channel_id)",
            ]
            for sql in v14_migrations:
                try:
                    await self._connection.execute(sql)
                    logger.info(f"Migration v14: {sql[:60]}… OK")
                except Exception as e:
                    logger.warning(f"Migration v14 Fehler: {e}")

        if current_version < 15:
            v15_migrations = [
                """CREATE TABLE IF NOT EXISTS video_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id TEXT NOT NULL,
                    linked_video_id TEXT NOT NULL,
                    source_url TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(video_id, linked_video_id)
                )""",
                "CREATE INDEX IF NOT EXISTS idx_video_links_video ON video_links(video_id)",
                "CREATE INDEX IF NOT EXISTS idx_video_links_linked ON video_links(linked_video_id)",
            ]
            for sql in v15_migrations:
                try:
                    await self._connection.execute(sql)
                    logger.info(f"Migration v15: {sql[:60]}… OK")
                except Exception as e:
                    logger.warning(f"Migration v15 Fehler: {e}")

        # Migration v16: Like/Dislike-Daten + API-Endpoints-Registry
        if current_version < 16:
            v16_migrations = [
                "ALTER TABLE videos ADD COLUMN dislike_count INTEGER",
                "ALTER TABLE videos ADD COLUMN like_ratio REAL",
                "ALTER TABLE videos ADD COLUMN likes_fetched_at TEXT",
                """CREATE TABLE IF NOT EXISTS api_endpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    label TEXT NOT NULL,
                    url TEXT NOT NULL,
                    category TEXT DEFAULT 'external',
                    enabled BOOLEAN DEFAULT 1,
                    test_path TEXT,
                    description TEXT,
                    last_tested TEXT,
                    last_status TEXT,
                    sort_order INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now'))
                )""",
            ]
            for sql in v16_migrations:
                try:
                    await self._connection.execute(sql)
                    logger.info(f"Migration v16: {sql[:60]}… OK")
                except Exception as e:
                    logger.warning(f"Migration v16 Fehler: {e}")

            # Standard-Endpunkte einfügen
            default_endpoints = [
                ("ryd_api", "Return YouTube Dislike", "https://returnyoutubedislikeapi.com", "external", "/votes?videoId=dQw4w9WgXcQ", "Like/Dislike-Daten für Videos", 1),
                ("backend_api", "TubeVault Backend", "http://localhost:8031", "internal", "/api/system/info", "Eigenes Backend (FastAPI)", 0),
                ("youtube_rss", "YouTube RSS", "https://www.youtube.com", "external", "/feeds/videos.xml?channel_id=UC_x5XG1OV2P6uZZ5FSM9Ttw", "YouTube RSS-Feeds für Abos", 2),
                ("lrclib_api", "LRCLIB", "https://lrclib.net/api", "external", "/search?q=test", "Lyrics-Datenbank (Synced + Plain)", 3),
                ("sponsorblock_api", "SponsorBlock", "https://sponsor.ajay.app", "external", "/api/skipSegments?videoID=dQw4w9WgXcQ&categories=[%22sponsor%22]", "Werbung/Sponsor-Segmente in Videos", 4),
                ("youtube_thumbs", "YouTube Thumbnails", "https://i.ytimg.com", "external", "/vi/dQw4w9WgXcQ/hqdefault.jpg", "Video-Vorschaubilder von YouTube", 5),
            ]
            for name, label, url, cat, test, desc, sort in default_endpoints:
                try:
                    await self._connection.execute(
                        "INSERT OR IGNORE INTO api_endpoints (name, label, url, category, test_path, description, sort_order) VALUES (?,?,?,?,?,?,?)",
                        (name, label, url, cat, test, desc, sort)
                    )
                except Exception:
                    pass

        # Migration v17: is_archived Flag + Kategorie-Hierarchie entfernen
        if current_version < 17:
            v17_migrations = [
                "ALTER TABLE videos ADD COLUMN is_archived INTEGER DEFAULT 0",
            ]
            for sql in v17_migrations:
                try:
                    await self._connection.execute(sql)
                    logger.info(f"Migration v17: {sql[:60]}… OK")
                except Exception as e:
                    logger.warning(f"Migration v17 Fehler: {e}")

        # Migration v18: Batch-Queue für Schleich-Downloads
        if current_version < 18:
            v18_migrations = [
                """CREATE TABLE IF NOT EXISTS batch_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    title TEXT,
                    channel_name TEXT,
                    thumbnail_url TEXT,
                    duration INTEGER,
                    source_playlist TEXT,
                    source_playlist_title TEXT,
                    status TEXT DEFAULT 'waiting',
                    added_at TEXT DEFAULT (datetime('now')),
                    started_at TEXT,
                    completed_at TEXT,
                    removed_at TEXT,
                    removal_reason TEXT,
                    error_message TEXT,
                    batch_group INTEGER
                )""",
            ]
            for sql in v18_migrations:
                try:
                    await self._connection.execute(sql)
                    logger.info(f"Migration v18: batch_queue OK")
                except Exception as e:
                    logger.warning(f"Migration v18 Fehler: {e}")

        # Migration v19: AI-Thumbnail-Analyse Spalten
        if current_version < 19:
            for sql in [
                "ALTER TABLE videos ADD COLUMN ai_analysis TEXT DEFAULT NULL",
                "ALTER TABLE videos ADD COLUMN ai_analyzed_at TEXT DEFAULT NULL",
                "ALTER TABLE rss_entries ADD COLUMN ai_analysis TEXT DEFAULT NULL",
            ]:
                try:
                    await self._connection.execute(sql)
                    logger.info(f"Migration v19: {sql[:60]}… OK")
                except Exception as e:
                    logger.warning(f"Migration v19 Fehler: {e}")

        # Migration v20: download_queue Tabelle entfernen (ersetzt durch jobs)
        if current_version < 20:
            try:
                await self._connection.execute("DROP TABLE IF EXISTS download_queue")
                logger.info("Migration v20: download_queue Tabelle entfernt (→ jobs)")
            except Exception as e:
                logger.warning(f"Migration v20 Fehler: {e}")

        if current_version < 21:
            try:
                from app.utils.tag_utils import sanitize_tags_json
                # Videos: tags bereinigen
                rows = await self._connection.execute_fetchall(
                    "SELECT id, tags FROM videos WHERE tags IS NOT NULL AND tags != '[]'"
                )
                cleaned_v = 0
                for row in rows:
                    old = row[1]
                    new = sanitize_tags_json(old)
                    if old != new:
                        await self._connection.execute(
                            "UPDATE videos SET tags = ? WHERE id = ?", (new, row[0]))
                        cleaned_v += 1
                # Subscriptions: channel_tags bereinigen
                rows2 = await self._connection.execute_fetchall(
                    "SELECT id, channel_tags FROM subscriptions WHERE channel_tags IS NOT NULL AND channel_tags != '[]'"
                )
                cleaned_s = 0
                for row in rows2:
                    old = row[1]
                    new = sanitize_tags_json(old)
                    if old != new:
                        await self._connection.execute(
                            "UPDATE subscriptions SET channel_tags = ? WHERE id = ?", (new, row[0]))
                        cleaned_s += 1
                # rss_entries: keywords bereinigen
                rows3 = await self._connection.execute_fetchall(
                    "SELECT id, keywords FROM rss_entries WHERE keywords IS NOT NULL AND keywords != '[]'"
                )
                cleaned_r = 0
                for row in rows3:
                    old = row[1]
                    new = sanitize_tags_json(old)
                    if old != new:
                        await self._connection.execute(
                            "UPDATE rss_entries SET keywords = ? WHERE id = ?", (new, row[0]))
                        cleaned_r += 1
                logger.info(f"Migration v21: Tags bereinigt – {cleaned_v} Videos, {cleaned_s} Subs, {cleaned_r} RSS")
            except Exception as e:
                logger.warning(f"Migration v21 Fehler: {e}")

        if current_version < 22:
            # v22: Musik/Lyrics-Spalten
            for col, typedef in [
                ("is_music", "INTEGER"),
                ("music_artist", "TEXT"),
                ("music_title", "TEXT"),
                ("music_album", "TEXT"),
                ("has_lyrics", "INTEGER DEFAULT 0"),
                ("lyrics_source", "TEXT"),
                ("lrclib_id", "INTEGER"),
            ]:
                try:
                    await self._connection.execute(f"ALTER TABLE videos ADD COLUMN {col} {typedef}")
                except Exception:
                    pass  # Spalte existiert bereits
            logger.info("Migration v22: Musik/Lyrics-Spalten hinzugefügt")

        if current_version < 23:
            try:
                await self._connection.execute("ALTER TABLE videos ADD COLUMN lrclib_id INTEGER")
            except Exception:
                pass  # Spalte existiert bereits
            logger.info("Migration v23: lrclib_id Spalte hinzugefügt")

        if current_version < 24:
            # Playlists: Kanal-Verknüpfung + Sichtbarkeit
            for col, typedef in [
                ("channel_id", "TEXT"),
                ("visibility", "TEXT DEFAULT 'global'"),
            ]:
                try:
                    await self._connection.execute(f"ALTER TABLE playlists ADD COLUMN {col} {typedef}")
                except Exception:
                    pass
            # Bestehende YouTube-Imports verknüpfen
            try:
                await self._connection.execute("""
                    UPDATE playlists SET channel_id = (
                        SELECT cp.channel_id FROM channel_playlists cp
                        WHERE cp.playlist_id = playlists.source_id
                    ) WHERE source = 'youtube' AND source_id IS NOT NULL AND channel_id IS NULL
                """)
            except Exception:
                pass
            logger.info("Migration v24: Playlists channel_id + visibility")

        if current_version < 25:
            # Fix: Backend-URL 8021 → 8031
            try:
                await self._connection.execute(
                    "UPDATE api_endpoints SET url = 'http://localhost:8031' WHERE name = 'backend_api' AND url = 'http://localhost:8021'"
                )
            except Exception:
                pass
            # Neue Service-Endpoints hinzufügen
            new_eps = [
                ("lrclib_api", "LRCLIB", "https://lrclib.net/api", "external", "/search?q=test", "Lyrics-Datenbank (Synced + Plain)", 3),
                ("sponsorblock_api", "SponsorBlock", "https://sponsor.ajay.app", "external", "/api/skipSegments?videoID=dQw4w9WgXcQ&categories=[%22sponsor%22]", "Werbung/Sponsor-Segmente in Videos", 4),
                ("youtube_thumbs", "YouTube Thumbnails", "https://i.ytimg.com", "external", "/vi/dQw4w9WgXcQ/hqdefault.jpg", "Video-Vorschaubilder von YouTube", 5),
            ]
            for name, label, url, cat, test, desc, sort in new_eps:
                try:
                    await self._connection.execute(
                        "INSERT OR IGNORE INTO api_endpoints (name, label, url, category, test_path, description, sort_order) VALUES (?,?,?,?,?,?,?)",
                        (name, label, url, cat, test, desc, sort)
                    )
                except Exception:
                    pass
            logger.info("Migration v25: API-Endpoints Cleanup + neue Services")

        # Migration v26: Enrichment-Log (Auto-Anreicherung Tracking)
        if current_version < 26:
            try:
                await self._connection.executescript("""
                    CREATE TABLE IF NOT EXISTS enrichment_log (
                        video_id TEXT NOT NULL,
                        type TEXT NOT NULL,
                        attempted_at TEXT NOT NULL DEFAULT (datetime('now')),
                        success INTEGER DEFAULT 0,
                        result_count INTEGER DEFAULT 0,
                        error TEXT,
                        PRIMARY KEY (video_id, type)
                    );
                """)
                logger.info("Migration v26: enrichment_log Tabelle erstellt")
            except Exception as e:
                logger.warning(f"Migration v26 Fehler: {e}")

        if current_version < 27:
            try:
                await self._connection.executescript("""
                    CREATE TABLE IF NOT EXISTS scan_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_id INTEGER,
                        scan_path TEXT NOT NULL,
                        youtube_archive BOOLEAN DEFAULT 1,
                        status TEXT DEFAULT 'running',
                        total_files INTEGER DEFAULT 0,
                        scanned_files INTEGER DEFAULT 0,
                        created_at TEXT DEFAULT (datetime('now')),
                        finished_at TEXT
                    );

                    CREATE TABLE IF NOT EXISTS scan_staging (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id INTEGER NOT NULL,
                        file_path TEXT NOT NULL,
                        filename TEXT,
                        folder_name TEXT,
                        title TEXT,
                        channel_name TEXT,
                        duration INTEGER,
                        file_size INTEGER DEFAULT 0,
                        resolution TEXT,
                        codec TEXT,
                        youtube_id TEXT,
                        is_portrait BOOLEAN DEFAULT 0,
                        nfo_found BOOLEAN DEFAULT 0,
                        thumbnail_path TEXT,
                        description_text TEXT,
                        subtitles_found TEXT,
                        match_type TEXT DEFAULT 'none',
                        match_id TEXT,
                        match_title TEXT,
                        match_channel TEXT,
                        match_confidence REAL DEFAULT 0,
                        match_duration INTEGER,
                        duration_boost BOOLEAN DEFAULT 0,
                        duration_penalty BOOLEAN DEFAULT 0,
                        match_candidates TEXT DEFAULT '[]',
                        already_registered BOOLEAN DEFAULT 0,
                        existing_id TEXT,
                        decision TEXT,
                        decision_channel TEXT,
                        decision_at TEXT,
                        FOREIGN KEY (session_id) REFERENCES scan_sessions(id) ON DELETE CASCADE
                    );

                    CREATE INDEX IF NOT EXISTS idx_scan_staging_session ON scan_staging(session_id);
                    CREATE INDEX IF NOT EXISTS idx_scan_staging_decision ON scan_staging(session_id, decision);
                    CREATE INDEX IF NOT EXISTS idx_scan_staging_match ON scan_staging(session_id, match_type);
                """)
                logger.info("Migration v27: scan_sessions + scan_staging Tabellen erstellt")
            except Exception as e:
                logger.warning(f"Migration v27 Fehler: {e}")

        if current_version < 28:
            try:
                # Drip-Feed Spalten
                for col, default in [
                    ("drip_enabled", "0"), ("drip_count", "3"),
                    ("drip_auto_archive", "0"), ("drip_next_run", "NULL"),
                    ("drip_completed_at", "NULL"), ("suggest_exclude", "0"),
                ]:
                    try:
                        await self._connection.execute(
                            f"ALTER TABLE subscriptions ADD COLUMN {col} {'TEXT' if 'run' in col or 'completed' in col else 'INTEGER'} DEFAULT {default}"
                        )
                    except Exception:
                        pass

                # Video suggest_override
                try:
                    await self._connection.execute(
                        "ALTER TABLE videos ADD COLUMN suggest_override TEXT DEFAULT NULL"
                    )
                except Exception:
                    pass

                await self._connection.commit()
                logger.info("Migration v28: drip-feed + suggest-exclude Spalten")
            except Exception as e:
                logger.warning(f"Migration v28 Fehler: {e}")

        # 4. Indexes NACH Migration (braucht source-Spalte)
        await self._connection.executescript(INDEXES_SQL)

        if current_version < SCHEMA_VERSION:
            await self._connection.execute(
                "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,)
            )

        for key, value, desc, cat in DEFAULT_SETTINGS:
            await self._connection.execute(
                """INSERT OR IGNORE INTO settings (key, value, description, category)
                   VALUES (?, ?, ?, ?)""",
                (key, value, desc, cat)
            )

        await self._connection.commit()
        logger.info(f"Schema v{SCHEMA_VERSION} initialisiert")

    @property
    def conn(self) -> aiosqlite.Connection:
        if not self._connection:
            raise RuntimeError("Datenbank nicht verbunden")
        return self._connection

    async def execute(self, sql: str, params=None):
        cursor = await self.conn.execute(sql, params or ())
        await self.conn.commit()
        return cursor

    async def fetch_one(self, sql: str, params=None):
        cursor = await self.conn.execute(sql, params or ())
        return await cursor.fetchone()

    async def fetch_all(self, sql: str, params=None):
        cursor = await self.conn.execute(sql, params or ())
        return await cursor.fetchall()

    async def fetch_val(self, sql: str, params=None):
        row = await self.fetch_one(sql, params)
        return row[0] if row else None


# Singleton
db = Database()

"""
TubeVault Backend – Main Application v1.3.0
© HalloWelt42 – Private Nutzung

Selbstgehostetes Video-Vault & Streaming-System
FastAPI Backend mit pytubefix, FFmpeg und SQLite
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import (
    VERSION, APP_NAME, HOST, PORT,
    CORS_ORIGINS, THUMBNAILS_DIR, SUBTITLES_DIR, AVATARS_DIR, DATA_DIR,
    ensure_directories,
)
from app.database import db
from app.database_scan import scan_db
from app.services.download_service import download_service
from app.services.job_service import job_service
from app.services.rss_service import rss_service
from app.services.task_manager import task_manager
from app.routers import (
    videos, downloads, player, favorites, categories, settings, system,
    jobs, subscriptions, playlists, chapters, search, exports, imports,
    streams, ad_markers, own_videos, scan, backup, api_endpoints,
    feed_router, channel_playlists, lyrics,
)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# httpx loggt jeden HTTP-Request (auch erwartbare 404s) → nur Warnungen zeigen
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


async def _backfill_banners():
    """Externe Banner-URLs beim Start lokal cachen."""
    import asyncio
    await asyncio.sleep(30)  # Warte bis System bereit
    try:
        import httpx
        from app.config import BANNERS_DIR
        BANNERS_DIR.mkdir(parents=True, exist_ok=True)
        rows = await db.fetch_all(
            "SELECT channel_id, banner_url FROM subscriptions "
            "WHERE banner_url IS NOT NULL AND banner_url NOT LIKE '/api/%'")
        cached = 0
        for row in rows:
            dest = BANNERS_DIR / f"{row['channel_id']}.jpg"
            if dest.exists() and dest.stat().st_size > 1000:
                await db.execute(
                    "UPDATE subscriptions SET banner_url = ? WHERE channel_id = ?",
                    (f"/api/subscriptions/banner/{row['channel_id']}", row["channel_id"]))
                cached += 1
                continue
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(row["banner_url"])
                    if resp.status_code == 200 and len(resp.content) > 1000:
                        dest.write_bytes(resp.content)
                        await db.execute(
                            "UPDATE subscriptions SET banner_url = ? WHERE channel_id = ?",
                            (f"/api/subscriptions/banner/{row['channel_id']}", row["channel_id"]))
                        cached += 1
            except Exception:
                pass
            await asyncio.sleep(1)
        if cached:
            logger.info(f"Banner-Backfill: {cached} Banner lokal gecacht")
    except Exception as e:
        logger.warning(f"Banner-Backfill Fehler: {e}")


async def _drip_cron_loop():
    """Drip-Feed Cron: Prüft alle 15 Min ob Kanäle fällig sind.
    Lädt 2 älteste + 1 neuestes fehlendes Video pro Kanal."""
    import random
    await asyncio.sleep(120)  # 2 Min warten bis System bereit
    logger.info("[DRIP-CRON] Drip-Feed-Timer gestartet (alle 15 Min)")
    while True:
        try:
            # Fällige Kanäle suchen
            due = await db.fetch_all(
                """SELECT s.id, s.channel_id, s.channel_name, s.drip_count,
                          s.drip_auto_archive, s.download_quality, s.audio_only
                   FROM subscriptions s
                   WHERE s.drip_enabled = 1
                     AND s.drip_next_run IS NOT NULL
                     AND s.drip_next_run <= datetime('now')"""
            )
            for sub in due:
                # Auto-Archive: Kürzlich geladene Videos dieses Kanals archivieren
                if sub["drip_auto_archive"]:
                    await db.execute(
                        """UPDATE videos SET is_archived = 1
                           WHERE channel_id = ? AND status = 'ready'
                             AND is_archived = 0 AND source = 'youtube'""",
                        (sub["channel_id"],)
                    )

                drip_count = sub["drip_count"] or 3
                # 2 älteste + 1 neuestes (bei count >= 3)
                old_count = max(1, drip_count - 1)
                new_count = 1

                # Älteste fehlende
                oldest = await db.fetch_all(
                    """SELECT r.video_id, r.title FROM rss_entries r
                       WHERE r.channel_id = ?
                         AND r.video_id NOT IN (SELECT id FROM videos WHERE status = 'ready')
                       ORDER BY r.published ASC LIMIT ?""",
                    (sub["channel_id"], old_count)
                )
                # Neuestes fehlendes (nicht in oldest)
                old_ids = [o["video_id"] for o in oldest]
                exclude_clause = ""
                params = [sub["channel_id"]]
                if old_ids:
                    placeholders = ",".join("?" * len(old_ids))
                    exclude_clause = f"AND r.video_id NOT IN ({placeholders})"
                    params.extend(old_ids)
                params.append(new_count)
                newest = await db.fetch_all(
                    f"""SELECT r.video_id, r.title FROM rss_entries r
                        WHERE r.channel_id = ?
                          AND r.video_id NOT IN (SELECT id FROM videos WHERE status = 'ready')
                          {exclude_clause}
                        ORDER BY r.published DESC LIMIT ?""",
                    tuple(params)
                )

                to_download = oldest + newest
                if not to_download:
                    # Kanal komplett → deaktivieren
                    await db.execute(
                        """UPDATE subscriptions SET drip_enabled = 0,
                           drip_completed_at = datetime('now'), drip_next_run = NULL
                           WHERE id = ?""", (sub["id"],)
                    )
                    logger.info(f"[DRIP] {sub['channel_name']}: komplett! Drip deaktiviert.")
                    continue

                # In Download-Queue stellen
                queued = 0
                for vid in to_download:
                    try:
                        url = f"https://www.youtube.com/watch?v={vid['video_id']}"
                        await download_service.add_to_queue(
                            url=url,
                            quality=sub["download_quality"] or "720p",
                            audio_only=bool(sub["audio_only"]),
                        )
                        queued += 1
                    except Exception as e:
                        logger.warning(f"[DRIP] Queue-Fehler {vid['video_id']}: {e}")

                # Nächsten Run würfeln (morgen 02:00-10:00)
                from datetime import datetime, timedelta
                tomorrow = datetime.now().replace(hour=0, minute=0, second=0) + timedelta(days=1)
                next_run = tomorrow.replace(
                    hour=random.randint(2, 9), minute=random.randint(0, 59)
                )
                await db.execute(
                    "UPDATE subscriptions SET drip_next_run = ? WHERE id = ?",
                    (next_run.strftime("%Y-%m-%d %H:%M:%S"), sub["id"])
                )
                logger.info(f"[DRIP] {sub['channel_name']}: {queued} Videos gequeued, nächster Run: {next_run}")

        except Exception as e:
            logger.error(f"[DRIP-CRON] Fehler: {e}", exc_info=True)
        await asyncio.sleep(900)  # 15 Minuten


async def _rss_cron_loop():
    """Interner RSS-Cron: Ruft alle 5 Min rss_service.tick() auf.
    Ersetzt externen System-Cron komplett."""
    await asyncio.sleep(60)  # 1 Min warten bis System bereit
    logger.info("[RSS-CRON] Interner RSS-Timer gestartet (alle 5 Min)")
    while True:
        try:
            result = await rss_service.tick(max_feeds=20)
            new = result.get("new_videos", 0)
            status = result.get("status", "?")
            if new > 0:
                from app.routers.jobs import activity_ws
                await activity_ws.broadcast({
                    "type": "feed_updated",
                    "new_videos": new,
                })
                logger.info(f"[RSS-CRON] {new} neue Videos gefunden")
            elif status not in ("idle", "disabled"):
                logger.debug(f"[RSS-CRON] Tick: {status}")
        except Exception as e:
            logger.error(f"[RSS-CRON] Fehler: {e}")
        await asyncio.sleep(300)  # 5 Minuten


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application Lifecycle: Startup und Shutdown."""
    # --- STARTUP ---
    logger.info(f"[START] {APP_NAME} v{VERSION} startet...")
    ensure_directories()
    await db.connect()
    await scan_db.connect()
    # Ghost-Einträge automatisch bereinigen (Videos ohne Datei)
    try:
        from pathlib import Path as _P
        ghost_rows = await db.fetch_all(
            "SELECT id, file_path FROM videos WHERE status = 'ready'")
        ghost_count = 0
        for gr in ghost_rows:
            if not gr["file_path"] or not _P(gr["file_path"]).exists():
                await db.execute("UPDATE videos SET status = 'ghost' WHERE id = ?", (gr["id"],))
                ghost_count += 1
        if ghost_count:
            logger.info(f"[STARTUP] {ghost_count} Ghost-Einträge bereinigt (keine Datei)")
    except Exception as e:
        logger.warning(f"[STARTUP] Ghost-Check Fehler: {e}")
    job_service.set_loop(asyncio.get_event_loop())
    await job_service.startup()
    await download_service.start_worker()
    # Download-Progress auch über Activity-WS senden (unified WS)
    from app.routers.jobs import activity_ws
    download_service.add_progress_callback(activity_ws.broadcast)
    await rss_service.start_worker()
    await rss_service.resume_avatar_jobs()
    # ─── Hintergrund-Tasks über TaskManager registrieren ─────────
    task_manager.register("rss_cron", "RSS-Feed Cron (5 Min)",
                          _rss_cron_loop, auto_restart=True, essential=True)
    task_manager.register("drip_cron", "Drip-Feed Cron (15 Min)",
                          _drip_cron_loop, auto_restart=True, essential=True)
    task_manager.register("thumbnail_backfill", "Thumbnail-Backfill",
                          rss_service.backfill_missing_thumbnails, auto_restart=False, essential=False)
    task_manager.register("banner_backfill", "Banner-Backfill",
                          _backfill_banners, auto_restart=False, essential=False)
    await task_manager.start_all()
    logger.info(f"[OK] {APP_NAME} v{VERSION} bereit")
    logger.info(f"   API: http://{HOST}:{PORT}")
    logger.info(f"   Docs: http://{HOST}:{PORT}/docs")
    logger.info(f"   Daten: {DATA_DIR}")

    yield

    # --- SHUTDOWN ---
    logger.info(f"[STOP] {APP_NAME} wird heruntergefahren...")
    await task_manager.stop_all()
    await rss_service.stop_worker()
    await download_service.stop_worker()
    await job_service.shutdown()
    await db.disconnect()
    await scan_db.disconnect()
    logger.info(f"[BYE] {APP_NAME} gestoppt")


# --- App erstellen ---
app = FastAPI(
    title=APP_NAME,
    description="Selbstgehostetes Video-Vault & Streaming-System – YouTube + eigene Videos",
    version=VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Range", "Accept-Ranges", "Content-Length"],
)


# --- API Access Logging Middleware ---
import time as _time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest

# Pfade die nicht geloggt werden sollen (High-Frequency / WS / Static)
_LOG_SKIP = {"/api/system/health", "/api/system/badges", "/api/system/ws/logs",
             "/api/system/ws/progress", "/api/downloads/ws/progress",
             "/api/system/tasks", "/api/jobs/active", "/api/jobs/stats",
             "/api/jobs/ws"}
_LOG_SKIP_PREFIXES = ("/thumbnails/", "/avatars/", "/subtitles/", "/api/player/")


class APIAccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        path = request.url.path
        # Skip noise
        if path in _LOG_SKIP or any(path.startswith(p) for p in _LOG_SKIP_PREFIXES):
            return await call_next(request)
        start = _time.time()
        response = await call_next(request)
        duration_ms = (_time.time() - start) * 1000
        # Nur /api/ Pfade loggen
        if path.startswith("/api/"):
            from app.routers.system import log_buffer
            log_buffer.push_api(
                method=request.method,
                path=path,
                status=response.status_code,
                duration_ms=duration_ms,
                client=request.client.host if request.client else "",
            )
            # Slow-Request Warning (>2s)
            if duration_ms > 2000:
                log_buffer.push_event(
                    cat="api", level="WARNING", name="slow-req",
                    msg=f"SLOW {request.method} {path} → {duration_ms:.0f}ms",
                    rate_key=f"slow:{path}", rate_seconds=10,
                )
            # Timeout/Error Warnung (5xx)
            if response.status_code >= 500:
                log_buffer.push_event(
                    cat="api", level="ERROR", name="api-error",
                    msg=f"{response.status_code} {request.method} {path} ({duration_ms:.0f}ms)",
                )
        return response


app.add_middleware(APIAccessLogMiddleware)

# --- Static Files ---
THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)
SUBTITLES_DIR.mkdir(parents=True, exist_ok=True)
AVATARS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/thumbnails", StaticFiles(directory=str(THUMBNAILS_DIR)), name="thumbnails")
app.mount("/subtitles", StaticFiles(directory=str(SUBTITLES_DIR)), name="subtitles")
app.mount("/avatars", StaticFiles(directory=str(AVATARS_DIR)), name="avatars")

# --- Router registrieren ---
# Core
app.include_router(videos.router)
app.include_router(downloads.router)
app.include_router(player.router)
# Organisation
app.include_router(favorites.router)
app.include_router(categories.router)
app.include_router(playlists.router)
app.include_router(chapters.router)
app.include_router(ad_markers.router)
# YouTube
app.include_router(search.router)
app.include_router(subscriptions.router)
app.include_router(feed_router.router)
app.include_router(channel_playlists.router)
app.include_router(imports.router)
app.include_router(own_videos.router)
app.include_router(scan.router)
app.include_router(backup.router)
# System
app.include_router(settings.router)
app.include_router(system.router)
app.include_router(api_endpoints.router)
app.include_router(jobs.router)
app.include_router(exports.router)
app.include_router(streams.router)
app.include_router(lyrics.router)


# --- Root Endpoint ---
@app.get("/")
async def root():
    return {
        "app": APP_NAME,
        "version": VERSION,
        "status": "running",
        "docs": "/docs",
        "api": "/api",
    }


@app.get("/api")
async def api_overview():
    """API-Übersicht aller verfügbaren Endpunkte."""
    return {
        "app": APP_NAME,
        "version": VERSION,
        "endpoints": {
            "videos": {
                "list": "GET /api/videos",
                "info": "GET /api/videos/info?url=...",
                "detail": "GET /api/videos/{id}",
                "update": "PUT /api/videos/{id}",
                "delete": "DELETE /api/videos/{id}",
                "stats": "GET /api/videos/stats",
                "tags": "GET /api/videos/tags",
                "history": "GET /api/videos/history",
                "position": "GET/POST /api/videos/{id}/position",
            },
            "downloads": {
                "add": "POST /api/downloads",
                "batch": "POST /api/downloads/batch",
                "queue": "GET /api/downloads",
                "cancel": "DELETE /api/downloads/{id}",
                "retry": "POST /api/downloads/{id}/retry",
                "websocket": "WS /api/downloads/ws/progress",
            },
            "player": {
                "stream": "GET /api/player/{video_id}",
                "stream_specific": "GET /api/player/{video_id}/stream/{stream_id}",
                "thumbnail": "GET /api/player/{video_id}/thumbnail",
                "subtitles": "GET /api/player/{video_id}/subtitles",
                "subtitle_download": "POST /api/player/{video_id}/subtitles/download",
                "audio_extract": "POST /api/player/{video_id}/audio/extract",
                "audio_get": "GET /api/player/{video_id}/audio",
            },
            "search": {
                "youtube": "GET /api/search/youtube?q=...",
                "youtube_playlists": "GET /api/search/youtube/playlists?q=...",
                "local": "GET /api/search/local?q=...",
            },
            "import": {
                "youtube_playlist": "POST /api/import/youtube-playlist",
                "download_selected": "POST /api/import/youtube-playlist/download-selected",
                "channel_videos": "GET /api/import/channel-videos/{channel_id}",
                "url_list": "POST /api/import/url-list",
                "local_video": "POST /api/import/local-video",
                "scan_directory": "POST /api/import/scan-directory",
            },
            "playlists": {
                "list": "GET /api/playlists",
                "create": "POST /api/playlists",
                "detail": "GET /api/playlists/{id}",
                "update": "PUT /api/playlists/{id}",
                "delete": "DELETE /api/playlists/{id}",
                "add_video": "POST /api/playlists/{id}/videos",
                "remove_video": "DELETE /api/playlists/{id}/videos/{video_id}",
                "reorder": "PUT /api/playlists/{id}/reorder",
            },
            "chapters": {
                "get": "GET /api/chapters/{video_id}",
                "add": "POST /api/chapters/{video_id}",
                "update": "PUT /api/chapters/{id}",
                "delete": "DELETE /api/chapters/{id}",
                "fetch_yt": "POST /api/chapters/{video_id}/fetch",
            },
            "favorites": {
                "list": "GET /api/favorites",
                "lists": "GET /api/favorites/lists",
                "add": "POST /api/favorites",
                "remove": "DELETE /api/favorites/{id}",
                "check": "GET /api/favorites/check/{video_id}",
            },
            "categories": {
                "tree": "GET /api/categories",
                "flat": "GET /api/categories/flat",
                "create": "POST /api/categories",
                "update": "PUT /api/categories/{id}",
                "delete": "DELETE /api/categories/{id}",
                "videos": "GET /api/categories/{id}/videos",
            },
            "subscriptions": {
                "list": "GET /api/subscriptions",
                "add": "POST /api/subscriptions",
                "feed": "GET /api/subscriptions/feed",
                "channel": "GET /api/subscriptions/channel/{id}",
            },
            "exports": {
                "list": "GET /api/exports",
                "backup": "POST /api/exports/backup",
                "download_backup": "GET /api/exports/backup/download",
                "videos_json": "GET /api/exports/videos/json",
                "videos_csv": "GET /api/exports/videos/csv",
                "subscriptions_csv": "GET /api/exports/subscriptions/csv",
                "playlists_json": "GET /api/exports/playlists/json",
            },
            "settings": {
                "all": "GET /api/settings",
                "get": "GET /api/settings/{key}",
                "update": "PUT /api/settings/{key}",
                "reset": "POST /api/settings/reset",
            },
            "system": {
                "health": "GET /api/system/health",
                "version": "GET /api/system/version",
                "stats": "GET /api/system/stats",
                "storage": "GET /api/system/storage",
                "cleanup": "POST /api/system/cleanup-temp",
            },
        },
    }

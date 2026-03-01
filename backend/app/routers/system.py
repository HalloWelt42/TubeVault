"""
TubeVault -  System Router v1.5.54
System-Status, Rate-Limiter Stats, Health, Live-Logs
© HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
"""

import logging
from collections import deque
from datetime import datetime

logger = logging.getLogger(__name__)

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.config import VERSION, APP_NAME, DATA_DIR, DB_PATH, DB_DIR, VIDEOS_DIR, THUMBNAILS_DIR
from app.database import db
from app.utils.file_utils import get_disk_usage, get_directory_size, human_size
from app.services.metadata_service import metadata_service
from app.services.rate_limiter import rate_limiter
from app.services.job_service import job_service

router = APIRouter(prefix="/api/system", tags=["System"])


# ─── Live-Log Ring-Buffer + WebSocket ─────────────────────

LOG_BUFFER_SIZE = 3000

# Logger-Name → Kategorie Mapping
_LOGGER_CAT_MAP = {
    "download_service": "download",
    "rss_service": "rss",
    "job_service": "queue",
    "rate_limiter": "rate",
    "channel_scanner": "scan",
    "import_service": "import",
    "metadata_service": "meta",
    "scan_service": "scan",
    "lyrics_service": "lyrics",
    "lyrics": "lyrics",
    "stream_service": "stream",
    "playlist_service": "playlist",
    "backup": "system",
    "system": "system",
    "archive_service": "system",
    "ryd_service": "meta",
    "jobs": "queue",
}


class LogBuffer(logging.Handler):
    """Ring-Buffer + gebatchter WebSocket-Stream.
    _push() ist synchron und schnell (nur deque.append).
    WS-Broadcast alle 250ms gebatcht -  blockiert nie den Haupt-Thread."""

    def __init__(self, maxlen: int = LOG_BUFFER_SIZE):
        super().__init__()
        self.buffer: deque[dict] = deque(maxlen=maxlen)
        self.connections: list[WebSocket] = []
        self._loop = None
        self._pending: deque[dict] = deque(maxlen=500)  # WS-Sende-Puffer
        self._flush_task = None
        self._rate_cache: dict[str, float] = {}

    def emit(self, record: logging.LogRecord):
        short_name = record.name.split(".")[-1]
        cat = _LOGGER_CAT_MAP.get(short_name, "backend")
        entry = {
            "ts": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
            "level": record.levelname,
            "name": short_name,
            "msg": self.format(record),
            "cat": cat,
        }
        self._push(entry)

    def push_api(self, method: str, path: str, status: int, duration_ms: float,
                 client: str = ""):
        level = "INFO" if status < 400 else ("WARNING" if status < 500 else "ERROR")
        entry = {
            "ts": datetime.now().strftime("%H:%M:%S"),
            "level": level,
            "name": "api",
            "msg": f"{method} {path} → {status} ({duration_ms:.0f}ms)",
            "cat": "api",
            "method": method,
            "path": path,
            "status": status,
            "duration_ms": round(duration_ms, 1),
        }
        self._push(entry)

    def push_frontend(self, entries: list[dict]):
        for e in entries:
            entry = {
                "ts": e.get("ts", datetime.now().strftime("%H:%M:%S")),
                "level": e.get("level", "INFO").upper(),
                "name": e.get("source", "ui"),
                "msg": e.get("msg", ""),
                "cat": "frontend",
            }
            self._push(entry)

    def push_event(self, cat: str, level: str, name: str, msg: str,
                   rate_key: str = None, rate_seconds: float = 0):
        if rate_key and rate_seconds > 0:
            import time
            now = time.time()
            last = self._rate_cache.get(rate_key, 0)
            if now - last < rate_seconds:
                return
            self._rate_cache[rate_key] = now
            if len(self._rate_cache) > 500:
                cutoff = now - 60
                self._rate_cache = {k: v for k, v in self._rate_cache.items() if v > cutoff}
        entry = {
            "ts": datetime.now().strftime("%H:%M:%S"),
            "level": level,
            "name": name,
            "msg": msg,
            "cat": cat,
        }
        self._push(entry)

    def _push(self, entry: dict):
        """Schnell & synchron -  nur deque-Append, kein I/O."""
        self.buffer.append(entry)
        if self.connections:
            self._pending.append(entry)

    async def _flush_loop(self):
        """Alle 250ms ausstehende Einträge gebatcht per WS senden."""
        import asyncio
        while True:
            await asyncio.sleep(0.25)
            if not self._pending or not self.connections:
                continue
            # Batch rausholen
            batch = []
            while self._pending and len(batch) < 100:
                batch.append(self._pending.popleft())
            if not batch:
                continue
            dead = []
            for ws in self.connections:
                try:
                    for entry in batch:
                        await ws.send_json(entry)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                if ws in self.connections:
                    self.connections.remove(ws)

    def get_history(self, n: int = 200, cat: str = None) -> list[dict]:
        items = list(self.buffer)
        if cat:
            items = [e for e in items if e.get("cat") == cat]
        return items[-n:]

    def set_loop(self, loop):
        self._loop = loop
        # Flush-Loop starten
        if self._flush_task is None or self._flush_task.done():
            import asyncio
            self._flush_task = asyncio.ensure_future(self._flush_loop())


log_buffer = LogBuffer()
log_buffer.setFormatter(logging.Formatter("%(message)s"))
log_buffer.setLevel(logging.DEBUG)
_root = logging.getLogger()
_root.addHandler(log_buffer)
# Stdout-Handler für docker logs
_stdout = logging.StreamHandler()
_stdout.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S"))
_stdout.setLevel(logging.INFO)
_root.addHandler(_stdout)
# Root-Logger Level explizit setzen -  basicConfig() in main.py greift nicht,
# weil dieser Handler bereits existiert bevor basicConfig aufgerufen wird.
_root.setLevel(logging.INFO)
# Noisy Third-Party Logger auf WARNING setzen
for _noisy in ("uvicorn", "uvicorn.access", "uvicorn.error",
               "httpx", "httpcore", "asyncio", "aiosqlite",
               "watchfiles", "websockets", "multipart"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)


@router.get("/logs")
async def get_logs(n: int = Query(500, ge=1, le=5000), cat: str = Query(None)):
    """Letzte N Log-Einträge aus dem Ring-Buffer. Optional nach Kategorie filtern."""
    return {"logs": log_buffer.get_history(n, cat)}


@router.get("/logs/docker")
async def get_docker_logs(service: str = Query("backend"), n: int = Query(200, ge=1, le=2000)):
    """Echte Docker-Container-Logs lesen (stdout/stderr vom aktuellen Prozess)."""
    import subprocess
    logs = []
    try:
        # Im Container: /proc/1/fd/1 = stdout, /proc/1/fd/2 = stderr
        # Alternativ: einfach aus dem Python-Logging-Buffer
        if service == "backend":
            # Backend-Logs aus Ring-Buffer (enthält alle Python-Logs)
            items = log_buffer.get_history(n, "backend")
            logs = items
        elif service == "api":
            items = log_buffer.get_history(n, "api")
            logs = items
        elif service == "frontend":
            items = log_buffer.get_history(n, "frontend")
            logs = items
        else:
            # Alle Logs
            logs = log_buffer.get_history(n)
    except Exception as e:
        return {"logs": [], "error": str(e)}
    return {"logs": logs, "total": len(logs)}


@router.get("/logs/stats")
async def get_log_stats():
    """Log-Statistiken: echte Zähler pro Kategorie und Level."""
    all_logs = list(log_buffer.buffer)
    stats = {
        "total": len(all_logs),
        "by_category": {},
        "by_level": {},
        "errors_last_hour": 0,
    }
    from datetime import datetime, timedelta
    hour_ago = (datetime.now() - timedelta(hours=1)).strftime("%H:%M:%S")

    for entry in all_logs:
        cat = entry.get("cat", "unknown")
        level = entry.get("level", "INFO")
        stats["by_category"][cat] = stats["by_category"].get(cat, 0) + 1
        stats["by_level"][level] = stats["by_level"].get(level, 0) + 1
        if level in ("ERROR", "CRITICAL") and entry.get("ts", "") >= hour_ago:
            stats["errors_last_hour"] += 1

    return stats


@router.post("/logs/frontend")
async def push_frontend_logs(entries: list[dict]):
    """Frontend-Console-Logs empfangen und in den Buffer einfügen."""
    log_buffer.push_frontend(entries[:50])  # Max 50 pro Batch
    return {"received": len(entries)}


@router.websocket("/ws/logs")
async def logs_websocket(websocket: WebSocket):
    """WebSocket: Live-Log-Stream."""
    import asyncio
    await websocket.accept()
    log_buffer.set_loop(asyncio.get_event_loop())
    log_buffer.connections.append(websocket)
    try:
        # History senden
        for entry in log_buffer.get_history(100):
            await websocket.send_json(entry)
        # Keepalive
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in log_buffer.connections:
            log_buffer.connections.remove(websocket)


@router.get("/health")
async def health_check():
    return {"status": "ok", "app": APP_NAME, "version": VERSION}


@router.get("/badges")
async def get_badges():
    """Leichtgewichtige Zähler für Sidebar-Badges."""
    videos = await db.fetch_val("SELECT COUNT(*) FROM videos WHERE status = 'ready' AND COALESCE(is_archived, 0) = 0") or 0
    subs = await db.fetch_val("SELECT COUNT(*) FROM subscriptions WHERE enabled = 1") or 0
    new_feed = await db.fetch_val("SELECT COUNT(*) FROM rss_entries WHERE status = 'new' AND COALESCE(feed_status, 'active') = 'active'") or 0
    active_dl = await db.fetch_val("SELECT COUNT(*) FROM jobs WHERE type='download' AND status IN ('queued','active')") or 0
    favorites = await db.fetch_val("SELECT COUNT(*) FROM favorites") or 0
    playlists = await db.fetch_val("SELECT COUNT(*) FROM playlists WHERE COALESCE(visibility, 'global') = 'global'") or 0
    categories = await db.fetch_val("SELECT COUNT(*) FROM categories") or 0
    history = await db.fetch_val("SELECT COUNT(*) FROM videos WHERE play_count > 0") or 0
    archives = await db.fetch_val("SELECT COUNT(*) FROM videos WHERE status = 'ready' AND COALESCE(is_archived, 0) = 1") or 0
    own_videos = await db.fetch_val("SELECT COUNT(*) FROM videos WHERE source IN ('local', 'imported') AND status = 'ready' AND file_path IS NOT NULL") or 0
    # Batch-Queue: Sicher abfragen (Tabelle existiert evtl. noch nicht)
    try:
        batch_waiting = await db.fetch_val("SELECT COUNT(*) FROM batch_queue WHERE status IN ('waiting','downloading')") or 0
    except Exception:
        batch_waiting = 0
    return {
        "videos": videos, "subscriptions": subs, "new_feed": new_feed,
        "active_downloads": active_dl, "favorites": favorites,
        "playlists": playlists, "categories": categories,
        "history": history, "archives": archives,
        "own_videos": own_videos, "batch_queue": batch_waiting,
    }


@router.get("/version")
async def get_version():
    return {"app": APP_NAME, "version": VERSION, "api_version": "v1"}


@router.get("/mountpoints")
async def get_mountpoints():
    """Docker-Mountpoints und reale Festplatten-Pfade ermitteln."""
    import subprocess
    from app.config import DATA_DIR, DB_DIR, VIDEOS_DIR, EXPORTS_DIR

    mounts = [
        {"container_path": str(DATA_DIR), "label": "Daten (Videos, DB, Thumbnails)", "type": "data"},
        {"container_path": str(VIDEOS_DIR), "label": "Video-Dateien", "type": "videos"},
        {"container_path": str(DB_DIR), "label": "Datenbank", "type": "db"},
        {"container_path": str(EXPORTS_DIR), "label": "Backups & Exporte", "type": "exports"},
    ]

    # Reale Mount-Quelle ermitteln via /proc/mounts
    try:
        with open("/proc/mounts", "r") as f:
            proc_mounts = f.readlines()
        for m in mounts:
            cp = m["container_path"]
            best_match = ""
            best_device = ""
            for line in proc_mounts:
                parts = line.strip().split()
                if len(parts) >= 2:
                    device, mount_point = parts[0], parts[1]
                    if cp.startswith(mount_point) and len(mount_point) > len(best_match):
                        best_match = mount_point
                        best_device = device
            m["host_mount"] = best_match
            m["device"] = best_device

            # Disk Usage
            usage = get_disk_usage(cp)
            m["total"] = usage.get("total", 0)
            m["used"] = usage.get("used", 0)
            m["free"] = usage.get("free", 0)
            m["percent"] = usage.get("percent", 0)
            m["total_human"] = human_size(m["total"])
            m["free_human"] = human_size(m["free"])
    except Exception as e:
        for m in mounts:
            m["error"] = str(e)

    return {"mounts": mounts, "version": VERSION}


@router.get("/stats")
async def get_system_stats():
    """Umfassende System-Statistiken für Dashboard."""
    video_stats = await metadata_service.get_stats()
    # Zwei Platten: Medien (Videos) + Metadaten (DB)
    disk_media = get_disk_usage(str(VIDEOS_DIR))
    disk_meta = get_disk_usage(str(DB_DIR))
    # Prüfen ob verschiedene Platten (verschiedene total-Größe)
    is_split = abs(disk_media.get("total", 0) - disk_meta.get("total", 0)) > 1_000_000_000
    db_size = DB_PATH.stat().st_size if DB_PATH.exists() else 0

    active_dl = await db.fetch_val("SELECT COUNT(*) FROM jobs WHERE type='download' AND status = 'active'") or 0
    pending_dl = await db.fetch_val("SELECT COUNT(*) FROM jobs WHERE type='download' AND status = 'queued'") or 0
    active_jobs = await db.fetch_val("SELECT COUNT(*) FROM jobs WHERE status = 'active'") or 0
    total_subs = await db.fetch_val("SELECT COUNT(*) FROM subscriptions") or 0
    error_subs = await db.fetch_val("SELECT COUNT(*) FROM subscriptions WHERE error_count > 0") or 0

    result = {
        "version": VERSION,
        **video_stats,
        "total_size_human": human_size(video_stats.get("total_size_bytes", 0)),
        "disk": disk_media,
        "db_size_bytes": db_size,
        "db_size_human": human_size(db_size),
        "download_queue_active": active_dl,
        "download_queue_pending": pending_dl,
        "active_jobs": active_jobs,
        "total_subscriptions": total_subs,
        "error_subscriptions": error_subs,
    }
    # Split-Info: beide Platten separat
    if is_split:
        result["disk_media"] = disk_media
        result["disk_media"]["label"] = "Medien"
        result["disk_meta"] = disk_meta
        result["disk_meta"]["label"] = "System"
        result["storage_split"] = True
    else:
        result["storage_split"] = False

    return result


@router.get("/status")
async def get_full_status():
    """Gesamtstatus aller Services -  für Frontend-Header/Footer.

    Zeigt: Rate-Limiter, RSS-Worker, Download-Queue, Service-Health, Jobs.
    Frontend pollt z.B. alle 10s für Live-Status-Anzeige mit LEDs.
    """
    from app.services.rss_service import rss_service
    from app.services.download_service import download_service

    # Rate Limiter
    rl_stats = rate_limiter.get_stats()
    any_backoff = any(s.get("in_backoff") for s in rl_stats.values())
    yt_ok = rate_limiter.is_youtube_healthy()

    # Cooldown
    cooldown_state = download_service.get_cooldown_state()

    # RSS
    rss_stats = await rss_service.get_stats()

    # Downloads
    active_dl = await db.fetch_val("SELECT COUNT(*) FROM jobs WHERE type='download' AND status = 'active'") or 0
    pending_dl = await db.fetch_val("SELECT COUNT(*) FROM jobs WHERE type='download' AND status = 'queued'") or 0
    error_dl = await db.fetch_val("SELECT COUNT(*) FROM jobs WHERE type='download' AND status = 'error'") or 0

    # Jobs
    active_jobs = await db.fetch_val("SELECT COUNT(*) FROM jobs WHERE status = 'active'") or 0
    queued_jobs = await db.fetch_val("SELECT COUNT(*) FROM jobs WHERE status = 'queued'") or 0

    # Service-Health aus api_endpoints (sparsam: nur last_status lesen, kein neuer Test)
    ryd_status = await db.fetch_one(
        "SELECT last_status, last_tested FROM api_endpoints WHERE name = 'ryd_api'"
    )

    # DB Schema-Version
    db_version = await db.fetch_val("SELECT MAX(version) FROM schema_version") or "?"

    return {
        "version": VERSION,
        "db_version": db_version,
        "rate_limiter": rl_stats,
        "rate_limiter_warning": any_backoff,
        "rate_limiter_disabled": rate_limiter.disabled,
        "services": {
            "backend": {"ok": True},
            "youtube": {"ok": yt_ok, "backoff": not yt_ok,
                        "block_count": rate_limiter._yt_block_count,
                        "block_active": not yt_ok},
            "rss": {"ok": rss_service._running, "running": rss_service._running},
            "ryd": {
                "ok": ryd_status["last_status"] == "ok" if ryd_status and ryd_status["last_status"] else False,
                "last_check": ryd_status["last_tested"] if ryd_status else None,
            },
        },
        "rss": {
            **rss_stats,
            "worker_running": rss_service._running,
        },
        "downloads": {
            "active": active_dl,
            "pending": pending_dl,
            "errors": error_dl,
        },
        "jobs": {
            "active": active_jobs,
            "queued": queued_jobs,
        },
        "cooldown": cooldown_state,
    }


@router.post("/rate-limit/reset")
async def reset_rate_limit(category: str = None):
    """Rate-Limit Backoff manuell zurücksetzen. Ohne Kategorie: alles reset."""
    rate_limiter.reset(category)
    # Queue-Pause aufheben wenn sie wegen Rate-Limit aktiv war
    if job_service._paused and job_service._pause_reason == "rate_limit":
        await job_service.resume_queue()
    return {"ok": True, "reset": category or "all", "stats": rate_limiter.get_stats()}


@router.post("/rate-limit/toggle")
async def toggle_rate_limit():
    """Rate-Limiter ein-/ausschalten. Wenn disabled: kein Delay zwischen Anfragen."""
    rate_limiter.disabled = not rate_limiter.disabled
    state = "deaktiviert" if rate_limiter.disabled else "aktiviert"
    logger.info(f"Rate-Limiter {state} (manuell)")
    return {"ok": True, "disabled": rate_limiter.disabled, "message": f"Rate-Limiter {state}"}


@router.get("/storage")
async def get_storage_details():
    """Detaillierte Speicher-Übersicht mit Split-Storage."""
    from app.config import VIDEOS_DIR, AUDIO_DIR, THUMBNAILS_DIR, TEMP_DIR, SUBTITLES_DIR, AVATARS_DIR

    disk_media = get_disk_usage(str(VIDEOS_DIR))
    disk_meta = get_disk_usage(str(DB_DIR))
    is_split = abs(disk_media.get("total", 0) - disk_meta.get("total", 0)) > 1_000_000_000

    result = {
        "disk": disk_media,
        "storage_split": is_split,
        "directories": {
            "videos": {
                "path": str(VIDEOS_DIR),
                "size": get_directory_size(VIDEOS_DIR),
                "size_human": human_size(get_directory_size(VIDEOS_DIR)),
                "disk": "media",
            },
            "audio": {
                "path": str(AUDIO_DIR),
                "size": get_directory_size(AUDIO_DIR),
                "size_human": human_size(get_directory_size(AUDIO_DIR)),
                "disk": "media",
            },
            "subtitles": {
                "path": str(SUBTITLES_DIR),
                "size": get_directory_size(SUBTITLES_DIR),
                "size_human": human_size(get_directory_size(SUBTITLES_DIR)),
                "disk": "media",
            },
            "thumbnails": {
                "path": str(THUMBNAILS_DIR),
                "size": get_directory_size(THUMBNAILS_DIR),
                "size_human": human_size(get_directory_size(THUMBNAILS_DIR)),
                "disk": "meta",
            },
            "avatars": {
                "path": str(AVATARS_DIR),
                "size": get_directory_size(AVATARS_DIR),
                "size_human": human_size(get_directory_size(AVATARS_DIR)),
                "disk": "meta",
            },
            "temp": {
                "path": str(TEMP_DIR),
                "size": get_directory_size(TEMP_DIR),
                "size_human": human_size(get_directory_size(TEMP_DIR)),
                "disk": "meta",
            },
        },
    }
    if is_split:
        result["disk_media"] = {**disk_media, "label": "Medien (USB)"}
        result["disk_meta"] = {**disk_meta, "label": "System (NVMe)"}
    return result


@router.post("/cleanup-temp")
async def cleanup_temp():
    """Temporäre Dateien löschen."""
    import shutil
    from app.config import TEMP_DIR

    size_before = get_directory_size(TEMP_DIR)
    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR)
        TEMP_DIR.mkdir(parents=True)

    return {
        "cleaned": True,
        "freed_bytes": size_before,
        "freed_human": human_size(size_before),
    }


@router.post("/cleanup-ghosts")
async def cleanup_ghost_entries():
    """Ghost-Einträge finden und bereinigen: Videos mit status='ready' aber ohne Datei."""
    from pathlib import Path

    rows = await db.fetch_all(
        "SELECT id, title, file_path, status FROM videos WHERE status = 'ready'"
    )
    ghosts = []
    for row in rows:
        fp = row["file_path"]
        if not fp or not Path(fp).exists():
            ghosts.append({"id": row["id"], "title": row["title"], "file_path": fp})

    if not ghosts:
        return {"ghosts_found": 0, "cleaned": 0, "entries": []}

    # Ghost-Einträge auf status='ghost' setzen (nicht löschen, recoverable)
    for g in ghosts:
        await db.execute(
            "UPDATE videos SET status = 'ghost' WHERE id = ?", (g["id"],))

    return {
        "ghosts_found": len(ghosts),
        "cleaned": len(ghosts),
        "entries": ghosts,
    }


@router.post("/cleanup-full")
async def full_cleanup():
    """Umfassende Datenbankbereinigung mit detailliertem Protokoll."""
    from pathlib import Path
    from app.config import TEMP_DIR, THUMBNAILS_DIR, VIDEOS_DIR, AUDIO_DIR

    protocol = []
    totals = {"cleaned": 0, "freed_bytes": 0, "errors": 0}

    def log(action, detail, count=0, freed=0):
        protocol.append({"action": action, "detail": detail, "count": count, "freed": freed})
        totals["cleaned"] += count
        totals["freed_bytes"] += freed

    def log_error(action, error):
        protocol.append({"action": action, "detail": f"Fehler: {error}", "count": 0, "freed": 0})
        totals["errors"] += 1

    # 1. Ghost-Videos (status='ready' ohne Datei)
    try:
        ready = await db.fetch_all("SELECT id, title, file_path FROM videos WHERE status = 'ready'")
        ghosts = [r for r in ready if not r["file_path"] or not Path(r["file_path"]).exists()]
        for g in ghosts:
            await db.execute("UPDATE videos SET status = 'ghost' WHERE id = ?", (g["id"],))
        log("ghost_videos", f"{len(ghosts)} Videos ohne Datei → status='ghost'", len(ghosts))
    except Exception as e:
        log_error("ghost_videos", e)

    # 2. Verwaiste video_categories (Video existiert nicht oder nicht ready)
    try:
        orphan_cats = await db.fetch_val(
            """SELECT COUNT(*) FROM video_categories
               WHERE video_id NOT IN (SELECT id FROM videos WHERE status = 'ready')"""
        )
        if orphan_cats:
            await db.execute(
                """DELETE FROM video_categories
                   WHERE video_id NOT IN (SELECT id FROM videos WHERE status = 'ready')"""
            )
        log("orphan_categories", f"{orphan_cats} verwaiste Kategorie-Zuordnungen entfernt", orphan_cats)
    except Exception as e:
        log_error("orphan_categories", e)

    # 3. Verwaiste playlist_videos
    try:
        orphan_pl = await db.fetch_val(
            """SELECT COUNT(*) FROM playlist_videos
               WHERE video_id NOT IN (SELECT id FROM videos WHERE status = 'ready')"""
        )
        if orphan_pl:
            await db.execute(
                """DELETE FROM playlist_videos
                   WHERE video_id NOT IN (SELECT id FROM videos WHERE status = 'ready')"""
            )
        log("orphan_playlists", f"{orphan_pl} verwaiste Playlist-Einträge entfernt", orphan_pl)
    except Exception as e:
        log_error("orphan_playlists", e)

    # 4. Verwaiste Favoriten
    try:
        orphan_fav = await db.fetch_val(
            """SELECT COUNT(*) FROM favorites
               WHERE video_id NOT IN (SELECT id FROM videos)"""
        )
        if orphan_fav:
            await db.execute(
                "DELETE FROM favorites WHERE video_id NOT IN (SELECT id FROM videos)"
            )
        log("orphan_favorites", f"{orphan_fav} verwaiste Favoriten entfernt", orphan_fav)
    except Exception as e:
        log_error("orphan_favorites", e)

    # 5. Verwaiste Watch-History
    try:
        orphan_hist = await db.fetch_val(
            """SELECT COUNT(*) FROM watch_history
               WHERE video_id NOT IN (SELECT id FROM videos)"""
        )
        if orphan_hist:
            await db.execute(
                "DELETE FROM watch_history WHERE video_id NOT IN (SELECT id FROM videos)"
            )
        log("orphan_history", f"{orphan_hist} verwaiste Verlauf-Einträge entfernt", orphan_hist)
    except Exception as e:
        log_error("orphan_history", e)

    # 6. Verwaiste Streams
    try:
        orphan_streams = await db.fetch_val(
            """SELECT COUNT(*) FROM streams
               WHERE video_id NOT IN (SELECT id FROM videos)"""
        )
        if orphan_streams:
            await db.execute(
                "DELETE FROM streams WHERE video_id NOT IN (SELECT id FROM videos)"
            )
        log("orphan_streams", f"{orphan_streams} verwaiste Stream-Einträge entfernt", orphan_streams)
    except Exception as e:
        log_error("orphan_streams", e)

    # 7. Verwaiste Kapitel
    try:
        orphan_chap = await db.fetch_val(
            """SELECT COUNT(*) FROM chapters
               WHERE video_id NOT IN (SELECT id FROM videos)"""
        )
        if orphan_chap:
            await db.execute(
                "DELETE FROM chapters WHERE video_id NOT IN (SELECT id FROM videos)"
            )
        log("orphan_chapters", f"{orphan_chap} verwaiste Kapitel entfernt", orphan_chap)
    except Exception as e:
        log_error("orphan_chapters", e)

    # 8. Abgeschlossene Download-Jobs (älter als 7 Tage)
    try:
        old_dl = await db.fetch_val(
            """SELECT COUNT(*) FROM jobs
               WHERE type='download' AND status IN ('done','error','cancelled')
               AND created_at < datetime('now', '-7 days')"""
        )
        if old_dl:
            await db.execute(
                """DELETE FROM jobs
                   WHERE type='download' AND status IN ('done','error','cancelled')
                   AND created_at < datetime('now', '-7 days')"""
            )
        log("old_downloads", f"{old_dl} alte Download-Jobs entfernt (>7 Tage)", old_dl)
    except Exception as e:
        log_error("old_downloads", e)

    # 9. Alte Jobs (>24h)
    try:
        old_jobs = await db.fetch_val(
            """SELECT COUNT(*) FROM jobs
               WHERE status IN ('completed','failed')
               AND created_at < datetime('now', '-1 day')"""
        )
        if old_jobs:
            await db.execute(
                """DELETE FROM jobs
                   WHERE status IN ('completed','failed')
                   AND created_at < datetime('now', '-1 day')"""
            )
        log("old_jobs", f"{old_jobs} alte Job-Einträge entfernt (>24h)", old_jobs)
    except Exception as e:
        log_error("old_jobs", e)

    # 10. Temp-Verzeichnis
    try:
        temp_size = get_directory_size(TEMP_DIR) if TEMP_DIR.exists() else 0
        if temp_size > 0:
            import shutil
            shutil.rmtree(TEMP_DIR)
            TEMP_DIR.mkdir(parents=True)
        log("temp_files", f"Temp-Verzeichnis geleert", 0, temp_size)
    except Exception as e:
        log_error("temp_files", e)

    # 11. Verwaiste Thumbnails (Datei existiert, aber kein Video)
    try:
        orphan_thumbs = 0
        orphan_thumb_size = 0
        if THUMBNAILS_DIR.exists():
            video_ids = set()
            rows = await db.fetch_all("SELECT id FROM videos")
            for r in rows:
                video_ids.add(r["id"])
            for f in THUMBNAILS_DIR.iterdir():
                vid = f.stem  # Dateiname ohne Extension = video_id
                if vid not in video_ids:
                    try:
                        if f.is_dir():
                            import shutil
                            fsize = get_directory_size(f)
                            shutil.rmtree(f)
                        else:
                            fsize = f.stat().st_size
                            f.unlink()
                        orphan_thumbs += 1
                        orphan_thumb_size += fsize
                    except Exception:
                        pass
        log("orphan_thumbnails", f"{orphan_thumbs} verwaiste Thumbnail-Dateien entfernt", orphan_thumbs, orphan_thumb_size)
    except Exception as e:
        log_error("orphan_thumbnails", e)

    # 12. VACUUM (Datenbank komprimieren)
    try:
        db_before = DB_DIR / "tubevault.db"
        size_before = db_before.stat().st_size if db_before.exists() else 0
        # Commit pending changes before VACUUM
        await db._connection.commit()
        await db._connection.execute("VACUUM")
        await db._connection.commit()
        size_after = db_before.stat().st_size if db_before.exists() else 0
        freed = max(0, size_before - size_after)
        log("vacuum", f"VACUUM: {human_size(size_before)} → {human_size(size_after)}", 0, freed)
    except Exception as e:
        protocol.append({"action": "vacuum", "detail": f"Fehler: {e}", "count": 0, "freed": 0})
        totals["errors"] += 1

    totals["freed_human"] = human_size(totals["freed_bytes"])
    logger.info(f"[CLEANUP] Abgeschlossen: {totals['cleaned']} Einträge, {totals['freed_human']} freigegeben")

    return {"protocol": protocol, "totals": totals}


@router.post("/cleanup-safe")
async def cleanup_safe():
    """Wrapper: cleanup-full mit globalem Error-Fang."""
    try:
        return await full_cleanup()
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"[CLEANUP] Globaler Fehler: {e}\n{tb}")
        return {
            "protocol": [{"action": "GLOBAL_ERROR", "detail": str(e), "count": 0, "freed": 0}],
            "totals": {"cleaned": 0, "freed_bytes": 0, "errors": 1, "freed_human": "0 B", "traceback": tb},
        }


# ─── Task Manager ──────────────────────────────────────
from app.services.task_manager import task_manager


@router.get("/tasks")
async def list_tasks():
    """Alle Hintergrund-Tasks mit Status."""
    return task_manager.list_tasks()


@router.post("/tasks/{name}/stop")
async def stop_task(name: str):
    """Task manuell stoppen."""
    ok = await task_manager.stop(name)
    if not ok:
        from fastapi import HTTPException
        raise HTTPException(404, f"Task '{name}' nicht gefunden")
    return {"status": "stopped", "name": name}


@router.post("/tasks/{name}/start")
async def start_task(name: str):
    """Task manuell starten."""
    ok = await task_manager.start(name)
    if not ok:
        from fastapi import HTTPException
        raise HTTPException(404, f"Task '{name}' nicht gefunden")
    return {"status": "started", "name": name}


@router.post("/tasks/{name}/restart")
async def restart_task(name: str):
    """Task stoppen und neu starten."""
    ok = await task_manager.restart(name)
    if not ok:
        from fastapi import HTTPException
        raise HTTPException(404, f"Task '{name}' nicht gefunden")
    return {"status": "restarted", "name": name}

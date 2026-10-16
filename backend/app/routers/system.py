"""
TubeVault – System Router v1.5.54
System-Status, Rate-Limiter Stats, Health, Live-Logs
© HalloWelt42 – Private Nutzung
"""

import asyncio
import itertools
import logging
import time
import uuid
from collections import deque
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Body, WebSocket, WebSocketDisconnect, Query
from app.config import VERSION, APP_NAME, DATA_DIR, DB_PATH, DB_DIR, VIDEOS_DIR, THUMBNAILS_DIR
from app.database import db
from app.utils.file_utils import get_disk_usage, get_directory_size, human_size
from app.services.metadata_service import metadata_service
from app.services.rate_limiter import rate_limiter
from app.services.job_service import job_service

router = APIRouter(prefix="/api/system", tags=["System"])


# ─── Live-Log Ring-Buffer + WebSocket ─────────────────────

LOG_BUFFER_SIZE = 10_000      # etwa 1 bis 3 Stunden; die Abfragen der Oberfläche sind der Großteil
LOG_FRAME_LIMIT = 500        # Einträge je WebSocket-Rahmen
LOG_HISTORY = 500            # so viel Verlauf bekommt ein frisch geöffnetes Terminal

# Logger-Name → Kategorie Mapping
_LOGGER_CAT_MAP = {
    "download_service": "download",
    "rss_service": "rss",
    "job_service": "queue",
    "rate_limiter": "rate",
    "channel_scanner": "scan",
    "own_scan": "import",
    "own_actions": "import",
    "metadata_service": "meta",
    "lyrics_service": "lyrics",
    "lyrics": "lyrics",
    "playlist_service": "playlist",
    "backup": "system",
    "system": "system",
    "archive_service": "system",
    "ryd_service": "meta",
    "jobs": "queue",
}


class LogBuffer(logging.Handler):
    """Ring-Puffer aller Meldungen; jedes offene Live-Log liest ihn mit
    eigenem Lesezeiger (logs_websocket). _push() ist synchron und schnell
    (nur deque.append), gesendet wird in den Verbindungen selbst.

    Jeder Eintrag trägt:
      epoch  - numerischer Zeitstempel (Statistik zählt darüber, nicht über
               den HH:MM:SS-String: kein Mitternachtsfehler)
      seq    - lückenlos steigende Nummer je Prozess; boot kennzeichnet den
               Prozess, damit ein Terminal nach einem Neustart neu beginnt
               statt alles mit kleinerer Nummer zu verwerfen
      trace  - optional: Traceback/Folgezeilen getrennt von der 1. Zeile
    """

    def __init__(self, maxlen: int = LOG_BUFFER_SIZE):
        super().__init__()
        self.buffer: deque[dict] = deque(maxlen=maxlen)
        self.boot = uuid.uuid4().hex[:12]
        self._rate_cache: dict[str, float] = {}
        self._seq = 0

    @property
    def last_seq(self) -> int:
        return self._seq

    def emit(self, record: logging.LogRecord):
        short_name = record.name.split(".")[-1]
        cat = _LOGGER_CAT_MAP.get(short_name, "backend")
        # format() hängt bei exc_info den mehrzeiligen Traceback an die
        # Meldung. Für das Terminal trennen: 1. Zeile = msg, Rest = trace.
        text = self.format(record)
        trace = None
        if "\n" in text:
            text, trace = text.split("\n", 1)
        entry = {
            "ts": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
            "epoch": round(record.created, 3),
            "level": record.levelname,
            "name": short_name,
            "msg": text,
            "cat": cat,
        }
        if trace:
            entry["trace"] = trace
        self._push(entry)

    def push_api(self, method: str, path: str, status: int, duration_ms: float,
                 client: str = ""):
        # Lesende Abfragen, die gelingen, sind Rauschen (die Oberfläche fragt
        # laufend nach): Stufe DEBUG. Änderungen und Fehler sind Ereignisse.
        if status >= 500:
            level = "ERROR"
        elif status >= 400:
            level = "WARNING"
        else:
            level = "DEBUG" if method in ("GET", "HEAD") else "INFO"
        now = time.time()
        entry = {
            "ts": datetime.fromtimestamp(now).strftime("%H:%M:%S"),
            "epoch": round(now, 3),
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

    def push_frontend(self, entries: list["FrontendLogEntry"]):
        for e in entries:
            now = time.time()
            self._push({
                "ts": datetime.fromtimestamp(now).strftime("%H:%M:%S"),
                "epoch": round(now, 3),
                "level": e.level,
                "name": e.source,
                "msg": e.msg,
                "cat": "frontend",
                **({"trace": e.trace} if e.trace else {}),
            })

    def push_event(self, cat: str, level: str, name: str, msg: str,
                   rate_key: str = None, rate_seconds: float = 0):
        now = time.time()
        if rate_key and rate_seconds > 0:
            last = self._rate_cache.get(rate_key, 0)
            if now - last < rate_seconds:
                return
            self._rate_cache[rate_key] = now
            if len(self._rate_cache) > 500:
                cutoff = now - 60
                self._rate_cache = {k: v for k, v in self._rate_cache.items() if v > cutoff}
        entry = {
            "ts": datetime.fromtimestamp(now).strftime("%H:%M:%S"),
            "epoch": round(now, 3),
            "level": level,
            "name": name,
            "msg": msg,
            "cat": cat,
        }
        self._push(entry)

    def _push(self, entry: dict):
        """Schnell und synchron - nur deque-Append, kein I/O."""
        self._seq += 1
        entry["seq"] = self._seq
        self.buffer.append(entry)

    def entries_after(self, after: int, limit: int) -> tuple[list[dict], int]:
        """Höchstens limit Einträge mit seq > after, dazu die Anzahl, die
        dazwischen schon aus dem Ring gefallen ist (Lücke)."""
        if not self.buffer:
            return [], 0
        first = self.buffer[0]["seq"]
        gap = max(0, first - after - 1)
        start = max(0, after + 1 - first)          # seq ist im Ring lückenlos
        return list(itertools.islice(self.buffer, start, start + limit)), gap

    def get_history(self, n: int = 200, cat: str = None) -> list[dict]:
        items = list(self.buffer)
        if cat:
            items = [e for e in items if e.get("cat") == cat]
        return items[-n:]


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
# Root-Logger Level explizit setzen – basicConfig() in main.py greift nicht,
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


def compute_log_stats(entries: list[dict], now: float = None) -> dict:
    """Log-Statistiken über eine Eintragsliste (pure Funktion, testbar).

    errors_last_hour zählt numerisch über das epoch-Feld. Der frühere
    Vergleich von "%H:%M:%S"-Strings zählte nach Mitternacht falsch:
    frische Einträge (z.B. "00:05:00") lagen lexikografisch UNTER dem
    Cutoff (z.B. "23:30:00") und fielen raus, während alte von gestern
    Abend fälschlich zählten.
    """
    now = now if now is not None else time.time()
    cutoff = now - 3600
    stats = {
        "total": len(entries),
        "by_category": {},
        "by_level": {},
        "errors_last_hour": 0,
    }
    for entry in entries:
        cat = entry.get("cat", "unknown")
        level = entry.get("level", "INFO")
        stats["by_category"][cat] = stats["by_category"].get(cat, 0) + 1
        stats["by_level"][level] = stats["by_level"].get(level, 0) + 1
        if level in ("ERROR", "CRITICAL") and entry.get("epoch", 0) >= cutoff:
            stats["errors_last_hour"] += 1
    return stats


@router.get("/logs/stats")
async def get_log_stats():
    """Log-Statistiken: echte Zähler pro Kategorie und Level."""
    return compute_log_stats(list(log_buffer.buffer))


class FrontendLogEntry(BaseModel):
    """Eine Meldung aus dem Browser (lib/utils/frontendLog.js); Zeit setzt der Server."""
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    source: str = Field("ui", max_length=40)
    msg: str = Field(..., max_length=2000)
    trace: Optional[str] = Field(None, max_length=8000)

    @field_validator("level", mode="before")
    @classmethod
    def _level(cls, value):
        value = str(value or "INFO").upper()
        return {"WARN": "WARNING", "LOG": "INFO", "CRITICAL": "ERROR"}.get(value, value)


@router.post("/logs/frontend")
async def push_frontend_logs(entries: list[FrontendLogEntry] = Body(..., max_length=50)):
    """Meldungen aus dem Browser in den Ring übernehmen (höchstens 50 je Aufruf)."""
    log_buffer.push_frontend(entries)
    return {"accepted": len(entries)}


@router.websocket("/ws/logs")
async def logs_websocket(websocket: WebSocket, boot: str = "", after: int = 0):
    """Live-Log-Stream mit eigenem Lesezeiger je Verbindung. Der Client meldet
    beim Verbinden, was er schon hat (boot, after); gesendet werden Rahmen
    {boot, entries, gap, restarted}: gap zählt Einträge, die inzwischen aus
    dem Ring gefallen sind, restarted heißt: neuer Prozess, von vorn beginnen."""
    await websocket.accept()
    same_process = boot == log_buffer.boot
    cursor = after if same_process else max(0, log_buffer.last_seq - LOG_HISTORY)
    if not same_process and log_buffer.buffer:
        cursor = max(cursor, log_buffer.buffer[0]["seq"] - 1)   # Verlauf ist kein Verlust
    sender = asyncio.create_task(_stream_logs(websocket, cursor, restarted=bool(boot) and not same_process))
    try:
        while True:
            if await websocket.receive_text() == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        sender.cancel()


async def _stream_logs(websocket: WebSocket, cursor: int, restarted: bool) -> None:
    first = True
    try:
        while True:
            entries, gap = log_buffer.entries_after(cursor, LOG_FRAME_LIMIT)
            if entries or gap or first:
                frame = {"boot": log_buffer.boot, "entries": entries, "gap": gap}
                if first and restarted:
                    frame["restarted"] = True
                await websocket.send_json(frame)
                first = False
                if entries:
                    cursor = entries[-1]["seq"]
            if len(entries) < LOG_FRAME_LIMIT:
                await asyncio.sleep(0.25)
    except (WebSocketDisconnect, RuntimeError):
        pass     # Verbindung zu; der Empfänger beendet sich selbst


@router.get("/health")
async def health_check():
    return {"status": "ok", "app": APP_NAME, "version": VERSION}


@router.get("/badges")
async def get_badges():
    """Leichtgewichtige Zähler für Sidebar-Badges.
    Alle Definitionen zentral aus counts_service (eine Quelle der Wahrheit).
    Jedes Badge zählt exakt das, was seine Zielseite anzeigt."""
    # Jedes Fenster fragt alle 8 s: einmal gerechnet gilt für alle (shared_cache)
    from app.services import shared_cache
    return await shared_cache.cached("badges", BADGES_TTL_S, _badges)


BADGES_TTL_S = 8


async def _badges() -> dict:
    from app.services.counts_service import counts_service as cs
    active_dl = await db.fetch_val(
        "SELECT COUNT(*) FROM jobs WHERE type='download' AND status IN ('queued','active')") or 0
    # Batch-Queue: Sicher abfragen (Tabelle existiert evtl. noch nicht)
    try:
        batch_waiting = await db.fetch_val(
            "SELECT COUNT(*) FROM batch_queue WHERE status IN ('waiting','downloading')") or 0
    except Exception:
        batch_waiting = 0
    return {
        "videos": await cs.library_videos(),
        "subscriptions": await cs.subscriptions_enabled(),
        "new_feed": await cs.feed_new(),
        "active_downloads": active_dl,
        "favorites": await cs.favorites(),
        "playlists": await cs.playlists_global(),
        "categories": await cs.categories(),
        "history": await cs.history_played(),
        "archives": await cs.archived_videos(),
        "own_videos": await cs.own_videos(),   # jetzt = OwnVideos-Seite (file_size>0)
        "music": await cs.music(),
        "batch_queue": batch_waiting,
        "dubbing": await db.fetch_val(
            "SELECT COUNT(*) FROM dub_requests WHERE status IN ('queued', 'working')") or 0,
    }


@router.get("/background")
async def background_work_overview():
    """Laufende Hintergrundarbeiten mit Stand, Laufzeit und Restdauer."""
    from app.services import background_work
    return {"items": await background_work.overview()}


@router.get("/semantic")
async def semantic_overview():
    """Stand der Bedeutungssuche: eingeschaltet, erreichbar, wie viele Videos eingebettet."""
    from app.services import semantic_index
    return await semantic_index.overview()


@router.get("/shorts")
async def shorts_overview():
    """Wie viele bestätigte Shorts sind geladen, wie viele Typen noch ungeprüft?"""
    from app.services import video_classifier
    return await video_classifier.shorts_overview()


@router.post("/shorts/delete")
async def delete_shorts():
    """Alle geladenen, als Short bestätigten Videos restlos löschen."""
    from app.services import video_classifier
    return {"deleted": await video_classifier.delete_shorts()}


@router.get("/version")
async def get_version():
    return {"app": APP_NAME, "version": VERSION, "api_version": "v1"}


@router.get("/update")
async def get_update_status():
    """Ist eine neuere Version des Projekts erschienen? (services/update_check)"""
    from app.services import update_check
    return await update_check.status()


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
    from app.services.counts_service import counts_service as cs
    video_stats = await metadata_service.get_stats()
    # Disk: zentral aus counts_service – IMMER beide Mounts, Split via st_dev
    # (löst die alte >1GB-Heuristik ab, die gleich große Platten verbarg).
    mounts = cs.disk_mounts()
    disk_media = mounts["media"]
    disk_meta = mounts["meta"]
    db_size = DB_PATH.stat().st_size if DB_PATH.exists() else 0

    active_dl = await db.fetch_val("SELECT COUNT(*) FROM jobs WHERE type='download' AND status = 'active'") or 0
    pending_dl = await db.fetch_val("SELECT COUNT(*) FROM jobs WHERE type='download' AND status = 'queued'") or 0
    active_jobs = await db.fetch_val("SELECT COUNT(*) FROM jobs WHERE status = 'active'") or 0
    total_subs = await cs.subscriptions_total()
    error_subs = await cs.subscriptions_error()

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
        # Beide Platten IMMER liefern (mit Label); Frontend zeigt bei
        # same_device nur eine Karte.
        "disk_media": disk_media,
        "disk_meta": disk_meta,
        "storage_split": not mounts["same_device"],
    }
    return result


@router.get("/status")
async def get_full_status():
    """Gesamtstatus aller Services – für Frontend-Header/Footer.

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
                        "block_active": not yt_ok,
                        "bot_detected": rate_limiter.is_bot_detected(),
                        "bot_until": rate_limiter._yt_bot_until if rate_limiter.is_bot_detected() else None},
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
    """Speicher-Übersicht: Platten sofort, Ordnergrößen aus der letzten
    Messung im Hintergrund (siehe services/storage_usage) - nie blockierend."""
    from app.services import storage_usage

    disk_media = get_disk_usage(str(VIDEOS_DIR))
    disk_meta = get_disk_usage(str(DB_DIR))
    is_split = abs(disk_media.get("total", 0) - disk_meta.get("total", 0)) > 1_000_000_000
    usage = await storage_usage.snapshot()
    result = {
        "disk": disk_media,
        "storage_split": is_split,
        "directories": {
            name: {"size": d.size, "size_human": human_size(d.size) if d.size is not None else None,
                   "disk": d.disk}
            for name, d in usage.directories.items()
        },
        "measured_at": usage.measured_at,
        "measuring": usage.measuring,
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

    from app.services import storage_usage
    size_before = await asyncio.to_thread(storage_usage.directory_size, TEMP_DIR)
    if TEMP_DIR.exists():
        await asyncio.to_thread(shutil.rmtree, TEMP_DIR)
        TEMP_DIR.mkdir(parents=True)
    storage_usage.refresh()

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
    from app.utils.file_utils import is_media_file
    ghosts = []
    for row in rows:
        fp = row["file_path"]
        if not is_media_file(fp):
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
        from app.utils.file_utils import is_media_file
        ghosts = [r for r in ready if not is_media_file(r["file_path"])]
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
        from app.services.search import index as search_extra_index
        await search_extra_index.after_vacuum(db._connection)
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

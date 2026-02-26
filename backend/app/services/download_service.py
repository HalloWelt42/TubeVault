"""
TubeVault – Download Service v1.8.40
Live-Progress, Stufen, FFmpeg-Merge, Rate-Limiting, Resume, Job-Tracking, Adaptive Cooldown
pytubefix: Chapters, Captions, Audio-Only nativ
© HalloWelt42 – Private Nutzung

Download-Stufen:
1. resolving         – Video-Info von YouTube laden
2. resolved          – Streams erkannt
3. downloading_video – Video-Spur wird heruntergeladen
4. downloading_audio – Audio-Spur wird heruntergeladen (nur adaptive)
5. merging           – FFmpeg merged Video+Audio
6. finalizing        – Thumbnail, DB-Eintrag
7. done              – Fertig
"""

import asyncio
import json
import logging
import os
import time as _time
import re
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable

from pytubefix import YouTube, Stream

from app.config import (
    VIDEOS_DIR, THUMBNAILS_DIR,
    MAX_CONCURRENT_DOWNLOADS, DEFAULT_QUALITY, DEFAULT_FORMAT,
)
from app.database import db
from app.services.rate_limiter import rate_limiter
from app.services.job_service import job_service
from app.utils.file_utils import now_sqlite, future_sqlite
from app.utils.tag_utils import sanitize_tags

logger = logging.getLogger(__name__)

_last_ws_time: dict[int, float] = {}
WS_THROTTLE = 0.4


def _srt_to_vtt(srt_text: str) -> str:
    """SRT-Format zu WebVTT konvertieren."""
    # SRT nutzt Komma als Dezimaltrenner, VTT nutzt Punkt
    vtt = srt_text.replace(",", ".")
    # SRT-Nummern entfernen (Zeilen die nur Ziffern sind)
    lines = vtt.split("\n")
    cleaned = []
    for line in lines:
        if line.strip().isdigit():
            continue
        cleaned.append(line)
    return "WEBVTT\n\n" + "\n".join(cleaned).strip() + "\n"


def extract_video_id(url: str) -> Optional[str]:
    patterns = [
        r'(?:v=|\/v\/|youtu\.be\/|\/embed\/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def detect_video_type(yt, source_url: str = "") -> str:
    """Erkennt Video-Typ: 'video', 'short' oder 'live'.

    Signale (Priorität):
    1. InnerTube videoDetails: isLive, isLiveContent, isPostLiveDvr → "live"
    2. URL enthält /shorts/ → "short"
    3. Canonical URL in microformat enthält /shorts/ → "short"
    4. Duration allein reicht NICHT für Short-Erkennung
    """
    try:
        details = yt.vid_info.get("videoDetails", {})
        # Live-Erkennung
        if details.get("isLive"):
            return "live"
        if details.get("isLiveContent") or details.get("isPostLiveDvr"):
            return "live"
    except Exception:
        pass

    # Short-Erkennung: URL-basiert (zuverlässigster Indikator)
    url_to_check = source_url or ""
    try:
        url_to_check = url_to_check or getattr(yt, "watch_url", "") or ""
    except Exception:
        pass

    if "/shorts/" in url_to_check:
        return "short"

    # Short-Erkennung: Canonical URL aus microformat
    try:
        mf = yt.vid_info.get("microformat", {}).get("playerMicroformatRenderer", {})
        canonical = mf.get("urlCanonical", "")
        if "/shorts/" in canonical:
            return "short"
    except Exception:
        pass

    return "video"


class DownloadService:

    def __init__(self):
        self._active_downloads: dict[int, asyncio.Task] = {}
        self._progress_callbacks: list[Callable] = []
        self._worker_task: Optional[asyncio.Task] = None
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._phases_cache: dict[int, list] = {}  # job_id → letzte phases
        self._last_db_write: dict[int, float] = {}  # job_id → timestamp des letzten DB-Writes
        # Cooldown-State (initialisiert in _queue_loop, hier Defaults für get_cooldown_state)
        self._cooldown = 30
        self._cooldown_base = 30
        self._cooldown_max = 7200
        self._cooldown_until = 0.0
        self._cooldown_active = False

    async def _get_setting(self, key: str, default: str = "") -> str:
        val = await db.fetch_val("SELECT value FROM settings WHERE key = ?", (key,))
        return val or default

    def add_progress_callback(self, cb: Callable):
        self._progress_callbacks.append(cb)

    def remove_progress_callback(self, cb: Callable):
        if cb in self._progress_callbacks:
            self._progress_callbacks.remove(cb)

    async def _ws_broadcast(self, data: dict):
        # Automatisch type-Feld setzen wenn nicht vorhanden
        if "type" not in data and "job_id" in data:
            data["type"] = "download_progress"
        # Phasen cachen wenn vorhanden
        job_id = data.get("job_id")
        if job_id and "phases" in data and data["phases"]:
            self._phases_cache[job_id] = data["phases"]

        # Progress periodisch in DB schreiben (alle 5s)
        # Damit GET /api/jobs auch während Downloads echten Fortschritt zeigt
        progress = data.get("progress")
        if job_id and progress is not None and data.get("type") == "download_progress":
            now = _time.time()
            last = self._last_db_write.get(job_id, 0)
            if now - last >= 5.0:
                self._last_db_write[job_id] = now
                try:
                    await db.execute(
                        "UPDATE jobs SET progress = ? WHERE id = ?",
                        (round(progress, 3), job_id)
                    )
                except Exception:
                    pass

        for cb in self._progress_callbacks:
            try:
                await cb(data)
            except Exception as e:
                logger.error(f"WS callback error: {e}")

    def _ws_broadcast_sync(self, data: dict):
        """Thread-safe broadcast. Caches + injects phases automatically."""
        job_id = data.get("job_id")
        stage = data.get("stage", "")
        # Phasen cachen wenn vorhanden
        if job_id and "phases" in data and data["phases"]:
            self._phases_cache[job_id] = data["phases"]
        elif job_id and job_id in self._phases_cache and "phases" not in data:
            # Cached phases injizieren + Status nach aktuellem Stage aktualisieren
            cached = self._phases_cache[job_id]
            stage_map = {
                "resolving": "resolving", "resolved": "resolving",
                "downloading_video": "downloading_video",
                "downloading_audio": "downloading_audio",
                "merging": "merging", "finalizing": "finalizing",
            }
            phase_id = stage_map.get(stage, stage)
            active_idx = next((i for i, p in enumerate(cached) if p["id"] == phase_id), -1)
            if active_idx >= 0:
                updated = []
                for i, p in enumerate(cached):
                    cp = {**p}
                    if i < active_idx:
                        cp["status"] = "done"
                    elif i == active_idx:
                        cp["status"] = "active"
                    else:
                        cp["status"] = "pending"
                    updated.append(cp)
                data["phases"] = updated
            else:
                data["phases"] = cached
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._ws_broadcast(data), self._loop)

    # Phasen-Definition für mehrstufigen Fortschrittsbalken
    PHASES = [
        {"id": "resolving",         "label": "Auflösen",  "start": 0.00, "end": 0.05, "color": "#90A4AE"},
        {"id": "downloading_video", "label": "Video ↓",   "start": 0.05, "end": 0.60, "color": "#4CAF50"},
        {"id": "downloading_audio", "label": "Audio ↓",   "start": 0.60, "end": 0.90, "color": "#2196F3"},
        {"id": "merging",           "label": "Merge",      "start": 0.90, "end": 0.96, "color": "#FF9800"},
        {"id": "finalizing",        "label": "Abschluss",  "start": 0.96, "end": 1.00, "color": "#9C27B0"},
    ]

    # Phasen ohne Merge (progressive Downloads)
    PHASES_PROGRESSIVE = [
        {"id": "resolving",         "label": "Auflösen",  "start": 0.00, "end": 0.05, "color": "#90A4AE"},
        {"id": "downloading_video", "label": "Video ↓",   "start": 0.05, "end": 0.90, "color": "#4CAF50"},
        {"id": "finalizing",        "label": "Abschluss",  "start": 0.90, "end": 1.00, "color": "#9C27B0"},
    ]

    # Phasen für Audio-Only
    PHASES_AUDIO = [
        {"id": "resolving",         "label": "Auflösen",  "start": 0.00, "end": 0.05, "color": "#90A4AE"},
        {"id": "downloading_audio", "label": "Audio ↓",   "start": 0.05, "end": 0.90, "color": "#2196F3"},
        {"id": "finalizing",        "label": "Abschluss",  "start": 0.90, "end": 1.00, "color": "#9C27B0"},
    ]

    def _get_phases(self, stage: str, opts: dict = None) -> list:
        """Passende Phasen-Definition basierend auf Download-Typ."""
        if opts and opts.get("audio_only"):
            return self.PHASES_AUDIO
        # Wenn wir schon in der Merge-Phase sind, ist es definitiv adaptive
        if stage in ("downloading_audio", "merging"):
            return self.PHASES
        if opts and opts.get("merge_audio", True):
            return self.PHASES  # Standard: adaptive assumed
        return self.PHASES_PROGRESSIVE

    async def _stage(self, job_id: int, vid: str, stage: str, progress: float, label: str,
                     opts: dict = None):
        """Stage-Update: WebSocket + Job-System mit Phasen-Info."""
        if stage in ("done", "error", "cancelled"):
            ws_status = stage
        else:
            ws_status = "active"

        # Phasen-Metadaten für Frontend
        phases = self._get_phases(stage, opts)
        # Stage → Phase Mapping (z.B. "resolved" → "resolving", "retry_wait" → keiner)
        stage_to_phase = {
            "resolving": "resolving", "resolved": "resolving",
            "downloading_video": "downloading_video",
            "downloading_audio": "downloading_audio",
            "merging": "merging",
            "finalizing": "finalizing",
        }
        phase_id = stage_to_phase.get(stage, stage)
        active_idx = next((i for i, p in enumerate(phases) if p["id"] == phase_id), -1)
        phases_info = []
        for i, p in enumerate(phases):
            if i < active_idx:
                status = "done"
            elif i == active_idx:
                status = "active"
                # Fortschritt innerhalb der Phase berechnen
            else:
                status = "pending"
            phases_info.append({**p, "status": status})

        await self._ws_broadcast({
            "type": "download_progress",
            "job_id": job_id, "queue_id": job_id, "video_id": vid,
            "status": ws_status, "progress": round(progress, 3),
            "stage": stage, "stage_label": label,
            "phases": phases_info,
        })
        if job_id and stage in ("done", "error", "cancelled"):
            self._phases_cache.pop(job_id, None)
            self._last_db_write.pop(job_id, None)
        if job_id and stage not in ("done", "error", "cancelled"):
            # DB direkt updaten OHNE job_service.notify() → verhindert doppelte WS-Message
            # _ws_broadcast oben hat die Live-Daten bereits gesendet
            try:
                await db.execute(
                    "UPDATE jobs SET progress = ?, description = ? WHERE id = ?",
                    (round(progress, 3), label, job_id)
                )
            except Exception:
                pass

    # --- Video-Info (gecacht) ---

    async def get_video_info(self, url: str) -> dict:
        video_id = extract_video_id(url)
        if not video_id:
            raise ValueError(f"Ungültige YouTube-URL: {url}")

        existing = await db.fetch_one("SELECT id, status FROM videos WHERE id = ?", (video_id,))

        await rate_limiter.acquire("pytubefix")

        def _fetch():
            try:
                yt = YouTube(f"https://www.youtube.com/watch?v={video_id}")
            except Exception as e:
                logger.error(f"[VideoInfo] YouTube-Objekt erstellen fehlgeschlagen für {video_id}: {e}")
                raise ValueError(f"YouTube-Zugriff fehlgeschlagen: {e}")

            # Streams (häufigste Fehlerquelle bei pytubefix-Updates)
            streams = []
            try:
                for s in yt.streams:
                    try:
                        streams.append({
                            "itag": s.itag, "mime_type": s.mime_type, "type": s.type,
                            "quality": getattr(s, "resolution", None) or getattr(s, "abr", None),
                            "codec": s.codecs[0] if getattr(s, "codecs", None) else None,
                            "file_size": getattr(s, "filesize_approx", None),
                            "is_progressive": getattr(s, "is_progressive", False),
                            "is_adaptive": getattr(s, "is_adaptive", False),
                            "fps": getattr(s, "fps", None),
                        })
                    except Exception as se:
                        logger.debug(f"[VideoInfo] Stream-Eintrag übersprungen: {se}")
            except Exception as e:
                logger.warning(f"[VideoInfo] Streams laden fehlgeschlagen für {video_id}: {e}")

            # Captions
            captions = []
            try:
                for cap in yt.captions:
                    captions.append({"code": cap.code, "name": cap.name})
            except Exception:
                pass

            # Chapters
            chapters = []
            try:
                for ch in yt.chapters:
                    chapters.append({
                        "title": ch.title,
                        "start_time": ch.start_seconds,
                        "end_time": ch.start_seconds + ch.duration,
                    })
            except Exception:
                pass

            # Video-Typ
            video_type = "video"
            try:
                video_type = detect_video_type(yt, url)
            except Exception:
                pass

            # Basis-Metadaten (jeweils einzeln abgesichert)
            def safe(fn, default=None):
                try:
                    return fn()
                except Exception:
                    return default

            return {
                "id": video_id,
                "title": safe(lambda: yt.title, video_id),
                "channel_name": safe(lambda: yt.author),
                "channel_id": safe(lambda: yt.channel_id),
                "description": safe(lambda: yt.description),
                "duration": safe(lambda: yt.length),
                "upload_date": safe(lambda: str(yt.publish_date) if yt.publish_date else None),
                "view_count": safe(lambda: yt.views),
                "thumbnail_url": safe(lambda: yt.thumbnail_url, f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"),
                "tags": safe(lambda: sanitize_tags(yt.keywords or []), []),
                "streams": streams,
                "captions": captions, "chapters": chapters,
                "video_type": video_type,
                "already_downloaded": existing is not None,
                "existing_status": dict(existing)["status"] if existing else None,
            }

        try:
            result = await asyncio.get_event_loop().run_in_executor(None, _fetch)
            rate_limiter.success("pytubefix")
            return result
        except ValueError:
            raise  # Wird als 400 behandelt
        except Exception as e:
            logger.error(f"[VideoInfo] get_video_info fehlgeschlagen für {video_id}: {type(e).__name__}: {e}")
            rate_limiter.error("pytubefix", str(e))
            raise

    # --- Queue ---

    async def add_to_queue(self, url: str, quality: str = None, format: str = None,
                           download_thumbnail: bool = None, priority: int = 0,
                           itag: int = None, audio_itag: int = None,
                           merge_audio: bool = True,
                           subtitle_lang: str = None, audio_only: bool = False,
                           force: bool = False) -> dict:
        video_id = extract_video_id(url)
        if not video_id:
            raise ValueError(f"Ungültige YouTube-URL: {url}")

        # Settings aus DB lesen wenn nicht explizit übergeben
        if quality is None:
            quality = await self._get_setting("download.quality", DEFAULT_QUALITY)
        if format is None:
            format = await self._get_setting("download.format", DEFAULT_FORMAT)
        if download_thumbnail is None:
            download_thumbnail = (await self._get_setting("download.auto_thumbnail", "true")) == "true"

        # Audio-only → quality override
        if audio_only:
            quality = "audio_only"

        # Duplikat-Check: bereits heruntergeladen?
        existing = await db.fetch_one(
            "SELECT id, status FROM videos WHERE id = ?", (video_id,)
        )
        if existing and existing["status"] == "ready" and not force:
            raise ValueError(f"Video {video_id} ist bereits heruntergeladen")

        # Duplikat-Check: in externem Archiv vorhanden?
        if not force:
            in_archive = await db.fetch_one(
                """SELECT va.*, a.name as archive_name, a.mount_path
                   FROM video_archives va JOIN archives a ON va.archive_id = a.id
                   WHERE va.video_id = ?""",
                (video_id,)
            )
            if in_archive:
                archive_name = in_archive["archive_name"]
                raise ValueError(
                    f"Video {video_id} existiert bereits im Archiv '{archive_name}'. "
                    f"Nutze force=true um trotzdem lokal herunterzuladen."
                )

        # Queue-Duplikat-Check (in jobs statt download_queue)
        dup = await db.fetch_one(
            "SELECT id FROM jobs WHERE type = 'download' AND status IN ('queued','active') AND json_extract(metadata, '$.video_id') = ?",
            (video_id,)
        )
        if dup:
            raise ValueError(f"Video {video_id} ist bereits in der Queue")

        # Titel aus vorhandenen Daten holen (rss_entries oder videos)
        known_title = None
        row = await db.fetch_one(
            "SELECT title FROM rss_entries WHERE video_id = ? AND title IS NOT NULL LIMIT 1",
            (video_id,)
        )
        if row and row["title"]:
            known_title = row["title"]
        else:
            row = await db.fetch_one(
                "SELECT title FROM videos WHERE id = ? AND title IS NOT NULL",
                (video_id,)
            )
            if row and row["title"]:
                known_title = row["title"]

        opts = {
            "quality": quality or DEFAULT_QUALITY, "format": format or DEFAULT_FORMAT,
            "download_thumbnail": download_thumbnail, "itag": itag, "audio_itag": audio_itag,
            "merge_audio": merge_audio,
            "subtitle_lang": subtitle_lang, "audio_only": audio_only,
        }
        full_url = f"https://www.youtube.com/watch?v={video_id}"
        display_title = known_title[:256] if known_title else video_id
        job = await job_service.create(
            job_type="download",
            title=display_title,
            description="In Warteschlange",
            metadata={
                "video_id": video_id, "url": full_url,
                "download_options": opts,
                "retry_count": 0, "max_retries": 3,
            },
            priority=priority,
        )
        job_id = job["id"]

        await self._ws_broadcast({
            "job_id": job_id, "queue_id": job_id, "video_id": video_id, "status": "queued",
            "progress": 0.0, "stage": "queued", "stage_label": "In Warteschlange",
        })
        return {"job_id": job_id, "queue_id": job_id, "video_id": video_id, "status": "queued"}

    async def add_batch_to_queue(self, urls: list[str], quality: str = None) -> list[dict]:
        results = []
        for u in urls:
            try:
                results.append(await self.add_to_queue(u, quality=quality))
            except Exception as e:
                results.append({"url": u, "status": "error", "error": str(e)})
        return results

    # --- Worker ---

    async def start_worker(self):
        if self._worker_task and not self._worker_task.done():
            return
        self._loop = asyncio.get_event_loop()
        # Concurrent-Einstellung aus DB lesen
        try:
            concurrent = int(await self._get_setting("download.concurrent", str(MAX_CONCURRENT_DOWNLOADS)))
            self._semaphore = asyncio.Semaphore(max(1, concurrent))
            logger.info(f"Download Semaphore: {concurrent} gleichzeitig")
        except (ValueError, TypeError):
            pass
        # Resume: stale 'active' Download-Jobs zurücksetzen auf 'queued'
        stale = await db.execute(
            "UPDATE jobs SET status = 'queued', progress = 0, description = NULL, error_message = NULL "
            "WHERE type = 'download' AND status = 'active'"
        )
        if stale.rowcount > 0:
            logger.info(f"Resume: {stale.rowcount} abgebrochene Downloads zurück in Queue")
        # Titel-Fixup: Jobs mit nur Video-ID → echten Titel aus RSS nachladen
        try:
            id_only_jobs = await db.fetch_all(
                "SELECT id, title, json_extract(metadata, '$.video_id') as vid FROM jobs "
                "WHERE type='download' AND status='queued' AND (length(title) = 11 OR title LIKE 'Download: %')"
            )
            fixed = 0
            for j in id_only_jobs:
                vid = j["vid"] or j["title"].replace("Download: ", "")
                real_title = await db.fetch_val(
                    "SELECT title FROM rss_entries WHERE video_id = ?", (vid,))
                if real_title:
                    await db.execute("UPDATE jobs SET title = ? WHERE id = ?",
                                     (real_title[:256], j["id"]))
                    fixed += 1
            if fixed:
                logger.info(f"Titel-Fixup: {fixed} queued Jobs mit echtem Titel aktualisiert")
        except Exception as e:
            logger.warning(f"Titel-Fixup Fehler: {e}")
        self._worker_task = asyncio.create_task(self._queue_loop())
        self._worker_task.add_done_callback(self._on_worker_done)
        # Watchdog starten
        if not getattr(self, '_watchdog_task', None) or self._watchdog_task.done():
            self._watchdog_task = asyncio.create_task(self._watchdog())
        logger.info("Download Worker gestartet")

    def _on_worker_done(self, task):
        """Callback wenn Worker-Task endet – loggt Fehler und plant Neustart."""
        try:
            exc = task.exception()
            if exc:
                logger.error(f"Download Worker abgestürzt: {exc}", exc_info=exc)
            else:
                logger.warning("Download Worker beendet (kein Fehler)")
        except asyncio.CancelledError:
            logger.info("Download Worker gestoppt (cancelled)")
            return
        # Auto-Restart über Watchdog (nicht direkt hier, da kein async-Kontext)
        logger.warning("Worker wird durch Watchdog neu gestartet…")

    async def _watchdog(self):
        """Prüft alle 30s ob der Worker lebt und startet ihn bei Bedarf neu."""
        while True:
            await asyncio.sleep(30)
            try:
                if not self._worker_task or self._worker_task.done():
                    logger.warning("[Watchdog] Worker tot – Neustart…")
                    self._worker_task = asyncio.create_task(self._queue_loop())
                    self._worker_task.add_done_callback(self._on_worker_done)
                    self._loop = asyncio.get_event_loop()
                    logger.info("[Watchdog] Worker neu gestartet")
            except Exception as e:
                logger.error(f"[Watchdog] Fehler: {e}")

    @property
    def worker_alive(self) -> bool:
        """Prüft ob der Worker-Task läuft."""
        return self._worker_task is not None and not self._worker_task.done()

    async def restart_worker(self):
        """Worker-Task neu starten (z.B. nach Crash)."""
        logger.warning("Download Worker wird neu gestartet…")
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        self._worker_task = None
        await self.start_worker()
        return {"restarted": True, "alive": self.worker_alive}

    async def stop_worker(self):
        # Watchdog stoppen
        if getattr(self, '_watchdog_task', None) and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def _queue_loop(self):
        # ─── Globaler Cooldown ────────────────────────
        # Basis: 30s zwischen jedem YouTube-Job
        # Bei Fehler: verdoppeln (30→60→120→…→7200)
        # Bei 7200 (2h) → harte Pause (wie User-Pause)
        # Bei Erfolg: zurück auf 30s
        self._cooldown = 30           # aktuelle Wartezeit in Sekunden
        self._cooldown_base = 30      # Basis-Wert
        self._cooldown_max = 7200     # 2 Stunden
        self._cooldown_until = 0.0    # Timestamp wann Cooldown endet (für Frontend-Timer)
        self._cooldown_active = False # True während countdown läuft

        while True:
            try:
                # Retry-Wait Items prüfen: zurück auf queued wenn Zeit abgelaufen
                now = now_sqlite()
                retry_rows = await db.fetch_all(
                    "SELECT id, metadata FROM jobs WHERE type='download' AND status='retry_wait'"
                )
                for rr in retry_rows:
                    meta = json.loads(rr["metadata"] or "{}")
                    if meta.get("retry_after") and meta["retry_after"] <= now:
                        await db.execute("UPDATE jobs SET status='queued' WHERE id=?", (rr["id"],))

                # Warten wenn Queue pausiert ist (User-Pause oder max-Cooldown-Pause)
                if job_service.is_paused():
                    await asyncio.sleep(3)
                    continue

                # Warten wenn ein SYSTEM-Job aktiv ist (Channel-Scan, Cleanup etc.)
                # RSS-Cycles laufen parallel zu Downloads – KEIN gegenseitiges Blockieren!
                has_blocking_job = await db.fetch_val(
                    """SELECT COUNT(*) FROM jobs
                       WHERE status='active'
                       AND type NOT IN ('download', 'rss_cycle', 'avatar_fetch')"""
                )
                if has_blocking_job:
                    await asyncio.sleep(3)
                    continue

                item = await db.fetch_one(
                    "SELECT * FROM jobs WHERE type='download' AND status='queued' ORDER BY priority DESC, created_at ASC LIMIT 1"
                )
                if item:
                    job_id = item["id"]

                    # Cooldown VOR dem eigentlichen Download abwarten
                    # Job bleibt 'queued' während Cooldown → blockiert nichts!
                    if self._cooldown > 0:
                        self._cooldown_until = _time.time() + self._cooldown
                        self._cooldown_active = True
                        await self._broadcast_cooldown()
                        remaining = self._cooldown
                        while remaining > 0:
                            sleep_step = min(remaining, 1.0)
                            await asyncio.sleep(sleep_step)
                            remaining -= sleep_step
                            self._cooldown_until = _time.time() + remaining
                            if remaining <= 0 or int(remaining) % 5 == 0:
                                await self._broadcast_cooldown()
                        self._cooldown_active = False
                        self._cooldown_until = 0.0
                        await self._broadcast_cooldown()

                        # Nach Cooldown: Pause prüfen
                        if job_service.is_paused():
                            continue

                        # System-Job aktiv? → warten
                        has_system = await db.fetch_val(
                            """SELECT COUNT(*) FROM jobs
                               WHERE status='active'
                               AND type NOT IN ('download', 'rss_cycle', 'avatar_fetch')"""
                        )
                        if has_system:
                            logger.info(f"Download {job_id} yielding to active system job")
                            await asyncio.sleep(3)
                            continue

                    # JETZT erst als aktiv markieren – Download startet wirklich
                    await db.execute(
                        "UPDATE jobs SET status = 'active' WHERE id = ?", (job_id,))

                    async with self._semaphore:
                        await self._process(dict(item))
                else:
                    await asyncio.sleep(2)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker error: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def _broadcast_cooldown(self):
        """Cooldown-Status an Frontend senden."""
        remaining = max(0, self._cooldown_until - _time.time())
        await self._ws_broadcast({
            "type": "cooldown",
            "cooldown": self._cooldown,
            "cooldown_base": self._cooldown_base,
            "cooldown_until": self._cooldown_until,
            "cooldown_remaining": round(remaining),
            "cooldown_active": self._cooldown_active,
        })

    def get_cooldown_state(self) -> dict:
        """Cooldown-Status für System-Status-Endpoint."""
        remaining = max(0, self._cooldown_until - _time.time()) if self._cooldown_until else 0
        return {
            "cooldown": self._cooldown,
            "cooldown_base": getattr(self, '_cooldown_base', 30),
            "cooldown_remaining": round(remaining),
            "cooldown_active": getattr(self, '_cooldown_active', False),
        }

    # --- Download-Pipeline ---

    async def _process(self, item: dict):
        job_id = item["id"]
        meta_raw = json.loads(item.get("metadata") or "{}")
        vid = meta_raw.get("video_id", "")
        url = meta_raw.get("url", "")
        opts = meta_raw.get("download_options", {})
        if isinstance(opts, str):
            opts = json.loads(opts)

        # Job als aktiv markieren
        try:
            await job_service.start(job_id, exclusive=False)
        except Exception as e:
            logger.warning(f"Job-Start für Download {vid} fehlgeschlagen: {e}")

        try:
            # Stage 1: RESOLVING (rate-limited)
            await rate_limiter.acquire("pytubefix")
            await self._stage(job_id, vid, "resolving", 0.02, "Video wird aufgelöst…")
            meta = await self._resolve(url)
            rate_limiter.success("pytubefix")
            await self._stage(job_id, vid, "resolved", 0.05,
                              f"Gefunden: {meta['title'][:120]} ({meta['stream_count']} Streams)")

            # Job-Titel aktualisieren mit echtem Video-Titel
            try:
                real_title = (meta['title'] or vid)[:256]
                await job_service.progress(job_id, 0.05, real_title)
                await db.execute(
                    "UPDATE jobs SET title = ? WHERE id = ?",
                    (real_title, job_id)
                )
            except Exception:
                pass

            # Stage 2+3: DOWNLOAD (rate-limited)
            await rate_limiter.acquire("download")
            final_path, file_size, stream_info, merged = await self._download(job_id, vid, url, opts, meta)
            rate_limiter.success("download")

            # Stage 4: FINALIZE
            await self._stage(job_id, vid, "finalizing", 0.96, "Thumbnail, Kapitel & DB-Eintrag…")
            thumb = None
            if opts.get("download_thumbnail", True) and meta.get("thumbnail_url"):
                thumb = await self._dl_thumbnail(vid, meta["thumbnail_url"])

            now = now_sqlite()
            tags_json = json.dumps(sanitize_tags(meta.get("tags", [])))
            source_url = f"https://www.youtube.com/watch?v={vid}"

            # Video-Typ: zuerst aus meta (get_video_info), dann rss_entries, fallback video
            video_type = meta.get("video_type", None)
            if not video_type or video_type == "video":
                vtype_row = await db.fetch_one(
                    "SELECT video_type FROM rss_entries WHERE video_id = ? LIMIT 1", (vid,)
                )
                if vtype_row and vtype_row[0] and vtype_row[0] != "video":
                    video_type = vtype_row[0]
            if not video_type:
                video_type = "video"

            # Video in DB: UPDATE wenn vorhanden (Upgrade), INSERT wenn neu
            existing_video = await db.fetch_one(
                "SELECT id FROM videos WHERE id = ?", (vid,))
            if existing_video:
                await db.execute(
                    """UPDATE videos SET title=?, channel_name=?, channel_id=?,
                       description=?, duration=?, upload_date=?,
                       download_date=?, thumbnail_path=COALESCE(?,thumbnail_path),
                       view_count=?, tags=?, status='ready',
                       file_path=?, file_size=?,
                       source='youtube', source_url=?, video_type=?, updated_at=?
                       WHERE id=?""",
                    (meta["title"], meta["channel_name"], meta["channel_id"],
                     meta["description"], meta["duration"], meta.get("upload_date"),
                     now, thumb, meta.get("view_count"), tags_json,
                     str(final_path), file_size, source_url, video_type, now, vid))
            else:
                await db.execute(
                    """INSERT INTO videos
                       (id,title,channel_name,channel_id,description,duration,upload_date,
                        download_date,thumbnail_path,view_count,tags,status,file_path,file_size,
                        source,source_url,video_type,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,'ready',?,?,'youtube',?,?,?,?)""",
                    (vid, meta["title"], meta["channel_name"], meta["channel_id"],
                     meta["description"], meta["duration"], meta.get("upload_date"),
                     now, thumb, meta.get("view_count"), tags_json,
                     str(final_path), file_size, source_url, video_type, now, now))
            await db.execute(
                """INSERT OR REPLACE INTO streams
                   (video_id,stream_type,itag,mime_type,quality,codec,file_path,file_size,is_default,is_combined,downloaded)
                   VALUES (?,?,?,?,?,?,?,?,1,?,1)""",
                (vid, stream_info["type"], stream_info["itag"], stream_info["mime"],
                 stream_info["quality"], stream_info["codec"],
                 str(final_path), file_size, 1 if not merged else 0)
            )

            # Kapitel speichern (pytubefix chapters) – NACH video INSERT
            auto_chapters = await db.fetch_val("SELECT value FROM settings WHERE key = 'download.auto_chapters'")
            if auto_chapters != "false" and meta.get("chapters"):
                for ch in meta["chapters"]:
                    await db.execute(
                        """INSERT OR IGNORE INTO chapters (video_id, title, start_time, end_time, source)
                           VALUES (?, ?, ?, ?, 'youtube')""",
                        (vid, ch["title"], ch["start_time"], ch.get("end_time"), )
                    )

            # Untertitel automatisch herunterladen wenn aktiviert
            sub_setting = await db.fetch_val("SELECT value FROM settings WHERE key = 'download.auto_subtitle'")
            if sub_setting == "true":
                try:
                    lang_setting = await db.fetch_val("SELECT value FROM settings WHERE key = 'download.subtitle_lang'")
                    langs = (lang_setting or "de,en").split(",")
                    for lang in langs:
                        await self.download_subtitles(vid, lang.strip())
                except Exception as e:
                    logger.warning(f"Auto-Subtitle fail {vid}: {e}")

            # DONE
            await self._stage(job_id, vid, "done", 1.0,
                              f"Fertig: {meta['title'][:50]} ({file_size/1024/1024:.1f} MB)")

            # Auto-Link: Video in passende lokale Playlists einfügen
            try:
                from app.services.playlist_service import auto_link_video_to_playlists
                await auto_link_video_to_playlists(vid)
            except Exception as e:
                logger.debug(f"Auto-Link skip: {e}")

            # Job abschließen
            try:
                await job_service.complete(
                    job_id, f"{meta['title'][:50]} ({file_size/1024/1024:.1f} MB)"
                )
            except Exception:
                pass
            logger.info(f"[OK] {vid} fertig ({file_size/1024/1024:.1f}MB, merge={merged})")

            # Erfolg → Cooldown auf Basis zurücksetzen
            if self._cooldown > self._cooldown_base:
                logger.info(f"Download OK → Cooldown {self._cooldown}s → {self._cooldown_base}s")
                self._cooldown = self._cooldown_base

            # Like/Dislike-Daten abrufen (Return YouTube Dislike API)
            try:
                from app.services.ryd_service import fetch_votes
                await fetch_votes(vid)
            except Exception as e:
                logger.debug(f"RYD-Fetch für {vid}: {e}")

        except Exception as e:
            err = str(e)[:500]
            logger.error(f"[ERR] {vid}: {e}", exc_info=True)
            rate_limiter.error("download", str(e)[:200])

            # Auto-Retry bei Throttle/Rate-Limit/Temporary Fehlern
            retry_count = meta_raw.get("retry_count", 0) or 0
            max_retries = meta_raw.get("max_retries", 3) or 3
            err_lower = err.lower()

            is_throttle = any(kw in err_lower for kw in [
                "retries exceeded", "429", "too many requests",
                "throttl", "rate limit", "forbidden",
            ])
            is_temporary = any(kw in err_lower for kw in [
                "503", "service unavailable", "temporarily unavailable",
                "http error 5", "server error", "connection reset",
                "timed out", "timeout",
            ])
            # Video dauerhaft nicht erreichbar → parken statt retrien
            is_unavailable = any(kw in err_lower for kw in [
                "video unavailable", "private video", "removed",
                "account terminated", "copyright", "not available",
                "join this channel", "members-only", "age-restricted",
                "sign in to confirm your age",
            ])

            if is_unavailable:
                # Sofort parken – kein Retry sinnvoll
                await db.execute(
                    "UPDATE jobs SET status='parked', error_message=? WHERE id=?",
                    (f"Nicht verfügbar: {err[:200]}", job_id)
                )
                await self._ws_broadcast({
                    "job_id": job_id, "queue_id": job_id, "video_id": vid, "status": "parked",
                    "progress": 0, "stage": "parked", "stage_label": f"Geparkt: {err[:80]}",
                })
                await job_service.notify(await job_service.get(job_id))
                logger.warning(f"[PARKED] {vid}: Nicht verfügbar – {err[:120]}")

            elif (is_throttle or is_temporary) and retry_count < max_retries:
                # Exponentieller Backoff: 2min, 5min, 15min
                delays = [120, 300, 900]
                delay = delays[min(retry_count, len(delays) - 1)]
                retry_after = future_sqlite(seconds=delay)
                new_meta = {**meta_raw, "retry_count": retry_count + 1, "retry_after": retry_after}
                await db.execute(
                    "UPDATE jobs SET status='retry_wait', error_message=?, metadata=? WHERE id=?",
                    (f"Retry {retry_count + 1}/{max_retries} in {delay // 60}min – {err[:200]}",
                     json.dumps(new_meta), job_id)
                )
                await self._ws_broadcast({
                    "job_id": job_id, "queue_id": job_id, "video_id": vid, "status": "retry_wait",
                    "progress": 0, "stage": "retry_wait",
                    "stage_label": f"Retry {retry_count + 1}/{max_retries} in {delay // 60}min",
                    "retry_after": retry_after,
                })
                await job_service.notify(await job_service.get(job_id))
                logger.info(f"[RETRY] {vid}: Retry {retry_count + 1} in {delay}s ({('throttle' if is_throttle else 'temporary')})")

                # Adaptive Cooldown hochschrauben (verdoppeln bis 2h)
                old_cd = self._cooldown
                self._cooldown = min(self._cooldown * 2, self._cooldown_max)
                logger.warning(f"Rate-Limit bei {vid} → Cooldown {old_cd}s → {self._cooldown}s")

                # Bei Maximum (2h) erreicht → harte Pause wie User
                if self._cooldown >= self._cooldown_max:
                    if not job_service.is_paused():
                        await job_service.pause_queue("rate_limit")
                        self._cooldown = self._cooldown_base  # Reset für nächsten Start
                        logger.warning(f"Cooldown-Maximum ({self._cooldown_max}s) erreicht → Queue pausiert")

            elif (is_throttle or is_temporary) and retry_count >= max_retries:
                # Retries aufgebraucht → parken statt permanent error
                await db.execute(
                    "UPDATE jobs SET status='parked', error_message=? WHERE id=?",
                    (f"Geparkt nach {max_retries} Retries: {err[:200]}", job_id)
                )
                await self._ws_broadcast({
                    "job_id": job_id, "queue_id": job_id, "video_id": vid, "status": "parked",
                    "progress": 0, "stage": "parked", "stage_label": f"Geparkt (Retries erschöpft)",
                })
                await job_service.notify(await job_service.get(job_id))
                logger.warning(f"[PARKED] {vid}: {max_retries} Retries erschöpft – geparkt")
            else:
                try:
                    await job_service.fail(job_id, err[:200])
                except Exception:
                    pass
                await self._ws_broadcast({
                    "job_id": job_id, "queue_id": job_id, "video_id": vid, "status": "error",
                    "progress": 0, "stage": "error", "stage_label": f"Fehler: {err[:80]}",
                    "error": err,
                })
        finally:
            _last_ws_time.pop(job_id, None)

    async def _resolve(self, url: str) -> dict:
        def _r():
            yt = YouTube(url)
            chapters = []
            try:
                for ch in yt.chapters:
                    chapters.append({
                        "title": ch.title,
                        "start_time": ch.start_seconds,
                        "end_time": ch.start_seconds + ch.duration,
                    })
            except Exception:
                pass
            # Video-Typ aus InnerTube videoDetails
            video_type = "video"
            try:
                details = yt.vid_info.get("videoDetails", {})
                if details.get("isLive"):
                    video_type = "live"
                elif details.get("isLiveContent") or details.get("isPostLiveDvr"):
                    video_type = "live"
                elif yt.length and yt.length <= 60:
                    video_type = "short"
            except Exception:
                pass
            return {
                "title": yt.title, "channel_name": yt.author, "channel_id": yt.channel_id,
                "description": yt.description, "duration": yt.length,
                "upload_date": str(yt.publish_date) if yt.publish_date else None,
                "view_count": yt.views, "tags": sanitize_tags(yt.keywords or []),
                "thumbnail_url": yt.thumbnail_url, "stream_count": len(yt.streams),
                "chapters": chapters, "video_type": video_type,
            }
        result = await asyncio.get_event_loop().run_in_executor(None, _r)
        return result

    async def _download(self, job_id: int, vid: str, url: str, opts: dict, meta: dict):
        quality = opts.get("quality", DEFAULT_QUALITY)
        fmt = opts.get("format", DEFAULT_FORMAT)
        merge = opts.get("merge_audio", True)
        req_itag = opts.get("itag")
        req_audio_itag = opts.get("audio_itag")
        is_audio_only = opts.get("audio_only", False) or quality == "audio_only"

        vdir = VIDEOS_DIR / vid
        vdir.mkdir(parents=True, exist_ok=True)
        dl = {"phase": "audio" if is_audio_only else "video", "done": 0, "total": 0}

        def _on_progress(stream, chunk, remaining):
            total = stream.filesize
            if total <= 0:
                return
            done = total - remaining
            dl["done"] = done
            dl["total"] = total
            pct = done / total

            if dl["phase"] == "video":
                overall = 0.05 + pct * 0.55
            elif is_audio_only:
                overall = 0.05 + pct * 0.85
            else:
                overall = 0.60 + pct * 0.30

            now_t = time.time()
            if now_t - _last_ws_time.get(job_id, 0) < WS_THROTTLE:
                return
            _last_ws_time[job_id] = now_t

            mb_d = done / 1048576
            mb_t = total / 1048576
            phase_label = "Video" if dl["phase"] == "video" else "Audio"
            self._ws_broadcast_sync({
                "job_id": job_id, "queue_id": job_id, "video_id": vid, "status": "active",
                "progress": round(overall, 3),
                "stage": f"downloading_{dl['phase']}",
                "stage_label": f"{phase_label}: {mb_d:.1f}/{mb_t:.1f} MB ({pct*100:.0f}%)",
                "bytes_done": done, "bytes_total": total,
            })

        def _do():
            yt = YouTube(url, on_progress_callback=_on_progress)
            vs = None
            aus = None
            adaptive = False

            if is_audio_only:
                # Audio-only: spezifischer Audio-itag oder best
                if req_audio_itag:
                    vs = yt.streams.get_by_itag(req_audio_itag)
                else:
                    vs = yt.streams.get_audio_only()
            elif req_itag:
                vs = yt.streams.get_by_itag(req_itag)
                # Wenn Video-only Stream → Audio dazu
                if vs and not vs.is_progressive:
                    adaptive = True
                    if req_audio_itag:
                        aus = yt.streams.get_by_itag(req_audio_itag)
                    elif merge:
                        aus = yt.streams.get_audio_only()
            else:
                vs = self._pick_progressive(yt, quality, fmt)
                if merge and quality in ("best", "1080p", "1440p", "2160p"):
                    av = self._pick_adaptive_video(yt, quality)
                    if av:
                        p_res = self._res_num(vs)
                        a_res = self._res_num(av)
                        if a_res > p_res:
                            vs = av
                            aus = yt.streams.get_audio_only()
                            adaptive = True
                if not vs:
                    vs = yt.streams.get_highest_resolution()
            if not vs:
                raise ValueError("Kein passender Stream")

            dl["phase"] = "audio" if is_audio_only else "video"
            suffix = vs.subtype or ("m4a" if is_audio_only else "mp4")
            vf = f"{'audio' if is_audio_only else 'video'}_tmp.{suffix}"
            vpath = vs.download(output_path=str(vdir), filename=vf)

            apath = None
            if adaptive and aus:
                dl["phase"] = "audio"
                dl["done"] = 0
                dl["total"] = 0
                af = f"audio_tmp.{aus.subtype or 'mp4'}"
                apath = aus.download(output_path=str(vdir), filename=af)

            si = {
                "type": vs.type, "itag": vs.itag, "mime": vs.mime_type,
                "quality": getattr(vs, "resolution", None) or getattr(vs, "abr", None),
                "codec": vs.codecs[0] if vs.codecs else None,
            }
            return vpath, apath, adaptive, si

        stage_name = "downloading_audio" if is_audio_only else "downloading_video"
        stage_label = "Audio wird heruntergeladen…" if is_audio_only else "Video wird heruntergeladen…"
        await self._stage(job_id, vid, stage_name, 0.06, stage_label)

        vpath, apath, adaptive, si = await asyncio.get_event_loop().run_in_executor(None, _do)

        final = vpath
        if adaptive and apath:
            duration = meta.get("duration", 0) or 0
            await self._stage(job_id, vid, "merging", 0.90, "FFmpeg: Merge wird vorbereitet…")
            final = await self._ffmpeg_merge(vdir, vpath, apath, duration, job_id, vid)

        fsize = Path(final).stat().st_size
        return final, fsize, si, adaptive

    async def _ffmpeg_merge(self, vdir: Path, vpath: str, apath: str,
                            duration: float = 0, job_id: int = 0, vid: str = "") -> str:
        """FFmpeg Merge mit Live-Fortschritt via stderr-Parsing."""
        out = str(vdir / "video.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-i", vpath, "-i", apath,
            "-c:v", "copy", "-c:a", "aac",
            "-movflags", "+faststart",
            "-progress", "pipe:2",   # Fortschritt auf stderr
            out,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # stderr zeilenweise lesen für time= Fortschritt
        last_ws = 0.0
        merge_started = time.time()
        current_time_us = 0

        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").strip()

            # FFmpeg -progress gibt z.B. "out_time_us=12345678"
            if text.startswith("out_time_us="):
                try:
                    current_time_us = int(text.split("=", 1)[1])
                except (ValueError, IndexError):
                    pass
            # Fallback: klassisches "time=HH:MM:SS.xx" aus stderr
            elif "time=" in text:
                m = re.search(r"time=(\d+):(\d+):(\d+)\.(\d+)", text)
                if m:
                    h, mi, s, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
                    current_time_us = (h * 3600 + mi * 60 + s) * 1_000_000 + ms * 10_000

            # WS-Update (max alle 500ms)
            now_t = time.time()
            if current_time_us > 0 and now_t - last_ws >= 0.5:
                last_ws = now_t
                current_sec = current_time_us / 1_000_000
                elapsed = now_t - merge_started

                if duration > 0:
                    merge_pct = min(current_sec / duration, 1.0)
                    # Merge-Phase liegt bei 0.90–0.96
                    overall = 0.90 + merge_pct * 0.06
                    eta_sec = (elapsed / merge_pct * (1 - merge_pct)) if merge_pct > 0.01 else 0
                    eta_str = f" · ~{int(eta_sec)}s" if eta_sec > 1 else ""
                    label = f"Merge: {current_sec:.0f}/{duration:.0f}s ({merge_pct*100:.0f}%){eta_str}"
                else:
                    overall = 0.93
                    label = f"Merge: {current_sec:.0f}s verarbeitet…"

                await self._stage(job_id, vid, "merging", round(overall, 3), label)

        await proc.wait()
        if proc.returncode != 0:
            # Restliche stderr für Fehler
            raise RuntimeError(f"FFmpeg Fehler (code {proc.returncode})")

        # Temp-Dateien aufräumen
        for f in (vpath, apath):
            try:
                os.remove(f)
            except OSError:
                pass
        return out

    def _pick_progressive(self, yt, quality, fmt):
        if quality == "audio_only":
            return yt.streams.get_audio_only()
        if quality == "best":
            return yt.streams.get_highest_resolution()
        res = {"1080p":"1080p","720p":"720p","480p":"480p","360p":"360p","240p":"240p","144p":"144p"}.get(quality,"720p")
        s = yt.streams.filter(progressive=True, resolution=res, subtype=fmt).first()
        if s: return s
        s = yt.streams.filter(progressive=True, resolution=res).first()
        if s: return s
        return yt.streams.filter(progressive=True).order_by("resolution").desc().first()

    def _pick_adaptive_video(self, yt, quality):
        if quality in ("best","1080p","1440p","2160p"):
            return yt.streams.filter(adaptive=True, type="video").order_by("resolution").desc().first()
        res = {"720p":"720p","480p":"480p","360p":"360p"}.get(quality)
        if res:
            s = yt.streams.filter(adaptive=True, type="video", resolution=res).first()
            if s: return s
        return yt.streams.filter(adaptive=True, type="video").order_by("resolution").desc().first()

    def _res_num(self, s):
        if not s: return 0
        r = getattr(s, "resolution", "0p") or "0p"
        return int(r.replace("p","")) if r.replace("p","").isdigit() else 0

    async def _dl_thumbnail(self, vid: str, url: str) -> Optional[str]:
        import httpx
        tdir = THUMBNAILS_DIR / vid
        tp = tdir / "thumbnail.jpg"
        if tp.exists():
            return str(tp)
        tdir.mkdir(parents=True, exist_ok=True)
        try:
            await rate_limiter.acquire("thumbnail")
            async with httpx.AsyncClient() as c:
                r = await c.get(url, follow_redirects=True, timeout=15)
                r.raise_for_status()
                tp.write_bytes(r.content)
                rate_limiter.success("thumbnail")
                return str(tp)
        except Exception as e:
            rate_limiter.error("thumbnail", str(e)[:200])
            logger.warning(f"Thumb fail {vid}: {e}")
            return None

    async def download_subtitles(self, video_id: str, lang: str = "de") -> dict:
        """Untertitel für ein Video herunterladen.
        Findet sowohl manuelle ('de') als auch auto-generierte ('a.de') Untertitel.
        Speichert als echtes WebVTT-Format.
        """
        from app.config import SUBTITLES_DIR

        sdir = SUBTITLES_DIR / video_id
        sdir.mkdir(parents=True, exist_ok=True)

        await rate_limiter.acquire("pytubefix")

        def _dl():
            yt = YouTube(f"https://www.youtube.com/watch?v={video_id}")
            downloaded = []

            # Alle verfügbaren Captions loggen
            all_codes = [f"{cap.code} ({cap.name})" for cap in yt.captions]
            logger.info(f"[SUBS] {video_id}: Verfügbare Captions: {', '.join(all_codes) or 'keine'}")

            for cap in yt.captions:
                code = cap.code
                # Match: exakt 'de', startswith 'de-', oder auto-generiert 'a.de'
                matches = (
                    lang == "all"
                    or code == lang
                    or code.startswith(f"{lang}-")
                    or code == f"a.{lang}"
                    or code.startswith(f"a.{lang}-")
                )
                if not matches:
                    continue

                vtt_path = sdir / f"{code}.vtt"
                try:
                    # SRT generieren und zu VTT konvertieren
                    srt_text = cap.generate_srt_captions()
                    vtt_text = _srt_to_vtt(srt_text)
                    vtt_path.write_text(vtt_text, encoding="utf-8")
                    label = cap.name or code
                    downloaded.append({"code": code, "name": label, "path": str(vtt_path)})
                    logger.info(f"[SUBS] {video_id}: {code} ({cap.name}) heruntergeladen")
                except Exception as e:
                    logger.warning(f"Subtitle fail {video_id}/{code}: {e}")
            return downloaded

        try:
            result = await asyncio.get_event_loop().run_in_executor(None, _dl)
            rate_limiter.success("pytubefix")
            return {"video_id": video_id, "subtitles": result, "count": len(result)}
        except Exception as e:
            rate_limiter.error("pytubefix", str(e))
            raise ValueError(f"Untertitel-Download fehlgeschlagen: {e}")

    async def extract_audio(self, video_id: str, format: str = "mp3") -> dict:
        """Audio aus heruntergeladenem Video extrahieren."""
        from app.config import AUDIO_DIR

        video = await db.fetch_one("SELECT file_path FROM videos WHERE id = ? AND status = 'ready'", (video_id,))
        if not video or not video["file_path"]:
            raise ValueError(f"Video {video_id} nicht gefunden oder nicht bereit")

        src = Path(video["file_path"])
        if not src.exists():
            raise ValueError(f"Video-Datei nicht gefunden: {src}")

        adir = AUDIO_DIR / video_id
        adir.mkdir(parents=True, exist_ok=True)

        ext = {"mp3": "mp3", "m4a": "m4a", "flac": "flac", "ogg": "ogg"}.get(format, "mp3")
        codec_map = {"mp3": "libmp3lame", "m4a": "aac", "flac": "flac", "ogg": "libvorbis"}
        codec = codec_map.get(format, "libmp3lame")
        out_path = adir / f"audio.{ext}"

        cmd = ["ffmpeg", "-y", "-i", str(src), "-vn", "-c:a", codec]
        if format == "mp3":
            cmd.extend(["-q:a", "2"])
        cmd.append(str(out_path))

        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg Fehler: {stderr.decode()[-200:]}")

        fsize = out_path.stat().st_size
        logger.info(f"Audio extrahiert: {video_id} → {ext} ({fsize / 1024 / 1024:.1f} MB)")
        return {
            "video_id": video_id,
            "format": format,
            "path": str(out_path),
            "file_size": fsize,
        }

    # --- Queue CRUD (über jobs-Tabelle) ---

    async def get_queue(self) -> dict:
        items = await db.fetch_all(
            "SELECT * FROM jobs WHERE type='download' ORDER BY status='active' DESC, priority DESC, created_at ASC"
        )
        sts = {"active":0,"queued":0,"done":0,"error":0,"cancelled":0,"retry_wait":0}
        result = []
        for i in items:
            s = i["status"]
            if s in sts: sts[s] += 1
            item = dict(i)
            meta = json.loads(item.get("metadata") or "{}")
            vid = meta.get("video_id")
            # Kompatibilität: queue_id = job id
            item["queue_id"] = item["id"]
            item["video_id"] = vid
            item["url"] = meta.get("url", "")
            item["download_options"] = json.dumps(meta.get("download_options", {}))
            # Titel anreichern falls noch generisch
            if vid and item.get("title", "").startswith("Download:"):
                row = await db.fetch_one("SELECT title FROM videos WHERE id = ?", (vid,))
                if not row:
                    row = await db.fetch_one("SELECT title FROM rss_entries WHERE video_id = ?", (vid,))
                if row:
                    item["title"] = row["title"]
            result.append(item)
        return {
            "queue": result,
            "active_count": sts["active"],
            "queued_count": sts["queued"],
            "completed_count": sts["done"],
            "error_count": sts["error"],
            "cancelled_count": sts["cancelled"],
            "retry_wait_count": sts["retry_wait"],
            "failed_count": sts["error"] + sts["cancelled"],
        }

    async def cancel_download(self, job_id: int):
        await db.execute(
            "UPDATE jobs SET status='cancelled' WHERE id=? AND status IN ('queued','active','retry_wait')", (job_id,)
        )
        job = await job_service.get(job_id)
        if job:
            await job_service.notify(job)
        vid = ""
        if job and job.get("metadata"):
            vid = job["metadata"].get("video_id", "")
        await self._ws_broadcast({"job_id": job_id, "queue_id": job_id, "video_id": vid,
                                   "status": "cancelled", "stage": "cancelled", "stage_label": "Abgebrochen"})

    async def retry_download(self, job_id: int):
        row = await db.fetch_one("SELECT metadata FROM jobs WHERE id=?", (job_id,))
        if row:
            meta = json.loads(row["metadata"] or "{}")
            meta["retry_count"] = 0
            meta.pop("retry_after", None)
            await db.execute(
                "UPDATE jobs SET status='queued', error_message=NULL, progress=0, metadata=? WHERE id=? AND status IN ('error','cancelled','retry_wait')",
                (json.dumps(meta), job_id)
            )

    async def retry_all_failed(self) -> int:
        """Alle fehlgeschlagenen Download-Jobs zurück in Queue."""
        rows = await db.fetch_all(
            "SELECT id, metadata FROM jobs WHERE type='download' AND status IN ('error','cancelled','retry_wait')"
        )
        count = 0
        for row in rows:
            meta = json.loads(row["metadata"] or "{}")
            meta["retry_count"] = 0
            meta.pop("retry_after", None)
            await db.execute(
                "UPDATE jobs SET status='queued', error_message=NULL, progress=0, metadata=? WHERE id=?",
                (json.dumps(meta), row["id"])
            )
            count += 1
        return count

    async def retry_with_delay(self, job_id: int, delay_minutes: int = 5):
        """Download mit Verzögerung erneut versuchen."""
        retry_after = future_sqlite(minutes=delay_minutes)
        row = await db.fetch_one("SELECT metadata FROM jobs WHERE id=?", (job_id,))
        if row:
            meta = json.loads(row["metadata"] or "{}")
            meta["retry_count"] = 0
            meta["retry_after"] = retry_after
            await db.execute(
                "UPDATE jobs SET status='retry_wait', error_message=NULL, progress=0, metadata=? WHERE id=?",
                (json.dumps(meta), job_id)
            )

    async def clear_completed(self):
        await db.execute("DELETE FROM jobs WHERE type='download' AND status IN ('done','cancelled')")


download_service = DownloadService()

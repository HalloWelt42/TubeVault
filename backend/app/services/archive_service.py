"""
TubeVault -  Archive Service v1.1.0
Externes Archiv-Management mit Mount-Erkennung und Background-Scan
© HalloWelt42 -  Private Nutzung

Konzept:
- Externe Platten (USB, NAS) als Archive registrieren
- Background-Scanner durchsucht Archive nach YouTube-Videos
- Video-ID wird aus Dateinamen extrahiert (z.B. "Video Title [dQw4w9WgXcQ].mp4")
- Mount-Watcher prüft periodisch ob Archiv erreichbar ist
- Metadaten + Thumbnails bleiben IMMER lokal auf der SSD
- Videodateien können extern liegen → Offline-Hinweis wenn nicht erreichbar

storage_type Werte:
- 'local'    → Datei liegt auf der internen SSD (/app/data/videos/)
- 'archive'  → Datei liegt NUR im externen Archiv
- 'both'     → Lokal + im Archiv vorhanden (Backup-Szenario)
"""

import asyncio
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.database import db
from app.services.job_service import job_service
from app.utils.file_utils import now_sqlite

logger = logging.getLogger(__name__)

# YouTube Video-ID Pattern: 11 Zeichen [a-zA-Z0-9_-]
# Typische Dateinamen: "Title [VIDEO_ID].mp4" oder "VIDEO_ID.mp4"
YT_ID_PATTERNS = [
    re.compile(r'\[([a-zA-Z0-9_-]{11})\]'),          # "Title [dQw4w9WgXcQ].mp4"
    re.compile(r'\(([a-zA-Z0-9_-]{11})\)'),           # "Title (dQw4w9WgXcQ).mp4"
    re.compile(r'[-_]([a-zA-Z0-9_-]{11})\.\w+$'),     # "Title-dQw4w9WgXcQ.mp4"
    re.compile(r'^([a-zA-Z0-9_-]{11})\.\w+$'),        # "dQw4w9WgXcQ.mp4"
]

DEFAULT_PATTERNS = ["*.mp4", "*.mkv", "*.webm", "*.avi", "*.mov"]


class ArchiveService:
    """Verwaltet externe Video-Archive."""

    def __init__(self):
        self._mount_watcher_task: Optional[asyncio.Task] = None
        self._scanner_task: Optional[asyncio.Task] = None
        self._mount_status: dict[int, bool] = {}  # archive_id → is_mounted

    # === Lifecycle ===

    async def start(self):
        """Background-Tasks starten."""
        self._mount_watcher_task = asyncio.create_task(self._mount_watcher_loop())
        logger.info("Archive Mount-Watcher gestartet")

    async def stop(self):
        """Background-Tasks stoppen."""
        for task in (self._mount_watcher_task, self._scanner_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        logger.info("Archive Service gestoppt")

    # === Archive CRUD ===

    async def add_archive(self, name: str, mount_path: str, auto_scan: bool = True,
                          scan_pattern: str = None) -> dict:
        """Neues Archiv registrieren."""
        mount_path = mount_path.rstrip("/")
        pattern = scan_pattern or ",".join(DEFAULT_PATTERNS)

        cursor = await db.execute(
            """INSERT INTO archives (name, mount_path, auto_scan, scan_pattern)
               VALUES (?, ?, ?, ?)""",
            (name, mount_path, auto_scan, pattern)
        )
        archive_id = cursor.lastrowid

        # Sofort Mount-Status prüfen
        is_mounted = self._check_mount(mount_path)
        self._mount_status[archive_id] = is_mounted

        if is_mounted:
            await db.execute(
                "UPDATE archives SET last_seen = ? WHERE id = ?",
                (now_sqlite(), archive_id)
            )

        logger.info(f"Archiv registriert: '{name}' → {mount_path} (mounted={is_mounted})")

        result = await db.fetch_one("SELECT * FROM archives WHERE id = ?", (archive_id,))
        return {**dict(result), "is_mounted": is_mounted}

    async def remove_archive(self, archive_id: int):
        """Archiv entfernen. Videos mit storage_type='archive' werden zu 'offline'."""
        # Videos die NUR in diesem Archiv sind → status auf 'archived_offline'
        await db.execute(
            """UPDATE videos SET status = 'archived_offline'
               WHERE id IN (
                   SELECT video_id FROM video_archives WHERE archive_id = ?
               ) AND storage_type = 'archive'""",
            (archive_id,)
        )
        await db.execute("DELETE FROM video_archives WHERE archive_id = ?", (archive_id,))
        await db.execute("DELETE FROM archives WHERE id = ?", (archive_id,))
        self._mount_status.pop(archive_id, None)

    async def get_archives(self) -> list[dict]:
        """Alle Archive mit aktuellem Mount-Status."""
        rows = await db.fetch_all("SELECT * FROM archives ORDER BY name")
        result = []
        for r in rows:
            d = dict(r)
            d["is_mounted"] = self._mount_status.get(d["id"], self._check_mount(d["mount_path"]))
            result.append(d)
        return result

    async def get_archive(self, archive_id: int) -> Optional[dict]:
        row = await db.fetch_one("SELECT * FROM archives WHERE id = ?", (archive_id,))
        if not row:
            return None
        d = dict(row)
        d["is_mounted"] = self._mount_status.get(d["id"], self._check_mount(d["mount_path"]))
        return d

    # === Mount-Erkennung ===

    def _check_mount(self, mount_path: str) -> bool:
        """Prüft ob ein Pfad gemountet und lesbar ist."""
        p = Path(mount_path)
        try:
            return p.exists() and p.is_dir() and os.access(str(p), os.R_OK)
        except (OSError, PermissionError):
            return False

    async def check_all_mounts(self) -> dict[int, bool]:
        """Alle Archive auf Erreichbarkeit prüfen."""
        archives = await db.fetch_all("SELECT id, mount_path FROM archives WHERE enabled = 1")
        now = now_sqlite()
        changed = {}

        for a in archives:
            aid = a["id"]
            was_mounted = self._mount_status.get(aid)
            is_mounted = self._check_mount(a["mount_path"])
            self._mount_status[aid] = is_mounted

            if was_mounted != is_mounted:
                changed[aid] = is_mounted
                if is_mounted:
                    await db.execute(
                        "UPDATE archives SET last_seen = ? WHERE id = ?", (now, aid)
                    )
                    logger.info(f"Archiv #{aid} ist jetzt ONLINE: {a['mount_path']}")
                else:
                    logger.warning(f"Archiv #{aid} ist jetzt OFFLINE: {a['mount_path']}")

        return changed

    def is_archive_mounted(self, archive_id: int) -> bool:
        return self._mount_status.get(archive_id, False)

    # === Video-Datei Zugriff ===

    async def resolve_video_path(self, video_id: str) -> dict:
        """Prüft wo ein Video liegt und ob es erreichbar ist.

        Returns:
            {
                "available": bool,
                "path": str or None,
                "storage_type": "local"|"archive"|"both",
                "archive_name": str or None,
                "archive_mounted": bool,
            }
        """
        video = await db.fetch_one(
            "SELECT file_path, storage_type, archive_id FROM videos WHERE id = ?",
            (video_id,)
        )
        if not video:
            return {"available": False, "path": None, "storage_type": None}

        storage = video["storage_type"] or "local"

        # Lokale Datei vorhanden?
        if storage in ("local", "both") and video["file_path"]:
            if Path(video["file_path"]).exists():
                return {
                    "available": True,
                    "path": video["file_path"],
                    "storage_type": storage,
                    "archive_name": None,
                    "archive_mounted": True,
                }

        # Archiv-Datei prüfen
        archive_entries = await db.fetch_all(
            """SELECT va.file_path, va.archive_id, a.name, a.mount_path
               FROM video_archives va JOIN archives a ON va.archive_id = a.id
               WHERE va.video_id = ?""",
            (video_id,)
        )

        for entry in archive_entries:
            mounted = self._mount_status.get(entry["archive_id"],
                                              self._check_mount(entry["mount_path"]))
            if mounted:
                full_path = entry["file_path"]
                if Path(full_path).exists():
                    return {
                        "available": True,
                        "path": full_path,
                        "storage_type": "archive",
                        "archive_name": entry["name"],
                        "archive_mounted": True,
                    }

        # Archiv bekannt aber nicht erreichbar
        if archive_entries:
            return {
                "available": False,
                "path": None,
                "storage_type": "archive",
                "archive_name": archive_entries[0]["name"],
                "archive_mounted": False,
            }

        return {"available": False, "path": None, "storage_type": storage}

    # === Background-Scanner ===

    async def scan_archive(self, archive_id: int) -> dict:
        """Archiv nach YouTube-Videos durchsuchen."""
        archive = await self.get_archive(archive_id)
        if not archive:
            raise ValueError(f"Archiv #{archive_id} nicht gefunden")
        if not archive["is_mounted"]:
            raise ValueError(f"Archiv '{archive['name']}' ist nicht erreichbar")

        job = await job_service.create(
            job_type="archive_scan",
            title=f"Archiv-Scan: {archive['name']}",
            description=f"Durchsuche {archive['mount_path']}",
        )
        await job_service.start(job["id"])

        mount = Path(archive["mount_path"])
        patterns = (archive.get("scan_pattern") or "*.mp4,*.mkv,*.webm").split(",")

        # Dateien sammeln
        files = []
        for pattern in patterns:
            pattern = pattern.strip()
            files.extend(mount.rglob(pattern))

        found = 0
        new_videos = 0
        linked = 0
        ffprobe_found = 0
        total = len(files)

        logger.info(f"Archiv-Scan: {total} Dateien in '{archive['name']}'")

        for i, fpath in enumerate(files):
            try:
                # Step 1: ID aus Dateiname
                video_id = self._extract_video_id(fpath)

                # Step 2: Fallback FFprobe Metadaten
                if not video_id:
                    video_id = await self._extract_video_id_ffprobe(fpath)
                    if video_id:
                        ffprobe_found += 1

                if not video_id:
                    continue

                found += 1
                file_size = fpath.stat().st_size

                # Bereits in video_archives?
                existing_link = await db.fetch_one(
                    "SELECT id FROM video_archives WHERE video_id = ? AND archive_id = ?",
                    (video_id, archive_id)
                )
                if existing_link:
                    continue

                # Video in DB?
                video = await db.fetch_one("SELECT id FROM videos WHERE id = ?", (video_id,))

                if not video:
                    # Neues Video nur aus Dateiname → Minimal-Eintrag
                    title = fpath.stem
                    # Video-ID aus Titel entfernen
                    for p in YT_ID_PATTERNS:
                        title = p.sub("", title).strip(" -_")

                    await db.execute(
                        """INSERT OR IGNORE INTO videos
                           (id, title, status, storage_type, archive_id, file_path, file_size,
                            created_at, updated_at)
                           VALUES (?, ?, 'archived', 'archive', ?, ?, ?, datetime('now'), datetime('now'))""",
                        (video_id, title or video_id, archive_id, str(fpath), file_size)
                    )
                    new_videos += 1

                # Link erstellen
                await db.execute(
                    """INSERT OR IGNORE INTO video_archives
                       (video_id, archive_id, file_path, file_size)
                       VALUES (?, ?, ?, ?)""",
                    (video_id, archive_id, str(fpath), file_size)
                )
                linked += 1

            except Exception as e:
                logger.debug(f"Scan skip {fpath.name}: {e}")

            if i % 100 == 0 and total > 0:
                await job_service.progress(
                    job["id"], (i + 1) / total,
                    f"{found} erkannt ({ffprobe_found} via FFprobe), {new_videos} neu, {linked} verlinkt"
                )

        # Statistik updaten
        total_size = sum(f.stat().st_size for f in files if f.exists())
        await db.execute(
            "UPDATE archives SET last_scan = ?, total_videos = ?, total_size = ? WHERE id = ?",
            (now_sqlite(), found, total_size, archive_id)
        )

        result_msg = (f"{found} Videos erkannt ({ffprobe_found} via FFprobe), "
                      f"{new_videos} neu hinzugefügt, {linked} verlinkt")
        await job_service.complete(job["id"], result_msg)
        logger.info(f"Archiv-Scan abgeschlossen: {result_msg}")

        return {"found": found, "new_videos": new_videos, "linked": linked, "total_files": total}

    def _extract_video_id(self, filepath: Path) -> Optional[str]:
        """YouTube Video-ID aus Dateinamen extrahieren.
        Fallback: FFprobe Metadaten durchsuchen."""
        name = filepath.name
        for pattern in YT_ID_PATTERNS:
            m = pattern.search(name)
            if m:
                return m.group(1)
        return None

    async def _extract_video_id_ffprobe(self, filepath: Path) -> Optional[str]:
        """Video-ID per FFprobe aus Datei-Metadaten extrahieren.
        yt-dlp schreibt die YouTube-URL oft in Comment/PURL/Description."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", str(filepath),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != 0:
                return None

            import json
            data = json.loads(stdout.decode())
            tags = data.get("format", {}).get("tags", {})

            # Durchsuche bekannte Tag-Felder
            for key in ("comment", "COMMENT", "purl", "PURL",
                        "description", "DESCRIPTION", "synopsis",
                        "url", "URL"):
                val = tags.get(key, "")
                if not val:
                    continue
                # YouTube-URL oder Video-ID suchen
                for pattern in YT_ID_PATTERNS:
                    m = pattern.search(val)
                    if m:
                        return m.group(1)
                # Direkte URL-Suche
                import re
                url_match = re.search(
                    r'(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})', val
                )
                if url_match:
                    return url_match.group(1)

            return None
        except Exception:
            return None

    # === Duplikat-Prüfung ===

    async def check_duplicate(self, video_id: str) -> Optional[dict]:
        """Prüft ob ein Video bereits in irgendeinem Archiv existiert.

        Returns None wenn nicht gefunden, sonst dict mit Archiv-Info.
        """
        row = await db.fetch_one(
            """SELECT va.*, a.name as archive_name, a.mount_path
               FROM video_archives va JOIN archives a ON va.archive_id = a.id
               WHERE va.video_id = ?
               LIMIT 1""",
            (video_id,)
        )
        if not row:
            return None
        d = dict(row)
        d["is_mounted"] = self._mount_status.get(
            d["archive_id"], self._check_mount(d["mount_path"])
        )
        return d

    # === Background-Loops ===

    async def _mount_watcher_loop(self):
        """Periodisch alle Mounts prüfen."""
        while True:
            try:
                interval = await db.fetch_val(
                    "SELECT value FROM settings WHERE key = 'archive.mount_check_interval'"
                )
                interval = int(interval or 30)

                changed = await self.check_all_mounts()

                # Bei neu erkannten Mounts: Auto-Scan starten
                for aid, mounted in changed.items():
                    if mounted:
                        archive = await self.get_archive(aid)
                        if archive and archive.get("auto_scan"):
                            logger.info(f"Auto-Scan für wiedererkanntes Archiv: {archive['name']}")
                            asyncio.create_task(self.scan_archive(aid))

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Mount-Watcher Fehler: {e}")
                await asyncio.sleep(30)


# Singleton
archive_service = ArchiveService()

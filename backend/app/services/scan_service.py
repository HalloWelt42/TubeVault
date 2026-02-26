"""
TubeVault -  Scan Service v1.5.61
Inkrementeller Datei-Scan → Identifizieren → Registrieren (ins Vault kopieren).
Separate scan_index.db für persistenten Index.
© HalloWelt42 -  Private Nutzung
"""

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from app.config import DATA_DIR, VIDEOS_DIR, THUMBNAILS_DIR
from app.database import db
from app.database_scan import scan_db
from app.utils.file_utils import now_sqlite
from app.utils.tag_utils import sanitize_tags
from app.utils.thumbnail_utils import (
    download_yt_thumbnail, generate_ffmpeg_thumbnail,
    find_companion_thumbnail, YT_THUMB_QUALITIES
)

logger = logging.getLogger(__name__)

# ── Konstanten ──
DISCOVER_BATCH = 100
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v", ".flv", ".wmv", ".ts"}

# YouTube-ID Patterns (konservativ -  lieber keine ID als falsche)
YT_ID_PATTERNS = [
    re.compile(r'\[([a-zA-Z0-9_-]{11})\]'),        # [dQw4w9WgXcQ]
    re.compile(r'\(([a-zA-Z0-9_-]{11})\)'),         # (dQw4w9WgXcQ)
]


class ScanService:
    """Inkrementeller Scan mit persistentem Index + Vault-Registration."""

    def __init__(self):
        self._scanning = False
        self._should_stop = False
        self._task: asyncio.Task | None = None
        self._progress = {
            "phase": "idle",
            "discovered": 0,
            "total_files": 0,
            "current_batch": 0,
            "total_batches": 0,
        }

    # ═══════════════════════════════════════════════════════════
    #  Phase 1: DISCOVERY
    # ═══════════════════════════════════════════════════════════

    async def start_discover(self, path: str, youtube_archive: bool = True) -> dict:
        """Scan starten als Background-Task. Bereits bekannte Pfade → SKIP."""
        if self._scanning:
            return {"status": "already_running", "progress": self._progress}

        scan_path = Path(path)
        if not scan_path.exists() or not scan_path.is_dir():
            return {"status": "error", "message": f"Verzeichnis nicht gefunden: {path}"}

        # State merken
        await scan_db.execute(
            "INSERT OR REPLACE INTO scan_state (key, value) VALUES (?, ?)",
            ("scan_path", path))
        await scan_db.execute(
            "INSERT OR REPLACE INTO scan_state (key, value) VALUES (?, ?)",
            ("youtube_archive", "1" if youtube_archive else "0"))

        self._scanning = True
        self._should_stop = False
        self._task = asyncio.create_task(self._discover_loop(scan_path, youtube_archive))
        return {"status": "started", "path": path}

    async def stop_discover(self) -> dict:
        if not self._scanning:
            return {"status": "not_running"}
        self._should_stop = True
        return {"status": "stopping"}

    async def _discover_loop(self, scan_path: Path, youtube_archive: bool):
        """Background: Dateien in Batches entdecken + YouTube-ID extrahieren."""
        try:
            self._progress["phase"] = "discovering"
            now = now_sqlite()

            # Bekannte Pfade für Dedup
            known_rows = await scan_db.fetch_all("SELECT path FROM scan_index")
            known_paths = {r["path"] for r in known_rows}

            # Auch bereits in videos-Tabelle registrierte Pfade
            vid_rows = await db.fetch_all(
                "SELECT file_path FROM videos WHERE file_path IS NOT NULL")
            vault_paths = {r["file_path"] for r in vid_rows}

            # Alle YouTube-IDs die bereits im Vault sind
            vid_id_rows = await db.fetch_all(
                "SELECT id FROM videos WHERE source IN ('youtube', 'imported')")
            vault_ids = {r["id"] for r in vid_id_rows}

            all_files = sorted(
                f for f in scan_path.rglob("*")
                if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS
            )
            self._progress["total_files"] = len(all_files)
            self._progress["total_batches"] = (len(all_files) + DISCOVER_BATCH - 1) // DISCOVER_BATCH

            new_count = 0
            batch_num = 0
            batch = []

            for f in all_files:
                if self._should_stop:
                    break

                path_str = str(f)
                if path_str in known_paths:
                    continue

                # Ordner
                rel = f.relative_to(scan_path)
                folder = str(rel.parent) if rel.parent != Path(".") else "(Root)"
                title = f.stem
                channel_name = folder if youtube_archive and folder != "(Root)" else None

                # YouTube-ID extrahieren
                yt_id = self._extract_youtube_id(f.name)
                status = "identified" if yt_id else "discovered"

                # Duplikat-Check: ID schon im Vault?
                if yt_id and yt_id in vault_ids:
                    status = "duplicate"

                try:
                    file_size = f.stat().st_size
                except OSError:
                    file_size = 0

                # Companion-Dateien (schneller Check, kein Parsing)
                base = f.with_suffix("")
                has_nfo = any(base.with_suffix(e).exists() for e in [".nfo", ".xml"])
                has_thumb = any(
                    Path(str(base) + s + e).exists()
                    for e in [".jpg", ".jpeg", ".png", ".webp"]
                    for s in ["", "-thumb", "-poster", "_thumb"]
                )
                has_subs = any(
                    Path(str(base) + s).exists()
                    for s in [".srt", ".vtt", ".de.srt", ".en.srt"]
                )

                batch.append((
                    path_str, f.name, folder, title, channel_name,
                    status, yt_id, file_size,
                    has_nfo, has_thumb, has_subs, now,
                ))
                new_count += 1

                if len(batch) >= DISCOVER_BATCH:
                    batch_num += 1
                    await self._insert_batch(batch)
                    batch = []
                    self._progress["discovered"] = new_count
                    self._progress["current_batch"] = batch_num
                    await asyncio.sleep(0.05)

            if batch:
                batch_num += 1
                await self._insert_batch(batch)

            self._progress["discovered"] = new_count
            self._progress["current_batch"] = batch_num
            self._progress["phase"] = "done"
            logger.info(f"[SCAN] Discovery fertig: {new_count} neue, {len(all_files)} gesamt")

        except Exception as e:
            logger.error(f"[SCAN] Discovery-Fehler: {e}", exc_info=True)
            self._progress["phase"] = "error"
        finally:
            self._scanning = False
            self._should_stop = False

    async def _insert_batch(self, batch: list):
        await scan_db.execute_many(
            """INSERT OR IGNORE INTO scan_index
               (path, filename, folder, title, channel_name, status,
                youtube_id, file_size, has_nfo, has_thumb, has_subs, scanned_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            batch)

    # ═══════════════════════════════════════════════════════════
    #  Phase 2: REGISTRIEREN (ins Vault kopieren)
    # ═══════════════════════════════════════════════════════════

    async def register_items(self, ids: list[int]) -> dict:
        """Ausgewählte Einträge ins Vault registrieren.
        Kopiert Datei → VIDEOS_DIR, erstellt Thumbnail, INSERT in videos-Tabelle.
        """
        if not ids:
            return {"status": "error", "message": "Keine IDs"}

        placeholders = ",".join("?" * len(ids))
        rows = await scan_db.fetch_all(
            f"""SELECT * FROM scan_index
                WHERE id IN ({placeholders})
                AND status IN ('identified', 'discovered')""",
            ids)

        registered = 0
        errors = 0

        for row in rows:
            row = dict(row)
            try:
                result = await self._register_one(row)
                if result.get("status") == "ok":
                    registered += 1
                elif result.get("status") == "duplicate":
                    await scan_db.execute(
                        "UPDATE scan_index SET status = 'duplicate' WHERE id = ?",
                        (row["id"],))
            except Exception as e:
                errors += 1
                await scan_db.execute(
                    "UPDATE scan_index SET status = 'error', error_msg = ? WHERE id = ?",
                    (str(e)[:500], row["id"]))
                logger.error(f"[SCAN] Register-Fehler {row['path']}: {e}")

        return {"status": "completed", "registered": registered, "errors": errors}

    async def register_all_identified(self) -> dict:
        """Alle Einträge mit YouTube-ID auf einmal registrieren."""
        rows = await scan_db.fetch_all(
            "SELECT id FROM scan_index WHERE status = 'identified'")
        ids = [r["id"] for r in rows]
        if not ids:
            return {"status": "idle", "message": "Keine identifizierten Einträge"}
        return await self.register_items(ids)

    async def _register_one(self, row: dict) -> dict:
        """Einzelnes Video registrieren: Kopieren → ffprobe → Thumbnail → DB."""
        src_path = Path(row["path"])
        if not src_path.exists():
            raise FileNotFoundError(f"Quelldatei nicht gefunden: {row['path']}")

        yt_id = row.get("youtube_id")
        if not yt_id:
            import uuid
            yt_id = f"local_{uuid.uuid4().hex[:10]}"

        # Duplikat-Check in videos-Tabelle
        existing = await db.fetch_one("SELECT id FROM videos WHERE id = ?", (yt_id,))
        if existing:
            return {"status": "duplicate", "id": yt_id}

        # ── Datei ins Vault kopieren ──
        vault_dir = VIDEOS_DIR / yt_id
        vault_dir.mkdir(parents=True, exist_ok=True)
        dest_name = f"video{src_path.suffix.lower()}"
        dest_path = vault_dir / dest_name

        shutil.copy2(str(src_path), str(dest_path))
        logger.info(f"[SCAN] Kopiert: {src_path.name} → {dest_path}")

        # Verifizieren: Datei existiert + Größe stimmt
        if not dest_path.exists():
            raise IOError(f"Kopie fehlgeschlagen: {dest_path} existiert nicht")
        src_size = src_path.stat().st_size
        dest_size = dest_path.stat().st_size
        if dest_size < src_size * 0.95:  # Toleranz 5% (Metadaten-Unterschiede)
            raise IOError(f"Kopie unvollständig: {dest_size} vs {src_size} Bytes")

        # ── ffprobe ──
        probe = self._ffprobe(dest_path)
        duration = probe.get("duration") if probe else None
        resolution = probe.get("resolution") if probe else None

        if not probe:
            logger.warning(f"[SCAN] ffprobe fehlgeschlagen für {dest_path}, versuche Original…")
            probe = self._ffprobe(src_path)
            duration = probe.get("duration") if probe else None
            resolution = probe.get("resolution") if probe else None

        # ── Thumbnail generieren (Priorität: YT > Companion > ffmpeg) ──
        thumb_path = None

        # 1. YouTube-Thumbnail holen (beste Qualität)
        yt_thumb = await download_yt_thumbnail(yt_id, THUMBNAILS_DIR)
        if yt_thumb:
            thumb_path = str(yt_thumb)

        # 2. Companion-Thumbnail (lokale Datei neben dem Video)
        if not thumb_path:
            comp = find_companion_thumbnail(src_path, yt_id, THUMBNAILS_DIR)
            if comp:
                thumb_path = str(comp)

        # 3. ffmpeg aus Videodatei (letzte Option)
        if not thumb_path:
            ffm = generate_ffmpeg_thumbnail(dest_path, THUMBNAILS_DIR / f"{yt_id}.jpg", duration=duration)
            if ffm:
                thumb_path = str(ffm)

        # ── In videos-Tabelle eintragen ──
        now = now_sqlite()
        title = row.get("match_title") or row.get("title") or src_path.stem
        channel_name = row.get("channel_name")
        file_size = dest_path.stat().st_size
        source = "imported" if row.get("youtube_id") else "local"

        # Video-Typ (Short-Erkennung)
        video_type = "video"
        if resolution:
            try:
                w, h = resolution.split("x")
                if int(h) > int(w) and duration and duration <= 60:
                    video_type = "short"
            except (ValueError, AttributeError):
                pass

        tags = ["#Import"] if source == "imported" else ["#Eigenes Video"]
        if video_type == "short":
            tags.append("#Short")

        await db.execute(
            """INSERT INTO videos
               (id, title, channel_name, duration, download_date,
                thumbnail_path, tags, status, file_path, file_size,
                source, storage_type, import_path, video_type,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'ready', ?, ?, ?, 'local', ?, ?, ?, ?)""",
            (yt_id, title, channel_name, duration, now,
             thumb_path, json.dumps(sanitize_tags(tags)), str(dest_path), file_size,
             source, str(src_path), video_type, now, now))

        # ── Scan-Index aktualisieren ──
        await scan_db.execute(
            """UPDATE scan_index SET
               status = 'registered', imported_at = ?,
               duration = ?, resolution = ?
               WHERE id = ?""",
            (now, duration, resolution, row["id"]))

        logger.info(f"[SCAN] Registriert: {yt_id} ({title})")
        return {"status": "ok", "id": yt_id, "title": title}

    # ═══════════════════════════════════════════════════════════
    #  MANUELLES VERKNÜPFEN (YT-Suche → Link)
    # ═══════════════════════════════════════════════════════════

    async def link_youtube(self, scan_id: int, youtube_id: str,
                           title: str = None, channel: str = None) -> dict:
        """Manuell eine YouTube-ID zuweisen (aus YT-Suche)."""
        # Duplikat-Check
        existing = await db.fetch_one("SELECT id FROM videos WHERE id = ?", (youtube_id,))
        if existing:
            await scan_db.execute(
                "UPDATE scan_index SET status = 'duplicate', youtube_id = ? WHERE id = ?",
                (youtube_id, scan_id))
            return {"status": "duplicate", "message": f"{youtube_id} ist bereits im Vault"}

        await scan_db.execute(
            """UPDATE scan_index SET
               youtube_id = ?, status = 'identified',
               match_title = ?, channel_name = COALESCE(?, channel_name)
               WHERE id = ?""",
            (youtube_id, title or "", channel, scan_id))
        return {"status": "ok", "id": scan_id, "youtube_id": youtube_id}

    # ═══════════════════════════════════════════════════════════
    #  ORIGINAL LÖSCHEN
    # ═══════════════════════════════════════════════════════════

    async def delete_original(self, scan_id: int) -> dict:
        """Original-Datei löschen (alle Status erlaubt)."""
        row = await scan_db.fetch_one(
            "SELECT id, path, status FROM scan_index WHERE id = ?", (scan_id,))
        if not row:
            return {"status": "error", "message": "Eintrag nicht gefunden"}

        src = Path(row["path"])
        if src.exists():
            src.unlink()
            logger.info(f"[SCAN] Original gelöscht: {src}")

            # Companion-Dateien auch löschen
            base = src.with_suffix("")
            for ext in [".nfo", ".xml", ".jpg", ".jpeg", ".png", ".webp",
                        ".srt", ".vtt", ".description", ".txt",
                        "-thumb.jpg", "-poster.jpg", "_thumb.jpg"]:
                comp = Path(str(base) + ext)
                if comp.exists():
                    comp.unlink()
                    logger.info(f"[SCAN] Companion gelöscht: {comp}")

        await scan_db.execute(
            "UPDATE scan_index SET status = 'cleaned' WHERE id = ?", (scan_id,))
        return {"status": "ok", "deleted": str(src)}

    async def delete_originals_batch(self, ids: list[int]) -> dict:
        """Mehrere Originale löschen."""
        deleted = 0
        for sid in ids:
            r = await self.delete_original(sid)
            if r.get("status") == "ok":
                deleted += 1
        return {"status": "completed", "deleted": deleted}

    # ═══════════════════════════════════════════════════════════
    #  THUMBNAIL-VORSCHAU (Frames aus Video)
    # ═══════════════════════════════════════════════════════════

    async def get_preview_frames(self, scan_id: int, count: int = 6) -> list[str]:
        """N Frames aus dem Video extrahieren, als temp JPGs zurückgeben."""
        row = await scan_db.fetch_one(
            "SELECT path, duration FROM scan_index WHERE id = ?", (scan_id,))
        if not row:
            return []

        src = Path(row["path"])
        if not src.exists():
            return []

        # Dauer ermitteln
        dur = row["duration"]
        if not dur:
            probe = self._ffprobe(src)
            dur = probe.get("duration", 60) if probe else 60
            await scan_db.execute(
                "UPDATE scan_index SET duration = ? WHERE id = ?", (dur, scan_id))

        temp_dir = DATA_DIR / "temp" / f"preview_{scan_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        frames = []
        for i in range(count):
            pct = (i + 1) / (count + 1)  # gleichmäßig verteilt
            seek = max(1, int(dur * pct))
            out = temp_dir / f"frame_{i}.jpg"

            try:
                subprocess.run(
                    ["ffmpeg", "-ss", str(seek), "-i", str(src),
                     "-vframes", "1", "-vf", "scale=640:-1",
                     "-q:v", "3", str(out), "-y"],
                    capture_output=True, timeout=15)
                if out.exists() and out.stat().st_size > 0:
                    frames.append(str(out))
            except Exception as e:
                logger.warning(f"Frame-Extraktion fehlgeschlagen bei {seek}s: {e}")

        return frames

    async def set_thumbnail_from_frame(self, scan_id: int, frame_index: int) -> dict:
        """Bestimmten Frame als Thumbnail für ein bereits registriertes Video setzen."""
        row = await scan_db.fetch_one(
            "SELECT youtube_id, status FROM scan_index WHERE id = ?", (scan_id,))
        if not row or row["status"] != "registered" or not row["youtube_id"]:
            return {"status": "error", "message": "Nur für registrierte Videos"}

        frame_path = DATA_DIR / "temp" / f"preview_{scan_id}" / f"frame_{frame_index}.jpg"
        if not frame_path.exists():
            return {"status": "error", "message": f"Frame {frame_index} nicht gefunden"}

        dest = THUMBNAILS_DIR / f"{row['youtube_id']}.jpg"
        shutil.copy2(str(frame_path), str(dest))

        await db.execute(
            "UPDATE videos SET thumbnail_path = ? WHERE id = ?",
            (str(dest), row["youtube_id"]))

        return {"status": "ok", "thumbnail": str(dest)}

    # ═══════════════════════════════════════════════════════════
    #  INDEX-ABFRAGEN
    # ═══════════════════════════════════════════════════════════

    async def get_index(
        self, status: str = None, folder: str = None,
        search: str = None, page: int = 1, per_page: int = 50,
        sort_by: str = "id", sort_order: str = "asc",
    ) -> dict:
        conditions = []
        params = []

        if status and status != "all":
            conditions.append("status = ?")
            params.append(status)

        if folder:
            conditions.append("folder = ?")
            params.append(folder)

        if search:
            conditions.append("(title LIKE ? OR filename LIKE ? OR youtube_id LIKE ? OR channel_name LIKE ? OR folder LIKE ?)")
            q = f"%{search}%"
            params.extend([q, q, q, q, q])

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        allowed = {"id", "title", "folder", "status", "file_size", "scanned_at", "duration", "filename"}
        if sort_by not in allowed:
            sort_by = "id"
        order = f"ORDER BY {sort_by} {'DESC' if sort_order == 'desc' else 'ASC'}"

        total = await scan_db.fetch_val(
            f"SELECT COUNT(*) FROM scan_index {where}", params) or 0
        offset = (page - 1) * per_page
        rows = await scan_db.fetch_all(
            f"SELECT * FROM scan_index {where} {order} LIMIT ? OFFSET ?",
            params + [per_page, offset])

        return {
            "items": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": max(1, (total + per_page - 1) // per_page),
        }

    async def get_stats(self) -> dict:
        total = await scan_db.fetch_val("SELECT COUNT(*) FROM scan_index") or 0
        if total == 0:
            return {
                "total": 0, "discovered": 0, "identified": 0,
                "registered": 0, "skipped": 0, "duplicate": 0,
                "error": 0, "cleaned": 0, "folders": 0,
            }
        stats = {}
        for s in ["discovered", "identified", "registered", "skipped",
                   "duplicate", "error", "cleaned"]:
            stats[s] = await scan_db.fetch_val(
                "SELECT COUNT(*) FROM scan_index WHERE status = ?", (s,)) or 0
        stats["folders"] = await scan_db.fetch_val(
            "SELECT COUNT(DISTINCT folder) FROM scan_index") or 0
        return {"total": total, **stats}

    async def get_folders(self) -> list:
        rows = await scan_db.fetch_all(
            """SELECT folder,
                      COUNT(*) as total,
                      SUM(CASE WHEN status = 'discovered' THEN 1 ELSE 0 END) as discovered,
                      SUM(CASE WHEN status = 'identified' THEN 1 ELSE 0 END) as identified,
                      SUM(CASE WHEN status = 'registered' THEN 1 ELSE 0 END) as registered,
                      SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END) as skipped
               FROM scan_index GROUP BY folder ORDER BY total DESC""")
        return [dict(r) for r in rows]

    async def get_progress(self) -> dict:
        stats = await self.get_stats()
        return {
            "scanning": self._scanning,
            "phase": self._progress.get("phase", "idle"),
            "total_files": self._progress.get("total_files", 0),
            "current_batch": self._progress.get("current_batch", 0),
            "total_batches": self._progress.get("total_batches", 0),
            **stats,
        }

    # ═══════════════════════════════════════════════════════════
    #  STATUS-ÄNDERUNGEN
    # ═══════════════════════════════════════════════════════════

    async def update_status(self, scan_id: int, status: str) -> dict:
        allowed = {"discovered", "skipped", "identified"}
        if status not in allowed:
            return {"status": "error", "message": f"Ungültiger Status: {status}"}
        await scan_db.execute(
            "UPDATE scan_index SET status = ? WHERE id = ?", (status, scan_id))
        return {"status": "ok", "id": scan_id, "new_status": status}

    async def skip_folder(self, folder: str) -> dict:
        cursor = await scan_db.execute(
            """UPDATE scan_index SET status = 'skipped'
               WHERE folder = ? AND status IN ('discovered', 'identified')""",
            (folder,))
        return {"status": "ok", "folder": folder, "skipped": cursor.rowcount}

    async def reset_index(self) -> dict:
        await scan_db.execute("DELETE FROM scan_index")
        await scan_db.execute("DELETE FROM scan_state")
        return {"status": "ok"}

    # ═══════════════════════════════════════════════════════════
    #  HILFSFUNKTIONEN
    # ═══════════════════════════════════════════════════════════

    def _extract_youtube_id(self, filename: str) -> Optional[str]:
        for pattern in YT_ID_PATTERNS:
            m = pattern.search(filename)
            if m:
                return m.group(1)
        return None

    def _ffprobe(self, filepath: Path) -> Optional[dict]:
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", "-show_streams", str(filepath)],
                capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                return None
            data = json.loads(r.stdout)
            result = {}
            # Dauer
            dur = data.get("format", {}).get("duration")
            if dur:
                result["duration"] = int(float(dur))
            # Video-Stream für Auflösung
            for s in data.get("streams", []):
                if s.get("codec_type") == "video":
                    w = s.get("width")
                    h = s.get("height")
                    if w and h:
                        result["resolution"] = f"{w}x{h}"
                    result["codec"] = s.get("codec_name")
                    break
            return result
        except Exception as e:
            logger.warning(f"ffprobe fehlgeschlagen für {filepath}: {e}")
            return None

    # ═══════════════════════════════════════════════════════════
    #  REPAIR & ENRICH
    # ═══════════════════════════════════════════════════════════

    async def repair_thumbnail(self, video_id: str) -> dict:
        """Thumbnail für ein Video neu generieren."""
        video = await db.fetch_one(
            "SELECT id, file_path, duration FROM videos WHERE id = ?", (video_id,))
        if not video:
            return {"status": "error", "message": "Video nicht gefunden"}

        fp = Path(video["file_path"]) if video["file_path"] else None
        if not fp or not fp.exists():
            return {"status": "error", "message": f"Video-Datei nicht gefunden: {fp}"}

        dest = THUMBNAILS_DIR / f"{video_id}.jpg"
        result = generate_ffmpeg_thumbnail(fp, dest, duration=video["duration"])
        if result:
            await db.execute(
                "UPDATE videos SET thumbnail_path = ?, updated_at = ? WHERE id = ?",
                (str(result), now_sqlite(), video_id))
            return {"status": "ok", "thumbnail_path": str(result)}
        return {"status": "error", "message": "Thumbnail-Generierung fehlgeschlagen"}

    async def repair_all_thumbnails(self) -> dict:
        """Thumbnails für alle Videos ohne Thumbnail neu generieren."""
        rows = await db.fetch_all(
            """SELECT id, file_path, duration, thumbnail_path FROM videos
               WHERE source IN ('local', 'imported')""")
        repaired = 0
        for row in rows:
            tp = row["thumbnail_path"]
            if tp and Path(tp).exists():
                continue
            tid = row["id"]
            # Prüfe vorhandene Dateien
            found = False
            for ext in [".jpg", ".png", ".webp"]:
                if (THUMBNAILS_DIR / f"{tid}{ext}").exists():
                    found = True
                    await db.execute(
                        "UPDATE videos SET thumbnail_path = ? WHERE id = ?",
                        (str(THUMBNAILS_DIR / f"{tid}{ext}"), tid))
                    repaired += 1
                    break
            if found:
                continue
            # Neu generieren per ffmpeg
            fp = Path(row["file_path"]) if row["file_path"] else None
            if fp and fp.exists():
                dest = THUMBNAILS_DIR / f"{tid}.jpg"
                result = generate_ffmpeg_thumbnail(fp, dest, duration=row["duration"])
                if result:
                    await db.execute(
                        "UPDATE videos SET thumbnail_path = ?, updated_at = ? WHERE id = ?",
                        (str(result), now_sqlite(), tid))
                    repaired += 1
        return {"status": "ok", "repaired": repaired, "total": len(rows)}

    async def enrich_from_youtube(self, video_id: str) -> dict:
        """Video-Metadaten von YouTube abrufen und lokalen Eintrag anreichern."""
        if video_id.startswith("local_"):
            return {"status": "error", "message": "Kein YouTube-Video (lokale ID)"}

        video = await db.fetch_one("SELECT * FROM videos WHERE id = ?", (video_id,))
        if not video:
            return {"status": "error", "message": "Video nicht in DB"}

        try:
            from app.services.rate_limiter import rate_limiter

            # Rate-Limiter respektieren (gegen YouTube-Sperre)
            await rate_limiter.acquire("pytubefix")

            # pytubefix in Executor ausführen (blockiert sonst Event Loop!)
            def _fetch():
                from pytubefix import YouTube
                yt = YouTube(f"https://www.youtube.com/watch?v={video_id}")
                updates = {}
                if yt.title:
                    updates["title"] = yt.title
                if yt.author:
                    updates["channel_name"] = yt.author
                if yt.channel_id:
                    updates["channel_id"] = yt.channel_id
                if yt.description:
                    updates["description"] = yt.description
                if yt.length:
                    updates["duration"] = yt.length
                if yt.views:
                    updates["view_count"] = yt.views
                if yt.publish_date:
                    updates["upload_date"] = yt.publish_date.strftime("%Y-%m-%d")
                return updates

            updates = await asyncio.get_event_loop().run_in_executor(None, _fetch)
            rate_limiter.success("pytubefix")

            if not updates:
                return {"status": "error", "message": "Keine Metadaten von YouTube erhalten"}

            updates["updated_at"] = now_sqlite()

            # Thumbnail von YouTube holen falls lokal fehlt
            tp = video["thumbnail_path"]
            if not tp or not Path(tp).exists():
                yt_thumb = await download_yt_thumbnail(video_id, THUMBNAILS_DIR)
                if yt_thumb:
                    updates["thumbnail_path"] = str(yt_thumb)

            # DB updaten
            set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
            params = list(updates.values()) + [video_id]
            await db.execute(
                f"UPDATE videos SET {set_clause} WHERE id = ?", tuple(params))

            logger.info(f"[SCAN] YT-Anreicherung für {video_id}: {list(updates.keys())}")
            return {"status": "ok", "updated_fields": list(updates.keys()), "title": updates.get("title")}

        except Exception as e:
            logger.error(f"[SCAN] YT-Anreicherung fehlgeschlagen für {video_id}: {e}")
            return {"status": "error", "message": str(e)[:300]}

    async def create_thumbnail_at_position(self, video_id: str, position: int) -> dict:
        """Thumbnail aus bestimmter Video-Position generieren."""
        video = await db.fetch_one(
            "SELECT file_path FROM videos WHERE id = ?", (video_id,))
        if not video or not video["file_path"]:
            return {"status": "error", "message": "Video nicht gefunden"}

        fp = Path(video["file_path"])
        if not fp.exists():
            return {"status": "error", "message": "Video-Datei nicht gefunden"}

        dest = THUMBNAILS_DIR / f"{video_id}.jpg"
        result = generate_ffmpeg_thumbnail(fp, dest, position=position)
        if result:
            await db.execute(
                "UPDATE videos SET thumbnail_path = ?, updated_at = ? WHERE id = ?",
                (str(result), now_sqlite(), video_id))
            return {"status": "ok", "thumbnail_path": str(result), "position": position}
        return {"status": "error", "message": "Thumbnail-Erstellung fehlgeschlagen"}

    async def fetch_yt_thumbnail(self, video_id: str) -> dict:
        """YouTube-Thumbnail für ein Video laden (überschreibt immer)."""
        result = await download_yt_thumbnail(video_id, THUMBNAILS_DIR, overwrite=True)
        if result:
            await db.execute(
                "UPDATE videos SET thumbnail_path = ?, updated_at = ? WHERE id = ?",
                (str(result), now_sqlite(), video_id))
            return {"status": "ok", "quality": "best", "thumbnail_path": str(result)}
        return {"status": "error", "message": "Kein YouTube-Thumbnail verfügbar"}


# Singleton
scan_service = ScanService()

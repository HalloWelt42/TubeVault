"""
TubeVault -  Import Service v1.8.76
© HalloWelt42 -  Private Nutzung

Smart-Scan für eigene Videos: NFO-Parsing, Thumbnail-Erkennung,
Fuzzy-Matching gegen RSS/Bibliothek, Batch-Import.
"""

import json
import logging
import asyncio
import os
import re
import shutil
import subprocess
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import THUMBNAILS_DIR, VIDEOS_DIR, SUBTITLES_DIR, DATA_DIR
from app.database import db
from app.utils.file_utils import now_sqlite
from app.utils.tag_utils import sanitize_tags

logger = logging.getLogger(__name__)

# Unterstützte Dateiformate
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v", ".flv", ".wmv", ".ts"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
SUBTITLE_EXTENSIONS = {".srt", ".vtt", ".ass", ".ssa", ".sub"}

# Thumbnail-Suffixe (Jellyfin/Kodi-Pattern)
THUMB_PATTERNS = ["-poster", "-thumb", "-fanart", ".thumb", "_thumb", "-landscape"]


class ImportService:
    """Service für den Smart-Import eigener Videos."""

    # ─── Scan ──────────────────────────────────────────────────

    async def scan_directory(self, path: str, youtube_archive: bool = False) -> dict:
        """Verzeichnis rekursiv scannen und analysieren.

        Args:
            path: Container-Pfad zum Scan-Verzeichnis
            youtube_archive: Wenn True, Ordnernamen als YouTube-Kanäle interpretieren

        Returns:
            Strukturiertes Scan-Ergebnis mit Ordnern, Videos, Matches
        """
        scan_path = Path(path)
        if not scan_path.exists() or not scan_path.is_dir():
            return {"error": f"Verzeichnis nicht gefunden: {path}", "folders": []}

        # RSS-Entries + Videos für Matching laden
        rss_titles = await self._load_rss_titles()
        video_titles = await self._load_video_titles()
        subscriptions = await self._load_subscriptions()

        # Ergebnis-Struktur: gruppiert nach Ordner
        folders = {}

        # os.walk statt sorted(rglob) — kein RAM für komplette Dateiliste
        for dirpath, dirnames, filenames in os.walk(scan_path):
            dirnames.sort()
            for fname in sorted(filenames):
                f = Path(dirpath) / fname
                if f.suffix.lower() not in VIDEO_EXTENSIONS:
                    continue

            # Ordner bestimmen (relativ zum Scan-Root)
            rel = f.relative_to(scan_path)
            folder_name = str(rel.parent) if rel.parent != Path(".") else "(Root)"

            if folder_name not in folders:
                # Kanal-Match für Ordnernamen
                channel_match = None
                sub_exists = False
                if youtube_archive and folder_name != "(Root)":
                    channel_match = self._find_channel_match(
                        folder_name, subscriptions
                    )
                    sub_exists = channel_match is not None

                folders[folder_name] = {
                    "name": folder_name,
                    "is_youtube_archive": youtube_archive,
                    "channel_match": channel_match,
                    "subscription_exists": sub_exists,
                    "videos": [],
                }

            # Video analysieren
            video_info = await self._analyze_video(
                f, scan_path, rss_titles, video_titles, youtube_archive, folder_name
            )
            folders[folder_name]["videos"].append(video_info)

        folder_list = list(folders.values())

        # Statistiken
        total_videos = sum(len(f["videos"]) for f in folder_list)
        new_videos = sum(
            1 for f in folder_list for v in f["videos"]
            if not v["already_registered"]
        )
        matched = sum(
            1 for f in folder_list for v in f["videos"]
            if v.get("match") and v["match"]["confidence"] >= 0.7
        )
        portrait = sum(
            1 for f in folder_list for v in f["videos"]
            if v.get("is_portrait")
        )

        return {
            "path": path,
            "youtube_archive": youtube_archive,
            "total_folders": len(folder_list),
            "total_videos": total_videos,
            "new_videos": new_videos,
            "matched_videos": matched,
            "portrait_videos": portrait,
            "folders": folder_list,
        }

    async def _analyze_video(
        self, filepath: Path, scan_root: Path,
        rss_titles: list, video_titles: list,
        youtube_archive: bool, folder_name: str,
    ) -> dict:
        """Einzelnes Video analysieren: Companion-Dateien, Metadata, Matching."""
        base = filepath.with_suffix("")
        filename = filepath.name
        title_from_file = filepath.stem

        # Bereits registriert?
        existing = await db.fetch_one(
            "SELECT id, title, source FROM videos WHERE file_path = ?",
            (str(filepath),)
        )
        already = existing is not None

        # ── Companion-Dateien suchen ──
        nfo_data = self._find_and_parse_nfo(base)
        thumbnail = self._find_thumbnail(base, filepath.parent)
        description = self._find_description(base)
        subtitles = self._find_subtitles(base)

        # ── Metadaten zusammenbauen ──
        title = title_from_file
        duration = None
        resolution = None
        codec = None
        date_added = None
        channel_name = folder_name if youtube_archive and folder_name != "(Root)" else None

        if nfo_data:
            title = nfo_data.get("title", title)
            duration = nfo_data.get("duration")
            resolution = nfo_data.get("resolution")
            codec = nfo_data.get("codec")
            date_added = nfo_data.get("date_added")
            if not channel_name and nfo_data.get("channel"):
                channel_name = nfo_data["channel"]

        # FFprobe als Fallback für fehlende Daten
        if not duration or not resolution:
            probe = self._ffprobe(filepath)
            if probe:
                duration = duration or probe.get("duration")
                resolution = resolution or probe.get("resolution")
                codec = codec or probe.get("codec")

        # Dateigröße
        try:
            file_size = filepath.stat().st_size
        except OSError:
            file_size = 0

        # ── YouTube-ID aus Dateiname extrahieren ──
        yt_id = self._extract_youtube_id(filename)

        # ── Fuzzy-Matching ──
        match = None
        if not already:
            # Erst YouTube-ID matchen (genau)
            if yt_id:
                match = await self._match_by_youtube_id(yt_id)

            # Dann Titel-Matching (mit Duration-Vergleich)
            if not match:
                match = self._fuzzy_match_title(
                    title, rss_titles, video_titles, channel_name,
                    file_duration=duration
                )

        # Portrait-Erkennung (Shorts-Heuristik)
        is_portrait = False
        if resolution:
            try:
                w, h = resolution.split("x")
                is_portrait = int(h) > int(w)
            except (ValueError, AttributeError):
                pass

        return {
            "path": str(filepath),
            "filename": filename,
            "title": title,
            "channel_name": channel_name,
            "duration": duration,
            "file_size": file_size,
            "resolution": resolution,
            "codec": codec,
            "date_added": date_added,
            "youtube_id": yt_id,
            "nfo_found": nfo_data is not None,
            "thumbnail_found": thumbnail,
            "description_found": description is not None,
            "description_text": description,
            "subtitles_found": subtitles,
            "match": match,
            "already_registered": already,
            "existing_id": existing["id"] if existing else None,
            "is_portrait": is_portrait,
        }

    # ─── Import ────────────────────────────────────────────────

    async def import_video(
        self,
        file_path: str,
        title: str = None,
        channel_name: str = None,
        description: str = None,
        youtube_id: str = None,
        source: str = "imported",
        thumbnail_path: str = None,
        duration: int = None,
        date_added: str = None,
        tags: list = None,
        generate_thumbnail: bool = True,
    ) -> dict:
        """Ein Video importieren und in der DB registrieren.

        Args:
            file_path: Pfad zum Video im Container
            title: Titel (Fallback: Dateiname)
            youtube_id: Wenn bekannt, wird das die Video-ID
            source: 'imported' (ex-YouTube) oder 'local' (eigenes)
            generate_thumbnail: Thumbnail per FFmpeg erzeugen falls keins da

        Returns:
            Dict mit Video-ID und Metadaten
        """
        fp = Path(file_path)
        if not fp.exists():
            raise FileNotFoundError(f"Datei nicht gefunden: {file_path}")

        # Bereits registriert?
        existing = await db.fetch_one(
            "SELECT id FROM videos WHERE file_path = ?", (file_path,)
        )
        if existing:
            return {"id": existing["id"], "status": "already_exists"}

        # Video-ID
        if youtube_id:
            video_id = youtube_id
            source = "imported"
            # Prüfen ob diese YouTube-ID schon existiert
            yt_existing = await db.fetch_one(
                "SELECT id FROM videos WHERE id = ?", (youtube_id,)
            )
            if yt_existing:
                return {"id": youtube_id, "status": "youtube_id_exists"}
        else:
            video_id = f"own_{uuid.uuid4().hex[:12]}"

        # Metadaten
        title = title or fp.stem
        file_size = fp.stat().st_size

        # FFprobe für Duration + Resolution
        probe = self._ffprobe(fp)
        if not duration and probe:
            duration = probe.get("duration")

        # Thumbnail verarbeiten
        final_thumb = None
        if thumbnail_path and Path(thumbnail_path).exists():
            final_thumb = await self._copy_thumbnail(thumbnail_path, video_id)
        elif generate_thumbnail:
            final_thumb = await self._generate_thumbnail(file_path, video_id)

        now = now_sqlite()
        tags_list = tags or []
        # System-Tag hinzufügen
        if source == "imported" and "#Import" not in tags_list:
            tags_list.append("#Import")
        elif source == "local" and "#Eigenes Video" not in tags_list:
            tags_list.append("#Eigenes Video")

        # Video-Typ erkennen: Portrait-Format + kurz → Short
        video_type = "video"
        res_str = probe.get("resolution") if probe else None
        if res_str:
            try:
                w, h = res_str.split("x")
                if int(h) > int(w) and duration and int(duration) <= 60:
                    video_type = "short"
                    if "#Short" not in tags_list:
                        tags_list.append("#Short")
            except (ValueError, AttributeError):
                pass

        await db.execute(
            """INSERT INTO videos
               (id, title, channel_name, description, duration, download_date,
                thumbnail_path, tags, status, file_path, file_size,
                source, source_url, import_path, video_type, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ready', ?, ?, ?, ?, ?, ?, ?, ?)""",
            (video_id, title, channel_name, description, duration,
             date_added or now, final_thumb, json.dumps(sanitize_tags(tags_list)),
             file_path, file_size, source, None, file_path,
             video_type, now, now)
        )

        logger.info(f"Video importiert: {video_id} ({title}) [source={source}]")

        return {
            "id": video_id,
            "title": title,
            "channel_name": channel_name,
            "duration": duration,
            "file_size": file_size,
            "source": source,
            "video_type": video_type,
            "thumbnail": final_thumb,
            "status": "imported",
        }

    async def import_batch(self, videos: list, subscribe_channels: list = None) -> dict:
        """Mehrere Videos auf einmal importieren.

        Args:
            videos: Liste von Dicts mit Import-Parametern
            subscribe_channels: Liste von Kanalnamen die als Abo angelegt werden sollen

        Returns:
            Zusammenfassung
        """
        imported = 0
        skipped = 0
        errors = []

        for v in videos:
            try:
                result = await self.import_video(**v)
                if result["status"] == "imported":
                    imported += 1
                else:
                    skipped += 1
            except Exception as e:
                errors.append({"path": v.get("file_path"), "error": str(e)})
                logger.error(f"Import-Fehler: {v.get('file_path')}: {e}")

        # Kanäle abonnieren falls gewünscht
        subs_added = 0
        if subscribe_channels:
            for ch in subscribe_channels:
                try:
                    await self._subscribe_channel(ch)
                    subs_added += 1
                except Exception as e:
                    logger.warning(f"Abo-Fehler für {ch}: {e}")

        return {
            "imported": imported,
            "skipped": skipped,
            "errors": errors,
            "subscriptions_added": subs_added,
        }

    # ─── Eigene Videos abrufen ─────────────────────────────────

    async def get_own_videos(
        self, page: int = 1, per_page: int = 24,
        source_filter: str = None, channel: str = None,
        search: str = None, sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> dict:
        """Eigene/importierte Videos abrufen."""
        conditions = ["v.source IN ('local', 'imported')", "v.status = 'ready'", "v.file_path IS NOT NULL"]
        params = []

        if source_filter:
            conditions.append("v.source = ?")
            params.append(source_filter)

        if channel:
            conditions.append("v.channel_name = ?")
            params.append(channel)

        if search:
            conditions.append("(v.title LIKE ? OR v.channel_name LIKE ? OR v.file_path LIKE ? OR v.import_path LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])

        where = "WHERE " + " AND ".join(conditions)

        total = await db.fetch_val(
            f"SELECT COUNT(*) FROM videos v {where}", tuple(params)
        ) or 0

        allowed_sorts = {"created_at", "title", "duration", "file_size", "channel_name"}
        if sort_by not in allowed_sorts:
            sort_by = "created_at"
        order = "DESC" if sort_order.lower() == "desc" else "ASC"

        offset = (page - 1) * per_page
        rows = await db.fetch_all(
            f"""SELECT v.id, v.title, v.channel_name, v.duration, v.file_size,
                       v.thumbnail_path, v.source, v.import_path, v.tags,
                       v.created_at, v.rating, v.play_count, v.video_type
                FROM videos v {where}
                ORDER BY {sort_by} {order}
                LIMIT ? OFFSET ?""",
            tuple(params) + (per_page, offset)
        )

        videos = []
        for r in rows:
            tags = r["tags"]
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except (json.JSONDecodeError, TypeError):
                    tags = []
            videos.append({
                "id": r["id"],
                "title": r["title"],
                "channel_name": r["channel_name"],
                "duration": r["duration"],
                "file_size": r["file_size"],
                "thumbnail_path": r["thumbnail_path"],
                "source": r["source"],
                "import_path": r["import_path"],
                "tags": tags,
                "created_at": r["created_at"],
                "rating": r["rating"],
                "play_count": r["play_count"],
                "video_type": r["video_type"],
            })

        # Kanäle für Filter
        channels = await db.fetch_all(
            """SELECT channel_name, COUNT(*) as count
               FROM videos WHERE source IN ('local', 'imported')
               AND status = 'ready'
               AND channel_name IS NOT NULL AND channel_name != ''
               GROUP BY channel_name ORDER BY count DESC"""
        )

        return {
            "videos": videos,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": max(1, (total + per_page - 1) // per_page),
            "channels": [{"name": c["channel_name"], "count": c["count"]} for c in channels],
        }

    async def get_own_stats(self) -> dict:
        """Statistiken für eigene Videos."""
        total = await db.fetch_val(
            "SELECT COUNT(*) FROM videos WHERE source IN ('local', 'imported') AND status = 'ready' AND file_path IS NOT NULL"
        ) or 0
        imported = await db.fetch_val(
            "SELECT COUNT(*) FROM videos WHERE source = 'imported' AND status = 'ready' AND file_path IS NOT NULL"
        ) or 0
        local = await db.fetch_val(
            "SELECT COUNT(*) FROM videos WHERE source = 'local' AND status = 'ready' AND file_path IS NOT NULL"
        ) or 0
        total_size = await db.fetch_val(
            "SELECT COALESCE(SUM(file_size), 0) FROM videos WHERE source IN ('local', 'imported') AND status = 'ready' AND file_path IS NOT NULL"
        ) or 0
        total_duration = await db.fetch_val(
            "SELECT COALESCE(SUM(duration), 0) FROM videos WHERE source IN ('local', 'imported') AND status = 'ready' AND file_path IS NOT NULL"
        ) or 0

        return {
            "total": total,
            "imported": imported,
            "local": local,
            "total_size": total_size,
            "total_duration": total_duration,
        }

    # ─── Async Scan (Job-basiert) ─────────────────────────────

    async def start_scan_job(self, path: str, youtube_archive: bool = False) -> dict:
        """Async Scan-Job starten. Gibt Session-ID + Job-ID zurück."""
        from app.services.job_service import job_service

        # Prüfen ob bereits ein Scan läuft
        running = await db.fetch_one(
            "SELECT id FROM scan_sessions WHERE status = 'running' LIMIT 1"
        )
        if running:
            raise ValueError("Es läuft bereits ein Scan. Bitte warten oder abbrechen.")

        scan_path = Path(path)
        if not scan_path.exists() or not scan_path.is_dir():
            raise FileNotFoundError(f"Verzeichnis nicht gefunden: {path}")

        # Dateien vorab zählen (os.walk statt rglob — weniger RAM)
        total_files = 0
        for dp, dn, fns in os.walk(scan_path):
            total_files += sum(1 for fn in fns if Path(fn).suffix.lower() in VIDEO_EXTENSIONS)

        if total_files == 0:
            raise ValueError(f"Keine Videodateien gefunden in {path}")

        # Session anlegen
        cursor = await db.execute(
            """INSERT INTO scan_sessions (scan_path, youtube_archive, total_files)
               VALUES (?, ?, ?)""",
            (path, youtube_archive, total_files)
        )
        session_id = cursor.lastrowid

        # Job anlegen
        job = await job_service.create(
            job_type="import_scan",
            title=f"Video-Scan: {total_files} Dateien",
            description=path,
            metadata={"session_id": session_id, "total_files": total_files},
        )

        await db.execute(
            "UPDATE scan_sessions SET job_id = ? WHERE id = ?",
            (job["id"], session_id)
        )

        # Job async starten
        job_service.schedule_exclusive(
            job["id"], self._run_scan_job,
            session_id, path, youtube_archive, total_files
        )

        return {
            "session_id": session_id,
            "job_id": job["id"],
            "total_files": total_files,
            "path": path,
        }

    async def _run_scan_job(
        self, job_id: int, session_id: int,
        path: str, youtube_archive: bool, total_files: int
    ):
        """Scan-Job Worker: analysiert alle Videos und speichert in Staging.
        Memory-effizient: Keine volle Materialisierung, Batch-Writes mit Commit,
        periodisches GC.
        """
        import gc
        import time as _time
        from app.services.job_service import job_service

        scan_path = Path(path)

        # Lookup-Daten laden
        rss_titles = await self._load_rss_titles()
        video_titles = await self._load_video_titles()
        subscriptions = await self._load_subscriptions()

        scanned = 0
        batch = []
        BATCH_SIZE = 20
        GC_INTERVAL = 100  # gc.collect() alle 100 Dateien
        scan_start = _time.monotonic()

        # NICHT sorted(rglob("*")) — das materialisiert alles im RAM.
        # Stattdessen: os.walk + sortiert pro Ordner (streamed)
        for dirpath, dirnames, filenames in os.walk(scan_path):
            dirnames.sort()  # Sortiert traversieren ohne alles in RAM
            for fname in sorted(filenames):
                f = Path(dirpath) / fname
                if f.suffix.lower() not in VIDEO_EXTENSIONS:
                    continue

                # Pause prüfen
                while job_service.is_job_paused(job_id):
                    await job_service.progress(
                        job_id, round(scanned / total_files, 4),
                        f"⏸ Pausiert bei {scanned}/{total_files}"
                    )
                    await asyncio.sleep(1)
                    if job_service.is_cancelled(job_id):
                        break

                # Abbruch prüfen
                if job_service.is_cancelled(job_id):
                    await db.execute(
                        "UPDATE scan_sessions SET status = 'cancelled' WHERE id = ?",
                        (session_id,)
                    )
                    return f"Abgebrochen bei {scanned}/{total_files}"

                # Ordnername bestimmen
                rel = f.relative_to(scan_path)
                folder_name = str(rel.parent) if rel.parent != Path(".") else "(Root)"

                # Analysieren
                try:
                    info = await self._analyze_video(
                        f, scan_path, rss_titles, video_titles, youtube_archive, folder_name
                    )
                except Exception as e:
                    logger.warning(f"Scan-Fehler bei {f}: {e}")
                    scanned += 1
                    continue

                # Match-Info aufbereiten
                match = info.get("match")
                match_type = "none"
                match_id = None
                match_title = None
                match_channel = None
                match_confidence = 0
                match_duration_val = None
                dur_boost = False
                dur_penalty = False
                candidates_json = "[]"

                if info.get("already_registered"):
                    match_type = "duplicate"
                    match_id = info.get("existing_id")
                elif match:
                    match_confidence = match.get("confidence", 0)
                    match_id = match.get("id")
                    match_title = match.get("title")
                    match_channel = match.get("channel")
                    match_duration_val = match.get("match_duration")
                    dur_boost = match.get("duration_boost", False)
                    dur_penalty = match.get("duration_penalty", False)

                    if info.get("youtube_id") and match_confidence >= 0.95:
                        match_type = "exact"
                    elif match.get("type") == "rss" and match_confidence >= 0.95:
                        match_type = "exact_rss"
                    elif match_confidence >= 0.7:
                        match_type = "fuzzy_hi"
                    elif match_confidence >= 0.5:
                        match_type = "fuzzy_lo"
                    else:
                        match_type = "weak"

                    if match.get("candidates"):
                        candidates_json = json.dumps(match["candidates"][:5])

                batch.append((
                    session_id, str(f), info["filename"], folder_name,
                    info["title"], info.get("channel_name"),
                    info.get("duration"), info.get("file_size", 0),
                    info.get("resolution"), info.get("codec"),
                    info.get("youtube_id"),
                    1 if info.get("is_portrait") else 0,
                    1 if info.get("nfo_found") else 0,
                    info.get("thumbnail_found"),
                    info.get("description_text"),
                    json.dumps(info.get("subtitles_found")) if info.get("subtitles_found") else None,
                    match_type, match_id, match_title, match_channel,
                    match_confidence, match_duration_val,
                    1 if dur_boost else 0,
                    1 if dur_penalty else 0,
                    candidates_json,
                    1 if info.get("already_registered") else 0,
                    info.get("existing_id"),
                ))

                # Batch schreiben + sofort committen
                if len(batch) >= BATCH_SIZE:
                    await self._insert_staging_batch(batch)
                    await db.commit()
                    batch = []

                scanned += 1

                # Periodisch Speicher freigeben
                if scanned % GC_INTERVAL == 0:
                    gc.collect()
                    await asyncio.sleep(0)  # Event-Loop atmen lassen

                # Fortschritt (alle 10 Dateien)
                if scanned % 10 == 0 or scanned == total_files:
                    pct = round(scanned / total_files, 4)
                    elapsed = _time.monotonic() - scan_start
                    if scanned > 0 and elapsed > 0:
                        speed = scanned / elapsed
                        remaining = (total_files - scanned) / speed
                        if remaining > 3600:
                            eta_str = f"{remaining/3600:.1f}h"
                        elif remaining > 60:
                            eta_str = f"{remaining/60:.0f}min"
                        else:
                            eta_str = f"{remaining:.0f}s"
                        desc = f"{scanned}/{total_files} analysiert · {speed:.1f}/s · ~{eta_str}"
                    else:
                        desc = f"{scanned}/{total_files} Dateien analysiert"
                    await job_service.progress(job_id, pct, desc)
                    await db.execute(
                        "UPDATE scan_sessions SET scanned_files = ? WHERE id = ?",
                        (scanned, session_id)
                    )

        # Rest-Batch schreiben
        if batch:
            await self._insert_staging_batch(batch)
            await db.commit()

        # Lookup-Daten explizit freigeben
        del rss_titles, video_titles, subscriptions
        gc.collect()

        # Session abschließen
        await db.execute(
            "UPDATE scan_sessions SET status = 'done', scanned_files = ?, finished_at = datetime('now') WHERE id = ?",
            (scanned, session_id)
        )

        return f"{scanned} Dateien gescannt"

    async def _insert_staging_batch(self, batch: list):
        """Batch-Insert in scan_staging."""
        for row in batch:
            await db.execute(
                """INSERT INTO scan_staging (
                    session_id, file_path, filename, folder_name,
                    title, channel_name, duration, file_size,
                    resolution, codec, youtube_id, is_portrait,
                    nfo_found, thumbnail_path, description_text, subtitles_found,
                    match_type, match_id, match_title, match_channel,
                    match_confidence, match_duration, duration_boost, duration_penalty,
                    match_candidates, already_registered, existing_id
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                row
            )

    # ─── Scan-Ergebnisse abrufen ──────────────────────────────

    async def get_scan_session(self, session_id: int) -> dict:
        """Session-Info mit Statistiken."""
        session = await db.fetch_one(
            "SELECT * FROM scan_sessions WHERE id = ?", (session_id,)
        )
        if not session:
            return None

        stats = await db.fetch_one(
            """SELECT
                COUNT(*) as total,
                SUM(CASE WHEN match_type = 'duplicate' THEN 1 ELSE 0 END) as duplicates,
                SUM(CASE WHEN match_type = 'exact' THEN 1 ELSE 0 END) as exact,
                SUM(CASE WHEN match_type = 'exact_rss' THEN 1 ELSE 0 END) as exact_rss,
                SUM(CASE WHEN match_type IN ('fuzzy_hi', 'fuzzy_lo') THEN 1 ELSE 0 END) as fuzzy,
                SUM(CASE WHEN match_type = 'weak' THEN 1 ELSE 0 END) as weak,
                SUM(CASE WHEN match_type = 'none' THEN 1 ELSE 0 END) as unmatched,
                SUM(CASE WHEN decision IS NOT NULL THEN 1 ELSE 0 END) as decided
            FROM scan_staging WHERE session_id = ?""",
            (session_id,)
        )

        return {
            **dict(session),
            "stats": dict(stats) if stats else {},
        }

    async def get_scan_results(
        self, session_id: int,
        page: int = 1, per_page: int = 50,
        match_filter: str = None,
        folder_filter: str = None,
        decision_filter: str = None,
        search: str = None,
    ) -> dict:
        """Scan-Ergebnisse paginiert abrufen."""
        conditions = ["session_id = ?"]
        params = [session_id]

        if match_filter and match_filter != "all":
            if match_filter == "matched":
                conditions.append("match_type IN ('exact', 'exact_rss', 'fuzzy_hi')")
            elif match_filter == "unsure":
                conditions.append("match_type IN ('fuzzy_lo', 'weak')")
            elif match_filter == "new":
                conditions.append("match_type = 'none'")
            elif match_filter == "duplicate":
                conditions.append("match_type = 'duplicate'")
            elif match_filter == "decided":
                conditions.append("decision IS NOT NULL")
            elif match_filter == "undecided":
                conditions.append("decision IS NULL AND match_type != 'duplicate'")

        if folder_filter:
            conditions.append("folder_name = ?")
            params.append(folder_filter)

        if decision_filter:
            if decision_filter == "none":
                conditions.append("decision IS NULL")
            else:
                conditions.append("decision = ?")
                params.append(decision_filter)

        if search:
            conditions.append("(title LIKE ? OR filename LIKE ? OR channel_name LIKE ?)")
            params.extend([f"%{search}%"] * 3)

        where = " AND ".join(conditions)

        total = await db.fetch_val(
            f"SELECT COUNT(*) FROM scan_staging WHERE {where}", tuple(params)
        ) or 0

        offset = (page - 1) * per_page
        rows = await db.fetch_all(
            f"""SELECT * FROM scan_staging WHERE {where}
                ORDER BY folder_name, filename
                LIMIT ? OFFSET ?""",
            tuple(params) + (per_page, offset)
        )

        results = []
        for r in rows:
            d = dict(r)
            # JSON-Felder parsen
            try:
                d["match_candidates"] = json.loads(d.get("match_candidates") or "[]")
            except (json.JSONDecodeError, TypeError):
                d["match_candidates"] = []
            try:
                d["subtitles_found"] = json.loads(d.get("subtitles_found") or "null")
            except (json.JSONDecodeError, TypeError):
                pass
            results.append(d)

        # Ordner-Liste für Filter
        folders = await db.fetch_all(
            """SELECT folder_name, COUNT(*) as count,
                      SUM(CASE WHEN decision IS NOT NULL THEN 1 ELSE 0 END) as decided
               FROM scan_staging WHERE session_id = ?
               GROUP BY folder_name ORDER BY folder_name""",
            (session_id,)
        )

        return {
            "results": results,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": max(1, (total + per_page - 1) // per_page),
            "folders": [dict(f) for f in folders],
        }

    # ─── Entscheidungen ──────────────────────────────────────

    async def set_decision(self, staging_id: int, decision: str, channel: str = None) -> dict:
        """Entscheidung für eine Datei setzen."""
        valid = {"link", "link_rss", "import_new", "skip", "replace", "delete"}
        if decision not in valid:
            raise ValueError(f"Ungültige Entscheidung: {decision}. Erlaubt: {valid}")

        await db.execute(
            """UPDATE scan_staging
               SET decision = ?, decision_channel = ?, decision_at = datetime('now')
               WHERE id = ?""",
            (decision, channel, staging_id)
        )
        return {"id": staging_id, "decision": decision}

    async def set_bulk_decision(
        self, session_id: int, decision: str,
        match_type: str = None, folder_name: str = None,
        channel: str = None,
    ) -> dict:
        """Entscheidung für mehrere Dateien auf einmal."""
        valid = {"link", "link_rss", "import_new", "skip", "replace", "delete"}
        if decision not in valid:
            raise ValueError(f"Ungültige Entscheidung: {decision}")

        conditions = ["session_id = ?", "decision IS NULL"]
        params = [session_id]

        if match_type:
            conditions.append("match_type = ?")
            params.append(match_type)
        if folder_name:
            conditions.append("folder_name = ?")
            params.append(folder_name)

        where = " AND ".join(conditions)
        params_final = [decision, channel] + params

        result = await db.execute(
            f"""UPDATE scan_staging
               SET decision = ?, decision_channel = ?, decision_at = datetime('now')
               WHERE {where}""",
            tuple(params_final)
        )

        affected = await db.fetch_val(
            f"SELECT COUNT(*) FROM scan_staging WHERE {where.replace('decision IS NULL', 'decision = ?')}",
            tuple([decision] + params[1:] if len(params) > 1 else [decision, session_id])
        )

        return {"decision": decision, "affected": affected or 0}

    async def execute_decisions(self, session_id: int) -> dict:
        """Alle Entscheidungen einer Session ausführen.
        Verschiebt Dateien nach /app/data/videos/, verarbeitet Thumbnails,
        Untertitel, und räumt den Scan-Ordner auf.
        """
        # Session-Info laden
        session = await db.fetch_one(
            "SELECT scan_path FROM scan_sessions WHERE id = ?", (session_id,)
        )
        scan_root = Path(session["scan_path"]) if session else None

        # Alle entschiedenen Dateien laden
        rows = await db.fetch_all(
            """SELECT * FROM scan_staging
               WHERE session_id = ? AND decision IS NOT NULL
               ORDER BY decision, folder_name""",
            (session_id,)
        )

        if not rows:
            return {"error": "Keine Entscheidungen vorhanden"}

        results = {"linked": 0, "imported": 0, "replaced": 0, "skipped": 0, "deleted": 0, "errors": []}

        for r in rows:
            try:
                decision = r["decision"]

                if decision == "skip":
                    results["skipped"] += 1
                    continue

                elif decision == "delete":
                    self._delete_with_companions(r["file_path"])
                    results["deleted"] += 1
                    continue

                elif decision in ("link", "link_rss"):
                    video_id = r["match_id"]
                    if not video_id:
                        results["errors"].append(f"Kein Match-ID für {r['filename']}")
                        continue

                    # Datei verschieben
                    new_path = self._move_video_to_library(r["file_path"], video_id)
                    # Thumbnail verarbeiten
                    thumb = await self._handle_thumbnail_for_execute(r, video_id)
                    # Untertitel verschieben
                    self._move_subtitles_to_library(r["file_path"], video_id)
                    # Channel-ID auflösen
                    channel_id = await self._resolve_channel_id(r["channel_name"])

                    # Prüfen ob Video in DB existiert
                    existing = await db.fetch_one(
                        "SELECT id, source FROM videos WHERE id = ?", (video_id,)
                    )

                    if existing:
                        # Bestehendes Video aktualisieren (z.B. RSS-Stub → ready)
                        update_fields = {
                            "file_path": str(new_path),
                            "file_size": r["file_size"],
                            "status": "ready",
                        }
                        if r["duration"]:
                            update_fields["duration"] = r["duration"]
                        if thumb:
                            update_fields["thumbnail_path"] = thumb
                        if channel_id:
                            update_fields["channel_id"] = channel_id
                        if not existing["source"] or existing["source"] == "youtube":
                            update_fields["source"] = "imported"
                        update_fields["download_date"] = now_sqlite()
                        update_fields["updated_at"] = now_sqlite()

                        set_clause = ", ".join(f"{k} = ?" for k in update_fields)
                        vals = list(update_fields.values()) + [video_id]
                        await db.execute(
                            f"UPDATE videos SET {set_clause} WHERE id = ?", tuple(vals)
                        )
                    else:
                        # Neues Video anlegen (RSS-Entry ohne Video-Eintrag)
                        await self.import_video(
                            file_path=str(new_path),
                            title=r["title"],
                            channel_name=r["channel_name"],
                            youtube_id=video_id if r.get("youtube_id") else None,
                            source="imported",
                            thumbnail_path=thumb,
                            duration=r.get("duration"),
                            description=r.get("description_text"),
                            generate_thumbnail=not bool(thumb),
                        )
                        if channel_id:
                            await db.execute(
                                "UPDATE videos SET channel_id = ? WHERE id = ?",
                                (channel_id, video_id)
                            )

                    # Begleitdateien aufräumen
                    self._delete_companions(r["file_path"])
                    results["linked"] += 1

                elif decision == "import_new":
                    channel = r["decision_channel"] or r["channel_name"]
                    yt_id = r.get("youtube_id")
                    video_id = yt_id or f"own_{uuid.uuid4().hex[:12]}"
                    source = "imported" if yt_id else "local"

                    # Datei verschieben
                    new_path = self._move_video_to_library(r["file_path"], video_id)
                    # Thumbnail verarbeiten
                    thumb = await self._handle_thumbnail_for_execute(r, video_id)
                    # Untertitel verschieben
                    self._move_subtitles_to_library(r["file_path"], video_id)

                    # Video importieren mit neuem Pfad
                    await self.import_video(
                        file_path=str(new_path),
                        title=r["title"],
                        channel_name=channel,
                        description=r.get("description_text"),
                        youtube_id=yt_id,
                        source=source,
                        thumbnail_path=thumb,
                        duration=r.get("duration"),
                        generate_thumbnail=not bool(thumb),
                    )

                    # Channel-ID setzen
                    channel_id = await self._resolve_channel_id(channel)
                    if channel_id:
                        await db.execute(
                            "UPDATE videos SET channel_id = ? WHERE id = ?",
                            (channel_id, video_id)
                        )

                    # Begleitdateien aufräumen
                    self._delete_companions(r["file_path"])
                    results["imported"] += 1

                elif decision == "replace":
                    vid_id = r["match_id"] or r["existing_id"]
                    if not vid_id:
                        results["errors"].append(f"Kein Video-ID für replace: {r['filename']}")
                        continue

                    # Alte Datei ermitteln
                    old = await db.fetch_one(
                        "SELECT file_path FROM videos WHERE id = ?", (vid_id,)
                    )

                    # Neue Datei verschieben
                    new_path = self._move_video_to_library(r["file_path"], vid_id)

                    # Alte Datei löschen wenn anders
                    if old and old["file_path"] and old["file_path"] != str(new_path):
                        old_p = Path(old["file_path"])
                        if old_p.exists():
                            old_p.unlink()
                            logger.info(f"Alte Datei gelöscht: {old_p}")

                    # Thumbnail aktualisieren falls vorhanden
                    thumb = await self._handle_thumbnail_for_execute(r, vid_id)

                    # DB aktualisieren
                    update = "UPDATE videos SET file_path = ?, file_size = ?, status = 'ready', updated_at = datetime('now')"
                    params = [str(new_path), r["file_size"]]
                    if thumb:
                        update += ", thumbnail_path = ?"
                        params.append(thumb)
                    update += " WHERE id = ?"
                    params.append(vid_id)
                    await db.execute(update, tuple(params))

                    # Begleitdateien aufräumen
                    self._delete_companions(r["file_path"])
                    results["replaced"] += 1

            except Exception as e:
                results["errors"].append(f"{r['filename']}: {e}")
                logger.error(f"Execute-Fehler bei {r['filename']}: {e}", exc_info=True)

        # Leere Ordner im Scan-Verzeichnis aufräumen
        if scan_root and scan_root.exists():
            cleaned = self._cleanup_empty_dirs(scan_root)
            if cleaned:
                logger.info(f"Aufgeräumt: {cleaned} leere Ordner entfernt")

        # Session als ausgeführt markieren
        await db.execute(
            "UPDATE scan_sessions SET status = 'executed' WHERE id = ?",
            (session_id,)
        )

        return results

    # ─── Execute-Hilfsmethoden ────────────────────────────────

    def _move_video_to_library(self, src_path: str, video_id: str) -> Path:
        """Video-Datei nach /app/data/videos/{video_id}{ext} verschieben.
        Gibt den neuen Pfad zurück.
        """
        src = Path(src_path)
        if not src.exists():
            raise FileNotFoundError(f"Quelldatei nicht gefunden: {src_path}")

        ext = src.suffix.lower()
        dest = VIDEOS_DIR / f"{video_id}{ext}"

        # Bereits am Ziel?
        if src == dest:
            return dest

        # Kollision: Ziel existiert schon mit anderem Inhalt
        if dest.exists():
            # Gleiche Größe = vermutlich gleich, überschreiben
            if dest.stat().st_size == src.stat().st_size:
                src.unlink()
                logger.info(f"Identische Datei am Ziel, Quelle gelöscht: {src}")
                return dest
            # Andere Größe: Suffix anhängen
            dest = VIDEOS_DIR / f"{video_id}_imported{ext}"

        VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        logger.info(f"Video verschoben: {src.name} → {dest.name}")
        return dest

    def _move_subtitles_to_library(self, src_path: str, video_id: str):
        """Untertitel-Dateien neben der Quelldatei finden und nach
        /app/data/subtitles/{video_id}.{lang}{ext} verschieben.
        """
        base = Path(src_path).with_suffix("")
        SUBTITLES_DIR.mkdir(parents=True, exist_ok=True)

        for ext in SUBTITLE_EXTENSIONS:
            for candidate in base.parent.glob(base.name + "*" + ext):
                # Sprachcode extrahieren: video.de.srt → de
                parts = candidate.name.replace(base.name, "").split(".")
                lang_parts = [p for p in parts if p and p != ext.lstrip(".")]
                lang = ".".join(lang_parts) if lang_parts else ""
                suffix = f".{lang}{ext}" if lang else ext
                dest = SUBTITLES_DIR / f"{video_id}{suffix}"
                try:
                    shutil.move(str(candidate), str(dest))
                    logger.info(f"Untertitel verschoben: {candidate.name} → {dest.name}")
                except Exception as e:
                    logger.warning(f"Untertitel verschieben fehlgeschlagen: {candidate} → {e}")

    async def _handle_thumbnail_for_execute(self, row: dict, video_id: str) -> Optional[str]:
        """Thumbnail für ein Video beim Execute verarbeiten.
        1. Companion-Thumbnail aus Scan-Ordner kopieren
        2. Falls keins: per FFmpeg generieren
        Returns: Thumbnail-Pfad oder None
        """
        thumb_src = row.get("thumbnail_path") or row.get("thumbnail_found")
        if thumb_src and Path(thumb_src).exists():
            result = await self._copy_thumbnail(thumb_src, video_id)
            if result:
                return result

        # Fallback: generieren aus Video (das jetzt in /videos/ liegt)
        new_video = VIDEOS_DIR / f"{video_id}{Path(row['file_path']).suffix}"
        if new_video.exists():
            return await self._generate_thumbnail(str(new_video), video_id)
        return None

    def _delete_with_companions(self, file_path: str):
        """Video-Datei UND alle Begleitdateien löschen (für delete-Entscheidung)."""
        fp = Path(file_path)
        base = fp.with_suffix("")

        # Video selbst
        if fp.exists():
            fp.unlink()
            logger.info(f"Gelöscht: {fp}")

        # Alle Begleitdateien im gleichen Ordner
        self._delete_companions(file_path)

    def _delete_companions(self, file_path: str):
        """Nur Begleitdateien löschen (NFO, Thumbnail, Description, Subtitles).
        Die Video-Datei selbst wird NICHT gelöscht.
        """
        base = Path(file_path).with_suffix("")
        directory = Path(file_path).parent

        # NFO
        for nfo in [base.with_suffix(".nfo"), base.parent / (base.name + ".nfo")]:
            if nfo.exists():
                nfo.unlink()

        # Thumbnails
        for suffix in THUMB_PATTERNS:
            for ext in IMAGE_EXTENSIONS:
                f = base.parent / (base.name + suffix + ext)
                if f.exists():
                    f.unlink()
        for ext in IMAGE_EXTENSIONS:
            f = base.with_suffix(ext)
            if f.exists():
                f.unlink()

        # Description
        for ext in [".txt", ".description", ".desc"]:
            f = base.with_suffix(ext)
            if f.exists():
                f.unlink()

        # Subtitles
        for ext in SUBTITLE_EXTENSIONS:
            for f in base.parent.glob(base.name + "*" + ext):
                if f.exists():
                    f.unlink()

        # JSON-Metadaten (yt-dlp .info.json)
        for pattern in [".info.json", ".meta.json"]:
            f = base.parent / (base.name + pattern)
            if f.exists():
                f.unlink()

    async def _resolve_channel_id(self, channel_name: str) -> Optional[str]:
        """Channel-Name → Channel-ID aus Subscriptions auflösen."""
        if not channel_name:
            return None
        row = await db.fetch_one(
            "SELECT channel_id FROM subscriptions WHERE channel_name = ? COLLATE NOCASE",
            (channel_name,)
        )
        return row["channel_id"] if row else None

    def _cleanup_empty_dirs(self, root: Path) -> int:
        """Leere Unterordner rekursiv entfernen. Gibt Anzahl zurück."""
        if not root.exists() or not root.is_dir():
            return 0
        removed = 0
        # os.walk bottom-up: tiefste Ordner zuerst
        for dirpath, dirnames, filenames in os.walk(str(root), topdown=False):
            dp = Path(dirpath)
            if dp == root:
                continue
            try:
                if not any(dp.iterdir()):
                    dp.rmdir()
                    removed += 1
            except OSError:
                pass
        return removed

    async def _link_file_to_entry(
        self, file_path: str, video_id: str,
        title: str, channel_name: str, duration: int,
        file_size: int, thumbnail_path: str = None,
    ):
        """Datei mit bestehendem Video oder RSS-Entry verknüpfen."""
        from app.utils.file_utils import now_sqlite

        # Prüfen ob Video existiert
        existing = await db.fetch_one(
            "SELECT id, source FROM videos WHERE id = ?", (video_id,)
        )

        if existing:
            # Video existiert → file_path aktualisieren
            await db.execute(
                """UPDATE videos SET file_path = ?, file_size = ?,
                   status = 'ready' WHERE id = ?""",
                (file_path, file_size, video_id)
            )
        else:
            # RSS-Entry → neues Video anlegen mit verlinkter ID
            await self.import_video(
                file_path=file_path,
                title=title,
                channel_name=channel_name,
                youtube_id=video_id,
                source="imported",
                thumbnail_path=thumbnail_path,
                duration=duration,
                generate_thumbnail=not bool(thumbnail_path),
            )

    async def get_scan_sessions(self) -> list:
        """Alle Scan-Sessions auflisten."""
        rows = await db.fetch_all(
            """SELECT s.*,
                      (SELECT COUNT(*) FROM scan_staging WHERE session_id = s.id) as staged_count,
                      (SELECT COUNT(*) FROM scan_staging WHERE session_id = s.id AND decision IS NOT NULL) as decided_count
               FROM scan_sessions s
               ORDER BY s.created_at DESC
               LIMIT 20"""
        )
        return [dict(r) for r in rows]

    async def delete_scan_session(self, session_id: int) -> dict:
        """Scan-Session und zugehörige Staging-Daten löschen."""
        await db.execute("DELETE FROM scan_staging WHERE session_id = ?", (session_id,))
        await db.execute("DELETE FROM scan_sessions WHERE id = ?", (session_id,))
        return {"deleted": session_id}

    # ─── NFO-Parsing ──────────────────────────────────────────

    def _find_and_parse_nfo(self, base: Path) -> Optional[dict]:
        """NFO-Datei suchen und parsen (Jellyfin/Kodi-Format)."""
        # Mögliche NFO-Pfade
        candidates = [
            base.with_suffix(".nfo"),
            base.parent / (base.name + ".nfo"),
        ]

        for nfo_path in candidates:
            if nfo_path.exists():
                try:
                    return self._parse_nfo(nfo_path)
                except Exception as e:
                    logger.warning(f"NFO-Parse-Fehler {nfo_path}: {e}")

        return None

    def _parse_nfo(self, path: Path) -> dict:
        """Jellyfin/Kodi NFO-XML parsen."""
        tree = ET.parse(str(path))
        root = tree.getroot()

        result = {}

        # Titel
        title_el = root.find("title")
        if title_el is not None and title_el.text:
            result["title"] = title_el.text.strip()

        # Plot/Beschreibung
        plot_el = root.find("plot")
        if plot_el is not None and plot_el.text:
            result["description"] = plot_el.text.strip()

        # Datum
        date_el = root.find("dateadded")
        if date_el is not None and date_el.text:
            result["date_added"] = date_el.text.strip()

        # Runtime (Minuten)
        runtime_el = root.find("runtime")
        if runtime_el is not None and runtime_el.text:
            try:
                result["duration"] = int(runtime_el.text.strip()) * 60  # → Sekunden
            except ValueError:
                pass

        # DurationInSeconds (genauer)
        dur_sec = root.find(".//durationinseconds")
        if dur_sec is not None and dur_sec.text:
            try:
                result["duration"] = int(dur_sec.text.strip())
            except ValueError:
                pass

        # Video-Details
        video_el = root.find(".//video")
        if video_el is not None:
            w = video_el.findtext("width")
            h = video_el.findtext("height")
            if w and h:
                result["resolution"] = f"{w}x{h}"
            c = video_el.findtext("codec")
            if c:
                result["codec"] = c

        # Poster/Thumbnail
        poster_el = root.find(".//poster")
        if poster_el is not None and poster_el.text:
            result["poster_path"] = poster_el.text.strip()

        # Genre → Tags
        genres = root.findall("genre")
        if genres:
            result["genres"] = [g.text.strip() for g in genres if g.text]

        # Channel/Studio
        studio_el = root.find("studio")
        if studio_el is not None and studio_el.text:
            result["channel"] = studio_el.text.strip()

        return result

    # ─── Companion-Dateien ────────────────────────────────────

    def _find_thumbnail(self, base: Path, directory: Path) -> Optional[str]:
        """Thumbnail-Datei suchen (Jellyfin-Pattern)."""
        # Exakter Match: video-poster.jpg, video-thumb.png, etc.
        for suffix in THUMB_PATTERNS:
            for ext in IMAGE_EXTENSIONS:
                candidate = base.parent / (base.name + suffix + ext)
                if candidate.exists():
                    return str(candidate)

        # Gleicher Name, Bild-Extension
        for ext in IMAGE_EXTENSIONS:
            candidate = base.with_suffix(ext)
            if candidate.exists():
                return str(candidate)

        # folder.jpg / poster.jpg im gleichen Verzeichnis
        for name in ["poster", "folder", "thumb", "cover"]:
            for ext in IMAGE_EXTENSIONS:
                candidate = directory / (name + ext)
                if candidate.exists():
                    return str(candidate)

        return None

    def _find_description(self, base: Path) -> Optional[str]:
        """Beschreibungsdatei suchen (.txt, .description)."""
        for ext in [".txt", ".description", ".desc"]:
            candidate = base.with_suffix(ext)
            if candidate.exists():
                try:
                    text = candidate.read_text(encoding="utf-8", errors="replace")
                    return text.strip()[:5000]  # Max 5000 Zeichen
                except Exception:
                    pass
        return None

    def _find_subtitles(self, base: Path) -> list:
        """Untertitel-Dateien suchen."""
        found = []
        for ext in SUBTITLE_EXTENSIONS:
            # video.srt, video.de.srt, video.en.srt
            for candidate in base.parent.glob(base.name + "*" + ext):
                found.append(str(candidate))
        return found

    # ─── FFprobe ──────────────────────────────────────────────

    def _ffprobe(self, filepath: Path) -> Optional[dict]:
        """Video-Metadaten per FFprobe extrahieren."""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", "-show_streams", str(filepath)],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                return None

            probe = json.loads(result.stdout)
            fmt = probe.get("format", {})

            duration = None
            resolution = None
            codec = None

            dur = fmt.get("duration")
            if dur:
                duration = int(float(dur))

            for s in probe.get("streams", []):
                if s.get("codec_type") == "video":
                    w = s.get("width")
                    h = s.get("height")
                    if w and h:
                        resolution = f"{w}x{h}"
                    codec = s.get("codec_name")
                    if not duration:
                        d = s.get("duration")
                        if d:
                            duration = int(float(d))
                    break

            return {"duration": duration, "resolution": resolution, "codec": codec}
        except Exception as e:
            logger.warning(f"FFprobe fehlgeschlagen für {filepath}: {e}")
            return None

    # ─── Thumbnail-Erzeugung ──────────────────────────────────

    async def _copy_thumbnail(self, src: str, video_id: str) -> Optional[str]:
        """Thumbnail aus Companion-Datei kopieren."""
        try:
            src_path = Path(src)
            ext = src_path.suffix.lower()
            if ext not in IMAGE_EXTENSIONS:
                ext = ".jpg"
            dest = THUMBNAILS_DIR / f"{video_id}{ext}"
            # Pillow für Resize
            from PIL import Image
            img = Image.open(str(src_path))
            img.thumbnail((640, 360), Image.Resampling.LANCZOS)
            img.save(str(dest), quality=85)
            return str(dest)
        except Exception as e:
            logger.warning(f"Thumbnail-Kopie fehlgeschlagen: {e}")
            return None

    async def _generate_thumbnail(self, video_path: str, video_id: str) -> Optional[str]:
        """Thumbnail per FFmpeg aus Video generieren (Frame bei 25%)."""
        try:
            dest = THUMBNAILS_DIR / f"{video_id}.jpg"
            # Erst Dauer ermitteln
            probe = self._ffprobe(Path(video_path))
            duration = probe.get("duration", 60) if probe else 60
            seek = max(1, duration // 4)

            subprocess.run(
                ["ffmpeg", "-ss", str(seek), "-i", str(video_path),
                 "-vframes", "1", "-vf", "scale=640:-1",
                 "-q:v", "3", str(dest), "-y"],
                capture_output=True, timeout=30
            )
            if dest.exists() and dest.stat().st_size > 0:
                return str(dest)
        except Exception as e:
            logger.warning(f"Thumbnail-Generierung fehlgeschlagen: {e}")
        return None

    # ─── YouTube-ID Extraktion ────────────────────────────────

    def _extract_youtube_id(self, filename: str) -> Optional[str]:
        """YouTube-ID aus Dateiname extrahieren.
        Patterns: '[dQw4w9WgXcQ]', '(dQw4w9WgXcQ)', '-dQw4w9WgXcQ.mp4'
        """
        # [ID] Pattern (yt-dlp Standard)
        m = re.search(r'\[([a-zA-Z0-9_-]{11})\]', filename)
        if m:
            return m.group(1)

        # (ID) Pattern
        m = re.search(r'\(([a-zA-Z0-9_-]{11})\)', filename)
        if m:
            return m.group(1)

        # -ID.ext Pattern (am Ende vor Extension)
        m = re.search(r'-([a-zA-Z0-9_-]{11})\.[a-zA-Z0-9]+$', filename)
        if m:
            return m.group(1)

        return None

    # ─── Fuzzy-Matching ───────────────────────────────────────

    def _fuzzy_match_title(
        self, title: str, rss_titles: list, video_titles: list,
        channel_name: str = None, file_duration: int = None,
    ) -> Optional[dict]:
        """Titel gegen RSS-Entries und existierende Videos matchen.
        Duration-Vergleich als zusätzliches Signal:
        - ±5 Sek → +0.15 Confidence
        - ±30 Sek → neutral
        - >60 Sek Abweichung → -0.10 Confidence
        Gibt besten Match + Kandidaten-Liste zurück."""
        from rapidfuzz import fuzz

        if not title or len(title) < 3:
            return None

        all_candidates = []

        # Gegen RSS-Entries matchen
        for entry in rss_titles:
            score = fuzz.token_sort_ratio(title, entry["title"]) / 100.0

            # Bonus wenn Kanal übereinstimmt
            ch_bonus = False
            if channel_name and entry.get("channel_name"):
                ch_score = fuzz.token_sort_ratio(channel_name, entry["channel_name"]) / 100.0
                if ch_score >= 0.6:
                    score = min(1.0, score + 0.15)
                    ch_bonus = True

            # Duration-Vergleich
            dur_bonus = False
            dur_penalty = False
            entry_dur = entry.get("duration")
            if file_duration and entry_dur:
                diff = abs(file_duration - entry_dur)
                if diff <= 5:
                    score = min(1.0, score + 0.15)
                    dur_bonus = True
                elif diff > 60:
                    score = max(0.0, score - 0.10)
                    dur_penalty = True

            if score >= 0.4:
                all_candidates.append({
                    "type": "rss",
                    "id": entry["video_id"],
                    "title": entry["title"],
                    "channel": entry.get("channel_name"),
                    "confidence": round(score, 2),
                    "channel_boost": ch_bonus,
                    "duration_boost": dur_bonus,
                    "duration_penalty": dur_penalty,
                    "match_duration": entry_dur,
                })

        # Gegen existierende Videos matchen
        for vid in video_titles:
            score = fuzz.token_sort_ratio(title, vid["title"]) / 100.0

            ch_bonus = False
            if channel_name and vid.get("channel_name"):
                ch_score = fuzz.token_sort_ratio(channel_name, vid["channel_name"]) / 100.0
                if ch_score >= 0.6:
                    score = min(1.0, score + 0.15)
                    ch_bonus = True

            # Duration-Vergleich
            dur_bonus = False
            dur_penalty = False
            vid_dur = vid.get("duration")
            if file_duration and vid_dur:
                diff = abs(file_duration - vid_dur)
                if diff <= 5:
                    score = min(1.0, score + 0.15)
                    dur_bonus = True
                elif diff > 60:
                    score = max(0.0, score - 0.10)
                    dur_penalty = True

            if score >= 0.4:
                all_candidates.append({
                    "type": "video",
                    "id": vid["id"],
                    "title": vid["title"],
                    "channel": vid.get("channel_name"),
                    "confidence": round(score, 2),
                    "channel_boost": ch_bonus,
                    "duration_boost": dur_bonus,
                    "duration_penalty": dur_penalty,
                    "match_duration": vid_dur,
                })

        # Nach Score sortieren, Top-5
        all_candidates.sort(key=lambda c: c["confidence"], reverse=True)

        if not all_candidates:
            return None

        best = all_candidates[0]
        if best["confidence"] < 0.5:
            # Kein Match stark genug, aber Kandidaten mitgeben
            best_result = None
        else:
            best_result = {
                "type": best["type"],
                "id": best["id"],
                "title": best["title"],
                "channel": best.get("channel"),
                "confidence": best["confidence"],
                "duration_boost": best.get("duration_boost", False),
                "duration_penalty": best.get("duration_penalty", False),
                "match_duration": best.get("match_duration"),
            }

        # Kandidaten als Extra-Info (max 5)
        if best_result:
            best_result["candidates"] = all_candidates[:5]
        elif all_candidates:
            # Kein guter Match, aber Kandidaten trotzdem zurückgeben
            return {
                "type": all_candidates[0]["type"],
                "id": all_candidates[0]["id"],
                "title": all_candidates[0]["title"],
                "channel": all_candidates[0].get("channel"),
                "confidence": all_candidates[0]["confidence"],
                "duration_boost": all_candidates[0].get("duration_boost", False),
                "duration_penalty": all_candidates[0].get("duration_penalty", False),
                "match_duration": all_candidates[0].get("match_duration"),
                "candidates": all_candidates[:5],
                "weak": True,
            }

        return best_result

    async def _match_by_youtube_id(self, yt_id: str) -> Optional[dict]:
        """Exaktes Matching über YouTube-ID."""
        # In Videos
        vid = await db.fetch_one(
            "SELECT id, title, channel_name FROM videos WHERE id = ?", (yt_id,)
        )
        if vid:
            return {
                "type": "video",
                "id": vid["id"],
                "title": vid["title"],
                "channel": vid["channel_name"],
                "confidence": 1.0,
            }

        # In RSS-Entries
        rss = await db.fetch_one(
            """SELECT r.video_id, r.title, s.channel_name
               FROM rss_entries r
               JOIN subscriptions s ON r.channel_id = s.channel_id
               WHERE r.video_id = ?""",
            (yt_id,)
        )
        if rss:
            return {
                "type": "rss",
                "id": rss["video_id"],
                "title": rss["title"],
                "channel": rss["channel_name"],
                "confidence": 1.0,
            }

        return None

    # ─── Daten laden für Matching ─────────────────────────────

    async def _load_rss_titles(self) -> list:
        """RSS-Entry-Titel + Duration für Matching laden."""
        rows = await db.fetch_all(
            """SELECT r.video_id, r.title, s.channel_name, r.duration
               FROM rss_entries r
               JOIN subscriptions s ON r.channel_id = s.channel_id
               WHERE r.title IS NOT NULL"""
        )
        return [{"video_id": r["video_id"], "title": r["title"],
                 "channel_name": r["channel_name"],
                 "duration": r["duration"]} for r in rows]

    async def _load_video_titles(self) -> list:
        """Existierende Video-Titel + Duration für Matching laden."""
        rows = await db.fetch_all(
            "SELECT id, title, channel_name, duration FROM videos WHERE title IS NOT NULL"
        )
        return [{"id": r["id"], "title": r["title"],
                 "channel_name": r["channel_name"],
                 "duration": r["duration"]} for r in rows]

    async def _load_subscriptions(self) -> list:
        """Abonnements laden für Kanal-Matching."""
        rows = await db.fetch_all(
            "SELECT channel_id, channel_name FROM subscriptions"
        )
        return [{"channel_id": r["channel_id"],
                 "channel_name": r["channel_name"]} for r in rows]

    def _find_channel_match(self, folder_name: str, subscriptions: list) -> Optional[dict]:
        """Ordnernamen gegen Abonnements matchen."""
        from rapidfuzz import fuzz

        if not folder_name:
            return None

        for sub in subscriptions:
            score = fuzz.token_sort_ratio(folder_name, sub["channel_name"]) / 100.0
            if score >= 0.6:
                return {
                    "channel_id": sub["channel_id"],
                    "channel_name": sub["channel_name"],
                    "confidence": round(score, 2),
                }

        return None

    async def _subscribe_channel(self, channel_name: str):
        """Neues Abo für Kanalnamen anlegen (nur Platzhalter, ohne channel_id)."""
        existing = await db.fetch_one(
            "SELECT id FROM subscriptions WHERE channel_name = ?",
            (channel_name,)
        )
        if existing:
            return

        await db.execute(
            """INSERT INTO subscriptions (channel_id, channel_name, enabled)
               VALUES (?, ?, 1)""",
            (f"import_{uuid.uuid4().hex[:8]}", channel_name)
        )
        logger.info(f"Kanal aus Import abonniert: {channel_name}")


# Singleton
import_service = ImportService()

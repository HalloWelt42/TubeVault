"""
TubeVault - Diagnose eines Kanals (Reiter "Diagnose" der Kanalseite)

Zwei Fragen:
  - Liegen zu allen geladenen Videos die Dateien vor: Video, Vorschaubild
    und die Begleitdateien, aus denen sich die Datenbank neu aufbauen lässt
    (info.json, Beschreibung, Kapitel)? Inhalte gehören als Datei auf die
    Platte, die Datenbank ist Index und Suche (Nutzerentscheidung 16.10.2026).
  - Wie vollständig ist der Katalog des Kanals?

Geprüft werden alle Videos, im eigenen Faden, damit die Ereignisschleife
frei bleibt. Ersetzt die alte Dateiprüfung, die nur die ersten 100 Videos
ansah und Vorschaubilder am falschen Ort suchte.
"""
import asyncio
import os
from typing import Optional

from pydantic import BaseModel

from app.config import AVATARS_DIR, BANNERS_DIR, SUBTITLES_DIR
from app.database import db
from app.services import meta_sidecar
from app.services.storage import storage


class FileCount(BaseModel):
    present: int = 0
    total: int = 0


class ChannelFiles(BaseModel):
    videos: FileCount
    thumbnails: FileCount
    sidecars: FileCount                 # info.json neben dem Video
    descriptions: FileCount             # nur Videos mit Beschreibung
    chapters: FileCount                 # nur Videos mit Kapiteln
    subtitles: int                      # Videos mit Untertiteln
    avatar: bool
    banner: bool


class CatalogHealth(BaseModel):
    entries: int
    videos: int
    shorts: int
    live: int
    no_duration: int
    no_views: int
    no_description: int
    no_title: int
    last_scanned: Optional[str] = None
    scan_running: bool = False


class ChannelDiagnosis(BaseModel):
    files: ChannelFiles
    catalog: CatalogHealth


def _exists(path) -> bool:
    try:
        return bool(path) and os.path.exists(path)
    except (OSError, ValueError):
        return False


def _has_subtitles(folder: str) -> bool:
    """Ein Verzeichnis lesen statt glob: bei tausenden Videos spürbar schneller."""
    try:
        return any(name.endswith(".vtt") for name in os.listdir(folder))
    except OSError:
        return False


def _count_files(rows: list) -> dict:
    """Zählt vorhandene Dateien je Art (läuft im eigenen Faden)."""
    counts = {key: FileCount() for key in ("videos", "thumbnails", "sidecars", "descriptions", "chapters")}
    subtitles = 0
    for row in rows:
        video_id = row["id"]
        for key, present in (("videos", _exists(row["file_path"])),
                             ("thumbnails", _exists(row["thumbnail_path"])),
                             ("sidecars", _exists(meta_sidecar.sidecar_path(video_id)))):
            counts[key].total += 1
            counts[key].present += present
        if row["has_description"]:
            counts["descriptions"].total += 1
            counts["descriptions"].present += _exists(storage.text_file(video_id, "description"))
        if row["has_chapters"]:
            counts["chapters"].total += 1
            counts["chapters"].present += _exists(storage.text_file(video_id, "chapters"))
        subtitles += _has_subtitles(os.path.join(SUBTITLES_DIR, video_id))
    return {**counts, "subtitles": subtitles}


async def files_of(channel_id: str) -> ChannelFiles:
    rows = await db.fetch_all(
        """SELECT v.id, v.file_path, v.thumbnail_path,
                  (COALESCE(v.description, '') <> ''
                   OR EXISTS (SELECT 1 FROM text_files t WHERE t.video_id = v.id AND t.kind = 'description')) AS has_description,
                  EXISTS (SELECT 1 FROM chapters c WHERE c.video_id = v.id) AS has_chapters
           FROM videos v
           WHERE v.status = 'ready'
             AND (v.channel_id = ? OR v.id IN (SELECT video_id FROM rss_entries WHERE channel_id = ?))""",
        (channel_id, channel_id))
    counted = await asyncio.to_thread(_count_files, [dict(row) for row in rows])
    return ChannelFiles(**counted,
                        avatar=_exists(AVATARS_DIR / f"{channel_id}.jpg"),
                        banner=_exists(BANNERS_DIR / f"{channel_id}.jpg"))


async def catalog_of(channel_id: str) -> CatalogHealth:
    row = await db.fetch_one(
        """SELECT COUNT(*) AS entries,
                  COALESCE(SUM(COALESCE(video_type, 'video') = 'video'), 0) AS videos,
                  COALESCE(SUM(video_type = 'short'), 0) AS shorts,
                  COALESCE(SUM(video_type = 'live'), 0) AS live,
                  COALESCE(SUM(duration IS NULL), 0) AS no_duration,
                  COALESCE(SUM(views IS NULL), 0) AS no_views,
                  COALESCE(SUM(COALESCE(description, '') = ''), 0) AS no_description,
                  COALESCE(SUM(COALESCE(title, '') = ''), 0) AS no_title
           FROM rss_entries WHERE channel_id = ?""", (channel_id,))
    last_scanned = await db.fetch_val("SELECT last_scanned FROM subscriptions WHERE channel_id = ?", (channel_id,))
    scan_running = await db.fetch_val(
        """SELECT 1 FROM jobs WHERE type = 'channel_scan' AND status IN ('queued', 'active')
           AND json_extract(metadata, '$.channel_id') = ? LIMIT 1""", (channel_id,))
    return CatalogHealth(**dict(row), last_scanned=last_scanned, scan_running=bool(scan_running))


async def diagnose(channel_id: str) -> ChannelDiagnosis:
    return ChannelDiagnosis(files=await files_of(channel_id), catalog=await catalog_of(channel_id))

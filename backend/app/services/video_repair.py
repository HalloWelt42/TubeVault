"""
TubeVault – Video nachbessern

Vorschaubild und Angaben eines einzelnen Videos von Hand erneuern (Bedienung:
Bearbeiten-Bereich der Wiedergabeseite).
"""
import asyncio
import logging
from pathlib import Path

from app.config import THUMBNAILS_DIR
from app.database import db
from app.utils.file_utils import now_sqlite
from app.utils.thumbnail_utils import download_yt_thumbnail, generate_ffmpeg_thumbnail

logger = logging.getLogger(__name__)


class RepairError(Exception):
    """Nachbessern nicht möglich; die Meldung ist für den Nutzer."""


async def _video_file(video_id: str) -> tuple[Path, int | None]:
    video = await db.fetch_one(
        "SELECT file_path, duration FROM videos WHERE id = ?", (video_id,))
    if not video:
        raise RepairError("Video nicht gefunden")
    path = Path(video["file_path"]) if video["file_path"] else None
    if not path or not path.exists():
        raise RepairError("Video-Datei nicht gefunden")
    return path, video["duration"]


async def _store_thumbnail(video_id: str, thumbnail: Path | None) -> dict:
    if not thumbnail:
        raise RepairError("Vorschaubild konnte nicht erstellt werden")
    await db.execute(
        "UPDATE videos SET thumbnail_path = ?, updated_at = ? WHERE id = ?",
        (str(thumbnail), now_sqlite(), video_id))
    return {"status": "ok", "thumbnail_path": str(thumbnail)}


async def thumbnail_from_file(video_id: str, position: int | None = None) -> dict:
    """Vorschaubild aus der Videodatei erzeugen - an der genannten Stelle
    (Sekunden) oder an einer passenden Stelle nach Dauer."""
    path, duration = await _video_file(video_id)
    destination = THUMBNAILS_DIR / f"{video_id}.jpg"
    if position is None:
        thumbnail = generate_ffmpeg_thumbnail(path, destination, duration=duration)
    else:
        thumbnail = generate_ffmpeg_thumbnail(path, destination, position=position)
    return await _store_thumbnail(video_id, thumbnail)


async def thumbnail_from_source(video_id: str) -> dict:
    """Vorschaubild der Quelle laden (ersetzt das vorhandene)."""
    thumbnail = await download_yt_thumbnail(video_id, THUMBNAILS_DIR, overwrite=True)
    if not thumbnail:
        raise RepairError("Die Quelle bietet kein Vorschaubild an")
    return await _store_thumbnail(video_id, thumbnail)


def _fetch_metadata(video_id: str) -> dict:
    """Synchron (im Thread): Angaben der Quelle zu einem Video."""
    from app.utils.pytube_client import make_youtube
    yt = make_youtube(f"https://www.youtube.com/watch?v={video_id}")
    updates = {
        "title": yt.title,
        "channel_name": yt.author,
        "channel_id": yt.channel_id,
        "description": yt.description,
        "duration": yt.length,
        "view_count": yt.views,
        "upload_date": yt.publish_date.strftime("%Y-%m-%d") if yt.publish_date else None,
    }
    return {key: value for key, value in updates.items() if value}


async def metadata_from_source(video_id: str) -> dict:
    """Titel, Kanal, Beschreibung, Dauer und Aufrufe von der Quelle übernehmen."""
    if video_id.startswith("local_"):
        raise RepairError("Eigenes Video ohne Quelle")
    video = await db.fetch_one("SELECT thumbnail_path FROM videos WHERE id = ?", (video_id,))
    if not video:
        raise RepairError("Video nicht gefunden")

    from app.services.rate_limiter import rate_limiter
    await rate_limiter.acquire("pytubefix")
    try:
        updates = await asyncio.to_thread(_fetch_metadata, video_id)
    except Exception as e:
        rate_limiter.error("pytubefix", str(e)[:200])
        raise RepairError(f"Die Quelle gab keine Auskunft: {str(e)[:200]}") from e
    rate_limiter.success("pytubefix")
    if not updates:
        raise RepairError("Die Quelle lieferte keine Angaben")

    if not video["thumbnail_path"] or not Path(video["thumbnail_path"]).exists():
        thumbnail = await download_yt_thumbnail(video_id, THUMBNAILS_DIR)
        if thumbnail:
            updates["thumbnail_path"] = str(thumbnail)
    updates["updated_at"] = now_sqlite()

    await db.execute(
        f"UPDATE videos SET {', '.join(f'{key} = ?' for key in updates)} WHERE id = ?",
        (*updates.values(), video_id))
    logger.info(f"Angaben von der Quelle übernommen für {video_id}: {list(updates)}")
    return {"status": "ok", "updated_fields": list(updates), "title": updates.get("title")}

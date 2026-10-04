"""
TubeVault – Aufräumen

Sichten zum Ausmisten des Bestands: Shorts, alle Videos eines Kanals, große
und lange nicht gesehene Videos. Jede Sicht liefert dieselbe Zeilenform, damit
die Oberfläche eine einzige Liste mit Vorschaubild und Mehrfachauswahl zeigt.
Gelöscht wird restlos über metadata_service.delete_video.
"""
from typing import Literal, Optional

from pydantic import BaseModel

from app.database import db
from app.services.metadata_service import metadata_service

View = Literal["shorts", "channel", "big"]

_COLUMNS = """v.id, v.title, v.channel_id, v.channel_name, v.duration, v.file_size,
              v.video_type, v.type_verified, v.is_archived, v.play_count, v.last_played,
              v.upload_date, v.download_date"""


class CleanupVideo(BaseModel):
    id: str
    title: Optional[str] = None
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    duration: Optional[int] = None
    file_size: Optional[int] = None
    video_type: Optional[str] = None
    type_verified: Optional[int] = None
    is_archived: Optional[int] = None
    play_count: Optional[int] = None
    last_played: Optional[str] = None
    upload_date: Optional[str] = None
    download_date: Optional[str] = None


class CleanupPage(BaseModel):
    videos: list[CleanupVideo]
    total: int
    total_bytes: int
    offset: int


class ChannelSize(BaseModel):
    channel_id: str
    channel_name: Optional[str] = None
    videos: int
    bytes: int


class DeleteResult(BaseModel):
    deleted: int
    freed_bytes: int
    missing: list[str] = []


def _where(view: View, channel_id: Optional[str]) -> tuple[str, list]:
    """Bedingung und Reihenfolge je Sicht."""
    if view == "shorts":
        return "v.status = 'ready' AND v.video_type = 'short'", []
    if view == "channel":
        if not channel_id:
            raise ValueError("Für diese Sicht wird ein Kanal gebraucht")
        return "v.status = 'ready' AND v.channel_id = ?", [channel_id]
    return "v.status = 'ready'", []


_ORDER = {
    "shorts": "v.download_date DESC, v.id",
    "channel": "v.upload_date DESC NULLS LAST, v.id",
    # Groß zuerst; bei gleicher Größe das am längsten nicht Gesehene
    "big": "COALESCE(v.file_size, 0) DESC, v.last_played ASC NULLS FIRST, v.id",
}


async def list_videos(view: View, channel_id: Optional[str] = None,
                      offset: int = 0, limit: int = 60) -> CleanupPage:
    """Eine Seite der Sicht. Versatz statt Seitennummer: nimmt die Oberfläche
    Einträge heraus (gelöscht, "kein Short"), lädt sie ab der tatsächlichen
    Zahl weiter und überspringt nichts."""
    where, params = _where(view, channel_id)
    summary = await db.fetch_one(
        f"SELECT COUNT(*) AS n, COALESCE(SUM(v.file_size), 0) AS bytes FROM videos v WHERE {where}",
        params)
    rows = await db.fetch_all(
        f"SELECT {_COLUMNS} FROM videos v WHERE {where} ORDER BY {_ORDER[view]} LIMIT ? OFFSET ?",
        [*params, limit, offset])
    return CleanupPage(videos=[CleanupVideo(**dict(r)) for r in rows], total=summary["n"],
                       total_bytes=summary["bytes"], offset=offset)


async def all_ids(view: View, channel_id: Optional[str] = None) -> list[str]:
    """Alle Video-IDs einer Sicht (für "alle auswählen" über alle Seiten)."""
    where, params = _where(view, channel_id)
    rows = await db.fetch_all(f"SELECT v.id FROM videos v WHERE {where} ORDER BY {_ORDER[view]}", params)
    return [r["id"] for r in rows]


async def channels() -> list[ChannelSize]:
    """Kanäle mit geladenen Videos, größter Platzbedarf zuerst."""
    rows = await db.fetch_all(
        """SELECT v.channel_id, MAX(v.channel_name) AS channel_name,
                  COUNT(*) AS videos, COALESCE(SUM(v.file_size), 0) AS bytes
           FROM videos v WHERE v.status = 'ready' AND v.channel_id IS NOT NULL
           GROUP BY v.channel_id ORDER BY bytes DESC""")
    return [ChannelSize(**dict(r)) for r in rows]


async def delete(video_ids: list[str]) -> DeleteResult:
    """Videos restlos löschen. Sie landen auf der Ignorierliste, damit der
    Auto-Download sie nicht von selbst zurückholt."""
    ids = list(dict.fromkeys(video_ids))
    if not ids:
        return DeleteResult(deleted=0, freed_bytes=0)
    marks = ",".join("?" * len(ids))
    sizes = {r["id"]: r["file_size"] or 0 for r in await db.fetch_all(
        f"SELECT id, file_size FROM videos WHERE id IN ({marks})", ids)}
    deleted, freed, missing = 0, 0, []
    for video_id in ids:
        if await metadata_service.delete_video(video_id, ignore_for_future=True):
            deleted += 1
            freed += sizes.get(video_id, 0)
        else:
            missing.append(video_id)
    return DeleteResult(deleted=deleted, freed_bytes=freed, missing=missing)

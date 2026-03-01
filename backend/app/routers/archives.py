"""
TubeVault -  Archives Router v1.1.0
Externes Archiv-Management API
© HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.services.archive_service import archive_service

router = APIRouter(prefix="/api/archives", tags=["Archive"])


class ArchiveCreate(BaseModel):
    name: str
    mount_path: str
    auto_scan: bool = True
    scan_pattern: Optional[str] = None


class ArchiveUpdate(BaseModel):
    name: Optional[str] = None
    auto_scan: Optional[bool] = None
    scan_pattern: Optional[str] = None
    enabled: Optional[bool] = None


@router.get("")
async def get_archives():
    """Alle Archive mit aktuellem Mount-Status."""
    return await archive_service.get_archives()


@router.post("")
async def add_archive(data: ArchiveCreate):
    """Neues Archiv registrieren."""
    try:
        return await archive_service.add_archive(
            name=data.name,
            mount_path=data.mount_path,
            auto_scan=data.auto_scan,
            scan_pattern=data.scan_pattern,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{archive_id}")
async def get_archive(archive_id: int):
    """Einzelnes Archiv mit Status."""
    archive = await archive_service.get_archive(archive_id)
    if not archive:
        raise HTTPException(status_code=404, detail="Archiv nicht gefunden")
    return archive


@router.delete("/{archive_id}")
async def remove_archive(archive_id: int):
    """Archiv entfernen."""
    await archive_service.remove_archive(archive_id)
    return {"deleted": True}


@router.post("/{archive_id}/scan")
async def scan_archive(archive_id: int):
    """Archiv nach Videos durchsuchen."""
    try:
        return await archive_service.scan_archive(archive_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{archive_id}/videos")
async def get_archive_videos(archive_id: int, page: int = 1, per_page: int = 50):
    """Videos in einem Archiv auflisten."""
    from app.database import db
    offset = (page - 1) * per_page
    rows = await db.fetch_all(
        """SELECT v.*, va.file_path as archive_path, va.file_size as archive_file_size
           FROM video_archives va
           JOIN videos v ON va.video_id = v.id
           WHERE va.archive_id = ?
           ORDER BY v.title
           LIMIT ? OFFSET ?""",
        (archive_id, per_page, offset)
    )
    total = await db.fetch_val(
        "SELECT COUNT(*) FROM video_archives WHERE archive_id = ?", (archive_id,)
    )
    return {"videos": [dict(r) for r in rows], "total": total or 0, "page": page}


@router.get("/check/mounts")
async def check_mounts():
    """Alle Mounts prüfen und Status zurückgeben."""
    changed = await archive_service.check_all_mounts()
    archives = await archive_service.get_archives()
    return {
        "archives": archives,
        "changed": changed,
    }


@router.get("/video/{video_id}/resolve")
async def resolve_video_path(video_id: str):
    """Prüft ob und wo ein Video verfügbar ist."""
    return await archive_service.resolve_video_path(video_id)


@router.get("/video/{video_id}/duplicate")
async def check_duplicate(video_id: str):
    """Prüft ob Video in irgendeinem Archiv existiert."""
    result = await archive_service.check_duplicate(video_id)
    return {"exists": result is not None, "archive": result}

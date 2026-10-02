"""
TubeVault – Video nachbessern (Router)
Vorschaubild und Angaben eines Videos von Hand erneuern.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.services import video_repair
from app.services.video_repair import RepairError

router = APIRouter(prefix="/api/video-repair", tags=["Video nachbessern"])


async def _run(action):
    try:
        return await action
    except RepairError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/{video_id}/thumbnail-from-file")
async def thumbnail_from_file(video_id: str, position: Optional[int] = Query(None, ge=0)):
    """Vorschaubild aus der Videodatei erzeugen (optional an einer Stelle in Sekunden)."""
    return await _run(video_repair.thumbnail_from_file(video_id, position))


@router.post("/{video_id}/thumbnail-from-source")
async def thumbnail_from_source(video_id: str):
    """Vorschaubild der Quelle laden (ersetzt das vorhandene)."""
    return await _run(video_repair.thumbnail_from_source(video_id))


@router.post("/{video_id}/metadata-from-source")
async def metadata_from_source(video_id: str):
    """Titel, Kanal, Beschreibung, Dauer und Aufrufe von der Quelle übernehmen."""
    return await _run(video_repair.metadata_from_source(video_id))

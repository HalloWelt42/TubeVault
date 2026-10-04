"""
TubeVault – Aufräumen (Router)
Sichten zum Ausmisten und restloses Löschen in Mengen.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services import cleanup

router = APIRouter(prefix="/api/admin/cleanup", tags=["Aufräumen"])

# Je Aufruf gelöscht; größere Mengen schickt die Oberfläche in Teilen
MAX_DELETE_PER_CALL = 100


class DeleteRequest(BaseModel):
    video_ids: list[str] = Field(min_length=1, max_length=MAX_DELETE_PER_CALL)


@router.get("/videos", response_model=cleanup.CleanupPage)
async def cleanup_videos(view: cleanup.View, channel_id: Optional[str] = None,
                         offset: int = Query(0, ge=0), limit: int = Query(60, ge=1, le=200)):
    try:
        return await cleanup.list_videos(view, channel_id, offset, limit)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/ids", response_model=list[str])
async def cleanup_ids(view: cleanup.View, channel_id: Optional[str] = None):
    try:
        return await cleanup.all_ids(view, channel_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/channels", response_model=list[cleanup.ChannelSize])
async def cleanup_channels():
    return await cleanup.channels()


@router.post("/delete", response_model=cleanup.DeleteResult)
async def cleanup_delete(request: DeleteRequest):
    return await cleanup.delete(request.video_ids)

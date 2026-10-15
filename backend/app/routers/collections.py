"""
TubeVault – Sammlungen und Stand

Favoritenlisten und Playlists einheitlich lesen (mit Stand je Video) und
Videos als gesehen oder neu markieren.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services import collections, watch_state
from app.services.collections import Collection

router = APIRouter(prefix="/api/collections", tags=["Sammlungen"])


class WatchedRequest(BaseModel):
    video_ids: list[str]
    watched: bool


@router.get("", response_model=Collection)
async def get_collection(source: str = Query(..., min_length=3)):
    """favorites:<Liste> oder playlist:<Kennung>, in ihrer Reihenfolge."""
    try:
        return await collections.load(source)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/watched")
async def mark_watched(req: WatchedRequest):
    """Als gesehen (Stelle ans Ende) oder als neu markieren (Stelle vergessen)."""
    changed = await watch_state.set_watched(req.video_ids[:1000], req.watched)
    return {"changed": changed, "watched": req.watched}

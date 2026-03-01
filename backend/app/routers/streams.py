"""
TubeVault -  Streams Router v1.3.2
Stream-Analyse, Audio-Spuren, Kombinationen
© HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
"""

from fastapi import APIRouter, HTTPException
from app.services.stream_service import stream_service
from app.models.stream import StreamCombinationCreate

router = APIRouter(prefix="/api/streams", tags=["Streams"])


@router.post("/{video_id}/analyze")
async def analyze_video(video_id: str):
    """Video mit FFprobe analysieren und Streams in DB speichern."""
    try:
        result = await stream_service.analyze_video(video_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{video_id}")
async def get_streams(video_id: str):
    """Alle Streams eines Videos abrufen."""
    streams = await stream_service.get_streams(video_id)
    return {"streams": streams, "video_id": video_id}


@router.get("/{video_id}/combinations")
async def get_combinations(video_id: str):
    """Stream-Kombinationen abrufen."""
    combos = await stream_service.get_combinations(video_id)
    return {"combinations": combos}


@router.post("/{video_id}/combinations")
async def create_combination(video_id: str, data: StreamCombinationCreate):
    """Stream-Kombination speichern."""
    result = await stream_service.save_combination(
        video_id, data.name, data.video_stream_id,
        data.audio_stream_id, data.audio_offset_ms, data.is_default
    )
    return result


@router.delete("/combinations/{combo_id}")
async def delete_combination(combo_id: int):
    """Stream-Kombination löschen."""
    await stream_service.delete_combination(combo_id)
    return {"deleted": True}

"""
TubeVault – Transkripte (Router)
Stand der Transkripte und die Warteliste der KI-Transkripte für den
Nachvertoner (eigenes Programm auf einem leistungsfähigen Rechner).
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import transcripts

router = APIRouter(prefix="/api/transcripts", tags=["Transkripte"])


class ClaimRequest(BaseModel):
    worker: str


class ProgressRequest(BaseModel):
    note: Optional[str] = None


class FailRequest(BaseModel):
    note: str


@router.get("/status")
async def transcript_status():
    """Stand: Transkripte der Quelle und Warteliste der KI-Transkripte."""
    return {"transcripts": await transcripts.counts(), "ai": await transcripts.ai_counts()}


@router.post("/ai/claim")
async def claim_ai(request: ClaimRequest):
    """Nächsten KI-Auftrag abholen; request = null, wenn nichts wartet."""
    job = await transcripts.claim_ai(request.worker.strip() or "nachvertoner")
    if not job:
        return {"request": None}
    return {
        "request": job,
        "media_url": f"/api/player/{job.video_id}",
        "progress_url": f"/api/transcripts/ai/{job.video_id}/progress",
        "result_url": f"/api/transcripts/ai/{job.video_id}/result",
        "fail_url": f"/api/transcripts/ai/{job.video_id}/fail",
    }


@router.post("/ai/{video_id}/progress")
async def ai_progress(video_id: str, request: ProgressRequest):
    if not await transcripts.heartbeat_ai(video_id, request.note):
        raise HTTPException(status_code=409, detail="Auftrag ist nicht mehr in Arbeit")
    return {"ok": True}


@router.post("/ai/{video_id}/result")
async def ai_result(video_id: str, result: transcripts.AiResult):
    try:
        chunks = await transcripts.finish_ai(video_id, result)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"ok": True, "chunks": chunks}


@router.post("/ai/{video_id}/fail")
async def ai_fail(video_id: str, request: FailRequest):
    await transcripts.fail_ai(video_id, request.note)
    return {"ok": True}

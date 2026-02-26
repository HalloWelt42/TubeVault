"""
TubeVault -  Jobs Router v1.6.36
Unified Activity Tracking mit Pause/Resume
© HalloWelt42 -  Private Nutzung
"""

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.job_service import job_service
from app.database import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


@router.get("")
async def get_jobs(
    status: str = None,
    job_type: str = None,
    limit: int = 100,
):
    """Alle Jobs abrufen (filterbar)."""
    if status in ("active", "queued"):
        return await job_service.get_active(limit)
    return await job_service.get_recent(limit, job_type)


@router.get("/active")
async def get_active_jobs():
    """Nur aktive und wartende Jobs."""
    return await job_service.get_active()


@router.get("/stats")
async def get_job_stats():
    """Job-Statistiken inkl. Pause-Status."""
    return await job_service.get_stats()


@router.get("/queue/status")
async def get_queue_status():
    """Queue-Status: paused/running."""
    return job_service.get_queue_status()


@router.post("/queue/pause")
async def pause_queue(reason: str = "user"):
    """Queue pausieren -  laufende Jobs laufen fertig."""
    await job_service.pause_queue(reason)
    return {"paused": True, "reason": reason}


@router.post("/queue/resume")
async def resume_queue():
    """Queue fortsetzen."""
    await job_service.resume_queue()
    return {"paused": False}


@router.get("/{job_id}")
async def get_job(job_id: int):
    """Einzelnen Job abrufen."""
    job = await job_service.get(job_id)
    if not job:
        return {"error": "Job nicht gefunden"}
    return job


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: int):
    """Job abbrechen."""
    return await job_service.cancel(job_id)


@router.post("/{job_id}/pause")
async def pause_job(job_id: int):
    """Einzelnen Job pausieren."""
    job_service.pause_job(job_id)
    return {"paused": True, "job_id": job_id}


@router.post("/{job_id}/resume")
async def resume_job(job_id: int):
    """Einzelnen Job fortsetzen."""
    job_service.resume_job(job_id)
    return {"paused": False, "job_id": job_id}


@router.post("/{job_id}/unpark")
async def unpark_job(job_id: int):
    """Geparkten Job zurück in die Queue setzen."""
    job = await job_service.get(job_id)
    if not job:
        return {"error": "Job nicht gefunden"}
    if job["status"] not in ("parked", "error"):
        return {"error": f"Job hat Status '{job['status']}', nicht parked/error"}
    # Retry-Count zurücksetzen, zurück auf queued
    meta = json.loads(job.get("metadata") or "{}")
    meta["retry_count"] = 0
    meta.pop("retry_after", None)
    await db.execute(
        "UPDATE jobs SET status='queued', error_message=NULL, description=NULL, progress=0, metadata=? WHERE id=?",
        (json.dumps(meta), job_id)
    )
    return {"status": "queued", "job_id": job_id}


@router.post("/unpark-all")
async def unpark_all_jobs():
    """Alle geparkten Jobs zurück in die Queue."""
    rows = await db.fetch_all(
        "SELECT id, metadata FROM jobs WHERE type='download' AND status='parked'"
    )
    count = 0
    for row in rows:
        meta = json.loads(row.get("metadata") or row["metadata"] if isinstance(row, dict) else "{}")
        if isinstance(meta, str):
            meta = json.loads(meta)
        meta["retry_count"] = 0
        meta.pop("retry_after", None)
        await db.execute(
            "UPDATE jobs SET status='queued', error_message=NULL, description=NULL, progress=0, metadata=? WHERE id=?",
            (json.dumps(meta), row["id"])
        )
        count += 1
    return {"unparked": count}


@router.delete("/cleanup")
async def cleanup_jobs(max_age_hours: int = 24):
    """Alte abgeschlossene Jobs löschen."""
    await job_service.cleanup(max_age_hours)
    return {"cleaned": True}


@router.delete("/cleanup-all")
async def cleanup_all_jobs():
    """ALLE fertigen/fehlerhaften/abgebrochenen Jobs löschen."""
    count = await job_service.cleanup_all()
    return {"cleaned": True, "count": count}


# --- WebSocket für ALLE Echtzeit-Updates ---

class ActivityManager:
    """Verwaltet WebSocket-Verbindungen für Echtzeit-Aktivitäten."""

    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)
        logger.info(f"Activity-WS verbunden ({len(self.connections)} aktiv)")

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)
            logger.info(f"Activity-WS getrennt ({len(self.connections)} aktiv)")

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


activity_ws = ActivityManager()


@router.websocket("/ws")
async def jobs_websocket(websocket: WebSocket):
    """WebSocket: Alle Job-Updates in Echtzeit."""
    await activity_ws.connect(websocket)

    async def on_job_update(data: dict):
        await activity_ws.broadcast(data)

    job_service.add_callback(on_job_update)

    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        activity_ws.disconnect(websocket)
        job_service.remove_callback(on_job_update)

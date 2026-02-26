"""
TubeVault – Thumbnail AI Router v1.6.26
© HalloWelt42 – Private Nutzung

API-Endpunkte für Thumbnail-AI-Analyse via LM Studio Vision.
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.database import db

logger = logging.getLogger("tubevault.thumbnail_ai")
router = APIRouter(prefix="/api/thumbnail-ai", tags=["Thumbnail AI"])


def _get_service():
    from app.services.thumbnail_ai_service import thumbnail_ai
    return thumbnail_ai


# ─── Status ──────────────────────────────────────────────

@router.get("/status")
async def get_status():
    """AI Status + Verbindung + Queue-Count."""
    svc = _get_service()
    conn = await svc.check_connection()
    queue = await svc.get_queue_count()
    svc.status["queue_count"] = queue
    svc.status["running"] = svc._running
    return {
        "config": svc.config,
        "status": svc.status,
        "connection": conn,
    }


# ─── Config ──────────────────────────────────────────────

class AiConfigUpdate(BaseModel):
    lm_studio_url: Optional[str] = None
    model: Optional[str] = None
    enabled: Optional[bool] = None
    auto_analyze: Optional[bool] = None
    batch_size: Optional[int] = None
    interval_seconds: Optional[int] = None
    max_image_size: Optional[int] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None


@router.put("/config")
async def update_config(updates: AiConfigUpdate):
    """AI-Konfiguration aktualisieren."""
    svc = _get_service()
    changes = updates.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status_code=400, detail="Keine Änderungen")
    config = await svc.save_config(changes)
    return {"config": config}


@router.get("/config")
async def get_config():
    """Aktuelle AI-Konfiguration."""
    svc = _get_service()
    await svc.load_config()
    return svc.config


# ─── Queue starten / stoppen ─────────────────────────────

@router.post("/run")
async def run_queue():
    """Queue-Abarbeitung starten (alle unanalysierten Videos)."""
    svc = _get_service()
    result = await svc.run_queue()
    if result.get("error"):
        raise HTTPException(status_code=503, detail=result["error"])
    return result


@router.post("/stop")
async def stop_queue():
    """Laufende Abarbeitung stoppen."""
    svc = _get_service()
    return await svc.stop_queue()


# Legacy-Aliase
@router.post("/start")
async def start_worker():
    return await run_queue()

@router.post("/analyze/all-unanalyzed")
async def analyze_all():
    return await run_queue()


# ─── Einzelanalyse ───────────────────────────────────────

@router.post("/analyze/{video_id}")
async def analyze_single(video_id: str):
    """Einzelnes Video-Thumbnail analysieren (synchron)."""
    svc = _get_service()
    conn = await svc.check_connection()
    if not conn.get("connected"):
        raise HTTPException(status_code=503, detail=f"LM Studio nicht erreichbar: {conn.get('error', '?')}")
    result = await svc.analyze_video(video_id)
    return result


# ─── Batch (für Library Bulk) ────────────────────────────

class BulkAnalyzeRequest(BaseModel):
    video_ids: list[str]


@router.post("/analyze/batch")
async def analyze_batch(req: BulkAnalyzeRequest):
    """Ausgewählte Videos analysieren (async Task)."""
    svc = _get_service()
    conn = await svc.check_connection()
    if not conn.get("connected"):
        raise HTTPException(status_code=503, detail=f"LM Studio nicht erreichbar: {conn.get('error', '?')}")

    total = len(req.video_ids)
    svc.status["batch_total"] = total
    svc.status["batch_done"] = 0
    svc._running = True
    svc._add_log("info", f"▶ Batch-Analyse: {total} Videos")

    async def _run():
        try:
            for vid in req.video_ids:
                if not svc._running:
                    break
                await svc.analyze_video(vid)
                svc.status["queue_count"] = await svc.get_queue_count()
                await asyncio.sleep(0.5)
            done = svc.status["batch_done"]
            svc._add_log("info", f"■ Batch fertig: {done}/{total}")
        except Exception as e:
            svc._add_log("error", f"■ Batch-Fehler: {e}")
        finally:
            svc._running = False

    svc._task = asyncio.create_task(_run())
    return {"message": f"Batch gestartet ({total} Videos)", "total": total}


# ─── Log ─────────────────────────────────────────────────

@router.get("/log")
async def get_log(limit: int = Query(50, ge=1, le=500)):
    """Analyse-Log abrufen."""
    svc = _get_service()
    return {"log": svc.get_log(limit), "status": svc.status}


# ─── Queue Info + Reset ──────────────────────────────────

@router.get("/queue")
async def get_queue():
    """Queue-Info: Nächste Videos in der Queue."""
    svc = _get_service()
    count = await svc.get_queue_count()
    svc.status["queue_count"] = count

    # Fehlerhafte zählen
    error_count = await db.fetch_val(
        "SELECT COUNT(*) FROM videos WHERE ai_analysis LIKE '%\"error\"%'"
    ) or 0
    rss_error = await db.fetch_val(
        "SELECT COUNT(*) FROM rss_entries WHERE ai_analysis LIKE '%\"error\"%'"
    ) or 0
    error_count += rss_error

    # Bereits analysierte zählen
    analyzed_count = await db.fetch_val(
        "SELECT COUNT(*) FROM videos WHERE ai_analysis IS NOT NULL AND ai_analysis NOT LIKE '%\"error\"%'"
    ) or 0

    next_batch = await svc.get_next_batch(10)
    next_details = []
    for vid in next_batch:
        row = await db.fetch_one(
            "SELECT id, title, channel_name, video_type FROM videos WHERE id = ?", (vid,)
        )
        if row:
            next_details.append(dict(row))
        else:
            rss = await db.fetch_one(
                "SELECT video_id as id, title, channel_id as channel_name FROM rss_entries WHERE video_id = ?", (vid,)
            )
            if rss:
                next_details.append({**dict(rss), "video_type": "unknown", "source": "rss"})

    return {"queue_count": count, "error_count": error_count, "analyzed_count": analyzed_count, "next": next_details}


@router.post("/queue/reset-all")
async def reset_queue_all():
    """Alle Analysen löschen → alles neu in Queue."""
    svc = _get_service()
    if svc._running:
        raise HTTPException(status_code=409, detail="Erst stoppen, dann zurücksetzen")
    return await svc.reset_queue_all()


@router.post("/queue/reset-errors")
async def reset_queue_errors():
    """Nur fehlerhafte Analysen zurücksetzen."""
    svc = _get_service()
    return await svc.reset_queue_errors()


@router.post("/queue/reset-recent")
async def reset_queue_recent(n: int = Query(100, ge=1, le=10000)):
    """Letzte N analysierte Videos zurücksetzen."""
    svc = _get_service()
    return await svc.reset_queue_recent(n)


# ─── Connection Test + Models ────────────────────────────

@router.post("/test-connection")
async def test_connection(url: str = Query(None)):
    """LM Studio Verbindung testen."""
    svc = _get_service()
    if url:
        svc.config["lm_studio_url"] = url
    conn = await svc.check_connection()
    return conn


@router.get("/models")
async def list_models():
    """Verfügbare Modelle aus LM Studio."""
    svc = _get_service()
    conn = await svc.check_connection()
    return {
        "models": conn.get("models", []),
        "active": svc.status.get("model", ""),
        "configured": svc.config.get("model", ""),
        "connected": conn.get("connected", False),
    }


# ─── Analyse-Ergebnis ───────────────────────────────────

@router.get("/result/{video_id}")
async def get_analysis(video_id: str):
    """Analyse-Ergebnis für ein Video."""
    import json as json_module
    row = await db.fetch_one(
        "SELECT ai_analysis, ai_analyzed_at FROM videos WHERE id = ?", (video_id,)
    )
    if not row or not row["ai_analysis"]:
        rss = await db.fetch_one(
            "SELECT ai_analysis FROM rss_entries WHERE video_id = ?", (video_id,)
        )
        if rss and rss["ai_analysis"]:
            return {"video_id": video_id, "analysis": json_module.loads(rss["ai_analysis"]), "source": "rss"}
        raise HTTPException(status_code=404, detail="Keine Analyse vorhanden")

    return {
        "video_id": video_id,
        "analysis": json_module.loads(row["ai_analysis"]),
        "analyzed_at": row["ai_analyzed_at"],
    }


# ─── Prompt ──────────────────────────────────────────────

@router.get("/prompt")
async def get_prompt():
    """Aktuellen Prompt abrufen."""
    svc = _get_service()
    from app.services.thumbnail_ai_service import DEFAULT_PROMPT
    current = await svc.get_prompt()
    return {
        "prompt": current,
        "is_default": current.strip() == DEFAULT_PROMPT.strip(),
        "default_prompt": DEFAULT_PROMPT,
    }


class PromptUpdate(BaseModel):
    prompt: str


@router.put("/prompt")
async def update_prompt(body: PromptUpdate):
    """Prompt speichern."""
    svc = _get_service()
    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt darf nicht leer sein")
    saved = await svc.save_prompt(body.prompt)
    return {"prompt": saved, "is_default": False}


@router.post("/prompt/reset")
async def reset_prompt():
    """Prompt auf Default zurücksetzen."""
    svc = _get_service()
    default = await svc.reset_prompt()
    return {"prompt": default, "is_default": True}

"""
TubeVault -  Downloads Router v1.3.5
© HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
"""

import json
from fastapi import APIRouter, HTTPException, Query

from app.models.download import (
    DownloadRequest, DownloadBatchRequest,
    DownloadResponse, DownloadQueueResponse,
)
from app.services.download_service import download_service
from app.database import db

router = APIRouter(prefix="/api/downloads", tags=["Downloads"])


@router.post("")
async def add_download(request: DownloadRequest):
    """Video zur Download-Queue hinzufügen."""
    try:
        result = await download_service.add_to_queue(
            url=request.url,
            quality=request.quality,
            format=request.format,
            download_thumbnail=request.download_thumbnail,
            priority=request.priority,
            itag=request.itag,
            audio_itag=request.audio_itag,
            merge_audio=request.merge_audio,
            audio_only=request.audio_only,
            subtitle_lang=request.subtitle_lang if request.download_subtitles else None,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch")
async def add_batch_downloads(request: DownloadBatchRequest):
    """Mehrere Videos zur Queue hinzufügen."""
    results = []
    for url in request.urls:
        try:
            r = await download_service.add_to_queue(
                url=url, quality=request.quality, audio_only=request.audio_only,
            )
            results.append(r)
        except Exception as e:
            results.append({"url": url, "status": "error", "error": str(e)})
    return {"results": results, "total": len(results)}


@router.get("")
async def get_download_queue():
    """Download-Queue abrufen."""
    return await download_service.get_queue()


# ---- Spezifische Routen VOR /{queue_id} ----

@router.delete("/completed/clear")
async def clear_completed():
    """Abgeschlossene Downloads aus Queue entfernen."""
    await download_service.clear_completed()
    return {"message": "Abgeschlossene Downloads entfernt"}


@router.post("/fix-stale")
async def fix_stale_downloads():
    """Stale Downloads (status=active ohne Worker) zurücksetzen."""
    cursor = await db.execute(
        "UPDATE jobs SET status='queued', progress=0 WHERE type='download' AND status='active'"
    )
    return {"fixed": cursor.rowcount}


@router.get("/worker/health")
async def worker_health():
    """Worker-Status prüfen."""
    alive = download_service.worker_alive
    queued = await db.fetch_val(
        "SELECT COUNT(*) FROM jobs WHERE type='download' AND status = 'queued'"
    ) or 0
    oldest_queued = await db.fetch_one(
        "SELECT id, json_extract(metadata, '$.video_id') as video_id, created_at FROM jobs WHERE type='download' AND status = 'queued' ORDER BY created_at ASC LIMIT 1"
    )
    return {
        "alive": alive,
        "queued": queued,
        "oldest_queued": dict(oldest_queued) if oldest_queued else None,
    }


@router.post("/worker/restart")
async def restart_worker():
    """Worker manuell neu starten."""
    result = await download_service.restart_worker()
    return result


@router.delete("/clear-all")
async def clear_all_finished():
    """Alle fertigen + fehlerhaften + stale Downloads entfernen."""
    cursor = await db.execute(
        "DELETE FROM jobs WHERE type='download' AND status IN ('done','error','cancelled')"
    )
    return {"cleared": cursor.rowcount}


@router.post("/retry-all")
async def retry_all_failed():
    """Alle fehlgeschlagenen/abgebrochenen Downloads erneut versuchen."""
    count = await download_service.retry_all_failed()
    return {"retried": count}


# ---- Parametrische Routen ----

@router.get("/{queue_id}")
async def get_download_status(queue_id: int):
    """Status eines einzelnen Downloads (queue_id = job_id)."""
    item = await db.fetch_one("SELECT * FROM jobs WHERE id = ? AND type='download'", (queue_id,))
    if not item:
        raise HTTPException(status_code=404, detail="Download nicht gefunden")
    result = dict(item)
    meta = json.loads(result.get("metadata") or "{}")
    result["video_id"] = meta.get("video_id")
    result["url"] = meta.get("url", "")
    result["download_options"] = meta.get("download_options", {})
    return result


@router.delete("/{queue_id}")
async def cancel_download(queue_id: int):
    """Download abbrechen / aus Queue entfernen."""
    await download_service.cancel_download(queue_id)
    return {"message": "Download abgebrochen", "queue_id": queue_id}


@router.post("/{queue_id}/retry")
async def retry_download(queue_id: int):
    """Fehlgeschlagenen Download erneut versuchen."""
    await download_service.retry_download(queue_id)
    return {"message": "Download wird erneut versucht", "queue_id": queue_id}


@router.post("/{queue_id}/retry-delay")
async def retry_download_delayed(queue_id: int, minutes: int = Query(5)):
    """Download mit Verzoegerung erneut versuchen."""
    await download_service.retry_with_delay(queue_id, minutes)
    return {"message": f"Download startet in {minutes} Minuten", "queue_id": queue_id}

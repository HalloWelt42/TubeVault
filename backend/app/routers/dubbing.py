"""
TubeVault – Nachvertonung und zusätzliche Tonspuren (Router) v1.0.0

Zwei Nutzer dieser Schnittstelle:
  - die Oberfläche: Videos vormerken, Warteliste ansehen, Tonspur umschalten
  - der Nachvertoner (eigenes Programm auf einem leistungsfähigen Rechner):
    Auftrag abholen, Lebenszeichen senden, Tonspur abliefern

Die Erweiterung ist abschaltbar (Einstellung dub.enabled). Ist sie aus,
nimmt die Warteliste nichts an; vorhandene Tonspuren bleiben abspielbar.
"""
import logging
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import config
from app.services import audio_tracks, dubbing, transcripts

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Nachvertonung"])

_UPLOAD_CHUNK = 1024 * 1024


# ─── Tonspuren eines Videos ───────────────────────────────────────────

@router.get("/api/videos/{video_id}/audio-tracks")
async def list_audio_tracks(video_id: str):
    """Zusätzliche Tonspuren eines Videos (die Original-Spur steckt im Video)."""
    return {"video_id": video_id, "tracks": await audio_tracks.list_tracks(video_id)}


@router.get("/api/player/{video_id}/track/{track_id}")
async def stream_audio_track(video_id: str, track_id: int):
    """Tonspur ausliefern (unterstützt Teilabrufe für das Springen im Player)."""
    path = await audio_tracks.track_file(video_id, track_id)
    if not path:
        raise HTTPException(status_code=404, detail="Tonspur nicht gefunden")
    return FileResponse(str(path), media_type=audio_tracks.mime_for(path))


@router.delete("/api/videos/{video_id}/audio-tracks/{track_id}")
async def delete_audio_track(video_id: str, track_id: int):
    if not await audio_tracks.delete_track(video_id, track_id):
        raise HTTPException(status_code=404, detail="Tonspur nicht gefunden")
    return {"deleted": True}


# ─── Warteliste (Oberfläche) ──────────────────────────────────────────

class EnqueueRequest(BaseModel):
    video_id: str
    target_language: Optional[str] = None   # leer = Deutsch
    voice: Optional[str] = None             # leer = Vorauswahl
    subtitles: dubbing.SubtitleUse = "any"


class VoiceReport(BaseModel):
    voices: list[str]


async def _require_enabled() -> None:
    if not await dubbing.is_enabled():
        raise HTTPException(status_code=409, detail="Die Nachvertonung ist in den Einstellungen ausgeschaltet")


@router.get("/api/dubbing/status")
async def dubbing_status():
    """Ist die Erweiterung eingeschaltet, und wie steht die Warteliste?"""
    return {"enabled": await dubbing.is_enabled(), "counts": await dubbing.counts()}


@router.post("/api/dubbing/requests")
async def enqueue_dubbing(request: EnqueueRequest):
    """Ein Video zur Nachvertonung vormerken, mit Stimme und Zielsprache."""
    await _require_enabled()
    return await dubbing.enqueue(
        request.video_id, request.target_language, request.voice, request.subtitles)


@router.get("/api/dubbing/voices")
async def dubbing_voices():
    """Stimmen, die der Vertonungsdienst zuletzt gemeldet hat, samt Vorauswahl."""
    return await dubbing.voice_choice()


@router.post("/api/dubbing/voices")
async def report_dubbing_voices(report: VoiceReport):
    """Der Nachvertoner meldet die verfügbaren Stimmen."""
    await dubbing.report_voices(report.voices)
    return await dubbing.voice_choice()


@router.get("/api/dubbing/requests")
async def list_dubbing_requests(status: Optional[str] = None, limit: int = 200):
    """Warteliste. status: open | queued | working | done | error | skipped."""
    return {"requests": await dubbing.list_requests(status, max(1, min(limit, 500))),
            "counts": await dubbing.counts()}


@router.post("/api/dubbing/requests/{request_id}/retry")
async def retry_dubbing(request_id: int):
    if not await dubbing.retry(request_id):
        raise HTTPException(status_code=409, detail="Nur fehlgeschlagene oder übersprungene Aufträge lassen sich wiederholen")
    return {"queued": True}


@router.post("/api/dubbing/requests/{request_id}/cancel")
async def cancel_dubbing(request_id: int):
    """Offenen Auftrag abbrechen; er bleibt als abgebrochen in der Liste."""
    if not await dubbing.cancel(request_id):
        raise HTTPException(status_code=409, detail="Nur wartende oder laufende Aufträge lassen sich abbrechen")
    return {"cancelled": True}


@router.delete("/api/dubbing/requests/{request_id}")
async def remove_dubbing(request_id: int):
    """Abgeschlossenen Auftrag aus der Liste nehmen (eine fertige Tonspur bleibt)."""
    job = await dubbing.get(request_id)
    if not job:
        raise HTTPException(status_code=404, detail="Auftrag nicht gefunden")
    if job.status in dubbing.OPEN_STATUSES:
        raise HTTPException(status_code=409, detail="Offene Aufträge erst abbrechen")
    await dubbing.remove(request_id)
    return {"removed": True}


# ─── Nachvertoner (eigenes Programm) ──────────────────────────────────

class ClaimRequest(BaseModel):
    worker: str


class ProgressRequest(BaseModel):
    progress: Optional[float] = None
    note: Optional[str] = None


class FailRequest(BaseModel):
    note: str
    skipped: bool = False   # True: nichts zu tun (z.B. Material ist schon deutsch)


@router.post("/api/dubbing/claim")
async def claim_dubbing(request: ClaimRequest):
    """Nächsten Auftrag abholen. Antwort enthält, wo das Video zu holen ist.
    Leere Warteliste oder ausgeschaltete Erweiterung: request = null."""
    if not await dubbing.is_enabled():
        return {"request": None}
    claimed = await dubbing.claim(request.worker.strip() or "nachvertoner")
    if not claimed:
        return {"request": None}
    return {
        "request": claimed,
        "media_url": f"/api/player/{claimed.video_id}",
        "result_url": f"/api/dubbing/requests/{claimed.id}/result",
        "transcript_url": f"/api/dubbing/requests/{claimed.id}/transcript",
    }


@router.get("/api/dubbing/requests/{request_id}/transcript")
async def dubbing_transcript(request_id: int):
    """Transkript aus den Untertiteln der Quelle, sofern der Auftrag es
    erlaubt und Untertitel existieren. Sonst transcript = null samt Grund,
    und der Vertonungsdienst transkribiert selbst."""
    request = await dubbing.get(request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Auftrag nicht gefunden")
    return await transcripts.for_dubbing(request.video_id, request.subtitles)


@router.post("/api/dubbing/requests/{request_id}/progress")
async def dubbing_progress(request_id: int, request: ProgressRequest):
    """Lebenszeichen mit Fortschritt. 409, wenn der Auftrag nicht mehr in
    Arbeit ist (entfernt oder neu vergeben) - der Nachvertoner bricht dann ab."""
    if not await dubbing.heartbeat(request_id, request.progress, request.note):
        raise HTTPException(status_code=409, detail="Auftrag ist nicht mehr in Arbeit")
    return {"ok": True}


@router.post("/api/dubbing/requests/{request_id}/fail")
async def dubbing_failed(request_id: int, request: FailRequest):
    if not await dubbing.get(request_id):
        raise HTTPException(status_code=404, detail="Auftrag nicht gefunden")
    if (await dubbing.get(request_id)).status == "working":   # abgebrochene bleiben abgebrochen
        await dubbing.finish(request_id, "skipped" if request.skipped else "error", request.note[:500])
    return {"ok": True}


@router.post("/api/dubbing/requests/{request_id}/result")
async def dubbing_result(
    request_id: int,
    file: UploadFile = File(...),
    source_language: Optional[str] = Form(None),
    voice: Optional[str] = Form(None),
):
    """Fertige Tonspur abliefern. Sie wird geprüft und als zusätzliche Tonspur
    am Video gespeichert; erst dann gilt der Auftrag als fertig."""
    job = await dubbing.get(request_id)
    if not job:
        raise HTTPException(status_code=404, detail="Auftrag nicht gefunden")
    if job.status != "working":
        raise HTTPException(status_code=409, detail="Auftrag ist nicht mehr in Arbeit")
    suffix = Path(file.filename or "").suffix.lower()

    config.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=config.TEMP_DIR, suffix=suffix, delete=False) as tmp:
        staged = Path(tmp.name)
        while chunk := await file.read(_UPLOAD_CHUNK):
            tmp.write(chunk)
    try:
        track = await audio_tracks.store_track(
            job.video_id, job.target_language, staged,
            suffix=suffix, origin="dub", voice=voice or job.voice)
    except ValueError as e:
        staged.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(e))

    if source_language:
        from app.database import db
        await db.execute(
            "UPDATE videos SET language = ? WHERE id = ? AND COALESCE(language, '') = ''",
            (source_language.strip().lower()[:8], job.video_id))
    await dubbing.finish(request_id, "done")
    return {"ok": True, "track": track}

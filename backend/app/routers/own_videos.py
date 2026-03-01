"""
TubeVault -  Eigene Videos Router v1.8.76
© HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0

API-Endpoints für Smart-Scan (Job-basiert), Import-Wizard und Verwaltung eigener Videos.
"""

import logging
import os
import mimetypes
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

from app.config import SCAN_DIR, VIDEOS_DIR
from pydantic import BaseModel

from app.services.import_service import import_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/own-videos", tags=["Eigene Videos"])

# Erlaubte Basis-Verzeichnisse fuer Preview (Sicherheit)
ALLOWED_PREVIEW_BASES = [str(SCAN_DIR), str(VIDEOS_DIR)]


# ─── Pydantic Models ──────────────────────────────────────

class ScanRequest(BaseModel):
    path: str = str(SCAN_DIR / "youtube")
    youtube_archive: bool = True


class ImportVideoRequest(BaseModel):
    file_path: str
    title: Optional[str] = None
    channel_name: Optional[str] = None
    description: Optional[str] = None
    youtube_id: Optional[str] = None
    source: str = "imported"
    thumbnail_path: Optional[str] = None
    duration: Optional[float] = None
    date_added: Optional[str] = None
    tags: Optional[list] = None
    generate_thumbnail: bool = True
    # Neues Feld: manuelles Match-Override
    link_video_id: Optional[str] = None

    model_config = {"extra": "ignore", "coerce_numbers_to_str": False}


class ImportBatchRequest(BaseModel):
    videos: list[ImportVideoRequest]
    subscribe_channels: list[str] = None


class DecisionRequest(BaseModel):
    decision: str  # link, link_rss, import_new, skip, replace, delete
    channel: Optional[str] = None


class BulkDecisionRequest(BaseModel):
    decision: str
    match_type: Optional[str] = None
    folder_name: Optional[str] = None
    channel: Optional[str] = None


# ─── Endpoints ─────────────────────────────────────────────

# ── Scan-Job (async) ──────────────────────────────────────

@router.post("/scan-job")
async def start_scan_job(req: ScanRequest):
    """Async Scan-Job starten. Gibt Session-ID + Job-ID zurück.
    Fortschritt über /api/jobs/{job_id} abfragbar."""
    try:
        result = await import_service.start_scan_job(
            path=req.path,
            youtube_archive=req.youtube_archive,
        )
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Scan-Job-Fehler: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan-sessions")
async def list_scan_sessions():
    """Alle Scan-Sessions auflisten."""
    return await import_service.get_scan_sessions()


@router.get("/scan-session/{session_id}")
async def get_scan_session(session_id: int):
    """Session-Info mit Statistiken."""
    result = await import_service.get_scan_session(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="Session nicht gefunden")
    return result


@router.get("/scan-results/{session_id}")
async def get_scan_results(
    session_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    match_filter: Optional[str] = None,
    folder: Optional[str] = None,
    decision: Optional[str] = None,
    search: Optional[str] = None,
):
    """Scan-Ergebnisse paginiert abrufen mit Filtern."""
    return await import_service.get_scan_results(
        session_id=session_id,
        page=page, per_page=per_page,
        match_filter=match_filter,
        folder_filter=folder,
        decision_filter=decision,
        search=search,
    )


@router.post("/scan-decision/{staging_id}")
async def set_decision(staging_id: int, req: DecisionRequest):
    """Entscheidung für eine einzelne Datei setzen."""
    try:
        return await import_service.set_decision(
            staging_id=staging_id,
            decision=req.decision,
            channel=req.channel,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/scan-bulk-decision/{session_id}")
async def set_bulk_decision(session_id: int, req: BulkDecisionRequest):
    """Entscheidung für mehrere Dateien gleichzeitig."""
    try:
        return await import_service.set_bulk_decision(
            session_id=session_id,
            decision=req.decision,
            match_type=req.match_type,
            folder_name=req.folder_name,
            channel=req.channel,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/scan-execute/{session_id}")
async def execute_decisions(session_id: int):
    """Alle Entscheidungen einer Session ausführen."""
    try:
        return await import_service.execute_decisions(session_id)
    except Exception as e:
        logger.error(f"Execute-Fehler: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/scan-session/{session_id}")
async def delete_scan_session(session_id: int):
    """Scan-Session und Staging-Daten löschen."""
    return await import_service.delete_scan_session(session_id)

@router.post("/scan")
async def scan_directory(req: ScanRequest):
    """Verzeichnis scannen (SYNCHRON -  nur für kleine Verzeichnisse!).
    Für große Verzeichnisse /scan-job verwenden."""
    try:
        result = await import_service.scan_directory(
            path=req.path,
            youtube_archive=req.youtube_archive,
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Scan-Fehler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import")
async def import_video(req: ImportVideoRequest):
    """Einzelnes Video importieren."""
    try:
        # link_video_id überschreibt youtube_id (manuelles Matching)
        yt_id = req.link_video_id or req.youtube_id
        result = await import_service.import_video(
            file_path=req.file_path,
            title=req.title,
            channel_name=req.channel_name,
            description=req.description,
            youtube_id=yt_id,
            source=req.source,
            thumbnail_path=req.thumbnail_path,
            duration=int(req.duration) if req.duration else None,
            date_added=req.date_added,
            tags=req.tags,
            generate_thumbnail=req.generate_thumbnail,
        )
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Import-Fehler fuer {req.file_path}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import-batch")
async def import_batch(req: ImportBatchRequest):
    """Mehrere Videos auf einmal importieren."""
    try:
        videos = [v.model_dump() for v in req.videos]
        result = await import_service.import_batch(
            videos=videos,
            subscribe_channels=req.subscribe_channels,
        )
        return result
    except Exception as e:
        logger.error(f"Batch-Import-Fehler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def list_own_videos(
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=100),
    source: Optional[str] = None,
    channel: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
):
    """Eigene/importierte Videos auflisten."""
    return await import_service.get_own_videos(
        page=page, per_page=per_page,
        source_filter=source, channel=channel,
        search=search, sort_by=sort_by, sort_order=sort_order,
    )


@router.get("/stats")
async def own_video_stats():
    """Statistiken für eigene Videos."""
    return await import_service.get_own_stats()


@router.delete("/{video_id}")
async def delete_own_video(video_id: str):
    """Import rückgängig machen -  Video aus DB entfernen.
    Datei auf Festplatte bleibt erhalten!
    """
    from app.database import db

    video = await db.fetch_one(
        "SELECT id, title, source, file_path, import_path, thumbnail_path FROM videos WHERE id = ?",
        (video_id,)
    )
    if not video:
        raise HTTPException(status_code=404, detail="Video nicht gefunden")
    if video["source"] not in ("local", "imported"):
        raise HTTPException(status_code=400,
                            detail="Nur eigene/importierte Videos können entfernt werden")

    # Thumbnail löschen (generierte, nicht originale)
    thumb = video.get("thumbnail_path")
    if thumb:
        tp = Path(thumb)
        if tp.exists() and "/thumbnails/" in str(tp):
            try:
                tp.unlink()
                logger.info(f"Thumbnail gelöscht: {thumb}")
            except Exception:
                pass

    # Aus allen abhängigen Tabellen löschen (cascade sollte greifen, sicher ist sicher)
    for tbl in ["ad_markers", "favorites", "chapters"]:
        try:
            await db.execute(f"DELETE FROM {tbl} WHERE video_id = ?", (video_id,))
        except Exception:
            pass

    await db.execute("DELETE FROM videos WHERE id = ?", (video_id,))
    logger.info(f"Import zurückgenommen: {video_id} ({video['title']})")

    return {
        "deleted": True,
        "id": video_id,
        "title": video["title"],
        "file_kept": video.get("import_path") or video.get("file_path"),
    }


@router.get("/search-rss")
async def search_rss_entries(
    q: str = Query("", min_length=2),
    channel: Optional[str] = None,
    limit: int = Query(20, ge=1, le=50),
):
    """RSS-Entries durchsuchen -  für manuelles Matching aus der Scan-Liste.
    Liefert Titel, Kanal, Video-ID, Thumbnail-Verfügbarkeit.
    """
    from app.database import db

    conditions = ["r.title IS NOT NULL"]
    params = []

    if q:
        conditions.append("(r.title LIKE ? OR r.video_id LIKE ? OR s.channel_name LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])

    if channel:
        conditions.append("s.channel_name LIKE ?")
        params.append(f"%{channel}%")

    where = " AND ".join(conditions)
    params.append(limit)

    rows = await db.fetch_all(
        f"""SELECT r.video_id, r.title, r.duration, r.published,
                   s.channel_name, s.channel_id,
                   CASE WHEN v.id IS NOT NULL THEN 1 ELSE 0 END as in_library
            FROM rss_entries r
            JOIN subscriptions s ON r.channel_id = s.channel_id
            LEFT JOIN videos v ON v.id = r.video_id
            WHERE {where}
            ORDER BY r.published DESC
            LIMIT ?""",
        tuple(params)
    )

    return {
        "results": [dict(r) for r in rows],
        "count": len(rows),
    }


# ─── Preview / Vorschau ───────────────────────────────────

def _validate_preview_path(path: str) -> Path:
    """Prüft ob Pfad in erlaubtem Verzeichnis liegt."""
    resolved = Path(path).resolve()
    for base in ALLOWED_PREVIEW_BASES:
        if str(resolved).startswith(base):
            if resolved.exists() and resolved.is_file():
                return resolved
    raise HTTPException(status_code=403, detail="Zugriff verweigert")


@router.get("/preview/stream")
async def preview_stream(path: str = Query(...), request: Request = None):
    """Scan-Video als Stream vorschauen (Range-Support)."""
    file_path = _validate_preview_path(path)
    file_size = file_path.stat().st_size
    mime = mimetypes.guess_type(str(file_path))[0] or "video/mp4"

    range_header = request.headers.get("range") if request else None
    if range_header:
        start, end = 0, file_size - 1
        range_val = range_header.replace("bytes=", "")
        parts = range_val.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1
        end = min(end, file_size - 1)
        length = end - start + 1

        def _range_gen():
            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            _range_gen(), status_code=206, media_type=mime,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(length),
            }
        )

    return FileResponse(str(file_path), media_type=mime)


@router.get("/preview/thumb")
async def preview_thumbnail(path: str = Query(...)):
    """Thumbnail einer Scan-Datei liefern."""
    file_path = _validate_preview_path(path)
    mime = mimetypes.guess_type(str(file_path))[0] or "image/jpeg"
    return FileResponse(str(file_path), media_type=mime)

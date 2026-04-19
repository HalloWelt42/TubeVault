"""
TubeVault – Scan Router v1.5.61
Inkrementeller Scan → Identifizieren → Registrieren → Original löschen.
© HalloWelt42 – Private Nutzung
"""

import os
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import logging

from app.services.scan_service import scan_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scan", tags=["Scan-Index"])

from app.config import SCAN_DIR


# ─── Models ──────────────────────────────────────────

class ScanStartRequest(BaseModel):
    path: str = str(SCAN_DIR / "youtube")
    youtube_archive: bool = True

class RegisterRequest(BaseModel):
    ids: list[int]

class LinkRequest(BaseModel):
    youtube_id: str
    title: Optional[str] = None
    channel: Optional[str] = None

class StatusRequest(BaseModel):
    status: str

class SkipFolderRequest(BaseModel):
    folder: str

class DeleteRequest(BaseModel):
    ids: list[int]


# ─── Discovery ───────────────────────────────────────

@router.post("/start")
async def start_scan(req: ScanStartRequest):
    """Scan starten. Entdeckt Dateien + extrahiert YouTube-IDs."""
    return await scan_service.start_discover(req.path, req.youtube_archive)

@router.post("/stop")
async def stop_scan():
    """Laufenden Scan pausieren."""
    return await scan_service.stop_discover()

@router.get("/progress")
async def get_progress():
    """Scan-Fortschritt + Statistiken."""
    return await scan_service.get_progress()


# ─── Registrieren (ins Vault kopieren) ───────────────

@router.post("/register")
async def register_items(req: RegisterRequest):
    """Ausgewählte Einträge registrieren: Kopiert ins Vault, Thumbnail, DB-Eintrag."""
    return await scan_service.register_items(req.ids)

@router.post("/register-all")
async def register_all():
    """Alle identifizierten Einträge (mit YouTube-ID) auf einmal registrieren."""
    return await scan_service.register_all_identified()


# ─── YouTube-Verknüpfung ────────────────────────────

@router.post("/{scan_id}/link")
async def link_youtube(scan_id: int, req: LinkRequest):
    """Manuell YouTube-ID zuweisen (aus YT-Suche)."""
    return await scan_service.link_youtube(
        scan_id, req.youtube_id, req.title, req.channel)


# ─── Original löschen ───────────────────────────────

@router.post("/{scan_id}/delete-original")
async def delete_original(scan_id: int):
    """Original-Datei löschen (nur wenn registriert)."""
    return await scan_service.delete_original(scan_id)

@router.post("/delete-originals")
async def delete_originals_batch(req: DeleteRequest):
    """Mehrere Originale löschen."""
    return await scan_service.delete_originals_batch(req.ids)


# ─── Thumbnail-Vorschau ─────────────────────────────

@router.get("/{scan_id}/preview-frames")
async def get_preview_frames(scan_id: int, count: int = Query(6, ge=2, le=12)):
    """Frames aus Video extrahieren für Thumbnail-Auswahl."""
    frames = await scan_service.get_preview_frames(scan_id, count)
    return {"frames": [f"/api/scan/frame/{scan_id}/{i}" for i, _ in enumerate(frames)],
            "count": len(frames)}

@router.get("/frame/{scan_id}/{index}")
async def get_frame(scan_id: int, index: int):
    """Einzelnen Frame als Bild liefern."""
    from app.config import DATA_DIR
    frame_path = DATA_DIR / "temp" / f"preview_{scan_id}" / f"frame_{index}.jpg"
    if not frame_path.exists():
        raise HTTPException(status_code=404, detail="Frame nicht gefunden")
    return FileResponse(str(frame_path), media_type="image/jpeg")


@router.get("/{scan_id}/thumb")
async def get_scan_thumb(scan_id: int):
    """Thumbnail für Scan-Eintrag: Companion-Bild oder generiert aus Video."""
    from app.config import DATA_DIR, THUMBNAILS_DIR
    from app.database_scan import scan_db
    import subprocess

    row = await scan_db.fetch_one(
        "SELECT path, has_thumb FROM scan_index WHERE id = ?", (scan_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Scan-Eintrag nicht gefunden")

    src = Path(row["path"])

    # 1. Companion-Thumbnail suchen
    if row["has_thumb"]:
        base = src.with_suffix("")
        for ext in [".jpg", ".jpeg", ".png", ".webp"]:
            for suffix in ["", "-thumb", "-poster", "_thumb"]:
                candidate = Path(str(base) + suffix + ext)
                if candidate.exists():
                    mt = "image/jpeg" if ext in (".jpg", ".jpeg") else f"image/{ext.lstrip('.')}"
                    return FileResponse(str(candidate), media_type=mt)

    # 2. Cached generiertes Thumbnail
    cache_dir = DATA_DIR / "temp" / "scan_thumbs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"{scan_id}.jpg"
    if cached.exists() and cached.stat().st_size > 0:
        return FileResponse(str(cached), media_type="image/jpeg")

    # 3. Aus Video generieren
    if src.exists():
        try:
            r = subprocess.run(
                ["ffmpeg", "-ss", "5", "-i", str(src),
                 "-vframes", "1", "-vf", "scale=320:-1",
                 "-q:v", "5", str(cached), "-y"],
                capture_output=True, timeout=15)
            if cached.exists() and cached.stat().st_size > 0:
                return FileResponse(str(cached), media_type="image/jpeg")
            # Fallback: Frame bei Sekunde 0
            subprocess.run(
                ["ffmpeg", "-i", str(src),
                 "-vframes", "1", "-vf", "scale=320:-1",
                 "-q:v", "5", str(cached), "-y"],
                capture_output=True, timeout=15)
            if cached.exists() and cached.stat().st_size > 0:
                return FileResponse(str(cached), media_type="image/jpeg")
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            pass

    raise HTTPException(status_code=404, detail="Kein Thumbnail verfügbar")

@router.post("/{scan_id}/set-thumbnail")
async def set_thumbnail(scan_id: int, frame_index: int = Query(...)):
    """Frame als Thumbnail für registriertes Video setzen."""
    return await scan_service.set_thumbnail_from_frame(scan_id, frame_index)


# ─── Index-Abfragen ─────────────────────────────────

@router.get("/index")
async def get_index(
    status: Optional[str] = None,
    folder: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    sort_by: str = "id",
    sort_order: str = "asc",
):
    """Paginierter Scan-Index mit Filtern."""
    return await scan_service.get_index(
        status=status, folder=folder, search=search,
        page=page, per_page=per_page,
        sort_by=sort_by, sort_order=sort_order)

@router.get("/stats")
async def get_stats():
    """Statistiken: total, per status, folders."""
    return await scan_service.get_stats()

@router.get("/folders")
async def get_folders():
    """Ordner-Liste mit Counts pro Status."""
    return await scan_service.get_folders()


# ─── Status-Änderungen ──────────────────────────────

@router.patch("/{scan_id}/status")
async def update_status(scan_id: int, req: StatusRequest):
    """Status ändern (discovered, skipped, identified)."""
    return await scan_service.update_status(scan_id, req.status)

@router.post("/skip-folder")
async def skip_folder(req: SkipFolderRequest):
    """Ganzen Ordner überspringen."""
    return await scan_service.skip_folder(req.folder)


# ─── Reset ───────────────────────────────────────────

@router.delete("/reset")
async def reset_index():
    """Gesamten Scan-Index löschen."""
    return await scan_service.reset_index()


# ─── Repair & Enrich ────────────────────────────────

@router.post("/repair-thumbnails")
async def repair_all_thumbnails():
    """Thumbnails für alle importierten Videos reparieren."""
    return await scan_service.repair_all_thumbnails()


@router.post("/repair-thumbnail/{video_id}")
async def repair_thumbnail(video_id: str):
    """Thumbnail für ein Video neu generieren."""
    return await scan_service.repair_thumbnail(video_id)


@router.post("/enrich/{video_id}")
async def enrich_from_youtube(video_id: str):
    """Metadaten von YouTube abrufen und lokales Video anreichern."""
    return await scan_service.enrich_from_youtube(video_id)


@router.post("/thumbnail-at-position/{video_id}")
async def thumbnail_at_position(video_id: str, position: int = Query(..., ge=0)):
    """Thumbnail aus bestimmter Video-Position erstellen."""
    return await scan_service.create_thumbnail_at_position(video_id, position)


@router.post("/fetch-yt-thumbnail/{video_id}")
async def fetch_yt_thumbnail(video_id: str):
    """YouTube-Thumbnail laden (überschreibt vorhandenes)."""
    return await scan_service.fetch_yt_thumbnail(video_id)


@router.post("/cleanup-registered")
async def cleanup_registered():
    """Alle registrierten Originaldateien löschen (Aufräumen)."""
    from app.database_scan import scan_db as sdb
    rows = await sdb.fetch_all(
        "SELECT id FROM scan_index WHERE status = 'registered'")
    if not rows:
        return {"status": "ok", "cleaned": 0, "message": "Nichts zum Aufräumen"}
    ids = [r["id"] for r in rows]
    result = await scan_service.delete_originals_batch(ids)
    return {**result, "message": f"{result.get('deleted', 0)} Originaldateien gelöscht"}

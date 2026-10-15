"""
TubeVault – Eigene Videos: Sammlung einlesen und einordnen

Ordner der Sammlung einlesen lassen, den Stand abfragen (läuft auch während
des Einlesens: Geprüftes ist sofort sichtbar) und Dateien ansehen.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.models.own_files import OwnFile, OwnFolder
from app.services import own_scan

router = APIRouter(prefix="/api/own-videos", tags=["Eigene Videos"])


class Collection(BaseModel):
    available: bool                  # Sammlungsordner vorhanden
    folders: list[OwnFolder]         # schon eingelesene Ordner
    candidates: list[str]            # Ordner der obersten Ebene, die sich einlesen lassen


class FolderRequest(BaseModel):
    path: str = ""                   # relativ zur Sammlung, leer = alles


class FilePage(BaseModel):
    items: list[OwnFile]
    total: int


@router.get("/collection", response_model=Collection)
async def get_collection():
    candidates = await own_scan.candidates()
    available = bool(candidates) or own_scan.collection_root().is_dir()
    return Collection(available=available, folders=await own_scan.folders(), candidates=candidates)


@router.post("/folders")
async def add_folder(body: FolderRequest):
    try:
        return {"id": await own_scan.request_scan(body.path)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/folders/{folder_id}/scan")
async def scan_folder(folder_id: int):
    try:
        await own_scan.rescan(folder_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True}


@router.post("/folders/{folder_id}/pause")
async def pause_folder(folder_id: int):
    await own_scan.pause(folder_id)
    return {"ok": True}


@router.delete("/folders/{folder_id}")
async def forget_folder(folder_id: int):
    await own_scan.forget(folder_id)
    return {"ok": True}


@router.get("/folders/{folder_id}/files", response_model=FilePage)
async def list_files(folder_id: int, finding: Optional[str] = None, q: Optional[str] = None,
                     offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    try:
        items, total = await own_scan.files(folder_id, finding, q, offset, limit)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return FilePage(items=items, total=total)


@router.get("/files/{file_id}", response_model=OwnFile)
async def get_file(file_id: int):
    try:
        return await own_scan.file(file_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/files/{file_id}/thumbnail")
async def file_thumbnail(file_id: int):
    path = await own_scan.thumbnail_path(file_id)
    if not path or not path.is_file():
        raise HTTPException(status_code=404, detail="Kein Vorschaubild")
    return FileResponse(path)


@router.get("/files/{file_id}/media")
async def file_media(file_id: int):
    """Die Datei selbst zum Ansehen (mit Bereichsanfragen zum Spulen)."""
    try:
        path = await own_scan.media_path(file_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Datei nicht erreichbar")
    return FileResponse(path)

"""
TubeVault – Eigene Videos: Sammlung einlesen und einordnen

Ordner der Sammlung einlesen lassen, den Stand abfragen (läuft auch während
des Einlesens: Geprüftes ist sofort sichtbar), Dateien ansehen und
einordnen, Eingeordnetes auflisten.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.database import db
from app.models.own_files import OwnFile, OwnFolder
from app.services import own_actions, own_scan

router = APIRouter(prefix="/api/own-videos", tags=["Eigene Videos"])


class BulkState(BaseModel):
    action: str
    folder_path: str
    done: int
    failed: int
    total: int


class Collection(BaseModel):
    available: bool                  # Sammlungsordner vorhanden
    folders: list[OwnFolder]         # schon eingelesene Ordner
    candidates: list[str]            # Ordner der obersten Ebene, die sich einlesen lassen
    bulk: Optional[BulkState] = None # laufende Sammelaktion


class FolderRequest(BaseModel):
    path: str = ""                   # relativ zur Sammlung, leer = alles


class FilePage(BaseModel):
    items: list[OwnFile]
    total: int


@router.get("/collection", response_model=Collection)
async def get_collection():
    candidates = await own_scan.candidates()
    available = bool(candidates) or own_scan.collection_root().is_dir()
    run = own_actions.bulk_running()
    bulk = BulkState(action=run.action, folder_path=run.folder_path, done=run.done, failed=run.failed,
                     total=run.total) if run else None
    return Collection(available=available, folders=await own_scan.folders(), candidates=candidates, bulk=bulk)


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


# ─── Einordnen ────────────────────────────────────────────────────────

class AdoptRequest(BaseModel):
    video_id: Optional[str] = None   # leer = der erkannte Treffer


class OwnRequest(BaseModel):
    channel_name: str
    channel_id: Optional[str] = None
    title: Optional[str] = None


class BulkRequest(BaseModel):
    action: str                      # delete_duplicates | adopt_certain


async def _act(work):
    try:
        return await work
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except own_actions.ActionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (OSError, ValueError) as e:
        raise HTTPException(status_code=500, detail=f"Datei nicht bearbeitet: {e}")


@router.post("/files/{file_id}/delete")
async def delete_file(file_id: int):
    await _act(own_actions.delete(file_id))
    return {"ok": True}


@router.post("/files/{file_id}/adopt")
async def adopt_file(file_id: int, body: AdoptRequest):
    return {"video_id": await _act(own_actions.adopt(file_id, body.video_id))}


@router.post("/files/{file_id}/own")
async def own_file(file_id: int, body: OwnRequest):
    return {"video_id": await _act(own_actions.make_own(file_id, body.channel_name, body.channel_id, body.title))}


@router.post("/files/{file_id}/replace")
async def replace_file(file_id: int):
    return {"video_id": await _act(own_actions.replace(file_id))}


@router.post("/files/{file_id}/skip")
async def skip_file(file_id: int):
    await _act(own_actions.skip(file_id))
    return {"ok": True}


@router.post("/files/{file_id}/reopen")
async def reopen_file(file_id: int):
    await _act(own_actions.reopen(file_id))
    return {"ok": True}


@router.post("/folders/{folder_id}/bulk")
async def bulk(folder_id: int, body: BulkRequest):
    run = await _act(own_actions.start_bulk(folder_id, body.action))
    return {"total": run.total}


@router.get("/channels")
async def channels():
    """Kanäle zum Zuordnen: Abos und eigene Kanäle."""
    return await own_actions.channels()


@router.get("/lookup")
async def lookup(q: str = Query(..., min_length=2)):
    """Videos aus Bibliothek und Feed zum Zuordnen einer Datei."""
    like = f"%{q}%"
    library = await db.fetch_all(
        """SELECT id, title, channel_name, duration, 1 AS in_library FROM videos
           WHERE status = 'ready' AND length(id) = 11 AND title LIKE ? ORDER BY download_date DESC LIMIT 15""",
        (like,))
    feed = await db.fetch_all(
        """SELECT r.video_id AS id, r.title, s.channel_name, r.duration, 0 AS in_library
           FROM rss_entries r LEFT JOIN subscriptions s ON s.channel_id = r.channel_id
           WHERE r.title LIKE ? AND r.video_id NOT IN (SELECT id FROM videos WHERE status = 'ready')
           GROUP BY r.video_id ORDER BY r.published DESC LIMIT 15""", (like,))
    return [dict(r) for r in [*library, *feed]]


class OwnVideo(BaseModel):
    id: str
    title: Optional[str] = None
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    duration: Optional[int] = None
    file_size: Optional[int] = None
    source: Optional[str] = None
    import_path: Optional[str] = None


class OwnVideoPage(BaseModel):
    items: list[OwnVideo]
    total: int
    total_bytes: int
    folder_named_channels: int       # Kanalname ist ein Ordnerpfad ("youtube/ARTE/...")


@router.get("/library", response_model=OwnVideoPage)
async def library(offset: int = Query(0, ge=0), limit: int = Query(60, ge=1, le=200)):
    """Eingeordnete eigene und übernommene Videos, nach Kanal sortiert."""
    where = "status = 'ready' AND source IN ('local', 'imported')"
    totals = await db.fetch_one(
        f"""SELECT COUNT(*) AS n, COALESCE(SUM(file_size), 0) AS bytes,
                   SUM(CASE WHEN channel_name LIKE '%/%' THEN 1 ELSE 0 END) AS folder_named
            FROM videos WHERE {where}""")
    rows = await db.fetch_all(
        f"""SELECT id, title, channel_id, channel_name, duration, file_size, source, import_path
            FROM videos WHERE {where} ORDER BY channel_name COLLATE NOCASE, title COLLATE NOCASE
            LIMIT ? OFFSET ?""", (limit, offset))
    return OwnVideoPage(items=[OwnVideo(**dict(r)) for r in rows], total=totals["n"],
                        total_bytes=totals["bytes"], folder_named_channels=totals["folder_named"] or 0)

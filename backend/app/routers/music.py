"""
TubeVault – Musik

Übersicht, Titel, Interpreten, Alben, Musikkanäle und dynamische
Wiedergabelisten für die Musikseite und den Musikspieler; dazu die eigenen
Musikdateien (Abspielen, Cover, Liedtext, Wiedergaben, Lieblingssongs) und
der Bereich "Ausgeblendet" (ausgeblendete Dateien, ausgeschlossene Alben).
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from app.services import ad_free_export, audio_export, audiobooks, music_exclusions, music_files, music_library
from app.utils.range_file import range_response
from app.services.music_library import Group, PlayList, Track

router = APIRouter(prefix="/api/music", tags=["Musik"])


class Counts(BaseModel):
    tracks: int
    artists: int
    albums: int
    channels: int
    favorites: int
    duration: int
    books: int = 0                   # Hörbücher (eigener Bereich, nie in der Musik)
    hidden: int = 0                  # ausgeblendete Dateien und ausgeschlossene Alben


class SourceCounts(BaseModel):
    """Titel je Quelle, unabhängig von der gewählten (für den Quellen-Filter)."""
    videos: int
    sammlung: int


class Overview(BaseModel):
    counts: Counts
    source: str                      # gewählte Quelle: alle | sammlung | videos
    sources: SourceCounts
    artists: list[Group]             # meiste Titel zuerst
    new: list[Track]
    often: list[Track]
    channels: list[Group]


class TrackPage(BaseModel):
    items: list[Track]
    total: int


@router.get("/overview", response_model=Overview)
async def overview():
    items = await music_library.tracks()
    artists = music_library.artists(items)
    albums = music_library.albums(items)
    channels = music_library.channels(items)
    return Overview(
        source=await music_library.source_setting(),
        sources=SourceCounts(videos=len(await music_library.video_tracks()),
                             sammlung=await music_files.count()),
        counts=Counts(tracks=len(items), artists=len(artists), albums=len(albums), channels=len(channels),
                      favorites=sum(1 for t in items if t.favorite), duration=sum(t.duration or 0 for t in items),
                      books=len(await audiobooks.books()),
                      hidden=await music_files.hidden_count() + await music_exclusions.total()),
        artists=sorted(artists, key=lambda g: g.count, reverse=True)[:12],
        new=items[:12],
        often=sorted((t for t in items if t.play_count), key=lambda t: t.play_count, reverse=True)[:10],
        channels=sorted(channels, key=lambda g: g.count, reverse=True))


@router.get("/tracks", response_model=TrackPage)
async def track_list(sort: str = Query("added", pattern="^(added|title|artist|plays|duration|last_played)$"),
                     q: Optional[str] = None, favorites: bool = False,
                     offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
    items = await music_library.tracks()
    if favorites:
        items = [t for t in items if t.favorite]
    if q:
        items = music_library.search(items, q)
    items.sort(key=music_library.SORTS[sort], reverse=sort in music_library.DESCENDING)
    return TrackPage(items=items[offset:offset + limit], total=len(items))


@router.get("/artists", response_model=list[Group])
async def artist_list():
    return music_library.artists(await music_library.tracks())


@router.get("/albums", response_model=list[Group])
async def album_list():
    return music_library.albums(await music_library.tracks())


@router.get("/channels", response_model=list[Group])
async def channel_list():
    return music_library.channels(await music_library.tracks())


@router.get("/play", response_model=PlayList)
async def play(source: str = Query(..., min_length=3), shuffle: bool = False, start: Optional[str] = None):
    """Dynamische Wiedergabeliste: all, artist:<name>, album:<schlüssel>,
    channel:<id>, favorites, often, new, recent, forgotten, playlist:<id>,
    similar:<video_id>, sammlung:<favorites:Liste|playlist:id> (alle Videos
    als Ton) - wahlweise zufällig."""
    try:
        return await music_library.play_list(source, shuffle=shuffle, start=start)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/cover/{item_id}")
async def cover(item_id: str):
    """Bild eines Titels: Cover der Musikdatei oder Vorschaubild des Videos."""
    if not music_files.is_file_id(item_id):
        return RedirectResponse(f"/api/player/{item_id}/thumbnail")
    path = await music_files.cover_path(item_id)
    if not path:
        raise HTTPException(status_code=404, detail="Kein Cover")
    return FileResponse(str(path), media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/books", response_model=list[audiobooks.Book])
async def book_list():
    """Hörbücher und Hörspiele, zuletzt gehörte zuerst."""
    return await audiobooks.books()


class BookProgress(BaseModel):
    file_id: str
    position: float


@router.put("/books/{key}/progress")
async def book_progress(key: str, req: BookProgress):
    """Stand merken: welcher Teil, welche Stelle."""
    try:
        await audiobooks.save_progress(key, req.file_id, req.position)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"saved": True}


@router.delete("/books/{key}/progress")
async def book_restart(key: str):
    """Von vorn: gemerkten Stand vergessen."""
    await audiobooks.reset(key)
    return {"reset": True}


@router.get("/files/status")
async def files_status():
    """Eigene Musiksammlung: eingehängt?, Anzahl, letztes Einlesen."""
    return await music_files.status()


@router.post("/files/scan", response_model=music_files.ScanResult)
async def files_scan():
    """Sammlung jetzt einlesen (nur Neues und Geändertes wird gelesen)."""
    if not music_files.available():
        raise HTTPException(status_code=404, detail="Kein Musikordner eingehängt")
    return await music_files.scan()


async def _file_or_404(item_id: str) -> music_files.FileInfo:
    found = await music_files.get(item_id) if music_files.is_file_id(item_id) else None
    if not found:
        raise HTTPException(status_code=404, detail="Musikdatei unbekannt")
    return found


@router.get("/files/{item_id}", response_model=music_files.FileInfo)
async def file_info(item_id: str):
    return await _file_or_404(item_id)


@router.get("/files/{item_id}/stream")
async def file_stream(item_id: str, request: Request):
    await _file_or_404(item_id)
    path = await music_files.path_of(item_id)
    if not path:
        raise HTTPException(status_code=404, detail="Datei nicht erreichbar")
    return range_response(str(path), request, media_type=music_files.mime_of(path))


@router.get("/files/{item_id}/download")
async def file_download(item_id: str):
    """Die Datei unverändert, benannt "Interpret - Titel.flac"."""
    found = await _file_or_404(item_id)
    path = await music_files.path_of(item_id)
    if not path:
        raise HTTPException(status_code=404, detail="Datei nicht erreichbar")
    name = audio_export.safe_name(f"{found.artist} - {found.title}" if found.artist else found.title)
    return FileResponse(str(path), media_type=music_files.mime_of(path), filename=f"{name}{path.suffix.lower()}")


@router.get("/files/{item_id}/lyrics")
async def file_lyrics(item_id: str):
    """Liedtext wie bei Videos: {plain, synced, offset} (.lrc neben der Datei oder Tag)."""
    await _file_or_404(item_id)
    return await music_files.lyrics(item_id)


@router.post("/files/{item_id}/played")
async def file_played(item_id: str):
    await _file_or_404(item_id)
    await music_files.record_play(item_id)
    return {"recorded": True}


class FavoriteRequest(BaseModel):
    favorite: bool


@router.put("/files/{item_id}/favorite")
async def file_favorite(item_id: str, req: FavoriteRequest):
    await _file_or_404(item_id)
    await music_files.set_favorite(item_id, req.favorite)
    return {"favorite": req.favorite}


class HiddenRequest(BaseModel):
    hidden: bool


@router.put("/files/{item_id}/hidden")
async def file_hidden(item_id: str, req: HiddenRequest):
    """Titel der Sammlung ausblenden (statt löschen: die Sammlung liegt nur lesend vor) oder wieder einblenden."""
    await _file_or_404(item_id)
    await music_files.set_hidden(item_id, req.hidden)
    return {"hidden": req.hidden}


# ─── Ausgeblendet: zurückholen, einzeln oder mehrere ───

class HiddenArea(BaseModel):
    tracks: list[Track]                          # ausgeblendete Dateien der Sammlung
    albums: list[music_exclusions.Exclusion]     # ausgeschlossene Alben


class ExcludeRequest(BaseModel):
    source: str                                  # Gruppe, z.B. album:<schlüssel>


class RestoreRequest(BaseModel):
    tracks: list[str] = []
    albums: list[str] = []


@router.get("/hidden", response_model=HiddenArea)
async def hidden_area():
    """Was aus der Musik herausgenommen ist, zuletzt Herausgenommenes zuerst."""
    files = await music_files.hidden_files()
    return HiddenArea(tracks=[music_library.file_track(f) for f in files], albums=await music_exclusions.listing())


@router.post("/exclusions", response_model=music_exclusions.Exclusion)
async def exclude_group(req: ExcludeRequest):
    """Ein ganzes Album aus der Musik ausschließen (auch was später dazukommt)."""
    if not music_exclusions.allowed(req.source):
        raise HTTPException(status_code=400, detail="Nur Alben lassen sich ausschließen")
    album = await music_library.play_list(req.source)
    if not album.tracks:
        raise HTTPException(status_code=404, detail="Album nicht gefunden")
    entry = music_exclusions.Exclusion(source=req.source, name=album.title, subtitle=album.tracks[0].artist,
                                       count=len(album.tracks))
    await music_exclusions.exclude(entry.source, entry.name, entry.subtitle, entry.count)
    return entry


@router.post("/hidden/restore")
async def restore_hidden(req: RestoreRequest):
    """Ausgeblendete Titel und ausgeschlossene Alben zurückholen."""
    return {"tracks": await music_files.show_again(req.tracks), "albums": await music_exclusions.restore(req.albums)}


@router.get("/audio-info/{video_id}", response_model=audio_export.AudioInfo)
async def audio_info(video_id: str):
    """Format, Bitrate und Abtastrate der Tonspur (für die Anzeige im Spieler)."""
    measured = await audio_export.info(video_id)
    if not measured:
        raise HTTPException(status_code=404, detail="Datei nicht vorhanden")
    return measured


@router.get("/export.zip")
async def export_zip(source: str = Query(..., min_length=3),
                     format: str = Query(audio_export.ORIGINAL, pattern="^(original|mp3|m4a|flac|ogg)$")):
    """Alle Titel einer dynamischen Liste (Wiedergabeliste, Interpret,
    Lieblingssongs ...) als ZIP nur mit Ton. original = ohne Neukodierung."""
    try:
        title, items = await music_library.export_items(source)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not items:
        raise HTTPException(status_code=404, detail="Keine Titel")
    folder = ad_free_export.work_dir()
    try:
        archive = await audio_export.zip_tracks(items, format, folder, title)
    except LookupError as e:
        ad_free_export.remove(folder)
        raise HTTPException(status_code=404, detail=str(e))
    return FileResponse(str(archive), media_type="application/zip", filename=archive.name,
                        background=BackgroundTask(ad_free_export.remove, folder))


"""
TubeVault – Musik

Übersicht, Titel, Interpreten, Alben, Musikkanäle und dynamische
Wiedergabelisten für die Musikseite und den Musikspieler.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services import music_library
from app.services.music_library import Group, PlayList, Track

router = APIRouter(prefix="/api/music", tags=["Musik"])


class Counts(BaseModel):
    tracks: int
    artists: int
    albums: int
    channels: int
    favorites: int
    duration: int


class Overview(BaseModel):
    counts: Counts
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
        counts=Counts(tracks=len(items), artists=len(artists), albums=len(albums), channels=len(channels),
                      favorites=sum(1 for t in items if t.favorite), duration=sum(t.duration or 0 for t in items)),
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
    similar:<video_id> - wahlweise zufällig."""
    try:
        return await music_library.play_list(source, shuffle=shuffle, start=start)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

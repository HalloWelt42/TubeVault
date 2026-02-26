"""
TubeVault – Lyrics Router v1.8.0
API-Endpunkte für Songtext-Verwaltung.
© HalloWelt42 – Private Nutzung
"""

import asyncio
import logging
from fastapi import APIRouter, Body
from app.services import lyrics_service
from app.database import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lyrics", tags=["lyrics"])


@router.get("/{video_id}")
async def get_lyrics(video_id: str):
    """Lyrics + Musik-Info eines Videos abrufen."""
    info = await lyrics_service.get_music_info(video_id)
    texts = lyrics_service.load_lyrics(video_id)
    return {**info, **texts}


@router.post("/{video_id}/detect")
async def detect_music(video_id: str):
    """Automatisch erkennen ob Video Musik ist + Artist/Title extrahieren."""
    row = await db.fetch_one(
        "SELECT title, tags FROM videos WHERE id = ?", (video_id,)
    )
    if not row:
        return {"status": "error", "message": "Video nicht gefunden"}

    result = lyrics_service.detect_music(row["title"], row["tags"] or "[]")

    if result["is_music"]:
        await lyrics_service.set_music_info(
            video_id, True,
            result["artist"] or "",
            result["song_title"] or "",
        )

    return {
        "status": "ok",
        **result,
    }


@router.post("/{video_id}/search")
async def search_lyrics(video_id: str, provider: str = Body("auto", embed=True)):
    """Lyrics suchen (Provider: auto, ytmusic, lrclib)."""
    result = await lyrics_service.fetch_and_save(video_id, provider=provider)
    return result


@router.post("/{video_id}/search-all")
async def search_lyrics_all(video_id: str):
    """ALLE Versionen von LRCLIB zurückgeben (für Auswahl)."""
    info = await lyrics_service.get_music_info(video_id)
    if not info.get("artist") or not info.get("title"):
        return {"status": "error", "results": [], "message": "Artist/Titel fehlen"}
    results = await lyrics_service.search_lyrics_all(info["artist"], info["title"])
    return {"status": "ok", "results": results}


@router.post("/{video_id}/pick")
async def pick_lyrics(
    video_id: str,
    lrclib_id: int = Body(...),
    plain: str = Body(""),
    synced: str = Body(None),
    artist: str = Body(""),
    title: str = Body(""),
    album: str = Body(""),
):
    """Eine bestimmte LRCLIB-Version übernehmen."""
    lyrics_service.save_lyrics(video_id, plain, synced)
    await lyrics_service.set_lyrics_status(video_id, True, "lrclib", lrclib_id)
    if artist and title:
        await lyrics_service.set_music_info(video_id, True, artist, title, album)
    return {"status": "ok"}


@router.post("/{video_id}/music-info")
async def update_music_info(
    video_id: str,
    is_music: bool = Body(...),
    artist: str = Body(""),
    title: str = Body(""),
    album: str = Body(""),
):
    """Musik-Metadaten manuell setzen."""
    await lyrics_service.set_music_info(video_id, is_music, artist, title, album)
    return {"status": "ok"}


@router.post("/{video_id}/save")
async def save_lyrics_manual(
    video_id: str,
    plain: str = Body(""),
    synced: str = Body(None),
):
    """Lyrics manuell speichern."""
    lyrics_service.save_lyrics(video_id, plain, synced)
    await lyrics_service.set_lyrics_status(video_id, bool(plain), "manual")
    return {"status": "ok"}


@router.delete("/{video_id}")
async def delete_lyrics(video_id: str):
    """Lyrics löschen."""
    lyrics_service.delete_lyrics(video_id)
    await lyrics_service.set_lyrics_status(video_id, False, "")
    return {"status": "ok"}



# batch-detect und batch-search entfernt in v1.8.91
# (90-95% Fehlerkennungen, verursacht mehr Probleme als es löst)


@router.post("/{video_id}/from-subtitle")
async def lyrics_from_subtitle(video_id: str, subtitle_code: str = Body("en", embed=True)):
    """YouTube-Untertitel als Lyrics importieren."""
    from app.config import SUBTITLES_DIR
    sdir = SUBTITLES_DIR / video_id
    # Find matching subtitle file
    sub_file = None
    for ext in [".vtt", ".srt"]:
        candidate = sdir / f"{subtitle_code}{ext}"
        if candidate.exists():
            sub_file = candidate
            break
    if not sub_file:
        # Try partial match
        if sdir.exists():
            for f in sdir.iterdir():
                if f.stem.startswith(subtitle_code) and f.suffix in (".vtt", ".srt"):
                    sub_file = f
                    break
    if not sub_file:
        return {"status": "error", "message": f"Untertitel '{subtitle_code}' nicht gefunden"}

    vtt_text = sub_file.read_text(encoding="utf-8")
    plain, synced = lyrics_service.vtt_to_lrc(vtt_text)
    if not plain and not synced:
        return {"status": "error", "message": "Keine Textdaten im Untertitel"}

    lyrics_service.save_lyrics(video_id, plain, synced)
    await lyrics_service.set_lyrics_status(video_id, True, f"subtitle:{subtitle_code}")
    return {"status": "ok", "plain_lines": plain.count('\n') + 1, "synced_lines": synced.count('\n') + 1}


@router.post("/{video_id}/offset")
async def save_offset(video_id: str, offset: float = Body(..., embed=True)):
    """Sync-Offset speichern."""
    lyrics_service.save_offset(video_id, offset)
    return {"status": "ok", "offset": offset}


@router.post("/{video_id}/upload-lrc")
async def upload_lrc(video_id: str, plain: str = Body(""), synced: str = Body("")):
    """LRC/Text-Datei hochladen (synced und/oder plain)."""
    if not plain and not synced:
        return {"status": "error", "message": "Kein Text übergeben"}
    lyrics_service.save_lyrics(video_id, plain, synced)
    await lyrics_service.set_lyrics_status(video_id, True, "upload")
    return {"status": "ok"}

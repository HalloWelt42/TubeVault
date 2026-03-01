"""
TubeVault -  Player Router v1.3.0
Video-Streaming mit Range Requests + Archive-Support
Subtitles, Audio-Extraktion
© HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
"""

import os
import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse

from app.database import db
from app.config import THUMBNAILS_DIR
from app.services.archive_service import archive_service

router = APIRouter(prefix="/api/player", tags=["Player"])

CHUNK_SIZE = 1024 * 1024  # 1MB


@router.get("/{video_id}")
async def stream_video(video_id: str, request: Request):
    """Video streamen -  prüft lokale + Archiv-Pfade."""
    video = await db.fetch_one(
        "SELECT file_path, file_size, storage_type, status FROM videos WHERE id = ?",
        (video_id,)
    )
    if not video:
        raise HTTPException(status_code=404, detail="Video nicht gefunden")

    # Pfad auflösen: lokal → Archiv → offline
    resolved = await archive_service.resolve_video_path(video_id)

    if not resolved["available"]:
        if resolved.get("archive_name"):
            raise HTTPException(
                status_code=503,
                detail=f"Externes Archiv '{resolved['archive_name']}' ist nicht verbunden. "
                       f"Bitte Festplatte anschließen oder Video erneut herunterladen."
            )
        raise HTTPException(status_code=404, detail="Video-Datei nicht gefunden")

    file_path = resolved["path"]

    file_size = os.path.getsize(file_path)
    mime_type = mimetypes.guess_type(file_path)[0] or "video/mp4"

    # Range Request Header parsen
    range_header = request.headers.get("range")

    if range_header:
        # Range: bytes=start-end
        range_str = range_header.replace("bytes=", "")
        parts = range_str.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if parts[1] else file_size - 1

        # Grenzen prüfen
        if start >= file_size:
            raise HTTPException(status_code=416, detail="Range Not Satisfiable")
        end = min(end, file_size - 1)
        content_length = end - start + 1

        async def generate():
            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = content_length
                while remaining > 0:
                    chunk = f.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            generate(),
            status_code=206,
            media_type=mime_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Content-Length": str(content_length),
                "Accept-Ranges": "bytes",
                "Cache-Control": "no-cache",
            },
        )
    else:
        # Kein Range Request → komplette Datei
        async def generate_full():
            with open(file_path, "rb") as f:
                while chunk := f.read(CHUNK_SIZE):
                    yield chunk

        return StreamingResponse(
            generate_full(),
            media_type=mime_type,
            headers={
                "Content-Length": str(file_size),
                "Accept-Ranges": "bytes",
            },
        )


@router.get("/{video_id}/stream/{stream_id}")
async def stream_specific(video_id: str, stream_id: int, request: Request):
    """Spezifischen Stream (Audio oder Video) streamen."""
    stream = await db.fetch_one(
        "SELECT file_path, mime_type FROM streams WHERE id = ? AND video_id = ? AND downloaded = 1",
        (stream_id, video_id)
    )
    if not stream:
        raise HTTPException(status_code=404, detail="Stream nicht gefunden")

    file_path = stream["file_path"]
    if not file_path or not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="Stream-Datei nicht gefunden")

    file_size = os.path.getsize(file_path)
    mime_type = stream["mime_type"] or "application/octet-stream"

    range_header = request.headers.get("range")
    if range_header:
        range_str = range_header.replace("bytes=", "")
        parts = range_str.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if parts[1] else file_size - 1
        end = min(end, file_size - 1)
        content_length = end - start + 1

        async def generate():
            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = content_length
                while remaining > 0:
                    chunk = f.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            generate(),
            status_code=206,
            media_type=mime_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Content-Length": str(content_length),
                "Accept-Ranges": "bytes",
            },
        )

    return FileResponse(file_path, media_type=mime_type)


@router.get("/{video_id}/thumbnail")
async def get_thumbnail(video_id: str):
    """Thumbnail abrufen -  mit Cache-Control für Browser/Nginx."""
    video = await db.fetch_one(
        "SELECT thumbnail_path FROM videos WHERE id = ?", (video_id,)
    )

    cache_headers = {"Cache-Control": "public, max-age=86400", "Vary": "Accept"}

    if video and video["thumbnail_path"]:
        thumb_path = Path(video["thumbnail_path"])
        if thumb_path.exists():
            return FileResponse(str(thumb_path), media_type="image/jpeg", headers=cache_headers)

    # Fallback 1: Standard-Pfad (YT-Downloads: video_id/thumbnail.jpg)
    thumb_path = THUMBNAILS_DIR / video_id / "thumbnail.jpg"
    if thumb_path.exists():
        return FileResponse(str(thumb_path), media_type="image/jpeg", headers=cache_headers)

    # Fallback 2: Flacher Pfad (Importe: video_id.jpg)
    for ext in [".jpg", ".png", ".webp"]:
        thumb_path = THUMBNAILS_DIR / f"{video_id}{ext}"
        if thumb_path.exists():
            return FileResponse(str(thumb_path), media_type=f"image/{'jpeg' if ext == '.jpg' else ext[1:]}", headers=cache_headers)

    raise HTTPException(status_code=404, detail="Thumbnail nicht gefunden")


@router.get("/{video_id}/subtitles")
async def list_subtitles(video_id: str):
    """Verfügbare Untertitel für ein Video auflisten."""
    from app.config import SUBTITLES_DIR
    sdir = SUBTITLES_DIR / video_id
    if not sdir.exists():
        return {"subtitles": []}

    subs = []
    for f in sorted(sdir.iterdir()):
        if f.suffix in (".vtt", ".srt"):
            subs.append({
                "code": f.stem,
                "name": f.stem,
                "path": f"/{video_id}/subtitle/{f.name}",
                "size": f.stat().st_size,
            })
    return {"subtitles": subs}


@router.get("/{video_id}/subtitle/{filename}")
async def get_subtitle(video_id: str, filename: str):
    """Untertitel-Datei abrufen. Akzeptiert 'a.de', 'a.de.vtt', 'de.vtt' etc."""
    from app.config import SUBTITLES_DIR
    sub_dir = SUBTITLES_DIR / video_id
    sub_path = sub_dir / filename

    # Direkt gefunden
    if sub_path.exists() and sub_path.is_relative_to(SUBTITLES_DIR):
        return FileResponse(str(sub_path), media_type="text/vtt")

    # Probiere mit .vtt / .srt Endung
    for ext in (".vtt", ".srt"):
        candidate = sub_dir / f"{filename}{ext}"
        if candidate.exists() and candidate.is_relative_to(SUBTITLES_DIR):
            return FileResponse(str(candidate), media_type="text/vtt")

    raise HTTPException(status_code=404, detail="Untertitel nicht gefunden")


@router.post("/{video_id}/subtitles/download")
async def download_subtitles(video_id: str, lang: str = "de"):
    """Untertitel von YouTube herunterladen."""
    from app.services.download_service import download_service
    try:
        result = await download_service.download_subtitles(video_id, lang)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{video_id}/audio/extract")
async def extract_audio(video_id: str, format: str = "mp3"):
    """Audio aus Video extrahieren (mp3, m4a, flac, ogg)."""
    from app.services.download_service import download_service
    try:
        result = await download_service.extract_audio(video_id, format)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{video_id}/audio")
async def get_audio(video_id: str):
    """Extrahierte Audio-Datei abrufen."""
    from app.config import AUDIO_DIR
    adir = AUDIO_DIR / video_id
    if not adir.exists():
        raise HTTPException(status_code=404, detail="Audio nicht gefunden. Erst extrahieren.")

    for ext in ("mp3", "m4a", "flac", "ogg"):
        audio_path = adir / f"audio.{ext}"
        if audio_path.exists():
            mime_map = {"mp3": "audio/mpeg", "m4a": "audio/mp4", "flac": "audio/flac", "ogg": "audio/ogg"}
            return FileResponse(str(audio_path), media_type=mime_map.get(ext, "audio/mpeg"))

    raise HTTPException(status_code=404, detail="Audio nicht gefunden")

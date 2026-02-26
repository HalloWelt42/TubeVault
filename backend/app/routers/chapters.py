"""
TubeVault – Chapters Router v1.3.0
Video-Kapitel (YouTube + manuell erstellte)
© HalloWelt42 – Private Nutzung
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.database import db
from app.services.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chapters", tags=["Chapters"])


async def fetch_and_save_chapters(video_id: str) -> int:
    """Kapitel von YouTube laden und speichern. Gibt Anzahl zurück."""
    await rate_limiter.acquire("pytubefix")

    def _fetch():
        from pytubefix import YouTube
        yt = YouTube(f"https://www.youtube.com/watch?v={video_id}")
        chapters = []
        try:
            for ch in yt.chapters:
                chapters.append({
                    "title": ch.title,
                    "start_time": ch.start_seconds,
                    "end_time": ch.start_seconds + ch.duration,
                })
        except Exception:
            pass
        return chapters

    try:
        chapters = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        rate_limiter.success("pytubefix")
    except Exception as e:
        rate_limiter.error("pytubefix", str(e)[:200])
        raise RuntimeError(f"Kapitel-Abruf fehlgeschlagen: {e}")

    await db.execute("DELETE FROM chapters WHERE video_id = ? AND source = 'youtube'", (video_id,))
    for ch in chapters:
        await db.execute(
            """INSERT INTO chapters (video_id, title, start_time, end_time, source)
               VALUES (?, ?, ?, ?, 'youtube')""",
            (video_id, ch["title"], ch["start_time"], ch.get("end_time")))
    return len(chapters)


class ChapterCreate(BaseModel):
    title: str
    start_time: float
    end_time: Optional[float] = None


class ChapterUpdate(BaseModel):
    title: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None


@router.get("/{video_id}")
async def get_chapters(video_id: str):
    """Alle Kapitel eines Videos abrufen."""
    rows = await db.fetch_all(
        "SELECT * FROM chapters WHERE video_id = ? ORDER BY start_time ASC",
        (video_id,)
    )
    return {"video_id": video_id, "chapters": [dict(r) for r in rows]}


@router.post("/{video_id}")
async def add_chapter(video_id: str, data: ChapterCreate):
    """Manuelles Kapitel hinzufügen."""
    video = await db.fetch_one("SELECT id FROM videos WHERE id = ?", (video_id,))
    if not video:
        raise HTTPException(status_code=404, detail="Video nicht gefunden")

    cursor = await db.execute(
        """INSERT INTO chapters (video_id, title, start_time, end_time, source)
           VALUES (?, ?, ?, ?, 'manual')""",
        (video_id, data.title, data.start_time, data.end_time)
    )
    return {"id": cursor.lastrowid, "created": True}


@router.put("/{chapter_id}")
async def update_chapter(chapter_id: int, data: ChapterUpdate):
    """Kapitel aktualisieren."""
    updates = data.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Keine Änderungen")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [chapter_id]
    await db.execute(f"UPDATE chapters SET {set_clause} WHERE id = ?", values)
    return {"updated": True}


@router.delete("/{chapter_id}")
async def delete_chapter(chapter_id: int):
    """Kapitel löschen."""
    await db.execute("DELETE FROM chapters WHERE id = ?", (chapter_id,))
    return {"deleted": True}


@router.delete("/{video_id}/all")
async def delete_all_chapters(video_id: str):
    """Alle Kapitel eines Videos löschen."""
    cursor = await db.execute("DELETE FROM chapters WHERE video_id = ?", (video_id,))
    return {"deleted": cursor.rowcount}


@router.post("/{video_id}/fetch")
async def fetch_youtube_chapters(video_id: str):
    """Kapitel von YouTube nachladen (rate-limited).
    Funktioniert für YouTube-Videos UND importierte Videos mit gültiger YouTube-ID.
    """
    video = await db.fetch_one("SELECT id, source FROM videos WHERE id = ?", (video_id,))
    if not video:
        raise HTTPException(status_code=404, detail="Video nicht gefunden")

    # Prüfe ob gültige YouTube-ID (11 Zeichen, nicht local_)
    if video_id.startswith("local_") or len(video_id) != 11:
        raise HTTPException(status_code=400, detail="Keine gültige YouTube-ID")

    await rate_limiter.acquire("pytubefix")

    def _fetch():
        from pytubefix import YouTube
        yt = YouTube(f"https://www.youtube.com/watch?v={video_id}")
        chapters = []
        try:
            for ch in yt.chapters:
                chapters.append({
                    "title": ch.title,
                    "start_time": ch.start_seconds,
                    "end_time": ch.start_seconds + ch.duration,
                })
        except Exception:
            pass
        return chapters

    try:
        chapters = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        rate_limiter.success("pytubefix")
    except Exception as e:
        rate_limiter.error("pytubefix", str(e)[:200])
        raise HTTPException(status_code=500, detail=f"Kapitel-Abruf fehlgeschlagen: {e}")

    # Alte YouTube-Kapitel entfernen, neue einfügen
    await db.execute("DELETE FROM chapters WHERE video_id = ? AND source = 'youtube'", (video_id,))
    for ch in chapters:
        await db.execute(
            """INSERT INTO chapters (video_id, title, start_time, end_time, source)
               VALUES (?, ?, ?, ?, 'youtube')""",
            (video_id, ch["title"], ch["start_time"], ch.get("end_time"))
        )

    return {"video_id": video_id, "chapters": chapters, "count": len(chapters)}



async def generate_chapter_thumbs(video_id: str) -> int:
    """Vorschaubilder für Kapitel generieren. Gibt Anzahl zurück."""
    import subprocess
    from pathlib import Path
    from app.config import DATA_DIR

    video = await db.fetch_one(
        "SELECT file_path FROM videos WHERE id = ?", (video_id,))
    if not video or not video["file_path"]:
        logger.warning(f"Chapter-Thumbs: Kein Video oder file_path für {video_id}")
        return 0

    fp = Path(video["file_path"])
    if not fp.exists():
        logger.warning(f"Chapter-Thumbs: Datei nicht gefunden: {fp}")
        return 0

    chapters = await db.fetch_all(
        "SELECT id, start_time, thumbnail_url FROM chapters WHERE video_id = ? ORDER BY start_time",
        (video_id,))
    if not chapters:
        return 0

    thumb_dir = DATA_DIR / "chapter_thumbs" / video_id
    thumb_dir.mkdir(parents=True, exist_ok=True)

    generated = 0
    for ch in chapters:
        dest = thumb_dir / f"{ch['id']}.jpg"
        # Skip wenn Thumb schon existiert
        if ch["thumbnail_url"] and dest.exists():
            continue

        seek = max(0, ch["start_time"] + 2)
        try:
            result = subprocess.run(
                ["ffmpeg", "-ss", str(seek), "-i", str(fp),
                 "-vframes", "1", "-vf", "scale=1280:-1",
                 "-q:v", "3", str(dest), "-y"],
                capture_output=True, timeout=15)
            if dest.exists() and dest.stat().st_size > 0:
                await db.execute(
                    "UPDATE chapters SET thumbnail_url = ? WHERE id = ?",
                    (f"/api/chapters/thumb/{video_id}/{ch['id']}", ch["id"]))
                generated += 1
            elif result.returncode != 0:
                logger.warning(f"ffmpeg failed ch={ch['id']}: {result.stderr.decode('utf-8', errors='replace')[:200]}")
        except Exception as e:
            logger.warning(f"Chapter-Thumb fehlgeschlagen: ch={ch['id']} err={e}")

    return generated

    return generated


@router.post("/{video_id}/generate-thumbnails")
async def generate_chapter_thumbnails(video_id: str):
    """Vorschaubilder für alle Kapitel generieren (ffmpeg)."""
    try:
        count = await generate_chapter_thumbs(video_id)
    except Exception as e:
        logger.error(f"Chapter-Thumbnails für {video_id} fehlgeschlagen: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Thumbnail-Generierung fehlgeschlagen: {str(e)}")
    chapters = await db.fetch_all("SELECT id FROM chapters WHERE video_id = ?", (video_id,))
    if not chapters:
        raise HTTPException(status_code=404, detail="Keine Kapitel vorhanden")
    return {"status": "ok", "generated": count, "total": len(chapters)}


@router.get("/thumb/{video_id}/{chapter_id}")
async def get_chapter_thumbnail(video_id: str, chapter_id: int):
    """Kapitel-Vorschaubild ausliefern."""
    from pathlib import Path
    from app.config import DATA_DIR
    from fastapi.responses import FileResponse

    dest = DATA_DIR / "chapter_thumbs" / video_id / f"{chapter_id}.jpg"
    if dest.exists():
        return FileResponse(str(dest), media_type="image/jpeg",
                            headers={"Cache-Control": "public, max-age=604800"})
    raise HTTPException(status_code=404, detail="Chapter-Thumbnail nicht gefunden")


@router.post("/regenerate-all-thumbnails")
async def regenerate_all_chapter_thumbnails():
    """Alle Kapitel-Vorschaubilder für alle Videos neu generieren."""
    import subprocess
    from pathlib import Path
    from app.config import DATA_DIR

    # Alle Videos mit Kapiteln finden
    videos = await db.fetch_all(
        """SELECT DISTINCT v.id, v.file_path FROM videos v
           INNER JOIN chapters c ON c.video_id = v.id
           WHERE v.status = 'ready' AND v.file_path IS NOT NULL"""
    )

    total_generated = 0
    total_chapters = 0
    videos_processed = 0

    for vid in videos:
        fp = Path(vid["file_path"])
        if not fp.exists():
            continue

        chapters = await db.fetch_all(
            "SELECT id, start_time FROM chapters WHERE video_id = ? ORDER BY start_time",
            (vid["id"],))
        if not chapters:
            continue

        thumb_dir = DATA_DIR / "chapter_thumbs" / vid["id"]
        thumb_dir.mkdir(parents=True, exist_ok=True)

        for ch in chapters:
            total_chapters += 1
            dest = thumb_dir / f"{ch['id']}.jpg"
            seek = max(0, ch["start_time"] + 2)
            try:
                subprocess.run(
                    ["ffmpeg", "-ss", str(seek), "-i", str(fp),
                     "-vframes", "1", "-vf", "scale=1280:-1",
                     "-q:v", "3", str(dest), "-y"],
                    capture_output=True, timeout=15)
                if dest.exists() and dest.stat().st_size > 0:
                    await db.execute(
                        "UPDATE chapters SET thumbnail_url = ? WHERE id = ?",
                        (f"/api/chapters/thumb/{vid['id']}/{ch['id']}", ch["id"]))
                    total_generated += 1
            except Exception:
                pass
        videos_processed += 1

    return {
        "status": "ok",
        "videos_processed": videos_processed,
        "total_chapters": total_chapters,
        "generated": total_generated,
    }

"""
TubeVault – Eigene Videos Router v1.8.77
© HalloWelt42 – Private Nutzung

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


# ─── Hilfsfunktionen ──────────────────────────────────────

def _cleanup_companions(src_path: Path):
    """Begleitdateien einer Scan-Datei löschen (read-only safe)."""
    base = src_path.with_suffix("")
    for ext in [".nfo", ".description", ".txt", ".info.json",
                ".jpg", ".png", ".webp", "-poster.jpg", "-poster.png",
                ".srt", ".vtt", ".de.srt", ".en.srt", ".de.vtt", ".en.vtt"]:
        comp = base.parent / (base.name + ext)
        try:
            if comp.exists():
                comp.unlink()
        except OSError:
            pass
    # Leeren Ordner entfernen
    try:
        parent = src_path.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
    except OSError:
        pass


async def _mark_duplicates_in_session(session_id: int, video_id: str):
    """Andere Staging-Einträge die dasselbe Video referenzieren als Duplikat markieren."""
    from app.database import db
    await db.execute(
        """UPDATE scan_staging SET decision='skip', decision_at=datetime('now'),
           match_type='duplicate', match_id=?
           WHERE session_id = ? AND decision IS NULL
           AND (youtube_id = ? OR match_id = ?)""",
        (video_id, session_id, video_id, video_id)
    )


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
    """Verzeichnis scannen (SYNCHRON – nur für kleine Verzeichnisse!).
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
    """Import rückgängig machen – Video aus DB entfernen.
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
    """RSS-Entries durchsuchen – für manuelles Matching aus der Scan-Liste.
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


# ─── Sofort-Aktionen (kein Batch-Execute nötig) ────────────────

class LinkYoutubeRequest(BaseModel):
    youtube_id: str
    category_id: int | None = None

class ImportOwnRequest(BaseModel):
    category_id: int | None = None
    channel_name: str | None = None


@router.post("/staging/{staging_id}/link-youtube")
async def link_youtube(staging_id: int, req: LinkYoutubeRequest):
    """Scan-Datei sofort mit YouTube-Video verknüpfen.
    Holt Metadaten von YouTube, verschiebt Datei, erstellt Video-Eintrag.
    """
    from app.database import db
    from app.config import VIDEOS_DIR, THUMBNAILS_DIR, SUBTITLES_DIR
    from app.services.rate_limiter import rate_limiter
    import asyncio, shutil, json
    from datetime import datetime

    # 1. Staging-Eintrag holen
    row = await db.fetch_one(
        "SELECT * FROM scan_staging WHERE id = ?", (staging_id,)
    )
    if not row:
        raise HTTPException(404, "Staging-Eintrag nicht gefunden")

    src_path = Path(row["file_path"])
    yt_id = req.youtube_id.strip()
    if not yt_id or len(yt_id) < 8:
        raise HTTPException(400, "Ungültige YouTube-ID")

    # 2. Prüfen ob Video schon in Bibliothek existiert
    existing = await db.fetch_one(
        "SELECT id, title, file_path, status FROM videos WHERE id = ?", (yt_id,)
    )
    if existing and existing["status"] == "ready":
        # Video existiert schon → Scan-Datei als Duplikat markieren + Quelle aufräumen
        await db.execute(
            "UPDATE scan_staging SET decision='skip', decision_at=datetime('now'), "
            "match_type='duplicate', match_id=?, match_title=? WHERE id=?",
            (yt_id, existing["title"], staging_id)
        )
        # Quelldatei + Begleitdateien löschen wenn möglich
        if src_path.exists():
            try:
                src_path.unlink()
            except OSError:
                pass
            _cleanup_companions(src_path)
        # Andere Staging-Einträge mit gleichem Video auch als Duplikat markieren
        await _mark_duplicates_in_session(row["session_id"], yt_id)
        return {
            "success": True,
            "video_id": yt_id,
            "title": existing["title"],
            "already_existed": True,
            "message": "Video existiert bereits — Scan-Datei als Duplikat markiert",
        }

    # 3. Quelldatei muss existieren für echten Import
    if not src_path.exists():
        raise HTTPException(404, f"Datei nicht gefunden: {src_path}")

    # 4. YouTube-Metadaten holen
    await rate_limiter.acquire("pytubefix")
    try:
        def _fetch():
            from app.utils.pytube_client import make_youtube
            yt = make_youtube(f"https://www.youtube.com/watch?v={yt_id}")
            chapters = []
            try:
                for ch in (yt.chapters or []):
                    chapters.append({
                        "title": ch.title,
                        "start_time": ch.start_seconds,
                        "end_time": getattr(ch, "end_seconds", None),
                    })
            except Exception:
                pass
            captions = []
            try:
                for cap in yt.captions:
                    captions.append({"code": cap.code, "name": cap.name})
            except Exception:
                pass
            return {
                "title": yt.title,
                "channel_name": yt.author,
                "channel_id": yt.channel_id,
                "description": (yt.description or "")[:2000],
                "duration": yt.length,
                "view_count": yt.views,
                "thumbnail_url": yt.thumbnail_url,
                "publish_date": str(yt.publish_date) if yt.publish_date else None,
                "keywords": yt.keywords or [],
                "chapters": chapters,
                "captions": captions,
            }
        meta = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        rate_limiter.success("pytubefix")
    except Exception as e:
        rate_limiter.error("pytubefix", str(e)[:200])
        raise HTTPException(502, f"YouTube-Metadaten nicht abrufbar: {str(e)[:200]}")

    # 5. Datei kopieren (Quelle kann read-only sein)
    ext = src_path.suffix.lower()
    dest = VIDEOS_DIR / f"{yt_id}{ext}"
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    if src_path != dest:
        if dest.exists() and dest.stat().st_size == src_path.stat().st_size:
            pass  # Identische Datei am Ziel, nichts tun
        else:
            try:
                shutil.move(str(src_path), str(dest))
            except OSError:
                shutil.copy2(str(src_path), str(dest))

    # 6. Thumbnail von YouTube laden
    thumb_path = None
    try:
        if meta.get("thumbnail_url"):
            import urllib.request
            thumb_dest = THUMBNAILS_DIR / f"{yt_id}.jpg"
            THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: urllib.request.urlretrieve(meta["thumbnail_url"], str(thumb_dest))
            )
            thumb_path = f"thumbnails/{yt_id}.jpg"
    except Exception as e:
        logger.warning(f"Thumbnail-Download für {yt_id}: {e}")

    # 7. Untertitel kopieren (falls vorhanden)
    SUBTITLES_DIR.mkdir(parents=True, exist_ok=True)
    for sub_ext in [".srt", ".vtt", ".de.srt", ".en.srt", ".de.vtt", ".en.vtt"]:
        sub_src = src_path.with_suffix(sub_ext)
        if sub_src.exists():
            try:
                shutil.move(str(sub_src), str(SUBTITLES_DIR / f"{yt_id}{sub_ext}"))
            except OSError:
                shutil.copy2(str(sub_src), str(SUBTITLES_DIR / f"{yt_id}{sub_ext}"))

    # 8. Begleitdateien aufräumen (ignoriert read-only)
    for comp_ext in [".nfo", ".description", ".txt", ".info.json"]:
        comp = src_path.with_suffix(comp_ext)
        try:
            if comp.exists():
                comp.unlink()
        except OSError:
            pass

    # 9. Video in DB anlegen/updaten
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_size = dest.stat().st_size if dest.exists() else 0
    tags_json = json.dumps(meta.get("keywords", [])[:20], ensure_ascii=False)

    # Channel-ID: immer von pytubefix, nicht nur wenn Subscription existiert
    channel_id = meta.get("channel_id")

    existing = await db.fetch_one("SELECT id FROM videos WHERE id = ?", (yt_id,))
    if existing:
        await db.execute(
            """UPDATE videos SET title=?, channel_name=?, channel_id=?, description=?,
               duration=?, view_count=?, thumbnail_path=?, file_path=?, file_size=?,
               status='ready', source='imported', tags=?, updated_at=?,
               upload_date=?, download_date=?
               WHERE id=?""",
            (meta["title"], meta["channel_name"], channel_id, meta["description"],
             meta["duration"], meta["view_count"], thumb_path, str(dest), file_size,
             tags_json, now, meta.get("publish_date"), now, yt_id)
        )
    else:
        await db.execute(
            """INSERT INTO videos (id, title, channel_name, channel_id, description,
               duration, view_count, thumbnail_path, file_path, file_size,
               status, source, tags, created_at, updated_at, upload_date, download_date)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (yt_id, meta["title"], meta["channel_name"], channel_id, meta["description"],
             meta["duration"], meta["view_count"], thumb_path, str(dest), file_size,
             "ready", "imported", tags_json, now, now, meta.get("publish_date"), now)
        )

    # 10. FTS5 aktualisieren
    try:
        await db.fts_sync_video(yt_id)
    except Exception:
        pass

    # 10b. Kategorie zuweisen
    if req.category_id:
        await db.execute(
            "INSERT OR IGNORE INTO video_categories (video_id, category_id) VALUES (?,?)",
            (yt_id, req.category_id)
        )

    # 10c. Kapitel speichern (wie im Download-Service)
    try:
        auto_chapters = await db.fetch_val("SELECT value FROM settings WHERE key = 'download.auto_chapters'")
        if auto_chapters != "false" and meta.get("chapters"):
            for ch in meta["chapters"]:
                await db.execute(
                    """INSERT OR IGNORE INTO chapters (video_id, title, start_time, end_time, source)
                       VALUES (?, ?, ?, ?, 'youtube')""",
                    (yt_id, ch["title"], ch["start_time"], ch.get("end_time"))
                )
    except Exception as e:
        logger.warning(f"Chapters-Import für {yt_id}: {e}")

    # 10d. Untertitel von YouTube laden (wenn Setting aktiv und keine lokalen vorhanden)
    try:
        sub_setting = await db.fetch_val("SELECT value FROM settings WHERE key = 'download.auto_subtitle'")
        if sub_setting == "true" and meta.get("captions"):
            from app.services.download_service import download_service
            lang_setting = await db.fetch_val("SELECT value FROM settings WHERE key = 'download.subtitle_lang'")
            langs = (lang_setting or "de,en").split(",")
            for lang in langs:
                await download_service.download_subtitles(yt_id, lang.strip())
    except Exception as e:
        logger.warning(f"Auto-Subtitle für {yt_id}: {e}")

    # 10e. Playlist Auto-Link
    try:
        from app.services.playlist_service import auto_link_video_to_playlists
        await auto_link_video_to_playlists(yt_id)
    except Exception as e:
        logger.debug(f"Playlist Auto-Link für {yt_id}: {e}")

    # 10f. RYD (Return YouTube Dislike) Votes
    try:
        from app.services.ryd_service import fetch_votes
        await fetch_votes(yt_id)
    except Exception as e:
        logger.debug(f"RYD-Fetch für {yt_id}: {e}")

    # 11. Staging als erledigt markieren
    await db.execute(
        "UPDATE scan_staging SET decision='link', decision_at=datetime('now') WHERE id=?",
        (staging_id,)
    )

    # 12. Andere Staging-Einträge mit gleichem Video als Duplikat markieren
    await _mark_duplicates_in_session(row["session_id"], yt_id)

    # 13. Begleitdateien aufräumen (read-only safe)
    _cleanup_companions(src_path)

    return {
        "success": True,
        "video_id": yt_id,
        "title": meta["title"],
        "channel_name": meta["channel_name"],
        "file_path": str(dest),
    }


@router.post("/staging/{staging_id}/import-own")
async def import_own(staging_id: int, req: ImportOwnRequest):
    """Scan-Datei sofort als eigenes Video importieren (ohne YouTube-Verknüpfung)."""
    from app.database import db
    from app.config import VIDEOS_DIR, THUMBNAILS_DIR, SUBTITLES_DIR
    import shutil, uuid
    from datetime import datetime

    row = await db.fetch_one(
        "SELECT * FROM scan_staging WHERE id = ?", (staging_id,)
    )
    if not row:
        raise HTTPException(404, "Staging-Eintrag nicht gefunden")
    row = dict(row)  # sqlite3.Row → dict

    src_path = Path(row["file_path"])
    if not src_path.exists():
        raise HTTPException(404, f"Datei nicht gefunden: {src_path}")

    # Video-ID: YouTube-ID aus Scan oder UUID
    yt_id = row.get("youtube_id")
    video_id = yt_id or f"own_{uuid.uuid4().hex[:12]}"
    source = "imported" if yt_id else "local"
    channel = req.channel_name or row.get("channel_name") or row.get("folder_name") or "Unbekannt"

    # Datei kopieren (Quelle kann read-only sein)
    ext = src_path.suffix.lower()
    dest = VIDEOS_DIR / f"{video_id}{ext}"
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    if src_path != dest:
        try:
            shutil.move(str(src_path), str(dest))
        except OSError:
            shutil.copy2(str(src_path), str(dest))

    # Thumbnail: Begleit-Thumbnail oder generieren
    thumb_path = None
    thumb_patterns = []
    base = src_path.with_suffix("")
    for thumb_ext in [".jpg", ".png", ".webp"]:
        thumb_patterns.append(base.with_suffix(thumb_ext))
        thumb_patterns.append(base.parent / (base.name + "-poster" + thumb_ext))
    for thumb_src in thumb_patterns:
        if thumb_src.exists():
            THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)
            thumb_dest = THUMBNAILS_DIR / f"{video_id}.jpg"
            try:
                shutil.move(str(thumb_src), str(thumb_dest))
            except OSError:
                shutil.copy2(str(thumb_src), str(thumb_dest))
            thumb_path = f"thumbnails/{video_id}.jpg"
            break

    # Untertitel kopieren
    SUBTITLES_DIR.mkdir(parents=True, exist_ok=True)
    for sub_ext in [".srt", ".vtt", ".de.srt", ".en.srt", ".de.vtt", ".en.vtt"]:
        sub_src = src_path.with_suffix("").parent / (src_path.stem + sub_ext)
        if sub_src.exists():
            try:
                shutil.move(str(sub_src), str(SUBTITLES_DIR / f"{video_id}{sub_ext}"))
            except OSError:
                shutil.copy2(str(sub_src), str(SUBTITLES_DIR / f"{video_id}{sub_ext}"))

    # Begleitdateien aufräumen (ignoriert read-only)
    for comp_ext in [".nfo", ".description", ".txt", ".info.json"]:
        comp = src_path.with_suffix(comp_ext)
        try:
            if comp.exists():
                comp.unlink()
        except OSError:
            pass

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_size = dest.stat().st_size if dest.exists() else 0

    # Channel-ID resolven
    channel_id = None
    ch_row = await db.fetch_one(
        "SELECT channel_id FROM subscriptions WHERE channel_name = ? OR channel_id = ?",
        (channel, channel)
    )
    if ch_row:
        channel_id = ch_row["channel_id"]

    await db.execute(
        """INSERT OR REPLACE INTO videos (id, title, channel_name, channel_id, description,
           duration, file_path, file_size, status, source, thumbnail_path,
           created_at, updated_at, download_date)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (video_id, row.get("title") or row["filename"], channel, channel_id,
         row.get("description_text"),
         row.get("duration"), str(dest), file_size,
         "ready", source, thumb_path, now, now, now)
    )

    # Kategorie zuweisen
    if req.category_id:
        await db.execute(
            "INSERT OR IGNORE INTO video_categories (video_id, category_id) VALUES (?,?)",
            (video_id, req.category_id)
        )

    # FTS5
    try:
        await db.fts_sync_video(video_id)
    except Exception:
        pass

    # Playlist Auto-Link
    try:
        from app.services.playlist_service import auto_link_video_to_playlists
        await auto_link_video_to_playlists(video_id)
    except Exception:
        pass

    # Staging als erledigt markieren
    await db.execute(
        "UPDATE scan_staging SET decision='import_new', decision_at=datetime('now') WHERE id=?",
        (staging_id,)
    )

    # Duplikate markieren + Begleitdateien aufräumen
    if row.get("youtube_id"):
        await _mark_duplicates_in_session(row["session_id"], row["youtube_id"])
    _cleanup_companions(src_path)

    return {
        "success": True,
        "video_id": video_id,
        "title": row.get("title") or row["filename"],
        "source": source,
        "file_path": str(dest),
    }


@router.post("/staging/{staging_id}/replace")
async def replace_video(staging_id: int):
    """Scan-Datei sofort als Ersatz für bestehendes Video übernehmen."""
    from app.database import db
    from app.config import VIDEOS_DIR, THUMBNAILS_DIR
    import shutil
    from datetime import datetime

    row = await db.fetch_one(
        "SELECT * FROM scan_staging WHERE id = ?", (staging_id,)
    )
    if not row:
        raise HTTPException(404, "Staging-Eintrag nicht gefunden")

    src_path = Path(row["file_path"])
    if not src_path.exists():
        raise HTTPException(404, f"Datei nicht gefunden: {src_path}")

    # match_id oder existing_id = das Video das ersetzt werden soll
    vid_id = row["match_id"] or row["existing_id"]
    if not vid_id:
        raise HTTPException(400, "Kein Ziel-Video zum Ersetzen gefunden")

    existing = await db.fetch_one(
        "SELECT file_path FROM videos WHERE id = ?", (vid_id,)
    )
    if not existing:
        raise HTTPException(404, f"Ziel-Video {vid_id} nicht in DB")

    # Datei kopieren
    ext = src_path.suffix.lower()
    dest = VIDEOS_DIR / f"{vid_id}{ext}"
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(src_path), str(dest))
    except OSError:
        shutil.copy2(str(src_path), str(dest))

    # Alte Datei löschen wenn anderer Pfad
    if existing["file_path"] and existing["file_path"] != str(dest):
        try:
            old_p = Path(existing["file_path"])
            if old_p.exists():
                old_p.unlink()
        except OSError:
            pass

    # DB aktualisieren
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_size = dest.stat().st_size if dest.exists() else 0
    await db.execute(
        """UPDATE videos SET file_path = ?, file_size = ?, status = 'ready',
           updated_at = ?, download_date = ? WHERE id = ?""",
        (str(dest), file_size, now, now, vid_id)
    )

    # FTS5
    try:
        await db.fts_sync_video(vid_id)
    except Exception:
        pass

    # Staging markieren
    await db.execute(
        "UPDATE scan_staging SET decision='replace', decision_at=datetime('now') WHERE id=?",
        (staging_id,)
    )

    # Begleitdateien aufräumen
    _cleanup_companions(src_path)

    return {"success": True, "video_id": vid_id, "file_path": str(dest)}


@router.post("/staging/{staging_id}/skip")
async def skip_staging(staging_id: int):
    """Scan-Datei überspringen (bleibt im Scan-Ordner)."""
    from app.database import db

    row = await db.fetch_one(
        "SELECT id FROM scan_staging WHERE id = ?", (staging_id,)
    )
    if not row:
        raise HTTPException(404, "Staging-Eintrag nicht gefunden")

    await db.execute(
        "UPDATE scan_staging SET decision='skip', decision_at=datetime('now') WHERE id=?",
        (staging_id,)
    )

    return {"success": True, "skipped": True}


@router.post("/staging/cleanup-missing")
async def cleanup_missing_files():
    """Staging-Einträge entfernen wo die Quelldatei nicht mehr existiert."""
    from app.database import db
    import os

    rows = await db.fetch_all(
        "SELECT id, file_path FROM scan_staging WHERE decision IS NULL"
    )

    removed = 0
    for r in rows:
        if not os.path.exists(r["file_path"]):
            await db.execute(
                "UPDATE scan_staging SET decision='skip', decision_at=datetime('now') WHERE id=?",
                (r["id"],)
            )
            removed += 1

    return {"success": True, "removed": removed, "checked": len(rows)}


@router.post("/staging/delete-folder")
async def delete_folder(session_id: int = Query(...), folder: str = Query(...)):
    """Alle Dateien eines Ordners löschen (Quelldateien + Begleitdateien + Ordner)."""
    from app.database import db
    import os, shutil

    rows = await db.fetch_all(
        """SELECT id, file_path FROM scan_staging
           WHERE session_id = ? AND COALESCE(channel_folder, folder_name) = ?
           AND (decision IS NULL OR decision = '')""",
        (session_id, folder)
    )

    deleted = 0
    errors = []
    for r in rows:
        fp = Path(r["file_path"])
        try:
            if fp.exists():
                fp.unlink()
            _cleanup_companions(fp)
            deleted += 1
        except OSError as e:
            errors.append(f"{fp.name}: {e}")

        await db.execute(
            "UPDATE scan_staging SET decision='delete', decision_at=datetime('now') WHERE id=?",
            (r["id"],)
        )

    # Ordner entfernen wenn leer
    scan_dir = Path("/app/data/scan")
    folder_path = scan_dir / folder
    try:
        if folder_path.exists():
            # Rekursiv leere Unterordner entfernen
            for dirpath, dirnames, filenames in os.walk(str(folder_path), topdown=False):
                dp = Path(dirpath)
                if not any(dp.iterdir()):
                    dp.rmdir()
    except OSError:
        pass

    return {"success": True, "deleted": deleted, "errors": errors}


@router.post("/staging/bulk-skip")
async def bulk_skip(
    session_id: int = Query(...),
    match_type: str = Query(None),
    folder: str = Query(None),
):
    """Mehrere Staging-Einträge auf einmal überspringen (nur DB-Flag, keine Datei-Ops)."""
    from app.database import db

    conditions = ["session_id = ?", "(decision IS NULL OR decision = '')"]
    params = [session_id]

    if match_type:
        conditions.append("match_type = ?")
        params.append(match_type)

    if folder:
        conditions.append("COALESCE(channel_folder, folder_name) = ?")
        params.append(folder)

    where = " AND ".join(conditions)
    cursor = await db.execute(
        f"UPDATE scan_staging SET decision='skip', decision_at=datetime('now') WHERE {where}",
        tuple(params)
    )

    return {"success": True, "skipped": cursor.rowcount}

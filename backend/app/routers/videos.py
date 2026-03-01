"""
TubeVault -  Videos Router v1.3.0
© HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
import logging

from app.models.video import VideoCreate, VideoUpdate, VideoResponse, VideoListResponse, VideoInfo
from app.services.download_service import download_service
from app.services.metadata_service import metadata_service
from app.database import db
from app.utils.file_utils import now_sqlite

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/videos", tags=["Videos"])


@router.get("", response_model=VideoListResponse)
async def list_videos(
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=100),
    status: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    category_ids: Optional[str] = None,
    channel_id: Optional[str] = None,
    channel_ids: Optional[str] = None,
    tag: Optional[str] = None,
    tags: Optional[str] = None,
    video_type: Optional[str] = None,
    video_types: Optional[str] = None,
    is_archived: Optional[bool] = None,
    is_music: Optional[bool] = None,
):
    """Alle Videos abrufen (paginiert, filterbar, sortierbar). Mehrfachfilter via Komma-getrennte IDs."""
    result = await metadata_service.get_videos(
        page=page, per_page=per_page, status=status,
        sort_by=sort_by, sort_order=sort_order,
        search=search, category_id=category_id,
        category_ids=category_ids,
        channel_id=channel_id, channel_ids=channel_ids,
        tag=tag, tags=tags, video_type=video_type, video_types=video_types,
        is_archived=is_archived, is_music=is_music,
    )
    return result


@router.get("/stats")
async def get_video_stats():
    """Video-Statistiken abrufen."""
    return await metadata_service.get_stats()


@router.get("/tags")
async def get_all_tags():
    """Alle verwendeten Tags mit Anzahl."""
    return await metadata_service.get_all_tags()


@router.get("/channels")
async def get_video_channels():
    """Alle Kanaele mit Video-Anzahl (fuer Filter-Dropdown)."""
    rows = await db.fetch_all(
        """SELECT channel_id, channel_name, COUNT(*) as count
           FROM videos WHERE status = 'ready' AND channel_id IS NOT NULL
           GROUP BY channel_id ORDER BY channel_name COLLATE NOCASE ASC"""
    )
    return [dict(r) for r in rows]


@router.get("/history")
async def get_watch_history(
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=100),
    search: Optional[str] = None,
    channel_id: Optional[str] = None,
    channel_ids: Optional[str] = None,
    video_type: Optional[str] = None,
    video_types: Optional[str] = None,
):
    """Watch-History abrufen (filterbar)."""
    return await metadata_service.get_watch_history(
        page=page, per_page=per_page, search=search,
        channel_id=channel_id, channel_ids=channel_ids,
        video_type=video_type, video_types=video_types,
    )


@router.delete("/history")
async def clear_watch_history():
    """Komplette Watch-History löschen."""
    await metadata_service.clear_watch_history()
    return {"message": "Watch-History gelöscht"}


@router.get("/info")
async def get_video_info(url: str):
    """Video-Informationen von YouTube abrufen (ohne Download)."""
    try:
        info = await download_service.get_video_info(url)
        return info
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"[VideoInfo] Endpoint-Fehler für {url}: {error_msg}")
        raise HTTPException(status_code=500, detail=f"Fehler beim Abrufen: {error_msg}")



@router.get("/search/notes")
async def search_notes(q: str = Query(..., min_length=1)):
    """Globale Suche in Video-Notizen."""
    rows = await db.fetch_all(
        """SELECT id, title, channel_name, notes, thumbnail_path
           FROM videos WHERE notes IS NOT NULL AND notes != ''
           AND notes LIKE ? ORDER BY updated_at DESC LIMIT 50""",
        (f"%{q}%",))
    return {"results": [dict(r) for r in rows], "query": q}


@router.get("/random")
async def get_random_video(exclude: str = None, count: int = 1, pool: str = "all"):
    """Zufälliges Video für Vorschläge. pool: all|library|music|own|archive."""
    count = max(1, min(count, 5))
    conditions = ["status = 'ready'"]
    params = []
    if exclude:
        conditions.append("id != ?")
        params.append(exclude)
    # Pool-Filter
    if pool == "library":
        conditions.append("source = 'youtube' AND is_archived = 0")
    elif pool == "music":
        conditions.append("is_music = 1")
    elif pool == "own":
        conditions.append("source IN ('local', 'imported')")
    elif pool == "archive":
        conditions.append("is_archived = 1")
    # else: all → kein zusätzlicher Filter

    # Suggest-Ausschluss: Kanal-Level + Video-Override
    conditions.append("""COALESCE(suggest_override,
        CASE WHEN channel_id IN (SELECT channel_id FROM subscriptions WHERE suggest_exclude = 1)
        THEN 'exclude' ELSE 'include' END) != 'exclude'""")
    where = " AND ".join(conditions)
    params.append(count)
    rows = await db.fetch_all(
        f"""SELECT id, title, channel_name, duration, thumbnail_path, source
            FROM videos WHERE {where}
            ORDER BY RANDOM() LIMIT ?""",
        tuple(params)
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Keine Videos in diesem Pool")
    if count == 1:
        return dict(rows[0])
    return [dict(r) for r in rows]


@router.get("/preview/{video_id}")
async def get_video_preview(video_id: str):
    """Video-Preview: lokal oder aus RSS-Daten. Für nicht-heruntergeladene Videos."""
    # 1) Lokal vorhanden?
    video = await metadata_service.get_video(video_id)
    if video:
        return {**video, "preview_mode": False, "is_downloaded": True}

    # 2) In RSS-Einträgen?
    rss = await db.fetch_one(
        """SELECT r.*, s.channel_name, s.download_quality, s.audio_only
           FROM rss_entries r
           JOIN subscriptions s ON r.channel_id = s.channel_id
           WHERE r.video_id = ?""",
        (video_id,)
    )
    if rss:
        return {
            "id": video_id,
            "title": rss["title"],
            "channel_name": rss["channel_name"],
            "channel_id": rss["channel_id"],
            "thumbnail_url": rss["thumbnail_url"],
            "published": rss["published"],
            "duration": rss["duration"],
            "view_count": rss["views"],
            "description": rss["description"],
            "download_quality": rss["download_quality"],
            "audio_only": rss["audio_only"],
            "preview_mode": True,
            "is_downloaded": False,
        }

    # 3) In videos-Tabelle als Metadaten (z.B. aus Import)?
    meta = await db.fetch_one("SELECT * FROM videos WHERE id = ?", (video_id,))
    if meta:
        result = dict(meta)
        result["preview_mode"] = result.get("status") != "ready"
        result["is_downloaded"] = result.get("status") == "ready"
        return result

    # 4) Nicht lokal/RSS → Basisdaten per YouTube-ID zurückgeben
    return {
        "id": video_id,
        "title": video_id,
        "channel_name": None,
        "channel_id": None,
        "thumbnail_url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        "published": None,
        "duration": None,
        "view_count": None,
        "description": None,
        "preview_mode": True,
        "is_downloaded": False,
    }


@router.get("/{video_id}/neighbors")
async def get_video_neighbors(video_id: str):
    """Vorheriges und nächstes Video in der Bibliothek (nach created_at desc)."""
    prev_row = await db.fetch_one(
        """SELECT id, title, channel_name, duration FROM videos
           WHERE status = 'ready' AND created_at > (
             SELECT created_at FROM videos WHERE id = ?
           ) ORDER BY created_at ASC LIMIT 1""",
        (video_id,),
    )
    next_row = await db.fetch_one(
        """SELECT id, title, channel_name, duration FROM videos
           WHERE status = 'ready' AND created_at < (
             SELECT created_at FROM videos WHERE id = ?
           ) ORDER BY created_at DESC LIMIT 1""",
        (video_id,),
    )
    return {
        "prev": dict(prev_row) if prev_row else None,
        "next": dict(next_row) if next_row else None,
    }


@router.get("/{video_id}")
async def get_video(video_id: str):
    """Einzelnes Video abrufen -  inkl. Archiv-Status."""
    video = await metadata_service.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video nicht gefunden")

    # Archiv-Verfügbarkeit prüfen
    from app.services.archive_service import archive_service
    resolved = await archive_service.resolve_video_path(video_id)
    video["storage_available"] = resolved["available"]
    video["storage_type"] = resolved.get("storage_type", video.get("storage_type", "local"))
    video["archive_name"] = resolved.get("archive_name")
    video["archive_mounted"] = resolved.get("archive_mounted", True)

    return video


@router.put("/{video_id}")
async def update_video(video_id: str, updates: VideoUpdate):
    """Video-Metadaten aktualisieren."""
    video = await metadata_service.update_video(video_id, updates.model_dump(exclude_none=True))
    if not video:
        raise HTTPException(status_code=404, detail="Video nicht gefunden")
    return video


@router.put("/{video_id}/notes")
async def save_notes(video_id: str, body: dict):
    """Notizen schnell speichern (Auto-Save)."""
    notes = body.get("notes", "")
    await db.execute(
        "UPDATE videos SET notes = ?, updated_at = ? WHERE id = ?",
        (notes, now_sqlite(), video_id))
    return {"saved": True}


@router.patch("/{video_id}/rating")
async def set_rating(video_id: str, rating: int = Query(ge=0, le=5)):
    """Schnell-Bewertung setzen (0 = Reset)."""
    await db.execute(
        "UPDATE videos SET rating = ?, updated_at = ? WHERE id = ?",
        (rating, now_sqlite(), video_id)
    )
    return {"id": video_id, "rating": rating}


@router.get("/{video_id}/likes")
async def get_video_likes(video_id: str, force: bool = False):
    """Like/Dislike-Daten via Return YouTube Dislike API abrufen."""
    from app.services.ryd_service import fetch_votes
    result = await fetch_votes(video_id, force=force)
    if result is None:
        raise HTTPException(status_code=404, detail="Keine Like-Daten verfügbar")
    return result


@router.post("/likes/batch")
async def get_likes_batch(video_ids: list[str]):
    """Batch: Like/Dislike-Daten für mehrere Videos."""
    from app.services.ryd_service import fetch_votes_batch
    results = await fetch_votes_batch(video_ids[:50])
    return {"results": results}


# ─── Archiv-Funktionen ───

@router.post("/{video_id}/archive")
async def archive_video(video_id: str):
    """Video archivieren (aus Bibliothek ausblenden)."""
    video = await db.fetch_one("SELECT id FROM videos WHERE id = ?", (video_id,))
    if not video:
        raise HTTPException(status_code=404, detail="Video nicht gefunden")
    await db.execute(
        "UPDATE videos SET is_archived = 1, updated_at = datetime('now') WHERE id = ?",
        (video_id,)
    )
    return {"video_id": video_id, "is_archived": True}


@router.post("/{video_id}/unarchive")
async def unarchive_video(video_id: str):
    """Video dearchivieren (zurück in Bibliothek)."""
    video = await db.fetch_one("SELECT id FROM videos WHERE id = ?", (video_id,))
    if not video:
        raise HTTPException(status_code=404, detail="Video nicht gefunden")
    await db.execute(
        "UPDATE videos SET is_archived = 0, updated_at = datetime('now') WHERE id = ?",
        (video_id,)
    )
    return {"video_id": video_id, "is_archived": False}


@router.post("/archive/batch")
async def archive_batch(video_ids: list[str], unarchive: bool = False):
    """Batch: Mehrere Videos (de)archivieren."""
    val = 0 if unarchive else 1
    count = 0
    for vid in video_ids[:100]:
        cursor = await db.execute(
            "UPDATE videos SET is_archived = ?, updated_at = datetime('now') WHERE id = ?",
            (val, vid)
        )
        count += cursor.rowcount
    return {"updated": count, "is_archived": not unarchive}


class TypeBatchRequest(BaseModel):
    video_ids: list[str]
    video_type: str


@router.post("/type/batch")
async def set_type_batch(req: TypeBatchRequest):
    """Batch: Video-Typ für mehrere Videos setzen."""
    if req.video_type not in ("video", "short", "live"):
        raise HTTPException(status_code=400, detail=f"Ungültiger Typ: {req.video_type}")
    count = 0
    for vid in req.video_ids[:200]:
        cursor = await db.execute(
            "UPDATE videos SET video_type = ?, updated_at = datetime('now') WHERE id = ?",
            (req.video_type, vid)
        )
        count += cursor.rowcount
        # Auch RSS-Einträge aktualisieren
        await db.execute(
            "UPDATE rss_entries SET video_type = ? WHERE video_id = ?",
            (req.video_type, vid)
        )
    return {"updated": count, "video_type": req.video_type}


@router.delete("/{video_id}")
async def delete_video(video_id: str):
    """Video komplett löschen (Dateien + DB)."""
    deleted = await metadata_service.delete_video(video_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Video nicht gefunden")
    return {"message": f"Video {video_id} gelöscht", "deleted": True}


@router.post("/{video_id}/play")
async def record_play(video_id: str, position: int = 0):
    """Wiedergabe aufzeichnen."""
    await metadata_service.record_play(video_id, position)
    return {"recorded": True}


@router.post("/{video_id}/position")
async def save_position(video_id: str, position: float = 0):
    """Wiedergabeposition speichern."""
    try:
        await metadata_service.save_position(video_id, int(position))
        return {"saved": True, "position": int(position)}
    except Exception:
        return {"saved": False, "position": int(position)}


@router.get("/{video_id}/position")
async def get_position(video_id: str):
    """Letzte Wiedergabeposition abrufen."""
    pos = await metadata_service.get_last_position(video_id)
    return {"video_id": video_id, "position": pos}


# ─── Video-Links (Beschreibungs-Verknüpfungen) ───────────

@router.get("/{video_id}/links")
async def get_video_links(video_id: str):
    """Alle Verknüpfungen eines Videos (z.B. aus Beschreibungs-Links).
    Gibt linked_video_id + Metadaten des verlinkten Videos zurück."""
    rows = await db.fetch_all(
        """SELECT vl.linked_video_id, vl.source_url, vl.created_at,
                  v.title, v.channel_name, v.thumbnail_path, v.duration, v.status
           FROM video_links vl
           LEFT JOIN videos v ON v.id = vl.linked_video_id
           WHERE vl.video_id = ?""",
        (video_id,)
    )
    return {"video_id": video_id, "links": [dict(r) for r in rows]}


@router.post("/{video_id}/links")
async def create_video_link(video_id: str, body: dict):
    """Verknüpfung erstellen: { linked_video_id, source_url? }"""
    linked_id = body.get("linked_video_id", "").strip()
    if not linked_id:
        raise HTTPException(status_code=400, detail="linked_video_id erforderlich")
    source_url = body.get("source_url", f"https://www.youtube.com/watch?v={linked_id}")
    try:
        await db.execute(
            """INSERT OR IGNORE INTO video_links (video_id, linked_video_id, source_url)
               VALUES (?, ?, ?)""",
            (video_id, linked_id, source_url)
        )
        return {"ok": True, "video_id": video_id, "linked_video_id": linked_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{video_id}/links/{linked_video_id}")
async def delete_video_link(video_id: str, linked_video_id: str):
    """Verknüpfung entfernen."""
    await db.execute(
        "DELETE FROM video_links WHERE video_id = ? AND linked_video_id = ?",
        (video_id, linked_video_id)
    )
    return {"ok": True, "deleted": True}


@router.get("/{video_id}/metadata")
async def get_video_metadata(video_id: str):
    """Erweiterte Metadaten: DB-Daten + ffprobe Analyse."""
    import subprocess, json as _json
    from pathlib import Path

    video = await db.fetch_one("SELECT * FROM videos WHERE id = ?", (video_id,))
    if not video:
        raise HTTPException(status_code=404, detail="Video nicht gefunden")

    v = dict(video)
    # Tags parsen
    if isinstance(v.get("tags"), str):
        try: v["tags"] = _json.loads(v["tags"])
        except (ValueError, TypeError): v["tags"] = []

    # Dateigröße aktuell prüfen
    fp = v.get("file_path")
    file_info = {}
    if fp and Path(fp).exists():
        st = Path(fp).stat()
        file_info = {"file_exists": True, "file_size_actual": st.st_size}
    else:
        file_info = {"file_exists": False}

    # ffprobe für technische Details
    probe = {}
    if fp and Path(fp).exists():
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", "-show_streams", str(fp)],
                capture_output=True, text=True, timeout=15)
            if r.returncode == 0:
                data = _json.loads(r.stdout)
                fmt = data.get("format", {})
                probe["container"] = fmt.get("format_long_name", fmt.get("format_name", ""))
                probe["duration_raw"] = float(fmt.get("duration", 0))
                probe["bitrate"] = int(fmt.get("bit_rate", 0))
                probe["size_bytes"] = int(fmt.get("size", 0))

                for s in data.get("streams", []):
                    if s["codec_type"] == "video" and "video" not in probe:
                        probe["video"] = {
                            "codec": s.get("codec_name"),
                            "profile": s.get("profile"),
                            "width": s.get("width"),
                            "height": s.get("height"),
                            "fps": s.get("r_frame_rate"),
                            "bitrate": int(s.get("bit_rate", 0)) if s.get("bit_rate") else None,
                            "pix_fmt": s.get("pix_fmt"),
                        }
                    elif s["codec_type"] == "audio" and "audio" not in probe:
                        probe["audio"] = {
                            "codec": s.get("codec_name"),
                            "sample_rate": s.get("sample_rate"),
                            "channels": s.get("channels"),
                            "bitrate": int(s.get("bit_rate", 0)) if s.get("bit_rate") else None,
                        }
        except Exception:
            pass

    # Verknüpfungen zählen
    link_count = await db.fetch_val(
        "SELECT COUNT(*) FROM video_links WHERE video_id = ?", (video_id,)) or 0
    chapter_count = await db.fetch_val(
        "SELECT COUNT(*) FROM chapters WHERE video_id = ?", (video_id,)) or 0

    return {
        "db": v,
        "file": file_info,
        "probe": probe,
        "link_count": link_count,
        "chapter_count": chapter_count,
    }


@router.post("/{video_id}/auto-link")
async def auto_link_description(video_id: str):
    """YouTube-IDs aus der Beschreibung extrahieren und automatisch verknüpfen
    wenn die Videos schon in der Bibliothek sind."""
    import re
    video = await db.fetch_one("SELECT description FROM videos WHERE id = ?", (video_id,))
    if not video or not video["description"]:
        return {"linked": 0, "ids_found": 0}

    # Alle YouTube-Video-IDs extrahieren
    yt_pattern = r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})'
    found_ids = set(re.findall(yt_pattern, video["description"]))
    found_ids.discard(video_id)  # Sich selbst nicht verknüpfen

    linked = 0
    for yt_id in found_ids:
        # Prüfen ob Video in Bibliothek
        exists = await db.fetch_val(
            "SELECT COUNT(*) FROM videos WHERE id = ? AND status = 'ready'", (yt_id,))
        if exists:
            await db.execute(
                """INSERT OR IGNORE INTO video_links (video_id, linked_video_id, source_url)
                   VALUES (?, ?, ?)""",
                (video_id, yt_id, f"https://www.youtube.com/watch?v={yt_id}")
            )
            linked += 1

    return {"linked": linked, "ids_found": len(found_ids)}


@router.post("/{video_id}/upgrade")
async def upgrade_video(video_id: str, quality: str = "best"):
    """Video in besserer Qualität neu herunterladen. DB-Daten bleiben erhalten."""
    from pathlib import Path
    from app.services.download_service import download_service

    video = await db.fetch_one(
        "SELECT id, file_path, status, source FROM videos WHERE id = ?", (video_id,))
    if not video:
        raise HTTPException(status_code=404, detail="Video nicht gefunden")
    if video["source"] in ("local", "imported"):
        raise HTTPException(status_code=400, detail="Importierte Videos können nicht upgraded werden")
    if video_id.startswith("local_"):
        raise HTTPException(status_code=400, detail="Lokale Videos können nicht upgraded werden")

    # Alte Datei löschen
    old_path = video["file_path"]
    if old_path:
        p = Path(old_path)
        if p.exists():
            p.unlink()
            logger.info(f"[UPGRADE] Alte Datei gelöscht: {p}")

    # Status auf 'upgrading' setzen
    await db.execute(
        "UPDATE videos SET status = 'upgrading', updated_at = ? WHERE id = ?",
        (now_sqlite(), video_id))

    # Neu in Queue mit force
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        result = await download_service.add_to_queue(
            url, quality=quality, force=True, priority=10)
        return {"status": "ok", "quality": quality, "queue_id": result.get("queue_id")}
    except Exception as e:
        # Rollback status
        await db.execute(
            "UPDATE videos SET status = 'ready', updated_at = ? WHERE id = ?",
            (now_sqlite(), video_id))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{video_id}/auto-enrich")
async def auto_enrich(video_id: str):
    """Automatische Anreicherung beim Videoaufruf.
    Prüft ob SponsorBlock, Kapitel, Untertitel, Thumbnail fehlen
    und lädt sie nach. Tracking via enrichment_log.
    """
    video = await db.fetch_one("SELECT * FROM videos WHERE id = ?", (video_id,))
    if not video:
        raise HTTPException(status_code=404, detail="Video nicht gefunden")
    video = dict(video)

    # Keine Enrichments für lokale Videos
    if video_id.startswith("local_") or len(video_id) != 11:
        return {"enriched": {}, "skipped": "Keine YouTube-ID"}

    results = {}

    async def _should_enrich(etype: str) -> bool:
        """Prüft ob Enrichment nötig: nicht wenn schon erfolgreich oder kürzlich fehlgeschlagen."""
        row = await db.fetch_one(
            "SELECT success, attempted_at FROM enrichment_log WHERE video_id = ? AND type = ?",
            (video_id, etype))
        if not row:
            return True
        if row["success"]:
            return False
        # Fehlgeschlagen → erst nach 24h erneut versuchen
        return row["attempted_at"][:10] < now_sqlite()[:10]

    async def _log_attempt(etype: str, success: bool, count: int = 0, error: str = None):
        await db.execute(
            """INSERT OR REPLACE INTO enrichment_log (video_id, type, attempted_at, success, result_count, error)
               VALUES (?, ?, datetime('now'), ?, ?, ?)""",
            (video_id, etype, 1 if success else 0, count, error))

    # ─── SponsorBlock ───
    if await _should_enrich("sponsorblock"):
        try:
            existing = await db.fetch_val(
                "SELECT COUNT(*) FROM ad_markers WHERE video_id = ? AND source = 'sponsorblock'",
                (video_id,))
            if existing == 0:
                from app.routers.ad_markers import import_sponsorblock_segments
                count = await import_sponsorblock_segments(video_id)
                await _log_attempt("sponsorblock", count > 0, count,
                                   "Keine SponsorBlock-Segmente" if count == 0 else None)
                results["sponsorblock"] = count
            else:
                await _log_attempt("sponsorblock", True, existing)
        except Exception as e:
            await _log_attempt("sponsorblock", False, error=str(e)[:200])
            results["sponsorblock_error"] = str(e)[:100]

    # ─── Kapitel ───
    if await _should_enrich("chapters"):
        try:
            existing = await db.fetch_val(
                "SELECT COUNT(*) FROM chapters WHERE video_id = ?", (video_id,))
            if existing == 0:
                from app.routers.chapters import fetch_and_save_chapters
                count = await fetch_and_save_chapters(video_id)
                await _log_attempt("chapters", True, count)  # success auch bei 0 - YT hat keine
                results["chapters"] = count
            else:
                await _log_attempt("chapters", True, existing)
        except Exception as e:
            await _log_attempt("chapters", False, error=str(e)[:200])
            results["chapters_error"] = str(e)[:100]

    # ─── Kapitel-Thumbnails (nur wenn Kapitel + Video-Datei vorhanden) ───
    if await _should_enrich("chapter_thumbs"):
        try:
            ch_count = await db.fetch_val(
                "SELECT COUNT(*) FROM chapters WHERE video_id = ?", (video_id,))
            has_file = video.get("file_path") and video.get("status") == "ready"
            if ch_count > 0 and has_file:
                from app.routers.chapters import generate_chapter_thumbs
                gen = await generate_chapter_thumbs(video_id)
                await _log_attempt("chapter_thumbs", True, gen)
                if gen > 0:
                    results["chapter_thumbs"] = gen
            else:
                await _log_attempt("chapter_thumbs", ch_count == 0, 0,
                                   "Keine Kapitel" if ch_count == 0 else "Kein Video-File")
        except Exception as e:
            await _log_attempt("chapter_thumbs", False, error=str(e)[:200])

    # ─── Untertitel ───
    if await _should_enrich("subtitles"):
        try:
            from app.config import SUBTITLES_DIR
            sdir = SUBTITLES_DIR / video_id
            existing = list(sdir.glob("*.vtt")) if sdir.exists() else []
            if len(existing) == 0:
                res = await download_service.download_subtitles(video_id, "de")
                count = res.get("count", 0)
                # Auch englische Untertitel versuchen
                if count == 0:
                    res2 = await download_service.download_subtitles(video_id, "en")
                    count += res2.get("count", 0)
                await _log_attempt("subtitles", count > 0, count,
                                   "Keine Untertitel verfügbar" if count == 0 else None)
                results["subtitles"] = count
            else:
                await _log_attempt("subtitles", True, len(existing))
        except Exception as e:
            await _log_attempt("subtitles", False, error=str(e)[:200])
            results["subtitles_error"] = str(e)[:100]

    # ─── Thumbnail ───
    if await _should_enrich("thumbnail"):
        try:
            from app.config import THUMBNAILS_DIR
            tdir = THUMBNAILS_DIR / video_id
            thumb_exists = (tdir / "thumbnail.jpg").exists() if tdir.exists() else False
            if not thumb_exists and not video.get("thumbnail_path"):
                url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                path = await download_service._dl_thumbnail(video_id, url)
                if path:
                    await db.execute(
                        "UPDATE videos SET thumbnail_path = ? WHERE id = ?",
                        (path, video_id))
                    await _log_attempt("thumbnail", True, 1)
                    results["thumbnail"] = True
                else:
                    await _log_attempt("thumbnail", False, error="Download fehlgeschlagen")
            else:
                await _log_attempt("thumbnail", True, 1)
        except Exception as e:
            await _log_attempt("thumbnail", False, error=str(e)[:200])
            results["thumbnail_error"] = str(e)[:100]

    return {"video_id": video_id, "enriched": results}

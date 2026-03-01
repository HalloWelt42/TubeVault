"""
TubeVault -  Subscriptions Router v1.5.1
RSS-Abo-Verwaltung + Kanal-Details + Avatare + Shorts/Live/Debug
© HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import json
from pathlib import Path
import logging
import httpx

logger = logging.getLogger(__name__)

from app.config import AVATARS_DIR, RSS_THUMBS_DIR
from app.database import db
from app.services.rss_service import rss_service
from app.routers.jobs import activity_ws

router = APIRouter(prefix="/api/subscriptions", tags=["Abonnements"])


# --- Models ---

class SubscriptionCreate(BaseModel):
    channel_id: str  # Kann auch Video-URL oder Kanal-URL sein
    auto_download: bool = False
    download_quality: str = "720p"


class SubscriptionBatchCreate(BaseModel):
    channel_ids: list[str]
    auto_download: bool = False


class SubscriptionUpdate(BaseModel):
    auto_download: Optional[bool] = None
    download_quality: Optional[str] = None
    audio_only: Optional[bool] = None
    check_interval: Optional[int] = None
    enabled: Optional[bool] = None
    category_id: Optional[int] = None
    drip_enabled: Optional[bool] = None
    drip_count: Optional[int] = None
    drip_auto_archive: Optional[bool] = None
    suggest_exclude: Optional[bool] = None


# --- Endpoints ---

@router.get("")
async def get_subscriptions(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=1000),
):
    """Alle Abonnements abrufen."""
    return await rss_service.get_subscriptions(page, per_page)


@router.post("")
async def add_subscription(sub: SubscriptionCreate):
    """Neues Abo hinzufügen. Akzeptiert Channel-ID, Kanal-URL oder Video-URL."""
    channel_id = sub.channel_id.strip()

    # Video-URL erkennen und zu Channel-ID auflösen
    if "youtu.be/" in channel_id or "youtube.com/watch" in channel_id or "youtube.com/shorts" in channel_id:
        try:
            from pytubefix import YouTube
            yt = YouTube(channel_id if channel_id.startswith("http") else f"https://{channel_id}")
            channel_id = yt.channel_id
            if not channel_id:
                raise ValueError("Keine Channel-ID gefunden")
            logger.info(f"Video-URL aufgelöst → Channel: {channel_id}")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Konnte Channel nicht aus Video-URL ermitteln: {e}")

    # Kanal-URL zu Channel-ID
    elif "youtube.com/channel/" in channel_id:
        channel_id = channel_id.split("youtube.com/channel/")[-1].split("/")[0].split("?")[0]
    elif "youtube.com/@" in channel_id:
        # Handle-URL → per pytubefix auflösen
        try:
            from pytubefix import Channel
            ch = Channel(channel_id if channel_id.startswith("http") else f"https://{channel_id}")
            channel_id = ch.channel_id
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Konnte Channel nicht auflösen: {e}")

    try:
        result = await rss_service.add_subscription(
            channel_id=channel_id,
            auto_download=sub.auto_download,
            quality=sub.download_quality,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/batch")
async def add_subscriptions_batch(batch: SubscriptionBatchCreate):
    """Mehrere Abos importieren (z.B. FreeTube)."""
    return await rss_service.add_subscriptions_batch(
        channel_ids=batch.channel_ids,
        auto_download=batch.auto_download,
    )


# --- Kanal-Detail ---

@router.get("/channel/{channel_id}")
async def get_channel_detail(channel_id: str):
    """Kanal-Detailinfos: Abo-Daten + Statistiken + Typ-Counts."""
    sub = await db.fetch_one(
        "SELECT * FROM subscriptions WHERE channel_id = ?", (channel_id,)
    )
    if not sub:
        # Nicht abonniert → Basisdaten aus videos/rss oder Stub
        downloaded_count = await db.fetch_val(
            "SELECT COUNT(*) FROM videos WHERE channel_id = ? AND status = 'ready'",
            (channel_id,)
        ) or 0
        first_video = await db.fetch_one(
            "SELECT channel_name FROM videos WHERE channel_id = ? LIMIT 1", (channel_id,)
        )
        return {
            "channel_id": channel_id,
            "channel_name": first_video["channel_name"] if first_video else channel_id,
            "channel_url": f"https://www.youtube.com/channel/{channel_id}",
            "subscribed": False,
            "downloaded_count": downloaded_count,
            "rss_entry_count": 0,
            "new_video_count": 0,
            "type_counts": {"video": 0, "short": 0, "live": 0},
        }

    # Statistiken
    rss_count = await db.fetch_val(
        "SELECT COUNT(*) FROM rss_entries WHERE channel_id = ?", (channel_id,)
    ) or 0
    new_count = await db.fetch_val(
        "SELECT COUNT(*) FROM rss_entries WHERE channel_id = ? AND COALESCE(feed_status, 'active') = 'active'",
        (channel_id,)
    ) or 0
    downloaded_count = await db.fetch_val(
        """SELECT COUNT(DISTINCT v.id) FROM videos v
           WHERE v.status = 'ready' AND (
               v.channel_id = ?
               OR v.id IN (SELECT video_id FROM rss_entries WHERE channel_id = ?)
           )""",
        (channel_id, channel_id)
    ) or 0
    total_downloaded_size = await db.fetch_val(
        "SELECT COALESCE(SUM(file_size), 0) FROM videos WHERE channel_id = ?",
        (channel_id,)
    ) or 0
    total_downloaded_duration = await db.fetch_val(
        "SELECT COALESCE(SUM(duration), 0) FROM videos WHERE channel_id = ?",
        (channel_id,)
    ) or 0
    total_known_duration = await db.fetch_val(
        "SELECT COALESCE(SUM(duration), 0) FROM rss_entries WHERE channel_id = ? AND duration IS NOT NULL",
        (channel_id,)
    ) or 0
    total_views = await db.fetch_val(
        "SELECT COALESCE(SUM(views), 0) FROM rss_entries WHERE channel_id = ? AND views IS NOT NULL",
        (channel_id,)
    ) or 0

    # Typ-basierte Counts aus rss_entries
    type_counts = {}
    for vtype in ("video", "short", "live"):
        if vtype == "video":
            # NULL = video für alte Einträge
            type_counts[vtype] = await db.fetch_val(
                "SELECT COUNT(*) FROM rss_entries WHERE channel_id = ? AND (video_type = 'video' OR video_type IS NULL)",
                (channel_id,)
            ) or 0
        else:
            type_counts[vtype] = await db.fetch_val(
                "SELECT COUNT(*) FROM rss_entries WHERE channel_id = ? AND video_type = ?",
                (channel_id, vtype)
            ) or 0

    # Channel Tags parsen
    import json
    channel_tags = []
    try:
        raw_tags = sub["channel_tags"] if "channel_tags" in sub.keys() else "[]"
        channel_tags = json.loads(raw_tags) if raw_tags else []
    except Exception:
        pass

    result = dict(sub)
    result["subscribed"] = True
    result["rss_entry_count"] = rss_count
    result["new_video_count"] = new_count
    result["downloaded_count"] = downloaded_count
    result["total_downloaded_size"] = total_downloaded_size
    result["total_downloaded_duration"] = total_downloaded_duration
    result["total_known_duration"] = total_known_duration
    result["total_views"] = total_views
    result["needs_scan"] = not result.get("last_scanned")
    result["type_counts"] = type_counts
    result["channel_tags_parsed"] = channel_tags
    return result


@router.get("/channel/{channel_id}/videos")
async def get_channel_videos(
    channel_id: str,
    source: str = Query("all"),
    video_type: str = Query("all"),
    sort: str = Query("newest"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    include_dismissed: bool = False,
):
    """Alle Videos eines Kanals -  mit Typ-Filter und Sortierung.

    source: all | rss | downloaded
    video_type: all | video | short | live
    sort: newest | oldest | popular | longest | shortest
    """
    try:
        return await _get_channel_videos_impl(
            channel_id, source, video_type, sort, page, per_page, include_dismissed
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Channel videos Fehler (channel={channel_id}, source={source}, type={video_type}, sort={sort}): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Interner Fehler: {str(e)[:200]}")


async def _get_channel_videos_impl(
    channel_id: str, source: str, video_type: str, sort: str,
    page: int, per_page: int, include_dismissed: bool,
):
    offset = (page - 1) * per_page
    if source not in ("all", "rss", "downloaded"):
        source = "all"
    if video_type not in ("all", "video", "short", "live"):
        video_type = "all"
    if sort not in ("newest", "oldest", "popular", "longest", "shortest"):
        sort = "newest"

    # Typ-Filter für SQL (NULL = 'video' für alte Einträge)
    type_filter = ""
    type_params = []
    if video_type != "all":
        if video_type == "video":
            type_filter = "AND (re.video_type = 'video' OR re.video_type IS NULL)"
        else:
            type_filter = "AND re.video_type = ?"
            type_params = [video_type]

    # Sort-Mapping
    sort_map = {
        "newest": "re.published DESC",
        "oldest": "re.published ASC",
        "popular": "COALESCE(v.view_count, re.views, 0) DESC",
        "longest": "COALESCE(v.duration, re.duration, 0) DESC",
        "shortest": "COALESCE(v.duration, re.duration, 0) ASC",
    }
    order_by = sort_map.get(sort, "re.published DESC")

    videos = []

    if source == "downloaded":
        # Nur heruntergeladene Videos dieses Kanals (mit Typ aus rss_entries)
        dl_type_filter = ""
        dl_type_params = []
        if video_type != "all":
            if video_type == "video":
                dl_type_filter = "AND (re2.video_type = 'video' OR re2.video_type IS NULL)"
            else:
                dl_type_filter = "AND re2.video_type = ?"
                dl_type_params = [video_type]

        # Sort für downloaded
        dl_sort_map = {
            "newest": "v.upload_date DESC",
            "oldest": "v.upload_date ASC",
            "popular": "COALESCE(v.view_count, 0) DESC",
            "longest": "COALESCE(v.duration, 0) DESC",
            "shortest": "COALESCE(v.duration, 0) ASC",
        }
        dl_order = dl_sort_map.get(sort, "v.upload_date DESC")

        rows = await db.fetch_all(
            f"""SELECT v.id as video_id, v.title, v.channel_name, v.duration,
                      v.file_size, v.thumbnail_path, v.upload_date,
                      v.upload_date as published, v.status as video_status,
                      v.storage_type, v.view_count, v.description,
                      v.suggest_override,
                      1 as is_downloaded, 0 as is_in_queue,
                      'downloaded' as source,
                      COALESCE(re2.video_type, 'video') as video_type
               FROM videos v
               LEFT JOIN rss_entries re2 ON v.id = re2.video_id AND re2.channel_id = ?
               WHERE v.status = 'ready' AND (
                   v.channel_id = ?
                   OR v.id IN (SELECT video_id FROM rss_entries WHERE channel_id = ?)
               ) {dl_type_filter}
               ORDER BY {dl_order}
               LIMIT ? OFFSET ?""",
            (channel_id, channel_id, channel_id, *dl_type_params, per_page, offset)
        )
        total = await db.fetch_val(
            f"""SELECT COUNT(DISTINCT v.id) FROM videos v
               LEFT JOIN rss_entries re2 ON v.id = re2.video_id AND re2.channel_id = ?
               WHERE v.status = 'ready' AND (
                   v.channel_id = ?
                   OR v.id IN (SELECT video_id FROM rss_entries WHERE channel_id = ?)
               ) {dl_type_filter}""",
            (channel_id, channel_id, channel_id, *dl_type_params)
        ) or 0
        videos = [dict(r) for r in rows]

    elif source == "rss":
        # Nur RSS-Einträge (mit Download-Status angereichert)
        dismiss_filter = "" if include_dismissed else "AND COALESCE(re.feed_status, 'active') IN ('active', 'later')"
        rows = await db.fetch_all(
            f"""SELECT re.video_id, re.title, re.published, re.thumbnail_url,
                       re.status as rss_status, re.description as rss_description,
                       COALESCE(re.video_type, 'video') as video_type,
                       CASE WHEN v.id IS NOT NULL AND v.status = 'ready' THEN 1 ELSE 0 END as is_downloaded,
                       CASE WHEN (SELECT j.id FROM jobs j WHERE j.type='download' AND json_extract(j.metadata, '$.video_id') = re.video_id AND j.status IN ('queued','active') LIMIT 1) IS NOT NULL THEN 1 ELSE 0 END as is_in_queue,
                       COALESCE(v.duration, re.duration) as duration,
                       v.file_size,
                       COALESCE(v.view_count, re.views) as view_count,
                       COALESCE(v.description, re.description) as description,
                       v.thumbnail_path,
                       v.suggest_override,
                       COALESCE((SELECT j.status FROM jobs j WHERE j.type='download' AND json_extract(j.metadata, '$.video_id') = re.video_id AND j.status IN ('queued','active') LIMIT 1), '') as queue_status,
                       'rss' as source
                FROM rss_entries re
                LEFT JOIN videos v ON re.video_id = v.id
                WHERE re.channel_id = ? {dismiss_filter} {type_filter}
                ORDER BY {order_by}
                LIMIT ? OFFSET ?""",
            (channel_id, *type_params, per_page, offset)
        )
        total = await db.fetch_val(
            f"SELECT COUNT(*) FROM rss_entries re WHERE re.channel_id = ? {dismiss_filter} {type_filter}",
            (channel_id, *type_params)
        ) or 0
        videos = [dict(r) for r in rows]

    else:  # all
        # Alles zusammen: RSS-Einträge als Basis + nur-heruntergeladene (ohne RSS-Eintrag)
        dismiss_filter = "" if include_dismissed else "AND COALESCE(re.feed_status, 'active') IN ('active', 'later')"

        # 1) RSS-Einträge mit Download-Status (JOIN auf videos)
        rss_rows = await db.fetch_all(
            f"""SELECT re.video_id, re.title as rss_title, re.published, re.thumbnail_url,
                       re.status as rss_status, re.description as rss_description,
                       COALESCE(re.video_type, 'video') as video_type,
                       v.id as vid, v.title as dl_title,
                       COALESCE(v.duration, re.duration) as duration,
                       v.file_size,
                       COALESCE(v.view_count, re.views) as view_count,
                       COALESCE(v.description, re.description) as description,
                       v.thumbnail_path,
                       v.upload_date, v.status as video_status,
                       v.suggest_override,
                       CASE WHEN v.id IS NOT NULL AND v.status = 'ready' THEN 1 ELSE 0 END as is_downloaded,
                       CASE WHEN (SELECT j.id FROM jobs j WHERE j.type='download' AND json_extract(j.metadata, '$.video_id') = re.video_id AND j.status IN ('queued','active') LIMIT 1) IS NOT NULL THEN 1 ELSE 0 END as is_in_queue,
                       COALESCE((SELECT j.status FROM jobs j WHERE j.type='download' AND json_extract(j.metadata, '$.video_id') = re.video_id AND j.status IN ('queued','active') LIMIT 1), '') as queue_status
                FROM rss_entries re
                LEFT JOIN videos v ON re.video_id = v.id
                WHERE re.channel_id = ? {dismiss_filter} {type_filter}
                ORDER BY re.published DESC""",
            (channel_id, *type_params)
        )

        seen_ids = set()
        for r in rss_rows:
            d = dict(r)
            d["video_id"] = d["video_id"]
            # Bevorzuge lokale Daten wenn heruntergeladen
            if d["is_downloaded"]:
                d["title"] = d["dl_title"] or d["rss_title"]
            else:
                d["title"] = d["rss_title"] or d.get("dl_title")
            d["source"] = "rss"
            seen_ids.add(d["video_id"])
            videos.append(d)

        # 2) Nur heruntergeladene Videos OHNE RSS-Eintrag (nur wenn kein Typ-Filter)
        if video_type == "all":
            if seen_ids:
                placeholders = ",".join(["?"] * len(seen_ids))
                extra_rows = await db.fetch_all(
                    f"""SELECT id as video_id, title, channel_name, duration, file_size,
                               thumbnail_path, upload_date, upload_date as published,
                               status as video_status, view_count, description,
                               1 as is_downloaded, 0 as is_in_queue,
                               'downloaded' as source, 'video' as video_type
                        FROM videos
                        WHERE status = 'ready'
                          AND (channel_id = ? OR id IN (SELECT video_id FROM rss_entries WHERE channel_id = ?))
                          AND id NOT IN ({placeholders})
                        ORDER BY upload_date DESC""",
                    (channel_id, channel_id, *seen_ids)
                )
            else:
                extra_rows = await db.fetch_all(
                    """SELECT id as video_id, title, channel_name, duration, file_size,
                              thumbnail_path, upload_date, upload_date as published,
                              status as video_status, view_count, description,
                              1 as is_downloaded, 0 as is_in_queue,
                              'downloaded' as source, 'video' as video_type
                       FROM videos
                       WHERE status = 'ready'
                         AND (channel_id = ? OR id IN (SELECT video_id FROM rss_entries WHERE channel_id = ?))
                       ORDER BY upload_date DESC""",
                    (channel_id, channel_id)
                )
            for r in extra_rows:
                videos.append(dict(r))

        # Sortierung
        def sort_key(v):
            if sort == "popular":
                return v.get("view_count") or 0
            elif sort == "longest":
                return v.get("duration") or 0
            elif sort == "shortest":
                return -(v.get("duration") or 999999)
            elif sort == "oldest":
                return v.get("published") or v.get("upload_date") or ""
            else:  # newest
                return v.get("published") or v.get("upload_date") or ""

        reverse = sort not in ("oldest", "shortest")
        videos.sort(key=sort_key, reverse=reverse)

        total = len(videos)
        videos = videos[offset:offset + per_page]

    # Source-Counts für Badge-Anzeige (alle drei Quellen für aktuellen video_type)
    vt_filter_rss = ""
    vt_filter_dl = ""
    vt_params_rss = [channel_id]
    vt_params_dl = [channel_id, channel_id]
    if video_type == "video":
        vt_filter_rss = "AND (re.video_type = 'video' OR re.video_type IS NULL)"
        vt_filter_dl = "AND (COALESCE(re2.video_type, 'video') = 'video')"
    elif video_type in ("short", "live"):
        vt_filter_rss = "AND re.video_type = ?"
        vt_params_rss.append(video_type)
        vt_filter_dl = "AND re2.video_type = ?"
        vt_params_dl.append(video_type)

    rss_count = await db.fetch_val(
        f"""SELECT COUNT(*) FROM rss_entries re
            WHERE re.channel_id = ? AND COALESCE(re.feed_status, 'active') IN ('active','later')
            {vt_filter_rss}""",
        tuple(vt_params_rss)) or 0
    dl_count = await db.fetch_val(
        f"""SELECT COUNT(DISTINCT v.id) FROM videos v
            LEFT JOIN rss_entries re2 ON v.id = re2.video_id AND re2.channel_id = ?
            WHERE v.status = 'ready' AND (v.channel_id = ? OR re2.video_id IS NOT NULL)
            {vt_filter_dl}""",
        tuple(vt_params_dl)) or 0

    source_counts = {"all": rss_count, "rss": rss_count, "downloaded": dl_count}

    return {"videos": videos, "total": total, "page": page, "channel_id": channel_id,
            "source_counts": source_counts}


@router.post("/channel/{channel_id}/fetch-all")
async def fetch_channel_videos(channel_id: str, background_tasks: BackgroundTasks):
    """Alle Videos eines Kanals per pytubefix laden.
    Startet als Background-Job, gibt sofort job_id zurück.
    """
    sub = await db.fetch_one(
        "SELECT * FROM subscriptions WHERE channel_id = ?", (channel_id,)
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Kanal nicht abonniert")

    # Job vorab erstellen damit wir die ID zurückgeben können
    from app.services.job_service import job_service as _js
    channel_name = sub["channel_name"] or channel_id
    job = await _js.create(
        job_type="channel_scan",
        title=f"Kanal-Scan: {channel_name}",
        description=f"Lade alle Videos/Shorts/Live von {channel_name}",
        metadata={"channel_id": channel_id, "trigger": "manual"},
    )
    job_id = job["id"]

    async def _run_scan():
        try:
            result = await rss_service.fetch_all_channel_videos(channel_id, job_id=job_id)
            logger.info(f"Kanal-Scan {channel_id}: {result}")
        except Exception as e:
            logger.error(f"Kanal-Scan {channel_id} fehlgeschlagen: {e}")

    background_tasks.add_task(_run_scan)
    return {"status": "started", "channel_id": channel_id, "job_id": job_id}


@router.get("/channel/{channel_id}/missing-videos")
async def get_missing_videos(
    channel_id: str,
    limit: int = Query(50, ge=1, le=200),
    video_type: str = Query("all"),
):
    """Nicht heruntergeladene, nicht in Queue befindliche Video-IDs eines Kanals.
    Sortiert nach published DESC (neueste zuerst)."""
    type_filter = ""
    type_params = []
    if video_type == "video":
        type_filter = "AND (re.video_type = 'video' OR re.video_type IS NULL)"
    elif video_type in ("short", "live"):
        type_filter = "AND re.video_type = ?"
        type_params = [video_type]

    rows = await db.fetch_all(
        f"""SELECT re.video_id
           FROM rss_entries re
           LEFT JOIN videos v ON re.video_id = v.id AND v.status = 'ready'
           WHERE re.channel_id = ?
             AND v.id IS NULL
             AND COALESCE(re.feed_status, 'active') IN ('active', 'later')
             {type_filter}
             AND re.video_id NOT IN (
                 SELECT json_extract(j.metadata, '$.video_id')
                 FROM jobs j
                 WHERE j.type = 'download' AND j.status IN ('queued', 'active')
                 AND json_extract(j.metadata, '$.video_id') IS NOT NULL
             )
           ORDER BY re.published DESC
           LIMIT ?""",
        (channel_id, *type_params, limit))
    total_missing = await db.fetch_val(
        f"""SELECT COUNT(*) FROM rss_entries re
           LEFT JOIN videos v ON re.video_id = v.id AND v.status = 'ready'
           WHERE re.channel_id = ? AND v.id IS NULL
             AND COALESCE(re.feed_status, 'active') IN ('active', 'later')
             {type_filter}""",
        (channel_id, *type_params)) or 0
    return {
        "video_ids": [r["video_id"] for r in rows],
        "count": len(rows),
        "total_missing": total_missing,
    }


@router.get("/channel/{channel_id}/debug")
async def get_channel_debug(channel_id: str):
    """Debug-Infos für Kanal-Diagnose -  zeigt DB-Zustand und Scan-Details."""
    import json

    sub = await db.fetch_one(
        "SELECT * FROM subscriptions WHERE channel_id = ?", (channel_id,)
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Kanal nicht abonniert")

    # Typ-Verteilung
    type_dist = {}
    for vtype in ("video", "short", "live"):
        type_dist[vtype] = await db.fetch_val(
            "SELECT COUNT(*) FROM rss_entries WHERE channel_id = ? AND video_type = ?",
            (channel_id, vtype)
        ) or 0
    type_dist["unknown"] = await db.fetch_val(
        "SELECT COUNT(*) FROM rss_entries WHERE channel_id = ? AND (video_type IS NULL OR video_type = '')",
        (channel_id,)
    ) or 0

    # Duration-Statistiken
    duration_stats = {}
    for vtype in ("video", "short", "live"):
        row = await db.fetch_one(
            """SELECT
                COUNT(*) as count,
                COALESCE(MIN(duration), 0) as min_dur,
                COALESCE(MAX(duration), 0) as max_dur,
                COALESCE(AVG(duration), 0) as avg_dur,
                COALESCE(SUM(duration), 0) as total_dur
               FROM rss_entries WHERE channel_id = ? AND video_type = ? AND duration IS NOT NULL""",
            (channel_id, vtype)
        )
        if row:
            duration_stats[vtype] = {
                "count": row["count"],
                "min": row["min_dur"],
                "max": row["max_dur"],
                "avg": round(row["avg_dur"], 1),
                "total": row["total_dur"],
            }

    # Letzte Jobs für diesen Kanal
    jobs = await db.fetch_all(
        """SELECT id, type, status, progress, result, error_message, created_at, completed_at
           FROM jobs WHERE type = 'channel_scan' AND metadata LIKE ?
           ORDER BY created_at DESC LIMIT 5""",
        (f'%{channel_id}%',)
    )

    # Fehlende Daten
    missing = {
        "no_duration": await db.fetch_val(
            "SELECT COUNT(*) FROM rss_entries WHERE channel_id = ? AND duration IS NULL",
            (channel_id,)
        ) or 0,
        "no_views": await db.fetch_val(
            "SELECT COUNT(*) FROM rss_entries WHERE channel_id = ? AND views IS NULL",
            (channel_id,)
        ) or 0,
        "no_thumbnail": await db.fetch_val(
            "SELECT COUNT(*) FROM rss_entries WHERE channel_id = ? AND thumbnail_url IS NULL",
            (channel_id,)
        ) or 0,
        "no_description": await db.fetch_val(
            "SELECT COUNT(*) FROM rss_entries WHERE channel_id = ? AND (description IS NULL OR description = '')",
            (channel_id,)
        ) or 0,
        "no_title": await db.fetch_val(
            "SELECT COUNT(*) FROM rss_entries WHERE channel_id = ? AND (title IS NULL OR title = '')",
            (channel_id,)
        ) or 0,
    }

    # Keywords Statistik
    kw_count = await db.fetch_val(
        "SELECT COUNT(*) FROM rss_entries WHERE channel_id = ? AND keywords != '[]' AND keywords IS NOT NULL",
        (channel_id,)
    ) or 0

    # Subscription-Rohdaten
    sub_dict = dict(sub)
    # Tags parsen
    try:
        sub_dict["channel_tags_parsed"] = json.loads(sub_dict.get("channel_tags") or "[]")
    except Exception:
        sub_dict["channel_tags_parsed"] = []

    return {
        "subscription": sub_dict,
        "type_distribution": type_dist,
        "duration_stats": duration_stats,
        "missing_data": missing,
        "keywords_count": kw_count,
        "recent_jobs": [dict(j) for j in jobs],
        "total_entries": sum(type_dist.values()),
    }


@router.get("/channel/{channel_id}/filesystem")
async def get_channel_filesystem(channel_id: str):
    """Filesystem-Audit: Zeigt alle Datenpfade und deren Existenz für einen Kanal."""
    import os
    from app.config import (
        DATA_DIR, AVATARS_DIR, BANNERS_DIR, THUMBNAILS_DIR,
        SUBTITLES_DIR, TEXTS_DIR, VIDEOS_DIR, AUDIO_DIR, RSS_THUMBS_DIR,
    )

    HOST_DATA = os.getenv("TUBEVAULT_HOST_DATA", "./data")

    def check(path: Path) -> dict:
        """Prüft ob Datei/Ordner existiert und gibt Info zurück."""
        try:
            exists = path.exists()
        except (OSError, ValueError):
            exists = False
        docker_path = str(path)
        host_path = docker_path.replace(str(DATA_DIR), HOST_DATA)
        result = {"docker": docker_path, "host": host_path, "exists": exists}
        try:
            if exists and path.is_file():
                result["size"] = path.stat().st_size
            elif exists and path.is_dir():
                files = list(path.iterdir())
                result["file_count"] = len(files)
        except (OSError, PermissionError):
            pass
        return result

    sub = await db.fetch_one(
        "SELECT * FROM subscriptions WHERE channel_id = ?", (channel_id,))
    if not sub:
        raise HTTPException(status_code=404, detail="Kanal nicht abonniert")
    sub = dict(sub)

    # ─── Kanal-Dateien ───
    channel_files = {
        "avatar": check(AVATARS_DIR / f"{channel_id}.jpg"),
        "banner": check(BANNERS_DIR / f"{channel_id}.jpg"),
    }

    # ─── DB-Only Kanal-Daten (noch nicht als Datei) ───
    channel_db_fields = {
        "channel_name": sub["channel_name"],
        "channel_description": bool(sub.get("channel_description")),
        "subscriber_count": sub.get("subscriber_count"),
        "channel_tags": bool(sub.get("channel_tags") and sub["channel_tags"] != "[]"),
        "auto_download": bool(sub.get("auto_download")),
        "check_interval": sub.get("check_interval"),
    }

    rss_count = await db.fetch_val(
        "SELECT COUNT(*) FROM rss_entries WHERE channel_id = ?", (channel_id,)) or 0
    pl_count = await db.fetch_val(
        "SELECT COUNT(*) FROM channel_playlists WHERE channel_id = ?", (channel_id,)) or 0

    channel_db_only = {
        "rss_entries": {"count": rss_count, "has_file": False},
        "channel_playlists": {"count": pl_count, "has_file": False},
        "subscription_settings": {"has_file": False, "fields": channel_db_fields},
    }

    # ─── Geplante Dateistruktur (Zukunft) ───
    planned_channel_dir = DATA_DIR / "channels" / channel_id
    planned_files = {
        "channel_json": check(planned_channel_dir / "channel.json"),
        "catalog_jsonl": check(planned_channel_dir / "catalog.jsonl"),
        "playlists_dir": check(planned_channel_dir / "playlists"),
    }

    # ─── Video-Dateien dieses Kanals ───
    dl_videos = await db.fetch_all(
        """SELECT v.id, v.title, v.file_path, v.thumbnail_path, v.video_type,
                  v.description IS NOT NULL as has_description,
                  v.tags IS NOT NULL AND v.tags != '[]' as has_tags,
                  v.duration, v.view_count, v.notes IS NOT NULL as has_notes,
                  v.rating, v.play_count
           FROM videos v
           WHERE v.status = 'ready' AND (
               v.channel_id = ?
               OR v.id IN (SELECT video_id FROM rss_entries WHERE channel_id = ?)
           )
           ORDER BY v.upload_date DESC""",
        (channel_id, channel_id))

    video_audit = []
    totals = {"video": 0, "thumb": 0, "subs": 0, "lyrics": 0, "chapters": 0,
              "meta_json": 0, "total_videos": len(dl_videos)}

    for v in dl_videos[:100]:  # Max 100 für Performance
        vid = v["id"]
        entry = {"id": vid, "title": v["title"], "type": v.get("video_type", "video"), "files": {}}

        try:
            # Video-Datei
            fp = v["file_path"]
            if fp and fp.strip():
                vpath = Path(fp)
            else:
                vpath = VIDEOS_DIR / f"{vid}.mp4"
            entry["files"]["video"] = check(vpath)
            if entry["files"]["video"]["exists"]:
                totals["video"] += 1

            # Thumbnail
            entry["files"]["thumbnail"] = check(THUMBNAILS_DIR / f"{vid}.jpg")
            if entry["files"]["thumbnail"]["exists"]:
                totals["thumb"] += 1

            # RSS-Thumbnail
            entry["files"]["rss_thumb"] = check(RSS_THUMBS_DIR / f"{vid}.jpg")

            # Untertitel
            sub_dir = SUBTITLES_DIR / vid
            entry["files"]["subtitles"] = check(sub_dir)
            if entry["files"]["subtitles"]["exists"] and entry["files"]["subtitles"].get("file_count", 0) > 0:
                totals["subs"] += 1

            # Lyrics
            lyrics_dir = TEXTS_DIR / vid
            entry["files"]["lyrics"] = check(lyrics_dir)
            if entry["files"]["lyrics"]["exists"] and entry["files"]["lyrics"].get("file_count", 0) > 0:
                totals["lyrics"] += 1

            # Chapters
            ch_dir = DATA_DIR / "chapter_thumbs" / vid
            ch_count = await db.fetch_val(
                "SELECT COUNT(*) FROM chapters WHERE video_id = ?", (vid,)) or 0
            entry["files"]["chapter_thumbs"] = check(ch_dir)
            entry["db_chapters"] = ch_count
            if ch_count > 0:
                totals["chapters"] += 1

            # Geplant: meta.json
            entry["files"]["meta_json"] = check(DATA_DIR / "videos" / vid / "meta.json")
            if entry["files"]["meta_json"]["exists"]:
                totals["meta_json"] += 1

            # DB-Only Felder (noch nicht als Datei)
            entry["db_only"] = {
                "description": bool(v["has_description"]),
                "tags": bool(v["has_tags"]),
                "notes": bool(v["has_notes"]),
                "rating": v["rating"] or 0,
                "play_count": v["play_count"] or 0,
                "duration": v["duration"],
                "view_count": v["view_count"],
            }
        except Exception as e:
            entry["error"] = str(e)[:200]

        video_audit.append(entry)

    return {
        "channel_id": channel_id,
        "channel_name": sub["channel_name"],
        "paths": {
            "data_dir": {"docker": str(DATA_DIR), "host": HOST_DATA},
            "videos_dir": check(VIDEOS_DIR),
            "thumbnails_dir": check(THUMBNAILS_DIR),
            "subtitles_dir": check(SUBTITLES_DIR),
            "texts_dir": check(TEXTS_DIR),
            "rss_thumbs_dir": check(RSS_THUMBS_DIR),
            "avatars_dir": check(AVATARS_DIR),
            "banners_dir": check(BANNERS_DIR),
        },
        "channel_files": channel_files,
        "channel_db_only": channel_db_only,
        "planned_structure": planned_files,
        "video_totals": totals,
        "videos": video_audit,
    }



# /channel/{channel_id}/banner entfernt v1.8.91 — war Dead Code
# Frontend nutzt /banner/{channel_id} (Zeile ~1126)


# --- (Reclassify entfernt v1.6.21 — ersetzt durch Thumbnail-AI) ---


# --- Abo CRUD ---


@router.get("/drip-prognosis")
async def get_drip_prognosis():
    """Speicher-Prognose für aktive Drip-Feeds.
    HINWEIS: missing_count ist nur eine Schätzung —
    nur Kanäle mit Kanal-Scan (rss_entries) werden gezählt.
    """
    from app.config import VIDEOS_DIR
    from app.utils.file_utils import get_disk_usage

    avg_row = await db.fetch_one(
        "SELECT AVG(file_size) as avg_size, COUNT(*) as count FROM videos WHERE status = 'ready' AND file_size > 0")
    avg_size = int(avg_row["avg_size"]) if avg_row and avg_row["avg_size"] else 0
    video_count = avg_row["count"] if avg_row else 0

    # Aktive Drip-Kanäle
    drip_channels = await db.fetch_all(
        """SELECT s.id, s.channel_name, s.drip_count,
                  (SELECT COUNT(*) FROM rss_entries r
                   WHERE r.channel_id = s.channel_id
                   AND r.video_id NOT IN (SELECT id FROM videos WHERE status='ready')
                  ) as missing
           FROM subscriptions s WHERE s.drip_enabled = 1""")

    total_missing = sum(c["missing"] for c in drip_channels)
    total_drip_per_day = sum(c["drip_count"] or 3 for c in drip_channels)
    estimated_bytes = total_missing * avg_size if avg_size else 0
    days_remaining = round(total_missing / total_drip_per_day) if total_drip_per_day > 0 else 0

    # Wie viele Kanäle haben überhaupt einen Scan (rss_entries)?
    scanned_channels = await db.fetch_val(
        "SELECT COUNT(DISTINCT channel_id) FROM rss_entries") or 0
    total_channels = await db.fetch_val(
        "SELECT COUNT(*) FROM subscriptions") or 0
    unscanned = total_channels - scanned_channels

    # Disk-Messung auf VIDEOS_DIR (26TB Medien-Platte, nicht Container-Root!)
    disk = get_disk_usage(str(VIDEOS_DIR))

    return {
        "drip_channels": len(drip_channels),
        "total_missing": total_missing,
        "total_drip_per_day": total_drip_per_day,
        "avg_video_size": avg_size,
        "video_sample_count": video_count,
        "estimated_bytes": estimated_bytes,
        "days_remaining": days_remaining,
        "disk_total": disk["total"],
        "disk_free": disk["free"],
        "disk_used": disk["used"],
        "disk_total_human": disk["total_human"],
        "disk_free_human": disk["free_human"],
        "scanned_channels": scanned_channels,
        "total_channels": total_channels,
        "unscanned_channels": unscanned,
        "channels": [{"name": c["channel_name"], "missing": c["missing"]} for c in drip_channels],
    }


@router.put("/{sub_id}")
async def update_subscription(sub_id: int, updates: SubscriptionUpdate):
    """Abo bearbeiten."""
    await rss_service.update_subscription(sub_id, updates.model_dump(exclude_none=True))
    return {"updated": True}


@router.delete("/{sub_id}")
async def remove_subscription(sub_id: int):
    """Abo entfernen."""
    await rss_service.remove_subscription(sub_id)
    return {"deleted": True}


@router.get("/{sub_id}/drip-status")
async def get_drip_status(sub_id: int):
    """Drip-Feed Status eines Kanals."""
    sub = await db.fetch_one(
        """SELECT channel_id, drip_enabled, drip_count, drip_auto_archive,
                  drip_next_run, drip_completed_at
           FROM subscriptions WHERE id = ?""", (sub_id,))
    if not sub:
        raise HTTPException(status_code=404, detail="Kanal nicht gefunden")
    missing = await db.fetch_val(
        """SELECT COUNT(*) FROM rss_entries r
           WHERE r.channel_id = ?
             AND r.video_id NOT IN (SELECT id FROM videos WHERE status = 'ready')""",
        (sub["channel_id"],))
    return {**dict(sub), "missing_count": missing or 0}


@router.post("/{sub_id}/reset-suggest-overrides")
async def reset_suggest_overrides(sub_id: int):
    """Alle Video-Suggest-Overrides für diesen Kanal zurücksetzen."""
    sub = await db.fetch_one(
        "SELECT channel_id FROM subscriptions WHERE id = ?", (sub_id,))
    if not sub:
        raise HTTPException(status_code=404, detail="Kanal nicht gefunden")
    result = await db.execute(
        "UPDATE videos SET suggest_override = NULL WHERE channel_id = ?",
        (sub["channel_id"],))
    return {"reset": True, "channel_id": sub["channel_id"]}




# --- Aktionen ---

@router.post("/reset-errors")
async def reset_all_errors():
    """Alle Fehler-Abos zurücksetzen: error_count=0, enabled=1, normales Intervall."""
    default_interval = 3600
    result = await db.execute(
        """UPDATE subscriptions SET error_count = 0, last_error = NULL,
           enabled = 1, check_interval = ?
           WHERE error_count > 0 OR enabled = 0""",
        (default_interval,))
    count = result.rowcount if hasattr(result, 'rowcount') else 0
    # Fallback: manuell zählen
    if count == 0:
        count = await db.fetch_val(
            "SELECT changes()") or 0
    return {"reset": count, "message": f"{count} Abos zurückgesetzt"}


@router.post("/channel/{channel_id}/reset-error")
async def reset_channel_error(channel_id: str):
    """Einzelnen Kanal entsperren und Fehler zurücksetzen."""
    sub = await db.fetch_one(
        "SELECT id, channel_name, error_count, enabled FROM subscriptions WHERE channel_id = ?",
        (channel_id,))
    if not sub:
        raise HTTPException(status_code=404, detail="Kanal nicht gefunden")
    await db.execute(
        """UPDATE subscriptions SET error_count = 0, last_error = NULL,
           enabled = 1, check_interval = 3600 WHERE channel_id = ?""",
        (channel_id,))
    return {"status": "ok", "channel": sub["channel_name"],
            "was_disabled": not sub["enabled"], "was_errors": sub["error_count"]}


@router.post("/tick")
async def tick(max_feeds: int = 20):
    """Cron-Tick: Fällige RSS-Feeds prüfen.
    
    Wird alle 5 Minuten vom System-Cron angestoßen.
    Backend entscheidet intern anhand check_interval pro Feed.
    Sichtbar als Job im Activity Panel.
    """
    result = await rss_service.tick(max_feeds=max_feeds)

    # Frontend benachrichtigen wenn neue Videos gefunden
    if result.get("new_videos", 0) > 0:
        await activity_ws.broadcast({
            "type": "feed_updated",
            "new_videos": result["new_videos"],
            "checked": result.get("checked", 0),
        })

    return result


@router.post("/cron-poll")
async def cron_poll_legacy(max_feeds: int = 20):
    """Backward-kompatibel: Leitet an /tick weiter."""
    return await tick(max_feeds=max_feeds)


@router.post("/poll-now")
async def trigger_poll():
    """Manueller RSS-Check (alle Feeds, unabhängig vom Intervall)."""
    result = await rss_service.trigger_poll_now()

    if result.get("new_videos", 0) > 0:
        await activity_ws.broadcast({
            "type": "feed_updated",
            "new_videos": result["new_videos"],
        })

    return result


@router.post("/interval/reset-all")
async def reset_all_intervals():
    """Alle Kanal-Intervalle auf Basis-Wert zurücksetzen."""
    default_interval = int(
        (await db.fetch_val("SELECT value FROM settings WHERE key = 'rss.interval'"))
        or 1800
    )
    await db.execute(
        "UPDATE subscriptions SET check_interval = ? WHERE enabled = 1",
        (default_interval,)
    )
    count = await db.fetch_val("SELECT COUNT(*) FROM subscriptions WHERE enabled = 1")
    return {"reset": count, "interval": default_interval}


@router.post("/{sub_id}/interval/halve")
async def halve_interval(sub_id: int):
    """Prüfintervall eines Kanals halbieren."""
    default_interval = int(
        (await db.fetch_val("SELECT value FROM settings WHERE key = 'rss.interval'"))
        or 1800
    )
    sub = await db.fetch_one("SELECT check_interval FROM subscriptions WHERE id = ?", (sub_id,))
    if not sub:
        raise HTTPException(status_code=404, detail="Kanal nicht gefunden")
    current = sub["check_interval"] or default_interval
    new_interval = max(default_interval, current // 2)
    await db.execute("UPDATE subscriptions SET check_interval = ? WHERE id = ?", (new_interval, sub_id))
    return {"id": sub_id, "old_interval": current, "new_interval": new_interval}


@router.post("/{sub_id}/interval/reset")
async def reset_interval(sub_id: int):
    """Prüfintervall eines Kanals auf Basis-Wert zurücksetzen."""
    default_interval = int(
        (await db.fetch_val("SELECT value FROM settings WHERE key = 'rss.interval'"))
        or 1800
    )
    sub = await db.fetch_one("SELECT check_interval FROM subscriptions WHERE id = ?", (sub_id,))
    if not sub:
        raise HTTPException(status_code=404, detail="Kanal nicht gefunden")
    await db.execute("UPDATE subscriptions SET check_interval = ? WHERE id = ?", (default_interval, sub_id))
    return {"id": sub_id, "old_interval": sub["check_interval"], "new_interval": default_interval}


@router.post("/cleanup")
async def cleanup_subscriptions():
    """Ungültige Subscriptions finden und deaktivieren."""
    all_subs = await db.fetch_all("SELECT id, channel_id, channel_name FROM subscriptions")
    invalid = []
    for sub in all_subs:
        cid = sub["channel_id"]
        if not cid or not cid.startswith("UC") or len(cid) != 24:
            await db.execute(
                "UPDATE subscriptions SET enabled = 0, last_error = ? WHERE id = ?",
                (f"Ungültige channel_id: {cid[:100]}", sub["id"])
            )
            invalid.append({"id": sub["id"], "channel_id": cid[:80], "channel_name": sub["channel_name"]})
    return {"cleaned": len(invalid), "invalid_subscriptions": invalid}


@router.get("/stats")
async def get_rss_stats():
    """RSS-Statistiken."""
    return await rss_service.get_stats()


@router.get("/scheduler")
async def get_scheduler_status():
    """RSS-Scheduler Status: nächster Check, Pending, Verlauf."""
    return await rss_service.get_scheduler_status()


@router.get("/avatar/{channel_id}")
async def get_channel_avatar(channel_id: str):
    """Kanal-Avatar ausliefern."""
    avatar_file = AVATARS_DIR / f"{channel_id}.jpg"
    if avatar_file.exists():
        return FileResponse(str(avatar_file), media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Avatar nicht gefunden")


@router.get("/rss-thumb/{video_id}")
async def get_rss_thumbnail(video_id: str):
    """Lokal gecachtes RSS-Thumbnail ausliefern. Fallback: von YouTube proxyen + cachen."""
    from app.utils.thumbnail_utils import download_yt_thumbnail, YT_THUMB_QUALITIES_FAST

    RSS_THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    cached = RSS_THUMBS_DIR / f"{video_id}.jpg"

    # 1. Lokal vorhanden
    if cached.exists() and cached.stat().st_size > 500:
        return FileResponse(str(cached), media_type="image/jpeg",
                            headers={"Cache-Control": "public, max-age=604800"})

    # 2. Von YouTube holen, cachen, ausliefern
    result = await download_yt_thumbnail(
        video_id, RSS_THUMBS_DIR, qualities=YT_THUMB_QUALITIES_FAST, min_size=500)
    if result and result.exists():
        return FileResponse(str(result), media_type="image/jpeg",
                            headers={"Cache-Control": "public, max-age=604800"})

    raise HTTPException(status_code=404, detail="Thumbnail nicht verfügbar")


@router.get("/banner/{channel_id}")
async def get_channel_banner(channel_id: str):
    """Lokal gecachtes Kanalbanner ausliefern. Fallback: von URL proxyen + cachen."""
    from app.config import BANNERS_DIR
    BANNERS_DIR.mkdir(parents=True, exist_ok=True)
    cached = BANNERS_DIR / f"{channel_id}.jpg"

    # 1. Lokal vorhanden
    if cached.exists() and cached.stat().st_size > 1000:
        return FileResponse(str(cached), media_type="image/jpeg",
                            headers={"Cache-Control": "public, max-age=604800"})

    # 2. URL aus DB holen und cachen
    sub = await db.fetch_one(
        "SELECT banner_url FROM subscriptions WHERE channel_id = ?", (channel_id,))
    if sub and sub["banner_url"] and not sub["banner_url"].startswith("/api/"):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(sub["banner_url"])
                if resp.status_code == 200 and len(resp.content) > 1000:
                    cached.write_bytes(resp.content)
                    # URL auf lokal umstellen
                    await db.execute(
                        "UPDATE subscriptions SET banner_url = ? WHERE channel_id = ?",
                        (f"/api/subscriptions/banner/{channel_id}", channel_id))
                    return FileResponse(str(cached), media_type="image/jpeg",
                                        headers={"Cache-Control": "public, max-age=604800"})
        except Exception:
            pass

    raise HTTPException(status_code=404, detail="Banner nicht verfügbar")


@router.post("/cache-rss-thumbnails")
async def cache_all_rss_thumbnails(background_tasks: BackgroundTasks):
    """Alle fehlenden RSS-Thumbnails im Hintergrund cachen."""
    async def _cache_missing():
        rows = await db.fetch_all(
            "SELECT video_id, thumbnail_url FROM rss_entries WHERE thumbnail_url IS NOT NULL")
        cached = 0
        for row in rows:
            dest = RSS_THUMBS_DIR / f"{row['video_id']}.jpg"
            if dest.exists() and dest.stat().st_size > 500:
                continue
            try:
                await rss_service._cache_rss_thumbnail(row["video_id"], row["thumbnail_url"])
                cached += 1
            except Exception:
                pass
        logger.info(f"RSS-Thumb-Cache: {cached} neue Thumbnails gecacht")

    background_tasks.add_task(_cache_missing)
    return {"status": "started", "message": "Caching läuft im Hintergrund"}


@router.post("/cache-banners")
async def cache_all_banners(background_tasks: BackgroundTasks):
    """Alle externen Kanal-Banner lokal cachen und DB-URLs umstellen."""
    from app.config import BANNERS_DIR

    async def _cache_banners():
        BANNERS_DIR.mkdir(parents=True, exist_ok=True)
        rows = await db.fetch_all(
            "SELECT channel_id, banner_url FROM subscriptions WHERE banner_url IS NOT NULL AND banner_url NOT LIKE '/api/%'")
        cached = 0
        for row in rows:
            dest = BANNERS_DIR / f"{row['channel_id']}.jpg"
            if dest.exists() and dest.stat().st_size > 1000:
                await db.execute(
                    "UPDATE subscriptions SET banner_url = ? WHERE channel_id = ?",
                    (f"/api/subscriptions/banner/{row['channel_id']}", row["channel_id"]))
                cached += 1
                continue
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(row["banner_url"])
                    if resp.status_code == 200 and len(resp.content) > 1000:
                        dest.write_bytes(resp.content)
                        await db.execute(
                            "UPDATE subscriptions SET banner_url = ? WHERE channel_id = ?",
                            (f"/api/subscriptions/banner/{row['channel_id']}", row["channel_id"]))
                        cached += 1
            except Exception as e:
                logger.debug(f"Banner-Cache {row['channel_id']}: {e}")
            import asyncio
            await asyncio.sleep(0.5)
        logger.info(f"Banner-Cache: {cached} Banner lokal gecacht")

    background_tasks.add_task(_cache_banners)
    return {"status": "started", "message": "Banner-Caching läuft im Hintergrund"}



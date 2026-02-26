"""
TubeVault -  Feed Router
RSS-Feed Endpoints: Channels, Tags, Videos, Status-Aktionen.
Extrahiert aus subscriptions.py für bessere Modularität.
© HalloWelt42 -  Private Nutzung
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import json
import logging

logger = logging.getLogger(__name__)

from app.database import db
from app.services.rss_service import rss_service

router = APIRouter(prefix="/api/subscriptions", tags=["Feed"])


@router.get("/feed/channels")
async def get_feed_channels(feed_tab: str = Query("active")):
    """Alle abonnierten Kanaele fuer Feed-Filter -  IMMER alle, auch ohne Entries."""
    status_filter = ""
    if feed_tab == "active":
        status_filter = "AND COALESCE(r.feed_status, 'active') = 'active'"
    elif feed_tab in ("later", "dismissed", "archived"):
        status_filter = f"AND r.feed_status = '{feed_tab}'"

    rows = await db.fetch_all(
        f"""SELECT s.channel_id, s.channel_name,
                   COUNT(CASE WHEN r.id IS NOT NULL {status_filter.replace('AND', 'AND')} THEN 1 END) as count,
                   s.last_checked,
                   s.enabled
            FROM subscriptions s
            LEFT JOIN rss_entries r ON s.channel_id = r.channel_id
            WHERE s.enabled = 1
            GROUP BY s.channel_id
            ORDER BY s.channel_name COLLATE NOCASE ASC"""
    )
    return [dict(r) for r in rows]


@router.get("/feed/tags")
async def get_feed_tags(feed_tab: str = Query("active")):
    """Alle einzigartigen Tags/Keywords aus RSS-Entries zurueckgeben."""
    status_filter = ""
    if feed_tab == "active":
        status_filter = "AND COALESCE(r.feed_status, 'active') = 'active'"
    elif feed_tab in ("later", "dismissed", "archived"):
        status_filter = f"AND r.feed_status = '{feed_tab}'"

    rows = await db.fetch_all(
        f"""SELECT r.keywords FROM rss_entries r
            JOIN subscriptions s ON r.channel_id = s.channel_id
            WHERE r.keywords IS NOT NULL AND r.keywords != '[]'
            {status_filter}"""
    )
    tag_counts = {}
    for row in rows:
        try:
            kws = json.loads(row["keywords"]) if isinstance(row["keywords"], str) else row["keywords"]
            if isinstance(kws, list):
                for kw in kws:
                    kw = str(kw).strip()
                    if kw:
                        tag_counts[kw] = tag_counts.get(kw, 0) + 1
        except (json.JSONDecodeError, TypeError):
            pass
    sorted_tags = sorted(tag_counts.items(), key=lambda x: -x[1])
    return [{"tag": t, "count": c} for t, c in sorted_tags]


@router.get("/feed")
async def get_feed_videos(
    channel_id: Optional[str] = None,
    channel_ids: Optional[str] = None,
    video_type: str = Query("all"),
    video_types: Optional[str] = None,
    keywords: Optional[str] = None,
    duration_min: Optional[int] = None,
    duration_max: Optional[int] = None,
    feed_tab: str = Query("active"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """Neue Videos aus RSS-Feeds -  mit Mehrfach-Typ/Kanal/Tag/Dauer-Filter, Feed-Tabs und Pagination."""
    return await rss_service.get_new_videos(
        channel_id, channel_ids, video_type, video_types, feed_tab, page, per_page,
        keywords=keywords, duration_min=duration_min, duration_max=duration_max
    )


@router.post("/feed/{entry_id}/status")
async def set_entry_status(entry_id: int, status: str = Query(...)):
    """Feed-Eintrag Status setzen (active/later/archived/dismissed)."""
    try:
        await rss_service.set_feed_status(entry_id, status)
        return {"ok": True, "status": status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/feed/{entry_id}/type")
async def set_entry_type(entry_id: int, video_type: str = Query(...)):
    """Video-Typ manuell aendern (video/short/live)."""
    if video_type not in ("video", "short", "live"):
        raise HTTPException(status_code=400, detail=f"Ungueltiger Typ: {video_type}")
    await db.execute(
        "UPDATE rss_entries SET video_type = ? WHERE id = ?", (video_type, entry_id)
    )
    row = await db.fetch_one("SELECT video_id FROM rss_entries WHERE id = ?", (entry_id,))
    if row:
        await db.execute(
            "UPDATE videos SET video_type = ? WHERE id = ?", (video_type, row["video_id"])
        )
    return {"ok": True, "video_type": video_type}


@router.post("/feed/type-by-video")
async def set_type_by_video_id(video_id: str = Query(...), video_type: str = Query(...)):
    """Video-Typ per video_id ändern (für ChannelDetail)."""
    if video_type not in ("video", "short", "live"):
        raise HTTPException(status_code=400, detail=f"Ungültiger Typ: {video_type}")
    # RSS-Einträge aktualisieren (kann mehrere geben)
    await db.execute(
        "UPDATE rss_entries SET video_type = ? WHERE video_id = ?", (video_type, video_id)
    )
    # Videos-Tabelle aktualisieren
    await db.execute(
        "UPDATE videos SET video_type = ? WHERE id = ?", (video_type, video_id)
    )
    return {"ok": True, "video_id": video_id, "video_type": video_type}


@router.post("/feed/bulk-status")
async def set_bulk_status(body: dict):
    """Mehrere Feed-Eintraege auf Status setzen."""
    entry_ids = body.get("entry_ids", [])
    status = body.get("status", "")
    if not entry_ids or not status:
        raise HTTPException(status_code=400, detail="entry_ids und status erforderlich")
    try:
        await rss_service.set_feed_status_bulk(entry_ids, status)
        return {"ok": True, "count": len(entry_ids), "status": status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/feed/bulk-type")
async def set_bulk_type(body: dict):
    """Mehrere Feed-Eintraege Typ aendern."""
    entry_ids = body.get("entry_ids", [])
    video_type = body.get("video_type", "")
    if not entry_ids or video_type not in ("video", "short", "live"):
        raise HTTPException(status_code=400, detail="entry_ids und video_type (video/short/live) erforderlich")

    placeholders = ",".join("?" * len(entry_ids))
    await db.execute(
        f"UPDATE rss_entries SET video_type = ? WHERE id IN ({placeholders})",
        (video_type, *entry_ids)
    )
    rows = await db.fetch_all(
        f"SELECT video_id FROM rss_entries WHERE id IN ({placeholders})",
        tuple(entry_ids)
    )
    for row in rows:
        await db.execute(
            "UPDATE videos SET video_type = ? WHERE id = ?",
            (video_type, row["video_id"])
        )
    return {"ok": True, "count": len(entry_ids), "video_type": video_type}


@router.post("/feed/{entry_id}/dismiss")
async def dismiss_entry(entry_id: int):
    """RSS-Eintrag als gelesen markieren."""
    await rss_service.dismiss_entry(entry_id)
    return {"dismissed": True}


@router.post("/feed/{entry_id}/restore")
async def restore_entry(entry_id: int):
    """Ausgeblendeten Eintrag wiederherstellen."""
    await rss_service.restore_entry(entry_id)
    return {"restored": True}


@router.post("/feed/dismiss-all")
async def dismiss_all(channel_id: Optional[str] = None):
    """Alle aktiven Eintraege als gelesen markieren."""
    await rss_service.dismiss_all(channel_id)
    return {"dismissed": True}


@router.post("/feed/move-all")
async def move_all_status(body: dict):
    """Alle Eintraege von einem Status zum anderen verschieben."""
    from_status = body.get("from", "")
    to_status = body.get("to", "")
    ch = body.get("channel_id")
    if not from_status or not to_status:
        raise HTTPException(status_code=400, detail="from und to erforderlich")
    await rss_service.set_all_status(from_status, to_status, ch)
    return {"ok": True, "from": from_status, "to": to_status}

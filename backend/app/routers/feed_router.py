"""
TubeVault – Feed Router
RSS-Feed Endpoints: Channels, Tags, Videos, Status-Aktionen.
Extrahiert aus subscriptions.py für bessere Modularität.
© HalloWelt42 – Private Nutzung
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import logging

logger = logging.getLogger(__name__)

from app.database import db
from app.services import feed_scope
from app.services.rss_service import rss_service

router = APIRouter(prefix="/api/subscriptions", tags=["Feed"])


@router.get("/feed/channels")
async def get_feed_channels(feed_tab: str = Query("active")):
    """Alle abonnierten Kanaele fuer Feed-Filter – IMMER alle, auch ohne Entries."""
    status_filter = ""
    if feed_tab == "active":
        status_filter = f"AND {feed_scope.new_entry('r')}"
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
    """Schlagwörter der Feed-Einträge eines Reiters mit Anzahl ({tag, key, count}):
    je Schlüssel jeder Eintrag einmal, Schreibweise egal (feed_keywords, tag_index)."""
    status_filter = "1 = 1"
    if feed_tab == "active":
        status_filter = feed_scope.new_entry('r')
    elif feed_tab in ("later", "dismissed", "archived"):
        status_filter = f"r.feed_status = '{feed_tab}'"
    from app.services import feed_keywords
    return await feed_keywords.INDEX.counts(
        "rss_entries r JOIN subscriptions s ON r.channel_id = s.channel_id", "r", status_filter, [])


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
    language: Optional[list[str]] = Query(None, description="Sprachkürzel, mehrfach oder kommagetrennt; und = ohne Sprache"),
):
    """Neue Videos aus RSS-Feeds - mit Mehrfach-Typ/Kanal/Tag/Dauer/Sprach-Filter, Feed-Tabs und Pagination.
    language_counts in der Antwort: Zähler je Sprache mit allen Filtern außer der Sprache."""
    from app.services import language as language_service
    return await rss_service.get_new_videos(
        channel_id, channel_ids, video_type, video_types, feed_tab, page, per_page,
        keywords=keywords, duration_min=duration_min, duration_max=duration_max,
        languages=language_service.parse_filter(language),
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
    """Video-Typ von Hand ändern (video/short/live)."""
    row = await db.fetch_one("SELECT video_id FROM rss_entries WHERE id = ?", (entry_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Feed-Eintrag nicht gefunden")
    await _set_type([row["video_id"]], video_type)
    return {"ok": True, "video_type": video_type}


@router.post("/feed/type-by-video")
async def set_type_by_video_id(video_id: str = Query(...), video_type: str = Query(...)):
    """Video-Typ per video_id ändern (für ChannelDetail)."""
    await _set_type([video_id], video_type)
    return {"ok": True, "video_id": video_id, "video_type": video_type}


async def _set_type(video_ids: list[str], video_type: str) -> None:
    """Typ von Hand setzen - eine Stelle für Video und Feed (video_classifier)."""
    from app.services import video_classifier
    try:
        await video_classifier.set_manual(video_ids, video_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
    rows = await db.fetch_all(
        f"SELECT video_id FROM rss_entries WHERE id IN ({placeholders})",
        tuple(entry_ids)
    )
    await _set_type([row["video_id"] for row in rows], video_type)
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


@router.get("/feed-search")
async def search_feed_entries(
    q: str = Query("", min_length=2),
    channel: Optional[str] = None,
    limit: int = Query(20, ge=1, le=50),
):
    """Feed-Einträge nach Titel, Kennung oder Kanal durchsuchen (Zuordnen,
    Verknüpfen, Suchfeld). in_library: das Video liegt schon in der Bibliothek."""
    conditions = ["r.title IS NOT NULL"]
    params = []
    if q:
        conditions.append("(r.title LIKE ? OR r.video_id LIKE ? OR s.channel_name LIKE ?)")
        params.extend([f"%{q}%"] * 3)
    if channel:
        conditions.append("s.channel_name LIKE ?")
        params.append(f"%{channel}%")
    rows = await db.fetch_all(
        f"""SELECT r.video_id, r.title, r.duration, r.published, s.channel_name, s.channel_id,
                   CASE WHEN v.id IS NOT NULL THEN 1 ELSE 0 END AS in_library
            FROM rss_entries r
            JOIN subscriptions s ON r.channel_id = s.channel_id
            LEFT JOIN videos v ON v.id = r.video_id
            WHERE {" AND ".join(conditions)}
            ORDER BY r.published DESC LIMIT ?""", (*params, limit))
    return {"results": [dict(r) for r in rows], "count": len(rows)}


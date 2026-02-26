"""
TubeVault -  RYD (Return YouTube Dislike) Service v1.5.90
Ruft Like/Dislike-Daten von returnyoutubedislikeapi.com ab und cached sie in der DB.
© HalloWelt42 -  Private Nutzung
"""

import logging
import asyncio
from datetime import datetime, timedelta

import httpx

from app.database import db
from app.services.endpoint_service import get_service_url

logger = logging.getLogger(__name__)

RYD_BASE = "https://returnyoutubedislikeapi.com"
CACHE_DAYS = 7  # Nach X Tagen neu abrufen


async def _get_ryd_url() -> str:
    """RYD-API-URL aus api_endpoints-Tabelle lesen (falls geändert)."""
    url = await get_service_url("ryd_api")
    return url if url else RYD_BASE


async def fetch_votes(video_id: str, force: bool = False) -> dict | None:
    """Like/Dislike-Daten für ein Video abrufen + in DB speichern.
    Gibt dict mit likes, dislikes, ratio zurück oder None bei Fehler.
    """
    if not video_id or video_id.startswith("local_"):
        return None

    # Cache prüfen (außer force=True)
    if not force:
        cached = await db.fetch_one(
            "SELECT like_count, dislike_count, like_ratio, likes_fetched_at FROM videos WHERE id = ?",
            (video_id,)
        )
        if cached and cached["likes_fetched_at"]:
            try:
                fetched = datetime.fromisoformat(cached["likes_fetched_at"])
                if datetime.utcnow() - fetched < timedelta(days=CACHE_DAYS):
                    return {
                        "likes": cached["like_count"] or 0,
                        "dislikes": cached["dislike_count"] or 0,
                        "ratio": cached["like_ratio"] or 0,
                        "cached": True,
                    }
            except (ValueError, TypeError):
                pass

    # API abrufen
    base_url = await _get_ryd_url()
    url = f"{base_url}/votes?videoId={video_id}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            if resp.status_code == 404:
                logger.debug(f"RYD: Video {video_id} nicht gefunden")
                return None
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning(f"RYD-API Fehler für {video_id}: {e}")
        return None

    likes = data.get("likes", 0)
    dislikes = data.get("dislikes", 0)
    total = likes + dislikes
    ratio = round(likes / total, 4) if total > 0 else 0

    # In DB speichern
    now = datetime.utcnow().isoformat()
    try:
        await db.execute(
            """UPDATE videos SET like_count = ?, dislike_count = ?,
               like_ratio = ?, likes_fetched_at = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (likes, dislikes, ratio, now, video_id)
        )
    except Exception as e:
        logger.warning(f"RYD DB-Update für {video_id}: {e}")

    return {
        "likes": likes,
        "dislikes": dislikes,
        "ratio": ratio,
        "viewCount": data.get("viewCount"),
        "cached": False,
    }


async def fetch_votes_batch(video_ids: list[str], force: bool = False) -> dict:
    """Batch: Like/Dislike-Daten für mehrere Videos.
    Rate-Limit beachten: max 100/min.
    Gibt dict {video_id: result} zurück.
    """
    results = {}
    semaphore = asyncio.Semaphore(5)  # Max 5 gleichzeitig

    async def _fetch(vid):
        async with semaphore:
            results[vid] = await fetch_votes(vid, force=force)
            await asyncio.sleep(0.1)  # Rate-Limit schonen

    await asyncio.gather(*[_fetch(vid) for vid in video_ids[:50]])  # Max 50 pro Batch
    return results

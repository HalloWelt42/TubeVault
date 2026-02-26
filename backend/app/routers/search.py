"""
TubeVault -  Search Router v1.5.96
YouTube-Suche via pytubefix Search + lokale DB-Suche
Unified: Ein Search()-Call liefert Videos, Shorts, Playlists, Channels
© HalloWelt42 -  Private Nutzung
"""

import asyncio
import json
import logging
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.database import db
from app.services.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/search", tags=["Search"])


# ─── URL-Typ-Erkennung ───────────────────────────────────────────

def _detect_url_type(url: str) -> tuple[str, str | None]:
    """Erkennt URL-Typ: ('video', video_id), ('playlist', list_id), ('channel', channel_ref), ('unknown', None)"""

    url = url.strip()

    # Reine Playlist-URL: youtube.com/playlist?list=...
    if 'playlist?list=' in url or '/playlist/' in url:
        m = re.search(r'list=([a-zA-Z0-9_-]+)', url)
        return ('playlist', m.group(1)) if m else ('unknown', None)

    # Video mit Playlist: watch?v=...&list=... → Playlist bevorzugen
    if ('watch?' in url or 'youtu.be/' in url) and 'list=' in url:
        m = re.search(r'list=([a-zA-Z0-9_-]+)', url)
        return ('playlist', m.group(1)) if m else ('video', None)

    # Normales Video
    video_patterns = [
        r'(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',
    ]
    for p in video_patterns:
        m = re.search(p, url)
        if m:
            return ('video', m.group(1))

    # Channel: /@handle, /channel/UC..., /c/...
    channel_patterns = [
        r'youtube\.com/(@[a-zA-Z0-9_.-]+)',
        r'youtube\.com/channel/([a-zA-Z0-9_-]+)',
        r'youtube\.com/c/([a-zA-Z0-9_.-]+)',
    ]
    for p in channel_patterns:
        m = re.search(p, url)
        if m:
            return ('channel', m.group(1))

    return ('unknown', None)


# ─── URL Resolver ─────────────────────────────────────────────────

@router.post("/resolve-url")
async def resolve_url(data: dict):
    """Universeller URL-Router: Erkennt Video, Playlist oder Kanal und liefert Infos."""
    url = data.get("url", "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL fehlt")

    url_type, ref = _detect_url_type(url)

    if url_type == 'unknown':
        raise HTTPException(status_code=400, detail="URL nicht erkannt. Unterstützt: YouTube-Video, Playlist oder Kanal.")

    # ─── Video ───
    if url_type == 'video':
        from app.services.download_service import download_service
        try:
            info = await download_service.get_video_info(url)
            return {"type": "video", "data": info}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ─── Playlist ───
    if url_type == 'playlist':
        await rate_limiter.acquire("pytubefix")

        def _fetch_playlist():
            from pytubefix import Playlist
            pl = Playlist(f"https://www.youtube.com/playlist?list={ref}")
            videos = []
            for v in pl.videos:
                try:
                    videos.append({
                        "id": v.video_id,
                        "title": v.title,
                        "channel_name": v.author,
                        "channel_id": getattr(v, "channel_id", None),
                        "duration": v.length,
                        "thumbnail_url": v.thumbnail_url,
                    })
                except Exception as e:
                    logger.warning(f"Playlist video parse: {e}")

            # Safe title access (simpleText workaround)
            title = None
            try:
                title = pl.title
            except (KeyError, AttributeError) as e:
                logger.warning(f"Playlist title fallback: {e}")
                try:
                    title = pl._html_data.get("title", {}).get("runs", [{}])[0].get("text")
                except Exception:
                    pass
            title = title or f"Playlist {ref}"

            return {
                "playlist_id": getattr(pl, "playlist_id", ref),
                "title": title,
                "owner": getattr(pl, "owner", None),
                "owner_id": getattr(pl, "owner_id", None),
                "description": getattr(pl, "description", None) or "",
                "video_count": getattr(pl, "length", None) or len(videos),
                "videos": videos,
            }

        try:
            result = await asyncio.get_event_loop().run_in_executor(None, _fetch_playlist)
            rate_limiter.success("pytubefix")
        except Exception as e:
            rate_limiter.error("pytubefix", str(e)[:200])
            raise HTTPException(status_code=500, detail=f"Playlist-Abruf fehlgeschlagen: {e}")

        # Enrichment: welche Videos lokal vorhanden?
        for v in result["videos"]:
            existing = await db.fetch_one("SELECT status FROM videos WHERE id = ?", (v["id"],))
            v["already_downloaded"] = existing is not None and existing["status"] == "ready"
            v["status"] = existing["status"] if existing else None

        return {"type": "playlist", "data": result}

    # ─── Channel ───
    if url_type == 'channel':
        await rate_limiter.acquire("pytubefix")

        def _fetch_channel():
            from pytubefix import Channel
            if ref.startswith("@"):
                ch = Channel(f"https://www.youtube.com/{ref}")
            elif ref.startswith("UC"):
                ch = Channel(f"https://www.youtube.com/channel/{ref}")
            else:
                ch = Channel(f"https://www.youtube.com/c/{ref}")
            return {
                "channel_id": ch.channel_id,
                "channel_name": ch.channel_name,
                "vanity_url": getattr(ch, "vanity_url", None),
            }

        try:
            result = await asyncio.get_event_loop().run_in_executor(None, _fetch_channel)
            rate_limiter.success("pytubefix")
        except Exception as e:
            rate_limiter.error("pytubefix", str(e)[:200])
            raise HTTPException(status_code=500, detail=f"Kanal-Abruf fehlgeschlagen: {e}")

        # Bereits abonniert?
        sub = await db.fetch_one(
            "SELECT id FROM subscriptions WHERE channel_id = ?", (result["channel_id"],))
        result["already_subscribed"] = sub is not None

        return {"type": "channel", "data": result}


# ─── Shared YouTube-Suche (DRY) ──────────────────────────────────

def _do_yt_search(q: str, max_videos: int = 15, include_extras: bool = False) -> dict:
    """Shared pytubefix Search — ein Search()-Call für alles.

    Args:
        q: Suchbegriff
        max_videos: Max Video-Ergebnisse
        include_extras: True → auch Shorts, Playlists, Channels, Suggestions
    """
    from pytubefix import Search
    s = Search(q)

    videos = []
    for v in s.videos[:max_videos]:
        try:
            videos.append({
                "id": v.video_id, "title": v.title,
                "channel_name": v.author, "channel_id": v.channel_id,
                "duration": v.length, "view_count": v.views,
                "thumbnail_url": v.thumbnail_url,
            })
        except Exception:
            pass

    result = {"videos": videos}

    if not include_extras:
        return result

    # Shorts
    shorts = []
    try:
        for v in s.shorts[:8]:
            try:
                shorts.append({
                    "id": v.video_id, "title": v.title,
                    "channel_name": v.author, "duration": v.length,
                    "thumbnail_url": v.thumbnail_url,
                })
            except Exception:
                pass
    except Exception:
        pass

    # Playlists
    playlists = []
    try:
        for p in s.playlist[:6]:
            try:
                playlists.append({
                    "id": p.playlist_id, "title": p.title,
                    "url": p.playlist_url,
                    "owner": getattr(p, "owner", None),
                    "video_count": p.length if hasattr(p, "length") else None,
                })
            except Exception:
                pass
    except Exception:
        pass

    # Channels
    channels = []
    try:
        for c in s.channel[:4]:
            try:
                channels.append({
                    "id": c.channel_id, "name": c.channel_name,
                })
            except Exception:
                pass
    except Exception:
        pass

    # Autocomplete Suggestions
    suggestions = []
    try:
        suggestions = s.completion_suggestions[:8]
    except Exception:
        pass

    result.update({
        "shorts": shorts, "playlists": playlists,
        "channels": channels, "suggestions": suggestions,
    })
    return result


async def _enrich_videos(videos: list[dict]):
    """Enrichment: downloaded/queued Status für Video-Liste."""
    for r in videos:
        vid = r["id"]
        existing = await db.fetch_one("SELECT status FROM videos WHERE id = ?", (vid,))
        r["already_downloaded"] = existing is not None and existing["status"] == "ready"
        queued = await db.fetch_one(
            "SELECT id FROM jobs WHERE type='download' AND json_extract(metadata, '$.video_id') = ? AND status IN ('queued','active')", (vid,))
        r["already_in_queue"] = queued is not None


# ─── YouTube-Suche Endpoints ─────────────────────────────────────

@router.get("/youtube/full")
async def search_youtube_full(
    q: str = Query(..., min_length=1, max_length=200),
    max_results: int = Query(15, ge=1, le=30),
):
    """YouTube-Suche: Videos, Shorts, Playlists und Kanäle in einem Call."""
    await rate_limiter.acquire("pytubefix")

    try:
        results = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _do_yt_search(q, max_videos=max_results, include_extras=True)
        )
        rate_limiter.success("pytubefix")
    except Exception as e:
        rate_limiter.error("pytubefix", str(e)[:200])
        raise HTTPException(status_code=500, detail=f"YouTube-Suche fehlgeschlagen: {e}")

    await _enrich_videos(results["videos"])

    # Shorts auch enrichen
    for s in results.get("shorts", []):
        existing = await db.fetch_one("SELECT status FROM videos WHERE id = ?", (s["id"],))
        s["already_downloaded"] = existing is not None and existing["status"] == "ready"

    return {"query": q, **results}


@router.get("/youtube")
async def search_youtube(
    q: str = Query(..., min_length=1, max_length=200),
    max_results: int = Query(15, ge=1, le=50),
):
    """YouTube-Video-Suche (Compat-Endpoint, nur Videos). Genutzt von YouTubeSearchPicker."""
    await rate_limiter.acquire("pytubefix")

    try:
        results = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _do_yt_search(q, max_videos=max_results, include_extras=False)
        )
        rate_limiter.success("pytubefix")
    except Exception as e:
        rate_limiter.error("pytubefix", str(e)[:200])
        raise HTTPException(status_code=500, detail=f"YouTube-Suche fehlgeschlagen: {e}")

    await _enrich_videos(results["videos"])

    return {"query": q, "results": results["videos"], "count": len(results["videos"])}


# ─── Lokale Suche ─────────────────────────────────────────────────

@router.get("/local")
async def search_local(
    q: str = Query(..., min_length=1, max_length=200),
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=100),
    source: Optional[str] = None,
    scope: Optional[str] = None,
):
    """Lokale Suche über alle heruntergeladenen Videos + eigene Videos.
    scope: 'favorites' | 'playlists' | None (alle)
    """
    conditions = [
        "v.status = 'ready'",
        "COALESCE(v.is_archived, 0) = 0",
        "(v.title LIKE ? OR v.channel_name LIKE ? OR v.description LIKE ? OR v.tags LIKE ?)",
    ]
    search_term = f"%{q}%"
    params = [search_term, search_term, search_term, search_term]

    if source:
        conditions.append("v.source = ?")
        params.append(source)

    if scope == "favorites":
        conditions.append("v.id IN (SELECT video_id FROM favorites)")
    elif scope == "playlists":
        conditions.append("v.id IN (SELECT video_id FROM playlist_videos)")
    elif scope == "own":
        conditions.append("v.source IN ('local', 'imported')")

    where = f"WHERE {' AND '.join(conditions)}"
    total = await db.fetch_val(f"SELECT COUNT(*) FROM videos v {where}", params)
    offset = (page - 1) * per_page

    rows = await db.fetch_all(
        f"""SELECT v.* FROM videos v {where}
            ORDER BY v.play_count DESC, v.updated_at DESC
            LIMIT ? OFFSET ?""",
        params + [per_page, offset]
    )

    videos = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get("tags"), str):
            try:
                d["tags"] = json.loads(d["tags"])
            except (json.JSONDecodeError, TypeError):
                d["tags"] = []
        d.pop("ai_summary", None)
        d.pop("ai_tags", None)
        videos.append(d)

    total_pages = max(1, (total + per_page - 1) // per_page)
    return {
        "query": q,
        "videos": videos,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    }

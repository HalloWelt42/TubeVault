"""
TubeVault – Search Router v1.6.0
YouTube-Suche via pytubefix Search + lokale DB-Suche
Unified: Ein Search()-Call liefert Videos, Shorts, Playlists, Channels
© HalloWelt42 – Private Nutzung
"""

import asyncio
import logging
import re
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.database import db
from app.services.rate_limiter import rate_limiter
from app.routers.blocked_channels import get_blocked_ids
from app.services import language as _language
from app.services.search import engine as search_engine, saved as saved_searches, vocabulary
from app.services.search.filters import Length, Order, Period, SearchFilters
from app.services.search.models import Overview, Section, SectionPage, VideoSpots
from app.services.search.query import Location
from app.services.search.saved import SavedSearch, SavedSearchInput
from app.services.watch_state import State

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
            from app.utils.pytube_client import make_playlist
            pl = make_playlist(f"https://www.youtube.com/playlist?list={ref}")
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
            from app.utils.pytube_client import make_channel
            if ref.startswith("@"):
                ch = make_channel(f"https://www.youtube.com/{ref}")
            elif ref.startswith("UC"):
                ch = make_channel(f"https://www.youtube.com/channel/{ref}")
            else:
                ch = make_channel(f"https://www.youtube.com/c/{ref}")
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

# Zwischenspeicher je Suchbegriff. Die Quelle kennt kein echtes Blättern:
# für Seite N muss die Trefferliste bis zum Ende von Seite N neu geholt
# werden. Ohne Zwischenspeicher wurde jede Seite langsamer, und weil sich die
# Reihenfolge zwischen zwei Abrufen verschiebt, tauchten Treffer doppelt auf
# oder fehlten. Mit Zwischenspeicher blättern alle Seiten durch DIESELBE Liste.
_YT_CACHE_TTL_S = 600
_YT_CACHE_MAX_QUERIES = 30
_YT_SHORT_MAX_S = 60
_yt_cache: dict[str, dict] = {}


def _safe_items(getter, convert) -> list[dict]:
    """Elemente einer Adapter-Liste umwandeln; einzelne kaputte überspringen."""
    out = []
    try:
        items = list(getter())
    except Exception:
        return out
    for item in items:
        try:
            out.append(convert(item))
        except Exception:
            pass
    return out


def _fetch_yt(q: str, max_results: int) -> dict:
    """Ein Abruf bei der Quelle, aufbereitet und nach Videos/Shorts getrennt."""
    from app.utils.pytube_client import make_search

    s = make_search(q, max_results=max_results)
    seen: set[str] = set()
    entries = []
    for v in _safe_items(lambda: s.videos, lambda v: {
        "id": v.video_id, "title": v.title,
        "channel_name": v.author, "channel_id": v.channel_id,
        "duration": v.length, "view_count": v.views,
        "thumbnail_url": v.thumbnail_url,
    }):
        if v["id"] and v["id"] not in seen:
            seen.add(v["id"])
            entries.append(v)

    def _is_short(v: dict) -> bool:
        return 0 < (v.get("duration") or 0) <= _YT_SHORT_MAX_S

    return {
        "fetched_at": time.time(),
        "requested": max_results,
        # weniger geliefert als verlangt → es gibt nichts mehr
        "exhausted": len(entries) < max_results,
        # Shorts stehen NUR unter shorts (vorher zusätzlich unter videos = doppelt)
        "videos": [v for v in entries if not _is_short(v)],
        "shorts": [v for v in entries if _is_short(v)],
        "playlists": _safe_items(lambda: s.playlist, lambda p: {
            "id": p.playlist_id, "title": p.title, "url": p.playlist_url,
            "owner": getattr(p, "owner", None),
            "video_count": p.length if hasattr(p, "length") else None,
        }),
        "channels": _safe_items(lambda: s.channel, lambda c: {
            "id": c.channel_id, "name": c.channel_name,
        }),
        "suggestions": _safe_items(lambda: s.completion_suggestions, lambda x: x),
    }


def _yt_results(q: str, needed_videos: int) -> dict:
    """Trefferliste mit mindestens needed_videos Videos (oder allem, was es gibt)."""
    key = " ".join(q.lower().split())
    cached = _yt_cache.get(key)
    fresh = cached and time.time() - cached["fetched_at"] < _YT_CACHE_TTL_S
    if fresh and (len(cached["videos"]) >= needed_videos or cached["exhausted"]):
        return cached

    # Etwas Vorrat holen (Shorts fallen aus der Videoliste heraus)
    request = needed_videos + max(10, needed_videos // 2)
    result = _fetch_yt(q, request)
    if not result["exhausted"] and len(result["videos"]) < needed_videos:
        result = _fetch_yt(q, request * 2)
    if fresh:
        # Bereits gezeigte Treffer behalten ihren Platz; Neues wird angehängt.
        # Sonst würfelt ein grösserer Abruf die Seiten neu durcheinander.
        for kind in ("videos", "shorts"):
            known = {v["id"] for v in cached["videos"]} | {v["id"] for v in cached["shorts"]}
            result[kind] = cached[kind] + [v for v in result[kind] if v["id"] not in known]
        for kind in ("playlists", "channels", "suggestions"):
            result[kind] = cached[kind] or result[kind]

    _yt_cache[key] = result
    while len(_yt_cache) > _YT_CACHE_MAX_QUERIES:
        oldest = min(_yt_cache, key=lambda k: _yt_cache[k]["fetched_at"])
        _yt_cache.pop(oldest)
    return result


def _do_yt_search(q: str, max_videos: int = 15, include_extras: bool = False,
                   page: int = 1, per_page: Optional[int] = None) -> dict:
    """YouTube-Suche mit Blättern über eine zwischengespeicherte Trefferliste.

    Args:
        q: Suchbegriff
        max_videos: Anzahl, wenn per_page nicht gesetzt ist (eine Seite)
        include_extras: True → auch Shorts, Playlists, Channels, Suggestions
        page: 1-basierte Seitenzahl
        per_page: Elemente pro Seite. Wenn gesetzt, hat Vorrang vor max_videos.
    """
    if per_page is None:
        per_page = max_videos
        page = 1

    start = (page - 1) * per_page
    end = page * per_page
    found = _yt_results(q, end + 1)   # +1, um weitere Seiten zu erkennen

    videos = [dict(v) for v in found["videos"][start:end]]
    result = {
        "videos": videos,
        "page": page,
        "per_page": per_page,
        "has_more": len(found["videos"]) > end,
        "count_on_page": len(videos),
    }
    if not include_extras:
        return result

    # Shorts/Playlists/Channels nur auf Seite 1 (Blättern zielt auf Videos)
    first = page == 1
    result.update({
        "shorts": [dict(v) for v in found["shorts"][:8]] if first else [],
        "playlists": list(found["playlists"][:6]) if first else [],
        "channels": list(found["channels"][:4]) if first else [],
        "suggestions": list(found["suggestions"][:8]) if first else [],
    })
    return result


async def _filter_blocked(videos: list[dict]) -> list[dict]:
    """Videos von geblockten Channels aus der Liste entfernen."""
    blocked = await get_blocked_ids()
    if not blocked:
        return videos
    return [v for v in videos if v.get("channel_id") not in blocked]


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
    max_results: int = Query(15, ge=1, le=50),
    page: int = Query(1, ge=1, le=20),
    per_page: Optional[int] = Query(None, ge=5, le=50),
):
    """YouTube-Suche mit Paginierung: Videos (+ optional Shorts/Playlists/Channels).

    Parameter:
      q           Suchbegriff
      max_results Legacy: Anzahl wenn per_page nicht gesetzt (Einzel-Seite)
      page        1-basierte Seitenzahl (für echte Paginierung mit per_page)
      per_page    Items pro Seite (wenn gesetzt, überschreibt max_results)

    Antwort enthält:
      videos, shorts, playlists, channels, suggestions,
      page, per_page, has_more, count_on_page, query
    """
    await rate_limiter.acquire("pytubefix")

    try:
        results = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _do_yt_search(
                q, max_videos=max_results, include_extras=True,
                page=page, per_page=per_page,
            )
        )
        rate_limiter.success("pytubefix")
    except Exception as e:
        rate_limiter.error("pytubefix", str(e)[:200])
        raise HTTPException(status_code=500, detail=f"YouTube-Suche fehlgeschlagen: {e}")

    # Blockliste anwenden (Channels ausblenden)
    results["videos"] = await _filter_blocked(results["videos"])
    results["shorts"] = await _filter_blocked(results.get("shorts", []))

    await _enrich_videos(results["videos"])

    # Shorts auch enrichen (nur auf Seite 1, da Shorts/Playlists/Channels nicht paginiert)
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

    # Blockliste anwenden + enrichen
    results["videos"] = await _filter_blocked(results["videos"])
    await _enrich_videos(results["videos"])

    return {"query": q, "results": results["videos"], "count": len(results["videos"])}


# ─── Suche über alles (services/search) ──────────────────────────

_PRECISION = "^(aus|weit|ausgewogen|genau|sehr_genau)$"


def search_filters(
    language: Optional[list[str]] = Query(None, description="Sprachkürzel, mehrfach oder kommagetrennt; und = ohne Sprache"),
    length: Optional[Length] = None,
    period: Optional[Period] = None,
    location: Optional[Location] = None,
    state: Optional[State] = None,
    order: Order = "passend",
    precision: Optional[str] = Query(None, pattern=_PRECISION),
) -> SearchFilters:
    """Filter der Suche aus den Abfrageparametern (Angaben im Suchtext gehen vor)."""
    return SearchFilters(languages=_language.parse_filter(language), length=length, period=period,
                         location=location, state=state, order=order, precision=precision)


@router.get("", response_model=Overview)
async def search_all(
    q: str = Query("", max_length=200),
    limit: int = Query(5, ge=1, le=20),
    meaning: bool = Query(True, description="Bedeutungssuche einbeziehen (Aufklappliste: aus)"),
    filters: SearchFilters = Depends(search_filters),
):
    """Alle Bereiche auf einmal: je Bereich die besten Treffer und die Zahl.
    Suchsprache und Rangfolge: services/search (query, videos)."""
    return await search_engine.overview(q, filters, limit=limit, with_meaning=meaning)


@router.get("/section/{name}", response_model=SectionPage)
async def search_section(
    name: Section,
    q: str = Query(..., min_length=1, max_length=200),
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=100),
    filters: SearchFilters = Depends(search_filters),
):
    """Ein Bereich seitenweise (videos, gesagt, kapitel, abos, kanaele, playlists, musik, sinngemaess)."""
    return await search_engine.section(name, q, filters, page=page, per_page=per_page)


@router.get("/video-ids", response_model=list[str])
async def search_video_ids(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(1000, ge=1, le=5000),
    filters: SearchFilters = Depends(search_filters),
):
    """Kennungen der Videotreffer in Trefferfolge, etwa für "Treffer als Playlist"."""
    return await search_engine.video_ids(q, filters, limit=limit)


@router.get("/spots/{video_id}", response_model=VideoSpots)
async def search_spots(video_id: str, q: str = Query(..., min_length=1, max_length=200)):
    """Alle Fundstellen eines Videos (Vorschau): Kapitel, Gesagtes, Beschreibung."""
    return await search_engine.spots_of(video_id, q)


@router.get("/complete", response_model=list[str])
async def search_complete(q: str = Query(..., min_length=1, max_length=200), limit: int = Query(6, ge=1, le=12)):
    """Ergänzungen für das zuletzt getippte Wort aus dem Wortschatz der Titel."""
    return await vocabulary.complete(q, limit)


@router.get("/saved", response_model=list[SavedSearch])
async def saved_list():
    """Gemerkte Suchen mit der Zahl neuer Treffer seit dem letzten Öffnen."""
    return await saved_searches.all_saved()


@router.post("/saved", response_model=SavedSearch)
async def saved_create(data: SavedSearchInput):
    try:
        return await saved_searches.create(data)
    except ValueError as e:
        raise HTTPException(400, str(e))


class _Rename(BaseModel):
    name: str


@router.put("/saved/{saved_id}")
async def saved_rename(saved_id: str, data: _Rename):
    if not await saved_searches.rename(saved_id, data.name):
        raise HTTPException(404, "Gemerkte Suche nicht gefunden")
    return {"ok": True}


@router.post("/saved/{saved_id}/seen")
async def saved_seen(saved_id: str):
    """Neue Treffer als gesehen werten (beim Öffnen der Suche)."""
    if not await saved_searches.mark_seen(saved_id):
        raise HTTPException(404, "Gemerkte Suche nicht gefunden")
    return {"ok": True}


@router.delete("/saved/{saved_id}")
async def saved_delete(saved_id: str):
    if not await saved_searches.delete(saved_id):
        raise HTTPException(404, "Gemerkte Suche nicht gefunden")
    return {"ok": True}

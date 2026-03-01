"""
TubeVault -  Ad-Markers Router v1.5.49
Werbemarken + SponsorBlock-Integration
Eigene Marker (manual) + externe (sponsorblock), voll editierbar
© HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
"""

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.database import db
from app.services.endpoint_service import get_service_url

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ad-markers", tags=["AdMarkers"])

# SponsorBlock-Kategorien mit deutschen Labels
SB_CATEGORIES = {
    "sponsor": "Sponsor",
    "selfpromo": "Eigenwerbung",
    "interaction": "Interaktion",
    "intro": "Intro",
    "outro": "Outro",
    "preview": "Vorschau",
    "music_offtopic": "Musik (Off-Topic)",
    "filler": "Füller",
}

SB_API_BASE = "https://sponsor.ajay.app"


async def import_sponsorblock_segments(video_id: str, cat_list: list = None) -> int:
    """SponsorBlock-Segmente laden und speichern. Gibt Anzahl importierter Segmente zurück."""
    if not cat_list:
        cat_list = ["sponsor", "selfpromo", "intro", "outro", "interaction"]

    cats_param = '["' + '","'.join(cat_list) + '"]'
    sb_url = await get_service_url("sponsorblock_api") or SB_API_BASE
    url = f"{sb_url}/api/skipSegments?videoID={video_id}&categories={cats_param}"

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)

    if resp.status_code == 404:
        return 0
    if resp.status_code != 200:
        raise RuntimeError(f"SponsorBlock API {resp.status_code}")

    segments = resp.json()
    existing = await db.fetch_all(
        "SELECT sb_uuid FROM ad_markers WHERE video_id = ? AND source = 'sponsorblock'",
        (video_id,))
    existing_uuids = {r["sb_uuid"] for r in existing if r["sb_uuid"]}

    imported = 0
    for seg in segments:
        uuid = seg.get("UUID")
        if uuid and uuid in existing_uuids:
            continue
        cat = seg.get("category", "sponsor")
        label = SB_CATEGORIES.get(cat, cat.capitalize())
        start = seg.get("segment", [0, 0])[0]
        end = seg.get("segment", [0, 0])[1]
        votes = seg.get("votes", 0)
        if end <= start:
            continue
        await db.execute(
            """INSERT INTO ad_markers (video_id, start_time, end_time, label, source, category, sb_uuid, votes)
               VALUES (?, ?, ?, ?, 'sponsorblock', ?, ?, ?)""",
            (video_id, start, end, label, cat, uuid, votes))
        imported += 1
    return imported


class AdMarkerCreate(BaseModel):
    start_time: float
    end_time: float
    label: Optional[str] = "Werbung"
    source: Optional[str] = "manual"
    category: Optional[str] = None


class AdMarkerUpdate(BaseModel):
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    label: Optional[str] = None
    category: Optional[str] = None


@router.get("/{video_id}")
async def get_ad_markers(video_id: str):
    """Alle Werbemarken eines Videos -  eigene + SponsorBlock."""
    rows = await db.fetch_all(
        "SELECT * FROM ad_markers WHERE video_id = ? ORDER BY start_time ASC",
        (video_id,)
    )
    markers = [dict(r) for r in rows]
    manual_count = sum(1 for m in markers if (m.get("source") or "manual") == "manual")
    sb_count = sum(1 for m in markers if m.get("source") == "sponsorblock")
    return {
        "video_id": video_id,
        "ad_markers": markers,
        "manual_count": manual_count,
        "sb_count": sb_count,
    }


@router.post("/{video_id}")
async def add_ad_marker(video_id: str, data: AdMarkerCreate):
    """Werbemarke hinzufuegen (manuell oder importiert)."""
    video = await db.fetch_one("SELECT id FROM videos WHERE id = ?", (video_id,))
    if not video:
        raise HTTPException(status_code=404, detail="Video nicht gefunden")
    if data.end_time <= data.start_time:
        raise HTTPException(status_code=400, detail="Ende muss nach Start liegen")

    cursor = await db.execute(
        """INSERT INTO ad_markers (video_id, start_time, end_time, label, source, category)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (video_id, data.start_time, data.end_time,
         data.label or "Werbung", data.source or "manual", data.category)
    )
    return {"id": cursor.lastrowid, "created": True}


@router.put("/{marker_id}")
async def update_ad_marker(marker_id: int, data: AdMarkerUpdate):
    """Werbemarke aktualisieren (egal ob manual oder sponsorblock)."""
    updates = data.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Keine Aenderungen")
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [marker_id]
    await db.execute(f"UPDATE ad_markers SET {set_clause} WHERE id = ?", values)
    return {"updated": True}


@router.delete("/{marker_id}")
async def delete_ad_marker(marker_id: int):
    """Werbemarke loeschen."""
    await db.execute("DELETE FROM ad_markers WHERE id = ?", (marker_id,))
    return {"deleted": True}


@router.delete("/{video_id}/all")
async def delete_all_ad_markers(video_id: str, source: Optional[str] = None):
    """Alle Werbemarken eines Videos loeschen.
    source: 'manual' | 'sponsorblock' | None (alle)
    """
    if source:
        cursor = await db.execute(
            "DELETE FROM ad_markers WHERE video_id = ? AND source = ?",
            (video_id, source)
        )
    else:
        cursor = await db.execute(
            "DELETE FROM ad_markers WHERE video_id = ?", (video_id,)
        )
    return {"deleted": cursor.rowcount}


# ─── SponsorBlock-Integration ────────────────────────────

@router.post("/{video_id}/sponsorblock")
async def fetch_sponsorblock(
    video_id: str,
    categories: Optional[str] = Query(None),
    replace: bool = Query(False),
):
    """SponsorBlock-Segmente laden und als Ad-Marker speichern.

    categories: Komma-getrennt, z.B. 'sponsor,intro,outro'
                Standard: sponsor,selfpromo,intro,outro,interaction
    replace: True = bestehende SB-Marker vorher loeschen
    """
    video = await db.fetch_one("SELECT id FROM videos WHERE id = ?", (video_id,))
    if not video:
        raise HTTPException(status_code=404, detail="Video nicht gefunden")

    if categories:
        cat_list = [c.strip() for c in categories.split(",") if c.strip() in SB_CATEGORIES]
    else:
        cat_list = ["sponsor", "selfpromo", "intro", "outro", "interaction"]

    try:
        cats_param = '["' + '","'.join(cat_list) + '"]'
        sb_url = await get_service_url("sponsorblock_api") or SB_API_BASE
        url = f"{sb_url}/api/skipSegments?videoID={video_id}&categories={cats_param}"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)

        if resp.status_code == 404:
            return {"video_id": video_id, "found": 0, "imported": 0,
                    "message": "Keine SponsorBlock-Segmente vorhanden"}
        if resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"SponsorBlock API Fehler: {resp.status_code}"
            )

        segments = resp.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="SponsorBlock API Timeout")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"SponsorBlock Fehler: {str(e)}")

    if replace:
        await db.execute(
            "DELETE FROM ad_markers WHERE video_id = ? AND source = 'sponsorblock'",
            (video_id,)
        )

    existing = await db.fetch_all(
        "SELECT sb_uuid FROM ad_markers WHERE video_id = ? AND source = 'sponsorblock'",
        (video_id,)
    )
    existing_uuids = {r["sb_uuid"] for r in existing if r["sb_uuid"]}

    imported = 0
    skipped = 0
    for seg in segments:
        uuid = seg.get("UUID")
        if uuid and uuid in existing_uuids:
            skipped += 1
            continue

        cat = seg.get("category", "sponsor")
        label = SB_CATEGORIES.get(cat, cat.capitalize())
        start = seg.get("segment", [0, 0])[0]
        end = seg.get("segment", [0, 0])[1]
        votes = seg.get("votes", 0)

        if end <= start:
            continue

        await db.execute(
            """INSERT INTO ad_markers (video_id, start_time, end_time, label, source, category, sb_uuid, votes)
               VALUES (?, ?, ?, ?, 'sponsorblock', ?, ?, ?)""",
            (video_id, start, end, label, cat, uuid, votes)
        )
        imported += 1

    return {
        "video_id": video_id,
        "found": len(segments),
        "imported": imported,
        "skipped": skipped,
        "categories": cat_list,
    }


@router.get("/{video_id}/sponsorblock/check")
async def check_sponsorblock(video_id: str):
    """Pruefen ob SponsorBlock-Segmente verfuegbar sind (ohne Import)."""
    try:
        sb_url = await get_service_url("sponsorblock_api") or SB_API_BASE
        url = f"{sb_url}/api/skipSegments?videoID={video_id}"
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(url)

        if resp.status_code == 404:
            return {"available": False, "count": 0}
        if resp.status_code == 200:
            segments = resp.json()
            cats = {}
            for seg in segments:
                cat = seg.get("category", "sponsor")
                cats[cat] = cats.get(cat, 0) + 1
            return {"available": True, "count": len(segments), "categories": cats}
        return {"available": False, "count": 0}
    except Exception:
        return {"available": False, "count": 0, "error": "API nicht erreichbar"}

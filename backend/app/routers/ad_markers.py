"""
TubeVault – Werbemarken

Eigene Marken (manual) und die des Werbemarken-Dienstes (sponsorblock).
Welche Abschnitte als Werbung gelten und wie der Abgleich läuft, steht in
services/ad_segments.
© HalloWelt42 – Private Nutzung
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import db
from app.services import ad_segments

router = APIRouter(prefix="/api/ad-markers", tags=["AdMarkers"])


class AdMarkerCreate(BaseModel):
    start_time: float
    end_time: float
    label: Optional[str] = "Werbung"


class AdMarkerUpdate(BaseModel):
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    label: Optional[str] = None


async def _markers(video_id: str) -> dict:
    rows = await db.fetch_all(
        "SELECT * FROM ad_markers WHERE video_id = ? ORDER BY start_time ASC", (video_id,))
    markers = [{**dict(r), "hidden": ad_segments.is_hidden(r["category"], r["source"])} for r in rows]
    checked_at = await db.fetch_val(
        "SELECT checked_at FROM ad_marker_checks WHERE video_id = ?", (video_id,))
    return {
        "video_id": video_id,
        "ad_markers": markers,
        "skip_ranges": [list(r) for r in await ad_segments.skip_ranges(video_id)],
        "checked_at": checked_at,
    }


@router.get("/{video_id}")
async def get_ad_markers(video_id: str):
    """Werbemarken eines Videos. Ist es Zeit, wird vorher beim Dienst
    nachgefragt (kurz, siehe ad_segments.refresh_if_due) - so gilt beim
    Öffnen eines Videos schon vor dem Abspielen der aktuelle Stand."""
    await ad_segments.refresh_if_due(video_id)
    return await _markers(video_id)


@router.post("/{video_id}/refresh")
async def refresh_ad_markers(video_id: str):
    """Sofort beim Dienst abgleichen, unabhängig vom letzten Abruf."""
    if not ad_segments.has_source(video_id):
        raise HTTPException(status_code=400, detail="Eigene und importierte Videos haben keine Marken beim Dienst")
    try:
        result = await ad_segments.refresh(video_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Werbemarken-Dienst nicht erreichbar: {e.__class__.__name__}")
    return {**await _markers(video_id), "found": result.found, "changed": result.changed}


@router.post("/{video_id}")
async def add_ad_marker(video_id: str, data: AdMarkerCreate):
    """Eigene Werbemarke setzen."""
    if not await db.fetch_one("SELECT id FROM videos WHERE id = ?", (video_id,)):
        raise HTTPException(status_code=404, detail="Video nicht gefunden")
    if data.end_time <= data.start_time:
        raise HTTPException(status_code=400, detail="Ende muss nach Start liegen")
    cursor = await db.execute(
        """INSERT INTO ad_markers (video_id, start_time, end_time, label, source)
           VALUES (?, ?, ?, ?, 'manual')""",
        (video_id, data.start_time, data.end_time, data.label or "Werbung"))
    await ad_segments.markers_changed(video_id)
    return {"id": cursor.lastrowid, "created": True}


async def _own_marker(marker_id: int):
    row = await db.fetch_one("SELECT video_id, source FROM ad_markers WHERE id = ?", (marker_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Werbemarke nicht gefunden")
    if (row["source"] or "manual") != "manual":
        # Sie käme beim nächsten Abgleich ohnehin wieder
        raise HTTPException(status_code=400, detail="Marken des Dienstes lassen sich nicht ändern")
    return row


@router.put("/{marker_id}")
async def update_ad_marker(marker_id: int, data: AdMarkerUpdate):
    """Eigene Werbemarke ändern."""
    row = await _own_marker(marker_id)
    updates = data.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Keine Änderungen")
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    await db.execute(f"UPDATE ad_markers SET {set_clause} WHERE id = ?", [*updates.values(), marker_id])
    await ad_segments.markers_changed(row["video_id"])
    return {"updated": True}


@router.delete("/{marker_id}")
async def delete_ad_marker(marker_id: int):
    """Eigene Werbemarke löschen."""
    row = await _own_marker(marker_id)
    await db.execute("DELETE FROM ad_markers WHERE id = ?", (marker_id,))
    await ad_segments.markers_changed(row["video_id"])
    return {"deleted": True}

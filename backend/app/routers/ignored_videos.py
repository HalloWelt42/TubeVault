"""
TubeVault Backend – Ignored Videos Router v1.0.0
Videos die dauerhaft nicht erneut geladen werden sollen
(fehlerhafte / gelöschte / geo-blocked / manuell ausgeschlossene).
© HalloWelt42 – Private Nutzung
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import db

router = APIRouter(prefix="/api/ignored-videos", tags=["IgnoredVideos"])


class IgnoreRequest(BaseModel):
    video_id: str
    channel_id: str | None = None
    reason: str | None = None


@router.get("")
async def list_ignored(channel_id: str | None = None):
    """Alle ignorierten Videos. Optional: nur für einen Channel."""
    if channel_id:
        rows = await db.fetch_all(
            "SELECT * FROM ignored_videos WHERE channel_id = ? ORDER BY created_at DESC",
            (channel_id,)
        )
    else:
        rows = await db.fetch_all(
            "SELECT * FROM ignored_videos ORDER BY created_at DESC"
        )
    return [dict(r) for r in rows]


@router.post("")
async def ignore_video(req: IgnoreRequest):
    """Video zur Ignore-Liste hinzufügen."""
    if not req.video_id:
        raise HTTPException(status_code=400, detail="video_id required")
    # Channel-ID aus rss_entries oder videos ableiten falls nicht übergeben
    channel_id = req.channel_id
    if not channel_id:
        row = await db.fetch_one(
            "SELECT channel_id FROM videos WHERE id = ? UNION SELECT channel_id FROM rss_entries WHERE video_id = ? LIMIT 1",
            (req.video_id, req.video_id)
        )
        if row:
            channel_id = row["channel_id"]
    await db.execute(
        """INSERT OR REPLACE INTO ignored_videos (video_id, channel_id, reason)
           VALUES (?, ?, ?)""",
        (req.video_id, channel_id, req.reason)
    )
    return {"video_id": req.video_id, "ignored": True}


@router.delete("/{video_id}")
async def unignore_video(video_id: str):
    """Video wieder aufnehmen."""
    await db.execute("DELETE FROM ignored_videos WHERE video_id = ?", (video_id,))
    return {"video_id": video_id, "ignored": False}


async def get_ignored_ids() -> set[str]:
    """Set aller ignorierten video_ids – für Filter im RSS/Auto-Download."""
    rows = await db.fetch_all("SELECT video_id FROM ignored_videos")
    return {r["video_id"] for r in rows}

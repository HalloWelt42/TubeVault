"""
TubeVault Backend – Blocked Channels Router v1.0.0
Channels die aus der YouTube-Suche ausgeblendet werden sollen.
© HalloWelt42 – Private Nutzung
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import db

router = APIRouter(prefix="/api/blocked-channels", tags=["BlockedChannels"])


class BlockRequest(BaseModel):
    channel_id: str
    channel_name: str | None = None
    reason: str | None = None


@router.get("")
async def list_blocked():
    """Alle geblockten Channels zurückgeben."""
    rows = await db.fetch_all(
        "SELECT * FROM blocked_channels ORDER BY created_at DESC"
    )
    return [dict(r) for r in rows]


@router.post("")
async def block_channel(req: BlockRequest):
    """Channel blockieren."""
    if not req.channel_id:
        raise HTTPException(status_code=400, detail="channel_id required")
    try:
        await db.execute(
            """INSERT OR REPLACE INTO blocked_channels (channel_id, channel_name, reason)
               VALUES (?, ?, ?)""",
            (req.channel_id, req.channel_name, req.reason)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"channel_id": req.channel_id, "blocked": True}


@router.delete("/{channel_id}")
async def unblock_channel(channel_id: str):
    """Channel wieder freischalten."""
    await db.execute("DELETE FROM blocked_channels WHERE channel_id = ?", (channel_id,))
    return {"channel_id": channel_id, "blocked": False}


async def get_blocked_ids() -> set[str]:
    """Set aller geblockten channel_ids – für Filter in search.py."""
    rows = await db.fetch_all("SELECT channel_id FROM blocked_channels")
    return {r["channel_id"] for r in rows}

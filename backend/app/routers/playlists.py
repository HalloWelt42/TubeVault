"""
TubeVault -  Playlists Router v1.3.0
© HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
"""

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.database import db

router = APIRouter(prefix="/api/playlists", tags=["Playlists (Lokal)"])


class PlaylistCreate(BaseModel):
    name: str
    description: Optional[str] = None


class PlaylistUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class PlaylistAddVideo(BaseModel):
    video_id: str
    # Optional: Metadaten für Stub-Erstellung (Video noch nicht heruntergeladen)
    title: Optional[str] = None
    channel_name: Optional[str] = None
    channel_id: Optional[str] = None


class PlaylistReorder(BaseModel):
    video_ids: list[str]


@router.get("")
async def get_playlists():
    """Alle Playlists abrufen (nur global sichtbare)."""
    rows = await db.fetch_all("""
        SELECT p.*,
               (SELECT COUNT(*) FROM playlist_videos pv2
                JOIN videos v2 ON v2.id = pv2.video_id AND v2.status = 'ready'
                WHERE pv2.playlist_id = p.id) as video_count,
               (SELECT SUM(v3.duration) FROM playlist_videos pv3
                JOIN videos v3 ON v3.id = pv3.video_id AND v3.status = 'ready'
                WHERE pv3.playlist_id = p.id) as total_duration,
               (SELECT pv2.video_id FROM playlist_videos pv2
                JOIN videos v ON v.id = pv2.video_id AND v.status = 'ready'
                WHERE pv2.playlist_id = p.id
                ORDER BY pv2.position LIMIT 1) as cover_video_id
        FROM playlists p
        WHERE COALESCE(p.visibility, 'global') = 'global'
        ORDER BY p.created_at DESC
    """)
    return [dict(r) for r in rows]


@router.post("")
async def create_playlist(data: PlaylistCreate):
    """Neue Playlist erstellen."""
    cursor = await db.execute(
        "INSERT INTO playlists (name, description) VALUES (?, ?)",
        (data.name, data.description)
    )
    return {"id": cursor.lastrowid, "name": data.name, "created": True}


@router.get("/{playlist_id}")
async def get_playlist(playlist_id: int):
    """Playlist mit allen Videos abrufen."""
    playlist = await db.fetch_one("SELECT * FROM playlists WHERE id = ?", (playlist_id,))
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist nicht gefunden")

    videos = await db.fetch_all("""
        SELECT v.*, pv.position
        FROM playlist_videos pv
        JOIN videos v ON v.id = pv.video_id AND v.status = 'ready'
        WHERE pv.playlist_id = ?
        ORDER BY pv.position ASC
    """, (playlist_id,))

    result = dict(playlist)
    result["videos"] = []
    for v in videos:
        vd = dict(v)
        if "tags" in vd and isinstance(vd["tags"], str):
            try:
                vd["tags"] = json.loads(vd["tags"])
            except (json.JSONDecodeError, TypeError):
                vd["tags"] = []
        vd.pop("ai_summary", None)
        vd.pop("ai_tags", None)
        result["videos"].append(vd)

    return result


@router.put("/{playlist_id}")
async def update_playlist(playlist_id: int, data: PlaylistUpdate):
    """Playlist aktualisieren."""
    updates = data.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Keine Änderungen")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [playlist_id]
    await db.execute(f"UPDATE playlists SET {set_clause} WHERE id = ?", values)
    return {"updated": True}


@router.delete("/{playlist_id}")
async def delete_playlist(playlist_id: int):
    """Playlist löschen."""
    await db.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
    return {"deleted": True}


@router.post("/{playlist_id}/videos")
async def add_video_to_playlist(playlist_id: int, data: PlaylistAddVideo):
    """Video zur Playlist hinzufügen."""
    # Playlist existiert?
    pl = await db.fetch_one("SELECT id FROM playlists WHERE id = ?", (playlist_id,))
    if not pl:
        raise HTTPException(status_code=404, detail="Playlist nicht gefunden")

    # Video existiert? Falls nicht → Stub erstellen (Vormerken)
    vid = await db.fetch_one("SELECT id FROM videos WHERE id = ?", (data.video_id,))
    if not vid:
        # Stub-Video anlegen (status='bookmarked')
        from app.utils.file_utils import now_sqlite
        await db.execute(
            """INSERT OR IGNORE INTO videos (id, title, channel_name, channel_id, status, source, created_at)
               VALUES (?, ?, ?, ?, 'bookmarked', 'playlist_bookmark', ?)""",
            (data.video_id, data.title or f"Video {data.video_id}",
             data.channel_name, data.channel_id, now_sqlite())
        )

    # Bereits in Playlist?
    existing = await db.fetch_one(
        "SELECT * FROM playlist_videos WHERE playlist_id = ? AND video_id = ?",
        (playlist_id, data.video_id)
    )
    if existing:
        raise HTTPException(status_code=409, detail="Video bereits in Playlist")

    # Position: ans Ende
    max_pos = await db.fetch_val(
        "SELECT COALESCE(MAX(position), -1) FROM playlist_videos WHERE playlist_id = ?",
        (playlist_id,)
    )
    await db.execute(
        "INSERT INTO playlist_videos (playlist_id, video_id, position) VALUES (?, ?, ?)",
        (playlist_id, data.video_id, max_pos + 1)
    )
    # video_count aktualisieren
    count = await db.fetch_val(
        "SELECT COUNT(*) FROM playlist_videos WHERE playlist_id = ?", (playlist_id,)
    )
    await db.execute(
        "UPDATE playlists SET video_count = ? WHERE id = ?", (count or 0, playlist_id)
    )
    return {"added": True, "position": max_pos + 1, "video_count": count or 0}


@router.delete("/{playlist_id}/videos/{video_id}")
async def remove_video_from_playlist(playlist_id: int, video_id: str):
    """Video aus Playlist entfernen."""
    await db.execute(
        "DELETE FROM playlist_videos WHERE playlist_id = ? AND video_id = ?",
        (playlist_id, video_id)
    )
    # video_count aktualisieren
    count = await db.fetch_val(
        "SELECT COUNT(*) FROM playlist_videos WHERE playlist_id = ?", (playlist_id,)
    )
    await db.execute(
        "UPDATE playlists SET video_count = ? WHERE id = ?", (count or 0, playlist_id)
    )
    return {"removed": True, "video_count": count or 0}


@router.put("/{playlist_id}/reorder")
async def reorder_playlist(playlist_id: int, data: PlaylistReorder):
    """Videos in Playlist neu ordnen."""
    for i, vid in enumerate(data.video_ids):
        await db.execute(
            "UPDATE playlist_videos SET position = ? WHERE playlist_id = ? AND video_id = ?",
            (i, playlist_id, vid)
        )
    return {"reordered": True, "count": len(data.video_ids)}

"""
TubeVault – Playlists Router v1.3.0
© HalloWelt42 – Private Nutzung
"""

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.database import db
from app.services import watch_state

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


class PlaylistFromVideos(BaseModel):
    name: str
    video_ids: list[str]


class PlaylistFromSeries(BaseModel):
    key: str


@router.get("/series-proposals")
async def series_proposals(min_episodes: int = Query(3, ge=2, le=50)):
    """Aus Folgennummern in den Titeln erkannte Serien (je Kanal und Serie)."""
    from app.services import series_detector
    found = await series_detector.proposals(min_episodes)
    return {"series": [
        {**s.model_dump(exclude={"episodes"}), "episode_count": len(s.episodes),
         "sample": [e.title for e in s.episodes[:3]]}
        for s in found
    ]}


@router.post("/from-series")
async def playlist_from_series(request: PlaylistFromSeries):
    """Erkannte Serie als Playlist anlegen oder auf Stand bringen."""
    from app.services import series_detector
    try:
        return await series_detector.create_playlist(request.key)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/from-videos")
async def playlist_from_videos(request: PlaylistFromVideos):
    """Playlist aus einer Videoliste anlegen (z.B. aus Suchtreffern)."""
    from app.services import series_detector
    name = request.name.strip()
    if not name or not request.video_ids:
        raise HTTPException(status_code=400, detail="Name und Videos angeben")
    playlist_id = await series_detector.save_playlist(name, request.video_ids[:2000])
    return {"playlist_id": playlist_id, "name": name, "video_count": len(set(request.video_ids[:2000]))}


@router.get("")
async def get_playlists():
    """Alle Playlists (nur global sichtbare) mit Kennzahlen je Playlist:
    Anzahl, Dauer, wie viele gesehen bzw. angefangen (watch_state), wann
    zuletzt etwas daraus lief, und die ersten drei Videos für das Bild."""
    state = watch_state.state_sql("v")
    rows = await db.fetch_all(f"""
        WITH inhalt AS (
            SELECT pv.playlist_id, pv.video_id, pv.position, v.duration, v.last_played, {state} AS stand
            FROM playlist_videos pv JOIN videos v ON v.id = pv.video_id AND v.status = 'ready'
        )
        SELECT p.id, p.name, p.description, p.source, p.source_url, p.source_id, p.thumbnail_path,
               p.channel_id, p.visibility, p.created_at,
               (SELECT COUNT(*) FROM inhalt i WHERE i.playlist_id = p.id) AS video_count,
               (SELECT SUM(i.duration) FROM inhalt i WHERE i.playlist_id = p.id) AS total_duration,
               (SELECT COUNT(*) FROM inhalt i WHERE i.playlist_id = p.id AND i.stand = 'finished') AS finished_count,
               (SELECT COUNT(*) FROM inhalt i WHERE i.playlist_id = p.id AND i.stand = 'started') AS started_count,
               (SELECT MAX(i.last_played) FROM inhalt i WHERE i.playlist_id = p.id) AS last_played,
               (SELECT GROUP_CONCAT(video_id) FROM (SELECT i.video_id FROM inhalt i WHERE i.playlist_id = p.id
                                                   ORDER BY i.position LIMIT 3)) AS cover_ids
        FROM playlists p
        WHERE COALESCE(p.visibility, 'global') = 'global'
        ORDER BY p.created_at DESC
    """)
    result = []
    for row in rows:
        item = dict(row)
        item["cover_ids"] = (item["cover_ids"] or "").split(",") if item["cover_ids"] else []
        item["cover_video_id"] = item["cover_ids"][0] if item["cover_ids"] else None
        result.append(item)
    return result


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


@router.post("/{playlist_id}/copy")
async def copy_playlist(playlist_id: int):
    """Kopie mit allen Videos in derselben Reihenfolge anlegen."""
    source = await db.fetch_one("SELECT name, description FROM playlists WHERE id = ?", (playlist_id,))
    if not source:
        raise HTTPException(status_code=404, detail="Playlist nicht gefunden")
    cursor = await db.execute("INSERT INTO playlists (name, description) VALUES (?, ?)",
                              (f"{source['name']} (Kopie)", source["description"]))
    new_id = cursor.lastrowid
    await db.execute(
        """INSERT INTO playlist_videos (playlist_id, video_id, position)
           SELECT ?, video_id, position FROM playlist_videos WHERE playlist_id = ?""", (new_id, playlist_id))
    count = await db.fetch_val("SELECT COUNT(*) FROM playlist_videos WHERE playlist_id = ?", (new_id,))
    await db.execute("UPDATE playlists SET video_count = ? WHERE id = ?", (count or 0, new_id))
    return {"id": new_id, "name": f"{source['name']} (Kopie)", "video_count": count or 0}


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

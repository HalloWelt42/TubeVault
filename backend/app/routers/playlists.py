"""
TubeVault – Playlists Router v1.3.0
© HalloWelt42 – Private Nutzung
"""

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator

from app.database import db
from app.services import drip, loadable, music_files, playlist_items, watch_state
from app.utils.file_utils import next_drip_run

router = APIRouter(prefix="/api/playlists", tags=["Playlists (Lokal)"])


class PlaylistCreate(BaseModel):
    name: str
    description: Optional[str] = None


class PlaylistUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    drip_enabled: Optional[bool] = None      # fehlende Videos nach und nach laden
    drip_count: Optional[int] = None         # je Lauf (einmal am Tag), siehe drip.PLAYLIST_DRIP_COUNTS

    @field_validator("name")
    @classmethod
    def _name_filled(cls, value: Optional[str]) -> Optional[str]:
        """Umbenennen ja, leer nein (gleich, was die Oberfläche schickt)."""
        if value is None:
            return None
        if not value.strip():
            raise ValueError("Der Name darf nicht leer sein")
        return value.strip()


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
               COALESCE(p.drip_enabled, 0) AS drip_enabled, COALESCE(p.drip_count, 3) AS drip_count, p.drip_next_run,
               (SELECT COUNT(*) FROM playlist_videos pv WHERE pv.playlist_id = p.id AND {loadable.condition("pv.video_id")}) AS pending_count,
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
    if "drip_count" in updates and updates["drip_count"] not in drip.PLAYLIST_DRIP_COUNTS:
        raise HTTPException(status_code=400, detail="Unbekannte Menge je Tag")
    if "drip_enabled" in updates:
        # Der erste Lauf kommt im nächsten nächtlichen Zeitfenster, wie bei Kanälen
        updates["drip_enabled"] = int(updates["drip_enabled"])
        updates["drip_next_run"] = next_drip_run() if updates["drip_enabled"] else None
        if updates["drip_enabled"]:
            updates["drip_completed_at"] = None

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [playlist_id]
    await db.execute(f"UPDATE playlists SET {set_clause} WHERE id = ?", values)
    return {"updated": True}


@router.post("/{playlist_id}/load-pending")
async def load_pending(playlist_id: int, limit: Optional[int] = Query(None, ge=1, le=500)):
    """Fehlende Videos der Playlist jetzt laden (ausdrücklich gewählt), wahlweise nur die nächsten limit."""
    if not await db.fetch_one("SELECT 1 FROM playlists WHERE id = ?", (playlist_id,)):
        raise HTTPException(status_code=404, detail="Playlist nicht gefunden")
    return {"queued": await drip.queue(await drip.pending(playlist_id, limit), origin="manual")}


@router.post("/{playlist_id}/copy")
async def copy_playlist(playlist_id: int):
    """Kopie mit allen Einträgen (Videos und Dateien der Sammlung) in derselben Reihenfolge anlegen."""
    source = await db.fetch_one("SELECT name, description FROM playlists WHERE id = ?", (playlist_id,))
    if not source:
        raise HTTPException(status_code=404, detail="Playlist nicht gefunden")
    cursor = await db.execute("INSERT INTO playlists (name, description) VALUES (?, ?)",
                              (f"{source['name']} (Kopie)", source["description"]))
    new_id = cursor.lastrowid
    await playlist_items.copy(playlist_id, new_id)
    count = await playlist_items.refresh_count(new_id)
    return {"id": new_id, "name": f"{source['name']} (Kopie)", "video_count": count}


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

    # Titel der eigenen Musiksammlung: nur, was die Sammlung kennt
    if music_files.is_file_id(data.video_id):
        if not await playlist_items.add(playlist_id, [data.video_id]):
            raise HTTPException(status_code=409, detail="Titel unbekannt oder bereits in der Playlist")
        return {"added": True, "video_count": await playlist_items.refresh_count(playlist_id)}

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

    # Position: ans Ende (hinter Videos und Dateien)
    position = await playlist_items.next_position(playlist_id)
    await db.execute(
        "INSERT INTO playlist_videos (playlist_id, video_id, position) VALUES (?, ?, ?)",
        (playlist_id, data.video_id, position)
    )
    count = await playlist_items.refresh_count(playlist_id)
    return {"added": True, "position": position, "video_count": count}


@router.delete("/{playlist_id}/videos/{video_id}")
async def remove_video_from_playlist(playlist_id: int, video_id: str):
    """Video (oder Titel der Sammlung) aus Playlist entfernen."""
    await playlist_items.remove(playlist_id, video_id)
    return {"removed": True, "video_count": await playlist_items.refresh_count(playlist_id)}


@router.put("/{playlist_id}/reorder")
async def reorder_playlist(playlist_id: int, data: PlaylistReorder):
    """Einträge der Playlist neu ordnen (Videos und Dateien gemeinsam)."""
    await playlist_items.reorder(playlist_id, data.video_ids)
    return {"reordered": True, "count": len(data.video_ids)}

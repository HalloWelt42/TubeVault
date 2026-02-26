"""
TubeVault -  Favorites Router v1.0.0
© HalloWelt42 -  Private Nutzung
"""

from fastapi import APIRouter, HTTPException
from app.models.category import FavoriteCreate, FavoriteResponse, FavoriteListResponse
from app.database import db

router = APIRouter(prefix="/api/favorites", tags=["Favoriten"])


@router.get("")
async def get_favorites(list_name: str = None):
    """Alle Favoriten abrufen (optional nach Liste filtern)."""
    if list_name:
        rows = await db.fetch_all(
            """SELECT f.id as fav_id, f.video_id as id, f.list_name, f.position, f.added_at,
                      v.title, v.channel_name, v.duration, v.thumbnail_path, v.status,
                      v.file_size, v.view_count, v.download_date, v.upload_date
               FROM favorites f
               JOIN videos v ON f.video_id = v.id
               WHERE f.list_name = ?
               ORDER BY f.position ASC""",
            (list_name,)
        )
    else:
        rows = await db.fetch_all(
            """SELECT f.id as fav_id, f.video_id as id, f.list_name, f.position, f.added_at,
                      v.title, v.channel_name, v.duration, v.thumbnail_path, v.status,
                      v.file_size, v.view_count, v.download_date, v.upload_date
               FROM favorites f
               JOIN videos v ON f.video_id = v.id
               ORDER BY f.list_name, f.position ASC"""
        )
    return [dict(r) for r in rows]


@router.get("/lists")
async def get_favorite_lists():
    """Alle Favoritenlisten abrufen."""
    rows = await db.fetch_all(
        "SELECT list_name, COUNT(*) as count FROM favorites GROUP BY list_name ORDER BY list_name"
    )
    return [{"name": r["list_name"], "count": r["count"]} for r in rows]


@router.post("")
async def add_favorite(fav: FavoriteCreate):
    """Video zu Favoriten hinzufügen."""
    # Prüfen ob Video existiert
    video = await db.fetch_one("SELECT id FROM videos WHERE id = ?", (fav.video_id,))
    if not video:
        raise HTTPException(status_code=404, detail="Video nicht gefunden")

    # Duplikat-Check
    existing = await db.fetch_one(
        "SELECT id FROM favorites WHERE video_id = ? AND list_name = ?",
        (fav.video_id, fav.list_name)
    )
    if existing:
        raise HTTPException(status_code=409, detail="Video ist bereits in dieser Liste")

    # Nächste Position
    max_pos = await db.fetch_val(
        "SELECT COALESCE(MAX(position), -1) FROM favorites WHERE list_name = ?",
        (fav.list_name,)
    )

    cursor = await db.execute(
        "INSERT INTO favorites (video_id, list_name, position) VALUES (?, ?, ?)",
        (fav.video_id, fav.list_name, max_pos + 1)
    )
    return {"id": cursor.lastrowid, "video_id": fav.video_id, "list_name": fav.list_name}


@router.delete("/{favorite_id}")
async def remove_favorite(favorite_id: int):
    """Favorit entfernen."""
    await db.execute("DELETE FROM favorites WHERE id = ?", (favorite_id,))
    return {"deleted": True}


@router.delete("/video/{video_id}")
async def remove_favorite_by_video(video_id: str, list_name: str = None):
    """Video aus Favoriten entfernen (optional nach Liste)."""
    if list_name:
        await db.execute(
            "DELETE FROM favorites WHERE video_id = ? AND list_name = ?",
            (video_id, list_name)
        )
    else:
        await db.execute("DELETE FROM favorites WHERE video_id = ?", (video_id,))
    return {"deleted": True, "video_id": video_id}


@router.put("/reorder")
async def reorder_favorites(list_name: str, video_ids: list[str]):
    """Favoriten-Reihenfolge ändern."""
    for pos, vid in enumerate(video_ids):
        await db.execute(
            "UPDATE favorites SET position = ? WHERE video_id = ? AND list_name = ?",
            (pos, vid, list_name)
        )
    return {"reordered": True, "count": len(video_ids)}


@router.post("/lists")
async def create_favorite_list(name: str):
    """Neue Favoritenliste erstellen (implizit beim ersten Hinzufügen)."""
    return {"name": name, "count": 0}


@router.get("/check/{video_id}")
async def check_favorite(video_id: str):
    """Prüfen ob Video in irgendeiner Favoritenliste ist."""
    rows = await db.fetch_all(
        "SELECT list_name FROM favorites WHERE video_id = ?", (video_id,)
    )
    return {
        "is_favorite": len(rows) > 0,
        "lists": [r["list_name"] for r in rows],
    }

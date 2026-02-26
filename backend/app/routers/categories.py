"""
TubeVault – Categories Router v1.5.85
Vollständige Kategorie-Verwaltung mit korrekten Zählungen.
Alle Video-Queries filtern auf status='ready'.
© HalloWelt42 – Private Nutzung
"""

from fastapi import APIRouter, HTTPException, Query
from app.models.category import CategoryCreate, CategoryUpdate, CategoryResponse
from app.database import db

router = APIRouter(prefix="/api/categories", tags=["Kategorien"])

# ─── Hilfs-Query: video_count nur für fertige, nicht-archivierte Videos ───
_COUNT_SUBQUERY = """(
    SELECT COUNT(*) FROM video_categories vc
    JOIN videos v ON v.id = vc.video_id AND v.status = 'ready' AND COALESCE(v.is_archived, 0) = 0
    WHERE vc.category_id = c.id
)"""


@router.get("")
async def get_categories():
    """Alle Kategorien als flache Liste (video_count nur fertige, nicht-archivierte Videos)."""
    rows = await db.fetch_all(
        f"""SELECT c.*, {_COUNT_SUBQUERY} as video_count
            FROM categories c
            ORDER BY c.sort_order, c.name"""
    )
    return [dict(r) for r in rows]


@router.get("/flat")
async def get_categories_flat():
    """Alle Kategorien als flache Liste (video_count nur fertige Videos)."""
    rows = await db.fetch_all(
        f"""SELECT c.*, {_COUNT_SUBQUERY} as video_count
            FROM categories c
            ORDER BY c.sort_order, c.name"""
    )
    return [dict(r) for r in rows]


# ─── Stats-Route VOR /{category_id} um Konflikte zu vermeiden ───

@router.get("/stats/unassigned")
async def unassigned_videos_stats():
    """Statistik: Wie viele fertige Videos haben keine Kategorie?"""
    total = await db.fetch_val(
        "SELECT COUNT(*) FROM videos WHERE status = 'ready'"
    ) or 0
    assigned = await db.fetch_val(
        """SELECT COUNT(DISTINCT vc.video_id) FROM video_categories vc
           JOIN videos v ON v.id = vc.video_id AND v.status = 'ready'"""
    ) or 0
    # Top Kanäle ohne Kategorien
    channels = await db.fetch_all(
        """SELECT v.channel_name, COUNT(*) as count
           FROM videos v
           WHERE v.status = 'ready'
           AND v.id NOT IN (SELECT video_id FROM video_categories)
           AND v.channel_name IS NOT NULL AND v.channel_name != ''
           GROUP BY v.channel_name ORDER BY count DESC LIMIT 10"""
    )
    return {
        "total": total,
        "assigned": assigned,
        "unassigned": total - assigned,
        "top_unassigned_channels": [
            {"name": c["channel_name"], "count": c["count"]} for c in channels
        ],
    }


@router.post("")
async def create_category(cat: CategoryCreate):
    """Neue Kategorie erstellen (flach, keine Hierarchie)."""
    existing = await db.fetch_one(
        "SELECT id FROM categories WHERE name = ?",
        (cat.name,)
    )
    if existing:
        raise HTTPException(status_code=409, detail="Kategorie existiert bereits")

    cursor = await db.execute(
        """INSERT INTO categories (name, description, color, icon, sort_order)
           VALUES (?, ?, ?, ?, ?)""",
        (cat.name, cat.description, cat.color, cat.icon, cat.sort_order)
    )
    return {"id": cursor.lastrowid, "name": cat.name}


@router.put("/{category_id}")
async def update_category(category_id: int, updates: CategoryUpdate):
    """Kategorie bearbeiten."""
    existing = await db.fetch_one("SELECT id FROM categories WHERE id = ?", (category_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Kategorie nicht gefunden")

    fields = {k: v for k, v in updates.model_dump().items() if v is not None}
    if not fields:
        return {"id": category_id, "updated": False}

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [category_id]
    await db.execute(f"UPDATE categories SET {set_clause} WHERE id = ?", values)
    return {"id": category_id, "updated": True}


@router.delete("/{category_id}")
async def delete_category(category_id: int):
    """Kategorie löschen (Zuordnungen werden explizit entfernt)."""
    await db.execute("DELETE FROM video_categories WHERE category_id = ?", (category_id,))
    await db.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    return {"deleted": True}


@router.get("/{category_id}/videos")
async def get_category_videos(
    category_id: int,
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    search: str = Query(None),
):
    """Videos einer Kategorie abrufen (nur status='ready')."""
    # Sortierung absichern
    allowed_sort = {"created_at", "title", "channel_name", "duration", "file_size", "rating", "download_date"}
    if sort_by not in allowed_sort:
        sort_by = "created_at"
    if sort_order not in ("asc", "desc"):
        sort_order = "desc"

    conditions = ["vc.category_id = ?", "v.status = 'ready'"]
    params = [category_id]

    if search:
        conditions.append("(v.title LIKE ? OR v.channel_name LIKE ?)")
        term = f"%{search}%"
        params.extend([term, term])

    where = " AND ".join(conditions)
    rows = await db.fetch_all(
        f"""SELECT v.* FROM videos v
            JOIN video_categories vc ON v.id = vc.video_id
            WHERE {where}
            ORDER BY v.{sort_by} {sort_order}""",
        tuple(params)
    )
    return [dict(r) for r in rows]


# ─── Video <-> Kategorie Zuordnungen ───

@router.post("/videos/{video_id}")
async def assign_categories(video_id: str, category_ids: list[int]):
    """Video Kategorien zuordnen (ersetzt bestehende)."""
    video = await db.fetch_one(
        "SELECT id FROM videos WHERE id = ? AND status = 'ready'", (video_id,)
    )
    if not video:
        raise HTTPException(status_code=404, detail="Video nicht gefunden oder nicht bereit")

    await db.execute("DELETE FROM video_categories WHERE video_id = ?", (video_id,))
    for cat_id in category_ids:
        await db.execute(
            "INSERT OR IGNORE INTO video_categories (video_id, category_id) VALUES (?, ?)",
            (video_id, cat_id)
        )
    return {"video_id": video_id, "categories": category_ids}


@router.get("/videos/{video_id}")
async def get_video_categories(video_id: str):
    """Kategorien eines Videos abrufen."""
    rows = await db.fetch_all(
        """SELECT c.* FROM categories c
           JOIN video_categories vc ON c.id = vc.category_id
           WHERE vc.video_id = ?
           ORDER BY c.sort_order, c.name""",
        (video_id,)
    )
    return [dict(r) for r in rows]


@router.post("/{category_id}/auto-assign")
async def auto_assign_category(category_id: int, channel: str = None, keyword: str = None):
    """Fertige Videos automatisch einer Kategorie zuordnen."""
    if not channel and not keyword:
        raise HTTPException(status_code=400, detail="channel oder keyword erforderlich")

    cat = await db.fetch_one("SELECT id FROM categories WHERE id = ?", (category_id,))
    if not cat:
        raise HTTPException(status_code=404, detail="Kategorie nicht gefunden")

    conditions = ["v.status = 'ready'"]
    params = []
    if channel:
        conditions.append("v.channel_name LIKE ?")
        params.append(f"%{channel}%")
    if keyword:
        conditions.append("(v.title LIKE ? OR v.tags LIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])

    where = " AND ".join(conditions)
    rows = await db.fetch_all(
        f"""SELECT v.id FROM videos v
            WHERE {where}
            AND v.id NOT IN (SELECT video_id FROM video_categories WHERE category_id = ?)""",
        tuple(params) + (category_id,)
    )

    count = 0
    for r in rows:
        await db.execute(
            "INSERT OR IGNORE INTO video_categories (video_id, category_id) VALUES (?, ?)",
            (r["id"], category_id)
        )
        count += 1

    return {"assigned": count, "category_id": category_id}


# ─── Aufräumen ───

@router.post("/cleanup-orphans")
async def cleanup_orphaned_assignments():
    """Verwaiste Zuordnungen entfernen (Videos die nicht mehr existieren oder nicht ready sind)."""
    cursor = await db.execute(
        """DELETE FROM video_categories
           WHERE video_id NOT IN (SELECT id FROM videos WHERE status = 'ready')"""
    )
    return {"cleaned": cursor.rowcount}


@router.get("/stats/debug")
async def category_debug_stats():
    """Diagnose: Zuordnungen und Zähler prüfen."""
    total_assignments = await db.fetch_val("SELECT COUNT(*) FROM video_categories")
    total_ready = await db.fetch_val("SELECT COUNT(*) FROM videos WHERE status = 'ready'")
    assigned_ready = await db.fetch_val(
        """SELECT COUNT(DISTINCT vc.video_id) FROM video_categories vc
           JOIN videos v ON v.id = vc.video_id AND v.status = 'ready'"""
    )
    orphan_count = await db.fetch_val(
        """SELECT COUNT(*) FROM video_categories
           WHERE video_id NOT IN (SELECT id FROM videos WHERE status = 'ready')"""
    )
    per_cat = await db.fetch_all(
        """SELECT c.id, c.name,
              (SELECT COUNT(*) FROM video_categories vc WHERE vc.category_id = c.id) as total,
              (SELECT COUNT(*) FROM video_categories vc
               JOIN videos v ON v.id = vc.video_id AND v.status = 'ready'
               WHERE vc.category_id = c.id) as ready
           FROM categories c ORDER BY c.name"""
    )
    return {
        "total_assignments": total_assignments,
        "total_ready_videos": total_ready,
        "assigned_ready_videos": assigned_ready,
        "orphan_assignments": orphan_count,
        "per_category": [dict(r) for r in per_cat],
    }


# ─── Quick-Assign: Kanal → Kategorie in einem Schritt ───

CHANNEL_COLORS = [
    "#E53935", "#D81B60", "#8E24AA", "#5E35B1", "#3949AB",
    "#1E88E5", "#039BE5", "#00ACC1", "#00897B", "#43A047",
    "#7CB342", "#C0CA33", "#FDD835", "#FFB300", "#FB8C00",
    "#F4511E", "#6D4C41", "#78909C", "#546E7A",
]


@router.post("/quick-channel-assign")
async def quick_channel_assign(channel_name: str, category_id: int = None):
    """Alle Videos eines Kanals einer Kategorie zuordnen.
    Ohne category_id: Erstellt automatisch eine Kategorie mit dem Kanalnamen.
    """
    if not channel_name or not channel_name.strip():
        raise HTTPException(status_code=400, detail="channel_name erforderlich")

    channel_name = channel_name.strip()

    if category_id:
        cat = await db.fetch_one("SELECT id, name FROM categories WHERE id = ?", (category_id,))
        if not cat:
            raise HTTPException(status_code=404, detail="Kategorie nicht gefunden")
        cat_id = cat["id"]
        cat_name = cat["name"]
    else:
        existing = await db.fetch_one("SELECT id, name FROM categories WHERE name = ?", (channel_name,))
        if existing:
            cat_id = existing["id"]
            cat_name = existing["name"]
        else:
            import random
            color = random.choice(CHANNEL_COLORS)
            cursor = await db.execute(
                "INSERT INTO categories (name, description, color) VALUES (?, ?, ?)",
                (channel_name, f"Videos von {channel_name}", color)
            )
            cat_id = cursor.lastrowid
            cat_name = channel_name

    rows = await db.fetch_all(
        """SELECT v.id FROM videos v
           WHERE v.status = 'ready' AND v.channel_name = ?
           AND v.id NOT IN (SELECT video_id FROM video_categories WHERE category_id = ?)""",
        (channel_name, cat_id)
    )

    count = 0
    for r in rows:
        await db.execute(
            "INSERT OR IGNORE INTO video_categories (video_id, category_id) VALUES (?, ?)",
            (r["id"], cat_id)
        )
        count += 1

    return {"category_id": cat_id, "category_name": cat_name, "assigned": count, "created": not bool(category_id and True)}


@router.post("/quick-channel-assign-all")
async def quick_channel_assign_all():
    """Alle unkategorisierten Videos automatisch nach Kanal-Namen gruppieren."""
    channels = await db.fetch_all(
        """SELECT DISTINCT v.channel_name, COUNT(*) as cnt
           FROM videos v
           WHERE v.status = 'ready'
           AND v.id NOT IN (SELECT video_id FROM video_categories)
           AND v.channel_name IS NOT NULL AND v.channel_name != ''
           GROUP BY v.channel_name ORDER BY cnt DESC"""
    )

    total_assigned = 0
    categories_created = 0

    for ch in channels:
        name = ch["channel_name"]
        existing = await db.fetch_one("SELECT id FROM categories WHERE name = ?", (name,))
        if existing:
            cat_id = existing["id"]
        else:
            import random
            color = random.choice(CHANNEL_COLORS)
            cursor = await db.execute(
                "INSERT INTO categories (name, description, color) VALUES (?, ?, ?)",
                (name, f"Videos von {name}", color)
            )
            cat_id = cursor.lastrowid
            categories_created += 1

        rows = await db.fetch_all(
            """SELECT id FROM videos
               WHERE status = 'ready' AND channel_name = ?
               AND id NOT IN (SELECT video_id FROM video_categories WHERE category_id = ?)""",
            (name, cat_id)
        )
        for r in rows:
            await db.execute(
                "INSERT OR IGNORE INTO video_categories (video_id, category_id) VALUES (?, ?)",
                (r["id"], cat_id)
            )
            total_assigned += 1

    return {"assigned": total_assigned, "categories_created": categories_created}


# ─── Hilfsfunktionen ───

def _build_tree(categories: list[dict]) -> list[dict]:
    """Flache Liste in Baumstruktur konvertieren."""
    by_id = {c["id"]: {**c, "children": []} for c in categories}
    tree = []
    for cat in categories:
        if cat["parent_id"] and cat["parent_id"] in by_id:
            by_id[cat["parent_id"]]["children"].append(by_id[cat["id"]])
        else:
            tree.append(by_id[cat["id"]])
    return tree

"""
Gemerkte Suchen: Suchtext samt Filtern unter einem Namen. Neu ist, was seit
dem letzten Öffnen dazukam - geladene Videos (download_date) und Feed-Einträge
(created_at) nach seen_at. Gezählt wird beim Abfragen, nicht im Hintergrund:
es sind wenige Suchen, und so stimmt die Zahl immer.
"""
import uuid
from typing import Optional

from pydantic import BaseModel

from app.database import db
from app.services.search import engine
from app.services.search.filters import SearchFilters

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS saved_searches (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    query TEXT NOT NULL,
    filters TEXT NOT NULL DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    seen_at TEXT DEFAULT (datetime('now'))
);
"""
MAX_NAME = 80


class SavedSearch(BaseModel):
    id: str
    name: str
    query: str
    filters: SearchFilters
    created_at: Optional[str] = None
    seen_at: Optional[str] = None
    new_videos: int = 0
    new_feed: int = 0


class SavedSearchInput(BaseModel):
    name: Optional[str] = None
    query: str
    filters: SearchFilters = SearchFilters()


async def install_schema(connection) -> None:
    await connection.executescript(SCHEMA_SQL)
    await connection.commit()


def _clean_name(name: Optional[str], query: str) -> str:
    text = " ".join((name or query).split())
    return text[:MAX_NAME] or "Suche"


async def _with_counts(row) -> SavedSearch:
    filters = SearchFilters.model_validate_json(row["filters"] or "{}")
    videos, feed = await engine.new_counts(row["query"], filters, since=row["seen_at"])
    return SavedSearch(id=row["id"], name=row["name"], query=row["query"], filters=filters,
                       created_at=row["created_at"], seen_at=row["seen_at"], new_videos=videos, new_feed=feed)


async def all_saved() -> list[SavedSearch]:
    rows = await db.fetch_all("SELECT * FROM saved_searches ORDER BY name COLLATE NOCASE")
    return [await _with_counts(row) for row in rows]


async def create(data: SavedSearchInput) -> SavedSearch:
    query = " ".join(data.query.split())
    if not query:
        raise ValueError("Ohne Suchtext lässt sich nichts merken")
    saved_id = str(uuid.uuid4())
    filters = data.filters.model_copy(update={"since": None})
    await db.execute(
        "INSERT INTO saved_searches (id, name, query, filters) VALUES (?, ?, ?, ?)",
        (saved_id, _clean_name(data.name, query), query, filters.model_dump_json()))
    return await _with_counts(await db.fetch_one("SELECT * FROM saved_searches WHERE id = ?", (saved_id,)))


async def rename(saved_id: str, name: str) -> bool:
    row = await db.fetch_one("SELECT query FROM saved_searches WHERE id = ?", (saved_id,))
    if not row:
        return False
    await db.execute("UPDATE saved_searches SET name = ? WHERE id = ?", (_clean_name(name, row["query"]), saved_id))
    return True


async def mark_seen(saved_id: str) -> bool:
    cursor = await db.execute("UPDATE saved_searches SET seen_at = datetime('now') WHERE id = ?", (saved_id,))
    return cursor.rowcount == 1


async def delete(saved_id: str) -> bool:
    cursor = await db.execute("DELETE FROM saved_searches WHERE id = ?", (saved_id,))
    return cursor.rowcount == 1

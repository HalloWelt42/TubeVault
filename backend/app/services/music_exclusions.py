"""
TubeVault – Ausgeschlossene Gruppen der Musik

Ganze Alben lassen sich aus der Musik ausschließen (Wunsch 16.10.2026): ihre
Titel fallen aus allen Listen, Mixen, Interpreten und der Suche, Dateien wie
Videos. Gemerkt wird die Gruppe, nicht die einzelnen Titel - was später zum
Album hinzukommt, bleibt ebenso draußen. Zurückholen geht im Bereich
"Ausgeblendet" der Musikseite, zusammen mit den ausgeblendeten Dateien.

Eine Gruppe heißt hier wie überall in der Musik, z.B. "album:cover:<prüfsumme>",
"album:ordner:<prüfsumme>" oder "album:abba|gold" (music_library.Track.album_source).
Wechselt der Schlüssel eines Albums der Sammlung, weil es gewachsen ist, führt
music_albums.resolve den gemerkten zum heutigen; das Album bleibt draußen. Name
und Unterzeile werden beim Ausschließen festgehalten, damit die Liste sie auch
ohne die Titel zeigen kann.
"""
from typing import Optional

from pydantic import BaseModel

from app.database import db

KINDS = ("album",)                    # was sich ausschließen lässt

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS music_exclusions (
    source TEXT PRIMARY KEY,          -- Gruppe wie in der Musik, z.B. album:<schlüssel>
    name TEXT NOT NULL,               -- Anzeige, festgehalten beim Ausschließen
    subtitle TEXT,
    count INTEGER DEFAULT 0,          -- so viele Titel hatte die Gruppe da
    excluded_at TEXT DEFAULT (datetime('now'))
);
"""


class Exclusion(BaseModel):
    source: str
    name: str
    subtitle: Optional[str] = None
    count: int = 0
    excluded_at: Optional[str] = None


async def install_schema(connection) -> None:
    await connection.executescript(SCHEMA_SQL)
    await connection.commit()


def allowed(source: str) -> bool:
    kind, _, value = source.partition(":")
    return kind in KINDS and bool(value)


async def sources() -> set[str]:
    return {row["source"] for row in await db.fetch_all("SELECT source FROM music_exclusions")}


async def listing() -> list[Exclusion]:
    """Ausgeschlossene Gruppen, zuletzt ausgeschlossene zuerst."""
    rows = await db.fetch_all("SELECT * FROM music_exclusions ORDER BY excluded_at DESC, name")
    return [Exclusion(**dict(row)) for row in rows]


async def exclude(source: str, name: str, subtitle: Optional[str], count: int) -> None:
    await db.execute(
        """INSERT INTO music_exclusions (source, name, subtitle, count) VALUES (?, ?, ?, ?)
           ON CONFLICT(source) DO UPDATE SET name = excluded.name, subtitle = excluded.subtitle,
                                             count = excluded.count, excluded_at = datetime('now')""",
        (source, name, subtitle, count))


async def restore(chosen: list[str]) -> int:
    if not chosen:
        return 0
    marks = ",".join("?" * len(chosen))
    cursor = await db.execute(f"DELETE FROM music_exclusions WHERE source IN ({marks})", chosen)
    return cursor.rowcount


async def total() -> int:
    return await db.fetch_val("SELECT COUNT(*) FROM music_exclusions") or 0

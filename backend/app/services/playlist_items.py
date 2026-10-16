"""
TubeVault – Einträge einer Wiedergabeliste: Videos und Dateien der Sammlung

Eine Wiedergabeliste hält Videos (playlist_videos, an videos gebunden) und
seit 16.10.2026 auch Titel der eigenen Musiksammlung (playlist_files): so
lassen sich Musiklisten aus allem bauen, was die Musik kennt. Beide Tabellen
teilen sich die Positionen einer Liste; diese eine Stelle liest, ergänzt,
entfernt und ordnet sie gemeinsam.

Dateien sind nicht fest an music_files gebunden: ist die Sammlung kurz nicht
eingehängt, fallen Einträge nicht weg, sie fehlen nur beim Abspielen.
"""
from app.database import db
from app.services import music_files

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS playlist_files (
    playlist_id INTEGER NOT NULL,
    file_id TEXT NOT NULL,            -- music_files.id ('f' + Prüfsumme des Pfads)
    position INTEGER DEFAULT 0,
    PRIMARY KEY (playlist_id, file_id),
    FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE
);
"""

_ENTRIES_SQL = """SELECT video_id AS id, position FROM playlist_videos WHERE playlist_id = ?
                  UNION ALL
                  SELECT file_id AS id, position FROM playlist_files WHERE playlist_id = ?
                  ORDER BY position, id"""


async def install_schema(connection) -> None:
    await connection.executescript(SCHEMA_SQL)
    await connection.commit()


def _table(item_id: str) -> tuple[str, str]:
    return ("playlist_files", "file_id") if music_files.is_file_id(item_id) else ("playlist_videos", "video_id")


async def entries(playlist_id: int) -> list[str]:
    """Kennungen der Liste in ihrer Reihenfolge (Videos und Dateien gemischt)."""
    return [row["id"] for row in await db.fetch_all(_ENTRIES_SQL, (playlist_id, playlist_id))]


async def next_position(playlist_id: int) -> int:
    """Stelle hinter dem letzten Eintrag (Positionen dürfen Lücken haben)."""
    last = await db.fetch_val(
        """SELECT MAX(position) FROM (SELECT position FROM playlist_videos WHERE playlist_id = ?
                                      UNION ALL SELECT position FROM playlist_files WHERE playlist_id = ?)""",
        (playlist_id, playlist_id))
    return 0 if last is None else last + 1


async def _renumber(playlist_id: int, ids: list[str]) -> None:
    for position, item_id in enumerate(ids):
        table, column = _table(item_id)
        await db.conn.execute(f"UPDATE {table} SET position = ? WHERE playlist_id = ? AND {column} = ?",
                              (position, playlist_id, item_id))


async def refresh_count(playlist_id: int) -> int:
    count = await db.fetch_val(
        """SELECT (SELECT COUNT(*) FROM playlist_videos WHERE playlist_id = ?)
                + (SELECT COUNT(*) FROM playlist_files WHERE playlist_id = ?)""", (playlist_id, playlist_id)) or 0
    await db.execute("UPDATE playlists SET video_count = ? WHERE id = ?", (count, playlist_id))
    return count


async def add(playlist_id: int, item_ids: list[str]) -> int:
    """Titel ans Ende anfügen; schon enthaltene und unbekannte bleiben
    draußen. Liefert, wie viele dazukamen (die Stelle setzt reorder)."""
    current = await entries(playlist_id)
    have = set(current)
    fresh = []
    for item_id in dict.fromkeys(item_ids):
        if item_id in have:
            continue
        if music_files.is_file_id(item_id):
            known = await db.fetch_val("SELECT 1 FROM music_files WHERE id = ?", (item_id,))
        else:
            known = await db.fetch_val("SELECT 1 FROM videos WHERE id = ?", (item_id,))
        if known:
            fresh.append(item_id)
    if not fresh:
        return 0
    for item_id in fresh:
        table, column = _table(item_id)
        await db.conn.execute(f"INSERT INTO {table} (playlist_id, {column}, position) VALUES (?, ?, 0)",
                              (playlist_id, item_id))
    await _renumber(playlist_id, current + fresh)
    await db.conn.commit()
    await refresh_count(playlist_id)
    return len(fresh)


async def remove(playlist_id: int, item_id: str) -> bool:
    table, column = _table(item_id)
    cursor = await db.execute(f"DELETE FROM {table} WHERE playlist_id = ? AND {column} = ?", (playlist_id, item_id))
    await refresh_count(playlist_id)
    return cursor.rowcount > 0


async def reorder(playlist_id: int, item_ids: list[str]) -> None:
    """Neue Reihenfolge; Einträge, die item_ids nicht nennt, kommen dahinter."""
    current = await entries(playlist_id)
    known = set(current)
    ordered = [i for i in dict.fromkeys(item_ids) if i in known]
    rest = [i for i in current if i not in set(ordered)]
    await _renumber(playlist_id, ordered + rest)
    await db.conn.commit()


async def copy(source_id: int, target_id: int) -> None:
    """Alle Einträge einer Liste in eine andere (gleiche Reihenfolge)."""
    for table, column in (("playlist_videos", "video_id"), ("playlist_files", "file_id")):
        await db.conn.execute(
            f"""INSERT OR IGNORE INTO {table} (playlist_id, {column}, position)
                SELECT ?, {column}, position FROM {table} WHERE playlist_id = ?""", (target_id, source_id))
    await db.conn.commit()
    await refresh_count(target_id)

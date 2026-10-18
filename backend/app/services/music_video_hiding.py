"""
TubeVault – Videos aus der Musik abwählen

Der Minus-Knopf nimmt einen Titel aus der ganzen Musik (Wunsch 19.10.2026):
Warteschlange, Wiedergabelisten, Lieblingssongs, Alben, Interpreten, Kanäle,
als Musik gespielte Sammlungen, Suche, Mixe und Zähler. Gelöscht wird nichts.
Dateien der Sammlung tragen das als music_files.hidden, Videos hier als
videos.music_hidden - die Videobibliothek außerhalb der Musik bleibt
unberührt. Zurückholen geht im Bereich "Ausgeblendet", einzeln oder mehrere.

Durchgesetzt wird es an einer Stelle: music_library.TRACK_SQL, aus der jede
Musikliste ihre Videos liest.
"""
from app.database import db

VISIBLE = "COALESCE(v.music_hidden, 0) = 0"     # Bedingung über videos v
HIDDEN = "COALESCE(v.music_hidden, 0) = 1"


async def install_schema(connection) -> None:
    for column in ("music_hidden INTEGER DEFAULT 0", "music_hidden_at TEXT"):
        try:
            await connection.execute(f"ALTER TABLE videos ADD COLUMN {column}")
        except Exception:
            pass  # Spalte existiert bereits
    await connection.commit()


async def set_hidden(video_id: str, hidden: bool) -> bool:
    """Abwählen oder zurückholen; das Video selbst bleibt unberührt."""
    cursor = await db.execute(
        "UPDATE videos SET music_hidden = ?, music_hidden_at = CASE WHEN ? THEN datetime('now') END WHERE id = ?",
        (int(hidden), int(hidden), video_id))
    return cursor.rowcount == 1


async def show_again(video_ids: list[str]) -> int:
    """Mehrere abgewählte Videos auf einmal zurückholen."""
    if not video_ids:
        return 0
    marks = ",".join("?" * len(video_ids))
    cursor = await db.execute(
        f"UPDATE videos SET music_hidden = 0, music_hidden_at = NULL WHERE music_hidden = 1 AND id IN ({marks})", video_ids)
    return cursor.rowcount


async def hidden_count() -> int:
    """Abgewählte Videos, die die Musik sonst zeigen könnte (geladen)."""
    return await db.fetch_val(f"SELECT COUNT(*) FROM videos v WHERE v.status = 'ready' AND {HIDDEN}") or 0

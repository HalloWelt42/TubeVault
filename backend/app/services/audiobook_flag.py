"""
TubeVault – Hörbuch oder nicht (Videos)

Hörbücher und Hörspiele gibt es auch als Videos (Wunsch 15.10.2026). Sie sind
keine Musik: Sie kommen nie in Musiklisten oder Mixe, sondern in den eigenen
Bereich Hörbücher (audiobooks), in ihrer Reihenfolge.

videos.is_audiobook und seine Herkunft videos.audiobook_source:
  'user'  vom Nutzer festgelegt - die Automatik ändert das nie
  'auto'  eindeutig erkannt: Titel oder Schlagwort nennt Hörbuch, Hörspiel,
          Audiobook. Die Beschreibung zählt nicht - dort steht oft Werbung
          ("Hörbuch gratis bei ...").
Für Dateien der eigenen Sammlung entscheidet music_files.category.
"""
import json
import re
from typing import Iterable, Optional

from app.database import db

USER = "user"
AUTO = "auto"

_MARKERS = re.compile(r"(?<!\w)(hörbuch|hörbücher|hörspiel|hörspiele|hoerbuch|hoerspiel|audiobook|audio book)(?!\w)",
                      re.IGNORECASE)


def is_certainly_audiobook(title: Optional[str], tags) -> bool:
    if _MARKERS.search(title or ""):
        return True
    try:
        tag_list = json.loads(tags) if isinstance(tags, str) else (tags or [])
    except (ValueError, TypeError):
        tag_list = []
    return any(_MARKERS.search(str(tag)) for tag in tag_list)


async def install_schema(connection) -> None:
    for column in ("is_audiobook INTEGER DEFAULT 0", "audiobook_source TEXT"):
        try:
            await connection.execute(f"ALTER TABLE videos ADD COLUMN {column}")
        except Exception:
            pass  # Spalte existiert bereits
    await connection.commit()


async def apply_auto(video_id: str, title: Optional[str], tags) -> None:
    """Nach dem Laden: eindeutig Erkanntes kennzeichnen, die Nutzerwahl bleibt."""
    if is_certainly_audiobook(title, tags):
        await db.execute(
            """UPDATE videos SET is_audiobook = 1, audiobook_source = ?
               WHERE id = ? AND COALESCE(audiobook_source, '') <> ?""", (AUTO, video_id, USER))


async def backfill(connection) -> int:
    """Bestand einmal durchsehen (Migration); liefert die Zahl der erkannten."""
    rows = await (await connection.execute(
        "SELECT id, title, tags FROM videos WHERE COALESCE(audiobook_source, '') <> ?", (USER,))).fetchall()
    found = [row[0] for row in rows if is_certainly_audiobook(row[1], row[2])]
    for video_id in found:
        await connection.execute("UPDATE videos SET is_audiobook = 1, audiobook_source = ? WHERE id = ?", (AUTO, video_id))
    await connection.commit()
    return len(found)


async def set_by_user(video_ids: Iterable[str], is_audiobook: bool) -> int:
    ids = list(dict.fromkeys(video_ids))
    if not ids:
        return 0
    marks = ",".join("?" * len(ids))
    cursor = await db.execute(
        f"UPDATE videos SET is_audiobook = ?, audiobook_source = ? WHERE id IN ({marks})", (int(is_audiobook), USER, *ids))
    return cursor.rowcount

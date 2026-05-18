"""
TubeVault – Text-Resolver v1.0.0

Liefert dokument-artige Texte eines Videos (description, später chapters,
tags, notes). Strategie:

    1. Datei im TEXTS_DIR (Wahrheit) – wenn da, diese zurückgeben.
    2. DB-Spalte (Legacy-Index) – nur als Fallback.
    3. None wenn beides leer/fehlt.

Dieser Service ist reiner Reader – er schreibt nichts (kein Self-Heal),
damit Read-Pfade keine Seiteneffekte auslösen. Wer Files schreiben will,
nutzt text_export.export_description().

Solange die DB-Spalte gefüllt ist, ist der Fallback redundant aber
gefahrlos. Nach einer DB-Leerung trägt die Datei-Schicht alle Reads.
"""
import logging
from pathlib import Path

from app.database import db
from app.services.storage import storage

logger = logging.getLogger(__name__)


def _description_file(video_id: str) -> Path:
    """Pfad zur description.txt – respektiert TEXTS_DIR-Override aus text_export
    damit Tests beide Services mit dem gleichen monkeypatch umlenken können."""
    from app.services import text_export as _te
    override = _te.TEXTS_DIR
    if override is not None:
        return override / video_id / "description.txt"
    return storage.text_file(video_id, "description")


async def get_description(video_id: str) -> str | None:
    """Liefert die Beschreibung eines Videos. File-first, DB-Fallback.

    Returns:
        str mit Inhalt, oder None wenn weder Datei noch DB-Spalte Text haben.
    """
    f = _description_file(video_id)
    try:
        if f.exists():
            content = f.read_text(encoding="utf-8")
            if content:
                return content
    except OSError as e:
        logger.warning(f"Datei-Read fehlgeschlagen {video_id}: {e}")

    row = await db.fetch_one(
        "SELECT description FROM videos WHERE id = ?", (video_id,)
    )
    if row and row["description"]:
        return row["description"]
    return None


async def get_chapters(video_id: str) -> list | None:
    """Liefert die Chapter-Liste eines Videos. File-first, DB-Fallback.

    Returns:
        Liste von dicts {title, start_time, end_time, thumbnail_url, source},
        oder None wenn keine Chapters existieren.
    """
    import json
    from app.services.storage import storage as _storage
    from app.services import text_export as _te

    # File-Pfad analog zu description
    override = _te.TEXTS_DIR
    f = (override / video_id / "chapters.json") if override is not None \
        else _storage.text_file(video_id, "chapters")
    try:
        if f.exists():
            raw = f.read_text(encoding="utf-8")
            if raw.strip():
                data = json.loads(raw)
                if isinstance(data, list) and data:
                    return data
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Chapter-File-Read fehlgeschlagen {video_id}: {e}")

    # DB-Fallback
    rows = await db.fetch_all(
        """SELECT title, start_time, end_time, thumbnail_url, source
           FROM chapters WHERE video_id = ? ORDER BY start_time""",
        (video_id,),
    )
    if not rows:
        return None
    return [dict(r) for r in rows]


async def has_description(video_id: str) -> bool:
    """Billiger Check ohne Content zu laden: gibt es überhaupt was?"""
    f = _description_file(video_id)
    try:
        if f.exists() and f.stat().st_size > 0:
            return True
    except OSError:
        pass
    row = await db.fetch_one(
        "SELECT 1 FROM videos WHERE id = ? AND description IS NOT NULL AND description != ''",
        (video_id,),
    )
    return row is not None

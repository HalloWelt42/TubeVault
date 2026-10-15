"""
TubeVault – Speicherbelegung der Datenordner

Die Größe eines Ordners zu bestimmen heißt, jede Datei darin anzufassen. Im
Videoordner sind das zehntausende Dateien auf einer langsamen Platte. Früher
geschah das bei jedem Aufruf der Statistik, synchron im Hauptlauf und je
Ordner zweimal - TubeVault antwortete dann minutenlang auf gar nichts mehr.

Jetzt: Die Videogröße kommt aus der Datenbank (jede Datei ist dort mit
file_size erfasst). Die übrigen Ordner werden in einem Hintergrund-Thread
gemessen und zwischengespeichert; die Statistik liefert sofort den letzten
Stand mit seinem Zeitpunkt und stößt höchstens alle MAX_AGE eine neue Messung
an.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from app.config import AUDIO_DIR, AVATARS_DIR, SUBTITLES_DIR, TEMP_DIR, THUMBNAILS_DIR
from app.database import db

logger = logging.getLogger(__name__)

MAX_AGE = timedelta(hours=6)

# Ordner, die gemessen werden: Name -> (Pfad, Platte)
MEASURED_DIRS: dict[str, tuple[Path, str]] = {
    "audio": (AUDIO_DIR, "media"),
    "subtitles": (SUBTITLES_DIR, "media"),
    "thumbnails": (THUMBNAILS_DIR, "meta"),
    "avatars": (AVATARS_DIR, "meta"),
    "temp": (TEMP_DIR, "meta"),
}


class DirectoryUsage(BaseModel):
    size: Optional[int] = None         # None = noch nicht gemessen
    disk: str


class UsageSnapshot(BaseModel):
    directories: dict[str, DirectoryUsage]
    measured_at: Optional[str] = None  # Zeitpunkt der Ordnermessung (UTC)
    measuring: bool = False


_sizes: dict[str, int] = {}
_measured_at: Optional[datetime] = None
_task: Optional[asyncio.Task] = None


def directory_size(path: Path) -> int:
    """Größe aller Dateien unter path (synchron, für einen Thread). Folgt
    keinen Verknüpfungen; nicht lesbare Einträge werden übergangen."""
    total, stack = 0, [str(path)]
    while stack:
        try:
            with os.scandir(stack.pop()) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


async def _measure() -> None:
    global _sizes, _measured_at
    sizes = {}
    for name, (path, _disk) in MEASURED_DIRS.items():
        sizes[name] = await asyncio.to_thread(directory_size, path)
    _sizes, _measured_at = sizes, datetime.now(timezone.utc)
    logger.info("[SPEICHER] Ordner gemessen: " + ", ".join(f"{k}={v}" for k, v in sizes.items()))


def refresh() -> None:
    """Neue Messung im Hintergrund anstoßen (läuft höchstens einmal zugleich)."""
    global _task
    if _task and not _task.done():
        return
    _task = asyncio.ensure_future(_measure())
    _task.add_done_callback(lambda t: t.cancelled() or t.exception())


async def snapshot() -> UsageSnapshot:
    """Sofort: Videogröße aus der Datenbank, die übrigen Ordner aus der
    letzten Messung. Ist sie zu alt oder fehlt sie, läuft eine neue an."""
    if not _measured_at or datetime.now(timezone.utc) - _measured_at > MAX_AGE:
        refresh()
    videos = await db.fetch_val(
        "SELECT COALESCE(SUM(file_size), 0) FROM videos WHERE status = 'ready'") or 0
    directories = {"videos": DirectoryUsage(size=videos, disk="media")}
    for name, (_path, disk) in MEASURED_DIRS.items():
        directories[name] = DirectoryUsage(size=_sizes.get(name), disk=disk)
    return UsageSnapshot(
        directories=directories,
        measured_at=_measured_at.strftime("%Y-%m-%d %H:%M:%S") if _measured_at else None,
        measuring=bool(_task and not _task.done()))

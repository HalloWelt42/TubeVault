"""
TubeVault - Videos ohne Datei

Die eine Stelle, die fertige Videos ohne Mediendatei auf status='ghost' setzt (Startprüfung, Bereinigung im System-Menü,
große Bereinigung). Markiert wird nur, wenn der Bestand erreichbar ist und nicht auf einmal zu viel fehlt
(missing_guard); sonst bleibt jedes Video, wie es ist (NETZ-28). Gelöscht wird hier nie etwas.
"""
import asyncio
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from app.config import AUDIO_DIR, VIDEOS_DIR
from app.database import db
from app.services import missing_guard
from app.utils.file_utils import is_media_file

MEDIA_ROOTS = (VIDEOS_DIR, AUDIO_DIR)


class GhostEntry(BaseModel):
    id: str
    title: Optional[str] = None
    file_path: Optional[str] = None


class GhostResult(BaseModel):
    ready: int
    found: int
    marked: int
    blocked_reason: str = ""
    entries: list[GhostEntry] = []


def _roots_in_use(paths: list[str]) -> list[Path]:
    """Die Medienordner, unter denen mindestens eines der Videos liegt."""
    return [root for root in MEDIA_ROOTS if any(p.startswith(str(root)) for p in paths)]


async def mark_ghosts(force: bool = False) -> GhostResult:
    """Fertige Videos ohne Datei finden und als ghost markieren.

    Ist ein Medienordner nicht erreichbar, wird gar nicht erst gesucht (jede Prüfung einer Datei auf einem
    weggefallenen Netzlaufwerk wartet sonst einzeln auf eine Zeitgrenze). force markiert auch dann, wenn ungewöhnlich
    viel fehlt; das ist nur für ausdrückliches Aufräumen nach dem Löschen vieler Dateien von Hand gedacht.
    """
    rows = await db.fetch_all("SELECT id, title, file_path FROM videos WHERE status = 'ready'")
    paths = [r["file_path"] or "" for r in rows]
    roots = _roots_in_use(paths)
    gone = await asyncio.to_thread(missing_guard.unreachable_roots, roots)
    if gone and not force:
        verdict = missing_guard.judge(len(rows), len(rows), gone, "Videos ohne Datei")
        return GhostResult(ready=len(rows), found=0, marked=0, blocked_reason=verdict.reason)

    ghosts = await asyncio.to_thread(lambda: [r for r in rows if not is_media_file(r["file_path"])])
    entries = [GhostEntry(id=g["id"], title=g["title"], file_path=g["file_path"]) for g in ghosts]
    verdict = await asyncio.to_thread(missing_guard.judge, len(ghosts), len(rows), roots, "Videos ohne Datei")
    if not verdict.allowed and not force:
        return GhostResult(ready=len(rows), found=len(ghosts), marked=0,
                           blocked_reason=verdict.reason, entries=entries)
    for g in ghosts:
        await db.execute("UPDATE videos SET status = 'ghost' WHERE id = ? AND status = 'ready'", (g["id"],))
    return GhostResult(ready=len(rows), found=len(ghosts), marked=len(ghosts), entries=entries)

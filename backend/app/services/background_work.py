"""
TubeVault – Laufende Hintergrundarbeiten v1.0.0

Lang laufende Vorgänge sollen sichtbar sein: was läuft, wie weit, wie lange
noch. Diese Übersicht sammelt den Stand aller Arbeiten, die ohne Zutun des
Nutzers im Hintergrund laufen, an einer Stelle - die Oberfläche zeigt sie in
der Statusleiste. (Downloads haben ihre eigene, ausführlichere Anzeige.)

Eine neue Hintergrundarbeit trägt sich hier mit einer Funktion ein, die
ihren Stand als WorkItem liefert (oder None, wenn nichts zu tun ist).
"""
from datetime import datetime
from typing import Awaitable, Callable, Optional

from pydantic import BaseModel

from app.database import db


class WorkItem(BaseModel):
    key: str
    label: str
    detail: Optional[str] = None      # was gerade geschieht
    done: Optional[int] = None        # erledigte Einheiten
    total: Optional[int] = None       # Einheiten insgesamt
    progress: Optional[float] = None  # 0..1, falls bekannt
    since: Optional[str] = None       # läuft seit (Ortszeit)
    eta_seconds: Optional[int] = None # geschätzte Restdauer
    waiting: int = 0                  # weitere wartende Aufträge dahinter


# Höchststand je Arbeit seit Programmstart: daraus ergibt sich "x von y"
_peak: dict[str, int] = {}
_first_seen: dict[str, str] = {}


def _countdown(key: str, remaining: int) -> tuple[int, int, str]:
    """(erledigt, gesamt, seit) aus einer schrumpfenden Restmenge ableiten."""
    if remaining > _peak.get(key, 0):
        _peak[key] = remaining
        _first_seen.setdefault(key, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    total = _peak[key]
    return total - remaining, total, _first_seen[key]


def _forget(key: str) -> None:
    _peak.pop(key, None)
    _first_seen.pop(key, None)


async def _search_index() -> Optional[WorkItem]:
    from app.services import search_index
    remaining = await search_index.pending()
    if remaining < 50:   # einzelne Änderungen zieht die nächste Suche nach
        _forget("search_index")
        return None
    done, total, since = _countdown("search_index", remaining)
    return WorkItem(key="search_index", label="Suchindex wird aufgebaut",
                    detail="Die Suche findet bis dahin noch nicht alle Videos.",
                    done=done, total=total, progress=done / total if total else None, since=since)


async def _type_check() -> Optional[WorkItem]:
    from app.services import video_classifier
    remaining = await video_classifier.pending()
    if remaining == 0:
        _forget("type_check")
        return None
    done, total, since = _countdown("type_check", remaining)
    return WorkItem(
        key="type_check", label="Video-Typen werden geprüft",
        detail="Fragt die Quelle, was Short und was Video ist (bewusst langsam).",
        done=done, total=total, progress=done / total if total else None, since=since,
        eta_seconds=int(remaining * video_classifier.SECONDS_PER_PROBE))


async def _dubbing() -> Optional[WorkItem]:
    row = await db.fetch_one(
        """SELECT d.progress, d.note, d.claimed_at, d.worker, v.title
           FROM dub_requests d LEFT JOIN videos v ON v.id = d.video_id
           WHERE d.status = 'working' ORDER BY d.claimed_at LIMIT 1""")
    waiting = await db.fetch_val("SELECT COUNT(*) FROM dub_requests WHERE status = 'queued'") or 0
    if not row:
        return None   # wartende Aufträge ohne Nachvertoner zeigt die Seite Nachvertonung
    title = (row["title"] or "Video")[:60]
    return WorkItem(key="dubbing", label=f"Nachvertonung: {title}",
                    detail=" · ".join(filter(None, [row["note"], row["worker"]])) or None,
                    progress=row["progress"] or 0, since=row["claimed_at"], waiting=waiting)


SOURCES: list[Callable[[], Awaitable[Optional[WorkItem]]]] = [_dubbing, _search_index, _type_check]


async def overview() -> list[WorkItem]:
    items = []
    for source in SOURCES:
        item = await source()
        if item:
            items.append(item)
    return items

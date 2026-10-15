"""
TubeVault – Reuploads erkennen

Manche Kanäle laden dasselbe Video Monate später unter neuer ID noch einmal
hoch (ARTE etwa mit dem Zusatz "Reupload"). Liegt es schon in der Bibliothek,
brächte ein zweiter Download nur doppelten Platzbedarf. Dasselbe Video heißt
hier: derselbe Kanal, derselbe Titel (ohne den Zusatz "Reupload",
Groß-/Kleinschreibung und Leerraum egal) und dieselbe Dauer bis auf
DURATION_TOLERANCE_S Sekunden.

Messung am Bestand (15.10.2026): 55 solcher Doppel in 52 Gruppen. Gleicher
Titel mit anderer Dauer war fast immer etwas anderes (Short oder Trailer zum
Video), über Kanäle hinweg gab es keinen Treffer - daher die enge Regel.
"""
import re
from typing import Optional

from pydantic import BaseModel

from app.database import db

DURATION_TOLERANCE_S = 2

_REUPLOAD_MARKER = re.compile(r"\breupload\b", re.IGNORECASE)
_SPACE = re.compile(r"\s+")


class Twin(BaseModel):
    """Das schon vorhandene Video, das ein neuer Download noch einmal wäre."""
    id: str
    title: str


def comparable_title(title: Optional[str]) -> str:
    """Titel in der Form, in der zwei Uploads verglichen werden."""
    return _SPACE.sub(" ", _REUPLOAD_MARKER.sub(" ", title or "")).strip().casefold()


async def find_twin(video_id: str, channel_id: Optional[str], title: Optional[str],
                    duration: Optional[int]) -> Optional[Twin]:
    """Das fertig geladene Video desselben Kanals mit gleichem Titel und
    gleicher Dauer - oder None. Ohne Kanal, Titel oder Dauer wird nichts
    angenommen."""
    wanted = comparable_title(title)
    if not (channel_id and wanted and duration):
        return None
    rows = await db.fetch_all(
        """SELECT id, title FROM videos
           WHERE channel_id = ? AND status = 'ready' AND id <> ?
             AND duration BETWEEN ? AND ?
           ORDER BY download_date""",
        (channel_id, video_id, duration - DURATION_TOLERANCE_S, duration + DURATION_TOLERANCE_S))
    for row in rows:
        if comparable_title(row["title"]) == wanted:
            return Twin(id=row["id"], title=row["title"])
    return None

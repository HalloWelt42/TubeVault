"""
TubeVault – Wie weit gesehen

Die eine Stelle, die festlegt, wann ein Video neu, angefangen oder zu Ende
gesehen ist. Grundlage ist allein die gemerkte Stelle (videos.last_position)
im Verhältnis zur Dauer:
  neu          gemerkte Stelle höchstens STARTED_FROM_S Sekunden (Antippen zählt nicht)
  angefangen   dazwischen
  gesehen      ab FINISHED_SHARE der Dauer

"Als gesehen markieren" setzt die Stelle ans Ende, "als neu" bzw. "gemerkte
Stelle vergessen" auf den Anfang - so bleibt es bei dieser einen Grundlage.
"""
from typing import Iterable, Literal, Optional

from app.database import db

STARTED_FROM_S = 5
FINISHED_SHARE = 0.95

State = Literal["new", "started", "finished"]
STATES: tuple[State, ...] = ("new", "started", "finished")


def progress(position: Optional[int], duration: Optional[int]) -> float:
    """Gesehener Anteil 0..1."""
    if not duration or not position or position <= STARTED_FROM_S:
        return 0.0
    return min(1.0, position / duration)


def state_of(position: Optional[int], duration: Optional[int]) -> State:
    share = progress(position, duration)
    if share >= FINISHED_SHARE:
        return "finished"
    return "started" if share > 0 else "new"


def state_sql(alias: str = "v") -> str:
    """SQL-Ausdruck mit 'new' | 'started' | 'finished' - dieselbe Regel wie state_of."""
    position, duration = f"COALESCE({alias}.last_position, 0)", f"COALESCE({alias}.duration, 0)"
    return (f"(CASE WHEN {duration} <= 0 OR {position} <= {STARTED_FROM_S} THEN 'new' "
            f"WHEN {position} >= {duration} * {FINISHED_SHARE} THEN 'finished' ELSE 'started' END)")


async def set_watched(video_ids: Iterable[str], watched: bool) -> int:
    """Als gesehen (Stelle ans Ende) oder als neu (Stelle auf den Anfang) markieren."""
    ids = list(dict.fromkeys(video_ids))
    if not ids:
        return 0
    marks = ",".join("?" * len(ids))
    position = "COALESCE(duration, 0)" if watched else "0"
    cursor = await db.execute(
        f"UPDATE videos SET last_position = {position}, updated_at = datetime('now') WHERE id IN ({marks})", ids)
    return cursor.rowcount

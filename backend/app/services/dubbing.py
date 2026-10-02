"""
TubeVault – Nachvertonung (Warteliste) v1.0.0

TubeVault vertont nicht selbst. Es führt nur die Warteliste: welche Videos
sollen in welche Sprache nachvertont werden. Ein eigenes Programm auf einem
Rechner mit genug Leistung (der "Nachvertoner") holt sich Aufträge ab, wenn
dort Kapazität frei ist, und liefert die fertige Tonspur zurück. Die Spur
landet als zusätzliche Tonspur am Video (services/audio_tracks.py).

Ablauf eines Auftrags:
    wartet → in Arbeit (abgeholt) → fertig | fehlgeschlagen | übersprungen
Meldet sich der Nachvertoner länger nicht (Absturz, Rechner aus), geht der
Auftrag zurück in die Warteliste.
"""
import logging
from typing import Literal, Optional

from pydantic import BaseModel

from app.database import db
from app.services import audio_tracks

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS dub_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    target_language TEXT NOT NULL,
    voice TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    progress REAL DEFAULT 0,
    note TEXT,
    worker TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    claimed_at TEXT,
    heartbeat_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_dub_requests_status ON dub_requests(status, created_at);
CREATE INDEX IF NOT EXISTS idx_dub_requests_video ON dub_requests(video_id);
"""

Status = Literal["queued", "working", "done", "error", "skipped"]
OPEN_STATUSES = ("queued", "working")
# Ohne Lebenszeichen gilt ein abgeholter Auftrag nach dieser Zeit als verwaist
STALE_AFTER_MINUTES = 30


class DubRequest(BaseModel):
    id: int
    video_id: str
    title: Optional[str] = None
    channel_name: Optional[str] = None
    duration: Optional[int] = None
    source_language: Optional[str] = None
    target_language: str
    voice: Optional[str] = None
    status: Status
    progress: float = 0
    note: Optional[str] = None
    worker: Optional[str] = None
    created_at: Optional[str] = None
    claimed_at: Optional[str] = None
    finished_at: Optional[str] = None


class EnqueueResult(BaseModel):
    queued: list[str]
    skipped: dict[str, str]   # video_id → Grund


_SELECT = """
    SELECT d.*, v.title, v.channel_name, v.duration, v.language AS source_language
    FROM dub_requests d LEFT JOIN videos v ON v.id = d.video_id
"""


def _to_model(row) -> DubRequest:
    data = dict(row)
    return DubRequest(**{k: data.get(k) for k in DubRequest.model_fields})


async def _setting(key: str) -> str:
    from app import settings_schema
    value = await db.fetch_val("SELECT value FROM settings WHERE key = ?", (key,))
    return value if value not in (None, "") else settings_schema.BY_KEY[key].default


async def is_enabled() -> bool:
    return (await _setting("dub.enabled")) == "true"


async def enqueue(video_ids: list[str], target_language: str | None = None,
                  voice: str | None = None) -> EnqueueResult:
    """Videos zur Nachvertonung vormerken. Übersprungen wird, was nicht bereit
    ist, schon in der Zielsprache vorliegt oder bereits vorgemerkt ist."""
    target = (target_language or await _setting("dub.target_language")).strip().lower()
    voice = voice or await _setting("dub.voice")
    queued, skipped = [], {}
    for video_id in dict.fromkeys(video_ids):   # Reihenfolge behalten, Doppelte raus
        video = await db.fetch_one(
            "SELECT id, status, language FROM videos WHERE id = ?", (video_id,))
        if not video or video["status"] != "ready":
            skipped[video_id] = "Video ist nicht geladen"
            continue
        if (video["language"] or "").lower() == target:
            skipped[video_id] = f"Original ist bereits {audio_tracks.language_name(target)}"
            continue
        if await db.fetch_one(
                "SELECT id FROM audio_tracks WHERE video_id = ? AND language = ?", (video_id, target)):
            skipped[video_id] = f"Tonspur {audio_tracks.language_name(target)} ist schon vorhanden"
            continue
        if await db.fetch_one(
                "SELECT id FROM dub_requests WHERE video_id = ? AND target_language = ? "
                "AND status IN ('queued', 'working')", (video_id, target)):
            skipped[video_id] = "ist bereits vorgemerkt"
            continue
        await db.execute(
            "INSERT INTO dub_requests (video_id, target_language, voice) VALUES (?, ?, ?)",
            (video_id, target, voice))
        queued.append(video_id)
    if queued:
        logger.info(f"[NACHVERTONUNG] {len(queued)} Videos vorgemerkt ({target})")
    return EnqueueResult(queued=queued, skipped=skipped)


async def list_requests(status: str | None = None, limit: int = 200) -> list[DubRequest]:
    where, params = "", []
    if status == "open":
        where = "WHERE d.status IN ('queued', 'working')"
    elif status:
        where, params = "WHERE d.status = ?", [status]
    rows = await db.fetch_all(
        f"""{_SELECT} {where}
            ORDER BY CASE d.status WHEN 'working' THEN 0 WHEN 'queued' THEN 1 ELSE 2 END,
                     COALESCE(d.finished_at, d.created_at) DESC, d.id DESC
            LIMIT ?""", [*params, limit])
    return [_to_model(r) for r in rows]


async def counts() -> dict[str, int]:
    rows = await db.fetch_all("SELECT status, COUNT(*) AS n FROM dub_requests GROUP BY status")
    result = {s: 0 for s in ("queued", "working", "done", "error", "skipped")}
    result.update({r["status"]: r["n"] for r in rows})
    return result


async def get(request_id: int) -> DubRequest | None:
    row = await db.fetch_one(f"{_SELECT} WHERE d.id = ?", (request_id,))
    return _to_model(row) if row else None


async def _release_stale() -> None:
    await db.execute(
        f"""UPDATE dub_requests
            SET status = 'queued', worker = NULL, claimed_at = NULL, progress = 0,
                note = 'Nachvertoner hat sich nicht mehr gemeldet - erneut in der Warteliste'
            WHERE status = 'working'
              AND COALESCE(heartbeat_at, claimed_at) < datetime('now', 'localtime', '-{STALE_AFTER_MINUTES} minutes')""")


async def claim(worker: str) -> DubRequest | None:
    """Den ältesten wartenden Auftrag für einen Nachvertoner reservieren."""
    await _release_stale()
    row = await db.fetch_one(
        "SELECT id FROM dub_requests WHERE status = 'queued' ORDER BY created_at, id LIMIT 1")
    if not row:
        return None
    cursor = await db.execute(
        """UPDATE dub_requests
           SET status = 'working', worker = ?, claimed_at = datetime('now', 'localtime'),
               heartbeat_at = datetime('now', 'localtime'), progress = 0, note = NULL
           WHERE id = ? AND status = 'queued'""", (worker, row["id"]))
    if cursor.rowcount != 1:
        return None   # ein anderer Nachvertoner war schneller
    return await get(row["id"])


async def heartbeat(request_id: int, progress: float | None = None, note: str | None = None) -> bool:
    cursor = await db.execute(
        """UPDATE dub_requests
           SET heartbeat_at = datetime('now', 'localtime'),
               progress = COALESCE(?, progress), note = COALESCE(?, note)
           WHERE id = ? AND status = 'working'""",
        (None if progress is None else max(0.0, min(1.0, progress)), note, request_id))
    return cursor.rowcount == 1


async def finish(request_id: int, status: Status, note: str | None = None) -> None:
    await db.execute(
        """UPDATE dub_requests
           SET status = ?, note = ?, finished_at = datetime('now', 'localtime'),
               progress = CASE WHEN ? = 'done' THEN 1 ELSE progress END
           WHERE id = ?""", (status, note, status, request_id))


async def retry(request_id: int) -> bool:
    cursor = await db.execute(
        """UPDATE dub_requests
           SET status = 'queued', worker = NULL, claimed_at = NULL, finished_at = NULL,
               progress = 0, note = NULL
           WHERE id = ? AND status IN ('error', 'skipped')""", (request_id,))
    return cursor.rowcount == 1


async def remove(request_id: int) -> bool:
    cursor = await db.execute("DELETE FROM dub_requests WHERE id = ?", (request_id,))
    return cursor.rowcount == 1

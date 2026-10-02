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
    subtitles TEXT NOT NULL DEFAULT 'manual',
    status TEXT NOT NULL DEFAULT 'queued',
    progress REAL DEFAULT 0,
    note TEXT,
    worker TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    claimed_at TEXT,
    heartbeat_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_dub_requests_status ON dub_requests(status, created_at);
CREATE INDEX IF NOT EXISTS idx_dub_requests_video ON dub_requests(video_id);

-- Stimmen, die der Nachvertoner zuletzt als verfügbar gemeldet hat
CREATE TABLE IF NOT EXISTS dub_voices (
    name TEXT PRIMARY KEY,
    reported_at TEXT DEFAULT (datetime('now'))
);
"""


async def install_schema(connection) -> None:
    await connection.executescript(SCHEMA_SQL)
    try:
        await connection.execute(
            "ALTER TABLE dub_requests ADD COLUMN subtitles TEXT NOT NULL DEFAULT 'manual'")
    except Exception as e:
        if "duplicate column" not in str(e).lower():
            raise
    await connection.commit()


Status = Literal["queued", "working", "done", "error", "skipped", "cancelled"]
# Welche Untertitel der Quelle als Transkript dienen dürfen
SubtitleUse = Literal["never", "manual", "any"]
DEFAULT_TARGET_LANGUAGE = "de"
# Vorauswahl: die erste gemeldete Stimme, deren Name so beginnt
DEFAULT_VOICE_HINT = "zeit"
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
    subtitles: SubtitleUse = "manual"
    status: Status
    progress: float = 0
    note: Optional[str] = None
    worker: Optional[str] = None
    created_at: Optional[str] = None
    claimed_at: Optional[str] = None
    finished_at: Optional[str] = None


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


class VoiceChoice(BaseModel):
    voices: list[str]
    default: Optional[str] = None
    reported_at: Optional[str] = None


async def report_voices(names: list[str]) -> None:
    """Der Nachvertoner meldet, welche Stimmen der Vertonungsdienst gerade hat."""
    names = sorted({name.strip() for name in names if name and name.strip()}, key=str.lower)
    await db.execute("DELETE FROM dub_voices")
    for name in names:
        await db.execute("INSERT INTO dub_voices (name) VALUES (?)", (name,))


async def voice_choice() -> VoiceChoice:
    """Verfügbare Stimmen und die Vorauswahl."""
    rows = await db.fetch_all("SELECT name, reported_at FROM dub_voices ORDER BY name COLLATE NOCASE")
    voices = [row["name"] for row in rows]
    default = next((v for v in voices if v.lower().startswith(DEFAULT_VOICE_HINT)), None)
    return VoiceChoice(voices=voices, default=default or (voices[0] if voices else None),
                       reported_at=rows[0]["reported_at"] if rows else None)


class EnqueueOutcome(BaseModel):
    queued: bool
    reason: Optional[str] = None      # warum nicht vorgemerkt
    request: Optional[DubRequest] = None


async def enqueue(video_id: str, target_language: str | None = None,
                  voice: str | None = None, subtitles: SubtitleUse = "any") -> EnqueueOutcome:
    """Ein Video zur Nachvertonung vormerken - immer eine ausdrückliche
    Entscheidung für genau dieses Video. Ohne Stimme gilt die Vorauswahl.
    Ist die Zielsprache die des Originals, wird nur neu gesprochen."""
    target = (target_language or DEFAULT_TARGET_LANGUAGE).strip().lower()
    voice = (voice or "").strip() or (await voice_choice()).default

    def refused(reason: str) -> EnqueueOutcome:
        return EnqueueOutcome(queued=False, reason=reason)

    video = await db.fetch_one("SELECT id, status, language FROM videos WHERE id = ?", (video_id,))
    if not video or video["status"] != "ready":
        return refused("Video ist nicht geladen")
    # Gleiche Sprache ist erlaubt: das Video wird dann mit einer anderen Stimme
    # neu gesprochen, ohne Übersetzung.
    if await db.fetch_one(
            "SELECT id FROM audio_tracks WHERE video_id = ? AND language = ?", (video_id, target)):
        return refused(f"Tonspur {audio_tracks.language_name(target)} ist schon vorhanden")
    if await db.fetch_one(
            "SELECT id FROM dub_requests WHERE video_id = ? AND target_language = ? "
            "AND status IN ('queued', 'working')", (video_id, target)):
        return refused("ist bereits vorgemerkt")
    cursor = await db.execute(
        "INSERT INTO dub_requests (video_id, target_language, voice, subtitles) VALUES (?, ?, ?, ?)",
        (video_id, target, voice, subtitles))
    logger.info(f"[NACHVERTONUNG] {video_id} vorgemerkt ({target}, Stimme {voice or 'Vorauswahl'})")
    return EnqueueOutcome(queued=True, request=await get(cursor.lastrowid))


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
    result = {s: 0 for s in ("queued", "working", "done", "error", "skipped", "cancelled")}
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
              AND COALESCE(heartbeat_at, claimed_at) < datetime('now', '-{STALE_AFTER_MINUTES} minutes')""")


async def claim(worker: str) -> DubRequest | None:
    """Den ältesten wartenden Auftrag für einen Nachvertoner reservieren."""
    await _release_stale()
    row = await db.fetch_one(
        "SELECT id FROM dub_requests WHERE status = 'queued' ORDER BY created_at, id LIMIT 1")
    if not row:
        return None
    cursor = await db.execute(
        """UPDATE dub_requests
           SET status = 'working', worker = ?, claimed_at = datetime('now'),
               heartbeat_at = datetime('now'), progress = 0, note = NULL
           WHERE id = ? AND status = 'queued'""", (worker, row["id"]))
    if cursor.rowcount != 1:
        return None   # ein anderer Nachvertoner war schneller
    return await get(row["id"])


async def heartbeat(request_id: int, progress: float | None = None, note: str | None = None) -> bool:
    cursor = await db.execute(
        """UPDATE dub_requests
           SET heartbeat_at = datetime('now'),
               progress = COALESCE(?, progress), note = COALESCE(?, note)
           WHERE id = ? AND status = 'working'""",
        (None if progress is None else max(0.0, min(1.0, progress)), note, request_id))
    return cursor.rowcount == 1


async def finish(request_id: int, status: Status, note: str | None = None) -> None:
    await db.execute(
        """UPDATE dub_requests
           SET status = ?, note = ?, finished_at = datetime('now'),
               progress = CASE WHEN ? = 'done' THEN 1 ELSE progress END
           WHERE id = ?""", (status, note, status, request_id))


async def retry(request_id: int) -> bool:
    cursor = await db.execute(
        """UPDATE dub_requests
           SET status = 'queued', worker = NULL, claimed_at = NULL, finished_at = NULL,
               progress = 0, note = NULL
           WHERE id = ? AND status IN ('error', 'skipped', 'cancelled')""", (request_id,))
    return cursor.rowcount == 1


async def cancel(request_id: int) -> bool:
    """Offenen Auftrag abbrechen. Er bleibt als "abgebrochen" in der Liste;
    ein Nachvertoner, der daran arbeitet, erfährt es beim nächsten Lebenszeichen."""
    cursor = await db.execute(
        """UPDATE dub_requests
           SET status = 'cancelled', finished_at = datetime('now'),
               note = CASE WHEN status = 'working' THEN 'Abgebrochen bei ' || CAST(ROUND(progress * 100) AS INTEGER) || ' %'
                           ELSE 'Abgebrochen, bevor die Arbeit begann' END
           WHERE id = ? AND status IN ('queued', 'working')""", (request_id,))
    return cursor.rowcount == 1


async def remove(request_id: int) -> bool:
    cursor = await db.execute("DELETE FROM dub_requests WHERE id = ?", (request_id,))
    return cursor.rowcount == 1

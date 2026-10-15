"""
TubeVault - Nachvertonung (Warteliste) v1.1.0

TubeVault vertont nicht selbst. Es führt nur die Warteliste: welche Videos
sollen in welche Sprache nachvertont werden. Ein eigenes Programm auf einem
Rechner mit genug Leistung (der "Nachvertoner") holt sich Aufträge ab, wenn
dort Kapazität frei ist, und liefert die fertige Tonspur zurück. Die Spur
landet als zusätzliche Tonspur am Video (services/audio_tracks.py).

Ablauf eines Auftrags:
    wartet → in Arbeit (abgeholt) → fertig | fehlgeschlagen | übersprungen
Meldet sich der Nachvertoner länger nicht (Absturz, Rechner aus), geht der
Auftrag zurück in die Warteliste.

Was die Seite Nachvertonung zeigt, entsteht hier: Zählungen je Reiter, die
Schritte laufender Aufträge (services/dubbing_steps.py), das letzte
Lebenszeichen des Nachvertoners und die Stimmen samt Hörprobe.
"""
import logging
import time
from typing import Literal, Optional

from pydantic import BaseModel

from app.database import db
from app.services import audio_tracks, dubbing_steps, setting_values
from app.services.dubbing_steps import DubStep

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


# Vertonen an oder angehalten (Liste der Hintergrundarbeiten); angehalten ist der Standard
PROCESSING_SWITCH = "dub.processing_enabled"


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
STATUSES: tuple[Status, ...] = ("queued", "working", "done", "error", "skipped", "cancelled")
# Welche Untertitel der Quelle als Transkript dienen dürfen
SubtitleUse = Literal["never", "manual", "any"]
DEFAULT_TARGET_LANGUAGE = "de"
# Vorauswahl ohne eigene Wahl: die erste gemeldete Stimme, deren Name so beginnt
DEFAULT_VOICE_HINT = "zeit"
OPEN_STATUSES = ("queued", "working")
FINISHED_STATUSES = ("done", "error", "skipped", "cancelled")
# Ohne Lebenszeichen gilt ein abgeholter Auftrag nach dieser Zeit als verwaist
STALE_AFTER_MINUTES = 30
# So lange nach dem letzten Lebenszeichen gilt der Nachvertoner als bereit.
# Er meldet sich ohne Arbeit jede Minute (Stimmen), bei der Arbeit alle 15 s.
ONLINE_WITHIN_SECONDS = 5 * 60
# Hörprobe: ab diesem Anteil einer fertigen Tonspur (der Anfang ist oft Vorspann)
SAMPLE_AT_SHARE = 0.25
# Seitengröße der Auftragsliste
PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

# Reiter der Seite und die Zustände, die sie zeigen. Laufende Aufträge stehen
# unter "Alle" als Karten über der Liste, deshalb nicht in deren Liste.
Tab = Literal["all", "working", "queued", "done", "error"]
TAB_STATUSES: dict[str, tuple[Status, ...]] = {
    "all": ("queued", "done", "error", "skipped", "cancelled"),
    "working": ("working",),
    "queued": ("queued",),
    "done": ("done",),
    "error": ("error",),
}


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
    track_id: Optional[int] = None     # vorhandene Tonspur des Videos in der Zielsprache


_SELECT = """
    SELECT d.*, v.title, v.channel_name, v.duration, v.language AS source_language,
           a.id AS track_id
    FROM dub_requests d
    LEFT JOIN videos v ON v.id = d.video_id
    LEFT JOIN audio_tracks a ON a.video_id = d.video_id AND a.language = d.target_language
"""


def _to_model(row) -> DubRequest:
    data = dict(row)
    return DubRequest(**{k: data.get(k) for k in DubRequest.model_fields})


async def is_enabled() -> bool:
    return await setting_values.is_on("dub.enabled")


# ─── Stimmen ───────────────────────────────────────────────────────────

class VoiceSample(BaseModel):
    """Hörprobe einer Stimme: ein Stück aus einer fertigen Tonspur."""
    video_id: str
    track_id: int
    start: float


class VoiceInfo(BaseModel):
    name: str
    dubs: int = 0                         # fertige Tonspuren mit dieser Stimme
    sample: Optional[VoiceSample] = None


class VoiceChoice(BaseModel):
    voices: list[str]
    default: Optional[str] = None
    reported_at: Optional[str] = None
    details: list[VoiceInfo] = []


async def report_voices(names: list[str]) -> None:
    """Der Nachvertoner meldet, welche Stimmen der Vertonungsdienst gerade hat."""
    names = sorted({name.strip() for name in names if name and name.strip()}, key=str.lower)
    await db.execute("DELETE FROM dub_voices")
    for name in names:
        await db.execute("INSERT INTO dub_voices (name) VALUES (?)", (name,))


def pick_default(voices: list[str], chosen: str) -> Optional[str]:
    """Vorauswahl: die eingestellte Stimme, sonst die erste, deren Name mit
    DEFAULT_VOICE_HINT beginnt, sonst die erste. Ohne gemeldete Stimmen gilt
    die eingestellte (der Nachvertoner sucht sie dann selbst)."""
    chosen = (chosen or "").strip()
    if chosen and (not voices or chosen in voices):
        return chosen
    hinted = next((v for v in voices if v.lower().startswith(DEFAULT_VOICE_HINT)), None)
    return hinted or (voices[0] if voices else None)


async def _samples() -> dict[str, VoiceInfo]:
    """Je Stimme: wie viele Tonspuren sie gesprochen hat und die jüngste als Hörprobe."""
    rows = await db.fetch_all(
        """SELECT voice, video_id, id, duration,
                  COUNT(*) OVER (PARTITION BY voice) AS dubs,
                  ROW_NUMBER() OVER (PARTITION BY voice ORDER BY created_at DESC, id DESC) AS rank
           FROM audio_tracks WHERE COALESCE(voice, '') != ''""")
    return {
        row["voice"]: VoiceInfo(
            name=row["voice"], dubs=row["dubs"],
            sample=VoiceSample(video_id=row["video_id"], track_id=row["id"],
                               start=round((row["duration"] or 0) * SAMPLE_AT_SHARE, 1)))
        for row in rows if row["rank"] == 1
    }


async def voice_choice() -> VoiceChoice:
    """Verfügbare Stimmen, die Vorauswahl und je Stimme die Hörprobe."""
    rows = await db.fetch_all("SELECT name, reported_at FROM dub_voices ORDER BY name COLLATE NOCASE")
    voices = [row["name"] for row in rows]
    samples = await _samples()
    return VoiceChoice(
        voices=voices,
        default=pick_default(voices, await setting_values.get("dub.default_voice")),
        reported_at=rows[0]["reported_at"] if rows else None,
        details=[samples.get(name, VoiceInfo(name=name)) for name in voices])


# ─── Vormerken ─────────────────────────────────────────────────────────

class EnqueueOutcome(BaseModel):
    queued: bool
    reason: Optional[str] = None      # warum nicht vorgemerkt
    request: Optional[DubRequest] = None


def _refused(reason: str) -> EnqueueOutcome:
    return EnqueueOutcome(queued=False, reason=reason)


async def default_subtitles() -> SubtitleUse:
    return await setting_values.get("dub.default_subtitles")


async def enqueue(video_id: str, target_language: str | None = None,
                  voice: str | None = None, subtitles: SubtitleUse | None = None) -> EnqueueOutcome:
    """Ein Video zur Nachvertonung vormerken - immer eine ausdrückliche
    Entscheidung für genau dieses Video. Ohne Stimme gilt die Vorauswahl,
    ohne Angabe zu den Untertiteln die eingestellte Vorauswahl.
    Ist die Zielsprache die des Originals, wird nur neu gesprochen."""
    target = (target_language or DEFAULT_TARGET_LANGUAGE).strip().lower()
    voice = (voice or "").strip() or (await voice_choice()).default
    subtitles = subtitles or await default_subtitles()

    video = await db.fetch_one("SELECT id, status, language FROM videos WHERE id = ?", (video_id,))
    if not video or video["status"] != "ready":
        return _refused("Video ist nicht geladen")
    # Gleiche Sprache ist erlaubt: das Video wird dann mit einer anderen Stimme
    # neu gesprochen, ohne Übersetzung.
    if await db.fetch_one(
            "SELECT id FROM audio_tracks WHERE video_id = ? AND language = ?", (video_id, target)):
        return _refused(f"Tonspur {audio_tracks.language_name(target)} ist schon vorhanden")
    if await _open_duplicate(video_id, target):
        return _refused("ist bereits vorgemerkt")
    cursor = await db.execute(
        "INSERT INTO dub_requests (video_id, target_language, voice, subtitles) VALUES (?, ?, ?, ?)",
        (video_id, target, voice, subtitles))
    logger.info(f"[NACHVERTONUNG] {video_id} vorgemerkt ({target}, Stimme {voice or 'Vorauswahl'})")
    return EnqueueOutcome(queued=True, request=await get(cursor.lastrowid))


async def _open_duplicate(video_id: str, target: str, except_id: int | None = None) -> bool:
    row = await db.fetch_one(
        "SELECT id FROM dub_requests WHERE video_id = ? AND target_language = ? "
        "AND status IN ('queued', 'working') AND id != ?", (video_id, target, except_id or -1))
    return row is not None


async def revoice(request_id: int, voice: str) -> EnqueueOutcome:
    """Mit anderer Stimme neu vertonen. Ein abgeschlossener Auftrag kommt mit
    der neuen Stimme ans Ende der Warteliste; die vorhandene Tonspur bleibt
    abspielbar, bis die neue sie ersetzt. Ein wartender Auftrag bekommt nur
    die andere Stimme."""
    voice = (voice or "").strip()
    job = await get(request_id)
    if not job:
        return _refused("Auftrag nicht gefunden")
    if not voice:
        return _refused("Keine Stimme gewählt")
    if job.status == "working":
        return _refused("Läuft gerade - erst abbrechen")
    if voice == job.voice and (job.status == "queued" or job.track_id):
        return _refused(f"Die Stimme {voice} ist schon gewählt")
    if job.status == "queued":
        await db.execute("UPDATE dub_requests SET voice = ? WHERE id = ? AND status = 'queued'",
                         (voice, request_id))
        return EnqueueOutcome(queued=True, request=await get(request_id))
    if not await db.fetch_one("SELECT id FROM videos WHERE id = ? AND status = 'ready'", (job.video_id,)):
        return _refused("Video ist nicht geladen")
    if await _open_duplicate(job.video_id, job.target_language, except_id=request_id):
        return _refused("ist bereits vorgemerkt")
    cursor = await db.execute(
        """UPDATE dub_requests
           SET voice = ?, status = 'queued', created_at = datetime('now'), worker = NULL,
               claimed_at = NULL, heartbeat_at = NULL, finished_at = NULL, progress = 0, note = NULL
           WHERE id = ? AND status IN ('done', 'error', 'skipped', 'cancelled')""", (voice, request_id))
    if cursor.rowcount != 1:
        return _refused("Auftrag hat sich inzwischen geändert")
    logger.info(f"[NACHVERTONUNG] {job.video_id} wird mit Stimme {voice} neu vertont")
    return EnqueueOutcome(queued=True, request=await get(request_id))


# ─── Liste und Zählungen ───────────────────────────────────────────────

class StatusCounts(BaseModel):
    queued: int = 0
    working: int = 0
    done: int = 0
    error: int = 0
    skipped: int = 0
    cancelled: int = 0


class TabCounts(BaseModel):
    all: int = 0
    working: int = 0
    queued: int = 0
    done: int = 0
    error: int = 0


async def counts() -> StatusCounts:
    rows = await db.fetch_all("SELECT status, COUNT(*) AS n FROM dub_requests GROUP BY status")
    return StatusCounts(**{r["status"]: r["n"] for r in rows if r["status"] in STATUSES})


def tab_counts(status_counts: StatusCounts) -> TabCounts:
    """Zahl je Reiter. "Alle" zählt auch die laufenden mit, die als Karten
    über der Liste stehen."""
    values = status_counts.model_dump()
    return TabCounts(all=sum(values.values()),
                     **{tab: sum(values[s] for s in statuses)
                        for tab, statuses in TAB_STATUSES.items() if tab != "all"})


class DubRequestPage(BaseModel):
    items: list[DubRequest]
    total: int
    offset: int
    limit: int


# Wartende in der Reihenfolge, in der sie abgeholt werden; Abgeschlossenes,
# das Neueste zuerst. Gruppen in der Reihenfolge von STATUSES der Seite.
_ORDER = """
    ORDER BY CASE d.status WHEN 'working' THEN 0 WHEN 'queued' THEN 1 WHEN 'done' THEN 2
                           WHEN 'error' THEN 3 WHEN 'skipped' THEN 4 ELSE 5 END,
             CASE WHEN d.status IN ('queued', 'working') THEN d.created_at END ASC,
             COALESCE(d.finished_at, d.created_at) DESC, d.id DESC
"""


async def list_page(tab: Tab = "all", offset: int = 0, limit: int = PAGE_SIZE) -> DubRequestPage:
    statuses = TAB_STATUSES[tab]
    marks = ", ".join("?" for _ in statuses)
    offset, limit = max(0, offset), max(1, min(limit, MAX_PAGE_SIZE))
    total = await db.fetch_val(
        f"SELECT COUNT(*) FROM dub_requests WHERE status IN ({marks})", statuses) or 0
    rows = await db.fetch_all(
        f"{_SELECT} WHERE d.status IN ({marks}) {_ORDER} LIMIT ? OFFSET ?", [*statuses, limit, offset])
    return DubRequestPage(items=[_to_model(r) for r in rows], total=total, offset=offset, limit=limit)


async def get(request_id: int) -> DubRequest | None:
    row = await db.fetch_one(f"{_SELECT} WHERE d.id = ?", (request_id,))
    return _to_model(row) if row else None


# ─── Laufende Aufträge und der Nachvertoner ────────────────────────────

_clock = dubbing_steps.StepClock()


class RunningDub(BaseModel):
    request: DubRequest
    steps: list[DubStep]
    activity: Optional[str] = None             # Notiz des Nachvertoners, wenn sie mehr sagt als der Schritt
    step_remaining_seconds: Optional[int] = None


async def running() -> list[RunningDub]:
    rows = await db.fetch_all(f"{_SELECT} WHERE d.status = 'working' {_ORDER}")
    jobs = [_to_model(r) for r in rows]
    now = time.monotonic()
    _clock.keep_only({(job.id, job.claimed_at or "") for job in jobs})
    result = []
    for job in jobs:
        _clock.observe(job.id, job.claimed_at, job.progress, job.note, now)
        result.append(RunningDub(
            request=job, steps=dubbing_steps.steps_for(job.progress, job.note),
            activity=dubbing_steps.activity(job.note, job.progress),
            step_remaining_seconds=_clock.remaining(job.id, job.claimed_at, job.progress, job.note, now)))
    return result


class WorkerPresence(BaseModel):
    last_seen: Optional[str] = None       # letztes Lebenszeichen (Weltzeit)
    seconds_ago: Optional[int] = None
    online: bool = False


async def worker_presence() -> WorkerPresence:
    """Letztes Lebenszeichen des Nachvertoners. Er meldet ohne Arbeit
    regelmäßig die Stimmen, bei der Arbeit den Fortschritt - an einer
    Vertonung oder an einem KI-Transkript."""
    row = await db.fetch_one(
        """SELECT MAX(seen) AS last_seen,
                  CAST((julianday('now') - julianday(MAX(seen))) * 86400 AS INTEGER) AS seconds_ago
           FROM (SELECT MAX(reported_at) AS seen FROM dub_voices
                 UNION ALL SELECT MAX(heartbeat_at) FROM dub_requests
                 UNION ALL SELECT MAX(heartbeat_at) FROM ai_transcriptions)""")
    if not row or row["last_seen"] is None:
        return WorkerPresence()
    seconds = max(0, row["seconds_ago"] or 0)
    return WorkerPresence(last_seen=row["last_seen"], seconds_ago=seconds,
                          online=seconds <= ONLINE_WITHIN_SECONDS)


class DubbingOverview(BaseModel):
    enabled: bool
    processing: bool                      # Vertonen an; aus: keine neuen Aufträge an den Nachvertoner
    counts: StatusCounts
    tabs: TabCounts
    worker: WorkerPresence
    running: list[RunningDub]


async def overview() -> DubbingOverview:
    """Alles, was die Seite im Takt neu braucht: Zählungen, Nachvertoner,
    laufende Aufträge mit ihren Schritten."""
    status_counts = await counts()
    return DubbingOverview(
        enabled=await is_enabled(), processing=await setting_values.is_on(PROCESSING_SWITCH),
        counts=status_counts, tabs=tab_counts(status_counts),
        worker=await worker_presence(), running=await running())


# ─── Arbeit des Nachvertoners ──────────────────────────────────────────

async def _release_stale() -> None:
    await db.execute(
        f"""UPDATE dub_requests
            SET status = 'queued', worker = NULL, claimed_at = NULL, progress = 0,
                note = 'Nachvertoner hat sich nicht mehr gemeldet - erneut in der Warteliste'
            WHERE status = 'working'
              AND COALESCE(heartbeat_at, claimed_at) < datetime('now', '-{STALE_AFTER_MINUTES} minutes')""")


async def claim(worker: str) -> DubRequest | None:
    """Den ältesten wartenden Auftrag für einen Nachvertoner reservieren.
    Angehalten (PROCESSING_SWITCH aus) gibt es keinen neuen Auftrag."""
    await _release_stale()
    if not await setting_values.is_on(PROCESSING_SWITCH):
        return None
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
    if cursor.rowcount != 1:
        return False
    row = await db.fetch_one("SELECT claimed_at, progress, note FROM dub_requests WHERE id = ?", (request_id,))
    _clock.observe(request_id, row["claimed_at"], row["progress"] or 0, row["note"], time.monotonic())
    return True


async def finish(request_id: int, status: Status, note: str | None = None) -> None:
    await db.execute(
        """UPDATE dub_requests
           SET status = ?, note = ?, finished_at = datetime('now'),
               progress = CASE WHEN ? = 'done' THEN 1 ELSE progress END
           WHERE id = ?""", (status, note, status, request_id))


async def report_failure(request_id: int, note: str, skipped: bool = False) -> bool:
    """Der Nachvertoner meldet einen Fehlschlag (oder: nichts zu tun).
    Gilt nur für laufende Aufträge; abgebrochene bleiben abgebrochen.
    False, wenn es den Auftrag nicht gibt."""
    job = await get(request_id)
    if not job:
        return False
    if job.status == "working":
        await finish(request_id, "skipped" if skipped else "error", note[:500])
    return True


# ─── Eingriffe aus der Oberfläche ──────────────────────────────────────

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


RemoveOutcome = Literal["removed", "missing", "open"]


async def remove(request_id: int, with_track: bool = False) -> RemoveOutcome:
    """Abgeschlossenen Auftrag aus der Liste nehmen. Die fertige Tonspur
    bleibt am Video - außer with_track: dann wird sie mit gelöscht."""
    job = await get(request_id)
    if not job:
        return "missing"
    if job.status in OPEN_STATUSES:
        return "open"
    if with_track and job.track_id:
        await audio_tracks.delete_track(job.video_id, job.track_id)
    await db.execute("DELETE FROM dub_requests WHERE id = ?", (request_id,))
    return "removed"

"""
TubeVault – Transkripte

Gesprochener Inhalt der Videos, durchsuchbar gemacht. Die Texte stammen aus
den Untertiteln der Quelle (vom Autor erstellte zuerst, sonst automatisch
erzeugte in der Originalsprache). Jedes Transkript wird in Abschnitte mit
Zeitangabe zerlegt; die Suche findet darin Wörter (Volltext) und Bedeutungen
(Einbettung je Abschnitt, siehe semantic_index) und kann an die Stelle im
Video springen.

Tabellen:
    transcripts          je Video: Sprache, Art, Stand (auch "keine Untertitel")
    transcript_chunks    Abschnitte mit Start und Ende in Sekunden
    transcript_fts       Volltext über die Abschnitte

Der Bestand wird im Hintergrund abgearbeitet, bewusst langsam: jeder Abruf
ist eine Anfrage an die Quelle, und die sperrt bei zu vielen.

KI-Transkripte: Hat die Quelle für ein Video keine Untertitel, kommt es auf
die Warteliste ai_transcriptions. Der Nachvertoner auf dem leistungsfähigen
Rechner holt sich von dort Aufträge, sobald er nichts zu vertonen hat, lässt
den Ton per Spracherkennung abschreiben und liefert die Sätze zurück. Solche
Transkripte tragen die Art "ai" und sind überall als KI-Transkript
gekennzeichnet - sie stammen nicht vom Autor und können Hörfehler enthalten.
"""
import asyncio
import logging
from typing import Literal, Optional

from pydantic import BaseModel

from app.config import SUBTITLES_DIR
from app.database import db
from app.services import subtitle_segments
from app.services.subtitle_segments import Segment

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS transcripts (
    video_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,            -- ok | none (keine Untertitel) | error
    language TEXT,
    kind TEXT,                       -- manual | auto | ai
    note TEXT,
    fetched_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS transcript_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    start REAL NOT NULL,
    end REAL NOT NULL,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transcript_chunks_video ON transcript_chunks(video_id, start);
CREATE VIRTUAL TABLE IF NOT EXISTS transcript_fts USING fts5(
    text, content='transcript_chunks', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2', prefix='2 3 4'
);
CREATE TRIGGER IF NOT EXISTS trg_transcript_chunk_insert AFTER INSERT ON transcript_chunks
BEGIN
    INSERT INTO transcript_fts (rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS trg_transcript_chunk_delete AFTER DELETE ON transcript_chunks
BEGIN
    INSERT INTO transcript_fts (transcript_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS trg_transcript_video_delete AFTER DELETE ON videos
BEGIN
    DELETE FROM transcript_chunks WHERE video_id = old.id;
    DELETE FROM transcripts WHERE video_id = old.id;
    DELETE FROM ai_transcriptions WHERE video_id = old.id;
END;
-- Warteliste für KI-Transkripte (Videos ohne Untertitel der Quelle)
CREATE TABLE IF NOT EXISTS ai_transcriptions (
    video_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'queued',   -- queued | working | done | error
    worker TEXT,
    note TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    claimed_at TEXT,
    heartbeat_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_ai_transcriptions_status ON ai_transcriptions(status, created_at);
"""

# Woher ein Transkript stammt - so steht es überall in der Oberfläche
KIND_LABELS = {
    "manual": "Untertitel vom Autor",
    "auto": "Untertitel der Quelle (automatisch erzeugt)",
    "ai": "KI-Transkript",
}
_FILE_PREFIX = {"manual": "", "auto": "a.", "ai": "ki."}
# Ohne Lebenszeichen gilt ein abgeholter KI-Auftrag nach dieser Zeit als verwaist
AI_STALE_AFTER_MINUTES = 30

# Ein Abschnitt fasst Sätze zusammen, bis er etwa so lang ist: lang genug für
# einen Gedanken, kurz genug, um beim Sprung an der richtigen Stelle zu landen
CHUNK_CHARS = 700
# Nach einer längeren Sprechpause beginnt ein neuer Abschnitt - sonst läge
# die Sprungmarke weit vor der Textstelle
CHUNK_MAX_GAP_SECONDS = 20
# Pause zwischen zwei Abrufen bei der Quelle. Bewusst lang: jeder Abruf zählt
# bei der Quelle mit, und zu viele bringen ihr die Sperre "kein Automat?" ein,
# die dann auch die Downloads trifft. Die Quelle drosselt Untertitel
# streng und ohne festen Wert, deshalb passt sich der Abstand an: nach jeder
# Bremsung wird er verdoppelt, nach einer Reihe geglückter Abrufe wieder
# langsam kürzer.
SECONDS_PER_FETCH = 120
MAX_SECONDS_PER_FETCH = 1800
SPEED_UP_AFTER = 20          # geglückte Abrufe in Folge, bis der Abstand sinkt
# Pause, wenn die Quelle bremst oder nicht erreichbar ist
BACKOFF_SECONDS = 3600
# Fehlgeschlagene Abrufe frühestens nach so vielen Tagen erneut versuchen
RETRY_ERROR_DAYS = 7
_BLOCK_MARKERS = ("429", "too many requests", "sign in to confirm", "timed out", "timeout",
                  "name resolution", "connection refused", "network is unreachable")

Status = Literal["ok", "none", "error"]


class Passage(BaseModel):
    """Eine Textstelle in einem Video."""
    chunk_id: int
    video_id: str
    start: float
    text: str
    kind: Optional[str] = None        # Herkunft des Transkripts (manual | auto | ai)


class FetchResult(BaseModel):
    status: Status
    language: Optional[str] = None
    kind: Optional[str] = None
    chunks: int = 0
    note: Optional[str] = None


async def install_schema(connection) -> None:
    await connection.executescript(SCHEMA_SQL)
    # Videos, für die die Quelle schon "keine Untertitel" gemeldet hat
    await connection.execute(
        """INSERT OR IGNORE INTO ai_transcriptions (video_id)
           SELECT video_id FROM transcripts WHERE status = 'none'""")
    await connection.commit()


def into_chunks(sentences: list[Segment]) -> list[Segment]:
    """Sätze zu Abschnitten von etwa CHUNK_CHARS Zeichen bündeln; eine längere
    Sprechpause trennt immer."""
    chunks: list[Segment] = []
    current: Optional[Segment] = None
    for sentence in sentences:
        if current and (len(current.text) + len(sentence.text) + 1 > CHUNK_CHARS
                        or sentence.start - current.end > CHUNK_MAX_GAP_SECONDS):
            chunks.append(current)
            current = None
        if current is None:
            current = sentence.model_copy()
        else:
            current.end = sentence.end
            current.text = f"{current.text} {sentence.text}"
    if current:
        chunks.append(current)
    return chunks


async def store(video_id: str, language: str, kind: str, sentences: list[Segment]) -> int:
    """Transkript eines Videos ablegen (ersetzt ein vorhandenes)."""
    chunks = into_chunks(sentences)
    await db.execute("DELETE FROM transcript_chunks WHERE video_id = ?", (video_id,))
    for chunk in chunks:
        await db.execute(
            "INSERT INTO transcript_chunks (video_id, start, end, text) VALUES (?, ?, ?, ?)",
            (video_id, chunk.start, chunk.end, chunk.text))
    await _mark(video_id, "ok" if chunks else "none", language, kind)
    return len(chunks)


async def _mark(video_id: str, status: Status, language: str | None = None,
                kind: str | None = None, note: str | None = None) -> None:
    await db.execute(
        """INSERT INTO transcripts (video_id, status, language, kind, note)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(video_id) DO UPDATE SET status = excluded.status,
               language = excluded.language, kind = excluded.kind, note = excluded.note,
               fetched_at = datetime('now')""",
        (video_id, status, language, kind, note))


def _download_caption(video_id: str, preferred_language: str | None):
    """Synchron (im Thread): passende Untertitel bei der Quelle finden und laden.
    Liefert (Auswahl, Text) oder (None, None), wenn es keine gibt."""
    from app.utils.pytube_client import make_youtube
    choice = make_youtube(f"https://www.youtube.com/watch?v={video_id}").caption_choice(preferred_language)
    if not choice:
        return None, None
    from app.utils import source_net
    with source_net.client(timeout=30) as http:
        response = http.get(choice.url)
    response.raise_for_status()
    return choice, response.text


def _subtitle_file(video_id: str, language: str, kind: str):
    """Ablageort der Untertitel: automatisch erzeugte tragen die Kennung "a.",
    KI-Transkripte "ki." - so bleibt die Herkunft auch an der Datei sichtbar."""
    return SUBTITLES_DIR / video_id / f"{_FILE_PREFIX.get(kind, 'a.')}{language}.vtt"


class DubTranscript(BaseModel):
    """Transkript für die Nachvertonung: Sätze mit Zeitangabe."""
    language: str
    kind: str                          # manual | auto | ai
    segments: list[Segment]


class DubTranscriptAnswer(BaseModel):
    transcript: Optional[DubTranscript] = None
    reason: Optional[str] = None       # warum es keines gibt


async def for_dubbing(video_id: str, use: str) -> DubTranscriptAnswer:
    """Transkript eines Videos für die Nachvertonung. Die Originalsprache
    bestimmt die Quelle selbst - sie muss am Video nicht bekannt sein. Liegt
    noch kein Transkript vor, wird es jetzt geholt. Gibt es keines, steht der
    Grund in der Antwort (der Vertonungsdienst transkribiert dann selbst)."""
    def missing(reason: str) -> DubTranscriptAnswer:
        return DubTranscriptAnswer(reason=reason)

    if use == "never":
        return missing("Untertitel sollen für diesen Auftrag nicht verwendet werden")

    async def state():
        return await db.fetch_one(
            "SELECT status, language, kind FROM transcripts WHERE video_id = ?", (video_id,))

    row = await state()
    path = _subtitle_file(video_id, row["language"], row["kind"]) if row and row["status"] == "ok" else None
    if not row or row["status"] == "error" or (path and not path.exists()):
        try:
            await fetch(video_id)
        except Exception as e:
            return missing(f"Untertitel bei der Quelle nicht abrufbar: {str(e)[:160]}")
        row = await state()
    if not row or row["status"] != "ok":
        return missing("Die Quelle hat keine Untertitel in der Originalsprache")
    if row["kind"] != "manual" and use == "manual":
        return missing("Es gibt nur automatisch erzeugte Untertitel; gewünscht waren vom Autor erstellte")
    segments = subtitle_segments.segments_from_file(_subtitle_file(video_id, row["language"], row["kind"]))
    if not segments:
        return missing("Die Untertitel enthalten keinen Text")
    return DubTranscriptAnswer(
        transcript=DubTranscript(language=row["language"], kind=row["kind"], segments=segments))


async def fetch(video_id: str) -> FetchResult:
    """Transkript eines Videos bei der Quelle holen und ablegen. Fehler der
    Quelle werden durchgereicht - der Aufrufer entscheidet, ob er pausiert."""
    language = await db.fetch_val("SELECT language FROM videos WHERE id = ?", (video_id,))
    choice, text = await asyncio.to_thread(_download_caption, video_id, language)
    if not choice:
        await _mark(video_id, "none")
        await enqueue_ai(video_id)       # Ersatz: KI-Transkript vom Ton
        return FetchResult(status="none")

    # Die Untertitel auch für Wiedergabe und Nachvertonung ablegen
    path = _subtitle_file(video_id, choice.language, choice.kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    # Die Sprache der Untertitel ist die Sprache des Videos, falls noch unbekannt
    await db.execute(
        "UPDATE videos SET language = ? WHERE id = ? AND COALESCE(language, '') = ''",
        (choice.language, video_id))

    sentences = subtitle_segments.into_sentences(
        subtitle_segments.without_repeats(subtitle_segments.parse_vtt(text)))
    count = await store(video_id, choice.language, choice.kind, sentences)
    return FetchResult(status="ok" if count else "none", language=choice.language,
                       kind=choice.kind, chunks=count)


# ─── Bestand abarbeiten ───────────────────────────────────────────────

_WAITING_SQL = f"""
    FROM videos v LEFT JOIN transcripts t ON t.video_id = v.id
    WHERE v.status = 'ready' AND COALESCE(v.source, 'youtube') = 'youtube'
      AND v.id NOT LIKE 'local\\_%' ESCAPE '\\'
      AND (t.video_id IS NULL
           OR (t.status = 'error' AND t.fetched_at < datetime('now', '-{RETRY_ERROR_DAYS} days')))
"""


async def pending() -> int:
    return await db.fetch_val(f"SELECT COUNT(*) {_WAITING_SQL}") or 0


async def counts() -> dict[str, int]:
    rows = await db.fetch_all("SELECT status, COUNT(*) AS n FROM transcripts GROUP BY status")
    result = {"ok": 0, "none": 0, "error": 0}
    result.update({row["status"]: row["n"] for row in rows})
    result["chunks"] = await db.fetch_val("SELECT COUNT(*) FROM transcript_chunks") or 0
    result["pending"] = await pending()
    return result


def is_blocked(error: Exception) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in _BLOCK_MARKERS)


class _Pace:
    """Aktueller Abstand zwischen zwei Abrufen."""
    seconds = SECONDS_PER_FETCH
    successes = 0

    @classmethod
    def blocked(cls) -> None:
        cls.seconds = min(cls.seconds * 2, MAX_SECONDS_PER_FETCH)
        cls.successes = 0

    @classmethod
    def succeeded(cls) -> None:
        cls.successes += 1
        if cls.successes >= SPEED_UP_AFTER:
            cls.seconds = max(SECONDS_PER_FETCH, int(cls.seconds * 0.8))
            cls.successes = 0


def seconds_per_fetch() -> int:
    return _Pace.seconds


async def background_fetch() -> None:
    """Hintergrundlauf: neueste Videos zuerst. Bremst die Quelle, ruht der
    Lauf und fragt danach in größerem Abstand."""
    await asyncio.sleep(90)
    while True:
        pause = _Pace.seconds
        try:
            row = await db.fetch_one(
                f"SELECT v.id {_WAITING_SQL} ORDER BY v.download_date DESC, v.id LIMIT 1")
            if not row:
                pause = 600
            else:
                video_id = row["id"]
                try:
                    result = await fetch(video_id)
                    _Pace.succeeded()
                    logger.debug(f"[TRANSKRIPT] {video_id}: {result.status} ({result.chunks} Abschnitte)")
                except Exception as e:
                    if is_blocked(e):
                        _Pace.blocked()
                        logger.info(f"[TRANSKRIPT] Quelle bremst, Pause {BACKOFF_SECONDS // 60} Min, "
                                    f"danach alle {_Pace.seconds} s: {str(e)[:120]}")
                        pause = BACKOFF_SECONDS
                    else:
                        await _mark(video_id, "error", note=str(e)[:300])
        except Exception as e:
            logger.warning(f"[TRANSKRIPT] Hintergrundlauf: {e.__class__.__name__}: {e}")
            pause = 300
        await asyncio.sleep(pause)


# ─── KI-Transkripte ───────────────────────────────────────────────────

class AiJob(BaseModel):
    """Ein KI-Transkript-Auftrag für den Nachvertoner."""
    video_id: str
    title: Optional[str] = None
    duration: Optional[int] = None
    language: Optional[str] = None     # Sprache des Videos, falls bekannt (sonst erkennen)


class AiResult(BaseModel):
    language: str                      # Kürzel der erkannten Sprache, z.B. "de"
    segments: list[Segment]


async def enqueue_ai(video_id: str) -> None:
    await db.execute("INSERT OR IGNORE INTO ai_transcriptions (video_id) VALUES (?)", (video_id,))


async def _release_stale_ai() -> None:
    await db.execute(
        f"""UPDATE ai_transcriptions
            SET status = 'queued', worker = NULL, claimed_at = NULL,
                note = 'Bearbeiter hat sich nicht mehr gemeldet - erneut in der Warteliste'
            WHERE status = 'working'
              AND COALESCE(heartbeat_at, claimed_at) < datetime('now', '-{AI_STALE_AFTER_MINUTES} minutes')""")


async def claim_ai(worker: str) -> Optional[AiJob]:
    """Den nächsten KI-Auftrag reservieren: zuletzt geladene Videos zuerst."""
    await _release_stale_ai()
    row = await db.fetch_one(
        """SELECT a.video_id FROM ai_transcriptions a JOIN videos v ON v.id = a.video_id
           WHERE a.status = 'queued' AND v.status = 'ready'
           ORDER BY v.download_date DESC, a.video_id LIMIT 1""")
    if not row:
        return None
    cursor = await db.execute(
        """UPDATE ai_transcriptions SET status = 'working', worker = ?, note = NULL,
               claimed_at = datetime('now'), heartbeat_at = datetime('now')
           WHERE video_id = ? AND status = 'queued'""", (worker, row["video_id"]))
    if cursor.rowcount != 1:
        return None
    video = await db.fetch_one(
        "SELECT id, title, duration, language FROM videos WHERE id = ?", (row["video_id"],))
    return AiJob(video_id=video["id"], title=video["title"], duration=video["duration"],
                 language=(video["language"] or None))


async def heartbeat_ai(video_id: str, note: Optional[str] = None) -> bool:
    cursor = await db.execute(
        """UPDATE ai_transcriptions SET heartbeat_at = datetime('now'), note = COALESCE(?, note)
           WHERE video_id = ? AND status = 'working'""", (note, video_id))
    return cursor.rowcount == 1


async def finish_ai(video_id: str, result: AiResult) -> int:
    """KI-Transkript übernehmen: Abschnitte für die Suche, Untertitel-Datei
    "ki.<sprache>.vtt" für die Wiedergabe. Ein Transkript der Quelle, das
    inzwischen eingetroffen ist, wird nicht überschrieben."""
    job = await db.fetch_one("SELECT status FROM ai_transcriptions WHERE video_id = ?", (video_id,))
    if not job or job["status"] != "working":
        raise ValueError("Auftrag ist nicht in Arbeit")
    existing = await db.fetch_one("SELECT status, kind FROM transcripts WHERE video_id = ?", (video_id,))
    language = result.language.strip().lower()[:8]
    sentences = [s for s in result.segments if s.text.strip() and s.end > s.start]
    if not existing or existing["status"] != "ok" or existing["kind"] == "ai":
        path = _subtitle_file(video_id, language, "ai")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(subtitle_segments.to_vtt(
            sentences, note="KI-Transkript (Spracherkennung, nicht vom Autor)"), encoding="utf-8")
        count = await store(video_id, language, "ai", sentences)
        await db.execute(
            "UPDATE videos SET language = ? WHERE id = ? AND COALESCE(language, '') = ''",
            (language, video_id))
    else:
        count = 0
    await db.execute(
        """UPDATE ai_transcriptions SET status = 'done', finished_at = datetime('now'), note = ?
           WHERE video_id = ?""", (f"{len(sentences)} Sätze, {language}", video_id))
    return count


async def fail_ai(video_id: str, note: str) -> None:
    await db.execute(
        """UPDATE ai_transcriptions SET status = 'error', finished_at = datetime('now'), note = ?
           WHERE video_id = ? AND status = 'working'""", (note[:500], video_id))


async def ai_counts() -> dict[str, int]:
    rows = await db.fetch_all("SELECT status, COUNT(*) AS n FROM ai_transcriptions GROUP BY status")
    result = {"queued": 0, "working": 0, "done": 0, "error": 0}
    result.update({row["status"]: row["n"] for row in rows})
    return result


# ─── Suchen ───────────────────────────────────────────────────────────

async def keyword_passages(match: str, limit: int = 400) -> list[Passage]:
    """Abschnitte, in denen die Suchwörter vorkommen, beste zuerst.
    match ist ein fertiger Volltext-Ausdruck (search_index.build_match)."""
    rows = await db.fetch_all(
        """SELECT c.id AS chunk_id, c.video_id, c.start, c.text, t.kind
           FROM transcript_fts f JOIN transcript_chunks c ON c.id = f.rowid
           LEFT JOIN transcripts t ON t.video_id = c.video_id
           WHERE transcript_fts MATCH ? ORDER BY bm25(transcript_fts) LIMIT ?""",
        (match, limit))
    return [Passage(**dict(row)) for row in rows]


async def passages_by_id(chunk_ids: list[int]) -> dict[int, Passage]:
    if not chunk_ids:
        return {}
    marks = ",".join("?" * len(chunk_ids))
    rows = await db.fetch_all(
        f"""SELECT c.id AS chunk_id, c.video_id, c.start, c.text, t.kind
            FROM transcript_chunks c LEFT JOIN transcripts t ON t.video_id = c.video_id
            WHERE c.id IN ({marks})""",
        chunk_ids)
    return {row["chunk_id"]: Passage(**dict(row)) for row in rows}

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
"""
import asyncio
import logging
from typing import Literal, Optional

import httpx
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
    kind TEXT,                       -- manual | auto
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
END;
"""

# Ein Abschnitt fasst Sätze zusammen, bis er etwa so lang ist: lang genug für
# einen Gedanken, kurz genug, um beim Sprung an der richtigen Stelle zu landen
CHUNK_CHARS = 700
# Nach einer längeren Sprechpause beginnt ein neuer Abschnitt - sonst läge
# die Sprungmarke weit vor der Textstelle
CHUNK_MAX_GAP_SECONDS = 20
# Pause zwischen zwei Abrufen bei der Quelle
SECONDS_PER_FETCH = 20
# Pause, wenn die Quelle bremst oder nicht erreichbar ist
BACKOFF_SECONDS = 1800
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


class FetchResult(BaseModel):
    status: Status
    language: Optional[str] = None
    kind: Optional[str] = None
    chunks: int = 0
    note: Optional[str] = None


async def install_schema(connection) -> None:
    await connection.executescript(SCHEMA_SQL)
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
    response = httpx.get(choice.url, timeout=30)
    response.raise_for_status()
    return choice, response.text


async def fetch(video_id: str) -> FetchResult:
    """Transkript eines Videos bei der Quelle holen und ablegen. Fehler der
    Quelle werden durchgereicht - der Aufrufer entscheidet, ob er pausiert."""
    language = await db.fetch_val("SELECT language FROM videos WHERE id = ?", (video_id,))
    choice, text = await asyncio.to_thread(_download_caption, video_id, language)
    if not choice:
        await _mark(video_id, "none")
        return FetchResult(status="none")

    # Die Untertitel auch für die Wiedergabe ablegen
    folder = SUBTITLES_DIR / video_id
    folder.mkdir(parents=True, exist_ok=True)
    code = choice.language if choice.kind == "manual" else f"a.{choice.language}"
    (folder / f"{code}.vtt").write_text(text, encoding="utf-8")

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


async def background_fetch() -> None:
    """Hintergrundlauf: neueste Videos zuerst, ein Abruf alle SECONDS_PER_FETCH
    Sekunden. Bremst die Quelle, ruht der Lauf, statt weiter anzufragen."""
    await asyncio.sleep(90)
    while True:
        pause = SECONDS_PER_FETCH
        try:
            row = await db.fetch_one(
                f"SELECT v.id {_WAITING_SQL} ORDER BY v.download_date DESC, v.id LIMIT 1")
            if not row:
                pause = 600
            else:
                video_id = row["id"]
                try:
                    result = await fetch(video_id)
                    logger.debug(f"[TRANSKRIPT] {video_id}: {result.status} ({result.chunks} Abschnitte)")
                except Exception as e:
                    if is_blocked(e):
                        logger.info(f"[TRANSKRIPT] Quelle bremst, Pause {BACKOFF_SECONDS // 60} Min: {str(e)[:120]}")
                        pause = BACKOFF_SECONDS
                    else:
                        await _mark(video_id, "error", note=str(e)[:300])
        except Exception as e:
            logger.warning(f"[TRANSKRIPT] Hintergrundlauf: {e.__class__.__name__}: {e}")
            pause = 300
        await asyncio.sleep(pause)


# ─── Suchen ───────────────────────────────────────────────────────────

async def keyword_passages(match: str, limit: int = 400) -> list[Passage]:
    """Abschnitte, in denen die Suchwörter vorkommen, beste zuerst.
    match ist ein fertiger Volltext-Ausdruck (search_index.build_match)."""
    rows = await db.fetch_all(
        """SELECT c.id AS chunk_id, c.video_id, c.start, c.text
           FROM transcript_fts f JOIN transcript_chunks c ON c.id = f.rowid
           WHERE transcript_fts MATCH ? ORDER BY bm25(transcript_fts) LIMIT ?""",
        (match, limit))
    return [Passage(**dict(row)) for row in rows]


async def passages_by_id(chunk_ids: list[int]) -> dict[int, Passage]:
    if not chunk_ids:
        return {}
    marks = ",".join("?" * len(chunk_ids))
    rows = await db.fetch_all(
        f"SELECT id AS chunk_id, video_id, start, text FROM transcript_chunks WHERE id IN ({marks})",
        chunk_ids)
    return {row["chunk_id"]: Passage(**dict(row)) for row in rows}

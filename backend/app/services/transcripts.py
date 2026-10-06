"""
TubeVault – Transkripte

Gesprochener Inhalt der Videos, durchsuchbar gemacht. Jedes Transkript wird
in Abschnitte mit Zeitangabe zerlegt; die Suche findet darin Wörter (Volltext) und Bedeutungen
(Einbettung je Abschnitt, siehe semantic_index) und kann an die Stelle im
Video springen.

Tabellen:
    transcripts          je Video: Sprache, Art, Stand (auch "keine Untertitel")
    transcript_chunks    Abschnitte mit Start und Ende in Sekunden
    transcript_fts       Volltext über die Abschnitte

Woher die Texte kommen: Untertitel werden NICHT mehr bei der Quelle geholt -
die vielen Abrufe brachten ihr den Verdacht auf einen Automaten ein. Die
Transkripte entstehen stattdessen lokal per Spracherkennung: Der Nachvertoner
auf dem leistungsfähigen Rechner holt sich einen Auftrag, sobald der
Vertonungsdienst frei ist und nichts zu vertonen ansteht, lässt den Ton
abschreiben und liefert die Sätze zurück. Reihenfolge: immer das zuletzt
geladene Video ohne Transkript - neu geladene kommen also sofort an die Reihe,
danach geht es mit den nächstälteren weiter.

Solche Transkripte tragen die Art "ai" und sind überall als KI-Transkript
gekennzeichnet - sie stammen nicht vom Autor und können Hörfehler enthalten.
Früher geholte Untertitel der Quelle (Art "manual" oder "auto") bleiben
bestehen und werden nicht ersetzt.

ai_transcriptions hält den Stand je Video (working | done | error, sowie
queued für einen wieder freigegebenen Auftrag); was dort nicht steht und
noch kein Transkript hat, wartet.
"""
from typing import Literal, Optional

from pydantic import BaseModel

from app.config import SUBTITLES_DIR
from app.database import db
from app.services import subtitle_segments
from app.services.subtitle_segments import Segment

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
-- Stand der KI-Transkripte je Video (siehe Kopf)
CREATE TABLE IF NOT EXISTS ai_transcriptions (
    video_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'queued',   -- queued (wieder frei) | working | done | error
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

Status = Literal["ok", "none", "error"]


class Passage(BaseModel):
    """Eine Textstelle in einem Video."""
    chunk_id: int
    video_id: str
    start: float
    text: str
    kind: Optional[str] = None        # Herkunft des Transkripts (manual | auto | ai)


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
    """Vorhandenes Transkript eines Videos für die Nachvertonung. Gibt es
    keines, steht der Grund in der Antwort (der Vertonungsdienst transkribiert
    dann selbst). Bei der Quelle wird nichts geholt."""
    def missing(reason: str) -> DubTranscriptAnswer:
        return DubTranscriptAnswer(reason=reason)

    if use == "never":
        return missing("Untertitel sollen für diesen Auftrag nicht verwendet werden")

    row = await db.fetch_one(
        "SELECT status, language, kind FROM transcripts WHERE video_id = ?", (video_id,))
    if not row or row["status"] != "ok":
        return missing("Für dieses Video gibt es noch kein Transkript")
    if row["kind"] != "manual" and use == "manual":
        return missing(f"Es gibt nur ein {KIND_LABELS[row['kind']]}; gewünscht waren Untertitel vom Autor")
    path = _subtitle_file(video_id, row["language"], row["kind"])
    if not path.exists():
        return missing("Die Untertitel-Datei des Transkripts fehlt")
    segments = subtitle_segments.segments_from_file(path)
    if not segments:
        return missing("Die Untertitel enthalten keinen Text")
    return DubTranscriptAnswer(
        transcript=DubTranscript(language=row["language"], kind=row["kind"], segments=segments))


# ─── Bestand ──────────────────────────────────────────────────────────

# Videos, die auf ein KI-Transkript warten: fertig geladen, keine Musik (kaum
# Sprache, nur Rechenzeit), noch ohne Transkript und nicht schon in Arbeit,
# fertig oder gescheitert
_WAITING_SQL = """
    FROM videos v
    LEFT JOIN transcripts t ON t.video_id = v.id
    LEFT JOIN ai_transcriptions a ON a.video_id = v.id
    WHERE v.status = 'ready' AND COALESCE(v.is_music, 0) = 0
      AND (t.video_id IS NULL OR t.status != 'ok')
      AND (a.video_id IS NULL OR a.status = 'queued')
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


async def _release_stale_ai() -> None:
    await db.execute(
        f"""UPDATE ai_transcriptions
            SET status = 'queued', worker = NULL, claimed_at = NULL,
                note = 'Bearbeiter hat sich nicht mehr gemeldet - erneut in der Warteliste'
            WHERE status = 'working'
              AND COALESCE(heartbeat_at, claimed_at) < datetime('now', '-{AI_STALE_AFTER_MINUTES} minutes')""")


async def claim_ai(worker: str) -> Optional[AiJob]:
    """Den nächsten KI-Auftrag reservieren: immer das zuletzt geladene Video
    ohne Transkript. Neu geladene kommen so sofort an die Reihe, danach geht
    es mit den nächstälteren weiter."""
    await _release_stale_ai()
    row = await db.fetch_one(f"SELECT v.id {_WAITING_SQL} ORDER BY v.download_date DESC, v.id LIMIT 1")
    if not row:
        return None
    cursor = await db.execute(
        """INSERT INTO ai_transcriptions (video_id, status, worker, claimed_at, heartbeat_at)
           VALUES (?, 'working', ?, datetime('now'), datetime('now'))
           ON CONFLICT(video_id) DO UPDATE SET status = 'working', worker = excluded.worker,
               note = NULL, claimed_at = excluded.claimed_at, heartbeat_at = excluded.heartbeat_at
           WHERE ai_transcriptions.status = 'queued'""", (row["id"], worker))
    if cursor.rowcount != 1:
        return None
    video = await db.fetch_one(
        "SELECT id, title, duration, language FROM videos WHERE id = ?", (row["id"],))
    return AiJob(video_id=video["id"], title=video["title"], duration=video["duration"],
                 language=(video["language"] or None))


async def heartbeat_ai(video_id: str, note: Optional[str] = None) -> bool:
    cursor = await db.execute(
        """UPDATE ai_transcriptions SET heartbeat_at = datetime('now'), note = COALESCE(?, note)
           WHERE video_id = ? AND status = 'working'""", (note, video_id))
    return cursor.rowcount == 1


async def finish_ai(video_id: str, result: AiResult) -> int:
    """KI-Transkript übernehmen: Abschnitte für die Suche, Untertitel-Datei
    "ki.<sprache>.vtt" für die Wiedergabe. Ein früher geholtes Transkript
    der Quelle wird nicht überschrieben."""
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

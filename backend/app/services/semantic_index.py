"""
TubeVault – Bedeutungssuche (Einbettungen) v1.0.0

Optionale Erweiterung zur Wortsuche: Jedes Video bekommt einen Vektor, der
seinen Inhalt beschreibt (Titel, Kanal, Tags, Anfang der Beschreibung). Eine
Suchanfrage wird ebenso in einen Vektor gewandelt; ähnliche Vektoren sind
inhaltlich verwandte Videos - auch wenn kein Wort übereinstimmt ("Brot
backen" findet "Sauerteig ansetzen").

Die Vektoren rechnet ein lokaler KI-Dienst mit OpenAI-kompatibler
Schnittstelle (Einstellungen ai.url, ai.embedding_model). TubeVault
speichert sie und vergleicht selbst. Ist der Dienst aus oder nicht
erreichbar, arbeitet die Suche unverändert als reine Wortsuche - nichts
hängt davon ab.

Aufbau:
    video_embeddings   video_id → Vektor (float32) samt Modell und Textprüfsumme
    semantic_dirty     Warteliste geänderter Videos (per Trigger gefüllt)
"""
import asyncio
import hashlib
import json
import logging
import time
from typing import Optional

import httpx

from app.database import db

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS video_embeddings (
    video_id TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    vector BLOB NOT NULL,
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS semantic_dirty (
    video_id TEXT PRIMARY KEY
);
CREATE TRIGGER IF NOT EXISTS trg_semantic_dirty_insert AFTER INSERT ON videos
BEGIN
    INSERT OR IGNORE INTO semantic_dirty (video_id) VALUES (new.id);
END;
CREATE TRIGGER IF NOT EXISTS trg_semantic_dirty_update
AFTER UPDATE OF title, channel_name, description, tags, status ON videos
BEGIN
    INSERT OR IGNORE INTO semantic_dirty (video_id) VALUES (new.id);
END;
CREATE TRIGGER IF NOT EXISTS trg_semantic_delete AFTER DELETE ON videos
BEGIN
    DELETE FROM video_embeddings WHERE video_id = old.id;
    DELETE FROM semantic_dirty WHERE video_id = old.id;
END;
"""

# Kleine Stapel: der KI-Dienst arbeitet nacheinander, eine Suchanfrage soll
# während des Einbettens nicht lange hinter einem Stapel warten.
_BATCH = 16
_DESCRIPTION_CHARS = 1200
_REQUEST_TIMEOUT_S = 60
_QUERY_TIMEOUT_S = 4            # die Suche wartet nicht lange auf die KI
_AVAILABILITY_TTL_S = 60
_IDLE_PAUSE_S = 300
# Welche Videos gelten als inhaltlich verwandt? Zwei Bedingungen, beide nötig:
#   1. Mindest-Ähnlichkeit (Einstellung ai.min_similarity). An echten Titeln
#      gemessen (bge-m3): passende Treffer ab etwa 0,50, Zufallstreffer bei
#      sinnlosen Anfragen bis etwa 0,48.
#   2. Das Video ragt aus der Masse heraus: mindestens MIN_Z
#      Standardabweichungen über dem Durchschnitt aller Videos. Das fängt
#      Anfragen ab, zu denen alles ein wenig passt.
# Höchstens TOP_K Treffer.
TOP_K = 80
MIN_Z = 2.5
SMALL_COLLECTION = 200   # darunter sagt die Streuung wenig

_available: tuple[float, bool] = (0.0, False)
_matrix = None                  # (ids, numpy-Matrix, Stempel)
_query_cache: dict[tuple[str, str], list[float]] = {}


async def install_schema(connection) -> None:
    await connection.executescript(SCHEMA_SQL)


# ─── Einstellungen und Erreichbarkeit ─────────────────────────────────

async def _setting(key: str) -> str:
    from app import settings_schema
    value = await db.fetch_val("SELECT value FROM settings WHERE key = ?", (key,))
    return value if value not in (None, "") else settings_schema.BY_KEY[key].default


async def config() -> Optional[tuple[str, str]]:
    """(Adresse, Modell), wenn die Erweiterung eingeschaltet und eingerichtet ist."""
    if (await _setting("ai.enabled")) != "true":
        return None
    url = (await _setting("ai.url")).strip().rstrip("/")
    model = (await _setting("ai.embedding_model")).strip()
    return (url, model) if url and model else None


async def _embed(texts: list[str], url: str, model: str, timeout: float) -> list[list[float]]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(f"{url}/embeddings", json={"model": model, "input": texts})
        response.raise_for_status()
        data = sorted(response.json()["data"], key=lambda item: item.get("index", 0))
    return [item["embedding"] for item in data]


async def available() -> bool:
    """Ist der KI-Dienst gerade erreichbar? (kurz zwischengespeichert)"""
    global _available
    checked, ok = _available
    if time.time() - checked < _AVAILABILITY_TTL_S:
        return ok
    cfg = await config()
    ok = False
    if cfg:
        try:
            await _embed(["bereit"], cfg[0], cfg[1], timeout=_QUERY_TIMEOUT_S)
            ok = True
        except Exception as e:
            logger.debug(f"[BEDEUTUNG] KI-Dienst nicht erreichbar: {e.__class__.__name__}")
    _available = (time.time(), ok)
    return ok


def reset_availability() -> None:
    global _available
    _available = (0.0, False)


# ─── Index pflegen ────────────────────────────────────────────────────

def document_text(title: str, channel: str | None, tags, description: str | None) -> str:
    """Der Text, der ein Video für die Bedeutungssuche beschreibt."""
    try:
        tag_list = json.loads(tags) if isinstance(tags, str) else (tags or [])
    except (ValueError, TypeError):
        tag_list = []
    parts = [title or "", f"Kanal: {channel}" if channel else "",
             "Stichworte: " + ", ".join(map(str, tag_list[:20])) if tag_list else "",
             (description or "")[:_DESCRIPTION_CHARS]]
    return "\n".join(p for p in parts if p).strip()


def _pack(vector: list[float]) -> bytes:
    import numpy as np
    array = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(array))
    return (array / norm if norm else array).tobytes()


async def pending() -> int:
    return await db.fetch_val("SELECT COUNT(*) FROM semantic_dirty") or 0


async def index_batch(url: str, model: str) -> int:
    """Einen Stapel wartender Videos einbetten. Gibt die Zahl der bearbeiteten zurück."""
    from app.services.text_resolver import get_description

    ids = [r["video_id"] for r in await db.fetch_all(
        "SELECT video_id FROM semantic_dirty LIMIT ?", (_BATCH,))]
    if not ids:
        return 0
    todo: list[tuple[str, str, str]] = []   # (video_id, text, hash)
    for video_id in ids:
        row = await db.fetch_one(
            "SELECT id, title, channel_name, tags, status FROM videos WHERE id = ?", (video_id,))
        if not row or row["status"] != "ready":
            await db.execute("DELETE FROM video_embeddings WHERE video_id = ?", (video_id,))
            continue
        text = document_text(row["title"], row["channel_name"], row["tags"], await get_description(video_id))
        text_hash = hashlib.sha256(f"{model}\n{text}".encode()).hexdigest()
        known = await db.fetch_val(
            "SELECT text_hash FROM video_embeddings WHERE video_id = ?", (video_id,))
        if known != text_hash:
            todo.append((video_id, text, text_hash))

    if todo:
        vectors = await _embed([text for _, text, _ in todo], url, model, timeout=_REQUEST_TIMEOUT_S)
        for (video_id, _text, text_hash), vector in zip(todo, vectors):
            await db.conn.execute(
                """INSERT INTO video_embeddings (video_id, model, text_hash, vector)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(video_id) DO UPDATE SET model = excluded.model,
                       text_hash = excluded.text_hash, vector = excluded.vector,
                       updated_at = datetime('now', 'localtime')""",
                (video_id, model, text_hash, _pack(vector)))
    placeholders = ",".join("?" * len(ids))
    await db.conn.execute(f"DELETE FROM semantic_dirty WHERE video_id IN ({placeholders})", ids)
    await db.conn.commit()
    return len(ids)


async def mark_missing() -> None:
    """Videos ohne Vektor (oder mit Vektor eines anderen Modells) vormerken."""
    cfg = await config()
    if not cfg:
        return
    await db.execute(
        """INSERT OR IGNORE INTO semantic_dirty (video_id)
           SELECT v.id FROM videos v LEFT JOIN video_embeddings e ON e.video_id = v.id
           WHERE v.status = 'ready' AND (e.video_id IS NULL OR e.model <> ?)""", (cfg[1],))


async def background_index() -> None:
    """Hintergrundlauf: wartende Videos einbetten, solange der KI-Dienst
    erreichbar ist. Ist er aus, wird in Ruhe wieder nachgesehen."""
    await asyncio.sleep(45)
    while True:
        try:
            cfg = await config()
            if cfg and await available():
                await mark_missing()
                while await index_batch(*cfg):
                    await asyncio.sleep(0.05)
        except Exception as e:
            reset_availability()
            logger.info(f"[BEDEUTUNG] Einbetten unterbrochen: {e.__class__.__name__}: {e}")
        await asyncio.sleep(_IDLE_PAUSE_S)


# ─── Suchen ───────────────────────────────────────────────────────────

async def _load_matrix(model: str):
    """Alle Vektoren als Matrix im Speicher (neu geladen, wenn sich der Bestand ändert)."""
    global _matrix
    import numpy as np
    stamp = tuple(await db.fetch_one(
        "SELECT COUNT(*), COALESCE(MAX(updated_at), '') FROM video_embeddings WHERE model = ?", (model,)))
    if _matrix and _matrix[2] == (model, stamp):
        return _matrix
    rows = await db.fetch_all("SELECT video_id, vector FROM video_embeddings WHERE model = ?", (model,))
    if not rows:
        _matrix = ([], None, (model, stamp))
        return _matrix
    ids = [r["video_id"] for r in rows]
    matrix = np.frombuffer(b"".join(r["vector"] for r in rows), dtype=np.float32).reshape(len(rows), -1)
    _matrix = (ids, matrix, (model, stamp))
    return _matrix


async def search(query: str) -> Optional[list[tuple[str, float]]]:
    """Inhaltlich ähnlichste Videos als (video_id, Ähnlichkeit), beste zuerst.
    None, wenn die Bedeutungssuche gerade nicht zur Verfügung steht."""
    cfg = await config()
    if not cfg or not query.strip() or not await available():
        return None
    url, model = cfg
    import numpy as np

    ids, matrix, _ = await _load_matrix(model)
    if matrix is None:
        return None
    key = (model, query.strip().casefold())
    vector = _query_cache.get(key)
    if vector is None:
        try:
            vector = (await _embed([query.strip()], url, model, timeout=_QUERY_TIMEOUT_S))[0]
        except Exception:
            reset_availability()
            return None
        if len(_query_cache) > 200:
            _query_cache.clear()
        _query_cache[key] = vector

    q = np.asarray(vector, dtype=np.float32)
    q = q / (np.linalg.norm(q) or 1.0)
    if q.shape[0] != matrix.shape[1]:
        return None   # Modell gewechselt, Vektoren werden gerade neu gerechnet
    scores = matrix @ q
    # In kleinen Beständen sagt die Streuung wenig; dort genügt "über dem Durchschnitt".
    z = MIN_Z if len(ids) >= SMALL_COLLECTION else 0.0
    try:
        min_similarity = float(await _setting("ai.min_similarity"))
    except ValueError:
        min_similarity = 0.5
    floor = max(min_similarity, float(scores.mean()) + z * float(scores.std()))
    top = np.argsort(-scores)[:TOP_K]
    return [(ids[i], float(scores[i])) for i in top if scores[i] >= floor]


async def overview() -> dict:
    cfg = await config()
    return {
        "enabled": cfg is not None,
        "available": await available() if cfg else False,
        "model": cfg[1] if cfg else None,
        "indexed": await db.fetch_val("SELECT COUNT(*) FROM video_embeddings") or 0,
        "pending": await pending(),
    }

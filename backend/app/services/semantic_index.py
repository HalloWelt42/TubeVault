"""
TubeVault – Bedeutungssuche (Einbettungen) v1.0.0

Optionale Erweiterung zur Wortsuche: Jedes Video bekommt einen Vektor, der
seinen Inhalt beschreibt (Titel, Kanal, Tags, Anfang der Beschreibung). Eine
Suchanfrage wird ebenso in einen Vektor gewandelt; ähnliche Vektoren sind
inhaltlich verwandte Videos - auch wenn kein Wort übereinstimmt ("Brot
backen" findet "Sauerteig ansetzen").

Die Vektoren rechnet ein lokaler KI-Dienst mit OpenAI-kompatibler
Schnittstelle (Einstellung ai.url, Modell EMBEDDING_MODEL). TubeVault
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
from dataclasses import dataclass
from typing import Optional

import httpx

from app.database import db
from app.services import setting_values

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS video_embeddings (
    video_id TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    vector BLOB NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
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
-- Vektoren der Transkript-Abschnitte. seq wächst mit jedem neuen Vektor:
-- so lädt die Suche nur nach, was seit dem letzten Mal dazukam.
CREATE TABLE IF NOT EXISTS chunk_embeddings (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id INTEGER NOT NULL UNIQUE,
    model TEXT NOT NULL,
    vector BLOB NOT NULL
);
CREATE TRIGGER IF NOT EXISTS trg_chunk_embedding_delete AFTER DELETE ON transcript_chunks
BEGIN
    DELETE FROM chunk_embeddings WHERE chunk_id = old.id;
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
#   1. Mindest-Ähnlichkeit. An echten Titeln gemessen (bge-m3): passende
#      Treffer ab etwa 0,50, Zufallstreffer bei sinnlosen Anfragen bis etwa 0,48.
#   2. Das Video ragt aus der Masse heraus: mindestens z Standardabweichungen
#      über dem Durchschnitt aller Videos. Das fängt Anfragen ab, zu denen
#      alles ein wenig passt.
# Wie streng, wählt der Nutzer in Stufen (Einstellung ai.precision als
# Standard, je Suche umstellbar; Wunsch 15.10.2026). "Ausgewogen" sind die
# früher fest eingebauten Werte.
@dataclass(frozen=True)
class Precision:
    label: str
    min_similarity: float
    min_z: float
    top_k: int            # höchstens so viele Videos und Textstellen


PRECISIONS: dict[str, Precision] = {
    "weit": Precision("Weit", 0.45, 1.5, 150),
    "ausgewogen": Precision("Ausgewogen", 0.50, 2.5, 80),
    "genau": Precision("Genau", 0.55, 3.0, 50),
    "sehr_genau": Precision("Sehr genau", 0.60, 3.5, 30),
}
DEFAULT_PRECISION = "ausgewogen"
OFF = "aus"           # nur für eine einzelne Suche: reine Wortsuche
# Modell des KI-Dienstes für die Einbettungen (mehrsprachig)
EMBEDDING_MODEL = "text-embedding-bge-m3"
SMALL_COLLECTION = 200   # darunter sagt die Streuung wenig

_available: tuple[float, bool] = (0.0, False)
# Wird gesetzt, wenn sich die KI-Einstellungen ändern
_wake = asyncio.Event()
_matrix = None                  # (ids, numpy-Matrix, Stempel)
_query_cache: dict[tuple[str, str], list[float]] = {}


async def install_schema(connection) -> None:
    await connection.executescript(SCHEMA_SQL)


# ─── Einstellungen und Erreichbarkeit ─────────────────────────────────

async def config() -> Optional[tuple[str, str]]:
    """(Adresse, Modell), wenn die Erweiterung eingeschaltet und eingerichtet ist."""
    if (await setting_values.get("ai.enabled")) != "true":
        return None
    url = (await setting_values.get("ai.url")).strip().rstrip("/")
    return (url, EMBEDDING_MODEL) if url else None


async def embed_texts(texts: list[str], url: str, model: str, timeout: float) -> list[list[float]]:
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
            await embed_texts(["bereit"], cfg[0], cfg[1], timeout=_QUERY_TIMEOUT_S)
            ok = True
        except Exception as e:
            logger.debug(f"[BEDEUTUNG] KI-Dienst nicht erreichbar: {e.__class__.__name__}")
    _available = (time.time(), ok)
    return ok


def reset_availability() -> None:
    """Erreichbarkeit neu prüfen und den Hintergrundlauf sofort wecken -
    nach dem Einschalten soll nicht erst die Ruhepause ablaufen."""
    global _available
    _available = (0.0, False)
    _wake.set()


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


def pack_vector(vector: list[float]) -> bytes:
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
        vectors = await embed_texts([text for _, text, _ in todo], url, model, timeout=_REQUEST_TIMEOUT_S)
        for (video_id, _text, text_hash), vector in zip(todo, vectors):
            await db.conn.execute(
                """INSERT INTO video_embeddings (video_id, model, text_hash, vector)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(video_id) DO UPDATE SET model = excluded.model,
                       text_hash = excluded.text_hash, vector = excluded.vector,
                       updated_at = datetime('now')""",
                (video_id, model, text_hash, pack_vector(vector)))
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
                while await index_chunk_batch(*cfg):
                    await asyncio.sleep(0.05)
                # Kanäle, Playlists, Liedtexte, Feed-Einträge (semantic_items)
                from app.services import semantic_items
                while await semantic_items.index_batch(*cfg):
                    await asyncio.sleep(0.05)
        except Exception as e:
            reset_availability()
            logger.info(f"[BEDEUTUNG] Einbetten unterbrochen: {e.__class__.__name__}: {e}")
        _wake.clear()
        try:
            await asyncio.wait_for(_wake.wait(), timeout=_IDLE_PAUSE_S)
        except asyncio.TimeoutError:
            pass


# ─── Transkript-Abschnitte ────────────────────────────────────────────

_CHUNK_WAITING_SQL = """
    FROM transcript_chunks c LEFT JOIN chunk_embeddings e ON e.chunk_id = c.id AND e.model = ?
    WHERE e.chunk_id IS NULL
"""


async def pending_chunks(model: str) -> int:
    return await db.fetch_val(f"SELECT COUNT(*) {_CHUNK_WAITING_SQL}", (model,)) or 0


async def index_chunk_batch(url: str, model: str) -> int:
    """Einen Stapel Transkript-Abschnitte einbetten. Gibt die Zahl zurück."""
    rows = await db.fetch_all(
        f"SELECT c.id, c.text {_CHUNK_WAITING_SQL} ORDER BY c.id LIMIT ?", (model, _BATCH))
    if not rows:
        return 0
    vectors = await embed_texts([row["text"] for row in rows], url, model, timeout=_REQUEST_TIMEOUT_S)
    for row, vector in zip(rows, vectors):
        await db.conn.execute(
            """INSERT INTO chunk_embeddings (chunk_id, model, vector) VALUES (?, ?, ?)
               ON CONFLICT(chunk_id) DO UPDATE SET model = excluded.model, vector = excluded.vector""",
            (row["id"], model, pack_vector(vector)))
    await db.conn.commit()
    return len(rows)


class _ChunkVectors:
    """Vektoren der Abschnitte im Speicher. Neue werden blockweise angehängt,
    statt bei jeder Suche alles neu zu laden - der Bestand wächst im
    Hintergrund laufend. Gelöschte Abschnitte bleiben bis zum Neustart als
    Zeile stehen; die Suche verwirft Treffer, deren Abschnitt es nicht mehr gibt."""

    def __init__(self):
        self.model = ""
        self.last_seq = 0
        self.ids: list[int] = []
        self.blocks: list = []

    async def refresh(self, model: str) -> None:
        import numpy as np
        if model != self.model:
            self.__init__()
            self.model = model
        rows = await db.fetch_all(
            "SELECT seq, chunk_id, vector FROM chunk_embeddings WHERE model = ? AND seq > ? ORDER BY seq",
            (model, self.last_seq))
        if not rows:
            return
        self.blocks.append(np.frombuffer(
            b"".join(row["vector"] for row in rows), dtype=np.float32).reshape(len(rows), -1))
        self.ids.extend(row["chunk_id"] for row in rows)
        self.last_seq = rows[-1]["seq"]
        if len(self.blocks) > 32:
            self.blocks = [np.vstack(self.blocks)]

    def scores(self, query):
        import numpy as np
        return np.concatenate([block @ query for block in self.blocks]) if self.blocks else None


_chunk_vectors = _ChunkVectors()


async def query_vector(query: str, url: str, model: str):
    """Vektor der Suchanfrage (normiert), aus dem Zwischenspeicher oder vom KI-Dienst."""
    import numpy as np
    key = (model, query.strip().casefold())
    vector = _query_cache.get(key)
    if vector is None:
        vector = (await embed_texts([query.strip()], url, model, timeout=_QUERY_TIMEOUT_S))[0]
        if len(_query_cache) > 200:
            _query_cache.clear()
        _query_cache[key] = vector
    q = np.asarray(vector, dtype=np.float32)
    return q / (np.linalg.norm(q) or 1.0)


async def precision(choice: Optional[str] = None) -> Optional[Precision]:
    """Stufe einer Suche: gewählt, sonst der Standard aus den Einstellungen;
    None = Bedeutungssuche für diese Suche aus."""
    if choice == OFF:
        return None
    if choice not in PRECISIONS:
        choice = await setting_values.get("ai.precision")
    return PRECISIONS.get(choice) or PRECISIONS[DEFAULT_PRECISION]


def score_floor(scores, level: Precision, collection_size: int) -> float:
    # In kleinen Beständen sagt die Streuung wenig; dort genügt "über dem Durchschnitt".
    z = level.min_z if collection_size >= SMALL_COLLECTION else 0.0
    return max(level.min_similarity, float(scores.mean()) + z * float(scores.std()))


def rule_floor(scores, level: Precision, collection_size: int) -> float:
    """Schwelle einer dauerhaften Regel ("Inhaltlich wie" einer Kategorie).

    Wie bei der Suche: Mindest-Ähnlichkeit der Stufe und deutlicher Abstand
    zur Masse. Die Masse wird hier robust gemessen (Median und mittlere
    Abweichung statt Durchschnitt und Streuung): ein Thema darf einen großen
    Teil der Sammlung ausmachen, ohne seine eigene Schwelle hochzutreiben.
    Ohne Obergrenze der Trefferzahl - eine Kategorie darf groß werden."""
    import numpy as np
    median = float(np.median(scores))
    if collection_size < SMALL_COLLECTION:
        return max(level.min_similarity, median)
    spread = float(np.median(np.abs(scores - median))) * 1.4826
    return max(level.min_similarity, median + level.min_z * spread)


async def text_vector(text: str):
    """Vektor eines Textes (normiert) oder None, wenn die KI gerade nicht
    zur Verfügung steht. Für Regeln, die einen Text mit Videos vergleichen."""
    cfg = await config()
    if not cfg or not text.strip() or not await available():
        return None
    try:
        return await query_vector(text, *cfg)
    except Exception:
        reset_availability()
        return None


async def all_vectors():
    """(Kennungen, Matrix) aller Videos mit Vektor des aktuellen Modells,
    oder None. Die Matrix ist dieselbe, mit der die Suche arbeitet."""
    cfg = await config()
    if not cfg:
        return None
    ids, matrix, _ = await _load_matrix(cfg[1])
    return (ids, matrix) if matrix is not None else None


async def search_passages(query: str, level: Precision) -> Optional[list[tuple[int, float]]]:
    """Inhaltlich ähnlichste Transkript-Abschnitte als (chunk_id, Ähnlichkeit).
    None, wenn die Bedeutungssuche gerade nicht zur Verfügung steht."""
    cfg = await config()
    if not cfg or not query.strip() or not await available():
        return None
    url, model = cfg
    import numpy as np
    await _chunk_vectors.refresh(model)
    try:
        q = await query_vector(query, url, model)
    except Exception:
        reset_availability()
        return None
    scores = _chunk_vectors.scores(q)
    if scores is None or q.shape[0] != _chunk_vectors.blocks[0].shape[1]:
        return []
    floor = score_floor(scores, level, len(scores))
    top = np.argsort(-scores)[:level.top_k]
    return [(_chunk_vectors.ids[i], float(scores[i])) for i in top if scores[i] >= floor]


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


async def search(query: str, level: Precision) -> Optional[list[tuple[str, float]]]:
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
    try:
        q = await query_vector(query, url, model)
    except Exception:
        reset_availability()
        return None
    if q.shape[0] != matrix.shape[1]:
        return None   # Modell gewechselt, Vektoren werden gerade neu gerechnet
    scores = matrix @ q
    floor = score_floor(scores, level, len(ids))
    top = np.argsort(-scores)[:level.top_k]
    return [(ids[i], float(scores[i])) for i in top if scores[i] >= floor]


async def similar_to(video_id: str, candidates: list[str], limit: int = 50) -> Optional[list[str]]:
    """Kandidaten, deren Inhalt dem eines Videos am nächsten ist, beste
    zuerst - aus den gespeicherten Vektoren, ohne den KI-Dienst zu fragen.
    None, wenn die Bedeutungssuche aus ist oder das Video keinen Vektor hat."""
    cfg = await config()
    if not cfg:
        return None
    import numpy as np
    ids, matrix, _ = await _load_matrix(cfg[1])
    if matrix is None:
        return None
    position = {vid: i for i, vid in enumerate(ids)}
    if video_id not in position:
        return None
    rows = [position[c] for c in candidates if c in position and c != video_id]
    if not rows:
        return []
    scores = matrix[rows] @ matrix[position[video_id]]
    return [ids[rows[i]] for i in np.argsort(-scores)[:limit]]


async def overview() -> dict:
    cfg = await config()
    return {
        "enabled": cfg is not None,
        "available": await available() if cfg else False,
        "model": cfg[1] if cfg else None,
        "indexed": await db.fetch_val("SELECT COUNT(*) FROM video_embeddings") or 0,
        "pending": await pending(),
        "passages_indexed": await db.fetch_val("SELECT COUNT(*) FROM chunk_embeddings") or 0,
        "passages_pending": await pending_chunks(cfg[1]) if cfg else 0,
        "items_indexed": await _items_overview(cfg[1] if cfg else None),
    }


async def _items_overview(model: Optional[str]) -> dict:
    from app.services import semantic_items
    return await semantic_items.overview(model)

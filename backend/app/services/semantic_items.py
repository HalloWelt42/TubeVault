"""
TubeVault – Bedeutungssuche über Videos hinaus

Videos und Transkript-Abschnitte rechnet semantic_index. Damit die
Bedeutungssuche alles findet (Wunsch 15.10.2026), bekommen weitere Dinge
einen Vektor - mit demselben KI-Dienst und Modell:

  channel   Kanal: Name, Beschreibung, Schlagwörter
  playlist  Playlist: Name, Beschreibung, Titel der ersten Videos
  feed      noch nicht geladene Feed-Einträge: Titel, Kanal, Beschreibung
  lyrics    Liedtexte geladener Musikvideos (Interpret, Song, Text)

Ein Eintrag wird neu gerechnet, wenn sich sein Text ändert (Prüfsumme);
Feed-Einträge ändern sich nicht und werden nur einmal gerechnet. Gesucht
wird zweistufig (vector_store): im Speicher liegen nur die Binärschlüssel
einer Art, erst wenn eine Suche sie braucht; die Kandidaten werden mit
ihren Vektoren aus der Datenbank genau bewertet.
"""
import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from app.database import db
from app.services import semantic_index

logger = logging.getLogger(__name__)

KINDS = ("channel", "playlist", "lyrics", "feed")
_BATCH = 32
_TIMEOUT_S = 120
_DESCRIPTION_CHARS = 1200
_LYRICS_CHARS = 1500

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS item_embeddings (
    kind TEXT NOT NULL,
    ref TEXT NOT NULL,
    model TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    vector BLOB NOT NULL,
    updated_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (kind, ref)
);
"""


async def install_schema(connection) -> None:
    await connection.executescript(SCHEMA_SQL)
    try:
        await connection.execute("ALTER TABLE item_embeddings ADD COLUMN code BLOB")
    except Exception:
        pass  # Spalte existiert bereits
    # Schlüssel und Stand je Art lesen, ohne die Vektoren anzufassen
    await connection.executescript("""
        CREATE INDEX IF NOT EXISTS idx_item_embeddings_codes ON item_embeddings(kind, model, ref, code);
        CREATE INDEX IF NOT EXISTS idx_item_embeddings_stamp ON item_embeddings(kind, model, updated_at);
    """)
    await connection.commit()


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _tags(raw) -> str:
    try:
        tags = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except (ValueError, TypeError):
        tags = []
    return ", ".join(map(str, tags[:20]))


# ─── Texte je Art ─────────────────────────────────────────────────────

async def _channels(model: str, limit: int) -> list[tuple[str, str]]:
    rows = await db.fetch_all("SELECT channel_id, channel_name, channel_description, channel_tags FROM subscriptions")
    return [(r["channel_id"], "\n".join(p for p in (
        f"Kanal: {(r['channel_name'] or '').strip()}",
        f"Stichworte: {_tags(r['channel_tags'])}" if r["channel_tags"] else "",
        (r["channel_description"] or "")[:_DESCRIPTION_CHARS]) if p)) for r in rows]


async def _playlists(model: str, limit: int) -> list[tuple[str, str]]:
    rows = await db.fetch_all(
        """SELECT p.id, p.name, p.description,
                  (SELECT GROUP_CONCAT(title, ' | ') FROM (SELECT v.title FROM playlist_videos pv
                     JOIN videos v ON v.id = pv.video_id WHERE pv.playlist_id = p.id ORDER BY pv.position LIMIT 20)) AS titles
           FROM playlists p""")
    return [(str(r["id"]), "\n".join(p for p in (
        f"Playlist: {r['name']}", r["description"] or "", f"Enthält: {r['titles']}" if r["titles"] else "") if p))
        for r in rows]


async def _lyrics(model: str, limit: int) -> list[tuple[str, str]]:
    from app.services import lyrics_service
    rows = await db.fetch_all(
        "SELECT id, title, music_artist, music_title FROM videos WHERE status = 'ready' AND COALESCE(has_lyrics, 0) = 1")

    def read() -> list[tuple[str, str]]:   # Dateien lesen, nicht im Ereignisstrang
        result = []
        for r in rows:
            plain = (lyrics_service.load_lyrics(r["id"]) or {}).get("plain") or ""
            if plain.strip():
                head = f"{r['music_artist']} - {r['music_title']}" if r["music_artist"] and r["music_title"] else r["title"]
                result.append((r["id"], f"Liedtext: {head}\n{plain[:_LYRICS_CHARS]}"))
        return result
    return await asyncio.to_thread(read)


# Bis zu diesem Feed-Eintrag (rss_entries.id) ist alles gerechnet - je Modell.
# Ohne Merker durchsuchte jeder Durchgang (alle 2 Min.) alle 100.000 Einträge,
# um meist nichts zu finden (gemessen 1,1 s, die Datenbank war so lange belegt).
_feed_done = {"model": "", "upto": 0}


async def _feed(model: str, limit: int) -> list[tuple[str, str]]:
    """Nur noch nicht gerechnete Einträge (Feed-Texte ändern sich nicht)."""
    if _feed_done["model"] != model:
        _feed_done.update(model=model, upto=0)
    newest = await db.fetch_val("SELECT MAX(id) FROM rss_entries") or 0
    if newest < _feed_done["upto"]:
        _feed_done["upto"] = 0           # andere Datenbank (zurückgespielt): von vorn
    if newest <= _feed_done["upto"]:
        return []
    rows = await db.fetch_all(
        """SELECT r.video_id, r.title, r.description, s.channel_name FROM rss_entries r
           LEFT JOIN subscriptions s ON s.channel_id = r.channel_id
           LEFT JOIN item_embeddings e ON e.kind = 'feed' AND e.ref = r.video_id AND e.model = ?
           WHERE r.id > ? AND e.ref IS NULL
             AND NOT EXISTS (SELECT 1 FROM videos v WHERE v.id = r.video_id AND v.status = 'ready')
           ORDER BY r.published DESC LIMIT ?""", (model, _feed_done["upto"], limit))
    if not rows:
        _feed_done["upto"] = newest      # alles bis hier gerechnet: künftig nur Neueres ansehen
    return [(r["video_id"], "\n".join(p for p in (
        r["title"] or "", f"Kanal: {r['channel_name']}" if r["channel_name"] else "",
        (r["description"] or "")[:600]) if p)) for r in rows]


_SOURCES: dict[str, Callable[[str, int], Awaitable[list[tuple[str, str]]]]] = {
    "channel": _channels, "playlist": _playlists, "lyrics": _lyrics, "feed": _feed}


# ─── Rechnen ──────────────────────────────────────────────────────────

async def _stored_hashes(kind: str, model: str) -> dict[str, str]:
    rows = await db.fetch_all("SELECT ref, text_hash FROM item_embeddings WHERE kind = ? AND model = ?", (kind, model))
    return {r["ref"]: r["text_hash"] for r in rows}


async def index_batch(url: str, model: str) -> int:
    """Einen Stapel neuer oder geänderter Einträge einbetten (Arten in der
    Reihenfolge von KINDS, kleine zuerst). Gibt die Zahl zurück, 0 = fertig."""
    for kind in KINDS:
        items = await _SOURCES[kind](model, _BATCH)
        stored = await _stored_hashes(kind, model) if kind != "feed" else {}
        todo = [(ref, text, _hash(text)) for ref, text in items if text.strip() and stored.get(ref) != _hash(text)][:_BATCH]
        if not todo:
            continue
        vectors = await semantic_index.embed_texts([text for _, text, _ in todo], url, model, timeout=_TIMEOUT_S,
                                                   purpose="Einträge für die Bedeutungssuche einbetten", background=True)
        for (ref, _, text_hash), vector in zip(todo, vectors):
            packed, code = semantic_index.pack_with_code(vector)
            await db.conn.execute(
                """INSERT INTO item_embeddings (kind, ref, model, text_hash, vector, code) VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(kind, ref) DO UPDATE SET model = excluded.model, text_hash = excluded.text_hash,
                       vector = excluded.vector, code = excluded.code, updated_at = datetime('now')""",
                (kind, ref, model, text_hash, packed, code))
        await db.conn.commit()
        return len(todo)
    return 0


async def overview(model: Optional[str]) -> dict[str, int]:
    rows = await db.fetch_all("SELECT kind, COUNT(*) AS n FROM item_embeddings WHERE model = ? GROUP BY kind", (model or "",))
    counts = {r["kind"]: r["n"] for r in rows}
    return {kind: counts.get(kind, 0) for kind in KINDS}


# ─── Suchen ───────────────────────────────────────────────────────────

@dataclass
class _Codes:
    stamp: tuple
    index: object          # vector_store.BinaryIndex
    sample: object         # genaue Vektoren der Stichprobe (numpy) für die Schwelle


_codes: dict[str, _Codes] = {}


async def _vectors_of(kind: str, refs: list[str]) -> dict[str, bytes]:
    rows = await db.fetch_all(
        "SELECT ref, vector FROM item_embeddings WHERE kind = ? AND ref IN (SELECT value FROM json_each(?))",
        (kind, json.dumps(refs)))
    return {row["ref"]: row["vector"] for row in rows}


async def _loaded(kind: str, model: str) -> Optional[_Codes]:
    """Schlüssel einer Art, neu gelesen, wenn sich ihr Bestand geändert hat."""
    from app.services import vector_store
    stamp = tuple(await db.fetch_one(
        "SELECT COUNT(*), COALESCE(MAX(updated_at), '') FROM item_embeddings WHERE kind = ? AND model = ?", (kind, model)))
    cached = _codes.get(kind)
    if cached and cached.stamp == (model, stamp):
        return cached
    rows = await db.fetch_all(
        "SELECT ref, code FROM item_embeddings WHERE kind = ? AND model = ? AND code IS NOT NULL", (kind, model))
    if not rows:
        return None
    index = vector_store.BinaryIndex()
    index.append([row["ref"] for row in rows], vector_store.codes_from_bytes([row["code"] for row in rows]))
    sample_refs = [index.refs[i] for i in vector_store.sample_positions(len(index))]
    sample = vector_store.vectors_from_bytes(list((await _vectors_of(kind, sample_refs)).values()))
    _codes[kind] = _Codes((model, stamp), index, sample)
    return _codes[kind]


async def search(query: str, kind: str, level, limit: int = 12) -> list[tuple[str, float]]:
    """Ähnlichste Einträge einer Art als (ref, Ähnlichkeit), beste zuerst;
    leer, wenn die Bedeutungssuche nicht zur Verfügung steht."""
    from app.services import vector_store
    cfg = await semantic_index.config()
    if not cfg or not query.strip() or not level or not await semantic_index.available():
        return []
    url, model = cfg
    loaded = await _loaded(kind, model)
    if loaded is None:
        return []
    try:
        q = await semantic_index.query_vector(query, url, model)
    except Exception:
        semantic_index.reset_availability()
        return []
    stats = vector_store.spread(loaded.sample, q)
    if stats is None or loaded.sample.shape[1] != q.shape[0]:
        return []
    found = await _vectors_of(kind, loaded.index.candidates(q))
    refs = list(found)
    floor = semantic_index.floor_from(stats, level, len(loaded.index))
    return vector_store.best(refs, vector_store.vectors_from_bytes([found[r] for r in refs]), q, floor, limit)

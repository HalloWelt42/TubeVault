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
Feed-Einträge ändern sich nicht und werden nur einmal gerechnet. Die
Vektoren einer Art liegen erst im Speicher, wenn eine Suche sie braucht.
"""
import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from pydantic import BaseModel

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


async def _feed(model: str, limit: int) -> list[tuple[str, str]]:
    """Nur noch nicht gerechnete Einträge (Feed-Texte ändern sich nicht)."""
    rows = await db.fetch_all(
        """SELECT r.video_id, r.title, r.description, s.channel_name FROM rss_entries r
           LEFT JOIN subscriptions s ON s.channel_id = r.channel_id
           LEFT JOIN item_embeddings e ON e.kind = 'feed' AND e.ref = r.video_id AND e.model = ?
           WHERE e.ref IS NULL
             AND NOT EXISTS (SELECT 1 FROM videos v WHERE v.id = r.video_id AND v.status = 'ready')
           ORDER BY r.published DESC LIMIT ?""", (model, limit))
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
        vectors = await semantic_index.embed_texts([text for _, text, _ in todo], url, model, timeout=_TIMEOUT_S)
        for (ref, _, text_hash), vector in zip(todo, vectors):
            await db.conn.execute(
                """INSERT INTO item_embeddings (kind, ref, model, text_hash, vector) VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(kind, ref) DO UPDATE SET model = excluded.model, text_hash = excluded.text_hash,
                       vector = excluded.vector, updated_at = datetime('now')""",
                (kind, ref, model, text_hash, semantic_index.pack_vector(vector)))
        await db.conn.commit()
        return len(todo)
    return 0


async def overview(model: Optional[str]) -> dict[str, int]:
    rows = await db.fetch_all("SELECT kind, COUNT(*) AS n FROM item_embeddings WHERE model = ? GROUP BY kind", (model or "",))
    counts = {r["kind"]: r["n"] for r in rows}
    return {kind: counts.get(kind, 0) for kind in KINDS}


# ─── Suchen ───────────────────────────────────────────────────────────

@dataclass
class _Matrix:
    stamp: tuple
    refs: list[str]
    matrix: object


_matrices: dict[str, _Matrix] = {}


async def _matrix(kind: str, model: str) -> Optional[_Matrix]:
    import numpy as np
    stamp = tuple(await db.fetch_one(
        "SELECT COUNT(*), COALESCE(MAX(updated_at), '') FROM item_embeddings WHERE kind = ? AND model = ?", (kind, model)))
    cached = _matrices.get(kind)
    if cached and cached.stamp == (model, stamp):
        return cached
    rows = await db.fetch_all("SELECT ref, vector FROM item_embeddings WHERE kind = ? AND model = ?", (kind, model))
    if not rows:
        return None
    matrix = np.frombuffer(b"".join(r["vector"] for r in rows), dtype=np.float32).reshape(len(rows), -1)
    _matrices[kind] = _Matrix((model, stamp), [r["ref"] for r in rows], matrix)
    return _matrices[kind]


async def search(query: str, kind: str, level, limit: int = 12) -> list[tuple[str, float]]:
    """Ähnlichste Einträge einer Art als (ref, Ähnlichkeit), beste zuerst;
    leer, wenn die Bedeutungssuche nicht zur Verfügung steht."""
    import numpy as np
    cfg = await semantic_index.config()
    if not cfg or not query.strip() or not level or not await semantic_index.available():
        return []
    url, model = cfg
    loaded = await _matrix(kind, model)
    if loaded is None:
        return []
    try:
        q = await semantic_index.query_vector(query, url, model)
    except Exception:
        semantic_index.reset_availability()
        return []
    if q.shape[0] != loaded.matrix.shape[1]:
        return []
    scores = loaded.matrix @ q
    floor = semantic_index.score_floor(scores, level, len(loaded.refs))
    top = np.argsort(-scores)[:limit]
    return [(loaded.refs[i], float(scores[i])) for i in top if scores[i] >= floor]


# ─── Treffer für die Suche ────────────────────────────────────────────

class ChannelHit(BaseModel):
    channel_id: str
    channel_name: str
    score: float


class PlaylistHit(BaseModel):
    id: int
    name: str
    video_count: int
    score: float


class FeedHit(BaseModel):
    video_id: str
    title: str
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    published: Optional[str] = None
    score: float


class Related(BaseModel):
    """Was die Bedeutungssuche außer Videos findet (nur für die erste Seite)."""
    channels: list[ChannelHit] = []
    playlists: list[PlaylistHit] = []
    feed: list[FeedHit] = []


async def related(query: str, level) -> Related:
    """Passende Kanäle, Playlists und noch nicht geladene Feed-Einträge;
    Verschwundenes (Abo beendet, inzwischen geladen) fällt heraus."""
    result = Related()
    hits = dict(await search(query, "channel", level, 6))
    if hits:
        rows = await db.fetch_all(
            f"SELECT channel_id, channel_name FROM subscriptions WHERE channel_id IN ({','.join('?' * len(hits))})", list(hits))
        result.channels = sorted((ChannelHit(channel_id=r["channel_id"], channel_name=(r["channel_name"] or "").strip(),
                                             score=hits[r["channel_id"]]) for r in rows), key=lambda h: -h.score)
    hits = dict(await search(query, "playlist", level, 6))
    if hits:
        rows = await db.fetch_all(
            f"""SELECT p.id, p.name, (SELECT COUNT(*) FROM playlist_videos pv WHERE pv.playlist_id = p.id) AS n
                FROM playlists p WHERE p.id IN ({','.join('?' * len(hits))})""", [int(h) for h in hits])
        result.playlists = sorted((PlaylistHit(id=r["id"], name=r["name"], video_count=r["n"], score=hits[str(r["id"])])
                                   for r in rows), key=lambda h: -h.score)
    hits = dict(await search(query, "feed", level, 12))
    if hits:
        rows = await db.fetch_all(
            f"""SELECT r.video_id, r.title, r.channel_id, s.channel_name, r.published FROM rss_entries r
                LEFT JOIN subscriptions s ON s.channel_id = r.channel_id
                WHERE r.video_id IN ({','.join('?' * len(hits))})
                  AND NOT EXISTS (SELECT 1 FROM videos v WHERE v.id = r.video_id AND v.status = 'ready')""", list(hits))
        result.feed = sorted((FeedHit(**dict(r), score=hits[r["video_id"]]) for r in rows), key=lambda h: -h.score)
    return result

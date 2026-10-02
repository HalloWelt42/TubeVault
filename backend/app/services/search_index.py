"""
TubeVault – Suchindex v1.0.0

Die EINE Stelle für die lokale Volltextsuche: Aufbau, Pflege und Abfrage.

Warum ein eigener Baustein
--------------------------
Der frühere Index hing direkt an videos.rowid und wurde an einer Handvoll
Schreibstellen von Hand nachgezogen. Folgen:
  - Änderungen über andere Wege (Titel bearbeiten, Tags, Import, Reparatur)
    kamen nie im Index an.
  - VACUUM und INSERT OR REPLACE vergeben neue rowids - der Index zeigte danach
    auf falsche Videos.
  - Die Suche schloss das Archiv aus, obwohl dort fast alle Videos liegen.

Aufbau
------
  search_docs    video_id -> doc_id (eigene, stabile Nummer; unabhängig von rowid)
  videos_fts     FTS5 ohne eigenen Inhalt, rowid = doc_id
  search_dirty   Warteliste geänderter Videos

Trigger auf videos tragen jede Änderung an Titel, Kanal, Beschreibung, Tags
und Notizen in die Warteliste ein - egal welcher Schreibweg. flush() arbeitet
die Warteliste ab; die Beschreibung kommt dabei aus dem text_resolver
(Datei zuerst), weil die DB-Spalte geleert sein kann. Wer Beschreibungs-
dateien schreibt, ruft mark_dirty().

Suche
-----
Jedes Wort wird als Wortanfang gesucht (UND-verknüpft), damit Tippen im
Suchfeld sofort Treffer liefert. Zusätzlich greift eine Teilwort-Suche über
Titel und Kanalname ("teig" findet "Sauerteig"). Volltext-Treffer stehen nach
Relevanz vorn, reine Teilwort-Treffer dahinter.
"""
import asyncio
import json
import logging
import re

from app.database import db

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS search_docs (
    doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS search_dirty (
    video_id TEXT PRIMARY KEY
);
CREATE VIRTUAL TABLE IF NOT EXISTS videos_fts USING fts5(
    title, channel_name, description, tags, notes,
    content='', contentless_delete=1,
    tokenize='unicode61 remove_diacritics 2',
    prefix='2 3 4'
);
CREATE TRIGGER IF NOT EXISTS trg_search_dirty_insert AFTER INSERT ON videos
BEGIN
    INSERT OR IGNORE INTO search_dirty (video_id) VALUES (new.id);
END;
CREATE TRIGGER IF NOT EXISTS trg_search_dirty_update
AFTER UPDATE OF title, channel_name, description, tags, notes ON videos
BEGIN
    INSERT OR IGNORE INTO search_dirty (video_id) VALUES (new.id);
END;
CREATE TRIGGER IF NOT EXISTS trg_search_dirty_delete AFTER DELETE ON videos
BEGIN
    INSERT OR IGNORE INTO search_dirty (video_id) VALUES (old.id);
END;
"""

# Gewichte je Spalte (title, channel_name, description, tags, notes)
_BM25_WEIGHTS = "10.0, 5.0, 1.0, 3.0, 2.0"
# Vor jeder Suche höchstens so viele wartende Videos nachziehen (Antwortzeit)
_FLUSH_BEFORE_SEARCH = 300
_COMMIT_EVERY = 200

_lock = asyncio.Lock()


async def install_schema(connection, *, rebuild: bool) -> None:
    """Tabellen und Trigger anlegen. rebuild=True ersetzt einen Altindex und
    setzt alle Videos auf die Warteliste."""
    if rebuild:
        await connection.execute("DROP TABLE IF EXISTS videos_fts")
        await connection.execute("DROP TABLE IF EXISTS search_docs")
    await connection.executescript(SCHEMA_SQL)
    if rebuild:
        await connection.execute(
            "INSERT OR IGNORE INTO search_dirty (video_id) SELECT id FROM videos")


async def mark_dirty(video_id: str) -> None:
    """Video zum Nachziehen vormerken (z.B. nach Schreiben der Beschreibungsdatei)."""
    await db.execute(
        "INSERT OR IGNORE INTO search_dirty (video_id) VALUES (?)", (video_id,))


async def mark_all_dirty() -> None:
    await db.execute(
        "INSERT OR IGNORE INTO search_dirty (video_id) SELECT id FROM videos")


async def pending() -> int:
    return await db.fetch_val("SELECT COUNT(*) FROM search_dirty") or 0


def _tags_as_text(raw) -> str:
    if not raw:
        return ""
    try:
        tags = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return str(raw)
    return " ".join(str(t) for t in tags) if isinstance(tags, list) else str(tags)


async def _reindex(video_id: str) -> None:
    """Ein Video im Index ersetzen bzw. entfernen, wenn es nicht mehr existiert."""
    from app.services.text_resolver import get_description

    conn = db.conn
    cursor = await conn.execute(
        "SELECT id, title, channel_name, tags, notes FROM videos WHERE id = ?", (video_id,))
    video = await cursor.fetchone()
    cursor = await conn.execute(
        "SELECT doc_id FROM search_docs WHERE video_id = ?", (video_id,))
    doc = await cursor.fetchone()

    if doc:
        await conn.execute("DELETE FROM videos_fts WHERE rowid = ?", (doc["doc_id"],))
    if not video:
        if doc:
            await conn.execute("DELETE FROM search_docs WHERE doc_id = ?", (doc["doc_id"],))
    else:
        if doc:
            doc_id = doc["doc_id"]
        else:
            cursor = await conn.execute(
                "INSERT INTO search_docs (video_id) VALUES (?)", (video_id,))
            doc_id = cursor.lastrowid
        description = await get_description(video_id) or ""
        await conn.execute(
            "INSERT INTO videos_fts (rowid, title, channel_name, description, tags, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (doc_id, video["title"] or "", video["channel_name"] or "", description,
             _tags_as_text(video["tags"]), video["notes"] or ""))
    await conn.execute("DELETE FROM search_dirty WHERE video_id = ?", (video_id,))


async def flush(limit: int | None = None) -> int:
    """Warteliste abarbeiten. Gibt die Zahl der nachgezogenen Videos zurück."""
    async with _lock:
        sql = "SELECT video_id FROM search_dirty"
        rows = await db.fetch_all(sql + (" LIMIT ?" if limit else ""), (limit,) if limit else ())
        done = 0
        for row in rows:
            await _reindex(row["video_id"])
            done += 1
            if done % _COMMIT_EVERY == 0:
                await db.conn.commit()
                await asyncio.sleep(0)   # anderen Anfragen Luft lassen
        if done:
            await db.conn.commit()
        return done


async def refresh_before_query() -> None:
    """Vor einer Abfrage einen begrenzten Teil der Warteliste nachziehen, damit
    frische Änderungen sofort findbar sind, die Antwort aber schnell bleibt."""
    await flush(limit=_FLUSH_BEFORE_SEARCH)


async def rebuild() -> dict:
    """Index vollständig neu aufbauen (Wartung)."""
    await mark_all_dirty()
    rebuilt = await flush()
    count = await db.fetch_val("SELECT COUNT(*) FROM search_docs") or 0
    return {"rebuilt": rebuilt, "fts_count": count}


async def background_catch_up() -> None:
    """Beim Start: wartende Videos im Hintergrund nachziehen."""
    waiting = await pending()
    if not waiting:
        return
    logger.info(f"[SUCHINDEX] {waiting} Videos werden nachgezogen…")
    while await flush(limit=_COMMIT_EVERY):
        await asyncio.sleep(0.05)
    logger.info("[SUCHINDEX] Index ist aktuell")


# ─── Abfrage ──────────────────────────────────────────────────────────

_WORD = re.compile(r"[\w]+", re.UNICODE)


def split_terms(query: str) -> list[str]:
    """Suchtext in Wörter zerlegen (Leerraum-getrennt, ohne leere Reste)."""
    return [t for t in (query or "").split() if t.strip()]


def build_match(query: str) -> str | None:
    """FTS5-Ausdruck: jedes Wort als Wortanfang, UND-verknüpft.
    None, wenn kein durchsuchbares Wort übrig bleibt."""
    parts = []
    for term in split_terms(query):
        words = _WORD.findall(term)
        if not words:
            continue
        # Ein Begriff wie "c++" oder "foo-bar" wird zur Wortfolge; nur das
        # letzte Wort darf Wortanfang sein.
        phrase = " ".join(words)
        parts.append(f'"{phrase}"*')
    return " AND ".join(parts) if parts else None


def _like_pattern(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _infix_condition(query: str, alias: str) -> tuple[str, list]:
    """Teilwort-Suche über Titel und Kanalname (alle Wörter müssen vorkommen)."""
    clauses, params = [], []
    for term in split_terms(query):
        pattern = _like_pattern(term)
        clauses.append(
            f"({alias}.title LIKE ? ESCAPE '\\' OR {alias}.channel_name LIKE ? ESCAPE '\\')")
        params.extend([pattern, pattern])
    return (" AND ".join(clauses) if clauses else "0"), params


def condition(query: str, alias: str = "v") -> tuple[str, list]:
    """WHERE-Baustein "Video passt zum Suchtext" für beliebige Video-Listen.
    Gleiche Regeln wie die Suche selbst, damit Listenfilter und Suche nie
    Unterschiedliches finden."""
    infix_sql, infix_params = _infix_condition(query, alias)
    match = build_match(query)
    parts = [f"({infix_sql})", f"{alias}.id = ?"]
    params = [*infix_params, query.strip()]
    if match:
        parts.insert(0, f"""{alias}.id IN (
            SELECT d.video_id FROM videos_fts
            JOIN search_docs d ON d.doc_id = videos_fts.rowid
            WHERE videos_fts MATCH ?)""")
        params.insert(0, match)
    return "(" + " OR ".join(parts) + ")", params


async def search_videos(
    query: str,
    *,
    page: int = 1,
    per_page: int = 24,
    archived: bool | None = None,
    source: str | None = None,
    scope: str | None = None,
) -> dict:
    """Videos suchen. archived: None = Bibliothek UND Archiv, True/False = nur eines.
    Sortierung: Volltext-Treffer nach Relevanz, danach Teilwort-Treffer."""
    await refresh_before_query()

    match = build_match(query)
    infix_sql, infix_params = _infix_condition(query, "v")

    if match:
        hits_sql = f"""SELECT d.video_id AS video_id,
                              bm25(videos_fts, {_BM25_WEIGHTS}) AS score
                       FROM videos_fts
                       JOIN search_docs d ON d.doc_id = videos_fts.rowid
                       WHERE videos_fts MATCH ?"""
        hits_params = [match]
    else:
        hits_sql = "SELECT NULL AS video_id, NULL AS score WHERE 0"
        hits_params = []

    conditions = [
        "v.status = 'ready'",
        f"(h.video_id IS NOT NULL OR ({infix_sql}) OR v.id = ?)",
    ]
    params = [*infix_params, query.strip()]

    if archived is True:
        conditions.append("COALESCE(v.is_archived, 0) = 1")
    elif archived is False:
        conditions.append("COALESCE(v.is_archived, 0) = 0")
    if source:
        conditions.append("v.source = ?")
        params.append(source)
    if scope == "favorites":
        conditions.append("v.id IN (SELECT video_id FROM favorites)")
    elif scope == "playlists":
        conditions.append("v.id IN (SELECT video_id FROM playlist_videos)")
    elif scope == "own":
        conditions.append("v.source IN ('local', 'imported')")

    cte = f"WITH hits AS ({hits_sql})"
    from_where = f"""FROM videos v LEFT JOIN hits h ON h.video_id = v.id
                     WHERE {' AND '.join(conditions)}"""
    base_params = [*hits_params, *params]

    total = await db.fetch_val(f"{cte} SELECT COUNT(*) {from_where}", base_params) or 0
    offset = (page - 1) * per_page
    rows = await db.fetch_all(
        f"""{cte} SELECT v.* {from_where}
            ORDER BY (h.score IS NULL), h.score, v.upload_date DESC, v.id
            LIMIT ? OFFSET ?""",
        [*base_params, per_page, offset])

    videos = []
    for row in rows:
        video = dict(row)
        video["tags"] = _parse_tags(video.get("tags"))
        video.pop("ai_summary", None)
        video.pop("ai_tags", None)
        videos.append(video)

    return {
        "query": query, "videos": videos, "total": total,
        "page": page, "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    }


def _parse_tags(raw) -> list:
    if isinstance(raw, list):
        return raw
    try:
        tags = json.loads(raw) if raw else []
    except (ValueError, TypeError):
        return []
    return tags if isinstance(tags, list) else []

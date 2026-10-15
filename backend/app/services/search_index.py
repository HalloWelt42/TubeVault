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

Abfragen
--------
Gesucht wird in services/search (Suchsprache, Rangfolge, alle Bereiche);
hier steht nur noch der Listenfilter für Bibliothek und Archiv (condition),
nach denselben Wortregeln.
"""
import asyncio
import json
import logging

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
    title, channel_name, description, tags, notes, lyrics,
    content='', contentless_delete=1,
    tokenize='unicode61 remove_diacritics 2',
    prefix='2 3 4'
);
CREATE TRIGGER IF NOT EXISTS trg_search_dirty_insert AFTER INSERT ON videos
BEGIN
    INSERT OR IGNORE INTO search_dirty (video_id) VALUES (new.id);
END;
CREATE TRIGGER IF NOT EXISTS trg_search_dirty_update
AFTER UPDATE OF title, channel_name, description, tags, notes, has_lyrics ON videos
BEGIN
    INSERT OR IGNORE INTO search_dirty (video_id) VALUES (new.id);
END;
CREATE TRIGGER IF NOT EXISTS trg_search_dirty_delete AFTER DELETE ON videos
BEGIN
    INSERT OR IGNORE INTO search_dirty (video_id) VALUES (old.id);
END;
"""

# Gewichte je Spalte (title, channel_name, description, tags, notes, lyrics)
BM25_WEIGHTS = "10.0, 5.0, 1.0, 3.0, 2.0, 1.0"
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
    from app.services import lyrics_service
    from app.services.text_resolver import get_description

    conn = db.conn
    cursor = await conn.execute(
        "SELECT id, title, channel_name, tags, notes, has_lyrics FROM videos WHERE id = ?", (video_id,))
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
        lyrics = (lyrics_service.load_lyrics(video_id).get("plain") or "") if video["has_lyrics"] else ""
        await conn.execute(
            "INSERT INTO videos_fts (rowid, title, channel_name, description, tags, notes, lyrics) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (doc_id, video["title"] or "", video["channel_name"] or "", description,
             _tags_as_text(video["tags"]), video["notes"] or "", lyrics))
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


# ─── Listenfilter ─────────────────────────────────────────────────────


def condition(text: str, alias: str = "v") -> tuple[str, list]:
    """WHERE-Baustein "Video passt zum Suchtext" für Video-Listen (Bibliothek,
    Archiv). Dieselben Wortregeln wie die Suche (services/search/query):
    Wörter im Index, Teilwörter in Titel und Kanal, eine eingetippte Kennung;
    ausgeschlossene Wörter fallen weg. Angaben wie kanal: wirken hier nicht."""
    from app.services.search import query as query_module
    query = query_module.parse(text)
    parts, params = [f"{alias}.id = ?"], [text.strip()]
    expression = query.expression()
    if expression:
        parts.insert(0, f"""{alias}.id IN (
            SELECT d.video_id FROM videos_fts JOIN search_docs d ON d.doc_id = videos_fts.rowid
            WHERE videos_fts MATCH ?)""")
        params.insert(0, expression)
        infix_sql, infix_params = query_module.like_clause(query, [f"{alias}.title", f"{alias}.channel_name"])
        if infix_sql != "0":
            parts.append(f"({infix_sql})")
            params.extend(infix_params)
    sql = "(" + " OR ".join(parts) + ")"
    if query.excluded:
        sql = f"""({sql} AND {alias}.id NOT IN (
            SELECT d.video_id FROM videos_fts JOIN search_docs d ON d.doc_id = videos_fts.rowid
            WHERE videos_fts MATCH ?))"""
        params.append(query.exclusion())
    return sql, params

"""
TubeVault – Schlagwort-Index (gemeinsamer Baustein)

Schlagwörter stehen als JSON-Liste in einer Spalte (videos.tags,
rss_entries.keywords), mit \\u-Umschreibung (ensure_ascii). Mit LIKE darin zu
suchen fand kein Schlagwort mit Umlaut oder fremder Schrift, kannte Groß und
Klein nur für ASCII und nahm % und _ als Platzhalter (gemessen 19.10.2026:
15.615 von 137.213 Schlagwörtern der Videos nie zu finden). Die Spalte bleibt
die gespeicherte Quelle; daneben steht je Zeile und Schlagwort eine Zeile im
Index mit Suchschlüssel tag_suche.

Hier steht beides einmal:
- die Regel (search_key, parse, keyed): Unicode NFC, ohne Groß und Klein
  (casefold), Leerraum einfach; je Zeile jeder Schlüssel einmal mit der
  ersten Schreibweise;
- der Index (TagIndex): Tabelle, Warteliste und Trigger je Quelle. Trigger
  merken jede neue Zeile mit Schlagwörtern und jede Änderung der Spalte vor,
  gleich welcher Schreibweg; index() ist die eine Funktion, die die Zeilen
  schreibt; gelöschte Zeilen nehmen ihre mit (Fremdschlüssel). Vor einer
  Abfrage zieht refresh_before_query() ein Stück der Warteliste nach (frisch
  Geändertes ist sofort findbar), den Bestand nach der Einführung arbeitet
  background_catch_up() in Portionen ab - unterbrechbar, die Warteliste ist
  der Stand.

Abfragen: condition (genaues Schlagwort, mehrere = oder), contains_condition
(Teilwort auf dem Schlüssel), counts (Anzahl je Schlüssel). counts zählt aus
der Quelle mit derselben Regel, nicht über den Index (gemessen 19.10.2026 mit
dem Bestand der Videos, 30.008 Zeilen mit Schlagwörtern, 499.000 Zuordnungen,
am Mac; der Pi braucht rund dreimal so lang): über den Index 0,55 s, die ganze
Zeit in der einen Datenbankverbindung; aus der Quelle 0,06 s in der Datenbank
(nur die Spalte lesen) und 0,42 s Zusammenzählen neben der Ereignisschleife.
Gleich dem Index ist das, sobald dieser aktuell ist.

Nutzer: video_tags (Bibliothek, Archiv, Kategorie-Regeln), feed_keywords (Feed).
"""
import asyncio
import json
import logging
import unicodedata
from typing import Iterable, Optional

from app.database import db

logger = logging.getLogger(__name__)

_FLUSH_BEFORE_QUERY = 500      # vor einer Abfrage höchstens so viele Zeilen nachziehen
_CHUNK = 500                   # Kennungen je IN-Liste


# ─── Die Regel ────────────────────────────────────────────────────────

def search_key(tag: str) -> str:
    """Suchschlüssel eines Schlagworts: NFC, ohne Groß und Klein, Leerraum einfach.
    Reines ASCII (die meisten) braucht keine Unicode-Form, casefold ist dort lower."""
    text = str(tag)
    if text.isascii():
        return " ".join(text.lower().split())
    folded = unicodedata.normalize("NFC", text).casefold()
    return unicodedata.normalize("NFC", " ".join(folded.split()))


def parse(raw) -> list[str]:
    """Schlagwörter aus der Spalte (JSON-Liste); Unlesbares zählt als keine."""
    if not raw:
        return []
    try:
        tags = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return []
    return [str(tag) for tag in tags if str(tag).strip()] if isinstance(tags, list) else []


def keyed(raw) -> dict[str, str]:
    """Die Regel des Index: Schlüssel -> Schreibweise (die erste) einer Zeile."""
    found: dict[str, str] = {}
    for tag in parse(raw):
        key = search_key(tag)
        if key and key not in found:
            found[key] = " ".join(tag.split())
    return found


def tally(raws: Iterable[str]) -> list[dict]:
    """Anzahl je Schlüssel über viele Zeilen (je Zeile jeder Schlüssel einmal),
    mit der häufigsten Schreibweise; meiste zuerst. Wie keyed, je Aufruf mit
    Gedächtnis je Schreibweise (viele Zeilen teilen ihre Schlagwörter)."""
    memo: dict[str, tuple[str, str]] = {}
    total: dict[str, int] = {}
    spellings: dict[tuple[str, str], int] = {}
    for raw in raws:
        seen = set()
        for tag in parse(raw):
            entry = memo.get(tag)
            if entry is None:
                entry = memo[tag] = (search_key(tag), " ".join(tag.split()))
            key = entry[0]
            if key and key not in seen:
                seen.add(key)
                total[key] = total.get(key, 0) + 1
                spellings[entry] = spellings.get(entry, 0) + 1
    best: dict[str, tuple[int, str]] = {}
    for (key, tag), n in spellings.items():
        if n > best.get(key, (0, ""))[0]:
            best[key] = (n, tag)
    ordered = sorted(total.items(), key=lambda item: (-item[1], item[0]))
    return [{"tag": best[key][1], "key": key, "count": n} for key, n in ordered]


def _chunks(items: list) -> Iterable[list]:
    for start in range(0, len(items), _CHUNK):
        yield items[start:start + _CHUNK]


# ─── Der Index ────────────────────────────────────────────────────────

class TagIndex:
    """Schlagwort-Index einer Spalte: table(id_column, tag_suche, tag) neben
    owner(id, column), Warteliste table_dirty. id_type: Art der Kennung von owner."""

    def __init__(self, *, table: str, id_column: str, id_type: str, owner: str, column: str, batch: int = 500):
        self.table, self.id_column, self.id_type = table, id_column, id_type
        self.owner, self.column = owner, column
        self.dirty = f"{table}_dirty"
        self.batch = batch                # Zeilen je Portion im Hintergrund
        self._lock = asyncio.Lock()

    def schema_sql(self) -> str:
        t, i, o, c, d = self.table, self.id_column, self.owner, self.column, self.dirty
        return f"""
CREATE TABLE IF NOT EXISTS {t} (
    {i} {self.id_type} NOT NULL,
    tag_suche TEXT NOT NULL,          -- Suchschlüssel (tag_index.search_key)
    tag TEXT NOT NULL,                -- Schreibweise in der Quelle
    PRIMARY KEY ({i}, tag_suche),
    FOREIGN KEY ({i}) REFERENCES {o}(id) ON DELETE CASCADE
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_{t}_suche ON {t}(tag_suche, {i});
CREATE TABLE IF NOT EXISTS {d} ({i} {self.id_type} PRIMARY KEY);
CREATE TRIGGER IF NOT EXISTS trg_{t}_insert AFTER INSERT ON {o}
WHEN new.{c} IS NOT NULL AND new.{c} NOT IN ('', '[]')
BEGIN
    INSERT OR IGNORE INTO {d} ({i}) VALUES (new.id);
END;
CREATE TRIGGER IF NOT EXISTS trg_{t}_update AFTER UPDATE OF {c} ON {o}
BEGIN
    INSERT OR IGNORE INTO {d} ({i}) VALUES (new.id);
END;
CREATE TRIGGER IF NOT EXISTS trg_{t}_delete AFTER DELETE ON {o}
BEGIN
    DELETE FROM {d} WHERE {i} = old.id;
END;
"""

    async def install_schema(self, connection, *, backfill: bool) -> None:
        """Tabellen und Trigger anlegen; backfill=True merkt den Bestand vor."""
        await connection.executescript(self.schema_sql())
        if backfill:
            cursor = await connection.execute(
                f"INSERT OR IGNORE INTO {self.dirty} ({self.id_column}) "
                f"SELECT id FROM {self.owner} WHERE {self.column} IS NOT NULL AND {self.column} NOT IN ('', '[]')")
            logger.info(f"{self.table}: {cursor.rowcount} Zeilen für den Schlagwort-Index vorgemerkt")
        await connection.commit()

    async def index(self, ids: Iterable) -> int:
        """Die eine Funktion, die den Index schreibt: Zeilen dieser Kennungen aus
        der Quelle neu bilden und von der Warteliste nehmen. Erst austragen,
        dann lesen - ändert sich eine Zeile währenddessen, bleibt ihre neue Marke."""
        wanted = list(dict.fromkeys(ids))
        if not wanted:
            return 0
        t, i, d = self.table, self.id_column, self.dirty
        async with self._lock:
            for chunk in _chunks(wanted):
                marks = ",".join("?" * len(chunk))
                await db.conn.execute(f"DELETE FROM {d} WHERE {i} IN ({marks})", chunk)
                rows = await (await db.conn.execute(
                    f"SELECT id, {self.column} FROM {self.owner} WHERE id IN ({marks})", chunk)).fetchall()
                await db.conn.execute(f"DELETE FROM {t} WHERE {i} IN ({marks})", chunk)
                await db.conn.executemany(
                    f"INSERT INTO {t} ({i}, tag_suche, tag) VALUES (?, ?, ?)",
                    [(row[0], key, tag) for row in rows for key, tag in keyed(row[1]).items()])
            await db.conn.commit()
        return len(wanted)

    async def pending(self) -> int:
        return await db.fetch_val(f"SELECT COUNT(*) FROM {self.dirty}") or 0

    async def flush(self, limit: Optional[int] = None) -> int:
        """Warteliste abarbeiten (höchstens limit Zeilen). Gibt die Zahl zurück."""
        rows = await db.fetch_all(f"SELECT {self.id_column} FROM {self.dirty}" + (" LIMIT ?" if limit else ""),
                                  (limit,) if limit else ())
        return await self.index(row[0] for row in rows)

    async def refresh_before_query(self) -> None:
        """Vor einer Abfrage ein Stück der Warteliste nachziehen: frisch Geändertes
        ist sofort findbar, die Antwort bleibt schnell."""
        await self.flush(limit=_FLUSH_BEFORE_QUERY)

    async def ensure(self, ids: Optional[list] = None) -> bool:
        """Ist der Index für diese Kennungen (None: alle) aktuell? Wartende unter
        bestimmten werden gleich nachgezogen; für alle ein Stück wie vor einer
        Abfrage, den großen Bestand zieht der Hintergrund nach."""
        if ids is None:
            await self.refresh_before_query()
            return not await self.pending()
        waiting = []
        for chunk in _chunks(list(ids)):
            marks = ",".join("?" * len(chunk))
            waiting += [row[0] for row in await db.fetch_all(
                f"SELECT {self.id_column} FROM {self.dirty} WHERE {self.id_column} IN ({marks})", chunk)]
        await self.index(waiting)
        return True

    async def background_catch_up(self) -> None:
        """Beim Start: die Warteliste in Portionen abarbeiten (der Bestand nach der
        Einführung, sonst nur, was zwischendurch liegen blieb)."""
        waiting = await self.pending()
        if not waiting:
            return
        logger.info(f"[SCHLAGWÖRTER] {self.table}: {waiting} Zeilen werden in den Index aufgenommen")
        while await self.flush(limit=self.batch):
            await asyncio.sleep(0.05)
        logger.info(f"[SCHLAGWÖRTER] {self.table}: Index ist aktuell")

    def condition(self, tags: list[str], alias: str) -> tuple[str, list]:
        """Zeilen mit einem dieser Schlagwörter (genau, Schreibweise egal)."""
        keys = list(dict.fromkeys(key for key in map(search_key, tags) if key))
        if not keys:
            return "0", []
        marks = ",".join("?" * len(keys))
        return f"{alias}.id IN (SELECT {self.id_column} FROM {self.table} WHERE tag_suche IN ({marks}))", keys

    @staticmethod
    def contains_condition(needle: str, alias: str) -> tuple[str, list]:
        """Schlagwort enthält needle (Teilwort, Schreibweise egal; ohne Platzhalter)."""
        return f"instr({alias}.tag_suche, ?) > 0", [search_key(needle)]

    async def counts(self, source: str, alias: str, where: str, params: list) -> list[dict]:
        """Schlagwörter der Zeilen alias aus source (FROM-Teil), die where
        erfüllen, mit Anzahl (tally): je Schlüssel jede Zeile einmal - so viele,
        wie condition mit diesem Schlagwort findet."""
        column = f"{alias}.{self.column}"
        rows = await db.fetch_all(
            f"SELECT {column} FROM {source} WHERE {where} AND {column} IS NOT NULL AND {column} NOT IN ('', '[]')",
            params)
        return await asyncio.to_thread(tally, [row[0] for row in rows])

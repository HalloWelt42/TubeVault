"""
TubeVault – Schlagwörter der Videos (eigener Index)

Die eine Stelle zum Nachschlagen der Schlagwörter (Tags). videos.tags bleibt
die gespeicherte Quelle (JSON-Liste, wie geladen); daraus entsteht je Video
und Schlagwort eine Zeile in video_tags mit Suchschlüssel tag_suche
(search_key: Unicode NFC, ohne Groß und Klein (casefold), Leerraum einfach).
Je Video steht jeder Schlüssel einmal, mit der ersten Schreibweise.

Warum (entschieden 19.10.2026, gemessen am Bestand): Der Listenfilter suchte
mit tags LIKE '%"<tag>"%' im JSON. Das JSON steht mit \\u-Umschreibung
(ensure_ascii), also fand er kein Schlagwort mit Umlaut oder fremder Schrift
("Körper", "erklärung", "техно"); LIKE kennt Groß und Klein nur für ASCII und
nimmt % und _ als Platzhalter. Von 137.213 Schlagwörtern waren 15.615 (36.479
Zuordnungen an 29.988 Videos) nie zu finden.

Pflege: Trigger auf videos merken jedes neue Video mit Schlagwörtern und jede
Änderung an videos.tags in video_tags_dirty vor - gleich welcher Schreibweg
(Download, Metadaten, Bearbeiten, Import, Wiederaufbau, Bereinigung).
index_videos() ist die eine Funktion, die daraus die Zeilen schreibt; ein
gelöschtes Video nimmt seine Zeilen mit (Fremdschlüssel, dazu
metadata_service._VIDEO_ROWS). Vor einer Abfrage zieht refresh_before_query()
die Warteliste in kleinen Stücken nach, frisch Bearbeitetes ist also sofort
findbar. Den Bestand nach der Einführung (Migration v59 merkt alle Videos mit
Schlagwörtern vor) arbeitet background_catch_up() in Portionen ab, ohne den
Start aufzuhalten; die Warteliste ist der Stand, ein Neustart macht dort
weiter. Solange sie lang ist, zeigt die Statusleiste den Fortschritt
(background_work).

Nutzer: Listenfilter (genaues Schlagwort, mehrere = oder) und Kategorie-
Regeln "Schlagwort enthält" (Teilwort auf dem Schlüssel) fragen den Index;
die Zählung der Schlagwortleiste (gleiche Filter wie die Liste, jedes Video
einmal je Schlüssel) zählt mit derselben Regel (counts, dort warum). Der Volltext der Suche liest die Schlagwörter weiter aus dem JSON
(search_index entschlüsselt es dabei).
"""
import asyncio
import json
import logging
import unicodedata
from typing import Iterable, Optional

from app.database import db

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS video_tags (
    video_id TEXT NOT NULL,
    tag_suche TEXT NOT NULL,          -- Suchschlüssel (search_key)
    tag TEXT NOT NULL,                -- Schreibweise am Video
    PRIMARY KEY (video_id, tag_suche),
    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_video_tags_suche ON video_tags(tag_suche, video_id);
CREATE TABLE IF NOT EXISTS video_tags_dirty (video_id TEXT PRIMARY KEY);
CREATE TRIGGER IF NOT EXISTS trg_video_tags_insert AFTER INSERT ON videos
WHEN new.tags IS NOT NULL AND new.tags NOT IN ('', '[]')
BEGIN
    INSERT OR IGNORE INTO video_tags_dirty (video_id) VALUES (new.id);
END;
CREATE TRIGGER IF NOT EXISTS trg_video_tags_update AFTER UPDATE OF tags ON videos
BEGIN
    INSERT OR IGNORE INTO video_tags_dirty (video_id) VALUES (new.id);
END;
CREATE TRIGGER IF NOT EXISTS trg_video_tags_delete AFTER DELETE ON videos
BEGIN
    DELETE FROM video_tags_dirty WHERE video_id = old.id;
END;
"""

BATCH = 500                    # Videos je Portion im Hintergrund
_FLUSH_BEFORE_QUERY = 500      # vor einer Abfrage höchstens so viele nachziehen
_CHUNK = 500                   # Kennungen je IN-Liste

_lock = asyncio.Lock()


async def install_schema(connection, *, backfill: bool) -> None:
    """Tabellen und Trigger anlegen; backfill=True merkt den Bestand vor."""
    await connection.executescript(SCHEMA_SQL)
    if backfill:
        cursor = await connection.execute(
            "INSERT OR IGNORE INTO video_tags_dirty (video_id) "
            "SELECT id FROM videos WHERE tags IS NOT NULL AND tags NOT IN ('', '[]')")
        logger.info(f"Migration v59: {cursor.rowcount} Videos für den Schlagwort-Index vorgemerkt")
    await connection.commit()


def search_key(tag: str) -> str:
    """Suchschlüssel eines Schlagworts: NFC, ohne Groß und Klein, Leerraum einfach.
    Reines ASCII (die meisten) braucht keine Unicode-Form, casefold ist dort lower."""
    text = str(tag)
    if text.isascii():
        return " ".join(text.lower().split())
    folded = unicodedata.normalize("NFC", text).casefold()
    return unicodedata.normalize("NFC", " ".join(folded.split()))


def parse(raw) -> list[str]:
    """Schlagwörter aus videos.tags (JSON-Liste); Unlesbares zählt als keine."""
    if not raw:
        return []
    try:
        tags = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return []
    return [str(tag) for tag in tags if str(tag).strip()] if isinstance(tags, list) else []


def keyed(raw) -> dict[str, str]:
    """Die Regel des Index: Schlüssel -> Schreibweise (die erste) eines Videos."""
    found: dict[str, str] = {}
    for tag in parse(raw):
        key = search_key(tag)
        if key and key not in found:
            found[key] = " ".join(tag.split())
    return found


def rows_of(video_id: str, raw) -> list[tuple[str, str, str]]:
    """Zeilen eines Videos: (video_id, tag_suche, tag)."""
    return [(video_id, key, tag) for key, tag in keyed(raw).items()]


def _chunks(items: list[str]) -> Iterable[list[str]]:
    for start in range(0, len(items), _CHUNK):
        yield items[start:start + _CHUNK]


async def index_videos(video_ids: Iterable[str]) -> int:
    """Die eine Funktion, die den Index schreibt: Zeilen dieser Videos aus
    videos.tags neu bilden und sie von der Warteliste nehmen. Erst austragen,
    dann lesen - ändert sich ein Video währenddessen, bleibt seine neue Marke."""
    ids = list(dict.fromkeys(video_ids))
    if not ids:
        return 0
    async with _lock:
        for chunk in _chunks(ids):
            marks = ",".join("?" * len(chunk))
            await db.conn.execute(f"DELETE FROM video_tags_dirty WHERE video_id IN ({marks})", chunk)
            rows = await (await db.conn.execute(f"SELECT id, tags FROM videos WHERE id IN ({marks})", chunk)).fetchall()
            await db.conn.execute(f"DELETE FROM video_tags WHERE video_id IN ({marks})", chunk)
            await db.conn.executemany("INSERT INTO video_tags (video_id, tag_suche, tag) VALUES (?, ?, ?)",
                                      [entry for row in rows for entry in rows_of(row["id"], row["tags"])])
        await db.conn.commit()
    return len(ids)


async def pending() -> int:
    return await db.fetch_val("SELECT COUNT(*) FROM video_tags_dirty") or 0


async def flush(limit: Optional[int] = None) -> int:
    """Warteliste abarbeiten (höchstens limit Videos). Gibt die Zahl zurück."""
    rows = await db.fetch_all("SELECT video_id FROM video_tags_dirty" + (" LIMIT ?" if limit else ""),
                              (limit,) if limit else ())
    return await index_videos(row["video_id"] for row in rows)


async def refresh_before_query() -> None:
    """Vor einer Abfrage ein Stück der Warteliste nachziehen: frisch Geändertes
    ist sofort findbar, die Antwort bleibt schnell."""
    await flush(limit=_FLUSH_BEFORE_QUERY)


async def ensure(video_ids: Optional[list[str]] = None) -> bool:
    """Ist der Index für diese Videos (None: alle) aktuell? Wartende unter
    bestimmten Videos werden gleich nachgezogen; für alle ein Stück wie vor
    einer Abfrage, den großen Bestand zieht der Hintergrund nach."""
    if video_ids is None:
        await refresh_before_query()
        return not await pending()
    waiting = []
    for chunk in _chunks(list(video_ids)):
        marks = ",".join("?" * len(chunk))
        waiting += [row["video_id"] for row in await db.fetch_all(
            f"SELECT video_id FROM video_tags_dirty WHERE video_id IN ({marks})", chunk)]
    await index_videos(waiting)
    return True


async def background_catch_up() -> None:
    """Beim Start: die Warteliste in Portionen abarbeiten (der Bestand nach der
    Einführung, sonst nur, was zwischendurch liegen blieb)."""
    waiting = await pending()
    if not waiting:
        return
    logger.info(f"[SCHLAGWÖRTER] {waiting} Videos werden in den Index aufgenommen")
    while await flush(limit=BATCH):
        await asyncio.sleep(0.05)
    logger.info("[SCHLAGWÖRTER] Index ist aktuell")


# ─── Abfragen ─────────────────────────────────────────────────────────

def condition(tags: list[str], alias: str = "v") -> tuple[str, list]:
    """Listenfilter: Videos mit einem dieser Schlagwörter (genau, Schreibweise egal)."""
    keys = list(dict.fromkeys(key for key in map(search_key, tags) if key))
    if not keys:
        return "0", []
    marks = ",".join("?" * len(keys))
    return f"{alias}.id IN (SELECT video_id FROM video_tags WHERE tag_suche IN ({marks}))", keys


def contains_condition(needle: str, alias: str = "t") -> tuple[str, list]:
    """Schlagwort enthält needle (Teilwort, Schreibweise egal; ohne Platzhalter)."""
    return f"instr({alias}.tag_suche, ?) > 0", [search_key(needle)]


async def counts(where: str, params: list) -> list[dict]:
    """Schlagwörter der Videos v, die where erfüllen, mit Anzahl: je Schlüssel
    jedes Video einmal - genau so viele, wie der Listenfilter mit diesem
    Schlagwort findet. Angezeigt wird die häufigste Schreibweise; key ist der
    Schlüssel. Meiste Videos zuerst.

    Gezählt wird aus der gespeicherten Quelle mit derselben Regel, nach der
    index_videos die Zeilen bildet (keyed) - gleich dem Index, sobald dieser
    aktuell ist. Gemessen
    19.10.2026 mit dem Bestand (30.008 Videos mit Schlagwörtern, 499.000
    Zuordnungen, Archiv, am Mac; der Pi braucht rund dreimal so lang): über
    den Index 0,55 s, die ganze Zeit in der einen Datenbankverbindung; aus der
    Quelle 0,06 s in der Datenbank (nur die Spalte lesen) und 0,42 s
    Zusammenzählen neben der Ereignisschleife, andere Anfragen laufen weiter."""
    rows = await db.fetch_all(
        f"SELECT v.tags FROM videos v WHERE {where} AND v.tags IS NOT NULL AND v.tags NOT IN ('', '[]')", params)
    return await asyncio.to_thread(_tally, [row[0] for row in rows])


def _tally(raws: list[str]) -> list[dict]:
    """Zählen wie keyed, je Aufruf mit Gedächtnis je Schreibweise (viele Videos
    teilen ihre Schlagwörter, der Schlüssel wird so je Schreibweise einmal gerechnet)."""
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

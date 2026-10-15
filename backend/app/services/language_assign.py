"""
TubeVault - Sprache zuordnen: Videos, Feed-Einträge, Kanäle

Hält die Spalten aktuell, die language.py beschreibt:
  videos.language / language_source         Sprache je Video und ihre Herkunft
  rss_entries.language / language_source    dasselbe je Feed-Eintrag
  subscriptions.language                    abgeleitete Kanalsprache ("mul" = gemischt)
  *.language_checked                        Stand der Regeln, mit dem zuletzt bewertet wurde

Zwei Schritte, immer in dieser Reihenfolge:
  1. Bewerten (evaluate_videos / evaluate_entries): eigene Hinweise eines
     Videos - Angabe beim Laden, Untertitel/Transkript, Titel und
     Beschreibung; ein Feed-Eintrag übernimmt die Angabe am geladenen Video.
  2. Kanäle (refresh_channels): Kanalsprache aus den bewerteten ableiten -
     die einzige Stelle, die subscriptions.language setzt - und Videos und
     Einträgen ohne eigene Angabe die eindeutige Kanalsprache geben.

Der Bestand wird im Hintergrund nachgezogen (worker): rein lokal, in
Portionen, idempotent - bewertet wird, was language_checked unter dem
aktuellen Stand der Regeln hat. Neu Geladenes und neue Feed-Einträge werden
sofort bewertet (refresh_videos, refresh_new_entries).
"""
import asyncio
import logging
import time
from typing import Iterable, Optional

from app.database import db
from app.models.language import LanguageCount
from app.services import language, language_detect
from app.services.language import Assignment

logger = logging.getLogger(__name__)

BATCH = 400                       # Videos bzw. Einträge je Portion
PAUSE_BETWEEN_BATCHES_S = 0.3     # schonend: der Pi bleibt für anderes frei
IDLE_S = 60                       # nichts zu tun: so lange bis zum nächsten Blick
START_DELAY_S = 45                # erst den Start der übrigen Dienste abwarten
FULL_REFRESH_S = 6 * 3600         # alle Kanäle neu ableiten (z.B. nach Löschungen)
REFRESH_DURING_BACKLOG_S = 120    # beim Nachziehen: so oft die Kanäle zwischendurch ableiten
_CHUNK = 500                      # Platzhalter je IN-Liste

_COLUMNS = (
    ("videos", "language_source TEXT"),
    ("videos", "language_checked INTEGER DEFAULT 0"),
    ("rss_entries", "language TEXT"),
    ("rss_entries", "language_source TEXT"),
    ("rss_entries", "language_checked INTEGER DEFAULT 0"),
    ("subscriptions", "language TEXT"),
)
_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_videos_language ON videos(language);
CREATE INDEX IF NOT EXISTS idx_videos_language_checked ON videos(language_checked);
CREATE INDEX IF NOT EXISTS idx_rss_entries_language ON rss_entries(language);
CREATE INDEX IF NOT EXISTS idx_rss_entries_language_checked ON rss_entries(language_checked);
"""


def _marks(items) -> str:
    return ",".join("?" * len(items))


def _chunks(items: list, size: int = _CHUNK):
    for start in range(0, len(items), size):
        yield items[start:start + size]


# ─── Schema ───────────────────────────────────────────────────────────


async def install_schema(connection, adopt_existing: bool = False) -> int:
    """Spalten und Indizes anlegen (bei jedem Start, idempotent). Mit
    adopt_existing (Migration v53) die vorhandenen Angaben übernehmen;
    liefert deren Zahl."""
    for table, column in _COLUMNS:
        try:
            await connection.execute(f"ALTER TABLE {table} ADD COLUMN {column}")
        except Exception as e:
            if "duplicate column" not in str(e).lower():
                raise
    await connection.executescript(_INDEXES)
    adopted = await _adopt_existing(connection) if adopt_existing else 0
    await connection.commit()
    return adopted


async def _adopt_existing(connection) -> int:
    """Vorhandene Angaben stammen aus dem Laden (Original-Tonspur) bzw. aus
    Untertiteln in der Originalsprache: sie gelten als Angabe beim Laden.
    Kürzel werden vereinheitlicht, Unbrauchbares verworfen."""
    rows = await (await connection.execute(
        "SELECT id, language FROM videos WHERE COALESCE(language, '') <> '' AND language_source IS NULL")).fetchall()
    updates = []
    for video_id, raw in rows:
        code = language.normalize(raw)
        updates.append((code, language.QUELLE if code else None, video_id))
    await connection.executemany("UPDATE videos SET language = ?, language_source = ? WHERE id = ?", updates)
    return sum(1 for code, _, _ in updates if code)


# ─── Schritt 1: bewerten ──────────────────────────────────────────────


async def _description(row) -> Optional[str]:
    """Beschreibung aus der Datenbank, sonst aus der Textdatei (nach einer
    Leerung der Spalte liegt sie nur noch dort)."""
    if row["description"]:
        return row["description"]
    from app.services import text_resolver
    try:
        return await text_resolver.get_description(row["id"])
    except Exception:
        return None


async def _store(table: str, key: str, updates: list[tuple]) -> None:
    await db.conn.executemany(
        f"UPDATE {table} SET language = ?, language_source = ?, language_checked = ? WHERE {key} = ?", updates)


async def evaluate_videos(video_ids: Iterable[str]) -> set[str]:
    """Videos nach ihren eigenen Hinweisen bewerten. Liefert die berührten
    Kanäle (für refresh_channels); ihre Feed-Einträge werden neu vorgemerkt."""
    ids = list(dict.fromkeys(video_ids))
    channels: set[str] = set()
    for chunk in _chunks(ids):
        rows = await db.fetch_all(
            f"""SELECT v.id, v.channel_id, v.title, v.description, v.language, v.language_source,
                       (SELECT t.language FROM transcripts t
                        WHERE t.video_id = v.id AND t.status = 'ok') AS spoken
                FROM videos v WHERE v.id IN ({_marks(chunk)})""", chunk)
        if not rows:
            continue
        texts = [(row["title"], await _description(row)) for row in rows]
        found = await asyncio.to_thread(language_detect.detect_many, texts)
        updates = []
        for row, detection in zip(rows, found):
            evidence = {language.UNTERTITEL: language.normalize(row["spoken"]),
                        language.TEXT: detection.code if detection else None}
            result = language.decide(Assignment(row["language"], row["language_source"]), evidence)
            updates.append((result.code, result.source, language.RULES_VERSION, row["id"]))
            if row["channel_id"]:
                channels.add(row["channel_id"])
        await _store("videos", "id", updates)
        found_ids = [row["id"] for row in rows]
        await db.conn.execute(
            f"UPDATE rss_entries SET language_checked = 0 WHERE video_id IN ({_marks(found_ids)})", found_ids)
        await db.conn.commit()
    return channels


async def evaluate_entries(entry_ids: Iterable[int]) -> set[str]:
    """Feed-Einträge bewerten: die Angabe am geladenen Video, sonst Titel und
    Beschreibung des Eintrags. Liefert die berührten Kanäle."""
    ids = list(dict.fromkeys(entry_ids))
    channels: set[str] = set()
    for chunk in _chunks(ids):
        rows = await db.fetch_all(
            f"""SELECT r.id, r.channel_id, r.title, r.description, r.language, r.language_source,
                       v.language AS video_language, v.language_source AS video_source
                FROM rss_entries r LEFT JOIN videos v ON v.id = r.video_id
                WHERE r.id IN ({_marks(chunk)})""", chunk)
        if not rows:
            continue
        # Text nur dort erkennen, wo das Video keine eigene Angabe hat
        needs_text = [not row["video_language"] for row in rows]
        texts = [(row["title"], row["description"]) for row, needed in zip(rows, needs_text) if needed]
        found = iter(await asyncio.to_thread(language_detect.detect_many, texts))
        updates = []
        for row, needed in zip(rows, needs_text):
            detection = next(found) if needed else None
            evidence = {language.TEXT: detection.code if detection else None}
            # Die Angabe am Video gilt mit ihrer Herkunft; die Kanalsprache
            # setzt erst refresh_channels (sie zählt dort nicht mit)
            if row["video_language"] and row["video_source"] not in (None, language.KANAL):
                evidence[row["video_source"]] = row["video_language"]
            result = language.decide(Assignment(row["language"], row["language_source"]), evidence)
            updates.append((result.code, result.source, language.RULES_VERSION, row["id"]))
            channels.add(row["channel_id"])
        await _store("rss_entries", "id", updates)
        await db.conn.commit()
    return channels


# ─── Schritt 2: Kanäle ────────────────────────────────────────────────


async def channel_languages(channel_ids: Optional[list[str]] = None) -> dict[str, Optional[str]]:
    """Kanalsprache je Kanal aus Videos und Feed-Einträgen. Was selbst nur die
    Kanalsprache trägt, zählt nicht mit; ein Video zählt einmal (Angabe am
    Video vor der am Feed-Eintrag). channel_ids None = alle Kanäle."""
    counts: dict[str, dict[str, int]] = {}

    async def collect(where: str, params: list) -> None:
        rows = await db.fetch_all(
            f"""WITH known AS (
                    SELECT v.id AS video_id, v.channel_id, v.language FROM videos v
                    WHERE v.language IS NOT NULL AND COALESCE(v.language_source, '') <> '{language.KANAL}'
                      {where.format(alias='v')}
                    UNION ALL
                    SELECT r.video_id, r.channel_id, r.language FROM rss_entries r
                    WHERE r.language IS NOT NULL AND COALESCE(r.language_source, '') <> '{language.KANAL}'
                      AND NOT EXISTS (SELECT 1 FROM videos w WHERE w.id = r.video_id AND w.language IS NOT NULL)
                      {where.format(alias='r')})
                SELECT channel_id, language, COUNT(DISTINCT video_id) AS n
                FROM known GROUP BY channel_id, language""", params + params)
        for row in rows:
            if row["channel_id"] and row["language"]:
                counts.setdefault(row["channel_id"], {})[row["language"]] = row["n"]

    if channel_ids is None:
        await collect("", [])
    else:
        for chunk in _chunks(list(channel_ids)):
            await collect(f"AND {{alias}}.channel_id IN ({_marks(chunk)})", list(chunk))
    return {channel_id: language.channel_language(per_language) for channel_id, per_language in counts.items()}


async def _all_channel_ids() -> list[str]:
    rows = await db.fetch_all(
        """SELECT channel_id FROM subscriptions
           UNION SELECT channel_id FROM videos WHERE COALESCE(channel_id, '') <> ''
           UNION SELECT channel_id FROM rss_entries""")
    return [row["channel_id"] for row in rows if row["channel_id"]]


async def refresh_channels(channel_ids: Optional[Iterable[str]] = None) -> int:
    """Kanalsprache neu ableiten und weitergeben. Liefert die Zahl der Abos,
    deren Sprache sich geändert hat. channel_ids None = alle Kanäle."""
    targets = await _all_channel_ids() if channel_ids is None else sorted({c for c in channel_ids if c})
    if not targets:
        return 0
    derived = await channel_languages(None if channel_ids is None else targets)
    single, cleared = [], []
    for channel_id in targets:
        code = derived.get(channel_id)
        if code and code != language.MIXED:
            single.append((code, channel_id, code))
        else:
            cleared.append((channel_id,))
    cursor = await db.conn.executemany(
        "UPDATE subscriptions SET language = ? WHERE channel_id = ? AND language IS NOT ?",
        [(derived.get(channel_id), channel_id, derived.get(channel_id)) for channel_id in targets])
    changed = max(cursor.rowcount, 0)
    # Ohne eigene Angabe (bewertet, aber nichts gefunden) gilt die eindeutige
    # Kanalsprache; ist der Kanal gemischt oder unbekannt, fällt sie weg
    for table in ("videos", "rss_entries"):
        await db.conn.executemany(
            f"""UPDATE {table} SET language = ?, language_source = '{language.KANAL}'
                WHERE channel_id = ? AND language_checked >= 1
                  AND (language_source IS NULL OR language_source = '{language.KANAL}')
                  AND (language IS NOT ? OR language_source IS NULL)""", single)
        await db.conn.executemany(
            f"UPDATE {table} SET language = NULL, language_source = NULL "
            f"WHERE channel_id = ? AND language_source = '{language.KANAL}'", cleared)
    await db.conn.commit()
    return changed


# ─── Einstiege für Laden, Feed und Nutzer ─────────────────────────────


async def record(video_id: str, raw_code, source: str) -> bool:
    """Eine Angabe übernehmen, wenn ihre Herkunft Vorrang hat (z.B. die
    Sprache der Original-Tonspur beim Laden). Danach refresh_videos."""
    code = language.normalize(raw_code)
    current = await db.fetch_one("SELECT language_source FROM videos WHERE id = ?", (video_id,))
    if not code or not current or not language.may_replace(current["language_source"], source):
        return False
    await db.execute("UPDATE videos SET language = ?, language_source = ? WHERE id = ?", (code, source, video_id))
    return True


async def reassess(video_id: str, raw_code=None, source: Optional[str] = None) -> None:
    """Ein Video sofort neu bewerten, etwa nach dem Laden (mit der Angabe der
    Quelle) oder nach einem neuen Transkript - samt Feed-Einträgen und Kanal.
    Wirft nie: scheitert etwas, holt es der Hintergrundlauf nach (das Video
    bleibt vorgemerkt)."""
    try:
        await db.execute("UPDATE videos SET language_checked = 0 WHERE id = ?", (video_id,))
        if source:
            await record(video_id, raw_code, source)
        await refresh_videos([video_id])
    except Exception as e:
        logger.warning(f"[SPRACHE] {video_id} neu bewerten: {e.__class__.__name__}: {e}")


async def _entry_ids_of_videos(video_ids: list[str]) -> list[int]:
    ids: list[int] = []
    for chunk in _chunks(video_ids):
        rows = await db.fetch_all(f"SELECT id FROM rss_entries WHERE video_id IN ({_marks(chunk)})", chunk)
        ids.extend(row["id"] for row in rows)
    return ids


async def refresh_videos(video_ids: Iterable[str]) -> None:
    """Videos sofort neu bewerten (nach dem Laden, nach einem Transkript),
    samt ihren Feed-Einträgen und Kanälen."""
    ids = list(dict.fromkeys(video_ids))
    if not ids:
        return
    channels = await evaluate_videos(ids)
    channels |= await evaluate_entries(await _entry_ids_of_videos(ids))
    await refresh_channels(channels)


async def refresh_new_entries(channel_id: str) -> None:
    """Nach dem Eintragen neuer Feed-Einträge eines Kanals: sofort bewerten.
    Wirft nie - was offen bleibt, holt der Hintergrundlauf nach."""
    try:
        rows = await db.fetch_all(
            "SELECT id FROM rss_entries WHERE channel_id = ? AND language_checked < ?",
            (channel_id, language.RULES_VERSION))
        channels = await evaluate_entries([row["id"] for row in rows])
        await refresh_channels(channels | {channel_id})
    except Exception as e:
        logger.warning(f"[SPRACHE] Feed-Einträge {channel_id}: {e.__class__.__name__}: {e}")


async def set_by_user(video_ids: Iterable[str], raw_code: Optional[str]) -> int:
    """Sprache von Hand festlegen (gilt für Video und Feed-Einträge mit dieser
    Kennung; keine Automatik ändert sie mehr). raw_code None: die Wahl wieder
    aufheben und automatisch bestimmen. Liefert die Zahl der Videos bzw.
    Einträge, die es gibt. Wirft ValueError bei unbekannter Sprache."""
    ids = list(dict.fromkeys(v for v in video_ids if v))
    if not ids:
        return 0
    code = None
    if raw_code is not None:
        code = language.normalize(raw_code)
        if not code:
            raise ValueError(f"Unbekannte Sprache: {raw_code}")
    found: set[str] = set()
    channels: set[str] = set()
    for chunk in _chunks(ids):
        marks = _marks(chunk)
        for table, key in (("videos", "id"), ("rss_entries", "video_id")):
            rows = await db.fetch_all(f"SELECT {key} AS vid, channel_id FROM {table} WHERE {key} IN ({marks})", chunk)
            found.update(row["vid"] for row in rows)
            channels.update(row["channel_id"] for row in rows if row["channel_id"])
            if code:
                await db.conn.execute(
                    f"""UPDATE {table} SET language = ?, language_source = '{language.HAND}', language_checked = ?
                        WHERE {key} IN ({marks})""", (code, language.RULES_VERSION, *chunk))
            else:
                await db.conn.execute(
                    f"""UPDATE {table} SET language = NULL, language_source = NULL, language_checked = 0
                        WHERE {key} IN ({marks}) AND language_source = '{language.HAND}'""", chunk)
    await db.conn.commit()
    if code:
        await refresh_channels(channels)
    else:
        await refresh_videos(ids)      # bewertet auch Einträge ohne geladenes Video
    from app.services import meta_sidecar
    for video_id in ids:
        await meta_sidecar.write_sidecar(video_id)
    return len(found)


# ─── Hintergrund: Bestand nachziehen ──────────────────────────────────


async def pending() -> int:
    """Videos und Feed-Einträge, die mit dem aktuellen Stand der Regeln noch
    nicht bewertet sind."""
    version = language.RULES_VERSION
    videos = await db.fetch_val("SELECT COUNT(*) FROM videos WHERE language_checked < ?", (version,)) or 0
    entries = await db.fetch_val("SELECT COUNT(*) FROM rss_entries WHERE language_checked < ?", (version,)) or 0
    return videos + entries


async def catch_up(limit: int = BATCH) -> int:
    """Eine Portion nachziehen: erst Videos, dann Feed-Einträge. Liefert die
    Zahl der bewerteten Zeilen (0 = nichts mehr offen). Die Kanäle leitet der
    Hintergrundlauf danach gesammelt ab - je Portion wäre das bei einem großen
    Bestand das Teuerste (gemessen: 85 % der Zeit)."""
    version = language.RULES_VERSION
    video_ids = [row["id"] for row in await db.fetch_all(
        "SELECT id FROM videos WHERE language_checked < ? LIMIT ?", (version, limit))]
    await evaluate_videos(video_ids)
    entry_ids = [row["id"] for row in await db.fetch_all(
        "SELECT id FROM rss_entries WHERE language_checked < ? LIMIT ?", (version, limit))]
    await evaluate_entries(entry_ids)
    return len(video_ids) + len(entry_ids)


async def worker() -> None:
    """Hintergrundlauf (task_manager): Bestand in Portionen nachziehen und
    zwischendurch sowie am Ende alle Kanalsprachen ableiten; ist nichts
    offen, alle paar Stunden erneut (z.B. nach Löschungen)."""
    await asyncio.sleep(START_DELAY_S)
    last_full: Optional[float] = None    # None = beim nächsten Blick ableiten
    started: Optional[float] = None
    while True:
        done = 0
        try:
            done = await catch_up()
            if done and started is None:
                started = time.monotonic()
                logger.info(f"[SPRACHE] {await pending() + done} Videos und Feed-Einträge werden zugeordnet")
            if not done and started is not None:
                logger.info(f"[SPRACHE] Bestand zugeordnet in {time.monotonic() - started:.0f} s")
                started, last_full = None, None
            interval = REFRESH_DURING_BACKLOG_S if done else FULL_REFRESH_S
            if last_full is None or time.monotonic() - last_full >= interval:
                changed = await refresh_channels(None)
                last_full = time.monotonic()
                if changed:
                    logger.info(f"[SPRACHE] Kanalsprache bei {changed} Kanälen neu bestimmt")
        except Exception as e:
            logger.warning(f"[SPRACHE] Zuordnen unterbrochen: {e.__class__.__name__}: {e}")
        await asyncio.sleep(PAUSE_BETWEEN_BATCHES_S if done else IDLE_S)


# ─── Zähler ───────────────────────────────────────────────────────────


async def counts(sql_from_where: str, params, column: str) -> list[LanguageCount]:
    """Zähler je Sprache für eine Liste: sql_from_where ist "FROM ... WHERE ..."
    der Liste ohne den Sprachfilter, column die Sprachspalte darin."""
    rows = await db.fetch_all(
        f"SELECT {language.code_sql(column)} AS code, COUNT(*) AS n {sql_from_where} GROUP BY 1", params)
    return language.counts_from_rows([(row["code"], row["n"]) for row in rows])

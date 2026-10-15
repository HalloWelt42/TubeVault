"""
TubeVault – Eigene Videos: Einlesen und Stand

Ein Einleser im Hintergrund (Task "own_scan") arbeitet die angeforderten
Ordner nacheinander ab:
  1. Dateien suchen (eigener Strang); neue und geänderte vormerken,
     verschwundene als fehlend kennzeichnen
  2. vorgemerkte Dateien prüfen (NFO oder ffprobe, eigener Strang) und mit
     Bibliothek und Feed abgleichen - jede Datei ist danach sofort sichtbar
  3. alle offenen Dateien des Ordners neu abgleichen, ohne Plattenzugriff
     (die Bibliothek ändert sich zwischen zwei Durchgängen)

Der Stand liegt vollständig in der Datenbank und bleibt nach dem Einlesen
erhalten. Ein Neustart unterbricht nur: ein laufender Ordner steht danach
wieder in der Warteschlange und macht weiter, wo er war; schon geprüfte
Dateien werden nicht noch einmal geöffnet. Ohne eingebundene Sammlung gibt
es schlicht nichts einzulesen - nichts setzt ein externes Laufwerk voraus.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.config import SCAN_DIR
from app.database import db
from app.models.own_files import (Decision, Finding, Match, OwnFile, OwnFolder, ScanPhase,
                                  ScanState)
from app.services import own_inventory, own_matching
from app.services.own_inventory import FileFacts, ListingProgress
from app.utils.file_utils import now_sqlite

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS own_folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,              -- relativ zum Sammlungsordner, '' = alles
    state TEXT NOT NULL DEFAULT 'idle',
    scan_started_at TEXT,
    scan_finished_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS own_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rel_path TEXT NOT NULL UNIQUE,          -- relativ zum Sammlungsordner
    size INTEGER,
    mtime REAL,
    present INTEGER NOT NULL DEFAULT 1,     -- 0: beim letzten Einlesen nicht mehr da
    checked INTEGER NOT NULL DEFAULT 0,     -- Angaben gelesen und abgeglichen
    title TEXT,
    channel_hint TEXT,
    channel_id_hint TEXT,
    duration INTEGER,
    width INTEGER,
    height INTEGER,
    source_id TEXT,
    source_id_certain INTEGER NOT NULL DEFAULT 0,
    thumbnail TEXT,
    finding TEXT NOT NULL DEFAULT 'pending',
    reason TEXT,
    match_json TEXT,
    decision TEXT NOT NULL DEFAULT 'open',
    decided_at TEXT,
    result_video_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_own_files_state ON own_files(decision, present, finding);
"""

CHECK_BATCH = 50
IDLE_WAIT_S = 60


async def install_schema(connection) -> None:
    await connection.executescript(SCHEMA_SQL)
    await connection.commit()


def collection_root() -> Path:
    """Der Sammlungsordner; was darin liegt, lässt sich einlesen."""
    return SCAN_DIR


# ─── Laufender Durchgang (nur im Speicher, der Rest steht in der Datenbank) ───

@dataclass
class _Live:
    folder_id: int
    path: str
    phase: ScanPhase
    listing: ListingProgress = field(default_factory=ListingProgress)


_live: Optional[_Live] = None
_stop: set[int] = set()
_wake = asyncio.Event()


def _scope(path: str) -> tuple[str, tuple]:
    """SQL-Bedingung für alle Dateien unter path (nutzt den Index auf rel_path)."""
    if not path:
        return "1 = 1", ()
    return "rel_path >= ? AND rel_path < ?", (path + "/", path + "0")


def clean_path(raw: str) -> str:
    """Ordnerpfad relativ zur Sammlung; wirft ValueError bei Pfaden nach außen."""
    path = str(raw or "").strip().strip("/")
    if any(part in ("..", ".") for part in Path(path).parts) or Path(path).is_absolute():
        raise ValueError("Ungültiger Ordner")
    return path


# ─── Anfragen der Oberfläche ──────────────────────────────────────────

async def request_scan(raw_path: str) -> int:
    """Ordner (neu) einlesen lassen; liefert die Ordner-Nummer."""
    path = clean_path(raw_path)
    exists = await asyncio.to_thread((collection_root() / path).is_dir)
    if not exists:
        raise ValueError("Ordner nicht gefunden")
    await db.execute("INSERT OR IGNORE INTO own_folders (path) VALUES (?)", (path,))
    folder_id = await db.fetch_val("SELECT id FROM own_folders WHERE path = ?", (path,))
    await _queue(folder_id)
    return folder_id


async def rescan(folder_id: int) -> None:
    if not await db.fetch_val("SELECT 1 FROM own_folders WHERE id = ?", (folder_id,)):
        raise LookupError("Ordner unbekannt")
    await _queue(folder_id)


async def _queue(folder_id: int) -> None:
    _stop.discard(folder_id)
    await db.execute("UPDATE own_folders SET state = ? WHERE id = ? AND state <> ?",
                     (ScanState.QUEUED.value, folder_id, ScanState.RUNNING.value))
    _wake.set()


async def pause(folder_id: int) -> None:
    """Einlesen anhalten; schon geprüfte Dateien bleiben, Fortsetzen macht dort weiter."""
    _stop.add(folder_id)
    if _live and _live.folder_id == folder_id:
        _live.listing.cancelled = True
    await db.execute("UPDATE own_folders SET state = ? WHERE id = ? AND state IN (?, ?)",
                     (ScanState.PAUSED.value, folder_id, ScanState.QUEUED.value, ScanState.RUNNING.value))


async def forget(folder_id: int) -> None:
    """Ordner aus der Liste nehmen; der Stand seiner Dateien bleibt erhalten."""
    await pause(folder_id)
    await db.execute("DELETE FROM own_folders WHERE id = ?", (folder_id,))


# ─── Einleser ─────────────────────────────────────────────────────────

async def worker() -> None:
    """Dauerläufer: arbeitet wartende Ordner nacheinander ab."""
    # Nach einem Neustart: Unterbrochenes macht weiter
    await db.execute("UPDATE own_folders SET state = ? WHERE state = ?",
                     (ScanState.QUEUED.value, ScanState.RUNNING.value))
    while True:
        row = await db.fetch_one("SELECT id, path FROM own_folders WHERE state = ? ORDER BY id LIMIT 1",
                                 (ScanState.QUEUED.value,))
        if not row:
            _wake.clear()
            try:
                await asyncio.wait_for(_wake.wait(), timeout=IDLE_WAIT_S)
            except asyncio.TimeoutError:
                pass
            continue
        await scan(row["id"], row["path"])


async def scan(folder_id: int, path: str) -> None:
    """Einen Ordner einlesen (Suchen, Prüfen, Neu abgleichen)."""
    global _live
    _live = _Live(folder_id, path, ScanPhase.LISTING)
    await db.execute("UPDATE own_folders SET state = ?, scan_started_at = ? WHERE id = ?",
                     (ScanState.RUNNING.value, now_sqlite(), folder_id))
    try:
        listed = await asyncio.to_thread(own_inventory.list_media, collection_root(), path, _live.listing)
        if folder_id in _stop:
            return
        if listed is None:
            # Ordner fehlt (Laufwerk nicht eingehängt): Stand bleibt, nichts gilt als verschwunden
            logger.info(f"[EIGENE] Ordner '{path}' nicht erreichbar - Stand bleibt erhalten")
        else:
            await _sync(path, listed)
            _live.phase = ScanPhase.ANALYSING
            index = await build_index()
            if not await _check_pending(folder_id, path, index):
                return
            await rematch_open(path, index)
        await db.execute(
            "UPDATE own_folders SET state = ?, scan_finished_at = ? WHERE id = ? AND state = ?",
            (ScanState.IDLE.value, now_sqlite(), folder_id, ScanState.RUNNING.value))
        logger.info(f"[EIGENE] Ordner '{path or '(alles)'}' eingelesen")
    finally:
        _live = None
        _stop.discard(folder_id)


async def _sync(path: str, listed: list[own_inventory.ListedFile]) -> None:
    """Gefundene Dateien mit dem gespeicherten Stand abgleichen."""
    scope, params = _scope(path)
    known = {r["rel_path"]: r for r in await db.fetch_all(
        f"SELECT id, rel_path, size, mtime, present FROM own_files WHERE {scope}", params)}
    seen = set()
    new, changed, returned = [], [], []
    for item in listed:
        seen.add(item.rel_path)
        row = known.get(item.rel_path)
        if row is None:
            new.append((item.rel_path, item.size, item.mtime))
        elif row["size"] != item.size or abs((row["mtime"] or 0) - item.mtime) > 1:
            changed.append((item.size, item.mtime, row["id"]))
        elif not row["present"]:
            returned.append((row["id"],))
    gone = [(row["id"],) for rel, row in known.items() if rel not in seen and row["present"]]
    connection = db.conn
    await connection.executemany("INSERT INTO own_files (rel_path, size, mtime) VALUES (?, ?, ?)", new)
    await connection.executemany(
        "UPDATE own_files SET size = ?, mtime = ?, checked = 0, present = 1 WHERE id = ?", changed)
    await connection.executemany("UPDATE own_files SET present = 1 WHERE id = ?", returned)
    await connection.executemany("UPDATE own_files SET present = 0 WHERE id = ?", gone)
    await connection.commit()
    logger.info(f"[EIGENE] '{path or '(alles)'}': {len(listed)} Videos, {len(new)} neu, "
                f"{len(changed)} geändert, {len(gone)} verschwunden")


async def build_index() -> own_matching.MatchIndex:
    """Bibliothek, Feed und Kanäle als Abgleich-Index (aufgebaut im eigenen Strang)."""
    library = await db.fetch_all(
        "SELECT id, title, channel_id, channel_name, duration, file_size FROM videos WHERE status = 'ready'")
    feed = await db.fetch_all(
        """SELECT r.video_id, r.title, r.channel_id, s.channel_name, r.duration
           FROM rss_entries r LEFT JOIN subscriptions s ON s.channel_id = r.channel_id
           WHERE r.title IS NOT NULL""")
    channels = await db.fetch_all(
        """SELECT channel_id, channel_name FROM subscriptions
           UNION SELECT channel_id, MAX(channel_name) FROM videos
           WHERE status = 'ready' AND COALESCE(channel_id, '') <> '' GROUP BY channel_id""")

    def make() -> own_matching.MatchIndex:
        return own_matching.MatchIndex(
            library=(own_matching.KnownVideo(r["id"], r["title"] or "", r["channel_id"], r["channel_name"],
                                             r["duration"], r["file_size"], in_library=True) for r in library),
            feed=(own_matching.KnownVideo(r["video_id"], r["title"], r["channel_id"], r["channel_name"],
                                          r["duration"]) for r in feed),
            channels=((r["channel_id"], r["channel_name"]) for r in channels))
    return await asyncio.to_thread(make)


def _examine(rel_path: str, index: own_matching.MatchIndex) -> Optional[tuple[FileFacts, Match]]:
    facts = own_inventory.probe(collection_root(), rel_path)
    return (facts, own_matching.match(facts, index)) if facts else None


async def _check_pending(folder_id: int, path: str, index: own_matching.MatchIndex) -> bool:
    """Vorgemerkte Dateien prüfen; False, wenn angehalten wurde."""
    scope, params = _scope(path)
    while True:
        rows = await db.fetch_all(
            f"""SELECT id, rel_path FROM own_files WHERE {scope} AND present = 1 AND checked = 0
                ORDER BY rel_path LIMIT {CHECK_BATCH}""", params)
        if not rows:
            return True
        for row in rows:
            if folder_id in _stop:
                return False
            examined = await asyncio.to_thread(_examine, row["rel_path"], index)
            if examined is None:
                await db.execute("UPDATE own_files SET present = 0 WHERE id = ?", (row["id"],))
                continue
            facts, result = examined
            await db.execute(
                """UPDATE own_files SET checked = 1, title = ?, channel_hint = ?, channel_id_hint = ?,
                       duration = ?, width = ?, height = ?, source_id = ?, source_id_certain = ?,
                       thumbnail = ?, finding = ?, reason = ?, match_json = ?
                   WHERE id = ?""",
                (facts.title, facts.channel_hint, index.channel_for(facts.channel_hint),
                 facts.duration, facts.width, facts.height, facts.source_id, int(facts.source_id_certain),
                 facts.thumbnail, result.finding.value, result.reason.value if result.reason else None,
                 _match_json(result), row["id"]))


def _match_json(result: Match) -> Optional[str]:
    return result.model_dump_json() if result.video_id else None


async def rematch_open(path: str, index: Optional[own_matching.MatchIndex] = None) -> int:
    """Offene, geprüfte Dateien neu abgleichen (ohne Plattenzugriff).
    Liefert die Zahl geänderter Befunde."""
    index = index or await build_index()
    scope, params = _scope(path)
    rows = await db.fetch_all(
        f"""SELECT id, title, size, channel_hint, duration, source_id, source_id_certain,
                   finding, reason, match_json
            FROM own_files WHERE {scope} AND present = 1 AND checked = 1 AND decision = ?""",
        (*params, Decision.OPEN.value))

    def compare() -> list[tuple]:
        updates = []
        for row in rows:
            facts = FileFacts(title=row["title"] or "", size=row["size"] or 0, channel_hint=row["channel_hint"],
                              duration=row["duration"], source_id=row["source_id"],
                              source_id_certain=bool(row["source_id_certain"]))
            result = own_matching.match(facts, index)
            new = (result.finding.value, result.reason.value if result.reason else None, _match_json(result))
            if new != (row["finding"], row["reason"], row["match_json"]):
                updates.append((*new, index.channel_for(row["channel_hint"]), row["id"]))
        return updates

    updates = await asyncio.to_thread(compare)
    await db.conn.executemany(
        "UPDATE own_files SET finding = ?, reason = ?, match_json = ?, channel_id_hint = ? WHERE id = ?",
        updates)
    await db.conn.commit()
    return len(updates)


# ─── Stand für die Oberfläche ─────────────────────────────────────────

async def folders() -> list[OwnFolder]:
    rows = await db.fetch_all("SELECT * FROM own_folders ORDER BY path COLLATE NOCASE")
    result = []
    for row in rows:
        scope, params = _scope(row["path"])
        counts = await db.fetch_one(
            f"SELECT COUNT(*) AS files, COALESCE(SUM(checked), 0) AS checked FROM own_files "
            f"WHERE {scope} AND present = 1", params)
        open_rows = await db.fetch_all(
            f"SELECT finding, COUNT(*) AS n FROM own_files WHERE {scope} AND present = 1 AND decision = ? "
            f"GROUP BY finding", (*params, Decision.OPEN.value))
        live = _live if _live and _live.folder_id == row["id"] else None
        result.append(OwnFolder(
            id=row["id"], path=row["path"], state=ScanState(row["state"]),
            phase=live.phase if live else None,
            present=await asyncio.to_thread((collection_root() / row["path"]).is_dir),
            files=counts["files"], checked=counts["checked"],
            found_so_far=live.listing.found if live and live.phase == ScanPhase.LISTING else None,
            open_by_finding={r["finding"]: r["n"] for r in open_rows},
            scan_started_at=row["scan_started_at"], scan_finished_at=row["scan_finished_at"]))
    return result


async def candidates() -> list[str]:
    """Ordner der Sammlung, die sich einlesen lassen (oberste Ebene)."""
    root = collection_root()

    def subfolders() -> list[str]:
        try:
            return sorted((p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")),
                          key=str.casefold)
        except OSError:
            return []
    return await asyncio.to_thread(subfolders)


FILE_FILTERS = {f.value for f in Finding} | {"done"}


async def files(folder_id: int, finding: Optional[str] = None, query: Optional[str] = None,
                offset: int = 0, limit: int = 50) -> tuple[list[OwnFile], int]:
    """Dateien eines Ordners, seitenweise. finding: Befund der offenen
    Dateien, "done" für erledigte, leer für alle offenen."""
    path = await db.fetch_val("SELECT path FROM own_folders WHERE id = ?", (folder_id,))
    if path is None:
        raise LookupError("Ordner unbekannt")
    scope, params = _scope(path)
    where, args = [scope, "present = 1"], list(params)
    if finding == "done":
        where.append("decision <> ?")
        args.append(Decision.OPEN.value)
    else:
        where.append("decision = ?")
        args.append(Decision.OPEN.value)
        if finding:
            if finding not in FILE_FILTERS:
                raise ValueError("Unbekannter Filter")
            where.append("finding = ?")
            args.append(finding)
    if query:
        where.append("(title LIKE ? OR rel_path LIKE ?)")
        args += [f"%{query}%"] * 2
    condition = " AND ".join(where)
    total = await db.fetch_val(f"SELECT COUNT(*) FROM own_files WHERE {condition}", args)
    rows = await db.fetch_all(
        f"SELECT * FROM own_files WHERE {condition} ORDER BY rel_path LIMIT ? OFFSET ?", (*args, limit, offset))
    return [_to_model(r) for r in rows], total


async def file(file_id: int) -> OwnFile:
    row = await db.fetch_one("SELECT * FROM own_files WHERE id = ?", (file_id,))
    if not row:
        raise LookupError("Datei unbekannt")
    return _to_model(row)


def _to_model(row) -> OwnFile:
    rel = Path(row["rel_path"])
    return OwnFile(
        id=row["id"], rel_path=row["rel_path"], name=rel.name, folder=str(rel.parent) if rel.parent != Path(".") else "",
        size=row["size"], duration=row["duration"], width=row["width"], height=row["height"],
        title=row["title"], channel_hint=row["channel_hint"], channel_id_hint=row["channel_id_hint"],
        source_id=row["source_id"], has_thumbnail=bool(row["thumbnail"]),
        finding=Finding(row["finding"]), reason=row["reason"],
        match=Match.model_validate_json(row["match_json"]) if row["match_json"] else None,
        decision=Decision(row["decision"]), result_video_id=row["result_video_id"],
        present=bool(row["present"]))


def resolve(rel_path: str) -> Path:
    """Absoluter Pfad einer Datei der Sammlung; wirft ValueError außerhalb."""
    root = collection_root().resolve()
    path = (root / rel_path).resolve()
    if root != path and root not in path.parents:
        raise ValueError("Pfad außerhalb der Sammlung")
    return path


async def thumbnail_path(file_id: int) -> Optional[Path]:
    rel = await db.fetch_val("SELECT thumbnail FROM own_files WHERE id = ?", (file_id,))
    return resolve(rel) if rel else None


async def media_path(file_id: int) -> Path:
    rel = await db.fetch_val("SELECT rel_path FROM own_files WHERE id = ? AND present = 1", (file_id,))
    if not rel:
        raise LookupError("Datei unbekannt")
    return resolve(rel)


@dataclass
class LiveScan:
    path: str
    phase: ScanPhase
    found: int
    checked: int
    files: int
    since: Optional[str]


async def live() -> Optional[LiveScan]:
    """Was gerade eingelesen wird (für die Hintergrundarbeiten)."""
    current = _live
    if not current:
        return None
    scope, params = _scope(current.path)
    counts = await db.fetch_one(
        f"SELECT COUNT(*) AS files, COALESCE(SUM(checked), 0) AS checked FROM own_files "
        f"WHERE {scope} AND present = 1", params)
    since = await db.fetch_val("SELECT scan_started_at FROM own_folders WHERE id = ?", (current.folder_id,))
    return LiveScan(current.path, current.phase, current.listing.found, counts["checked"], counts["files"], since)

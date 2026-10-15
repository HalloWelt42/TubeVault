"""
TubeVault – Eigene Videos: Einordnen

Was mit einer eingelesenen Datei geschehen kann:
  - löschen        (alte Datei samt Begleitdateien; typisch für Doppelte)
  - übernehmen     (als bekanntes Quellvideo in die Bibliothek)
  - eigenem Kanal  (als eigenes Video, Kanal vorhanden oder neu)
  - ersetzen       (die Datei eines Bibliotheksvideos durch diese)
  - überspringen / wieder öffnen

Übernommene Dateien liegen danach wie geladene Videos unter
VIDEOS_DIR/<id>/video.<ext>. Angaben kommen aus dem, was schon bekannt ist
(Feed, NFO, Datei) - bei der Quelle wird dafür nicht nachgefragt; Kapitel,
Untertitel und Typ ergänzt die übliche Anreicherung später von selbst.
Verschieben, Kopieren und Löschen laufen im eigenen Strang.
"""
import asyncio
import hashlib
import logging
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.config import RSS_THUMBS_DIR, THUMBNAILS_DIR, VIDEOS_DIR
from app.database import db
from app.models.own_files import Decision, Finding, Match
from app.services import own_inventory, own_matching, own_scan
from app.utils.file_utils import now_sqlite

logger = logging.getLogger(__name__)

OWN_VIDEO_PREFIX = "own_"
OWN_CHANNEL_PREFIX = "own_"


class ActionError(Exception):
    """Aktion nicht möglich; die Meldung ist für den Nutzer."""


@dataclass
class _File:
    id: int
    rel_path: str
    title: str
    duration: Optional[int]
    size: Optional[int]
    thumbnail: Optional[str]
    channel_hint: Optional[str]
    match: Optional[Match]
    decision: Decision


async def _load(file_id: int, open_only: bool = True) -> _File:
    row = await db.fetch_one("SELECT * FROM own_files WHERE id = ?", (file_id,))
    if not row:
        raise LookupError("Datei unbekannt")
    decision = Decision(row["decision"])
    if open_only and decision != Decision.OPEN:
        raise ActionError("Die Datei ist schon eingeordnet")
    if open_only and not row["present"]:
        raise ActionError("Die Datei ist nicht mehr da")
    return _File(row["id"], row["rel_path"], row["title"] or Path(row["rel_path"]).stem, row["duration"],
                 row["size"], row["thumbnail"], row["channel_hint"],
                 Match.model_validate_json(row["match_json"]) if row["match_json"] else None, decision)


async def _decide(file_id: int, decision: Decision, video_id: Optional[str] = None) -> None:
    await db.execute("UPDATE own_files SET decision = ?, decided_at = ?, result_video_id = ? WHERE id = ?",
                     (decision.value, now_sqlite(), video_id, file_id))


def own_channel_id(name: str) -> str:
    """Feste Kennung eines eigenen Kanals aus seinem Namen ("Werbespots")."""
    return OWN_CHANNEL_PREFIX + hashlib.sha1(own_matching.channel_key(name).encode()).hexdigest()[:12]


def _move_into_library(source: Path, video_id: str) -> Path:
    """Datei nach VIDEOS_DIR/<id>/video.<ext>; über Laufwerksgrenzen wird kopiert."""
    target = VIDEOS_DIR / video_id / f"video{source.suffix.lower()}"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    return target


def _thumbnail_from(image: Optional[Path], video_id: str) -> Optional[str]:
    if not image or not image.is_file():
        return None
    target = THUMBNAILS_DIR / video_id / f"thumbnail{image.suffix.lower()}"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(image, target)
    return str(target)


def _frame_thumbnail(video: Path, video_id: str, duration: Optional[int]) -> Optional[str]:
    from app.utils.thumbnail_utils import generate_ffmpeg_thumbnail
    made = generate_ffmpeg_thumbnail(video, THUMBNAILS_DIR / video_id / "thumbnail.jpg", duration=duration)
    return str(made) if made else None


def _remove_leftovers(rel_path: str) -> None:
    """Begleitdateien der alten Datei weg, leeren Ordner mit (das Video ist schon verschoben)."""
    root = own_scan.collection_root()
    own_inventory.remove_with_companions(root, rel_path, root / Path(rel_path).parts[0])


async def _after_library_change(video_id: str, title: str) -> None:
    """Begleitdatei, Suche und offene Dateien, die dasselbe Video meinen."""
    from app.services import meta_sidecar
    try:
        await meta_sidecar.write_sidecar(video_id)
        await db.fts_sync_video(video_id)
    except Exception as e:
        logger.warning(f"[EIGENE] Nacharbeit für {video_id}: {e}")
    # Weitere offene Dateien desselben Videos sind jetzt Doppelte
    await db.execute(
        """UPDATE own_files SET finding = ?, match_json = json_set(match_json, '$.in_library', json('true'),
                                                                     '$.finding', ?)
           WHERE decision = 'open' AND json_extract(match_json, '$.video_id') = ?""",
        (Finding.DUPLICATE.value, Finding.DUPLICATE.value, video_id))


# ─── Aktionen ─────────────────────────────────────────────────────────

async def delete(file_id: int) -> None:
    item = await _load(file_id)
    root = own_scan.collection_root()
    await asyncio.to_thread(own_inventory.remove_with_companions, root, item.rel_path,
                            root / Path(item.rel_path).parts[0])
    await _decide(file_id, Decision.DELETED)
    logger.info(f"[EIGENE] gelöscht: {item.rel_path}")


async def adopt(file_id: int, video_id: Optional[str] = None) -> str:
    """Als Quellvideo in die Bibliothek; video_id leer = der erkannte Treffer."""
    item = await _load(file_id)
    video_id = (video_id or (item.match.video_id if item.match else None) or "").strip()
    if len(video_id) != 11:
        raise ActionError("Kein Quellvideo zugeordnet")
    existing = await db.fetch_one("SELECT status FROM videos WHERE id = ?", (video_id,))
    if existing and existing["status"] == "ready":
        raise ActionError("Das Video ist schon in der Bibliothek - alte Datei löschen oder ersetzen")
    feed = await db.fetch_one(
        """SELECT r.title, r.channel_id, s.channel_name, r.published, r.duration, r.description
           FROM rss_entries r LEFT JOIN subscriptions s ON s.channel_id = r.channel_id
           WHERE r.video_id = ? ORDER BY r.id LIMIT 1""", (video_id,))
    title = (feed["title"] if feed else None) or (item.match.title if item.match else None) or item.title
    channel_id = feed["channel_id"] if feed else None
    channel_name = (feed["channel_name"] if feed else None) or (item.match.channel_name if item.match else None)

    root = own_scan.collection_root()
    source = own_scan.resolve(item.rel_path)
    poster = own_scan.resolve(item.thumbnail) if item.thumbnail else RSS_THUMBS_DIR / f"{video_id}.jpg"
    target = await asyncio.to_thread(_move_into_library, source, video_id)
    thumbnail = await asyncio.to_thread(_thumbnail_from, poster, video_id)
    if not thumbnail:
        from app.utils.thumbnail_utils import download_yt_thumbnail
        made = await download_yt_thumbnail(video_id, THUMBNAILS_DIR / video_id, filename="thumbnail.jpg")
        thumbnail = str(made) if made else None
    now = now_sqlite()
    await db.execute(
        """INSERT INTO videos (id, title, channel_id, channel_name, description, duration, upload_date,
                               download_date, thumbnail_path, file_path, file_size, status, source,
                               source_url, import_path, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready', 'imported', ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
               title = COALESCE(NULLIF(videos.title, ''), excluded.title),
               channel_id = COALESCE(NULLIF(videos.channel_id, ''), excluded.channel_id),
               channel_name = COALESCE(NULLIF(videos.channel_name, ''), excluded.channel_name),
               description = COALESCE(NULLIF(videos.description, ''), excluded.description),
               duration = COALESCE(videos.duration, excluded.duration),
               upload_date = COALESCE(videos.upload_date, excluded.upload_date),
               download_date = excluded.download_date,
               thumbnail_path = COALESCE(excluded.thumbnail_path, videos.thumbnail_path),
               file_path = excluded.file_path, file_size = excluded.file_size,
               status = 'ready', source = 'imported', import_path = excluded.import_path,
               updated_at = excluded.updated_at""",
        (video_id, title, channel_id, channel_name, feed["description"] if feed else None,
         item.duration or (feed["duration"] if feed else None), feed["published"] if feed else None,
         now, thumbnail, str(target), target.stat().st_size,
         f"https://www.youtube.com/watch?v={video_id}", item.rel_path, now, now))
    await asyncio.to_thread(_remove_leftovers, item.rel_path)
    await _decide(file_id, Decision.ADOPTED, video_id)
    await _after_library_change(video_id, title)
    logger.info(f"[EIGENE] übernommen als {video_id}: {item.rel_path}")
    return video_id


async def make_own(file_id: int, channel_name: str, channel_id: Optional[str] = None,
                   title: Optional[str] = None) -> str:
    """Als eigenes Video einem Kanal zuordnen. channel_id leer = eigener
    Kanal mit diesem Namen (gleicher Name, gleicher Kanal)."""
    item = await _load(file_id)
    channel_name = (channel_name or "").strip()
    if not channel_name:
        raise ActionError("Kanal fehlt")
    if not channel_id:
        known = await db.fetch_val("SELECT channel_id FROM subscriptions WHERE channel_name = ? COLLATE NOCASE",
                                   (channel_name,))
        channel_id = known or own_channel_id(channel_name)
    # Ein schon benutzter Kanal behält seine Schreibweise
    channel_name = await db.fetch_val(
        """SELECT channel_name FROM subscriptions WHERE channel_id = ?
           UNION ALL SELECT channel_name FROM videos WHERE channel_id = ? LIMIT 1""",
        (channel_id, channel_id)) or channel_name
    video_id = OWN_VIDEO_PREFIX + uuid.uuid4().hex[:12]
    title = (title or item.title).strip() or item.title

    source = own_scan.resolve(item.rel_path)
    poster = own_scan.resolve(item.thumbnail) if item.thumbnail else None
    target = await asyncio.to_thread(_move_into_library, source, video_id)
    thumbnail = await asyncio.to_thread(_thumbnail_from, poster, video_id) \
        or await asyncio.to_thread(_frame_thumbnail, target, video_id, item.duration)
    now = now_sqlite()
    await db.execute(
        """INSERT INTO videos (id, title, channel_id, channel_name, duration, download_date, thumbnail_path,
                               file_path, file_size, status, source, import_path, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready', 'local', ?, ?, ?)""",
        (video_id, title, channel_id, channel_name, item.duration, now, thumbnail, str(target),
         target.stat().st_size, item.rel_path, now, now))
    await asyncio.to_thread(_remove_leftovers, item.rel_path)
    await _decide(file_id, Decision.OWN, video_id)
    await _after_library_change(video_id, title)
    logger.info(f"[EIGENE] eigenes Video {video_id} in '{channel_name}': {item.rel_path}")
    return video_id


async def replace(file_id: int) -> str:
    """Die Datei des erkannten Bibliotheksvideos durch diese ersetzen (etwa
    wenn die alte Datei die bessere Fassung ist). Die bisherige Datei geht."""
    item = await _load(file_id)
    if not item.match or not item.match.in_library:
        raise ActionError("Kein Bibliotheksvideo zugeordnet")
    video = await db.fetch_one("SELECT id, file_path, storage_type FROM videos WHERE id = ? AND status = 'ready'",
                               (item.match.video_id,))
    if not video:
        raise ActionError("Das Bibliotheksvideo gibt es nicht mehr")
    if (video["storage_type"] or "local") != "local":
        raise ActionError("Das Video liegt in einem externen Archiv und wird dort nicht verändert")
    source = own_scan.resolve(item.rel_path)
    previous = Path(video["file_path"]) if video["file_path"] else None

    def swap() -> Path:
        target = VIDEOS_DIR / video["id"] / f"video{source.suffix.lower()}"
        staged = target.with_name(f".ersatz{source.suffix.lower()}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(staged))     # erst vollständig da, dann tauschen
        if previous and previous.is_file() and previous.resolve().parent == target.parent.resolve():
            previous.unlink()
        staged.replace(target)
        return target

    target = await asyncio.to_thread(swap)
    await db.execute("UPDATE videos SET file_path = ?, file_size = ?, updated_at = ? WHERE id = ?",
                     (str(target), target.stat().st_size, now_sqlite(), video["id"]))
    await asyncio.to_thread(_remove_leftovers, item.rel_path)
    await _decide(file_id, Decision.REPLACED, video["id"])
    logger.info(f"[EIGENE] Datei von {video['id']} ersetzt durch {item.rel_path}")
    return video["id"]


async def skip(file_id: int) -> None:
    await _load(file_id)
    await _decide(file_id, Decision.SKIPPED)


async def reopen(file_id: int) -> None:
    """Übersprungene Datei wieder zum Einordnen anbieten."""
    item = await _load(file_id, open_only=False)
    if item.decision != Decision.SKIPPED:
        raise ActionError("Nur übersprungene Dateien lassen sich wieder öffnen")
    await _decide(file_id, Decision.OPEN)


# ─── Sammelaktionen (im Hintergrund, eine zur Zeit) ───────────────────

BULK_ACTIONS = {"delete_duplicates": (Finding.DUPLICATE, "gelöscht"),
                "adopt_certain": (Finding.CERTAIN, "übernommen")}


@dataclass
class BulkRun:
    action: str
    folder_path: str
    done: int = 0
    failed: int = 0
    total: int = 0
    since: str = ""


_bulk: Optional[BulkRun] = None


def bulk_running() -> Optional[BulkRun]:
    return _bulk


async def start_bulk(folder_id: int, action: str) -> BulkRun:
    """Alle offenen Dateien eines Befunds im Ordner bearbeiten."""
    global _bulk
    if action not in BULK_ACTIONS:
        raise ActionError("Unbekannte Sammelaktion")
    if _bulk:
        raise ActionError("Es läuft schon eine Sammelaktion")
    path = await db.fetch_val("SELECT path FROM own_folders WHERE id = ?", (folder_id,))
    if path is None:
        raise LookupError("Ordner unbekannt")
    finding, _ = BULK_ACTIONS[action]
    scope, params = own_scan._scope(path)
    ids = [r["id"] for r in await db.fetch_all(
        f"SELECT id FROM own_files WHERE {scope} AND present = 1 AND decision = 'open' AND finding = ? "
        f"ORDER BY rel_path", (*params, finding.value))]
    _bulk = BulkRun(action, path, total=len(ids), since=now_sqlite())
    asyncio.create_task(_run_bulk(_bulk, ids))
    return _bulk


async def _run_bulk(run: BulkRun, ids: list[int]) -> None:
    global _bulk
    work = delete if run.action == "delete_duplicates" else adopt
    try:
        for file_id in ids:
            try:
                await work(file_id)
                run.done += 1
            except (ActionError, LookupError, OSError, ValueError) as e:
                run.failed += 1
                logger.warning(f"[EIGENE] Sammelaktion {run.action}, Datei {file_id}: {e}")
    finally:
        _bulk = None
        logger.info(f"[EIGENE] Sammelaktion {run.action}: {run.done} erledigt, {run.failed} nicht möglich")


# ─── Eingeordnet ──────────────────────────────────────────────────────

async def channels() -> list[dict]:
    """Kanäle zur Auswahl beim Zuordnen: Abos und eigene Kanäle."""
    # Zwei Abfragen statt UNION mit Gruppierung: SQLite 3.47 liefert dort
    # bei leerer Gruppe eine Zeile aus lauter NULL
    abos = await db.fetch_all(
        "SELECT channel_id, channel_name, 'abo' AS kind FROM subscriptions WHERE COALESCE(channel_name, '') <> ''")
    own = await db.fetch_all(
        """SELECT channel_id, MAX(channel_name) AS channel_name, 'eigen' AS kind FROM videos
           WHERE channel_id LIKE 'own\\_%' ESCAPE '\\' AND COALESCE(channel_name, '') <> ''
           GROUP BY channel_id""")
    rows = sorted([*abos, *own], key=lambda r: r["channel_name"].casefold())
    return [dict(r) for r in rows]

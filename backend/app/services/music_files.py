"""
TubeVault – Musikdateien (FLAC und andere Tondateien)

Die eigene Musiksammlung ist die zweite Quelle der Musik neben den Videos
(Wunsch 15.10.2026). Eingelesen wird der Ordner MUSIC_FILES_DIR (im Container
nur lesend eingehängt):
- Angaben aus den Tags (mutagen): Titel, Interpret, Album-Interpret, Album,
  Nummer, CD, Jahr, Genre, Dauer, Format, Bitrate, Abtastrate, Bittiefe.
  Fehlen sie, hilft der Dateiname ("01. Interpret - Titel").
- Cover: eingebettetes Bild oder cover/folder/front.jpg im Ordner,
  verkleinert zwischengespeichert in MUSIC_COVERS_DIR. Dazu die Prüfsumme
  der Bildbytes (cover_hash): Titel mit gleichem Cover sind ein Album
  (music_library). Für den Bestand von davor trägt fill_cover_hashes sie
  nach dem Einlesen nach.
- Liedtext: .lrc mit gleichem Namen (mitlaufend) oder Text im Tag.
Neu gelesen wird nur, was sich geändert hat (Größe, Änderungszeit);
Verschwundenes fällt heraus. Wiedergaben und Lieblingssongs merkt sich die
Tabelle selbst - die Dateien bleiben unberührt.

Hörbücher und Hörspiele sind keine Musik (Wunsch 15.10.2026): Jede Datei
bekommt eine Art (category). Hörbuch ist, was Genre oder Ordner so nennt
(Hörbuch, Hörspiel, Audiobook, Spoken Word, Lesung); sie fallen aus allen
Musiklisten und Mixen heraus und werden für sich in ihrer Reihenfolge gespielt.
"""
import asyncio
import hashlib
import logging
import os
import re
import time
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Optional

from pydantic import BaseModel

from app.config import MUSIC_COVERS_DIR, MUSIC_FILES_DIR
from app.database import db

logger = logging.getLogger(__name__)

AUDIO_SUFFIXES = {".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wav", ".aiff", ".aif", ".wv", ".ape"}
FOLDER_COVERS = ("cover.jpg", "cover.png", "folder.jpg", "folder.png", "front.jpg", "front.png")
COVER_SIZE = 600
EMBEDDED = "embedded"
COVER_HASH_BATCH = 50                 # so viele Dateien je Portion beim Nachtragen
ID_PREFIX = "f"
MUSIC = "musik"
AUDIOBOOK = "hoerbuch"
_AUDIOBOOK_WORDS = ("hörbuch", "hoerbuch", "hörspiel", "hoerspiel", "audiobook", "audio book", "spoken word",
                    "lesung", "hörbücher", "hörspiele")
MIME = {".flac": "audio/flac", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".ogg": "audio/ogg", ".opus": "audio/ogg",
        ".wav": "audio/wav", ".aiff": "audio/aiff", ".aif": "audio/aiff", ".wv": "audio/x-wavpack", ".ape": "audio/x-ape"}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS music_files (
    id TEXT PRIMARY KEY,              -- 'f' + Prüfsumme des Pfads
    path TEXT NOT NULL UNIQUE,        -- relativ zu MUSIC_FILES_DIR
    size INTEGER,
    mtime REAL,
    title TEXT,
    artist TEXT,
    album_artist TEXT,
    album TEXT,
    track_no INTEGER,
    disc_no INTEGER,
    year INTEGER,
    genre TEXT,
    duration REAL,
    codec TEXT,
    bitrate INTEGER,
    sample_rate INTEGER,
    bit_depth INTEGER,
    channels INTEGER,
    cover TEXT,                       -- 'embedded' | Pfad des Ordnerbilds | NULL
    lyrics_path TEXT,                 -- .lrc neben der Datei
    lyrics_text TEXT,                 -- Liedtext aus dem Tag
    play_count INTEGER DEFAULT 0,
    last_played TEXT,
    favorite INTEGER DEFAULT 0,
    added_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_music_files_artist ON music_files(artist);
CREATE TABLE IF NOT EXISTS music_files_scan (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    finished_at TEXT,
    files INTEGER,
    read INTEGER,
    removed INTEGER,
    seconds REAL
);
"""


class ScanResult(BaseModel):
    files: int
    read: int
    removed: int
    seconds: float


class FileInfo(BaseModel):
    """Ein Musikstück aus der Sammlung (für Anzeige, Spieler, Bibliothek)."""
    id: str
    path: str
    title: str
    artist: Optional[str] = None
    album_artist: Optional[str] = None
    album: Optional[str] = None
    track_no: Optional[int] = None
    disc_no: Optional[int] = None
    year: Optional[int] = None
    genre: Optional[str] = None
    duration: Optional[float] = None
    codec: Optional[str] = None
    bitrate: Optional[int] = None
    sample_rate: Optional[int] = None
    bit_depth: Optional[int] = None
    channels: Optional[int] = None
    category: str = MUSIC             # musik | hoerbuch
    has_cover: bool = False
    cover_hash: Optional[str] = None  # gleiche Prüfsumme = gleiches Bild
    has_lyrics: bool = False
    play_count: int = 0
    last_played: Optional[str] = None
    favorite: bool = False
    hidden: bool = False              # vom Nutzer ausgeblendet; die Datei bleibt unberührt
    hidden_at: Optional[str] = None
    added_at: Optional[str] = None


async def install_schema(connection) -> None:
    await connection.executescript(SCHEMA_SQL)
    for column in (f"category TEXT DEFAULT '{MUSIC}'", "hidden INTEGER DEFAULT 0", "hidden_at TEXT",
                   "cover_hash TEXT"):   # sha1 der Bildbytes, wie sie in Datei oder Ordnerbild stehen
        try:
            await connection.execute(f"ALTER TABLE music_files ADD COLUMN {column}")
        except Exception:
            pass  # Spalte existiert bereits
    await connection.commit()


def category_of(relpath: str, genre: Optional[str]) -> str:
    """Hörbuch, wenn Genre oder ein Ordner im Pfad es so nennt, sonst Musik.
    Der Dateiname zählt nicht: "Sendeschluss (Hörspiel Version)" ist ein Lied."""
    text = f"{genre or ''} {PurePosixPath(relpath).parent}".casefold()
    return AUDIOBOOK if any(word in text for word in _AUDIOBOOK_WORDS) else MUSIC


def is_file_id(item_id: str) -> bool:
    return len(item_id) == 16 and item_id.startswith(ID_PREFIX) and all(c in "0123456789abcdef" for c in item_id[1:])


def file_id(relpath: str) -> str:
    return ID_PREFIX + hashlib.sha1(relpath.encode("utf-8")).hexdigest()[:15]


def root() -> Path:
    return MUSIC_FILES_DIR


def available() -> bool:
    return root().is_dir()


# ─── Tags lesen ───────────────────────────────────────────────────────

_NAME = re.compile(r"^(?:\d+[.\s_-]+)?(?P<artist>.+?)\s+-\s+(?P<title>.+)$")
_NUMBERED = re.compile(r"^(?P<no>\d{1,4})[.\s_-]+(?P<rest>.+)$")


def _first(tags, *keys) -> Optional[str]:
    if not tags:
        return None
    for key in keys:
        try:
            value = tags.get(key)
        except (KeyError, ValueError):   # Name in diesem Tag-Format nicht erlaubt
            continue
        if value:
            value = value[0] if isinstance(value, list) else value
            text = str(value).strip()
            if text:
                return text
    return None


def _number(text: Optional[str]) -> Optional[int]:
    match = re.match(r"\d+", text or "")
    return int(match.group()) if match else None


def read_tags(path: Path) -> dict:
    """Angaben einer Datei (Tags, Technik, Cover, Liedtext); Dateiname als Rückfall.
    Höchstens zwei Zugriffe: einmal mit vereinheitlichten Tag-Namen, einmal roh
    (Bilder und Liedtext) - bei FLAC reicht einer."""
    import mutagen
    try:
        easy = mutagen.File(path, easy=True)
        raw = easy if path.suffix.lower() in (".flac", ".ogg", ".opus") else mutagen.File(path)
    except Exception as e:
        logger.debug(f"[MUSIKDATEI] {path.name}: Tags nicht lesbar ({e.__class__.__name__})")
        easy = raw = None
    tags = easy.tags if easy is not None else None
    stream = easy.info if easy is not None else None
    info: dict = {
        "title": _first(tags, "title"), "artist": _first(tags, "artist"),
        "album_artist": _first(tags, "albumartist", "album artist"), "album": _first(tags, "album"),
        "track_no": _number(_first(tags, "tracknumber")), "disc_no": _number(_first(tags, "discnumber")),
        "year": _number(_first(tags, "date", "year", "originaldate")), "genre": _first(tags, "genre"),
        "codec": path.suffix.lstrip(".").upper(),
    }
    if stream is not None:
        info["duration"] = round(getattr(stream, "length", 0) or 0, 2) or None
        info["bitrate"] = getattr(stream, "bitrate", None) or None
        info["sample_rate"] = getattr(stream, "sample_rate", None)
        info["bit_depth"] = getattr(stream, "bits_per_sample", None)
        info["channels"] = getattr(stream, "channels", None)
    numbered = _NUMBERED.match(path.stem)
    if numbered and not info["track_no"]:
        info["track_no"] = int(numbered["no"])   # Reihenfolge, wichtig bei Hörbüchern
    if not info["title"] or not info["artist"]:
        match = _NAME.match(path.stem)
        if match:
            info["artist"] = info["artist"] or match["artist"].strip()
            info["title"] = info["title"] or match["title"].strip()
    info["title"] = info["title"] or (numbered["rest"].strip() if numbered else path.stem)
    info["cover"], info["cover_hash"] = _cover_of(path, raw)
    lrc = path.with_suffix(".lrc")
    info["lyrics_path"] = str(lrc.relative_to(root())) if lrc.is_file() else None
    info["lyrics_text"] = _lyrics_of(raw)
    return info


def _picture_of(audio) -> Optional[bytes]:
    if audio is None:
        return None
    pictures = getattr(audio, "pictures", None)
    if pictures:
        return pictures[0].data
    tags = getattr(audio, "tags", None)
    if tags is None or not hasattr(tags, "keys"):
        return None
    for key in list(tags.keys()):
        if str(key).startswith("APIC"):
            return tags[key].data
        if key == "covr" and tags[key]:
            return bytes(tags[key][0])
    return None


def _digest(data: Optional[bytes]) -> Optional[str]:
    return hashlib.sha1(data).hexdigest() if data else None


def _folder_bytes(relpath: str) -> Optional[bytes]:
    try:
        return (root() / relpath).read_bytes()
    except OSError:
        return None


def _cover_of(path: Path, audio) -> tuple[Optional[str], Optional[str]]:
    """(cover, cover_hash): eingebettetes Bild vor dem Ordnerbild, ohne beides (None, None)."""
    picture = _picture_of(audio)
    if picture:
        return EMBEDDED, _digest(picture)
    folder = _folder_cover(path)
    return folder, _digest(_folder_bytes(folder)) if folder else None


def _cover_hash(relpath: str, cover: str) -> Optional[str]:
    """Prüfsumme des Covers, das am Eintrag steht (zum Nachtragen); None, wenn nicht lesbar."""
    data = _embedded_picture(root() / relpath) if cover == EMBEDDED else _folder_bytes(cover)
    return _digest(data)


def _embedded_picture(path: Path) -> Optional[bytes]:
    import mutagen
    try:
        return _picture_of(mutagen.File(path))
    except Exception:
        return None


def _folder_cover(path: Path) -> Optional[str]:
    for name in FOLDER_COVERS:
        candidate = path.parent / name
        if candidate.is_file():
            return str(candidate.relative_to(root()))
    return None


def _lyrics_of(audio) -> Optional[str]:
    tags = getattr(audio, "tags", None) if audio is not None else None
    if not tags or not hasattr(tags, "get"):
        return None
    for key in ("LYRICS", "UNSYNCEDLYRICS", "lyrics", "unsyncedlyrics", "©lyr"):
        try:
            value = tags.get(key)
        except (KeyError, ValueError):
            continue
        if value:
            text = str(value[0] if isinstance(value, list) else value).strip()
            if text:
                return text
    for key in list(tags.keys()) if hasattr(tags, "keys") else []:
        if str(key).startswith("USLT"):
            text = str(tags[key]).strip()
            if text:
                return text
    return None


# ─── Einlesen ─────────────────────────────────────────────────────────

_scan_lock = asyncio.Lock()


def _walk() -> dict[str, tuple[int, float]]:
    base = root()
    found = {}
    for folder, _, names in os.walk(base):
        for name in names:
            if Path(name).suffix.lower() in AUDIO_SUFFIXES and not name.startswith("."):
                full = Path(folder) / name
                try:
                    stat = full.stat()
                except OSError:
                    continue
                found[str(full.relative_to(base))] = (stat.st_size, stat.st_mtime)
    return found


async def scan() -> ScanResult:
    """Ordner einlesen: neue und geänderte Dateien lesen, Verschwundenes entfernen."""
    async with _scan_lock:
        started = time.monotonic()
        if not available():
            return ScanResult(files=0, read=0, removed=0, seconds=0)
        found = await asyncio.to_thread(_walk)
        known = {r["path"]: (r["size"], r["mtime"]) for r in await db.fetch_all("SELECT path, size, mtime FROM music_files")}
        changed = [p for p, stamp in found.items() if known.get(p) != stamp]
        removed = [p for p in known if p not in found]
        for start in range(0, len(changed), 100):
            batch = changed[start:start + 100]
            infos = await asyncio.to_thread(lambda b=batch: [(p, read_tags(root() / p)) for p in b])
            for relpath, info in infos:
                size, mtime = found[relpath]
                await db.execute(
                    """INSERT INTO music_files (id, path, size, mtime, title, artist, album_artist, album, track_no, disc_no,
                           year, genre, duration, codec, bitrate, sample_rate, bit_depth, channels, cover, cover_hash,
                           lyrics_path, lyrics_text, category)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(path) DO UPDATE SET size = excluded.size, mtime = excluded.mtime, title = excluded.title,
                           artist = excluded.artist, album_artist = excluded.album_artist, album = excluded.album,
                           track_no = excluded.track_no, disc_no = excluded.disc_no, year = excluded.year, genre = excluded.genre,
                           duration = excluded.duration, codec = excluded.codec, bitrate = excluded.bitrate,
                           sample_rate = excluded.sample_rate, bit_depth = excluded.bit_depth, channels = excluded.channels,
                           cover = excluded.cover, cover_hash = excluded.cover_hash,
                           lyrics_path = excluded.lyrics_path, lyrics_text = excluded.lyrics_text,
                           category = excluded.category""",
                    (file_id(relpath), relpath, size, mtime, info["title"], info["artist"], info["album_artist"], info["album"],
                     info["track_no"], info["disc_no"], info["year"], info["genre"], info.get("duration"), info["codec"],
                     info.get("bitrate"), info.get("sample_rate"), info.get("bit_depth"), info.get("channels"),
                     info["cover"], info["cover_hash"], info["lyrics_path"], info["lyrics_text"],
                     category_of(relpath, info["genre"])))
        for relpath in removed:
            await db.execute("DELETE FROM music_files WHERE path = ?", (relpath,))
        result = ScanResult(files=len(found), read=len(changed), removed=len(removed),
                            seconds=round(time.monotonic() - started, 1))
        await db.execute(
            """INSERT INTO music_files_scan (id, finished_at, files, read, removed, seconds)
               VALUES (1, datetime('now'), ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET finished_at = excluded.finished_at, files = excluded.files,
                   read = excluded.read, removed = excluded.removed, seconds = excluded.seconds""",
            (result.files, result.read, result.removed, result.seconds))
        logger.info(f"[MUSIKDATEIEN] {result.files} Dateien, {result.read} gelesen, {result.removed} entfernt "
                    f"({result.seconds} s)")
        return result


MISSING_COVER_HASH = "cover IS NOT NULL AND cover_hash IS NULL"


async def missing_cover_hashes() -> int:
    return await db.fetch_val(f"SELECT COUNT(*) FROM music_files WHERE {MISSING_COVER_HASH}") or 0


async def fill_cover_hashes() -> int:
    """Fehlende Prüfsummen der Cover nachtragen (Bestand von vor cover_hash):
    in Portionen im Hintergrund, die Dateien werden nur gelesen. Was fehlt,
    steht in der Tabelle - ein abgebrochener Lauf macht beim nächsten dort
    weiter; nicht Lesbares bleibt offen und kommt im nächsten Lauf wieder dran.
    Ändert das Einlesen einen Eintrag zwischendurch, gilt dessen Prüfsumme."""
    if not available():
        return 0
    filled, after = 0, ""
    while True:
        rows = await db.fetch_all(
            f"SELECT id, path, cover FROM music_files WHERE {MISSING_COVER_HASH} AND id > ? ORDER BY id LIMIT ?",
            (after, COVER_HASH_BATCH))
        if not rows:
            return filled
        after = rows[-1]["id"]
        hashes = await asyncio.to_thread(lambda b=rows: [(_cover_hash(r["path"], r["cover"]), r["id"], r["cover"]) for r in b])
        found = [entry for entry in hashes if entry[0]]
        await db.conn.executemany(
            f"UPDATE music_files SET cover_hash = ? WHERE id = ? AND cover = ? AND {MISSING_COVER_HASH}", found)
        await db.conn.commit()
        filled += len(found)


async def background_scan() -> None:
    """Beim Start und danach täglich einlesen (nur Geändertes kostet Zeit),
    danach fehlende Prüfsummen der Cover nachtragen."""
    await asyncio.sleep(90)
    while True:
        try:
            await scan()
            filled = await fill_cover_hashes()
            if filled:
                logger.info(f"[MUSIKDATEIEN] {filled} Cover-Prüfsummen nachgetragen")
        except Exception as e:
            logger.warning(f"[MUSIKDATEIEN] Einlesen fehlgeschlagen: {e}")
        await asyncio.sleep(24 * 3600)


# ─── Lesen ────────────────────────────────────────────────────────────

def info_of(row) -> FileInfo:
    """FileInfo aus einer Zeile von music_files (SELECT *)."""
    return FileInfo(**{k: row[k] for k in FileInfo.model_fields
                       if k in row.keys() and k not in ("has_cover", "has_lyrics", "favorite", "hidden")},
                    has_cover=bool(row["cover"]), has_lyrics=bool(row["lyrics_path"] or row["lyrics_text"]),
                    favorite=bool(row["favorite"]), hidden=bool(row["hidden"]) if "hidden" in row.keys() else False)


# Ausgeblendete Dateien zählen nirgends mit: die Sammlung liegt nur lesend vor,
# ausblenden ist dort das Gegenstück zum Löschen eines Videos
VISIBLE = "COALESCE(hidden, 0) = 0"


async def all_files(category: Optional[str] = MUSIC, visible_only: bool = True) -> list[FileInfo]:
    """Sichtbare Dateien einer Art (Standard: Musik), neueste zuerst; None = alle.
    visible_only=False: auch ausgeblendete (z.B. damit ihr Video-Doppel nicht nachrückt)."""
    visible = VISIBLE if visible_only else "1 = 1"
    if category is None:
        return [info_of(r) for r in await db.fetch_all(f"SELECT * FROM music_files WHERE {visible} ORDER BY added_at DESC, path")]
    return [info_of(r) for r in await db.fetch_all(
        f"SELECT * FROM music_files WHERE COALESCE(category, ?) = ? AND {visible} ORDER BY added_at DESC, path",
        (MUSIC, category))]


async def hidden_files() -> list[FileInfo]:
    """Ausgeblendete Dateien, zuletzt ausgeblendete zuerst."""
    return [info_of(r) for r in await db.fetch_all(
        "SELECT * FROM music_files WHERE COALESCE(hidden, 0) = 1 ORDER BY hidden_at DESC, path")]


async def count(category: str = MUSIC) -> int:
    return await db.fetch_val(
        f"SELECT COUNT(*) FROM music_files WHERE COALESCE(category, ?) = ? AND {VISIBLE}", (MUSIC, category)) or 0


async def set_hidden(item_id: str, hidden: bool) -> bool:
    """Ausblenden oder wieder einblenden; die Datei selbst bleibt unberührt."""
    cursor = await db.execute(
        "UPDATE music_files SET hidden = ?, hidden_at = CASE WHEN ? THEN datetime('now') END WHERE id = ?",
        (int(hidden), int(hidden), item_id))
    return cursor.rowcount == 1


# ─── Sicherung: Nutzerdaten der Sammlung (userdata_export, rebuild_service) ───
# Lieblingssong, Wiedergaben, Ausgeblendetes - dazu Pfad und Grundangaben, damit
# ein Neuaufbau den Eintrag schon vor dem nächsten Einlesen zeigen kann.
USERDATA_SQL = """SELECT id, path, title, artist, album, duration, category,
                         favorite, play_count, last_played, hidden, hidden_at
                  FROM music_files
                  WHERE COALESCE(favorite, 0) = 1 OR COALESCE(play_count, 0) > 0 OR COALESCE(hidden, 0) = 1"""


async def restore_userdata(rows: list[dict]) -> int:
    """Gesicherte Nutzerdaten zurückspielen, ohne Frischeres zu überschreiben:
    Lieblingssong und Ausgeblendet bleiben gesetzt, Wiedergaben zählen das
    Höhere. Fehlt die Datei noch in der Tabelle (Neuaufbau vor dem Einlesen),
    entsteht ein Eintrag aus Pfad und Grundangaben; Größe und Zeitstempel
    fehlen ihm, also liest das nächste Einlesen die Datei ganz und behält die
    Nutzerdaten (scan aktualisiert nur die Tags)."""
    changed = 0
    for row in rows:
        if not row.get("id") or not row.get("path"):
            continue
        cursor = await db.execute(
            """INSERT INTO music_files (id, path, title, artist, album, duration, category,
                                        favorite, play_count, last_played, hidden, hidden_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   favorite = MAX(COALESCE(favorite, 0), excluded.favorite),
                   play_count = MAX(COALESCE(play_count, 0), excluded.play_count),
                   last_played = COALESCE(last_played, excluded.last_played),
                   hidden = MAX(COALESCE(hidden, 0), excluded.hidden),
                   hidden_at = COALESCE(hidden_at, excluded.hidden_at)""",
            (row["id"], row["path"], row.get("title") or PurePosixPath(row["path"]).stem, row.get("artist"),
             row.get("album"), row.get("duration"), row.get("category") or MUSIC, int(row.get("favorite") or 0),
             int(row.get("play_count") or 0), row.get("last_played"), int(row.get("hidden") or 0), row.get("hidden_at")))
        changed += max(cursor.rowcount, 0)
    return changed


async def hidden_count() -> int:
    return await db.fetch_val("SELECT COUNT(*) FROM music_files WHERE COALESCE(hidden, 0) = 1") or 0


async def show_again(item_ids: list[str]) -> int:
    """Mehrere ausgeblendete Titel auf einmal wieder einblenden."""
    if not item_ids:
        return 0
    marks = ",".join("?" * len(item_ids))
    cursor = await db.execute(f"UPDATE music_files SET hidden = 0, hidden_at = NULL WHERE id IN ({marks})", item_ids)
    return cursor.rowcount


async def get(item_id: str) -> Optional[FileInfo]:
    row = await db.fetch_one("SELECT * FROM music_files WHERE id = ?", (item_id,))
    return info_of(row) if row else None


async def path_of(item_id: str) -> Optional[Path]:
    relpath = await db.fetch_val("SELECT path FROM music_files WHERE id = ?", (item_id,))
    if not relpath:
        return None
    full = root() / relpath
    return full if full.is_file() else None


def mime_of(path: Path) -> str:
    return MIME.get(path.suffix.lower(), "application/octet-stream")


async def cover_path(item_id: str) -> Optional[Path]:
    """Verkleinertes Cover (zwischengespeichert), None ohne Bild."""
    row = await db.fetch_one("SELECT path, cover, mtime FROM music_files WHERE id = ?", (item_id,))
    if not row or not row["cover"]:
        return None
    cached = MUSIC_COVERS_DIR / f"{item_id}.jpg"
    if cached.is_file() and cached.stat().st_mtime >= (row["mtime"] or 0):
        return cached

    def build() -> Optional[Path]:
        from PIL import Image
        source = root() / row["path"]
        data = _embedded_picture(source) if row["cover"] == EMBEDDED else (root() / row["cover"]).read_bytes()
        if not data:
            return None
        image = Image.open(BytesIO(data)).convert("RGB")
        image.thumbnail((COVER_SIZE, COVER_SIZE))
        MUSIC_COVERS_DIR.mkdir(parents=True, exist_ok=True)
        image.save(cached, "JPEG", quality=88)
        return cached
    try:
        return await asyncio.to_thread(build)
    except Exception as e:
        logger.debug(f"[MUSIKDATEI] Cover {item_id}: {e}")
        return None


async def lyrics(item_id: str) -> dict:
    """Liedtext wie lyrics_service: {plain, synced, offset}."""
    row = await db.fetch_one("SELECT lyrics_path, lyrics_text FROM music_files WHERE id = ?", (item_id,))
    if not row:
        return {"plain": "", "synced": "", "offset": 0.0}
    synced = ""
    if row["lyrics_path"]:
        lrc = root() / row["lyrics_path"]
        try:
            synced = await asyncio.to_thread(lrc.read_text, encoding="utf-8", errors="replace")
        except OSError:
            synced = ""
    plain = row["lyrics_text"] or re.sub(r"^\[[^\]]*\]\s*", "", synced, flags=re.MULTILINE).strip()
    return {"plain": plain, "synced": synced, "offset": 0.0}


async def record_play(item_id: str) -> None:
    await db.execute("UPDATE music_files SET play_count = play_count + 1, last_played = datetime('now') WHERE id = ?",
                     (item_id,))


async def set_favorite(item_id: str, favorite: bool) -> bool:
    cursor = await db.execute("UPDATE music_files SET favorite = ? WHERE id = ?", (int(favorite), item_id))
    return cursor.rowcount > 0


async def status() -> dict:
    row = await db.fetch_one("SELECT * FROM music_files_scan WHERE id = 1")
    return {"available": available(), "root": str(root()),
            "files": await db.fetch_val("SELECT COUNT(*) FROM music_files") or 0,
            "hidden": await db.fetch_val("SELECT COUNT(*) FROM music_files WHERE COALESCE(hidden, 0) = 1") or 0,
            "last_scan": dict(row) if row else None}

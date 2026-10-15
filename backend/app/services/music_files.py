"""
TubeVault – Musikdateien (FLAC und andere Tondateien)

Die eigene Musiksammlung ist die zweite Quelle der Musik neben den Videos
(Wunsch 15.10.2026). Eingelesen wird der Ordner MUSIC_FILES_DIR (im Container
nur lesend eingehängt):
- Angaben aus den Tags (mutagen): Titel, Interpret, Album-Interpret, Album,
  Nummer, CD, Jahr, Genre, Dauer, Format, Bitrate, Abtastrate, Bittiefe.
  Fehlen sie, hilft der Dateiname ("01. Interpret - Titel").
- Cover: eingebettetes Bild oder cover/folder/front.jpg im Ordner,
  verkleinert zwischengespeichert in MUSIC_COVERS_DIR.
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
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from app.config import MUSIC_COVERS_DIR, MUSIC_FILES_DIR
from app.database import db

logger = logging.getLogger(__name__)

AUDIO_SUFFIXES = {".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wav", ".aiff", ".aif", ".wv", ".ape"}
FOLDER_COVERS = ("cover.jpg", "cover.png", "folder.jpg", "folder.png", "front.jpg", "front.png")
COVER_SIZE = 600
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
    has_lyrics: bool = False
    play_count: int = 0
    last_played: Optional[str] = None
    favorite: bool = False
    added_at: Optional[str] = None


async def install_schema(connection) -> None:
    await connection.executescript(SCHEMA_SQL)
    try:
        await connection.execute(f"ALTER TABLE music_files ADD COLUMN category TEXT DEFAULT '{MUSIC}'")
    except Exception:
        pass  # Spalte existiert bereits
    await connection.commit()


def category_of(relpath: str, genre: Optional[str]) -> str:
    """Hörbuch, wenn Genre oder ein Ordner im Pfad es so nennt, sonst Musik."""
    text = f"{genre or ''} {relpath}".casefold()
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
    info["cover"] = "embedded" if _picture_of(raw) else _folder_cover(path)
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
                           year, genre, duration, codec, bitrate, sample_rate, bit_depth, channels, cover, lyrics_path, lyrics_text,
                           category)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(path) DO UPDATE SET size = excluded.size, mtime = excluded.mtime, title = excluded.title,
                           artist = excluded.artist, album_artist = excluded.album_artist, album = excluded.album,
                           track_no = excluded.track_no, disc_no = excluded.disc_no, year = excluded.year, genre = excluded.genre,
                           duration = excluded.duration, codec = excluded.codec, bitrate = excluded.bitrate,
                           sample_rate = excluded.sample_rate, bit_depth = excluded.bit_depth, channels = excluded.channels,
                           cover = excluded.cover, lyrics_path = excluded.lyrics_path, lyrics_text = excluded.lyrics_text,
                           category = excluded.category""",
                    (file_id(relpath), relpath, size, mtime, info["title"], info["artist"], info["album_artist"], info["album"],
                     info["track_no"], info["disc_no"], info["year"], info["genre"], info.get("duration"), info["codec"],
                     info.get("bitrate"), info.get("sample_rate"), info.get("bit_depth"), info.get("channels"),
                     info["cover"], info["lyrics_path"], info["lyrics_text"], category_of(relpath, info["genre"])))
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


async def background_scan() -> None:
    """Beim Start und danach täglich einlesen (nur Geändertes kostet Zeit)."""
    await asyncio.sleep(90)
    while True:
        try:
            await scan()
        except Exception as e:
            logger.warning(f"[MUSIKDATEIEN] Einlesen fehlgeschlagen: {e}")
        await asyncio.sleep(24 * 3600)


# ─── Lesen ────────────────────────────────────────────────────────────

def _info(row) -> FileInfo:
    return FileInfo(**{k: row[k] for k in FileInfo.model_fields if k in row.keys() and k not in ("has_cover", "has_lyrics", "favorite")},
                    has_cover=bool(row["cover"]), has_lyrics=bool(row["lyrics_path"] or row["lyrics_text"]),
                    favorite=bool(row["favorite"]))


async def all_files(category: Optional[str] = MUSIC) -> list[FileInfo]:
    """Dateien einer Art (Standard: Musik), neueste zuerst; None = alle."""
    if category is None:
        return [_info(r) for r in await db.fetch_all("SELECT * FROM music_files ORDER BY added_at DESC, path")]
    return [_info(r) for r in await db.fetch_all(
        "SELECT * FROM music_files WHERE COALESCE(category, ?) = ? ORDER BY added_at DESC, path", (MUSIC, category))]


async def get(item_id: str) -> Optional[FileInfo]:
    row = await db.fetch_one("SELECT * FROM music_files WHERE id = ?", (item_id,))
    return _info(row) if row else None


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
        data = _embedded_picture(source) if row["cover"] == "embedded" else (root() / row["cover"]).read_bytes()
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
            "last_scan": dict(row) if row else None}

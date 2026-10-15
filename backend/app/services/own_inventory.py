"""
TubeVault – Eigene Videos: Dateien auf der Platte

Alles, was die Sammlung selbst anfasst: Videodateien suchen, ihre Angaben
lesen (NFO, Dateiname, ffprobe), Vorschaubild und Begleitdateien finden.
Die Funktionen sind synchron und laufen im eigenen Strang
(asyncio.to_thread) - eine langsame oder hängende Platte hält so nie den
Server auf.

Pfade sind relativ zum Sammlungsordner (SCAN_DIR). Der oberste Ordner einer
Datei gilt als Hinweis auf den Kanal (Sammlungen sind meist nach Kanälen
geordnet, z.B. "ARTE/Titel/Titel.mp4").
"""
import json
import logging
import os
import re
import subprocess
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v", ".flv", ".wmv", ".ts"}
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
# Vorschaubild neben dem Video: "<Name>-poster.jpg" (Mediathek-Programme), "<Name>.jpg"
THUMBNAIL_SUFFIXES = ("-poster", "", "-thumb", "-fanart")
# Bild eines Ordners, in dem nur dieses eine Video liegt
FOLDER_IMAGES = ("poster", "folder", "cover", "thumb")
FFPROBE_TIMEOUT_S = 60

# Kennung der Quelle im Dateinamen. Eckige Klammern sind eindeutig (übliche
# Ablage von Download-Programmen); die anderen Formen treffen auch normale
# Wörter mit 11 Zeichen und gelten nur, wenn die Kennung bekannt ist.
_SOURCE_ID = r"([A-Za-z0-9_-]{11})"
_STRONG_ID = re.compile(rf"\[{_SOURCE_ID}\]")
_WEAK_IDS = (re.compile(rf"\({_SOURCE_ID}\)"), re.compile(rf"-{_SOURCE_ID}\.f\d+$"),
             re.compile(rf"[-_]{_SOURCE_ID}$"), re.compile(rf"^{_SOURCE_ID}$"))
# Angehängte Angaben, die nicht zum Titel gehören
_QUALITY_TAG = re.compile(r"\s*\((?:\d{3,4}p|\d+x\d+)[^)]*\)\s*$", re.IGNORECASE)
_BRACKET_ID = re.compile(rf"\s*\[{_SOURCE_ID}\]\s*$")


@dataclass
class ListedFile:
    rel_path: str
    size: int
    mtime: float


@dataclass
class ListingProgress:
    """Zwischenstand der Suche; der Suchstrang schreibt, der Server liest."""
    found: int = 0
    cancelled: bool = False


@dataclass
class FileFacts:
    """Was sich aus der Datei selbst ablesen lässt."""
    title: str
    size: int
    channel_hint: Optional[str] = None
    duration: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    source_id: Optional[str] = None
    source_id_certain: bool = False      # eindeutig ([Kennung]) oder nur möglich
    thumbnail: Optional[str] = None      # relativer Pfad des Vorschaubilds
    extra: dict = field(default_factory=dict)


def is_video(name: str) -> bool:
    return Path(name).suffix.lower() in VIDEO_EXTENSIONS


def list_media(root: Path, scope: str, progress: ListingProgress) -> Optional[list[ListedFile]]:
    """Alle Videodateien unter root/scope; None, wenn der Ordner fehlt
    (Platte nicht eingehängt). Versteckte Dateien und Ordner bleiben außen vor."""
    base = root / scope if scope else root
    if not base.is_dir():
        return None
    found: list[ListedFile] = []
    pending = [base]
    while pending and not progress.cancelled:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.name.startswith("."):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False) and is_video(entry.name):
                        stat = entry.stat(follow_symlinks=False)
                        found.append(ListedFile(os.path.relpath(entry.path, root), stat.st_size, stat.st_mtime))
                        progress.found += 1
        except OSError as e:
            logger.warning(f"[EIGENE] Ordner nicht lesbar: {directory}: {e}")
    return found


def channel_hint(rel_path: str) -> Optional[str]:
    """Oberster Ordner der Datei, wenn sie in einem Ordner liegt."""
    parts = Path(rel_path).parts
    return parts[0] if len(parts) > 1 else None


def readable_title(stem: str) -> str:
    """Titel aus dem Dateinamen. Download-Programme ersetzen Zeichen, die im
    Dateinamen nicht erlaubt sind, durch "_" - so weit erkennbar zurück."""
    title = _BRACKET_ID.sub("", _QUALITY_TAG.sub("", stem)).strip()
    title = title.replace(" _ ", " | ").replace("_ ", ": ")
    if title.endswith("_"):
        title = title[:-1] + "?"
    return title.strip() or stem


def source_id_of(name: str) -> tuple[Optional[str], bool]:
    """(Kennung, eindeutig) aus dem Dateinamen."""
    stem = Path(name).stem
    match = _STRONG_ID.search(stem)
    if match:
        return match.group(1), True
    for pattern in _WEAK_IDS:
        match = pattern.search(stem)
        # Eine mögliche Kennung enthält Ziffern oder Sonderzeichen; ein
        # Wort wie "Programming" ist keine
        if match and re.search(r"[0-9_-]", match.group(1)):
            return match.group(1), False
    return None, False


def _read_nfo(video: Path) -> dict:
    """Angaben aus "<Name>.nfo" (XML der Mediathek-Programme)."""
    nfo = video.with_name(video.stem + ".nfo")
    if not nfo.is_file():
        return {}
    try:
        text = nfo.read_text(encoding="utf-8-sig", errors="replace")
        root = ElementTree.fromstring(text)
    except (OSError, ElementTree.ParseError):
        return {}

    def number(tag: str) -> Optional[int]:
        node = root.find(f".//{tag}")
        try:
            return int(float(node.text)) if node is not None and node.text else None
        except ValueError:
            return None

    title = (root.findtext("title") or "").strip()
    studio = (root.findtext("studio") or root.findtext("showtitle") or "").strip()
    unique = next((u.text for u in root.findall("uniqueid")
                   if (u.get("type") or "").lower() == "youtube" and u.text), None)
    return {"title": title or None, "channel": studio or None, "source_id": unique,
            "duration": number("durationinseconds"), "width": number("width"), "height": number("height")}


def _ffprobe(video: Path) -> dict:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "format=duration:stream=width,height", "-of", "json", str(video)],
            capture_output=True, text=True, timeout=FFPROBE_TIMEOUT_S)
        data = json.loads(result.stdout or "{}")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        logger.info(f"[EIGENE] ffprobe ohne Ergebnis für {video.name}: {e}")
        return {}
    stream = (data.get("streams") or [{}])[0]
    duration = (data.get("format") or {}).get("duration")
    return {"duration": int(float(duration)) if duration else None,
            "width": stream.get("width"), "height": stream.get("height")}


def find_thumbnail(root: Path, rel_path: str) -> Optional[str]:
    video = root / rel_path
    try:
        names = set(os.listdir(video.parent))
    except OSError:
        return None
    for suffix in THUMBNAIL_SUFFIXES:
        for ext in IMAGE_EXTENSIONS:
            if video.stem + suffix + ext in names:
                return str(Path(rel_path).with_name(video.stem + suffix + ext))
    if sum(1 for n in names if is_video(n)) == 1:
        for base in FOLDER_IMAGES:
            for ext in IMAGE_EXTENSIONS:
                if base + ext in names:
                    return str(Path(rel_path).with_name(base + ext))
    return None


def probe(root: Path, rel_path: str) -> Optional[FileFacts]:
    """Angaben zu einer Datei; None, wenn sie nicht mehr da ist."""
    video = root / rel_path
    try:
        size = video.stat().st_size
    except OSError:
        return None
    nfo = _read_nfo(video)
    measured = {} if nfo.get("duration") else _ffprobe(video)
    source_id, certain = source_id_of(video.name)
    if nfo.get("source_id"):
        source_id, certain = nfo["source_id"], True
    return FileFacts(
        title=nfo.get("title") or readable_title(video.stem),
        size=size,
        channel_hint=nfo.get("channel") or channel_hint(rel_path),
        duration=nfo.get("duration") or measured.get("duration"),
        width=nfo.get("width") or measured.get("width"),
        height=nfo.get("height") or measured.get("height"),
        source_id=source_id, source_id_certain=certain,
        thumbnail=find_thumbnail(root, rel_path))


def companions(root: Path, rel_path: str) -> list[Path]:
    """Begleitdateien eines Videos (NFO, Bilder, Untertitel ...), die zu
    keinem anderen Video im selben Ordner gehören."""
    video = root / rel_path
    try:
        names = os.listdir(video.parent)
    except OSError:
        return []
    # das Video selbst zählt mit, auch wenn es schon verschoben ist
    stems = sorted({Path(n).stem for n in names if is_video(n)} | {video.stem}, key=len, reverse=True)

    def belongs_to(name: str, stem: str) -> bool:
        if not name.startswith(stem) or is_video(name):
            return False
        rest = name[len(stem):]
        return rest.startswith(".") or any(rest.startswith(s + ".") for s in THUMBNAIL_SUFFIXES if s)

    own = []
    for name in names:
        owner = next((stem for stem in stems if belongs_to(name, stem)), None)
        if owner == video.stem:
            own.append(video.parent / name)
    return own


def remove_with_companions(root: Path, rel_path: str, scope_root: Path) -> list[str]:
    """Video samt Begleitdateien löschen; ein dadurch leerer Ordner geht mit
    (nie der eingelesene Ordner selbst). Liefert die gelöschten Namen."""
    video = root / rel_path
    removed = []
    for path in [video, *companions(root, rel_path)]:
        try:
            path.unlink()
            removed.append(path.name)
        except FileNotFoundError:
            pass
    folder = video.parent
    try:
        if folder.resolve() != scope_root.resolve() and root.resolve() in folder.resolve().parents \
                and not any(folder.iterdir()):
            folder.rmdir()
    except OSError:
        pass
    return removed

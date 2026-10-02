"""
TubeVault – Zusätzliche Tonspuren v1.0.0

Ein Video hat seine Original-Tonspur in der Videodatei. Weitere Tonspuren
(z.B. eine deutsche Nachvertonung) liegen als eigene Audiodateien daneben und
werden in der Wiedergabe umgeschaltet - das Video wird nicht ein zweites Mal
gespeichert.

Ablage:  AUDIO_DIR/<video_id>/tracks/<sprache>.<endung>
Je Video und Sprache gibt es höchstens eine zusätzliche Tonspur; eine neue
ersetzt die alte.
"""
import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from app import config
from app.database import db

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS audio_tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    language TEXT NOT NULL,
    label TEXT,
    origin TEXT NOT NULL DEFAULT 'dub',
    voice TEXT,
    file_path TEXT NOT NULL,
    file_size INTEGER,
    duration REAL,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(video_id, language)
);
CREATE INDEX IF NOT EXISTS idx_audio_tracks_video ON audio_tracks(video_id);
"""

ALLOWED_SUFFIXES = (".m4a", ".mp3", ".ogg", ".opus", ".wav", ".aac", ".flac")
_MIME = {".m4a": "audio/mp4", ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".opus": "audio/ogg",
         ".wav": "audio/wav", ".aac": "audio/aac", ".flac": "audio/flac"}
LANGUAGE_NAMES = {"de": "Deutsch", "en": "Englisch", "fr": "Französisch", "es": "Spanisch",
                  "it": "Italienisch", "nl": "Niederländisch", "pl": "Polnisch", "ja": "Japanisch"}


class AudioTrack(BaseModel):
    id: int
    video_id: str
    language: str
    label: str
    origin: str
    voice: Optional[str] = None
    file_size: Optional[int] = None
    duration: Optional[float] = None
    created_at: Optional[str] = None


def language_name(code: str | None) -> str:
    return LANGUAGE_NAMES.get((code or "").lower(), (code or "unbekannt").upper())


def mime_for(path: Path) -> str:
    return _MIME.get(path.suffix.lower(), "application/octet-stream")


def _tracks_dir(video_id: str) -> Path:
    return config.AUDIO_DIR / video_id / "tracks"


def _to_model(row) -> AudioTrack:
    data = dict(row)
    data["label"] = data.get("label") or language_name(data["language"])
    return AudioTrack(**{k: data.get(k) for k in AudioTrack.model_fields})


async def list_tracks(video_id: str) -> list[AudioTrack]:
    rows = await db.fetch_all(
        "SELECT * FROM audio_tracks WHERE video_id = ? ORDER BY language", (video_id,))
    return [_to_model(r) for r in rows]


async def track_file(video_id: str, track_id: int) -> Path | None:
    row = await db.fetch_one(
        "SELECT file_path FROM audio_tracks WHERE id = ? AND video_id = ?", (track_id, video_id))
    if not row:
        return None
    path = Path(row["file_path"])
    return path if path.is_file() else None


async def _probe_duration(path: Path) -> float:
    """Dauer per ffprobe; wirft ValueError, wenn die Datei keine Tonspur enthält."""
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise ValueError(f"Datei ist kein lesbares Audio: {err.decode()[-160:].strip()}")
    probe = json.loads(out.decode() or "{}")
    if not any(s.get("codec_type") == "audio" for s in probe.get("streams", [])):
        raise ValueError("Datei enthält keine Tonspur")
    return float(probe.get("format", {}).get("duration") or 0)


async def store_track(video_id: str, language: str, source: Path, *, suffix: str,
                      origin: str = "dub", voice: str | None = None,
                      label: str | None = None) -> AudioTrack:
    """Audiodatei als Tonspur des Videos übernehmen (ersetzt eine vorhandene
    Spur derselben Sprache). source wird verschoben."""
    language = language.strip().lower()
    suffix = suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError(f"Dateiart {suffix or '(ohne)'} wird nicht als Tonspur angenommen")
    if not await db.fetch_one("SELECT id FROM videos WHERE id = ?", (video_id,)):
        raise ValueError("Video nicht gefunden")

    duration = await _probe_duration(source)
    if duration <= 0:
        raise ValueError("Tonspur ist leer")

    target_dir = _tracks_dir(video_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{language}{suffix}"
    old = await db.fetch_one(
        "SELECT file_path FROM audio_tracks WHERE video_id = ? AND language = ?", (video_id, language))
    shutil.move(str(source), str(target))
    if old and old["file_path"] != str(target):
        Path(old["file_path"]).unlink(missing_ok=True)

    await db.execute(
        """INSERT INTO audio_tracks (video_id, language, label, origin, voice, file_path, file_size, duration)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(video_id, language) DO UPDATE SET
               label = excluded.label, origin = excluded.origin, voice = excluded.voice,
               file_path = excluded.file_path, file_size = excluded.file_size,
               duration = excluded.duration, created_at = datetime('now', 'localtime')""",
        (video_id, language, label, origin, voice, str(target), os.path.getsize(target), duration))
    row = await db.fetch_one(
        "SELECT * FROM audio_tracks WHERE video_id = ? AND language = ?", (video_id, language))
    logger.info(f"[TONSPUR] {video_id}: Spur '{language}' gespeichert ({duration:.0f}s)")
    return _to_model(row)


async def delete_track(video_id: str, track_id: int) -> bool:
    row = await db.fetch_one(
        "SELECT file_path FROM audio_tracks WHERE id = ? AND video_id = ?", (track_id, video_id))
    if not row:
        return False
    Path(row["file_path"]).unlink(missing_ok=True)
    await db.execute("DELETE FROM audio_tracks WHERE id = ?", (track_id,))
    return True

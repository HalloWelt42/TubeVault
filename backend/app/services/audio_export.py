"""
TubeVault – Tonspuren: messen und ausgeben

- Messen: Format, Bitrate, Abtastrate und Kanäle der Tonspur einer Datei
  (ffprobe, einmal je Datei, gemerkt in audio_info). Der Musikspieler zeigt
  das an.
- Ausgeben: die Tonspur eines Videos als eigene Datei. "original" kopiert
  die Tonspur ohne Neukodierung (keine Qualitätsverluste); die anderen
  Formate kodieren neu (ad_free_export.AUDIO_CODECS). Werbestellen werden
  wie bei jedem Download herausgeschnitten - dann muss auch "original" neu
  kodiert werden, in derselben Art bei hoher Bitrate.
- ZIP: mehrere Tonspuren als ein Archiv (Wiedergabelisten, Interpreten ...).
- Musikdateien der eigenen Sammlung (music_files) gehen genauso: "original"
  kopiert die Datei unverändert, andere Formate kodieren neu.

Alles mit ffmpeg/ffprobe als eigener Prozess, die Dateiarbeit im eigenen
Strang - der Server bleibt währenddessen frei.
"""
import asyncio
import json
import re
import shutil
import zipfile
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from app.database import db
from app.services import ad_free_export, ad_segments, music_files

ORIGINAL = "original"
FORMATS = (ORIGINAL, *ad_free_export.AUDIO_CODECS)
MAX_ZIP_TRACKS = 500

# Original-Tonspur: Dateiendung je Format der Quelle
_CONTAINER = {"aac": "m4a", "opus": "opus", "mp3": "mp3", "vorbis": "ogg", "flac": "flac"}
# Mit Werbeschnitt muss neu kodiert werden: dieselbe Art, hohe Bitrate
_REENCODE = {"aac": ["-c:a", "aac", "-b:a", "256k"], "opus": ["-c:a", "libopus", "-b:a", "192k"],
             "mp3": ["-c:a", "libmp3lame", "-q:a", "0"], "vorbis": ["-c:a", "libvorbis", "-q:a", "8"],
             "flac": ["-c:a", "flac"]}
MIME = {"m4a": "audio/mp4", "opus": "audio/ogg", "mp3": "audio/mpeg", "ogg": "audio/ogg", "flac": "audio/flac"}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS audio_info (
    video_id TEXT PRIMARY KEY,
    file_size INTEGER,                -- gemessen an dieser Dateigröße; ändert sie sich, wird neu gemessen
    codec TEXT,
    bitrate INTEGER,                  -- Bit je Sekunde
    sample_rate INTEGER,
    channels INTEGER,
    measured_at TEXT DEFAULT (datetime('now'))
);
"""


class AudioInfo(BaseModel):
    codec: Optional[str] = None
    bitrate: Optional[int] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    bit_depth: Optional[int] = None


async def install_schema(connection) -> None:
    await connection.executescript(SCHEMA_SQL)
    await connection.commit()


async def _probe(path: Path) -> AudioInfo:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,bit_rate,sample_rate,channels:format=bit_rate", "-of", "json", str(path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, _ = await proc.communicate()
    data = json.loads(out or b"{}")
    stream = (data.get("streams") or [{}])[0]
    number = lambda v: int(float(v)) if v not in (None, "", "N/A") else None   # noqa: E731
    return AudioInfo(codec=stream.get("codec_name"), bitrate=number(stream.get("bit_rate")),
                     sample_rate=number(stream.get("sample_rate")), channels=stream.get("channels"))


async def info(video_id: str) -> Optional[AudioInfo]:
    """Angaben zur Tonspur eines geladenen Videos (gemerkt je Dateigröße) oder
    einer Musikdatei (aus ihren Tags)."""
    if music_files.is_file_id(video_id):
        f = await music_files.get(video_id)
        return AudioInfo(codec=(f.codec or "").lower() or None, bitrate=f.bitrate, sample_rate=f.sample_rate,
                         channels=f.channels, bit_depth=f.bit_depth) if f else None
    video = await db.fetch_one("SELECT file_path, file_size FROM videos WHERE id = ? AND status = 'ready'", (video_id,))
    if not video or not video["file_path"]:
        return None
    cached = await db.fetch_one("SELECT * FROM audio_info WHERE video_id = ?", (video_id,))
    if cached and cached["file_size"] == video["file_size"]:
        return AudioInfo(codec=cached["codec"], bitrate=cached["bitrate"],
                         sample_rate=cached["sample_rate"], channels=cached["channels"])
    path = Path(video["file_path"])
    if not await asyncio.to_thread(path.is_file):
        return None
    # Manche Behälter (Opus in WebM/MKV) nennen keine Bitrate der Spur; dann
    # bleibt sie leer - eine Schätzung aus der Dateigröße enthielte das Bild
    measured = await _probe(path)
    await db.execute(
        """INSERT OR REPLACE INTO audio_info (video_id, file_size, codec, bitrate, sample_rate, channels)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (video_id, video["file_size"], measured.codec, measured.bitrate, measured.sample_rate, measured.channels))
    return measured


def safe_name(text: str) -> str:
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", text).strip(" .")[:120] or "Titel"


async def _export_file(file_id: str, fmt: str, folder: Path, name: Optional[str]) -> Path:
    src = await music_files.path_of(file_id)
    if not src:
        raise LookupError("Datei nicht vorhanden")
    f = await music_files.get(file_id)
    label = safe_name(name or (f"{f.artist} - {f.title}" if f.artist else f.title))
    if fmt == ORIGINAL:
        out = folder / f"{label}{src.suffix.lower()}"
        await asyncio.to_thread(shutil.copy2, src, out)
        return out
    out = folder / f"{label}.{fmt}"
    await ad_free_export.run_tool("ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn", "-map", "0:a:0",
                                  *ad_free_export.AUDIO_CODECS[fmt], str(out))
    return out


async def export(video_id: str, fmt: str, folder: Path, name: Optional[str] = None) -> Path:
    """Tonspur eines Videos (ohne Werbestellen) oder eine Musikdatei als Datei in folder."""
    if fmt not in FORMATS:
        raise ValueError("Unbekanntes Format")
    if music_files.is_file_id(video_id):
        return await _export_file(video_id, fmt, folder, name)
    video = await db.fetch_one("SELECT title, file_path FROM videos WHERE id = ? AND status = 'ready'", (video_id,))
    if not video or not video["file_path"] or not Path(video["file_path"]).is_file():
        raise LookupError("Datei nicht vorhanden")
    src = Path(video["file_path"])
    codec = (await info(video_id) or AudioInfo()).codec or "aac"
    ext = _CONTAINER.get(codec, "m4a") if fmt == ORIGINAL else fmt
    out = folder / f"{safe_name(name or video['title'] or video_id)}.{ext}"
    await ad_segments.refresh_if_due(video_id)
    ranges = await ad_segments.skip_ranges(video_id)
    if ranges:
        keep = ad_segments.keep_ranges(ranges, await ad_free_export.duration(src))
        select = "+".join(f"between(t,{start:.3f},{end:.3f})" for start, end in keep)
        encode = _REENCODE.get(codec, _REENCODE["aac"]) if fmt == ORIGINAL else ad_free_export.AUDIO_CODECS[fmt]
        await ad_free_export.run_tool("ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn",
                                  "-af", f"aselect='{select}',asetpts=N/SR/TB", *encode, str(out))
    else:
        encode = ["-c:a", "copy"] if fmt == ORIGINAL else ad_free_export.AUDIO_CODECS[fmt]
        await ad_free_export.run_tool("ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn", "-map", "0:a:0",
                                  *encode, str(out))
    return out


async def zip_tracks(tracks: list[tuple[str, str]], fmt: str, folder: Path, title: str) -> Path:
    """Mehrere Tonspuren als ZIP. tracks: (video_id, Dateiname ohne Endung).
    Nicht ausgebbare Titel werden übersprungen."""
    files = []
    for number, (video_id, name) in enumerate(tracks[:MAX_ZIP_TRACKS], start=1):
        try:
            files.append(await export(video_id, fmt, folder, f"{number:03d} {name}"))
        except (LookupError, ValueError, ad_free_export.ExportError):
            continue
    if not files:
        raise LookupError("Keine Tonspur ausgebbar")
    archive = folder / f"{safe_name(title)}.zip"

    def pack() -> None:
        # Ton ist schon verdichtet: speichern statt nochmals packen
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as zf:
            for path in files:
                zf.write(path, arcname=path.name)
                path.unlink()
    await asyncio.to_thread(pack)
    return archive

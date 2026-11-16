"""
TubeVault - Abspielbare Fassung je Gerät (HELF-242)

Geladene Videos liegen so vor, wie die Quelle sie lieferte: H.264, AV1 oder
VP9, in mp4, webm oder mkv. Nicht jedes Gerät spielt alles - das iPhone
spielt keinen mkv-Container und AV1 nur mit eigenem Decoder. Ob ein Gerät
eine Datei abspielt, weiß nur das Gerät selbst; der Server liefert ihm dafür
die Angaben der Datei und, wenn nötig, eine zweite, überall abspielbare
Fassung.

- describe(video_id): Angaben der Datei (ffprobe, in media_info gemerkt und
  neu gemessen, sobald sich Größe oder Zeitstempel ändern) samt Codec-
  Kennungen, die der Player mit canPlayType prüft.
- Kompatible Fassung: COMPATIBLE_NAME im Ordner des Videos, H.264 und AAC
  in mp4. Ist das Video schon H.264, wird nur umgepackt (Sekunden); sonst
  wandelt ffmpeg um (auf dem Pi 5 bei 1080p etwa in Echtzeit). Das Original
  bleibt unberührt; wird das Video gelöscht, geht die Fassung mit dem Ordner.
- Aufträge (jobs.type JOB_TYPE) tragen die Liste ihrer Videos und die Art:
  "bei_bedarf" wandelt notfalls um, "umpacken" packt nur H.264 um und lässt
  den Rest liegen. worker() arbeitet sie nacheinander ab, nie zwei ffmpeg
  gleichzeitig.
"""
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

from app.database import db
from app.services.archive_service import archive_service
from app.services.job_service import job_service

logger = logging.getLogger(__name__)

JOB_TYPE = "compatible"
COMPATIBLE_NAME = "kompatibel.mp4"
_PART_NAME = "kompatibel.part.mp4"

# Umwandeln: so viel Qualität, wie das Telefon zeigt, ohne den Pi tagelang zu
# belegen (gemessen 16.11.2026: AV1 1080p nach H.264 1080p mit veryfast 0,87-
# fach Echtzeit, 720p 1,2-fach). Ein Kern bleibt für Downloads und Oberfläche.
MAX_HEIGHT = 1080
X264_PRESET = "veryfast"
X264_CRF = "23"
FFMPEG_THREADS = "3"
AUDIO_BITRATE = "160k"
NICENESS = "15"

IDLE_S = 300
START_DELAY_S = 60

Art = Literal["bei_bedarf", "umpacken"]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS media_info (
    video_id TEXT PRIMARY KEY,
    file_size INTEGER,
    file_mtime REAL,
    container TEXT,
    video_codec TEXT,
    video_tag TEXT,
    audio_codec TEXT,
    audio_tag TEXT,
    width INTEGER,
    height INTEGER,
    duration REAL,
    probed_at TEXT DEFAULT (datetime('now'))
);
"""


async def install_schema(connection) -> None:
    await connection.executescript(SCHEMA_SQL)
    await connection.commit()


# ─── Angaben der Datei ────────────────────────────────────────────────

class MediaInfo(BaseModel):
    container: str                    # mp4 | webm | mkv | ...
    video_codec: Optional[str] = None # h264 | av1 | vp9 | hevc | ...
    video_tag: Optional[str] = None   # Kennung für canPlayType, z.B. avc1.640028
    audio_codec: Optional[str] = None
    audio_tag: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None

    @property
    def mime(self) -> str:
        return {"mp4": "video/mp4", "webm": "video/webm", "mkv": "video/x-matroska"}.get(
            self.container, f"video/{self.container}")

    @property
    def codecs(self) -> str:
        return ", ".join(tag for tag in (self.video_tag, self.audio_tag) if tag)

    @property
    def label(self) -> str:
        names = {"h264": "H.264", "av1": "AV1", "vp9": "VP9", "hevc": "HEVC"}
        parts = [names.get(self.video_codec or "", (self.video_codec or "ohne Bild").upper())]
        if self.height:
            parts.append(f"{self.height}p")
        parts.append(self.container)
        return ", ".join(parts)


_AVC_PROFILES = {"baseline": "42", "constrained baseline": "42", "main": "4d",
                 "extended": "58", "high": "64", "high 10": "6e"}


def _avc_tag(stream: dict) -> str:
    profile = (stream.get("profile") or "").lower()
    level = stream.get("level")
    constraint = "e0" if profile == "constrained baseline" else "00"
    level_hex = f"{level:02x}" if isinstance(level, int) and level > 0 else "28"
    return f"avc1.{_AVC_PROFILES.get(profile, '64')}{constraint}{level_hex}"


def _bit_depth(stream: dict) -> int:
    return 10 if "10" in (stream.get("pix_fmt") or "") else 8


def _av1_tag(stream: dict) -> str:
    height = stream.get("height") or 1080
    level = 4 if height <= 480 else 5 if height <= 720 else 8 if height <= 1080 else 12
    return f"av01.0.{level:02d}M.{_bit_depth(stream):02d}"


def _vp9_tag(stream: dict) -> str:
    height = stream.get("height") or 1080
    level = 30 if height <= 480 else 31 if height <= 720 else 40 if height <= 1080 else 50
    profile = "02" if _bit_depth(stream) == 10 else "00"
    return f"vp09.{profile}.{level}.{_bit_depth(stream):02d}"


_VIDEO_TAGS = {"h264": _avc_tag, "av1": _av1_tag, "vp9": _vp9_tag,
               "hevc": lambda s: "hvc1.1.6.L120.B0"}
_AUDIO_TAGS = {"aac": "mp4a.40.2", "opus": "opus", "mp3": "mp3", "vorbis": "vorbis", "flac": "flac"}


def _container(path: Path, format_name: str) -> str:
    if "mp4" in format_name or "mov" in format_name:
        return "mp4"
    suffix = path.suffix.lower().lstrip(".")
    return suffix if suffix in ("webm", "mkv") else (format_name.split(",")[0] or suffix)


async def _ffprobe(path: Path) -> MediaInfo:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-show_entries",
        "format=format_name,duration:stream=codec_type,codec_name,profile,level,pix_fmt,width,height",
        "-of", "json", str(path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe: {err.decode(errors='replace').strip()[:200]}")
    data = json.loads(out or b"{}")
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"
                  and s.get("codec_name") not in ("mjpeg", "png")), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = data.get("format", {})
    video_codec = video.get("codec_name") if video else None
    audio_codec = audio.get("codec_name") if audio else None
    tag = _VIDEO_TAGS.get(video_codec or "")
    try:
        duration = float(fmt.get("duration")) if fmt.get("duration") else None
    except ValueError:
        duration = None
    return MediaInfo(
        container=_container(path, fmt.get("format_name", "")),
        video_codec=video_codec, video_tag=tag(video) if tag and video else video_codec,
        audio_codec=audio_codec, audio_tag=_AUDIO_TAGS.get(audio_codec or "", audio_codec),
        width=video.get("width") if video else None, height=video.get("height") if video else None,
        duration=duration)


async def _original_path(video_id: str) -> Optional[Path]:
    resolved = await archive_service.resolve_video_path(video_id)
    return Path(resolved["path"]) if resolved.get("available") else None


async def probe(video_id: str, path: Path) -> MediaInfo:
    """Angaben der Datei, gemerkt bis sich Größe oder Zeitstempel ändern."""
    stat = path.stat()
    row = await db.fetch_one("SELECT * FROM media_info WHERE video_id = ?", (video_id,))
    if row and row["file_size"] == stat.st_size and row["file_mtime"] == stat.st_mtime:
        return MediaInfo(**{k: row[k] for k in MediaInfo.model_fields})
    info = await _ffprobe(path)
    await db.execute(
        """INSERT OR REPLACE INTO media_info (video_id, file_size, file_mtime, container, video_codec,
               video_tag, audio_codec, audio_tag, width, height, duration, probed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
        (video_id, stat.st_size, stat.st_mtime, info.container, info.video_codec, info.video_tag,
         info.audio_codec, info.audio_tag, info.width, info.height, info.duration))
    return info


def compatible_path(original: Path) -> Path:
    return original.parent / COMPATIBLE_NAME


def compatible_ready(original: Path) -> bool:
    """Fassung da und nicht älter als das Original."""
    target = compatible_path(original)
    return target.is_file() and target.stat().st_mtime >= original.stat().st_mtime


# ─── Antwort an den Player ────────────────────────────────────────────

class Variant(BaseModel):
    url: str
    mime: str
    codecs: str
    label: str


class PendingJob(BaseModel):
    id: int
    status: str
    progress: float


class PlaybackMedia(BaseModel):
    original: Variant
    compatible: Optional[Variant] = None   # fertige kompatible Fassung
    job: Optional[PendingJob] = None       # Umwandlung wartet oder läuft
    compatible_way: Literal["umpacken", "umwandeln"]   # was ffmpeg dafür tun müsste


class Unavailable(Exception):
    """Videodatei fehlt oder liegt auf einem nicht verbundenen Archiv."""


async def describe(video_id: str) -> PlaybackMedia:
    path = await _original_path(video_id)
    if not path:
        raise Unavailable(video_id)
    info = await probe(video_id, path)
    original = Variant(url=f"/api/player/{video_id}", mime=info.mime, codecs=info.codecs, label=info.label)
    compatible = None
    if compatible_ready(path):
        compatible = Variant(url=f"/api/player/{video_id}/compatible", mime="video/mp4",
                             codecs="avc1.640028, mp4a.40.2", label="H.264, mp4")
    return PlaybackMedia(original=original, compatible=compatible, job=await _pending_job(video_id),
                         compatible_way="umpacken" if info.video_codec == "h264" else "umwandeln")


async def _pending_job(video_id: str) -> Optional[PendingJob]:
    row = await db.fetch_one(
        f"""SELECT j.id, j.status, j.progress FROM jobs j, json_each(j.metadata, '$.video_ids') v
            WHERE j.type = '{JOB_TYPE}' AND j.status IN ('queued', 'active') AND v.value = ?
            ORDER BY j.id LIMIT 1""", (video_id,))
    return PendingJob(id=row["id"], status=row["status"], progress=row["progress"] or 0) if row else None


async def compatible_file(video_id: str) -> Optional[Path]:
    path = await _original_path(video_id)
    return compatible_path(path) if path and compatible_ready(path) else None


# ─── Aufträge ─────────────────────────────────────────────────────────

_wake = asyncio.Event()


async def request(video_ids: list[str], art: Art, title: str) -> dict:
    """Auftrag anlegen; ein Video, das schon in einem offenen Auftrag steht,
    bekommt keinen zweiten."""
    if len(video_ids) == 1:
        pending = await _pending_job(video_ids[0])
        if pending:
            return await job_service.get(pending.id)
    job = await job_service.create(JOB_TYPE, title, "Wartet", metadata={"video_ids": video_ids, "art": art})
    _wake.set()
    return job


class Candidate(BaseModel):
    video_id: str
    size_bytes: int


async def repack_candidates() -> list[Candidate]:
    """Videos außerhalb des mp4-Containers ohne kompatible Fassung; ob H.264
    drin steckt, zeigt erst die Messung beim Abarbeiten."""
    rows = await db.fetch_all(
        """SELECT id, file_path, COALESCE(file_size, 0) AS size FROM videos WHERE status = 'ready'
           AND (lower(file_path) LIKE '%.mkv' OR lower(file_path) LIKE '%.webm')
           ORDER BY download_date DESC""")

    def without_compatible() -> list[Candidate]:
        return [Candidate(video_id=r["id"], size_bytes=r["size"]) for r in rows
                if not compatible_path(Path(r["file_path"])).exists()]

    return await asyncio.to_thread(without_compatible)


def videos_text(count: int) -> str:
    return "1 Video" if count == 1 else f"{count} Videos"


def _ffmpeg_args(source: Path, target: Path, info: MediaInfo) -> list[str]:
    audio = (["-c:a", "copy"] if info.audio_codec == "aac"
             else ["-c:a", "aac", "-b:a", AUDIO_BITRATE])
    if info.video_codec == "h264":
        video = ["-c:v", "copy"]
    else:
        video = ["-c:v", "libx264", "-preset", X264_PRESET, "-crf", X264_CRF,
                 "-pix_fmt", "yuv420p", "-vf", f"scale=-2:'min({MAX_HEIGHT},ih)'",
                 "-threads", FFMPEG_THREADS]
    return ["nice", "-n", NICENESS, "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source), "-map", "0:v:0", "-map", "0:a:0?", *video, *audio,
            "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(target)]


class Stopped(Exception):
    pass


async def _convert(job_id: int, source: Path, info: MediaInfo, report) -> None:
    target, part = compatible_path(source), source.parent / _PART_NAME
    proc = await asyncio.create_subprocess_exec(
        *_ffmpeg_args(source, part, info),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            if job_service.is_cancelled(job_id):
                proc.kill()
                raise Stopped()
            text = line.decode(errors="replace").strip()
            if text.startswith("out_time_us=") and info.duration:
                try:
                    await report(min(int(text.split("=", 1)[1]) / 1e6 / info.duration, 1.0))
                except ValueError:
                    pass
        err = (await proc.stderr.read()).decode(errors="replace").strip()
        if await proc.wait() != 0:
            raise RuntimeError(f"ffmpeg: {err[-300:] or 'Abbruch'}")
        os.replace(part, target)
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        part.unlink(missing_ok=True)


async def _title(video_id: str) -> str:
    return await db.fetch_val("SELECT title FROM videos WHERE id = ?", (video_id,)) or video_id


async def _run(job_id: int) -> str:
    job = await job_service.get(job_id)
    video_ids = job["metadata"].get("video_ids", [])
    art = job["metadata"].get("art", "bei_bedarf")
    counts = {"umgepackt": 0, "umgewandelt": 0, "vorhanden": 0, "braucht Umwandlung": 0, "fehlt": 0}
    total = max(len(video_ids), 1)
    for index, video_id in enumerate(video_ids):
        if job_service.is_cancelled(job_id):
            raise Stopped()
        source = await _original_path(video_id)
        if not source:
            counts["fehlt"] += 1
            continue
        if compatible_ready(source):
            counts["vorhanden"] += 1
            continue
        info = await probe(video_id, source)
        if info.video_codec != "h264" and art == "umpacken":
            counts["braucht Umwandlung"] += 1
            continue
        way = "Umpacken" if info.video_codec == "h264" else "Umwandeln"
        name = await _title(video_id)

        async def report(share: float, index=index, way=way, name=name):
            await job_service.progress(job_id, (index + share) / total,
                                       f"{way} {index + 1}/{total}: {name[:60]} ({share:.0%})")

        await report(0.0)
        await _convert(job_id, source, info, report)
        counts["umgepackt" if way == "Umpacken" else "umgewandelt"] += 1
    return ", ".join(f"{n} {label}" for label, n in counts.items() if n) or "nichts zu tun"


async def _next_job() -> Optional[int]:
    return await db.fetch_val(
        f"SELECT id FROM jobs WHERE type = '{JOB_TYPE}' AND status = 'queued' ORDER BY id LIMIT 1")


async def worker() -> None:
    """Aufträge nacheinander abarbeiten; ein neuer Auftrag weckt die Schleife,
    auch schon während der Startpause."""
    try:
        await asyncio.wait_for(_wake.wait(), START_DELAY_S)
    except asyncio.TimeoutError:
        pass
    while True:
        job_id = await _next_job()
        if not job_id:
            _wake.clear()
            try:
                await asyncio.wait_for(_wake.wait(), IDLE_S)
            except asyncio.TimeoutError:
                pass
            continue
        await job_service.start(job_id, exclusive=False)
        try:
            await job_service.complete(job_id, await _run(job_id))
        except Stopped:
            logger.info(f"[KOMPATIBEL] Auftrag #{job_id} abgebrochen")
        except Exception as e:
            logger.warning(f"[KOMPATIBEL] Auftrag #{job_id}: {e}")
            await job_service.fail(job_id, str(e)[:500])
        finally:
            job_service.clear_cancel(job_id)

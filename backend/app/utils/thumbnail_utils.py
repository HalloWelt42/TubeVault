"""
TubeVault -  Thumbnail Utilities
Zentrale Funktionen für YouTube-Thumbnail-Downloads und ffmpeg-Generierung.
© HalloWelt42 -  Private Nutzung
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# YouTube-Thumbnail Qualitätsstufen (beste zuerst)
YT_THUMB_QUALITIES = ["maxresdefault", "sddefault", "hqdefault", "mqdefault", "default"]
YT_THUMB_QUALITIES_FAST = ["hqdefault", "mqdefault", "default"]  # Für RSS/schnelle Lookups


async def download_yt_thumbnail(
    video_id: str,
    dest_dir: Path,
    filename: str = None,
    qualities: list[str] = None,
    overwrite: bool = False,
    min_size: int = 1000,
) -> Optional[Path]:
    """
    YouTube-Thumbnail herunterladen.

    Args:
        video_id: YouTube Video-ID (11 Zeichen)
        dest_dir: Zielverzeichnis
        filename: Dateiname (default: {video_id}.jpg)
        qualities: Qualitätsstufen (default: alle, beste zuerst)
        overwrite: Vorhandenes Thumbnail überschreiben
        min_size: Minimale Dateigröße in Bytes (gegen Placeholder-Bilder)

    Returns:
        Path zur gespeicherten Datei oder None
    """
    if not video_id or video_id.startswith("local_") or len(video_id) != 11:
        return None

    dest = dest_dir / (filename or f"{video_id}.jpg")
    if dest.exists() and not overwrite and dest.stat().st_size > min_size:
        return dest

    dest_dir.mkdir(parents=True, exist_ok=True)
    qualities = qualities or YT_THUMB_QUALITIES

    import httpx
    for quality in qualities:
        url = f"https://i.ytimg.com/vi/{video_id}/{quality}.jpg"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                if resp.status_code == 200 and len(resp.content) > min_size:
                    dest.write_bytes(resp.content)
                    logger.info(f"[THUMB] YT-Thumbnail geladen: {video_id} ({quality})")
                    return dest
        except Exception as e:
            logger.debug(f"[THUMB] {quality} fehlgeschlagen für {video_id}: {e}")
            continue

    logger.warning(f"[THUMB] Kein YT-Thumbnail verfügbar für {video_id}")
    return None


def generate_ffmpeg_thumbnail(
    video_path: str | Path,
    dest: Path,
    position: int = None,
    duration: int = None,
    width: int = 640,
    quality: int = 3,
) -> Optional[Path]:
    """
    Thumbnail per ffmpeg aus Videodatei generieren.

    Args:
        video_path: Pfad zur Videodatei
        dest: Zielpfad für das Thumbnail
        position: Seek-Position in Sekunden (default: 25% der Dauer)
        duration: Video-Dauer in Sekunden (für Position-Berechnung)
        width: Ausgabe-Breite (Höhe proportional)
        quality: JPEG-Qualität (1=best, 31=worst)

    Returns:
        Path zur gespeicherten Datei oder None
    """
    video_path = Path(video_path)
    if not video_path.exists():
        return None

    dest.parent.mkdir(parents=True, exist_ok=True)

    # Position bestimmen
    if position is None:
        if not duration:
            probe = ffprobe_duration(video_path)
            duration = probe or 60
        position = max(1, duration // 4)

    # Versuch 1: Gewünschte Position
    try:
        subprocess.run(
            ["ffmpeg", "-ss", str(position), "-i", str(video_path),
             "-vframes", "1", "-vf", f"scale={width}:-1",
             "-q:v", str(quality), str(dest), "-y"],
            capture_output=True, timeout=30)
        if dest.exists() and dest.stat().st_size > 0:
            return dest
    except Exception as e:
        logger.warning(f"[THUMB] ffmpeg Versuch 1 fehlgeschlagen: {e}")

    # Versuch 2: Sekunde 1 (Fallback für kurze Videos)
    try:
        subprocess.run(
            ["ffmpeg", "-ss", "1", "-i", str(video_path),
             "-vframes", "1", "-vf", f"scale={width}:-1",
             "-q:v", str(quality), str(dest), "-y"],
            capture_output=True, timeout=30)
        if dest.exists() and dest.stat().st_size > 0:
            return dest
    except Exception as e:
        logger.warning(f"[THUMB] ffmpeg Versuch 2 fehlgeschlagen: {e}")

    return None


def ffprobe_duration(video_path: Path) -> Optional[int]:
    """Video-Dauer per ffprobe ermitteln."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and r.stdout.strip():
            return int(float(r.stdout.strip()))
    except Exception:
        pass
    return None


def find_companion_thumbnail(src_path: Path, video_id: str, dest_dir: Path) -> Optional[Path]:
    """
    Companion-Thumbnail (.jpg/.png neben dem Video) suchen und kopieren.

    Returns:
        Path zur kopierten Datei oder None
    """
    import shutil
    base = src_path.with_suffix("")
    for ext in [".jpg", ".jpeg", ".png", ".webp"]:
        for suffix in ["", "-thumb", "-poster", "_thumb"]:
            candidate = Path(str(base) + suffix + ext)
            if candidate.exists() and candidate.stat().st_size > 500:
                dest = dest_dir / f"{video_id}.jpg"
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(candidate, dest)
                logger.info(f"[THUMB] Companion kopiert: {candidate.name}")
                return dest
    return None

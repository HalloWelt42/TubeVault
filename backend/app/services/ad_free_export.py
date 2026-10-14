"""
TubeVault – Downloads ohne Werbung

Lädt jemand ein Video oder seine Tonspur herunter, entsteht die Datei für
genau diesen einen Download ohne die Werbestellen (ad_segments) und wird
danach wieder gelöscht. Die Datei im Archiv bleibt vollständig; hat ein
Video keine Werbestellen, wird ohne ffmpeg das Original ausgeliefert.

Video: ohne Neukodierung (auf dem Pi sonst stundenlang). Ein Schnitt ohne
Neukodierung kann nur an einem Schlüsselbild beginnen; jedes verbleibende
Stück beginnt deshalb am ersten Schlüsselbild NACH dem Ende der Werbung -
lieber ein, zwei Sekunden Inhalt verlieren als Werbung behalten.

Ton: wird ohnehin neu kodiert, darum sekundengenau geschnitten.
"""
import asyncio
import shutil
import uuid
from pathlib import Path

from app.config import TEMP_DIR

AUDIO_CODECS = {"mp3": ["-c:a", "libmp3lame", "-q:a", "2"], "m4a": ["-c:a", "aac", "-b:a", "192k"],
                "flac": ["-c:a", "flac"], "ogg": ["-c:a", "libvorbis", "-q:a", "6"]}


class ExportError(RuntimeError):
    pass


def work_dir() -> Path:
    """Eigener Arbeitsordner je Download; der Aufrufer räumt ihn danach weg."""
    folder = TEMP_DIR / f"ohne_werbung_{uuid.uuid4().hex}"
    folder.mkdir(parents=True)
    return folder


def remove(folder: Path) -> None:
    shutil.rmtree(folder, ignore_errors=True)


async def _run(*cmd: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise ExportError(f"{cmd[0]}: {err.decode(errors='replace').strip()[-300:]}")
    return out.decode(errors="replace")


async def duration(src: Path) -> float:
    out = await _run("ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=nw=1:nk=1", str(src))
    return float(out.strip())


async def keyframes(src: Path) -> list[float]:
    """Zeitpunkte der Schlüsselbilder (nur aus den Paketen gelesen, ohne Dekodieren)."""
    out = await _run("ffprobe", "-v", "error", "-select_streams", "v:0",
                     "-show_entries", "packet=pts_time,flags", "-of", "csv=p=0", str(src))
    times = []
    for line in out.splitlines():
        parts = line.split(",")
        if len(parts) >= 2 and "K" in parts[1] and parts[0] not in ("", "N/A"):
            times.append(float(parts[0]))
    return sorted(times)


def snap_to_keyframes(keep: list[tuple[float, float]], frames: list[float]) -> list[tuple[float, float]]:
    """Jedes Stück beginnt am ersten Schlüsselbild ab seinem Anfang (der Anfang
    des Videos bleibt, wie er ist); Stücke, die dabei verschwinden, entfallen."""
    snapped = []
    for start, end in keep:
        if start > 0:
            start = next((t for t in frames if t >= start), end)
        if end - start > 0.05:
            snapped.append((start, end))
    return snapped


async def video(src: Path, keep: list[tuple[float, float]], folder: Path) -> Path:
    """Video ohne Werbung: die Stücke ohne Neukodierung ausschneiden und aneinanderhängen."""
    pieces = snap_to_keyframes(keep, await keyframes(src))
    if not pieces:
        raise ExportError("Nach dem Entfernen der Werbung bleibt nichts übrig")
    ext = src.suffix or ".mp4"
    names = []
    for index, (start, end) in enumerate(pieces):
        part = folder / f"teil_{index:03d}{ext}"
        await _run("ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-i", str(src),
                   "-t", f"{end - start:.3f}", "-map", "0:v:0", "-map", "0:a?", "-c", "copy",
                   "-avoid_negative_ts", "make_zero", str(part))
        names.append(f"file '{part.name}'")
    listing = folder / "teile.txt"
    listing.write_text("\n".join(names) + "\n", encoding="utf-8")
    out = folder / f"video{ext}"
    await _run("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
               "-map", "0", "-c", "copy", str(out))
    return out


async def audio(src: Path, keep: list[tuple[float, float]], fmt: str, folder: Path) -> Path:
    """Tonspur ohne Werbung, sekundengenau (wird ohnehin neu kodiert)."""
    if not keep:
        raise ExportError("Nach dem Entfernen der Werbung bleibt nichts übrig")
    select = "+".join(f"between(t,{start:.3f},{end:.3f})" for start, end in keep)
    out = folder / f"audio.{fmt}"
    await _run("ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn",
               "-af", f"aselect='{select}',asetpts=N/SR/TB", *AUDIO_CODECS[fmt], str(out))
    return out

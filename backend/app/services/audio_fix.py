"""
TubeVault – Audio-Fix Service v1.0.0

Nachträgliche Korrektur der Tonspur bei Videos, die mit der falschen
Audiospur heruntergeladen wurden (z.B. englische KI-Dub statt deutschem
Original – YouTube markiert den Dub als "(default)").

Sicherer, mehrstufiger Ablauf mit zwei Prüf-Gates – NICHTS wird
überschrieben bis der User beide bestätigt:

  1. fetch_original_audio()  → lädt NUR die Original-Audiospur ins Staging
  2. (User hört Audio ab – Gate 1)
  3. build_fixed_video()     → remuxt Video (copy) + neue Spur (aac) → fixed.mp4
  4. (User prüft das neue Video – Gate 2)
  5. commit()                → validiert, ersetzt Original, DB-Update, Cleanup

Staging-Layout:  AUDIO_DIR/<video_id>/audiofix/
  - original_audio.<ext>   frisch geladene Original-Audiospur
  - fixed.mp4              neu zusammengebautes Video
  - meta.json             erkannte Sprache, Quell-Codec, Zeitstempel
"""
import asyncio
import json
import logging
import shutil
from pathlib import Path

from app.database import db
from app.config import AUDIO_DIR

logger = logging.getLogger(__name__)


def _staging_dir(video_id: str) -> Path:
    return AUDIO_DIR / video_id / "audiofix"


def _audio_glob(video_id: str):
    d = _staging_dir(video_id)
    if not d.exists():
        return []
    return [p for p in d.iterdir() if p.name.startswith("original_audio.")]


async def _video_row(video_id: str) -> dict:
    row = await db.fetch_one(
        "SELECT id, title, file_path, file_size FROM videos WHERE id = ? AND status = 'ready'",
        (video_id,),
    )
    if not row or not row["file_path"]:
        raise ValueError("Video nicht gefunden oder nicht bereit")
    return dict(row)


async def _ffprobe(path: Path) -> dict:
    """ffprobe → dict mit streams + format. Wirft RuntimeError bei Fehler."""
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe: {err.decode()[-200:]}")
    return json.loads(out.decode())


def _audio_streams(probe: dict) -> list:
    return [s for s in probe.get("streams", []) if s.get("codec_type") == "audio"]


def _video_streams(probe: dict) -> list:
    return [s for s in probe.get("streams", []) if s.get("codec_type") == "video"]


# ─── Schritt 0: Welche Tonspuren bietet YouTube? ──────────────────

async def probe_tracks(video_id: str) -> dict:
    """Listet verfügbare Audio-Sprachen + die erkannte Original-Sprache.
    Plus: welche Sprache steckt aktuell in der lokalen Datei."""
    await _video_row(video_id)  # existiert?
    from app.utils.ytdlp_adapter import _ydl_extract

    url = f"https://www.youtube.com/watch?v={video_id}"
    info = await asyncio.to_thread(_ydl_extract, url)
    orig_lang = info.get("language")
    fmts = info.get("formats") or []
    seen = {}
    for f in fmts:
        if f.get("acodec") in (None, "none") or f.get("vcodec") not in (None, "none"):
            continue
        lg = f.get("language")
        note = f.get("format_note") or ""
        if lg not in seen:
            seen[lg] = {"language": lg, "note": note,
                        "is_original": "original" in note.lower()}
    tracks = list(seen.values())

    # Aktuelle lokale Spur
    local_lang = None
    try:
        row = await _video_row(video_id)
        probe = await _ffprobe(Path(row["file_path"]))
        astreams = _audio_streams(probe)
        if astreams:
            local_lang = (astreams[0].get("tags") or {}).get("language")
    except Exception as e:
        logger.debug(f"audiofix probe local {video_id}: {e}")

    return {
        "video_id": video_id,
        "original_language": orig_lang,
        "available_tracks": tracks,
        "multi_track": len(tracks) > 1,
        "local_language": local_lang,
    }


# ─── Schritt 1: Original-Audio laden (Staging) ────────────────────

async def fetch_original_audio(video_id: str) -> dict:
    """Lädt NUR die Original-Audiospur ins Staging. Überschreibt nichts
    am Video. Liefert erkannte Sprache + Pfad zum Probehören."""
    await _video_row(video_id)
    from app.utils.ytdlp_adapter import _build_ydl_opts
    import yt_dlp

    staging = _staging_dir(video_id)
    staging.mkdir(parents=True, exist_ok=True)
    # Altes Staging-Audio entfernen (frischer Versuch)
    for p in _audio_glob(video_id):
        p.unlink(missing_ok=True)

    url = f"https://www.youtube.com/watch?v={video_id}"
    opts = _build_ydl_opts(label=f"audiofix:{video_id}", for_download=True)
    opts.update({
        "format": "bestaudio",
        "format_sort": ["lang"],      # Original-Sprache gewinnt
        "outtmpl": str(staging / "original_audio.%(ext)s"),
        "postprocessors": [],
        "noprogress": True,
    })
    await asyncio.to_thread(_run_ydl_download, opts, url)

    files = _audio_glob(video_id)
    if not files:
        raise RuntimeError("Audio-Download lieferte keine Datei")
    audio_path = files[0]

    probe = await _ffprobe(audio_path)
    astreams = _audio_streams(probe)
    a = astreams[0] if astreams else {}
    lang = (a.get("tags") or {}).get("language")
    codec = a.get("codec_name")
    duration = float(probe.get("format", {}).get("duration") or 0)
    size = audio_path.stat().st_size

    meta = {
        "video_id": video_id,
        "audio_file": audio_path.name,
        "language": lang,
        "codec": codec,
        "duration": duration,
        "size": size,
    }
    (staging / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    logger.info(f"[audiofix] {video_id}: Original-Audio geladen "
                f"({codec}, lang={lang}, {size/1024/1024:.1f} MB)")
    return meta


def _run_ydl_download(opts: dict, url: str):
    """Synchroner yt-dlp Download (in Thread ausgeführt)."""
    import yt_dlp
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])


# ─── Schritt 2: Video neu zusammenbauen (Staging) ─────────────────

async def build_fixed_video(video_id: str) -> dict:
    """Remuxt das bestehende Video (Video-Spur verlustfrei kopiert) mit der
    geladenen Original-Audiospur (→ aac) nach fixed.mp4. Fasst das
    Original NICHT an."""
    row = await _video_row(video_id)
    staging = _staging_dir(video_id)
    files = _audio_glob(video_id)
    if not files:
        raise ValueError("Kein Original-Audio im Staging – erst laden")
    audio_path = files[0]
    src_video = Path(row["file_path"])
    if not src_video.exists():
        raise ValueError("Video-Datei nicht auf der Platte")

    fixed = staging / "fixed.mp4"
    fixed.unlink(missing_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(src_video),
        "-i", str(audio_path),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(fixed),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, err = await proc.communicate()
    if proc.returncode != 0 or not fixed.exists():
        raise RuntimeError(f"ffmpeg remux: {err.decode()[-200:]}")

    # Validieren: muss 1 Video + 1 Audio haben
    probe = await _ffprobe(fixed)
    if not _video_streams(probe) or not _audio_streams(probe):
        fixed.unlink(missing_ok=True)
        raise RuntimeError("Neu gebautes Video unvollständig (Video/Audio fehlt)")

    size = fixed.stat().st_size
    logger.info(f"[audiofix] {video_id}: fixed.mp4 gebaut ({size/1024/1024:.1f} MB)")
    return {"video_id": video_id, "fixed_size": size,
            "original_size": row["file_size"] or 0}


# ─── Schritt 3: Übernehmen (Original ersetzen) ────────────────────

async def commit(video_id: str) -> dict:
    """Ersetzt das Original durch das neu gebaute Video. Sicher:
    - fixed.mp4 wird vor dem Ersetzen ffprobe-validiert
    - Original wird erst nach erfolgreichem Move + Re-Validierung gelöscht
    - bei Fehler Rollback aus Backup
    - stale Audio-Extrakt-Cache wird invalidiert
    """
    row = await _video_row(video_id)
    staging = _staging_dir(video_id)
    fixed = staging / "fixed.mp4"
    if not fixed.exists():
        raise ValueError("Kein fertiges Video im Staging – erst neu bauen")

    # Vor-Validierung
    probe = await _ffprobe(fixed)
    if not _video_streams(probe) or not _audio_streams(probe):
        raise RuntimeError("fixed.mp4 ungültig – Übernahme abgebrochen")

    target = Path(row["file_path"])
    bak = target.with_suffix(target.suffix + ".audiofix-bak")

    # Backup + Ersetzen
    if target.exists():
        shutil.move(str(target), str(bak))
    try:
        shutil.move(str(fixed), str(target))
        # Re-Validierung der finalen Datei
        post = await _ffprobe(target)
        if not _video_streams(post) or not _audio_streams(post):
            raise RuntimeError("Finale Datei ungültig")
    except Exception as e:
        # Rollback
        if bak.exists():
            shutil.move(str(bak), str(target))
        logger.error(f"[audiofix] {video_id}: Commit fehlgeschlagen, Rollback: {e}")
        raise RuntimeError(f"Übernahme fehlgeschlagen (Rollback ausgeführt): {e}")

    new_size = target.stat().st_size
    await db.execute(
        "UPDATE videos SET file_size = ?, updated_at = datetime('now') WHERE id = ?",
        (new_size, video_id),
    )

    # Backup verwerfen (neue Datei validiert) + stale Audio-Extrakt löschen
    bak.unlink(missing_ok=True)
    for ext in ("mp3", "m4a", "flac", "ogg"):
        (AUDIO_DIR / video_id / f"audio.{ext}").unlink(missing_ok=True)

    # Staging aufräumen
    await discard(video_id)

    logger.info(f"[audiofix] {video_id}: Tonspur übernommen, neue Größe {new_size/1024/1024:.1f} MB")
    return {"video_id": video_id, "new_size": new_size,
            "old_size": row["file_size"] or 0}


# ─── Verwerfen / Status ───────────────────────────────────────────

async def discard(video_id: str) -> dict:
    """Staging-Verzeichnis löschen, keine Änderung am Video."""
    staging = _staging_dir(video_id)
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    return {"video_id": video_id, "discarded": True}


def status(video_id: str) -> dict:
    """Aktueller Staging-Zustand (für UI-Wiederaufnahme)."""
    staging = _staging_dir(video_id)
    has_audio = bool(_audio_glob(video_id))
    has_fixed = (staging / "fixed.mp4").exists()
    meta = None
    meta_f = staging / "meta.json"
    if meta_f.exists():
        try:
            meta = json.loads(meta_f.read_text())
        except Exception:
            meta = None
    return {
        "video_id": video_id,
        "has_audio": has_audio,
        "has_fixed": has_fixed,
        "meta": meta,
    }

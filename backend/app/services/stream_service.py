"""
TubeVault -  Stream Analysis Service v1.3.2
FFprobe-basierte Stream-Analyse
© HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
"""

import asyncio
import json
import logging
from pathlib import Path

from app.database import db
from app.services.archive_service import archive_service

logger = logging.getLogger(__name__)


class StreamService:
    """Analysiert Video-Streams per FFprobe."""

    async def analyze_video(self, video_id: str) -> dict:
        """Video mit FFprobe analysieren und Streams in DB speichern."""
        resolved = await archive_service.resolve_video_path(video_id)
        if not resolved["available"]:
            raise ValueError("Video-Datei nicht verfügbar")

        file_path = resolved["path"]

        # FFprobe ausführen
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_streams", "-show_format",
            str(file_path)
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"FFprobe fehlgeschlagen: {stderr.decode()}")

        probe = json.loads(stdout.decode())
        streams_data = probe.get("streams", [])
        format_data = probe.get("format", {})

        # Alte Streams löschen
        await db.execute("DELETE FROM streams WHERE video_id = ?", (video_id,))

        saved = []
        for s in streams_data:
            codec_type = s.get("codec_type", "")
            if codec_type not in ("video", "audio"):
                continue

            stream_info = {
                "video_id": video_id,
                "stream_type": codec_type,
                "codec": s.get("codec_name"),
                "mime_type": f"{codec_type}/{s.get('codec_name', 'unknown')}",
                "language": (s.get("tags", {}).get("language") or
                            s.get("tags", {}).get("LANGUAGE")),
                "file_path": str(file_path),
                "bitrate": int(s.get("bit_rate", 0)) if s.get("bit_rate") else None,
                "is_default": s.get("disposition", {}).get("default", 0) == 1,
                "is_combined": True,
                "downloaded": True,
            }

            if codec_type == "video":
                stream_info["resolution"] = f"{s.get('width', '?')}x{s.get('height', '?')}"
                stream_info["fps"] = _parse_fps(s.get("r_frame_rate", ""))
                stream_info["quality"] = f"{s.get('height', '?')}p"
            elif codec_type == "audio":
                stream_info["sample_rate"] = int(s.get("sample_rate", 0)) if s.get("sample_rate") else None
                stream_info["channels"] = s.get("channels")

            cursor = await db.execute(
                """INSERT INTO streams (video_id, stream_type, codec, mime_type, language,
                   file_path, bitrate, is_default, is_combined, downloaded,
                   resolution, fps, quality, sample_rate, channels)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (stream_info["video_id"], stream_info["stream_type"],
                 stream_info["codec"], stream_info["mime_type"],
                 stream_info.get("language"), stream_info["file_path"],
                 stream_info.get("bitrate"), stream_info["is_default"],
                 stream_info["is_combined"], stream_info["downloaded"],
                 stream_info.get("resolution"), stream_info.get("fps"),
                 stream_info.get("quality"), stream_info.get("sample_rate"),
                 stream_info.get("channels"))
            )
            stream_info["id"] = cursor.lastrowid
            saved.append(stream_info)

        logger.info(f"Video {video_id}: {len(saved)} Streams analysiert")
        return {
            "video_id": video_id,
            "streams": saved,
            "format": {
                "name": format_data.get("format_name"),
                "duration": float(format_data.get("duration", 0)),
                "size": int(format_data.get("size", 0)),
                "bitrate": int(format_data.get("bit_rate", 0)) if format_data.get("bit_rate") else None,
            }
        }

    async def get_streams(self, video_id: str) -> list[dict]:
        """Alle Streams eines Videos abrufen."""
        rows = await db.fetch_all(
            "SELECT * FROM streams WHERE video_id = ? ORDER BY stream_type, is_default DESC",
            (video_id,)
        )
        return [dict(r) for r in rows]

    async def get_combinations(self, video_id: str) -> list[dict]:
        """Stream-Kombinationen abrufen."""
        rows = await db.fetch_all(
            """SELECT sc.*, vs.quality as video_quality, vs.codec as video_codec,
                      as2.codec as audio_codec, as2.language as audio_lang
               FROM stream_combinations sc
               LEFT JOIN streams vs ON sc.video_stream_id = vs.id
               LEFT JOIN streams as2 ON sc.audio_stream_id = as2.id
               WHERE sc.video_id = ?
               ORDER BY sc.is_default DESC""",
            (video_id,)
        )
        return [dict(r) for r in rows]

    async def save_combination(self, video_id: str, name: str,
                               video_stream_id: int, audio_stream_id: int,
                               audio_offset_ms: int = 0, is_default: bool = False) -> dict:
        """Stream-Kombination speichern."""
        if is_default:
            await db.execute(
                "UPDATE stream_combinations SET is_default = 0 WHERE video_id = ?",
                (video_id,)
            )

        cursor = await db.execute(
            """INSERT INTO stream_combinations (video_id, name, video_stream_id,
               audio_stream_id, audio_offset_ms, is_default)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (video_id, name, video_stream_id, audio_stream_id, audio_offset_ms, is_default)
        )
        return {"id": cursor.lastrowid, "name": name}

    async def delete_combination(self, combo_id: int):
        """Stream-Kombination löschen."""
        await db.execute("DELETE FROM stream_combinations WHERE id = ?", (combo_id,))


def _parse_fps(fps_str: str) -> float | None:
    """FPS-String parsen (z.B. '30/1' → 30.0)."""
    if not fps_str:
        return None
    try:
        if "/" in fps_str:
            n, d = fps_str.split("/")
            return round(int(n) / int(d), 2) if int(d) > 0 else None
        return float(fps_str)
    except (ValueError, ZeroDivisionError):
        return None


stream_service = StreamService()

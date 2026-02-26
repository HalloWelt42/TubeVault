"""
TubeVault -  Export Router v1.5.80
CSV/JSON-Exporte für Videos, Abos, Playlists.
Backup-Funktionen sind in backup.py.
© HalloWelt42 -  Private Nutzung
"""

import json
import csv
import io
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.database import db
from app.config import EXPORTS_DIR

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/exports", tags=["Exports"])


@router.get("")
async def list_exports():
    """Vorhandene Exports auflisten."""
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(EXPORTS_DIR.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
    return [
        {
            "name": f.name,
            "size": f.stat().st_size,
            "created": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        }
        for f in files if f.is_file()
    ]


@router.get("/videos/json")
async def export_videos_json():
    """Alle Videos als JSON exportieren."""
    rows = await db.fetch_all("SELECT * FROM videos WHERE status = 'ready' ORDER BY title")
    videos = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get("tags"), str):
            try:
                d["tags"] = json.loads(d["tags"])
            except (json.JSONDecodeError, TypeError):
                d["tags"] = []
        d.pop("ai_summary", None)
        d.pop("ai_tags", None)
        videos.append(d)

    content = json.dumps(videos, ensure_ascii=False, indent=2)
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=tubevault-videos-{datetime.now().strftime('%Y%m%d')}.json"},
    )


@router.get("/videos/csv")
async def export_videos_csv():
    """Alle Videos als CSV exportieren."""
    rows = await db.fetch_all(
        """SELECT id, title, channel_name, channel_id, duration, upload_date,
                  download_date, file_size, rating, play_count, tags, notes, status
           FROM videos WHERE status = 'ready' ORDER BY title"""
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["video_id", "title", "channel", "channel_id", "duration_sec",
                     "upload_date", "download_date", "file_size_bytes", "rating",
                     "play_count", "tags", "notes", "status"])
    for r in rows:
        d = dict(r)
        tags_str = ""
        if d.get("tags"):
            try:
                tags = json.loads(d["tags"]) if isinstance(d["tags"], str) else d["tags"]
                tags_str = "; ".join(tags)
            except (json.JSONDecodeError, TypeError):
                pass
        writer.writerow([
            d["id"], d["title"], d["channel_name"], d["channel_id"],
            d["duration"], d["upload_date"], d["download_date"],
            d["file_size"], d["rating"], d["play_count"], tags_str,
            d["notes"], d["status"],
        ])

    content = output.getvalue()
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8-sig")),  # BOM für Excel
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=tubevault-videos-{datetime.now().strftime('%Y%m%d')}.csv"},
    )


@router.get("/subscriptions/csv")
async def export_subscriptions_csv():
    """Abonnements als CSV exportieren (FreeTube-kompatibel)."""
    rows = await db.fetch_all(
        "SELECT channel_id, channel_name, auto_download, enabled, created_at FROM subscriptions ORDER BY channel_name"
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["channel_id", "channel_name", "auto_download", "enabled", "subscribed_at"])
    for r in rows:
        d = dict(r)
        writer.writerow([d["channel_id"], d["channel_name"], d["auto_download"], d["enabled"], d["created_at"]])

    content = output.getvalue()
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=tubevault-subscriptions-{datetime.now().strftime('%Y%m%d')}.csv"},
    )


@router.get("/playlists/json")
async def export_playlists_json():
    """Alle Playlists mit Videos als JSON exportieren."""
    playlists = await db.fetch_all("SELECT * FROM playlists ORDER BY name")
    result = []
    for pl in playlists:
        p = dict(pl)
        videos = await db.fetch_all(
            """SELECT v.id, v.title, v.channel_name, pv.position
               FROM playlist_videos pv JOIN videos v ON v.id = pv.video_id
               WHERE pv.playlist_id = ? ORDER BY pv.position""",
            (p["id"],)
        )
        p["videos"] = [dict(v) for v in videos]
        result.append(p)

    content = json.dumps(result, ensure_ascii=False, indent=2)
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=tubevault-playlists-{datetime.now().strftime('%Y%m%d')}.json"},
    )


@router.delete("/{filename}")
async def delete_export(filename: str):
    """Export-Datei löschen."""
    filepath = EXPORTS_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Datei nicht gefunden")
    if not filepath.is_relative_to(EXPORTS_DIR):
        raise HTTPException(status_code=400, detail="Ungültiger Pfad")
    filepath.unlink()
    return {"deleted": True, "name": filename}

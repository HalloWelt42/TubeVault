"""
TubeVault – Import Router v1.3.0
YouTube-Playlist Import, URL-Listen, lokale Video-Registrierung
© HalloWelt42 – Private Nutzung
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from app.utils.tag_utils import sanitize_tags
from pydantic import BaseModel

from app.database import db
from app.config import VIDEOS_DIR, THUMBNAILS_DIR
from app.services.rate_limiter import rate_limiter
from app.utils.file_utils import now_sqlite

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/import", tags=["Import"])


class YTPlaylistImport(BaseModel):
    url: str
    download_all: bool = False
    quality: Optional[str] = "720p"


class URLListImport(BaseModel):
    urls: list[str]
    quality: Optional[str] = "720p"
    auto_download: bool = False


class LocalVideoRegister(BaseModel):
    file_path: str
    title: Optional[str] = None
    channel_name: Optional[str] = None
    description: Optional[str] = None
    tags: list[str] = []
    notes: Optional[str] = None


# --- YouTube-Playlist Import ---

@router.post("/youtube-playlist")
async def import_youtube_playlist(data: YTPlaylistImport):
    """YouTube-Playlist inspizieren → Videos auflisten (rate-limited)."""
    await rate_limiter.acquire("pytubefix")

    def _fetch():
        from pytubefix import Playlist
        pl = Playlist(data.url)
        videos = []
        for v in pl.videos:
            try:
                videos.append({
                    "id": v.video_id,
                    "title": v.title,
                    "channel_name": v.author,
                    "channel_id": v.channel_id,
                    "duration": v.length,
                    "thumbnail_url": v.thumbnail_url,
                })
            except Exception as e:
                logger.warning(f"Playlist video parse error: {e}")
        return {
            "playlist_id": pl.playlist_id,
            "title": pl.title,
            "owner": getattr(pl, "owner", None),
            "videos": videos,
        }

    try:
        result = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        rate_limiter.success("pytubefix")
    except Exception as e:
        rate_limiter.error("pytubefix", str(e)[:200])
        raise HTTPException(status_code=500, detail=f"Playlist-Abruf fehlgeschlagen: {e}")

    # Enrichment: welche Videos schon lokal vorhanden?
    for v in result["videos"]:
        existing = await db.fetch_one("SELECT status FROM videos WHERE id = ?", (v["id"],))
        v["already_downloaded"] = existing is not None and existing["status"] == "ready"
        v["status"] = existing["status"] if existing else None

    # Playlist in DB registrieren
    await db.execute(
        """INSERT OR IGNORE INTO playlists (name, source, source_url, source_id, video_count)
           VALUES (?, 'youtube', ?, ?, ?)""",
        (result["title"] or "YouTube Playlist", data.url,
         result["playlist_id"], len(result["videos"]))
    )

    return result


@router.post("/youtube-playlist/download-selected")
async def download_selected_from_playlist(
    video_ids: list[str],
    quality: str = "720p",
):
    """Ausgewählte Videos aus Playlist-Import herunterladen."""
    from app.services.download_service import download_service

    results = []
    for vid in video_ids:
        url = f"https://www.youtube.com/watch?v={vid}"
        try:
            r = await download_service.add_to_queue(url, quality=quality)
            results.append(r)
        except Exception as e:
            results.append({"video_id": vid, "status": "error", "error": str(e)})

    return {"queued": len([r for r in results if r.get("status") == "queued"]),
            "errors": len([r for r in results if r.get("status") == "error"]),
            "results": results}


# --- Channel-Videos via pytubefix Channel ---

@router.get("/channel-videos/{channel_id}")
async def fetch_channel_videos(
    channel_id: str,
    max_results: int = 30,
):
    """Alle Videos eines Kanals via pytubefix Channel laden (rate-limited, manuell)."""
    await rate_limiter.acquire("pytubefix")
    await rate_limiter.acquire("channel_scan")

    def _fetch():
        from pytubefix import Channel
        url = f"https://www.youtube.com/channel/{channel_id}"
        ch = Channel(url)
        videos = []
        for v in ch.videos:
            if len(videos) >= max_results:
                break
            try:
                videos.append({
                    "id": v.video_id,
                    "title": v.title,
                    "duration": v.length,
                    "view_count": v.views,
                    "thumbnail_url": v.thumbnail_url,
                    "publish_date": str(v.publish_date) if v.publish_date else None,
                })
            except Exception as e:
                logger.warning(f"Channel video parse error: {e}")
        return {
            "channel_name": ch.channel_name,
            "channel_id": channel_id,
            "videos": videos,
        }

    try:
        result = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        rate_limiter.success("pytubefix")
        rate_limiter.success("channel_scan")
    except Exception as e:
        rate_limiter.error("pytubefix", str(e)[:200])
        rate_limiter.error("channel_scan", str(e)[:200])
        raise HTTPException(status_code=500, detail=f"Kanal-Abruf fehlgeschlagen: {e}")

    # Enrichment
    for v in result["videos"]:
        existing = await db.fetch_one("SELECT status FROM videos WHERE id = ?", (v["id"],))
        v["already_downloaded"] = existing is not None and existing["status"] == "ready"

    return result


# --- URL-Listen Import ---

@router.post("/url-list")
async def import_url_list(data: URLListImport):
    """URLs aus Liste importieren (txt/csv kompatibel)."""
    from app.services.download_service import download_service

    results = []
    for url in data.urls:
        url = url.strip()
        if not url or url.startswith("#"):
            continue
        if data.auto_download:
            try:
                r = await download_service.add_to_queue(url, quality=data.quality)
                results.append(r)
            except Exception as e:
                results.append({"url": url, "status": "error", "error": str(e)})
        else:
            # Nur Info abrufen
            try:
                info = await download_service.get_video_info(url)
                results.append({"status": "resolved", **info})
            except Exception as e:
                results.append({"url": url, "status": "error", "error": str(e)})

    return {
        "total": len(results),
        "queued": len([r for r in results if r.get("status") == "queued"]),
        "resolved": len([r for r in results if r.get("status") == "resolved"]),
        "errors": len([r for r in results if r.get("status") == "error"]),
        "results": results,
    }


# --- Lokale Video-Registrierung (eigene Videos, nicht YouTube) ---

@router.post("/local-video")
async def register_local_video(data: LocalVideoRegister):
    """Eigenes lokales Video registrieren (nicht-YouTube)."""
    file_path = Path(data.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=400, detail=f"Datei nicht gefunden: {data.file_path}")

    # Video-ID generieren (UUID für lokale Videos)
    video_id = f"local_{uuid.uuid4().hex[:12]}"

    # Metadaten per FFprobe extrahieren
    duration = None
    file_size = file_path.stat().st_size
    try:
        import subprocess
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams",
             str(file_path)],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            probe = json.loads(result.stdout)
            fmt = probe.get("format", {})
            duration = int(float(fmt.get("duration", 0)))
    except Exception as e:
        logger.warning(f"FFprobe für lokales Video fehlgeschlagen: {e}")

    title = data.title or file_path.stem
    now = now_sqlite()
    tags_json = json.dumps(sanitize_tags(data.tags or []))

    await db.execute(
        """INSERT INTO videos
           (id, title, channel_name, description, duration, download_date,
            tags, status, file_path, file_size, source, source_url, notes,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'ready', ?, ?, 'local', ?, ?, ?, ?)""",
        (video_id, title, data.channel_name, data.description,
         duration, now, tags_json, str(file_path), file_size,
         str(file_path), data.notes, now, now)
    )

    logger.info(f"Lokales Video registriert: {video_id} ({title})")
    return {
        "id": video_id,
        "title": title,
        "duration": duration,
        "file_size": file_size,
        "source": "local",
        "registered": True,
    }


@router.post("/scan-directory")
async def scan_directory(
    path: str,
    extensions: str = ".mp4,.mkv,.webm,.avi,.mov",
):
    """Verzeichnis nach Videodateien scannen und auflisten."""
    scan_path = Path(path)
    if not scan_path.exists() or not scan_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Verzeichnis nicht gefunden: {path}")

    exts = [e.strip().lower() for e in extensions.split(",")]
    found = []

    for f in sorted(scan_path.rglob("*")):
        if f.is_file() and f.suffix.lower() in exts:
            # Bereits registriert?
            existing = await db.fetch_one(
                "SELECT id FROM videos WHERE file_path = ?", (str(f),)
            )
            found.append({
                "path": str(f),
                "name": f.name,
                "size": f.stat().st_size,
                "already_registered": existing is not None,
                "video_id": existing["id"] if existing else None,
            })

    return {
        "path": path,
        "total_found": len(found),
        "new": len([f for f in found if not f["already_registered"]]),
        "files": found,
    }


# --- FreeTube Import ---

class FreeTubeImport(BaseModel):
    """FreeTube Import aus profiles.db oder playlists.db."""
    type: str  # 'subscriptions' oder 'playlists'

@router.post("/freetube/subscriptions")
async def import_freetube_subscriptions(file: UploadFile = File(...)):
    """FreeTube Abonnements aus profiles.db importieren."""
    content = await file.read()
    
    # FreeTube profiles.db ist JSONL (eine JSON-Zeile pro Profil)
    lines = content.decode("utf-8", errors="replace").strip().split("\n")
    imported = 0
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            # FreeTube subscriptions format
            subs = entry.get("subscriptions", [])
            if not subs and entry.get("name"):
                # Einzelnes Abo
                subs = [entry]
            
            for sub in subs:
                channel_id = sub.get("id") or sub.get("channelId")
                channel_name = sub.get("name") or sub.get("channelName", "")
                thumbnail = sub.get("thumbnail", "")
                
                if not channel_id:
                    continue
                
                await db.execute(
                    """INSERT OR IGNORE INTO subscriptions 
                       (channel_id, channel_name, thumbnail_url, auto_download, check_interval)
                       VALUES (?, ?, ?, 0, 3600)""",
                    (channel_id, channel_name, thumbnail)
                )
                imported += 1
        except (json.JSONDecodeError, TypeError):
            continue
    
    return {"imported": imported, "source": "freetube_profiles"}


@router.post("/freetube/playlists")
async def import_freetube_playlists(file: UploadFile = File(...)):
    """FreeTube Playlists aus playlists.db importieren."""
    content = await file.read()
    lines = content.decode("utf-8", errors="replace").strip().split("\n")
    playlists_imported = 0
    videos_imported = 0
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            pl_name = entry.get("playlistName", entry.get("name", "FreeTube Playlist"))
            videos = entry.get("videos", [])
            
            # Playlist erstellen
            cursor = await db.execute(
                """INSERT INTO playlists (name, source, video_count, description)
                   VALUES (?, 'freetube', ?, ?)""",
                (pl_name, len(videos), f"Importiert aus FreeTube ({len(videos)} Videos)")
            )
            pl_id = cursor.lastrowid
            playlists_imported += 1
            
            # Videos zur Playlist hinzufügen
            for i, v in enumerate(videos):
                vid = v.get("videoId") or v.get("id", "")
                if not vid:
                    continue
                
                # Video als Metadaten registrieren (noch nicht heruntergeladen)
                title = v.get("title", f"Video {vid}")
                channel = v.get("author") or v.get("channelName", "")
                duration = v.get("lengthSeconds", 0)
                
                await db.execute(
                    """INSERT OR IGNORE INTO videos 
                       (id, title, channel_name, duration, source, source_url, status, created_at, updated_at)
                       VALUES (?, ?, ?, ?, 'freetube', ?, 'metadata', datetime('now'), datetime('now'))""",
                    (vid, title, channel, duration, f"https://www.youtube.com/watch?v={vid}")
                )
                
                await db.execute(
                    "INSERT OR IGNORE INTO playlist_videos (playlist_id, video_id, position) VALUES (?, ?, ?)",
                    (pl_id, vid, i)
                )
                videos_imported += 1
        except (json.JSONDecodeError, TypeError):
            continue
    
    return {
        "playlists_imported": playlists_imported,
        "videos_imported": videos_imported,
        "source": "freetube_playlists"
    }


# --- YouTube Takeout Import ---

@router.post("/youtube-takeout/watch-history")
async def import_youtube_takeout_history(file: UploadFile = File(...)):
    """YouTube Takeout Watch History (watch-history.json) importieren."""
    content = await file.read()
    
    try:
        data = json.loads(content.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Ungültige JSON-Datei")
    
    if not isinstance(data, list):
        raise HTTPException(status_code=400, detail="Erwarte JSON-Array")
    
    imported = 0
    for entry in data:
        url = entry.get("titleUrl", "")
        title = entry.get("title", "").replace("Watched ", "", 1)
        
        # Video-ID aus URL extrahieren
        vid = None
        if "watch?v=" in url:
            vid = url.split("watch?v=")[-1].split("&")[0]
        elif "youtu.be/" in url:
            vid = url.split("youtu.be/")[-1].split("?")[0]
        
        if not vid or len(vid) < 5:
            continue
        
        channel = ""
        subtitles = entry.get("subtitles", [])
        if subtitles:
            channel = subtitles[0].get("name", "")
        
        time_str = entry.get("time", "")
        
        # Video als Metadaten registrieren
        await db.execute(
            """INSERT OR IGNORE INTO videos 
               (id, title, channel_name, source, source_url, status, created_at, updated_at)
               VALUES (?, ?, ?, 'youtube_takeout', ?, 'metadata', datetime('now'), datetime('now'))""",
            (vid, title, channel, url)
        )
        
        # Watch History eintragen
        await db.execute(
            "INSERT OR IGNORE INTO watch_history (video_id, watched_at, completed) VALUES (?, ?, 0)",
            (vid, time_str or now_sqlite())
        )
        imported += 1
    
    return {"imported": imported, "total_entries": len(data), "source": "youtube_takeout_history"}


@router.post("/youtube-takeout/subscriptions")
async def import_youtube_takeout_subs(file: UploadFile = File(...)):
    """YouTube Takeout Subscriptions (subscriptions.csv oder .json) importieren."""
    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    imported = 0
    
    # Versuche JSON
    try:
        data = json.loads(text)
        for entry in data:
            cid = entry.get("snippet", {}).get("resourceId", {}).get("channelId", "")
            name = entry.get("snippet", {}).get("title", "")
            thumb = entry.get("snippet", {}).get("thumbnails", {}).get("default", {}).get("url", "")
            if cid:
                await db.execute(
                    """INSERT OR IGNORE INTO subscriptions 
                       (channel_id, channel_name, thumbnail_url, source, auto_download, check_interval)
                       VALUES (?, ?, ?, 'youtube_takeout', 0, 3600)""",
                    (cid, name, thumb)
                )
                imported += 1
        return {"imported": imported, "source": "youtube_takeout_subscriptions_json"}
    except (json.JSONDecodeError, TypeError):
        pass
    
    # Versuche CSV
    import csv
    import io
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    
    # YouTube Takeout CSV: Channel Id, Channel Url, Channel Title
    cid_idx = 0
    name_idx = 2
    if header:
        for i, h in enumerate(header):
            if "id" in h.lower():
                cid_idx = i
            if "title" in h.lower() or "name" in h.lower():
                name_idx = i
    
    for row in reader:
        if len(row) <= max(cid_idx, name_idx):
            continue
        cid = row[cid_idx].strip()
        name = row[name_idx].strip() if len(row) > name_idx else ""
        if cid and cid.startswith("UC"):
            await db.execute(
                """INSERT OR IGNORE INTO subscriptions 
                   (channel_id, channel_name, source, auto_download, check_interval)
                   VALUES (?, ?, 'youtube_takeout', 0, 3600)""",
                (cid, name)
            )
            imported += 1
    
    return {"imported": imported, "source": "youtube_takeout_subscriptions_csv"}

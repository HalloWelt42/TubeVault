"""
TubeVault -  Channel Playlists Router v1.7.0
YouTube-Playlist-Abruf und Import -  Job-basiert mit Fortschritt.
© HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
import json
import logging

logger = logging.getLogger(__name__)

from app.database import db
from app.services.job_service import job_service

router = APIRouter(prefix="/api/subscriptions", tags=["Kanal-Playlists (YouTube)"])


@router.get("/channel/{channel_id}/playlists")
async def get_channel_playlists(channel_id: str):
    """Gespeicherte YouTube-Playlists eines Kanals + lokale Import-Info."""
    try:
        rows = await db.fetch_all(
            "SELECT * FROM channel_playlists WHERE channel_id = ? ORDER BY title",
            (channel_id,)
        )
    except Exception as e:
        logger.warning(f"channel_playlists query failed: {e}")
        return {"channel_id": channel_id, "playlists": [], "local_playlists": []}

    playlists = []
    for r in rows:
        try:
            row_dict = dict(r)
            video_ids = json.loads(row_dict.get("video_ids") or "[]")
            if not isinstance(video_ids, list):
                video_ids = []
        except (json.JSONDecodeError, TypeError):
            video_ids = []

        have_count = 0
        in_rss = 0
        if video_ids:
            try:
                placeholders = ",".join("?" * len(video_ids))
                have_count = await db.fetch_val(
                    f"SELECT COUNT(*) FROM videos WHERE id IN ({placeholders}) AND status = 'ready'",
                    tuple(video_ids)
                ) or 0
                in_rss = await db.fetch_val(
                    f"SELECT COUNT(*) FROM rss_entries WHERE video_id IN ({placeholders})",
                    tuple(video_ids)
                ) or 0
            except Exception as e:
                logger.warning(f"Playlist stats query failed for {row_dict.get('playlist_id')}: {e}")

        # Prüfe ob lokal importiert
        local_pl = await db.fetch_one(
            "SELECT id FROM playlists WHERE source_id = ? AND source = 'youtube'",
            (row_dict["playlist_id"],))
        local_playlist_id = local_pl["id"] if local_pl else None

        playlists.append({
            **row_dict,
            "video_ids": video_ids,
            "have_count": have_count,
            "in_rss_count": in_rss,
            "local_playlist_id": local_playlist_id,
        })

    # Lokale Playlists dieses Kanals (inkl. manuell erstellte mit channel_id)
    local_playlists = []
    try:
        local_rows = await db.fetch_all(
            """SELECT p.*, COUNT(pv.video_id) as actual_count,
                      SUM(CASE WHEN v.status = 'ready' THEN 1 ELSE 0 END) as ready_count
               FROM playlists p
               LEFT JOIN playlist_videos pv ON p.id = pv.playlist_id
               LEFT JOIN videos v ON pv.video_id = v.id
               WHERE p.channel_id = ?
               GROUP BY p.id
               ORDER BY p.name""",
            (channel_id,))
        for lp in local_rows:
            local_playlists.append(dict(lp))
    except Exception as e:
        logger.warning(f"Local playlists query failed: {e}")

    return {"channel_id": channel_id, "playlists": playlists, "local_playlists": local_playlists}


@router.post("/channel/{channel_id}/fetch-playlists")
async def fetch_channel_playlists(channel_id: str, background_tasks: BackgroundTasks):
    """YouTube-Playlists eines Kanals abrufen -  als Background-Job."""
    from app.services.playlist_service import fetch_channel_playlists_job

    sub = await db.fetch_one(
        "SELECT channel_name FROM subscriptions WHERE channel_id = ?", (channel_id,))
    channel_name = sub["channel_name"] if sub else channel_id

    job = await job_service.create(
        job_type="playlist_fetch",
        title=f"Playlists laden: {channel_name}",
        description=f"Lade YouTube-Playlists von {channel_name}",
        metadata={"channel_id": channel_id, "trigger": "manual"},
    )

    async def _run():
        try:
            await fetch_channel_playlists_job(channel_id, job["id"])
        except Exception as e:
            logger.error(f"Playlist-Fetch {channel_id} fehlgeschlagen: {e}")

    background_tasks.add_task(_run)
    return {"status": "started", "job_id": job["id"], "channel_id": channel_id}


@router.post("/playlists/{playlist_id}/fetch-videos")
async def fetch_playlist_videos(playlist_id: str, background_tasks: BackgroundTasks):
    """Video-IDs einer YouTube-Playlist laden -  als Background-Job."""
    from app.services.playlist_service import fetch_playlist_videos_job

    row = await db.fetch_one(
        "SELECT * FROM channel_playlists WHERE playlist_id = ?", (playlist_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Playlist nicht gefunden")
    row = dict(row)

    job = await job_service.create(
        job_type="playlist_videos",
        title=f"Videos laden: {row.get('title', playlist_id)}",
        description=f"Lade Video-IDs für \u201e{row.get('title', '')}\u201c",
        metadata={"playlist_id": playlist_id, "title": row.get("title", ""), "trigger": "manual"},
    )

    async def _run():
        try:
            await fetch_playlist_videos_job(playlist_id, job["id"])
        except Exception as e:
            logger.error(f"Playlist-Videos {playlist_id} fehlgeschlagen: {e}")

    background_tasks.add_task(_run)
    return {"status": "started", "job_id": job["id"], "playlist_id": playlist_id}


@router.post("/playlists/{playlist_id}/import")
async def import_playlist_to_local(playlist_id: str, background_tasks: BackgroundTasks):
    """YouTube-Playlist als lokale Playlist importieren -  als Background-Job.
    Registriert alle Videos (auch nicht-heruntergeladene) als Platzhalter.
    """
    from app.services.playlist_service import import_playlist_to_local_job

    row = await db.fetch_one(
        "SELECT * FROM channel_playlists WHERE playlist_id = ?", (playlist_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Playlist nicht gefunden")
    row = dict(row)

    video_ids = json.loads(row.get("video_ids") or "[]")
    if not video_ids:
        raise HTTPException(status_code=400, detail="Keine Video-IDs geladen. Erst 'Videos laden' ausführen.")

    job = await job_service.create(
        job_type="playlist_import",
        title=f"Import: {row.get('title', playlist_id)}",
        description=f"Importiere \u201e{row.get('title', '')}\u201c ({len(video_ids)} Videos)",
        metadata={"playlist_id": playlist_id, "title": row.get("title", ""),
                  "total_videos": len(video_ids), "trigger": "manual"},
    )

    async def _run():
        try:
            await import_playlist_to_local_job(playlist_id, job["id"])
        except Exception as e:
            logger.error(f"Playlist-Import {playlist_id} fehlgeschlagen: {e}")

    background_tasks.add_task(_run)
    return {"status": "started", "job_id": job["id"], "playlist_id": playlist_id,
            "title": row.get("title", ""), "total_videos": len(video_ids)}


@router.post("/playlists/local/{playlist_id}/visibility")
async def toggle_playlist_visibility(playlist_id: int, data: dict):
    """Sichtbarkeit einer lokalen Playlist umschalten (global/channel)."""
    visibility = data.get("visibility", "global")
    if visibility not in ("global", "channel"):
        raise HTTPException(status_code=400, detail="Ungültig: 'global' oder 'channel'")
    await db.execute(
        "UPDATE playlists SET visibility = ? WHERE id = ?", (visibility, playlist_id))
    return {"status": "ok", "playlist_id": playlist_id, "visibility": visibility}

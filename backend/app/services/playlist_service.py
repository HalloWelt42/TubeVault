"""
TubeVault – Playlist Service v1.7.0
Job-basierte YouTube-Playlist-Operationen.
Alle YouTube-Calls laufen als Background-Jobs mit Fortschritt.
© HalloWelt42 – Private Nutzung
"""

import asyncio
import json
import logging
import threading

from app.database import db
from app.services.job_service import job_service
from app.services.rate_limiter import rate_limiter
from app.utils.file_utils import now_sqlite

logger = logging.getLogger(__name__)


async def fetch_channel_playlists_job(channel_id: str, job_id: int):
    """Background-Job: YouTube-Playlists eines Kanals abrufen."""
    await job_service.start(job_id, exclusive=True)

    try:
        await rate_limiter.acquire("pytubefix")

        def _fetch():
            from pytubefix import Channel
            ch = Channel(f"https://www.youtube.com/channel/{channel_id}")
            result = []
            errors = 0
            try:
                for pl in ch.playlists:
                    try:
                        pid = getattr(pl, "playlist_id", None)
                        if not pid:
                            try:
                                pid = pl.playlist_url.split("list=")[-1].split("&")[0]
                            except Exception:
                                errors += 1
                                continue

                        title = None
                        try:
                            title = pl.title
                        except (KeyError, AttributeError):
                            try:
                                title = pl._html_data.get("title", {}).get("runs", [{}])[0].get("text")
                            except Exception:
                                pass
                        title = title or f"Playlist {pid[:20]}"

                        result.append({
                            "playlist_id": pid,
                            "title": title,
                            "description": getattr(pl, "description", None) or "",
                            "video_count": getattr(pl, "length", 0) or 0,
                            "thumbnail_url": getattr(pl, "thumbnail_url", None),
                        })
                    except Exception as e:
                        errors += 1
                        logger.debug(f"Playlist parse skip: {e}")
            except Exception as e:
                logger.warning(f"Playlist-Iteration für {channel_id}: {e}")
            del ch  # pytubefix Channel-Objekt freigeben
            import gc; gc.collect()
            return result, errors

        loop = asyncio.get_event_loop()
        playlists, errors = await loop.run_in_executor(None, _fetch)
        rate_limiter.success("pytubefix")

        # In DB speichern
        now = now_sqlite()
        saved = 0
        for i, pl in enumerate(playlists):
            try:
                await db.execute(
                    """INSERT INTO channel_playlists
                       (channel_id, playlist_id, title, description, thumbnail_url, video_count, fetched_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(playlist_id) DO UPDATE SET
                       title = excluded.title, description = excluded.description,
                       thumbnail_url = excluded.thumbnail_url, video_count = excluded.video_count,
                       fetched_at = excluded.fetched_at""",
                    (channel_id, pl["playlist_id"], pl["title"], pl["description"],
                     pl["thumbnail_url"], pl["video_count"], now)
                )
                saved += 1
            except Exception as e:
                logger.warning(f"Playlist save error: {e}")

            # Fortschritt
            pct = (i + 1) / max(len(playlists), 1)
            await job_service.progress(
                job_id, pct,
                f"{saved} Playlists gespeichert",
                metadata={"found": len(playlists), "saved": saved, "errors": errors}
            )

        result_msg = f"{saved} Playlists gefunden, {errors} Fehler"
        await job_service.complete(job_id, result_msg)
        return {"found": len(playlists), "saved": saved, "errors": errors}

    except Exception as e:
        rate_limiter.error("pytubefix", str(e)[:200])
        await job_service.fail(job_id, str(e))
        raise


async def fetch_playlist_videos_job(playlist_id: str, job_id: int):
    """Background-Job: Video-IDs einer YouTube-Playlist laden.
    Nutzt video_urls (schnell, kein Metadaten-Abruf pro Video).
    Fortschritt wird live aktualisiert.
    """
    await job_service.start(job_id, exclusive=True)

    row = await db.fetch_one(
        "SELECT * FROM channel_playlists WHERE playlist_id = ?", (playlist_id,))
    if not row:
        await job_service.fail(job_id, "Playlist nicht in DB gefunden")
        return

    row = dict(row)
    est_count = row.get("video_count") or 0

    try:
        await rate_limiter.acquire("pytubefix")

        # Video-URLs in separatem Thread laden mit laufendem Zähler
        state = {"count": 0, "done": False, "error": None}
        state_lock = threading.Lock()
        collected_ids = []  # Nur im Thread geschrieben, am Ende gelesen

        def _fetch():
            from pytubefix import Playlist
            pl = Playlist(f"https://www.youtube.com/playlist?list={playlist_id}")
            for url in pl.video_urls:
                vid = url.split("v=")[-1].split("&")[0] if "v=" in url else url.split("/")[-1]
                if vid and len(vid) == 11:
                    collected_ids.append(vid)
                    with state_lock:
                        state["count"] = len(collected_ids)
            with state_lock:
                state["done"] = True
            del pl  # pytubefix Objekt freigeben
            import gc; gc.collect()
            return collected_ids

        # Starte Iterator in Thread
        loop = asyncio.get_event_loop()
        fetch_task = loop.run_in_executor(None, _fetch)

        # Progress-Tracker: pollt state alle 1.5s
        while True:
            await asyncio.sleep(1.5)
            with state_lock:
                count = state["count"]
                done = state["done"]

            if est_count > 0:
                pct = min(count / est_count, 0.99)
            else:
                pct = min(count / max(count + 50, 100), 0.90)

            await job_service.progress(
                job_id, pct,
                f"{count} Video-IDs geladen…",
                metadata={
                    "playlist_id": playlist_id,
                    "title": row.get("title", ""),
                    "count": count,
                    "estimated": est_count,
                }
            )

            if done:
                break

        video_ids = await fetch_task
        rate_limiter.success("pytubefix")

        # In DB speichern
        now = now_sqlite()
        await db.execute(
            "UPDATE channel_playlists SET video_ids = ?, video_count = ?, fetched_at = ? WHERE playlist_id = ?",
            (json.dumps(video_ids), len(video_ids), now, playlist_id)
        )

        # Stats: wie viele schon lokal? (in Batches wegen SQLite 999-Var-Limit)
        have = 0
        if video_ids:
            for batch_start in range(0, len(video_ids), 500):
                batch = video_ids[batch_start:batch_start + 500]
                placeholders = ",".join("?" * len(batch))
                have += await db.fetch_val(
                    f"SELECT COUNT(*) FROM videos WHERE id IN ({placeholders}) AND status = 'ready'",
                    tuple(batch)
                ) or 0

        result_msg = f"{len(video_ids)} Videos, {have} lokal vorhanden"
        await job_service.complete(job_id, result_msg)
        return {
            "playlist_id": playlist_id,
            "total": len(video_ids),
            "have": have,
            "missing": len(video_ids) - have,
        }

    except Exception as e:
        rate_limiter.error("pytubefix", str(e)[:200])
        await job_service.fail(job_id, str(e))
        raise


async def import_playlist_to_local_job(playlist_id: str, job_id: int):
    """Background-Job: YouTube-Playlist als lokale Playlist importieren/aktualisieren.
    Idempotent: Erstellt neu oder aktualisiert bestehende Playlist.
    """
    await job_service.start(job_id, exclusive=False)

    row = await db.fetch_one(
        "SELECT * FROM channel_playlists WHERE playlist_id = ?", (playlist_id,))
    if not row:
        await job_service.fail(job_id, "Playlist nicht in DB gefunden")
        return

    row = dict(row)
    video_ids = json.loads(row.get("video_ids") or "[]")
    if not video_ids:
        await job_service.fail(job_id, "Keine Video-IDs geladen. Erst 'Inhalt abrufen' ausführen.")
        return

    try:
        channel_id = row.get("channel_id", "")

        # Prüfe ob bereits importiert (source_id = YouTube playlist ID)
        existing = await db.fetch_one(
            "SELECT id FROM playlists WHERE source_id = ? AND source = 'youtube'",
            (playlist_id,))

        if existing:
            pl_id = existing["id"]
            # Aktualisiere Metadaten
            await db.execute(
                """UPDATE playlists SET name = ?, description = ?,
                   video_count = ?, channel_id = COALESCE(channel_id, ?)
                   WHERE id = ?""",
                (row["title"], row.get("description", ""), len(video_ids),
                 channel_id, pl_id))
            # Bestehende Zuordnungen holen
            existing_vids = set()
            ev_rows = await db.fetch_all(
                "SELECT video_id FROM playlist_videos WHERE playlist_id = ?", (pl_id,))
            for ev in ev_rows:
                existing_vids.add(ev["video_id"])
            is_update = True
        else:
            # Neue Playlist erstellen
            cursor = await db.execute(
                """INSERT INTO playlists (name, description, source, source_id, source_url,
                   video_count, channel_id, visibility)
                   VALUES (?, ?, 'youtube', ?, ?, ?, ?, 'global')""",
                (row["title"], row.get("description", ""), playlist_id,
                 f"https://www.youtube.com/playlist?list={playlist_id}",
                 len(video_ids), channel_id))
            pl_id = cursor.lastrowid
            existing_vids = set()
            is_update = False

        added = 0
        registered = 0
        skipped = 0
        for i, vid in enumerate(video_ids):
            if vid in existing_vids:
                # Position ggf. aktualisieren
                await db.execute(
                    "UPDATE playlist_videos SET position = ? WHERE playlist_id = ? AND video_id = ?",
                    (i, pl_id, vid))
                skipped += 1
            else:
                # Video in DB?
                exists = await db.fetch_one("SELECT id, status FROM videos WHERE id = ?", (vid,))
                if not exists:
                    await db.execute(
                        """INSERT OR IGNORE INTO videos
                           (id, title, source, source_url, status, created_at, updated_at)
                           VALUES (?, ?, 'youtube_playlist', ?, 'metadata', datetime('now'), datetime('now'))""",
                        (vid, f"Video {vid}", f"https://www.youtube.com/watch?v={vid}"))
                    registered += 1

                await db.execute(
                    "INSERT OR IGNORE INTO playlist_videos (playlist_id, video_id, position) VALUES (?, ?, ?)",
                    (pl_id, vid, i))
                added += 1

            if (i + 1) % 20 == 0 or i == len(video_ids) - 1:
                pct = (i + 1) / len(video_ids)
                await job_service.progress(
                    job_id, pct,
                    f"{added} neu, {skipped} aktualisiert, {registered} registriert",
                    metadata={"playlist_id": pl_id, "total": len(video_ids),
                              "added": added, "registered": registered, "skipped": skipped})

        # Entferne Videos die nicht mehr in der YT-Playlist sind
        removed = 0
        if is_update:
            yt_set = set(video_ids)
            to_remove = existing_vids - yt_set
            for vid in to_remove:
                await db.execute(
                    "DELETE FROM playlist_videos WHERE playlist_id = ? AND video_id = ?",
                    (pl_id, vid))
                removed += 1

        action = "aktualisiert" if is_update else "erstellt"
        result_msg = f"Playlist '{row['title']}' {action}: {added} neu, {skipped} bestehend"
        if removed:
            result_msg += f", {removed} entfernt"
        await job_service.complete(job_id, result_msg)
        return {"playlist_id": pl_id, "title": row["title"], "total": len(video_ids),
                "added": added, "registered": registered, "skipped": skipped,
                "removed": removed, "is_update": is_update}

    except Exception as e:
        await job_service.fail(job_id, str(e))
        raise


async def auto_link_video_to_playlists(video_id: str):
    """Nach Download: Video automatisch in alle passenden lokalen Playlists einfügen.

    Prüft channel_playlists → wenn video_id in video_ids UND lokale Playlist existiert
    → INSERT in playlist_videos.
    """
    try:
        rows = await db.fetch_all(
            "SELECT playlist_id, video_ids FROM channel_playlists WHERE video_ids LIKE ?",
            (f'%{video_id}%',))

        linked = 0
        for row in rows:
            row = dict(row)
            vid_list = json.loads(row.get("video_ids") or "[]")
            if video_id not in vid_list:
                continue

            # Lokale Playlist finden
            local_pl = await db.fetch_one(
                "SELECT id FROM playlists WHERE source_id = ? AND source = 'youtube'",
                (row["playlist_id"],))
            if not local_pl:
                continue

            # Position bestimmen
            pos = vid_list.index(video_id)

            # Einfügen (OR IGNORE falls schon drin)
            await db.execute(
                "INSERT OR IGNORE INTO playlist_videos (playlist_id, video_id, position) VALUES (?, ?, ?)",
                (local_pl["id"], video_id, pos))
            linked += 1

        if linked:
            logger.info(f"Auto-Link: {video_id} → {linked} Playlist(s)")
    except Exception as e:
        logger.warning(f"Auto-Link Fehler für {video_id}: {e}")

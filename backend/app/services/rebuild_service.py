"""
TubeVault – Rebuild Service v1.0.0

Offline-Wiederaufbau des DB-Index aus den redundanten Dateien:

1. rebuild_from_sidecars(): scannt VIDEOS_DIR/<id>/info.json (Sidecars aus
   meta_sidecar) und legt fehlende videos-Zeilen wieder an – Videodatei wird
   im Ordner gesucht (größte Mediendatei, deckt auch video_tmp.*-Altlasten ab),
   Beschreibung kommt aus TEXTS_DIR/<id>/description.txt falls vorhanden.
   Bestehende DB-Einträge werden NIE überschrieben (DB bleibt führend).

2. restore_userdata(): spielt einen userdata_export-Ordner (JSONL) zurück.
   Ganze Tabellen per INSERT OR IGNORE (vorhandene Zeilen gewinnen),
   Video-Nutzerfelder per UPDATE nur wo das Video existiert.

Alles läuft ohne Internet – genau der Zweck der Meta-Redundanz.
"""
import asyncio
import json
import logging

from app.database import db
from app.services import meta_sidecar
from app.services.storage import storage
from app.services.userdata_export import TABLES, userdata_root

logger = logging.getLogger(__name__)

MEDIA_EXTS = {".mp4", ".mkv", ".webm", ".m4v", ".avi", ".mov"}

# Fortschritt für die Admin-UI (ein Rebuild zur Zeit)
rebuild_state = {"running": False, "done": 0, "total": 0,
                 "restored": 0, "existing": 0, "invalid": 0, "no_media": 0,
                 "dry_run": False}


def _find_media_file(folder):
    """Größte Mediendatei im Video-Ordner (robust gegen video_tmp.*-Namen)."""
    best, best_size = None, -1
    try:
        for f in folder.iterdir():
            if f.is_file() and f.suffix.lower() in MEDIA_EXTS:
                size = f.stat().st_size
                if size > best_size:
                    best, best_size = f, size
    except OSError:
        return None, 0
    return best, max(best_size, 0)


def _read_description(video_id: str) -> str | None:
    p = storage.texts_root / video_id / "description.txt"
    try:
        if p.exists():
            return p.read_text(encoding="utf-8")
    except OSError:
        pass
    return None


async def rebuild_from_sidecars(dry_run: bool = False,
                                throttle_every: int = 50,
                                throttle_sleep: float = 0.1) -> dict:
    """Fehlende videos-Zeilen aus Sidecars wiederherstellen."""
    if rebuild_state["running"]:
        return {"error": "Rebuild läuft bereits"}

    root = storage.videos_root
    folders = await asyncio.to_thread(
        lambda: [d for d in root.iterdir() if d.is_dir()] if root.is_dir() else [])
    existing_rows = await db.fetch_all("SELECT id FROM videos")
    existing = {r["id"] for r in existing_rows}

    rebuild_state.update(running=True, done=0, total=len(folders),
                         restored=0, existing=0, invalid=0, no_media=0,
                         dry_run=dry_run)
    logger.info(f"[rebuild] Start: {len(folders)} Video-Ordner, dry_run={dry_run}")
    try:
        for i, folder in enumerate(folders):
            rebuild_state["done"] = i + 1
            if throttle_every and (i + 1) % throttle_every == 0:
                await asyncio.sleep(throttle_sleep)

            if folder.name in existing:
                rebuild_state["existing"] += 1
                continue
            data = await asyncio.to_thread(
                meta_sidecar.read_sidecar_file, folder / meta_sidecar.SIDECAR_NAME)
            if not data or data.get("id") != folder.name:
                rebuild_state["invalid"] += 1
                continue
            media, size = await asyncio.to_thread(_find_media_file, folder)
            if not media:
                rebuild_state["no_media"] += 1
                continue
            if dry_run:
                rebuild_state["restored"] += 1
                continue

            desc = await asyncio.to_thread(_read_description, data["id"])
            await db.execute(
                """INSERT OR IGNORE INTO videos
                   (id, title, channel_id, channel_name, description,
                    duration, upload_date, download_date, view_count,
                    like_count, dislike_count, tags, status,
                    file_path, file_size, source, source_url, video_type,
                    is_music, music_artist, music_title, music_album,
                    is_archived, thumbnail_path, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'ready',?,?,?,?,?,?,?,?,?,?,?,
                           datetime('now'), datetime('now'))""",
                (data["id"], data.get("title"), data.get("channel_id"),
                 data.get("channel_name"), desc,
                 data.get("duration"), data.get("upload_date"),
                 data.get("download_date"), data.get("view_count"),
                 data.get("like_count"), data.get("dislike_count"),
                 json.dumps(data.get("tags") or [], ensure_ascii=False),
                 str(media), size or data.get("file_size"),
                 data.get("source") or "youtube", data.get("source_url"),
                 data.get("video_type") or "video",
                 data.get("is_music") or 0, data.get("music_artist"),
                 data.get("music_title"), data.get("music_album"),
                 data.get("is_archived") or 0,
                 f"thumbnails/{data['id']}.jpg"))
            try:
                await db.fts_sync_video(data["id"])
            except Exception:
                pass
            rebuild_state["restored"] += 1
    finally:
        rebuild_state["running"] = False
    logger.info(f"[rebuild] Fertig: {rebuild_state['restored']} wiederhergestellt, "
                f"{rebuild_state['existing']} vorhanden, "
                f"{rebuild_state['invalid']} ohne/ungültiges Sidecar, "
                f"{rebuild_state['no_media']} ohne Mediendatei")
    return dict(rebuild_state)


async def restore_userdata(folder: str = None) -> dict:
    """Userdata-Export (JSONL) zurückspielen. folder=None → neuester Export.

    Ganze Tabellen: INSERT OR IGNORE – vorhandene Zeilen bleiben unangetastet.
    video_userdata: UPDATE nur, wo das Video existiert und das Feld leer ist
    (COALESCE) – ein Restore überschreibt keine frischeren Nutzerdaten.
    """
    root = userdata_root()
    if folder:
        target = root / folder
    else:
        candidates = sorted([d for d in root.iterdir()
                             if d.is_dir() and d.name.startswith("userdata_")]) \
            if root.is_dir() else []
        target = candidates[-1] if candidates else None
    if not target or not target.is_dir():
        return {"error": "Kein Userdata-Export gefunden"}

    result = {"folder": target.name, "tables": {}}
    for table in TABLES:
        f = target / f"{table}.jsonl"
        if not f.exists():
            continue
        lines = await asyncio.to_thread(
            lambda p=f: p.read_text(encoding="utf-8").splitlines())
        inserted = 0
        for line in lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            cols = list(row.keys())
            sql = (f"INSERT OR IGNORE INTO {table} ({', '.join(cols)}) "
                   f"VALUES ({', '.join('?' * len(cols))})")
            cursor = await db.execute(sql, tuple(row[c] for c in cols))
            inserted += cursor.rowcount if cursor.rowcount > 0 else 0
        result["tables"][table] = {"rows": len(lines), "inserted": inserted}

    f = target / "video_userdata.jsonl"
    if f.exists():
        lines = await asyncio.to_thread(
            lambda: f.read_text(encoding="utf-8").splitlines())
        updated = 0
        for line in lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            cursor = await db.execute(
                """UPDATE videos SET
                   rating = CASE WHEN COALESCE(rating, 0) = 0
                                 THEN COALESCE(?, rating) ELSE rating END,
                   play_count = MAX(COALESCE(play_count, 0), ?),
                   last_position = MAX(COALESCE(last_position, 0), ?),
                   last_played = COALESCE(last_played, ?),
                   notes = COALESCE(NULLIF(notes, ''), ?),
                   suggest_override = COALESCE(suggest_override, ?)
                   WHERE id = ?""",
                (row.get("rating"), row.get("play_count") or 0,
                 row.get("last_position") or 0, row.get("last_played"),
                 row.get("notes"), row.get("suggest_override"), row.get("id")))
            updated += cursor.rowcount if cursor.rowcount > 0 else 0
        result["tables"]["video_userdata"] = {"rows": len(lines), "updated": updated}

    logger.info(f"[rebuild] Userdata aus {target.name} zurückgespielt")
    return result

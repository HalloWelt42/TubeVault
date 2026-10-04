"""
TubeVault – Channel Scanner v2.0.0
Vollständiger Kanal-Scan (Videos, Shorts, Livestreams).

Die drei Listen der Quelle werden nacheinander seitenweise gelesen und
paketweise gespeichert. Der Scan ist ehrlich: Ein Abbruch oder eine Störung
gilt nicht als erfolgreicher Scan - gefundene Einträge bleiben erhalten, aber
"zuletzt gescannt" und die Zähler einer gestörten Liste werden nicht gesetzt.
© HalloWelt42 – Private Nutzung
"""

import asyncio
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx

from app.utils import source_net

from app.database import db
from app.services.job_service import job_service
from app.utils.file_utils import now_sqlite
from app.utils.tag_utils import sanitize_tags
from app.services.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)

# Der Scan liest getrennte Listen der Quelle (Videos, Shorts, Livestreams):
# der Typ ist damit bestätigt und gilt als geprüft (siehe video_classifier).
_TYPE_VERIFIED = 1

_executor = ThreadPoolExecutor(max_workers=1)  # Pi: nur 1 gleichzeitiger Scan

# Batch-Größe: alle N Einträge automatisch in DB speichern
BATCH_SIZE = 15  # Kleine Batches = weniger Memory-Spitzen auf Pi (16GB)


async def _save_entries_batch(entries, channel_id):
    """Batch von Einträgen in rss_entries speichern. Gibt (inserted, updated, errors) zurück."""
    inserted = 0
    updated = 0
    errors = 0
    for v in entries:
        try:
            cursor = await db.execute(
                """INSERT OR IGNORE INTO rss_entries
                   (video_id, channel_id, title, published, thumbnail_url,
                    duration, views, description, video_type, keywords, status, type_verified)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)""",
                (v["video_id"], channel_id, v.get("title"),
                 v.get("published"), v.get("thumbnail_url"),
                 v.get("duration"), v.get("views"),
                 (v.get("description") or "")[:5000],
                 v.get("video_type", "video"),
                 json.dumps(v.get("keywords", [])),
                 _TYPE_VERIFIED if v.get("video_type") else 0)
            )
            if cursor.rowcount > 0:
                inserted += 1
            else:
                await db.execute(
                    """UPDATE rss_entries SET
                        duration = COALESCE(?, duration),
                        views = COALESCE(?, views),
                        description = CASE WHEN ? IS NOT NULL AND ? != '' THEN ? ELSE description END,
                        title = COALESCE(?, title),
                        published = COALESCE(published, ?),
                        thumbnail_url = COALESCE(?, thumbnail_url),
                        video_type = CASE WHEN COALESCE(type_verified, 0) = 2 THEN video_type ELSE COALESCE(?, video_type) END,
                        type_verified = CASE WHEN COALESCE(type_verified, 0) = 2 THEN 2 WHEN ? IS NOT NULL THEN 1 ELSE type_verified END,
                        keywords = CASE WHEN ? != '[]' THEN ? ELSE keywords END
                       WHERE video_id = ? AND channel_id = ?""",
                    (v.get("duration"), v.get("views"),
                     v.get("description"), v.get("description"),
                     (v.get("description") or "")[:5000],
                     v.get("title"), v.get("published"), v.get("thumbnail_url"),
                     v.get("video_type"), v.get("video_type"),
                     json.dumps(v.get("keywords", [])),
                     json.dumps(v.get("keywords", [])),
                     v["video_id"], channel_id)
                )
                updated += 1
        except Exception as e:
            errors += 1
            if errors <= 3:
                logger.warning(f"Batch-Save Eintrag {v.get('video_id')} Fehler: {e}")
    return inserted, updated, errors


# Die drei Listen der Quelle: (Phase, Videotyp, Spalte des Zählers, Anzeige)
SCAN_PHASES = [
    ("videos", "video", "video_count", "Videos"),
    ("shorts", "short", "shorts_count", "Shorts"),
    ("live", "live", "live_count", "Livestreams"),
]
_PHASE_PROGRESS = {"metadata": 0.03, "videos": 0.35, "shorts": 0.55, "live": 0.65}


def published_from_upload_date(raw) -> str | None:
    """Datum der Quelle ("JJJJMMTT") in die gespeicherte Schreibweise bringen."""
    raw = str(raw or "")
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}T00:00:00+00:00"
    return None


def _entry_from_item(item, video_type: str) -> dict | None:
    """Listeneintrag der Quelle in einen Feed-Eintrag übersetzen. Beschreibung
    und Schlagworte fehlen bewusst: sie kosten einen Abruf je Video und
    kommen beim Download ohnehin."""
    if not item.video_id:
        return None
    return {
        "video_id": item.video_id,
        "title": item.title or None,
        "published": published_from_upload_date(item.publish_date),
        "thumbnail_url": item.thumbnail_url or None,
        "duration": item.length or None,
        "views": item.views or None,
        "description": None,
        "video_type": video_type,
        "keywords": [],
    }


def _read_channel_meta(ch) -> dict:
    """Grunddaten des Kanals (ein leichter Abruf, keine Videoliste)."""
    return {
        "channel_name": ch.channel_name or None,
        "description": ch.description or None,
        "subscriber_count": ch.subscriber_count,
        "banner_url": ch.banner_url or None,
        "channel_tags": ch.tags[:50],
    }


async def _cache_banner(channel_id: str, banner_url: str) -> str:
    """Banner lokal ablegen; liefert die Adresse, die gespeichert wird."""
    from app.config import BANNERS_DIR
    try:
        BANNERS_DIR.mkdir(parents=True, exist_ok=True)
        async with source_net.async_client(timeout=15) as client:
            resp = await client.get(banner_url)
        if resp.status_code == 200 and len(resp.content) > 1000:
            (BANNERS_DIR / f"{channel_id}.jpg").write_bytes(resp.content)
            return f"/api/subscriptions/banner/{channel_id}"
    except Exception as e:
        logger.warning(f"Banner-Cache fehlgeschlagen: {e}")
    return banner_url


async def _store_channel_meta(channel_id: str, channel_meta: dict):
    """Grunddaten in das Abo schreiben. Leere Werte überschreiben nichts."""
    updates, params = [], []
    if channel_meta.get("description"):
        updates.append("channel_description = ?")
        params.append(channel_meta["description"][:2000])
    if channel_meta.get("subscriber_count"):
        updates.append("subscriber_count = ?")
        params.append(channel_meta["subscriber_count"])
    if channel_meta.get("channel_name"):
        updates.append("channel_name = ?")
        params.append(channel_meta["channel_name"])
    if channel_meta.get("banner_url"):
        updates.append("banner_url = ?")
        params.append(await _cache_banner(channel_id, channel_meta["banner_url"]))
    if channel_meta.get("channel_tags"):
        updates.append("channel_tags = ?")
        params.append(json.dumps(sanitize_tags(channel_meta["channel_tags"])))
    if updates:
        await db.execute(
            f"UPDATE subscriptions SET {', '.join(updates)} WHERE channel_id = ?",
            (*params, channel_id))


async def refresh_type_counts(channel_id: str):
    """Zähler des Abos (Videos, Shorts, Livestreams) aus den gespeicherten
    Einträgen bilden. Scan und Prüfung rufen dieselbe Funktion - die Zähler
    sagen immer, was in der Datenbank steht."""
    await db.execute(
        """UPDATE subscriptions SET
             video_count = (SELECT COUNT(*) FROM rss_entries
                            WHERE channel_id = ?1 AND COALESCE(video_type, 'video') = 'video'),
             shorts_count = (SELECT COUNT(*) FROM rss_entries
                             WHERE channel_id = ?1 AND video_type = 'short'),
             live_count = (SELECT COUNT(*) FROM rss_entries
                           WHERE channel_id = ?1 AND video_type = 'live')
           WHERE channel_id = ?1""",
        (channel_id,))


async def refresh_channel_meta(channel_id: str) -> dict:
    """Nur die Grunddaten eines Kanals auffrischen (Name, Banner, Abonnenten,
    Schlagworte) - ohne Videoliste."""
    from app.utils.pytube_client import make_channel

    def _fetch():
        return _read_channel_meta(make_channel(f"https://www.youtube.com/channel/{channel_id}"))

    channel_meta = await asyncio.get_event_loop().run_in_executor(_executor, _fetch)
    await _store_channel_meta(channel_id, channel_meta)
    return channel_meta


async def fetch_all_channel_videos(channel_id: str, job_id: int = None) -> dict:
    """Alle Videos, Shorts und Livestreams eines Kanals laden. Nur auf
    ausdrücklichen Wunsch des Nutzers, nie automatisch."""
    sub = await db.fetch_one(
        "SELECT * FROM subscriptions WHERE channel_id = ?", (channel_id,)
    )
    sub = dict(sub) if sub else None
    channel_name = sub["channel_name"] if sub else channel_id

    # Job von außen (Router) oder selbst erstellen
    if job_id:
        if not await job_service.get(job_id):
            raise ValueError(f"Job #{job_id} nicht gefunden")
    else:
        job = await job_service.create(
            job_type="channel_scan",
            title=f"Kanal-Scan: {channel_name}",
            description="Verbinde mit YouTube…",
            metadata={"channel_id": channel_id, "trigger": "manual"},
        )
        job_id = job["id"]
    await job_service.start(job_id)
    if job_service.is_cancelled(job_id):
        # Abgebrochen, während der Scan auf seinen Platz wartete
        job_service.clear_cancel(job_id)
        return {"total": 0, "new": 0, "updated": 0, "cancelled": True, "channel_id": channel_id}

    precount = 0
    if sub:
        precount = sum(sub.get(column) or 0 for _, _, column, _ in SCAN_PHASES)

    # Geteilter Stand zwischen Lese-Thread und Fortschrittsmeldung
    state = {
        "phase": "metadata",
        "label": "Kanal-Daten werden geladen…",
        "counts": {vtype: 0 for _, vtype, _, _ in SCAN_PHASES},
        "errors": {},              # Videotyp -> Fehlermeldung
        "buffer": [],
        "done": False,
    }
    lock = threading.Lock()
    cancel_event = threading.Event()
    saved = {"inserted": 0, "updated": 0, "errors": 0, "count": 0}

    def _read_all() -> dict:
        """Synchron im Thread: Grunddaten, dann die drei Listen seitenweise."""
        from app.utils.pytube_client import make_channel
        ch = make_channel(f"https://www.youtube.com/channel/{channel_id}")
        channel_meta = _read_channel_meta(ch)
        for phase, vtype, _, phase_label in SCAN_PHASES:
            if cancel_event.is_set():
                break
            state["phase"] = phase
            state["label"] = f"{phase_label} werden geladen…"
            ch.html_url = {"videos": ch.videos_url, "shorts": ch.shorts_url,
                           "live": ch.live_url}[phase]
            try:
                for item in ch.url_generator():
                    if cancel_event.is_set():
                        break
                    entry = _entry_from_item(item, vtype)
                    if not entry:
                        continue
                    with lock:
                        state["buffer"].append(entry)
                    state["counts"][vtype] += 1
                    state["label"] = f"{state['counts'][vtype]} {phase_label} gefunden…"
            except Exception as e:
                state["errors"][vtype] = str(e)[:200]
                logger.warning(f"[Scan] {channel_name}: {phase_label} gestört: {str(e)[:200]}")
        return channel_meta

    async def _flush(minimum: int = 1):
        """Gesammelte Einträge speichern, sobald genug beisammen sind."""
        with lock:
            if len(state["buffer"]) < minimum:
                return
            batch = list(state["buffer"])
            state["buffer"].clear()
        inserted, updated, errors = await _save_entries_batch(batch, channel_id)
        saved["inserted"] += inserted
        saved["updated"] += updated
        saved["errors"] += errors
        saved["count"] += len(batch)

    async def _track_progress():
        """Fortschritt melden, paketweise speichern, Abbruch weiterreichen."""
        while not state["done"]:
            await asyncio.sleep(0.8)
            if job_service.is_cancelled(job_id):
                cancel_event.set()
                return
            await _flush(minimum=BATCH_SIZE)
            counts = state["counts"]
            found = sum(counts.values())
            label = state["label"]
            if state["errors"]:
                label += f" [{len(state['errors'])} Fehler]"
            try:
                await job_service.progress(
                    job_id, _PHASE_PROGRESS.get(state["phase"], 0.5), label,
                    metadata={
                        "phase": state["phase"],
                        "video_count": counts["video"],
                        "short_count": counts["short"],
                        "live_count": counts["live"],
                        "current_count": found,
                        "estimated_total": max(precount, found),
                        "precount": precount,
                        "precount_exceeded": precount > 0 and found > precount,
                        "precount_extra": max(0, found - precount) if precount else 0,
                        "batch_saved": saved["count"],
                    })
            except Exception:
                pass

    await rate_limiter.acquire("channel_scan")
    tracker = asyncio.create_task(_track_progress())
    try:
        channel_meta = await asyncio.get_event_loop().run_in_executor(_executor, _read_all)
    except Exception as e:
        # Schon die Grunddaten waren nicht zu bekommen: nichts gilt als gescannt
        rate_limiter.error("channel_scan", str(e)[:200])
        await job_service.fail(job_id, f"Kanal nicht erreichbar: {str(e)[:250]}")
        job_service.clear_cancel(job_id)
        raise
    finally:
        state["done"] = True
        await asyncio.gather(tracker, return_exceptions=True)

    await _flush()
    await _store_channel_meta(channel_id, channel_meta)

    counts = state["counts"]
    errors = state["errors"]
    cancelled = cancel_event.is_set() or job_service.is_cancelled(job_id)

    await refresh_type_counts(channel_id)
    # "Zuletzt gescannt" nur nach einem Scan ohne Abbruch und Störung
    if not cancelled and not errors:
        await db.execute(
            "UPDATE subscriptions SET last_scanned = ? WHERE channel_id = ?",
            (now_sqlite(), channel_id))

    found = [f"{counts[vtype]} {label}" for _, vtype, _, label in SCAN_PHASES if counts[vtype]]
    result_msg = " | ".join(found + [f"({saved['inserted']} neu, {saved['updated']} aktualisiert)"])
    if saved["errors"]:
        result_msg += f" | {saved['errors']} Einträge nicht gespeichert"

    result = {
        "total": saved["count"], "new": saved["inserted"], "updated": saved["updated"],
        "errors": saved["errors"], "channel_id": channel_id, "cancelled": cancelled,
        "phase_counts": counts, "scan_errors": errors,
        "channel_meta": {
            "banner_url": channel_meta.get("banner_url"),
            "channel_tags": channel_meta.get("channel_tags", []),
            "subscriber_count": channel_meta.get("subscriber_count"),
        },
    }

    if cancelled:
        # Status setzen und Platz freigeben (ohne Wirkung, falls schon geschehen)
        await job_service.cancel(job_id)
        await db.execute(
            "UPDATE jobs SET result = ? WHERE id = ?",
            (f"Abgebrochen - bis dahin gefunden: {result_msg}", job_id))
        job_service.clear_cancel(job_id)
        logger.info(f"Kanal-Scan {channel_name} abgebrochen: {result_msg}")
    elif errors:
        labels = {vtype: label for _, vtype, _, label in SCAN_PHASES}
        detail = "; ".join(f"{labels[vtype]}: {message[:120]}" for vtype, message in errors.items())
        rate_limiter.error("channel_scan", detail[:200])
        await job_service.fail(
            job_id, f"Scan unvollständig - {detail}. Bis dahin gefunden: {result_msg}")
    else:
        rate_limiter.success("channel_scan")
        await job_service.complete(job_id, result_msg)
        logger.info(f"Kanal-Scan {channel_name}: {result_msg}")
    return result

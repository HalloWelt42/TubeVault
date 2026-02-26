"""
TubeVault -  Channel Scanner v1.8.94
Vollständiger Kanal-Scan via pytubefix (Videos/Shorts/Live).
Pre-Count via video_urls, paketweises Speichern, Phase-Transparenz.
Memory-Fix: ch.url_generator() statt ch.videos/shorts/live
→ DeferredGeneratorList cached ALLE YouTube-Objekte in _elements
→ Bei 3500+ Videos = hunderte MB RAM, OOM auf Pi 16GB
→ url_generator() ist der rohe Generator OHNE Caching.
© HalloWelt42 -  Private Nutzung
"""

import asyncio
import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import httpx

from app.database import db
from app.services.job_service import job_service
from app.utils.file_utils import now_sqlite
from app.utils.tag_utils import sanitize_tags
from app.services.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)

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
                    duration, views, description, video_type, keywords, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')""",
                (v["video_id"], channel_id, v.get("title"),
                 v.get("published"), v.get("thumbnail_url"),
                 v.get("duration"), v.get("views"),
                 (v.get("description") or "")[:5000],
                 v.get("video_type", "video"),
                 json.dumps(v.get("keywords", [])))
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
                        thumbnail_url = COALESCE(?, thumbnail_url),
                        video_type = COALESCE(?, video_type),
                        keywords = CASE WHEN ? != '[]' THEN ? ELSE keywords END
                       WHERE video_id = ? AND channel_id = ?""",
                    (v.get("duration"), v.get("views"),
                     v.get("description"), v.get("description"),
                     (v.get("description") or "")[:5000],
                     v.get("title"), v.get("thumbnail_url"),
                     v.get("video_type"),
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


async def fetch_all_channel_videos(channel_id: str, job_id: int = None) -> dict:
    """ALLE Videos+Shorts+Live eines Kanals per pytubefix laden.
    NUR auf User-Klick! NIEMALS automatisch!
    v1.6.43: Pre-Count via video_urls, Batch-Saving, transparente Phasen
    """
    sub = await db.fetch_one(
        "SELECT * FROM subscriptions WHERE channel_id = ?", (channel_id,)
    )
    sub = dict(sub) if sub else None
    channel_name = sub["channel_name"] if sub else channel_id

    # Job von außen (Router) oder selbst erstellen
    if job_id:
        job = await job_service.get(job_id)
        if not job:
            raise ValueError(f"Job #{job_id} nicht gefunden")
        await job_service.start(job_id)
    else:
        job = await job_service.create(
            job_type="channel_scan",
            title=f"Kanal-Scan: {channel_name}",
            description="Verbinde mit YouTube…",
            metadata={"channel_id": channel_id, "trigger": "manual"},
        )
        job_id = job["id"]
        await job_service.start(job_id)

    # Rate Limit
    await rate_limiter.acquire("channel_scan")

    # Geteilter Status zwischen Thread (pytubefix) und Async (Job-Updates)
    scan_state = {
        "phase": "connecting",
        "phase_label": "Verbinde mit YouTube…",
        "video_count": 0,
        "short_count": 0,
        "live_count": 0,
        "current_count": 0,
        "precount": 0,              # Ergebnis der Video-URL-Zählung
        "precount_running": 0,      # Laufender Zähler während Precount
        "estimated_total": 0,
        "precount_exceeded": False,  # True wenn mehr gefunden als gezählt
        "precount_extra": 0,         # Wie viele mehr als erwartet
        "error": None,
        "phase_errors": {},
        "done": False,
        # Batch-Saving: geteilter Puffer
        "entries_buffer": [],       # Aktuelle Entries (wird nach Batch-Save getrimmt)
        "entries_lock": threading.Lock(),
        "saved_idx": 0,             # Global-Zähler: insgesamt gespeicherte Einträge
        "batch_inserted": 0,
        "batch_updated": 0,
        "batch_errors": 0,
        "total_collected": 0,       # Gesamtzahl gesammelter Entries (auch getrimmt)
    }
    cancel_event = threading.Event()

    loop = asyncio.get_event_loop()

    def _fetch_all():
        """Synchron: pytubefix Channel komplett auslesen mit Fortschritt."""
        from pytubefix import Channel

        # ─── Phase 0: Verbinden + Metadaten ─────────────
        scan_state["phase"] = "metadata"
        scan_state["phase_label"] = "Kanal-Metadaten werden geladen…"

        ch = Channel(f"https://www.youtube.com/channel/{channel_id}")

        channel_meta = {
            "channel_name": None, "description": None,
            "subscriber_count": None, "banner_url": None,
            "channel_tags": [],
        }

        try:
            channel_meta["channel_name"] = getattr(ch, "channel_name", None)
        except Exception:
            pass
        try:
            channel_meta["description"] = getattr(ch, "description", None)
        except Exception:
            pass
        try:
            channel_meta["subscriber_count"] = getattr(ch, "subscriber_count", None)
        except Exception:
            pass
        # Banner
        try:
            if hasattr(ch, "initial_data"):
                header = ch.initial_data.get("header", {})
                c4 = header.get("c4TabbedHeaderRenderer", {})
                thumbs = c4.get("banner", {}).get("thumbnails", [])
                if thumbs:
                    channel_meta["banner_url"] = thumbs[-1].get("url")
                if not channel_meta["banner_url"]:
                    phr = header.get("pageHeaderRenderer", {})
                    content = phr.get("content", {}).get("pageHeaderViewModel", {})
                    sources = content.get("banner", {}).get("imageBannerViewModel", {}).get("image", {}).get("sources", [])
                    if sources:
                        channel_meta["banner_url"] = sources[-1].get("url")
        except Exception:
            pass
        # Tags
        try:
            if hasattr(ch, "initial_data"):
                cr = ch.initial_data.get("metadata", {}).get("channelMetadataRenderer", {})
                kw = cr.get("keywords", "")
                if kw:
                    # YouTube keywords: space-separated, quoted multi-word
                    # z.B. '"electronic music" synthwave 80s' oder 'music, rock, pop'
                    import shlex
                    try:
                        tags = shlex.split(kw)
                    except ValueError:
                        # Fallback: comma-split oder space-split
                        if "," in kw:
                            tags = [t.strip().strip('"') for t in kw.split(",")]
                        else:
                            tags = kw.split()
                    channel_meta["channel_tags"] = [t.strip() for t in tags if t.strip()][:50]
        except Exception:
            pass

        name = channel_meta["channel_name"] or channel_name
        scan_state["phase_label"] = f"Metadaten geladen: {name}"

        # initial_data kann mehrere MB JSON sein -  sofort freigeben
        try:
            if hasattr(ch, '_initial_data'):
                ch._initial_data = None
        except Exception:
            pass

        if cancel_event.is_set():
            del ch; import gc; gc.collect()
            return channel_meta, [], {"video": 0, "short": 0, "live": 0}, {}

        # ─── Pre-Count: DB-Wert vom letzten Scan als Schätzung ──────────
        # KEIN separater Pre-Count-Durchlauf mehr!
        # ch.video_urls = @cache + DeferredGeneratorList → cached ALLES
        # ch.url_generator() = erstellt YouTube()-Objekte → doppelter Aufwand
        # Stattdessen: DB-Wert vom letzten Scan nutzen, live aktualisieren.
        precount = 0
        if sub:
            precount = (sub.get("video_count") or 0) + (sub.get("shorts_count") or 0) + (sub.get("live_count") or 0)
        scan_state["precount"] = precount
        scan_state["precount_running"] = precount
        scan_state["estimated_total"] = precount

        if precount > 0:
            scan_state["phase_label"] = f"~{precount} Videos erwartet (letzter Scan)"
        else:
            scan_state["phase_label"] = "Erster Scan -  Videoanzahl unbekannt"

        if cancel_event.is_set():
            del ch; import gc; gc.collect()
            return channel_meta, [], {"video": 0, "short": 0, "live": 0}, {}

        # ─── Video-Extraktion (wiederverwendbar) ────────
        # Primär-Attribute kommen vom Kanal-Listing (kein extra HTTP).
        # description + keywords erfordern Video-Page-Abruf (1 HTTP pro Video).
        # Bei Fehler (Rate-Limit) → wird übersprungen, Scan läuft weiter.
        def _extract(v, vtype):
            entry = {"video_id": None, "title": None, "published": None,
                     "thumbnail_url": None, "duration": None, "views": None,
                     "description": None, "video_type": vtype, "keywords": []}
            try:
                entry["video_id"] = v.video_id
            except Exception:
                return None
            # Listing-Attribute (kein extra HTTP)
            for attr, key in [("title", "title"), ("thumbnail_url", "thumbnail_url"),
                              ("length", "duration"), ("views", "views")]:
                try:
                    entry[key] = getattr(v, attr)
                except Exception:
                    pass
            # publish_date (aus Listing, kein extra HTTP)
            try:
                pd = v.publish_date
                if pd:
                    entry["published"] = str(pd)
            except Exception:
                pass
            # WICHTIG: v.description + v.keywords NICHT abrufen!
            # Diese lösen pro Video einen HTTP-Request zur Video-Seite aus.
            # Bei 3500+ Videos = 3500 Requests + hunderte MB RAM auf dem Pi.
            # Descriptions kommen beim Download sowieso automatisch.
            return entry

        def _add_entry(entry):
            """Thread-safe: Entry zum Puffer hinzufügen."""
            with scan_state["entries_lock"]:
                scan_state["entries_buffer"].append(entry)
                scan_state["total_collected"] += 1

        errors = {"video": [], "short": [], "live": []}
        counts = {"video": 0, "short": 0, "live": 0}
        _gc_counter = 0  # GC-Zähler über alle Phasen

        def _extract_and_add(v, vtype, phase_key):
            """Extract + add + periodisch GC."""
            nonlocal _gc_counter
            entry = _extract(v, vtype)
            if entry and entry["video_id"]:
                _add_entry(entry)
                counts[phase_key] += 1
                _gc_counter += 1
                if _gc_counter % 100 == 0:
                    import gc; gc.collect()

        # ─── Phase 1: Videos ────────────────────────────
        scan_state["phase"] = "videos"
        scan_state["phase_label"] = "Videos werden geladen…"
        scan_state["current_count"] = 0
        try:
            # WICHTIG: ch.videos NICHT verwenden!
            # ch.videos nutzt DeferredGeneratorList die ALLE YouTube-Objekte
            # in _elements cached → bei 3500 Videos = hunderte MB RAM.
            # ch.url_generator() ist der rohe Generator OHNE Caching.
            ch.html_url = ch.videos_url  # Videos-Tab aktivieren
            for v in ch.url_generator():
                if cancel_event.is_set():
                    break
                _extract_and_add(v, "video", "video")
                scan_state["video_count"] = counts["video"]
                scan_state["current_count"] = counts["video"]
                scan_state["phase_label"] = f"{counts['video']} Videos gefunden…"
                # Prüfen ob Precount überschritten
                total_found = counts["video"] + counts["short"] + counts["live"]
                if total_found > scan_state["precount"] > 0:
                    scan_state["precount_exceeded"] = True
                    scan_state["precount_extra"] = total_found - scan_state["precount"]
                    if scan_state["estimated_total"] < total_found:
                        scan_state["estimated_total"] = total_found
                del v  # YouTube-Objekt sofort freigeben
        except Exception as e:
            err_msg = f"Videos-Iterator: {str(e)[:200]}"
            errors["video"].append(err_msg)
            scan_state["phase_errors"]["video"] = err_msg

        if cancel_event.is_set():
            scan_state["done"] = True
            if hasattr(ch, '_initial_data'): ch._initial_data = None
            if hasattr(ch, '_html'): ch._html = None
            del ch; import gc; gc.collect()
            logger.info(f"[Scan] Abbruch nach Videos -  Channel-Objekt freigegeben")
            with scan_state["entries_lock"]:
                return channel_meta, list(scan_state["entries_buffer"]), counts, errors

        # Memory freigeben zwischen Phasen
        # _html und _initial_data sind die größten Speicherfresser
        if hasattr(ch, '_initial_data'): ch._initial_data = None
        if hasattr(ch, '_html'): ch._html = None
        import gc; gc.collect()

        # ─── Phase 2: Shorts ────────────────────────────
        scan_state["phase"] = "shorts"
        scan_state["phase_label"] = f"Shorts werden geladen… (bisher: {counts['video']})"
        scan_state["current_count"] = 0
        try:
            ch.html_url = ch.shorts_url  # Shorts-Tab aktivieren
            for v in ch.url_generator():
                if cancel_event.is_set():
                    break
                _extract_and_add(v, "short", "short")
                scan_state["short_count"] = counts["short"]
                scan_state["current_count"] = counts["short"]
                scan_state["phase_label"] = f"{counts['short']} Shorts gefunden… ({counts['video']})"
                total_found = counts["video"] + counts["short"] + counts["live"]
                if total_found > scan_state["precount"] > 0:
                    scan_state["precount_exceeded"] = True
                    scan_state["precount_extra"] = total_found - scan_state["precount"]
                    if scan_state["estimated_total"] < total_found:
                        scan_state["estimated_total"] = total_found
                del v
        except Exception as e:
            err_msg = f"Shorts-Iterator: {str(e)[:200]}"
            errors["short"].append(err_msg)
            scan_state["phase_errors"]["short"] = err_msg

        if cancel_event.is_set():
            scan_state["done"] = True
            if hasattr(ch, '_initial_data'): ch._initial_data = None
            if hasattr(ch, '_html'): ch._html = None
            del ch; import gc; gc.collect()
            logger.info(f"[Scan] Abbruch nach Shorts -  Channel-Objekt freigegeben")
            with scan_state["entries_lock"]:
                return channel_meta, list(scan_state["entries_buffer"]), counts, errors

        # Memory freigeben zwischen Phasen
        if hasattr(ch, '_initial_data'): ch._initial_data = None
        if hasattr(ch, '_html'): ch._html = None
        import gc; gc.collect()

        # ─── Phase 3: Live ──────────────────────────────
        scan_state["phase"] = "live"
        scan_state["phase_label"] = f"Livestreams werden geladen… ({counts['video']} V, {counts['short']} S)"
        scan_state["current_count"] = 0
        try:
            ch.html_url = ch.live_url  # Streams-Tab aktivieren
            for v in ch.url_generator():
                if cancel_event.is_set():
                    break
                _extract_and_add(v, "live", "live")
                scan_state["live_count"] = counts["live"]
                scan_state["current_count"] = counts["live"]
                scan_state["phase_label"] = f"{counts['live']} Live ({counts['video']} V, {counts['short']} S)"
                total_found = counts["video"] + counts["short"] + counts["live"]
                if total_found > scan_state["precount"] > 0:
                    scan_state["precount_exceeded"] = True
                    scan_state["precount_extra"] = total_found - scan_state["precount"]
                    if scan_state["estimated_total"] < total_found:
                        scan_state["estimated_total"] = total_found
                del v
        except Exception as e:
            err_msg = f"Live-Iterator: {str(e)[:200]}"
            errors["live"].append(err_msg)
            scan_state["phase_errors"]["live"] = err_msg

        scan_state["done"] = True
        # pytubefix Channel-Objekt freigeben (initial_data kann mehrere MB sein)
        del ch
        import gc; gc.collect()
        with scan_state["entries_lock"]:
            remaining = list(scan_state["entries_buffer"])  # Nur noch nicht-gespeicherte
            return channel_meta, remaining, counts, errors

    # ─── Progress-Tracker + Batch-Saver (async, parallel zum Executor) ─
    async def _track_progress():
        """Liest scan_state alle 0.8s, aktualisiert Job UND speichert Batches."""
        phase_weights = {
            "connecting": 0.01, "metadata": 0.03, "precount": 0.08,
            "videos": 0.35, "shorts": 0.55, "live": 0.65, "saving": 0.70,
        }
        while not scan_state["done"]:
            await asyncio.sleep(0.8)
            # Abbruch prüfen
            if job_service.is_cancelled(job_id):
                cancel_event.set()
                scan_state["done"] = True
                break
            phase = scan_state["phase"]
            base = phase_weights.get(phase, 0.5)
            label = scan_state["phase_label"]
            if scan_state.get("phase_errors"):
                err_list = list(scan_state["phase_errors"].values())
                label += f" [{len(err_list)} Fehler]"

            # ─── Batch-Saving: neue Einträge periodisch in DB schreiben ───
            with scan_state["entries_lock"]:
                buf_len = len(scan_state["entries_buffer"])
            if buf_len >= BATCH_SIZE:
                with scan_state["entries_lock"]:
                    batch = list(scan_state["entries_buffer"])
                    scan_state["entries_buffer"].clear()  # Buffer freigeben!
                if batch:
                    ins, upd, errs = await _save_entries_batch(batch, channel_id)
                    scan_state["saved_idx"] += len(batch)
                    scan_state["batch_inserted"] += ins
                    scan_state["batch_updated"] += upd
                    scan_state["batch_errors"] += errs
                    del batch  # Sofort freigeben
                    import gc; gc.collect()
                    logger.debug(f"Batch gespeichert: {ins} neu, {upd} aktualisiert (gesamt {scan_state['saved_idx']})")

            # X/Y Metadata für Frontend-Fortschrittsanzeige
            meta = {
                "phase": phase,
                "video_count": scan_state.get("video_count", 0),
                "short_count": scan_state.get("short_count", 0),
                "live_count": scan_state.get("live_count", 0),
                "current_count": scan_state.get("current_count", 0),
                "estimated_total": scan_state.get("estimated_total", 0),
                "precount": scan_state.get("precount", 0),
                "precount_running": scan_state.get("precount_running", 0),
                "precount_exceeded": scan_state.get("precount_exceeded", False),
                "precount_extra": scan_state.get("precount_extra", 0),
                "batch_saved": scan_state.get("saved_idx", 0),
            }
            try:
                await job_service.progress(job_id, base, label, metadata=meta)
            except Exception:
                pass

    # ─── Ausführung ──────────────────────────────────────
    tracker = asyncio.create_task(_track_progress())

    try:
        channel_meta, all_entries, phase_counts, scan_errors = await loop.run_in_executor(
            _executor, _fetch_all
        )
        rate_limiter.success("channel_scan")

        # Tracker stoppen
        scan_state["done"] = True
        tracker.cancel()
        try:
            await tracker
        except asyncio.CancelledError:
            pass

        # Abbruch nach Fetch -  trotzdem gefundene Einträge speichern
        cancelled_early = cancel_event.is_set() or job_service.is_cancelled(job_id)

        # ─── Phase 4: Rest-Einträge speichern (was Batch nicht erwischt hat) ───
        # all_entries enthält nur noch die nicht-batch-gespeicherten Entries
        remaining = all_entries
        del all_entries  # Referenz freigeben
        total_to_save = len(remaining)
        batch_ins = scan_state["batch_inserted"]
        batch_upd = scan_state["batch_updated"]
        batch_errs = scan_state["batch_errors"]
        already_saved = scan_state["saved_idx"]
        total_entries = already_saved + total_to_save  # Gesamtzahl

        if cancelled_early:
            summary = f"Abbruch -  speichere {total_entries} gefundene Einträge…"
            await job_service.progress(job_id, 0.70, summary)

        if total_to_save > 0:
            await job_service.progress(
                job_id, 0.70,
                f"Speichere Rest: {total_to_save} Einträge… ({already_saved} bereits gesichert)"
            )

        # Rest speichern
        inserted = batch_ins
        updated = batch_upd
        entry_errors = batch_errs
        for i, v in enumerate(remaining):
            # Abbruch-Check alle 100 Einträge
            if i % 100 == 0 and not cancelled_early and job_service.is_cancelled(job_id):
                await job_service.progress(job_id, 0, f"Abgebrochen bei {i}/{total_to_save} Einträgen")
                job_service.clear_cancel(job_id)
                return {"total": total_entries, "saved": already_saved + i, "cancelled": True}

            try:
                cursor = await db.execute(
                    """INSERT OR IGNORE INTO rss_entries
                       (video_id, channel_id, title, published, thumbnail_url,
                        duration, views, description, video_type, keywords, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')""",
                    (v["video_id"], channel_id, v.get("title"),
                     v.get("published"), v.get("thumbnail_url"),
                     v.get("duration"), v.get("views"),
                     (v.get("description") or "")[:5000],
                     v.get("video_type", "video"),
                     json.dumps(v.get("keywords", [])))
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
                            thumbnail_url = COALESCE(?, thumbnail_url),
                            video_type = COALESCE(?, video_type),
                            keywords = CASE WHEN ? != '[]' THEN ? ELSE keywords END
                           WHERE video_id = ? AND channel_id = ?""",
                        (v.get("duration"), v.get("views"),
                         v.get("description"), v.get("description"),
                         (v.get("description") or "")[:5000],
                         v.get("title"), v.get("thumbnail_url"),
                         v.get("video_type"),
                         json.dumps(v.get("keywords", [])),
                         json.dumps(v.get("keywords", [])),
                         v["video_id"], channel_id)
                    )
                    updated += 1
            except Exception as e:
                entry_errors += 1
                if entry_errors <= 5:
                    logger.warning(f"Eintrag {v.get('video_id')} Fehler: {e}")

            if i % 25 == 0 and total_to_save > 0:
                save_pct = 0.70 + (i / total_to_save) * 0.28
                await job_service.progress(
                    job_id, save_pct,
                    f"Speichere: {inserted} neu, {updated} aktualisiert ({already_saved + i + 1}/{total_entries})",
                    metadata={"save_current": already_saved + i + 1, "save_total": total_entries}
                )

        # ─── Kanal-Metadaten in subscriptions aktualisieren ───
        now = now_sqlite()
        updates = ["last_scanned = ?", "video_count = ?", "shorts_count = ?", "live_count = ?"]
        params = [now, phase_counts.get("video", 0), phase_counts.get("short", 0), phase_counts.get("live", 0)]

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
            # Banner lokal cachen
            try:
                from app.config import BANNERS_DIR
                BANNERS_DIR.mkdir(parents=True, exist_ok=True)
                banner_dest = BANNERS_DIR / f"{channel_id}.jpg"
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(channel_meta["banner_url"])
                    if resp.status_code == 200 and len(resp.content) > 1000:
                        banner_dest.write_bytes(resp.content)
                        updates.append("banner_url = ?")
                        params.append(f"/api/subscriptions/banner/{channel_id}")
                        logger.info(f"Banner gecacht: {channel_id}")
                    else:
                        updates.append("banner_url = ?")
                        params.append(channel_meta["banner_url"])
            except Exception as e:
                logger.warning(f"Banner-Cache fehlgeschlagen: {e}")
                updates.append("banner_url = ?")
                params.append(channel_meta["banner_url"])
        if channel_meta.get("channel_tags"):
            updates.append("channel_tags = ?")
            params.append(json.dumps(sanitize_tags(channel_meta["channel_tags"])))

        params.append(channel_id)
        await db.execute(
            f"UPDATE subscriptions SET {', '.join(updates)} WHERE channel_id = ?",
            tuple(params)
        )

        # ─── Ergebnis ────────────────────────────────────
        result_parts = []
        if phase_counts["video"]:
            result_parts.append(f"{phase_counts['video']} Videos")
        if phase_counts["short"]:
            result_parts.append(f"{phase_counts['short']} Shorts")
        if phase_counts["live"]:
            result_parts.append(f"{phase_counts['live']} Live")
        result_parts.append(f"({inserted} neu, {updated} aktualisiert)")

        error_parts = []
        for phase, errs in scan_errors.items():
            if errs:
                error_parts.append(f"{phase}: {errs[0][:80]}")
        if entry_errors > 0:
            error_parts.append(f"{entry_errors} DB-Fehler")

        result_msg = " | ".join(result_parts)
        if cancelled_early:
            result_msg = f"[Abgebrochen] {result_msg}"
        if error_parts:
            result_msg += f" [WARN] {'; '.join(error_parts)}"

        if cancelled_early:
            await job_service.progress(job_id, 1.0, result_msg)
            await db.execute(
                "UPDATE jobs SET status = 'cancelled', completed_at = ? WHERE id = ?",
                (now_sqlite(), job_id)
            )
            job_service.clear_cancel(job_id)
            logger.info(f"Kanal-Scan {channel_name} abgebrochen, Teildaten gespeichert: {result_msg}")
        else:
            await job_service.complete(job_id, result_msg)
            job_service.clear_cancel(job_id)
            logger.info(f"Kanal-Scan {channel_name}: {result_msg}")

        return {
            "total": total_entries, "new": inserted, "updated": updated,
            "errors": entry_errors, "channel_id": channel_id,
            "cancelled": cancelled_early,
            "phase_counts": phase_counts, "scan_errors": scan_errors,
            "channel_meta": {
                "banner_url": channel_meta.get("banner_url"),
                "channel_tags": channel_meta.get("channel_tags", []),
                "subscriber_count": channel_meta.get("subscriber_count"),
            },
        }

    except Exception as e:
        scan_state["done"] = True
        tracker.cancel()
        try:
            await tracker
        except asyncio.CancelledError:
            pass
        rate_limiter.error("channel_scan", str(e)[:200])
        await job_service.fail(job_id, str(e)[:300])
        job_service.clear_cancel(job_id)
        raise
    finally:
        # Speicher freigeben nach schwerem Scan
        import gc; gc.collect()

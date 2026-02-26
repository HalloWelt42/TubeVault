"""
TubeVault -  RSS Service v1.5.54
YouTube RSS Feed Polling + Channel Scan (Videos/Shorts/Live)
Phasen-Fortschritt, Abbruch-Unterstützung, Fehler-Transparenz
© HalloWelt42 -  Private Nutzung

Strategie für 800+ Abos:
- Feeds in Batches, gestaffeltes Polling über 24h verteilt
- Nachts: 1 Feed alle 30s (sanft, ~2880 Feeds/24h = reicht für 800)
- Tags: RSS = XML Feeds (harmlos), pytubefix = Scraping (gefährlich)
- Error-Backoff: fehlerhafte Feeds zunehmend seltener prüfen
- Auto-Download: max 20/Tag, kein Spam-Download
- Resume: abgebrochene Avatar-Jobs beim Start weitermachen
- KEIN automatischer pytubefix-Massen-Call, NUR auf User-Klick
"""

import asyncio
import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

import httpx

from app.config import AVATARS_DIR, RSS_THUMBS_DIR
from app.utils.file_utils import now_sqlite, past_sqlite
from app.database import db
from app.services.job_service import job_service
from app.services.rate_limiter import rate_limiter
from app.services.channel_scanner import fetch_all_channel_videos as _scan_channel

# YouTube RSS Feed URLs
# Undokumentierte Playlist-Prefixe für typ-getrennte Feeds:
# UC → UULF (nur Videos), UUSH (nur Shorts), UULV (nur Livestreams)
# Quelle: https://blog.amen6.com/blog/2025/01/no-shorts-please-hidden-youtube-rss-feed-urls/

logger = logging.getLogger(__name__)

YT_RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
YT_RSS_TYPED_URL = "https://www.youtube.com/feeds/videos.xml?playlist_id={playlist_id}"
ATOM_NS = "{http://www.w3.org/2005/Atom}"
YT_NS = "{http://www.youtube.com/xml/schemas/2015}"
MEDIA_NS = "{http://search.yahoo.com/mrss/}"

_executor = ThreadPoolExecutor(max_workers=2)

# Auto-Download: max pro Tag
AUTO_DL_DAILY_LIMIT = 20


class RSSService:
    """YouTube RSS Feed Manager -  produktionsreif."""

    def __init__(self):
        self._running = False
        self._polling = False  # Lock: verhindert parallele Tick-Ausführung
        self._auto_dl_today: int = 0
        self._auto_dl_date: str = ""
        # Scheduler-Status (für Frontend)
        self._last_checked_channel: str = ""
        self._last_checked_at: str = ""
        self._feeds_checked_cycle: int = 0
        self._feeds_pending: int = 0

    # ─── Worker Lifecycle ─────────────────────────────────

    async def start_worker(self):
        """RSS-Service initialisieren (kein Background-Loop mehr, Cron übernimmt)."""
        self._running = True
        logger.info("RSS Service bereit -  Feed-Checks werden per Cron ausgelöst")

    async def stop_worker(self):
        """RSS-Service stoppen."""
        self._running = False
        logger.info("RSS Service gestoppt")

    # ─── Tick-basiertes Feed-Polling ───────────────────────
    #
    # System-Cron ruft alle 5 Min /api/subscriptions/tick auf.
    # Backend entscheidet anhand check_interval pro Feed ob gepollt wird.
    #

    async def tick(self, max_feeds: int = 20) -> dict:
        """Vom System-Cron aufgerufen: Fällige Feeds prüfen.
        
        Cron = dummer Anstoß (alle 5 Min). Backend entscheidet intern
        anhand von check_interval pro Feed ob gepollt wird.
        
        Returns: Zusammenfassung des Durchlaufs + next_due_in_seconds.
        """
        # Parallele Ausführung verhindern
        if self._polling:
            logger.info("[TICK] Übersprungen -  vorheriger Durchlauf läuft noch")
            return {"status": "skipped", "message": "Vorheriger Durchlauf läuft noch"}
        
        self._polling = True
        try:
            return await self._do_tick(max_feeds)
        finally:
            self._polling = False

    async def _do_tick(self, max_feeds: int = 20) -> dict:
        """Eigentliche Tick-Logik (durch Lock geschützt)."""
        enabled = await self._get_setting("rss.enabled")
        if enabled != "true":
            return {"status": "disabled", "message": "RSS-Polling deaktiviert (rss.enabled=false)"}

        # Warten bis kein schwerer SYSTEM-Job aktiv ist
        # RSS + Downloads + Avatars laufen parallel, nur Channel-Scans/Cleanup blockieren
        idle = await job_service.wait_for_idle(
            label="rss_tick",
            exclude_types=["download", "rss_cycle", "avatar_fetch"],
            timeout=30,
        )
        if not idle:
            return {"status": "skipped", "message": "System-Job aktiv (Scan/Cleanup) -  RSS wartet"}

        # Fällige Feeds holen
        subs = await db.fetch_all(
            """SELECT * FROM subscriptions
               WHERE enabled = 1
               AND (last_checked IS NULL
                    OR last_checked < datetime('now', '-' || check_interval || ' seconds'))
               ORDER BY last_checked ASC NULLS FIRST, error_count ASC
               LIMIT ?""",
            (max_feeds,)
        )

        if not subs:
            # Nichts fällig — nächsten fälligen Feed berechnen
            self._feeds_pending = 0
            next_due = await self._next_due_seconds()
            return {
                "status": "idle",
                "message": "Keine fälligen Feeds",
                "checked": 0,
                "new_videos": 0,
                "next_due_in_seconds": next_due,
            }

        subs = [dict(s) for s in subs]
        total_pending = await db.fetch_val(
            """SELECT COUNT(*) FROM subscriptions WHERE enabled = 1
               AND (last_checked IS NULL
                    OR last_checked < datetime('now', '-' || check_interval || ' seconds'))"""
        ) or 0
        self._feeds_pending = total_pending

        # Job erstellen (sichtbar im Frontend) -  RSS hat höhere Priorität als Downloads
        job = await job_service.create(
            job_type="rss_cycle",
            title=f"RSS-Tick ({len(subs)}/{total_pending} fällig)",
            description=f"Tick: {len(subs)} Feeds werden geprüft",
            metadata={"trigger": "tick", "batch_size": len(subs), "total_pending": total_pending},
            priority=8,
        )
        await job_service.start(job["id"])

        total_new = 0
        errors = 0
        default_interval = int(await self._get_setting("rss.interval") or 1800)
        max_interval = 604800  # 7 Tage

        for i, sub in enumerate(subs):
            try:
                await rate_limiter.acquire("rss")
                new_count = await self._poll_single_feed(sub)
                total_new += new_count
                rate_limiter.success("rss")

                # Scheduler-State aktualisieren
                self._last_checked_channel = sub.get("channel_name") or sub["channel_id"]
                self._last_checked_at = now_sqlite()
                self._feeds_checked_cycle += 1

                # ─── Adaptives Interval ───
                current_interval = sub.get("check_interval", default_interval)
                if sub.get("error_count", 0) > 0:
                    # Fehler-Serie beendet → Error-Count reset, Interval beibehalten
                    await db.execute(
                        "UPDATE subscriptions SET error_count = 0, last_error = NULL WHERE id = ?",
                        (sub["id"],)
                    )

                if new_count > 0:
                    # Neue Videos → zurück auf Basis-Interval
                    await db.execute(
                        "UPDATE subscriptions SET check_interval = ? WHERE id = ?",
                        (default_interval, sub["id"])
                    )
                    if current_interval > default_interval:
                        logger.info(
                            f"[ADAPTIVE] {sub.get('channel_name', sub['channel_id'])}: "
                            f"{new_count} neue Videos → Interval {current_interval//60}min → {default_interval//60}min"
                        )
                else:
                    # Keine neuen Videos → Interval verdoppeln (max 7 Tage)
                    new_interval = min(current_interval * 2, max_interval)
                    if new_interval != current_interval:
                        await db.execute(
                            "UPDATE subscriptions SET check_interval = ? WHERE id = ?",
                            (new_interval, sub["id"])
                        )
                        logger.debug(
                            f"[ADAPTIVE] {sub.get('channel_name', sub['channel_id'])}: "
                            f"Keine neuen Videos → Interval {current_interval//60}min → {new_interval//60}min"
                        )

            except Exception as e:
                errors += 1
                rate_limiter.error("rss", str(e)[:200])
                error_count = sub.get("error_count", 0) + 1
                error_msg = str(e)[:500]

                # 404 = Kanal evtl. gelöscht/umgezogen → starkes Backoff, aber NICHT deaktivieren
                is_404 = "404" in error_msg
                if is_404:
                    new_interval = min(86400, 21600 * error_count)  # 6h, 12h, 24h max
                    await db.execute(
                        """UPDATE subscriptions SET
                           error_count = ?, last_error = ?, check_interval = ?,
                           last_checked = ?
                           WHERE id = ?""",
                        (error_count,
                         f"[404] Feed nicht erreichbar ({error_count}x) -  nächster Versuch in {new_interval//3600}h",
                         new_interval, now_sqlite(), sub["id"])
                    )
                    logger.warning(
                        f"RSS 404: {sub.get('channel_name', sub['channel_id'])} "
                        f"– Versuch {error_count}, nächstes Check in {new_interval//3600}h"
                    )
                else:
                    new_interval = min(sub.get("check_interval", 1800) * 2, 86400)
                    await db.execute(
                        """UPDATE subscriptions SET
                           error_count = ?, last_error = ?, check_interval = ?
                           WHERE id = ?""",
                        (error_count, error_msg, new_interval, sub["id"])
                    )
                logger.warning(f"RSS Cron-Feed Fehler {sub['channel_id']}: {e}")

            # Fortschritt
            if (i + 1) % 5 == 0 or i == len(subs) - 1:
                try:
                    await job_service.progress(
                        job["id"],
                        (i + 1) / len(subs),
                        f"{i + 1}/{len(subs)} Feeds, {total_new} neu, {errors} Fehler"
                    )
                except Exception:
                    pass

        # Job abschließen
        result_msg = f"{total_new} neue Videos, {len(subs)} Feeds geprüft, {errors} Fehler"
        await job_service.complete(job["id"], result_msg)
        logger.info(f"RSS Tick: {result_msg} (noch {total_pending - len(subs)} fällig)")

        # Verbleibende fällige Feeds + nächster fälliger
        remaining = await db.fetch_val(
            """SELECT COUNT(*) FROM subscriptions WHERE enabled = 1
               AND (last_checked IS NULL
                    OR last_checked < datetime('now', '-' || check_interval || ' seconds'))"""
        ) or 0
        self._feeds_pending = remaining

        total_enabled = await db.fetch_val(
            "SELECT COUNT(*) FROM subscriptions WHERE enabled = 1"
        ) or 0
        skipped = total_enabled - len(subs)
        next_due = await self._next_due_seconds()

        return {
            "status": "completed",
            "checked": len(subs),
            "skipped": max(0, skipped),
            "new_videos": total_new,
            "errors": errors,
            "remaining_pending": remaining,
            "next_due_in_seconds": next_due,
            "message": result_msg,
        }

    # ─── Einzelner Feed ──────────────────────────────────

    async def _next_due_seconds(self) -> int | None:
        """Sekunden bis der nächste Feed fällig ist. None wenn keine Feeds."""
        row = await db.fetch_one(
            """SELECT MIN(
                 MAX(0, CAST(
                   (julianday(last_checked) + (check_interval / 86400.0) - julianday('now')) * 86400
                 AS INTEGER))
               ) AS next_sec
               FROM subscriptions
               WHERE enabled = 1 AND last_checked IS NOT NULL"""
        )
        if row and row["next_sec"] is not None:
            return max(0, int(row["next_sec"]))
        # Feeds ohne last_checked = sofort fällig
        has_unchecked = await db.fetch_val(
            "SELECT COUNT(*) FROM subscriptions WHERE enabled = 1 AND last_checked IS NULL"
        )
        return 0 if has_unchecked else None

    async def _poll_single_feed(self, sub: dict) -> int:
        """Einzelnen RSS-Feed abrufen, parsen, neue Videos speichern.
        
        Nutzt typ-getrennte YouTube-Feeds (UUSH/UULV) statt
        pro-Video HTTP-Requests für die Klassifizierung.
        """
        channel_id = sub["channel_id"]

        # Ungültige channel_ids überspringen (z.B. URLs statt IDs)
        if not channel_id or not channel_id.startswith("UC") or len(channel_id) != 24:
            logger.warning(f"Ungültige channel_id übersprungen: {channel_id[:60]}… -  deaktiviere")
            await db.execute(
                "UPDATE subscriptions SET enabled = 0, last_error = ? WHERE id = ?",
                (f"Ungültige channel_id: {channel_id[:100]}", sub["id"])
            )
            return 0

        url = YT_RSS_URL.format(channel_id=channel_id)

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        root = ET.fromstring(resp.text)
        entries = root.findall(f"{ATOM_NS}entry")

        # Kanalname updaten wenn nötig
        feed_title = root.findtext(f"{ATOM_NS}title", "")
        if feed_title and (not sub.get("channel_name") or sub["channel_name"] == sub["channel_id"]):
            await db.execute(
                "UPDATE subscriptions SET channel_name = ? WHERE id = ?",
                (feed_title, sub["id"])
            )

        now = now_sqlite()
        max_age = int(await self._get_setting("rss.max_age_days") or 90)
        cutoff = past_sqlite(days=max_age)

        # Typ-Lookup: UUSH (Shorts) + UULV (Live) Feeds parallel abrufen
        auto_classify = await self._get_setting("feed.auto_classify")
        if auto_classify != "false":
            short_ids, live_ids = await self._fetch_typed_video_ids(channel_id)
        else:
            short_ids, live_ids = set(), set()

        new_count = 0
        for entry in entries:
            video_id = entry.findtext(f"{YT_NS}videoId", "")
            if not video_id:
                continue

            title = entry.findtext(f"{ATOM_NS}title", "")
            published = entry.findtext(f"{ATOM_NS}published", "")

            if published and published < cutoff:
                continue

            # Thumbnail
            thumb_url = None
            media_group = entry.find(f"{MEDIA_NS}group")
            if media_group is not None:
                thumb_el = media_group.find(f"{MEDIA_NS}thumbnail")
                if thumb_el is not None:
                    thumb_url = thumb_el.get("url")

            # Video-Typ aus den typ-getrennten Feeds bestimmen
            if video_id in short_ids:
                video_type = "short"
            elif video_id in live_ids:
                video_type = "live"
            else:
                video_type = "video"

            try:
                await db.execute(
                    """INSERT INTO rss_entries (video_id, channel_id, title, published, thumbnail_url, video_type)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (video_id, channel_id, title, published, thumb_url, video_type)
                )
                new_count += 1

                # Thumbnail lokal cachen (non-blocking)
                if thumb_url:
                    try:
                        await self._cache_rss_thumbnail(video_id, thumb_url)
                    except Exception:
                        pass

                # Auto-Download wenn aktiviert + Tageslimit nicht erreicht
                if sub.get("auto_download"):
                    await self._auto_queue_video(video_id, sub)

            except Exception:
                pass  # UNIQUE constraint = bereits bekannt

        # Subscription aktualisieren
        await db.execute(
            """UPDATE subscriptions SET
               last_checked = ?,
               video_count = (SELECT COUNT(*) FROM rss_entries WHERE channel_id = ?)
               WHERE id = ?""",
            (now, channel_id, sub["id"])
        )

        # Neuestes Video-Datum
        if entries:
            latest = max(
                (entry.findtext(f"{ATOM_NS}published", "") for entry in entries),
                default=""
            )
            if latest:
                await db.execute(
                    "UPDATE subscriptions SET last_video_date = ? WHERE id = ?",
                    (latest, sub["id"])
                )

        if new_count > 0:
            logger.info(f"RSS: {new_count} neue Videos von {sub.get('channel_name', channel_id)}")

        return new_count

    # ─── Typ-getrennte RSS-Feeds (UUSH/UULV) ──────────────

    @staticmethod
    def _channel_to_playlist_id(channel_id: str, prefix: str) -> str:
        """UC-Channel-ID in Playlist-ID umwandeln (UC → UULF/UUSH/UULV)."""
        if channel_id.startswith("UC"):
            return prefix + channel_id[2:]
        return channel_id

    async def _fetch_typed_video_ids(self, channel_id: str) -> tuple[set, set]:
        """UUSH- und UULV-Feeds parallel abrufen, Video-IDs als Sets zurückgeben.
        
        Returns: (short_ids: set, live_ids: set)
        Fehler werden leise geschluckt (leere Sets bei Fehler).
        """
        short_ids = set()
        live_ids = set()

        async def _fetch_feed_ids(prefix: str) -> set:
            playlist_id = self._channel_to_playlist_id(channel_id, prefix)
            url = YT_RSS_TYPED_URL.format(playlist_id=playlist_id)
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        return set()
                    root = ET.fromstring(resp.text)
                    return {
                        entry.findtext(f"{YT_NS}videoId", "")
                        for entry in root.findall(f"{ATOM_NS}entry")
                    } - {""}
            except Exception:
                return set()

        try:
            short_ids, live_ids = await asyncio.gather(
                _fetch_feed_ids("UUSH"),
                _fetch_feed_ids("UULV"),
            )
        except Exception as e:
            logger.debug(f"Typed-Feed Fehler für {channel_id}: {e}")

        return short_ids, live_ids

    # ─── Auto-Download (limitiert) ───────────────────────

    async def _auto_queue_video(self, video_id: str, sub: dict):
        """Video automatisch zur Queue -  mit Tageslimit."""
        # Tageslimit prüfen
        today = datetime.now().strftime("%Y-%m-%d")
        if self._auto_dl_date != today:
            self._auto_dl_date = today
            self._auto_dl_today = 0

        limit = int(await self._get_setting("rss.auto_dl_daily_limit") or AUTO_DL_DAILY_LIMIT)
        if self._auto_dl_today >= limit:
            logger.debug(f"Auto-DL Tageslimit ({limit}) erreicht, {video_id} übersprungen")
            return

        # Duplikat-Checks
        existing = await db.fetch_one("SELECT id FROM videos WHERE id = ?", (video_id,))
        if existing:
            return

        in_queue = await db.fetch_one(
            "SELECT id FROM jobs WHERE type='download' AND json_extract(metadata, '$.video_id') = ? AND status IN ('queued', 'active', 'retry_wait', 'parked')",
            (video_id,)
        )
        if in_queue:
            return

        # Bereits fehlgeschlagen? Nicht erneut versuchen (manueller Unpark nötig)
        was_parked = await db.fetch_one(
            "SELECT id FROM jobs WHERE type='download' AND json_extract(metadata, '$.video_id') = ? AND status = 'error'",
            (video_id,)
        )
        if was_parked:
            return

        quality = sub.get("download_quality", "720p")
        audio_only = bool(sub.get("audio_only", False))
        url = f"https://www.youtube.com/watch?v={video_id}"

        # Titel aus RSS-Entries holen
        rss_title = await db.fetch_val(
            "SELECT title FROM rss_entries WHERE video_id = ?", (video_id,))
        display_title = rss_title[:256] if rss_title else video_id

        # Download über job_service erstellen (nicht download_queue)
        from app.services.job_service import job_service
        await job_service.create(
            job_type="download",
            title=display_title,
            description="Auto-Download via RSS",
            metadata={
                "video_id": video_id, "url": url,
                "download_options": {
                    "quality": quality, "format": "mp4",
                    "download_thumbnail": True, "audio_only": audio_only,
                },
                "retry_count": 0, "max_retries": 3,
            },
            priority=5,
        )
        await db.execute(
            "UPDATE rss_entries SET status = 'queued', auto_queued = 1 WHERE video_id = ?",
            (video_id,)
        )

        self._auto_dl_today += 1
        logger.info(f"Auto-DL queued: {video_id} ({self._auto_dl_today}/{limit} heute)")

    # ─── Abo-Management ──────────────────────────────────

    async def add_subscription(self, channel_id: str, auto_download: bool = False,
                               quality: str = None) -> dict:
        """Neues Abo hinzufügen. RSS für Info, Avatar per pytubefix (rate-limited)."""
        # Quality: explizit → Setting → Fallback
        if not quality:
            quality = await self._get_setting("rss.auto_quality") or "720p"
        # Schritt 1: Basisinfo per RSS (harmlos)
        await rate_limiter.acquire("rss")
        url = YT_RSS_URL.format(channel_id=channel_id)
        channel_name = channel_id
        channel_url = f"https://www.youtube.com/channel/{channel_id}"

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                root = ET.fromstring(resp.text)
                channel_name = root.findtext(f"{ATOM_NS}title", channel_id)
                for link in root.findall(f"{ATOM_NS}link"):
                    if link.get("rel") == "alternate":
                        channel_url = link.get("href", channel_url)
                        break
            rate_limiter.success("rss")
        except Exception as e:
            rate_limiter.error("rss", str(e)[:200])
            logger.warning(f"RSS-Info Fehler für {channel_id}: {e}")

        # Schritt 2: Avatar per pytubefix (rate-limited!)
        avatar_path = None
        try:
            await rate_limiter.acquire("avatar")
            avatar_path = await self._fetch_channel_avatar(channel_id)
            if avatar_path:
                rate_limiter.success("avatar")
            else:
                rate_limiter.error("avatar", str(e)[:200])
        except Exception as e:
            rate_limiter.error("avatar", str(e)[:200])
            logger.warning(f"Avatar-Fetch Fehler für {channel_id}: {e}")

        # Schritt 3: In DB speichern (check_interval aus Einstellung)
        default_interval = int(await self._get_setting("rss.interval") or 1800)
        cursor = await db.execute(
            """INSERT OR IGNORE INTO subscriptions
               (channel_id, channel_name, channel_url, avatar_path, auto_download, download_quality, check_interval)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (channel_id, channel_name, channel_url, avatar_path, auto_download, quality, default_interval)
        )

        if cursor.rowcount == 0:
            if avatar_path:
                await db.execute(
                    "UPDATE subscriptions SET avatar_path = ? WHERE channel_id = ? AND avatar_path IS NULL",
                    (avatar_path, channel_id)
                )
            row = await db.fetch_one("SELECT * FROM subscriptions WHERE channel_id = ?", (channel_id,))
            return dict(row) if row else {}

        sub_id = cursor.lastrowid
        logger.info(f"Abo: {channel_name} ({channel_id}), Avatar: {'OK' if avatar_path else '-'}")

        # Sofort ersten Feed-Check
        sub = await db.fetch_one("SELECT * FROM subscriptions WHERE id = ?", (sub_id,))
        if sub:
            asyncio.create_task(self._safe_poll(dict(sub)))

        return dict(sub) if sub else {"id": sub_id, "channel_id": channel_id}

    async def _safe_poll(self, sub: dict):
        """Poll mit Error-Handling (für create_task)."""
        try:
            await rate_limiter.acquire("rss")
            await self._poll_single_feed(sub)
        except Exception as e:
            logger.debug(f"Initial poll skip: {e}")

    async def _cache_rss_thumbnail(self, video_id: str, thumb_url: str) -> Optional[str]:
        """RSS-Thumbnail lokal cachen. Gibt lokalen Pfad zurück oder None."""
        if not thumb_url:
            return None
        try:
            RSS_THUMBS_DIR.mkdir(parents=True, exist_ok=True)
            dest = RSS_THUMBS_DIR / f"{video_id}.jpg"
            if dest.exists() and dest.stat().st_size > 0:
                return str(dest)
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(thumb_url)
                if resp.status_code == 200 and len(resp.content) > 500:
                    dest.write_bytes(resp.content)
                    return str(dest)
        except Exception as e:
            logger.debug(f"RSS-Thumb Cache fehlgeschlagen für {video_id}: {e}")
        return None

    async def backfill_missing_thumbnails(self):
        """Fehlende RSS-Thumbnails beim Start nachcachen (non-blocking)."""
        import asyncio
        await asyncio.sleep(15)  # Warte bis System bereit
        try:
            rows = await db.fetch_all(
                "SELECT video_id, thumbnail_url FROM rss_entries WHERE thumbnail_url IS NOT NULL")
            cached = 0
            for row in rows:
                dest = RSS_THUMBS_DIR / f"{row['video_id']}.jpg"
                if dest.exists() and dest.stat().st_size > 500:
                    continue
                try:
                    await self._cache_rss_thumbnail(row["video_id"], row["thumbnail_url"])
                    cached += 1
                    if cached % 50 == 0:
                        await asyncio.sleep(2)  # Rate-Limit
                except Exception:
                    pass
            if cached > 0:
                logger.info(f"[RSS-Thumbs] {cached} fehlende Thumbnails nachgecacht")
        except Exception as e:
            logger.warning(f"[RSS-Thumbs] Backfill Fehler: {e}")

    async def _fetch_channel_avatar(self, channel_id: str) -> Optional[str]:
        """Kanal-Avatar per pytubefix holen. Caller muss rate_limiter.acquire('avatar') machen."""
        loop = asyncio.get_event_loop()

        def _fetch():
            from pytubefix import Channel
            ch = Channel(f"https://www.youtube.com/channel/{channel_id}")
            thumb_url = getattr(ch, 'thumbnail_url', None)
            if not thumb_url:
                try:
                    for thumb in ch.initial_data.get('metadata', {}).get(
                        'channelMetadataRenderer', {}
                    ).get('avatar', {}).get('thumbnails', []):
                        thumb_url = thumb.get('url')
                        if thumb_url:
                            break
                except Exception:
                    pass
            return thumb_url, getattr(ch, 'channel_name', None)

        try:
            thumb_url, ch_name = await loop.run_in_executor(_executor, _fetch)

            if not thumb_url:
                return None

            AVATARS_DIR.mkdir(parents=True, exist_ok=True)
            avatar_file = AVATARS_DIR / f"{channel_id}.jpg"

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(thumb_url)
                resp.raise_for_status()
                avatar_file.write_bytes(resp.content)

            if ch_name:
                await db.execute(
                    "UPDATE subscriptions SET channel_name = ? WHERE channel_id = ? AND (channel_name = ? OR channel_name IS NULL)",
                    (ch_name, channel_id, channel_id)
                )

            return str(avatar_file)
        except Exception as e:
            logger.warning(f"Avatar fetch failed for {channel_id}: {e}")
            return None

    # ─── Batch-Import (nur RSS, kein pytubefix) ──────────

    async def add_subscriptions_batch(self, channel_ids: list[str],
                                      auto_download: bool = False) -> dict:
        """Batch-Import: nur RSS für Namen, Avatare DANACH einzeln im Hintergrund."""
        job = await job_service.create(
            job_type="import",
            title=f"Abo-Import ({len(channel_ids)} Kanäle)",
            description="Importiere Kanal-Abonnements per RSS",
        )
        await job_service.start(job["id"])

        added = 0
        skipped = 0
        new_ids = []

        for i, cid in enumerate(channel_ids):
            cid = cid.strip()
            if not cid or len(cid) < 10:
                skipped += 1
                continue

            try:
                await rate_limiter.acquire("rss")
                result = await self._add_subscription_fast(cid, auto_download=auto_download)
                if result.get("new"):
                    added += 1
                    new_ids.append(cid)
                    rate_limiter.success("rss")
                else:
                    skipped += 1
            except Exception as e:
                rate_limiter.error("rss", str(e)[:200])
                logger.warning(f"Abo-Import Fehler für {cid}: {e}")
                skipped += 1

            if i % 10 == 0:
                await job_service.progress(
                    job["id"],
                    (i + 1) / len(channel_ids),
                    f"{added} hinzugefügt, {skipped} übersprungen"
                )

        await job_service.complete(
            job["id"],
            f"{added} Abos importiert, {skipped} übersprungen"
        )

        # Avatare nachträglich im Hintergrund (rate-limited, resume-fähig)
        if new_ids:
            asyncio.create_task(self._fetch_avatars_background(new_ids))

        return {"added": added, "skipped": skipped, "total": len(channel_ids)}

    async def _add_subscription_fast(self, channel_id: str,
                                     auto_download: bool = False) -> dict:
        """Schnell-Import: nur RSS für Kanalname. Kein pytubefix."""
        channel_name = channel_id
        channel_url = f"https://www.youtube.com/channel/{channel_id}"

        try:
            url = YT_RSS_URL.format(channel_id=channel_id)
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                root = ET.fromstring(resp.text)
                channel_name = root.findtext(f"{ATOM_NS}title", channel_id)
                for link in root.findall(f"{ATOM_NS}link"):
                    if link.get("rel") == "alternate":
                        channel_url = link.get("href", channel_url)
                        break
        except Exception:
            pass

        cursor = await db.execute(
            """INSERT OR IGNORE INTO subscriptions
               (channel_id, channel_name, channel_url, auto_download)
               VALUES (?, ?, ?, ?)""",
            (channel_id, channel_name, channel_url, auto_download)
        )

        return {"new": cursor.rowcount > 0, "channel_id": channel_id}

    # ─── Avatar Background-Fetch (resume-fähig) ─────────

    async def _fetch_avatars_background(self, channel_ids: list[str]):
        """Avatare im Hintergrund laden -  rate-limited, resume-fähig."""
        job = await job_service.create(
            job_type="avatar_fetch",
            title=f"Avatare laden ({len(channel_ids)} Kanäle)",
            description="Lade Kanal-Avatare per pytubefix (rate-limited)",
            metadata={"channel_ids": channel_ids, "completed_index": 0},
        )
        await job_service.start(job["id"])

        loaded = 0
        for i, cid in enumerate(channel_ids):
            # Prüfen ob Avatar schon existiert
            existing = await db.fetch_one(
                "SELECT avatar_path FROM subscriptions WHERE channel_id = ? AND avatar_path IS NOT NULL",
                (cid,)
            )
            if existing and existing["avatar_path"]:
                loaded += 1
                continue

            try:
                await rate_limiter.acquire("avatar")
                avatar_path = await self._fetch_channel_avatar(cid)
                if avatar_path:
                    await db.execute(
                        "UPDATE subscriptions SET avatar_path = ? WHERE channel_id = ?",
                        (avatar_path, cid)
                    )
                    loaded += 1
                    rate_limiter.success("avatar")
                else:
                    rate_limiter.error("avatar", str(e)[:200])
            except Exception as e:
                rate_limiter.error("avatar", str(e)[:200])
                logger.debug(f"Avatar skip {cid}: {e}")

            # Resume-Info speichern
            if i % 5 == 0:
                await job_service.progress(
                    job["id"],
                    (i + 1) / len(channel_ids),
                    f"{loaded}/{i + 1} Avatare geladen"
                )
                await db.execute(
                    "UPDATE jobs SET metadata = ? WHERE id = ?",
                    (json.dumps({"channel_ids": channel_ids, "completed_index": i + 1}), job["id"])
                )

        await job_service.complete(job["id"], f"{loaded} von {len(channel_ids)} Avatare geladen")

    async def resume_avatar_jobs(self):
        """Beim Start: abgebrochene Avatar-Jobs fortsetzen."""
        stale_jobs = await db.fetch_all(
            """SELECT * FROM jobs WHERE type = 'avatar_fetch' AND status = 'active'
               ORDER BY created_at DESC"""
        )
        for job_row in stale_jobs:
            job = dict(job_row)
            meta = json.loads(job.get("metadata", "{}"))
            channel_ids = meta.get("channel_ids", [])
            completed = meta.get("completed_index", 0)
            remaining = channel_ids[completed:]
            if remaining:
                logger.info(f"Avatar-Job #{job['id']} fortsetzen: {len(remaining)} verbleibend")
                await job_service.progress(
                    job["id"], completed / len(channel_ids),
                    f"Fortgesetzt bei {completed}/{len(channel_ids)}"
                )
                asyncio.create_task(self._fetch_avatars_background(remaining))
            else:
                await job_service.complete(job["id"], "Fortgesetzt: alle Avatare geladen")

    # ─── Kanal komplett laden → channel_scanner.py ─────────────

    async def fetch_all_channel_videos(self, channel_id: str, job_id: int = None) -> dict:
        """Delegation an channel_scanner.py"""
        return await _scan_channel(channel_id, job_id=job_id)

    # ─── Abo CRUD ────────────────────────────────────────

    async def remove_subscription(self, sub_id: int):
        await db.execute("DELETE FROM rss_entries WHERE channel_id = (SELECT channel_id FROM subscriptions WHERE id = ?)", (sub_id,))
        await db.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))

    async def update_subscription(self, sub_id: int, updates: dict):
        import random
        allowed = {"auto_download", "download_quality", "audio_only", "category_id",
                    "check_interval", "enabled", "drip_enabled", "drip_count",
                    "drip_auto_archive", "suggest_exclude"}
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if not filtered:
            return

        # Drip aktiviert → erste Ausführungszeit würfeln
        if filtered.get("drip_enabled"):
            from datetime import datetime, timedelta
            tomorrow = datetime.now().replace(hour=0, minute=0, second=0) + timedelta(days=1)
            random_hour = random.randint(2, 9)
            random_minute = random.randint(0, 59)
            next_run = tomorrow.replace(hour=random_hour, minute=random_minute)
            filtered["drip_next_run"] = next_run.strftime("%Y-%m-%d %H:%M:%S")
        elif "drip_enabled" in filtered and not filtered["drip_enabled"]:
            filtered["drip_next_run"] = None

        set_clause = ", ".join(f"{k} = ?" for k in filtered)
        values = list(filtered.values()) + [sub_id]
        await db.execute(f"UPDATE subscriptions SET {set_clause} WHERE id = ?", values)

    async def get_subscriptions(self, page: int = 1, per_page: int = 50) -> dict:
        total = await db.fetch_val("SELECT COUNT(*) FROM subscriptions")
        offset = (page - 1) * per_page
        rows = await db.fetch_all(
            """SELECT s.*,
               (SELECT COUNT(*) FROM rss_entries WHERE channel_id = s.channel_id AND status = 'new' AND COALESCE(feed_status, 'active') = 'active') as new_videos,
               (SELECT COUNT(*) FROM rss_entries WHERE channel_id = s.channel_id) as rss_count,
               (SELECT COUNT(*) FROM videos WHERE channel_id = s.channel_id AND status = 'ready') as downloaded_count
               FROM subscriptions s
               ORDER BY s.channel_name ASC
               LIMIT ? OFFSET ?""",
            (per_page, offset)
        )
        return {
            "subscriptions": [dict(r) for r in rows],
            "total": total or 0,
            "page": page,
            "per_page": per_page,
        }


    # ─── (Shorts-Scan / Reclassify / cropdetect entfernt v1.6.21) ───


    async def get_new_videos(self, channel_id: str = None, channel_ids: str = None,
                             video_type: str = "all", video_types: str = None,
                             feed_tab: str = "active",
                             page: int = 1, per_page: int = 50,
                             keywords: str = None,
                             duration_min: int = None, duration_max: int = None) -> dict:
        """Feed-Videos mit Pagination, Mehrfach-Typ/Kanal/Tag-Filter und Feed-Status-Tabs.
        
        feed_tab: active | later | dismissed | archived | all
        keywords: Komma-getrennte Tags zum Filtern (OR-Verknuepfung)
        duration_min/max: Dauer-Filter in Sekunden
        """
        offset = (page - 1) * per_page

        # Shorts ausblenden wenn in Einstellungen aktiviert
        hide_shorts = await self._get_setting("feed.hide_shorts")

        # Typ-Filter: video_types (Komma-getrennt) hat Vorrang
        type_filter = ""
        type_params = []
        if video_types:
            vtypes = [v.strip() for v in video_types.split(",") if v.strip()]
            if vtypes:
                placeholders = ",".join("?" * len(vtypes))
                type_filter = f"AND COALESCE(r.video_type, 'video') IN ({placeholders})"
                type_params = vtypes
        elif video_type == "video":
            type_filter = "AND r.video_type = 'video'"
        elif video_type == "short":
            type_filter = "AND r.video_type = 'short'"
        elif video_type == "live":
            type_filter = "AND r.video_type = 'live'"
        elif video_type == "all" and hide_shorts == "true":
            type_filter = "AND r.video_type != 'short'"

        # Kanal-Filter: channel_ids (Komma-getrennt) hat Vorrang
        channel_filter = ""
        channel_params = []
        if channel_ids:
            ch_list = [c.strip() for c in channel_ids.split(",") if c.strip()]
            if ch_list:
                placeholders = ",".join("?" * len(ch_list))
                channel_filter = f"AND r.channel_id IN ({placeholders})"
                channel_params = ch_list
        elif channel_id:
            channel_filter = "AND r.channel_id = ?"
            channel_params = [channel_id]

        # Keyword/Tag-Filter (OR: mindestens einer der Tags muss enthalten sein)
        keyword_filter = ""
        keyword_params = []
        if keywords:
            kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
            if kw_list:
                conditions = []
                for kw in kw_list:
                    conditions.append("r.keywords LIKE ?")
                    keyword_params.append(f'%"{kw}"%')
                keyword_filter = f"AND ({' OR '.join(conditions)})"

        # Dauer-Filter
        duration_filter = ""
        duration_params = []
        if duration_min is not None:
            duration_filter += "AND r.duration >= ? "
            duration_params.append(duration_min)
        if duration_max is not None:
            duration_filter += "AND r.duration <= ? "
            duration_params.append(duration_max)

        # Feed-Status-Filter (ersetzt altes dismissed=0)
        status_filter = ""
        if feed_tab == "active":
            status_filter = "AND COALESCE(r.feed_status, 'active') = 'active'"
        elif feed_tab == "later":
            status_filter = "AND r.feed_status = 'later'"
        elif feed_tab == "dismissed":
            status_filter = "AND r.feed_status = 'dismissed'"
        elif feed_tab == "archived":
            status_filter = "AND r.feed_status = 'archived'"
        # feed_tab == "all" → kein Filter

        base_where = f"WHERE 1=1 {status_filter} {channel_filter} {type_filter} {keyword_filter} {duration_filter}"
        all_params = channel_params + type_params + keyword_params + duration_params

        # Total
        total = await db.fetch_val(
            f"""SELECT COUNT(*) FROM rss_entries r
                JOIN subscriptions s ON r.channel_id = s.channel_id
                {base_where}""",
            tuple(all_params)
        ) or 0

        # Typ-Counts (fuer Filter-Badges) -  basieren auf gleichem Status-Tab + Keyword-Filter
        type_counts = {}
        for vt, cond in [("video", "COALESCE(r.video_type, 'video') = 'video'"),
                         ("short", "r.video_type = 'short'"),
                         ("live", "r.video_type = 'live'")]:
            c = await db.fetch_val(
                f"""SELECT COUNT(*) FROM rss_entries r
                    JOIN subscriptions s ON r.channel_id = s.channel_id
                    WHERE 1=1 {status_filter} {channel_filter} {keyword_filter} {duration_filter} AND {cond}""",
                tuple(channel_params + keyword_params + duration_params)
            ) or 0
            type_counts[vt] = c

        # Tab-Counts (fuer Tab-Badges)
        tab_counts = {}
        for tab in ["active", "later", "dismissed", "archived"]:
            tc = await db.fetch_val(
                f"""SELECT COUNT(*) FROM rss_entries r
                    JOIN subscriptions s ON r.channel_id = s.channel_id
                    WHERE COALESCE(r.feed_status, 'active') = ?""",
                (tab,)
            ) or 0
            tab_counts[tab] = tc

        # Ergebnisse
        rows = await db.fetch_all(
            f"""SELECT r.*, s.channel_name, s.download_quality, s.audio_only,
                       v.status as video_status,
                       COALESCE(r.video_type, 'video') as video_type_safe
                FROM rss_entries r
                JOIN subscriptions s ON r.channel_id = s.channel_id
                LEFT JOIN videos v ON r.video_id = v.id
                {base_where}
                ORDER BY r.published DESC
                LIMIT ? OFFSET ?""",
            tuple(all_params + [per_page, offset])
        )

        return {
            "entries": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "per_page": per_page,
            "has_more": (page * per_page) < total,
            "type_counts": type_counts,
            "tab_counts": tab_counts,
            "feed_tab": feed_tab,
        }

    # ─── Feed-Status-Aktionen ─────────────────────────────────

    async def set_feed_status(self, entry_id: int, status: str):
        """Einzelnen Feed-Eintrag auf Status setzen (active/later/archived/dismissed)."""
        if status not in ("active", "later", "archived", "dismissed"):
            raise ValueError(f"Ungueltiger Feed-Status: {status}")
        await db.execute(
            "UPDATE rss_entries SET feed_status = ?, dismissed = ? WHERE id = ?",
            (status, 1 if status == "dismissed" else 0, entry_id)
        )

    async def set_feed_status_bulk(self, entry_ids: list[int], status: str):
        """Mehrere Feed-Eintraege auf Status setzen."""
        if status not in ("active", "later", "archived", "dismissed"):
            raise ValueError(f"Ungueltiger Feed-Status: {status}")
        if not entry_ids:
            return
        placeholders = ",".join("?" * len(entry_ids))
        await db.execute(
            f"UPDATE rss_entries SET feed_status = ?, dismissed = ? WHERE id IN ({placeholders})",
            (status, 1 if status == "dismissed" else 0, *entry_ids)
        )

    async def dismiss_entry(self, entry_id: int):
        """Rueckwaertskompatibel: Eintrag ausblenden."""
        await self.set_feed_status(entry_id, "dismissed")

    async def dismiss_all(self, channel_id: str = None):
        """Rueckwaertskompatibel: Alle als gelesen markieren."""
        if channel_id:
            await db.execute(
                "UPDATE rss_entries SET feed_status = 'dismissed', dismissed = 1 WHERE channel_id = ? AND feed_status = 'active'",
                (channel_id,)
            )
        else:
            await db.execute(
                "UPDATE rss_entries SET feed_status = 'dismissed', dismissed = 1 WHERE feed_status = 'active'"
            )

    async def restore_entry(self, entry_id: int):
        """Ausgeblendeten Eintrag wiederherstellen (Undo)."""
        await self.set_feed_status(entry_id, "active")

    async def set_all_status(self, from_status: str, to_status: str, channel_id: str = None):
        """Alle Eintraege von einem Status zum anderen verschieben."""
        if from_status not in ("active", "later", "archived", "dismissed"):
            return
        if to_status not in ("active", "later", "archived", "dismissed"):
            return
        params = [to_status, 1 if to_status == "dismissed" else 0, from_status]
        ch_filter = ""
        if channel_id:
            ch_filter = " AND channel_id = ?"
            params.append(channel_id)
        await db.execute(
            f"UPDATE rss_entries SET feed_status = ?, dismissed = ? WHERE feed_status = ?{ch_filter}",
            tuple(params)
        )

    async def trigger_poll_now(self) -> dict:
        """Sofortigen RSS-Check für ALLE aktiven Feeds (manuell, ignoriert Intervalle)."""
        subs = await db.fetch_all(
            """SELECT * FROM subscriptions WHERE enabled = 1
               ORDER BY last_checked ASC NULLS FIRST"""
        )
        if subs:
            asyncio.create_task(self._process_batch_now([dict(s) for s in subs]))
            return {"triggered": True, "feed_count": len(subs)}
        return {"triggered": False, "feed_count": 0}

    async def _process_batch_now(self, subs: list[dict]):
        """Manueller Batch-Check mit Job-Sichtbarkeit."""
        job = await job_service.create(
            job_type="rss_cycle",
            title=f"RSS-Check ({len(subs)} Feeds)",
            description="Manuell ausgelöster RSS-Check",
            priority=8,
        )
        await job_service.start(job["id"])

        total_new = 0
        for i, sub in enumerate(subs):
            try:
                await rate_limiter.acquire("rss")
                new_count = await self._poll_single_feed(sub)
                total_new += new_count
                rate_limiter.success("rss")
            except Exception as e:
                rate_limiter.error("rss", str(e)[:200])
                logger.error(f"RSS Feed Fehler {sub['channel_id']}: {e}")

            await job_service.progress(
                job["id"],
                (i + 1) / len(subs),
                f"{i + 1}/{len(subs)} Feeds, {total_new} neue Videos"
            )

        await job_service.complete(
            job["id"],
            f"{total_new} neue Videos in {len(subs)} Feeds gefunden"
        )

    async def background_refresh(self):
        """Periodischer leichter Re-Scan fuer Kanaele die laenger nicht gescannt wurden.
        Wird vom Scheduler aufgerufen wenn feed.auto_refresh aktiviert ist.
        """
        enabled = await self._get_setting("feed.auto_refresh")
        if enabled != "true":
            return {"skipped": True, "reason": "auto_refresh deaktiviert"}

        interval_days = int(await self._get_setting("feed.refresh_interval_days") or 7)
        cutoff = past_sqlite(days=interval_days)

        # Kanaele die laenger als X Tage nicht gescannt wurden
        stale_subs = await db.fetch_all(
            """SELECT channel_id, channel_name FROM subscriptions
               WHERE enabled = 1 AND (last_scanned IS NULL OR last_scanned < ?)
               ORDER BY last_scanned ASC NULLS FIRST
               LIMIT 3""",
            (cutoff,)
        )

        if not stale_subs:
            return {"refreshed": 0, "reason": "Alle Kanaele aktuell"}

        refreshed = 0
        for sub in stale_subs:
            try:
                ch_id = sub["channel_id"]
                ch_name = sub["channel_name"] or ch_id
                logger.info(f"Background-Refresh: {ch_name}")
                # Vollstaendigen Channel-Scan als Job starten
                await self.scan_channel(ch_id, ch_name)
                refreshed += 1
                # Pause zwischen Scans gegen Rate-Limiting
                await asyncio.sleep(5)
            except Exception as e:
                logger.warning(f"Background-Refresh fehlgeschlagen fuer {sub['channel_id']}: {e}")

        return {"refreshed": refreshed, "total_stale": len(stale_subs)}

    async def get_stats(self) -> dict:
        total_subs = await db.fetch_val("SELECT COUNT(*) FROM subscriptions") or 0
        enabled_subs = await db.fetch_val("SELECT COUNT(*) FROM subscriptions WHERE enabled = 1") or 0
        new_videos = await db.fetch_val("SELECT COUNT(*) FROM rss_entries WHERE status = 'new' AND COALESCE(feed_status, 'active') = 'active'") or 0
        total_entries = await db.fetch_val("SELECT COUNT(*) FROM rss_entries") or 0
        auto_subs = await db.fetch_val("SELECT COUNT(*) FROM subscriptions WHERE auto_download = 1") or 0
        error_subs = await db.fetch_val("SELECT COUNT(*) FROM subscriptions WHERE error_count > 0") or 0
        checked_1h = await db.fetch_val(
            "SELECT COUNT(*) FROM subscriptions WHERE last_checked > datetime('now', '-1 hour')"
        ) or 0
        return {
            "total_subscriptions": total_subs,
            "enabled_subscriptions": enabled_subs,
            "auto_download_subscriptions": auto_subs,
            "error_subscriptions": error_subs,
            "new_videos": new_videos,
            "total_entries": total_entries,
            "checked_last_hour": checked_1h,
            "auto_dl_today": self._auto_dl_today,
            "auto_dl_limit": AUTO_DL_DAILY_LIMIT,
        }

    async def get_scheduler_status(self) -> dict:
        """Aktueller Scheduler-Status für Frontend-Anzeige -  volle Transparenz."""
        # Gesamtstatistiken
        total = await db.fetch_val("SELECT COUNT(*) FROM subscriptions") or 0
        enabled = await db.fetch_val("SELECT COUNT(*) FROM subscriptions WHERE enabled = 1") or 0
        checked = await db.fetch_val("SELECT COUNT(*) FROM subscriptions WHERE last_checked IS NOT NULL") or 0
        unchecked = await db.fetch_val("SELECT COUNT(*) FROM subscriptions WHERE last_checked IS NULL AND enabled = 1") or 0
        with_errors = await db.fetch_val("SELECT COUNT(*) FROM subscriptions WHERE error_count > 0") or 0
        disabled = total - enabled

        # Fällige Feeds
        pending = await db.fetch_val(
            """SELECT COUNT(*) FROM subscriptions
               WHERE enabled = 1
               AND (last_checked IS NULL
                    OR last_checked < datetime('now', '-' || check_interval || ' seconds'))"""
        ) or 0

        # RSS Entries Statistik
        total_entries = await db.fetch_val("SELECT COUNT(*) FROM rss_entries") or 0
        channels_with_entries = await db.fetch_val("SELECT COUNT(DISTINCT channel_id) FROM rss_entries") or 0
        channels_without = enabled - channels_with_entries if enabled > channels_with_entries else 0

        # Interval-Verteilung
        interval_stats = await db.fetch_all(
            """SELECT check_interval, COUNT(*) as cnt
               FROM subscriptions WHERE enabled = 1
               GROUP BY check_interval ORDER BY check_interval"""
        )

        # Nächste fällige Feeds
        upcoming = await db.fetch_all(
            """SELECT channel_id, channel_name, last_checked, check_interval, error_count,
                      datetime(last_checked, '+' || check_interval || ' seconds') as next_check
               FROM subscriptions
               WHERE enabled = 1 AND last_checked IS NOT NULL
               ORDER BY next_check ASC
               LIMIT 5"""
        )

        # Letzte Fehler
        recent_errors = await db.fetch_all(
            """SELECT channel_name, error_count, last_error, check_interval
               FROM subscriptions WHERE error_count > 0
               ORDER BY error_count DESC LIMIT 5"""
        )

        # Settings die den Scanner beeinflussen
        max_age = await self._get_setting("rss.max_age_days") or "90"
        interval = await self._get_setting("rss.interval") or "1800"
        rss_enabled = await self._get_setting("rss.enabled") or "true"
        auto_dl = await self._get_setting("rss.auto_download") or "false"
        daily_limit = await self._get_setting("rss.auto_dl_daily_limit") or "20"

        # Letzter Cron-Lauf aus Jobs-Tabelle
        last_cron_job = await db.fetch_one(
            """SELECT id, status, description, result, started_at, completed_at
               FROM jobs WHERE type = 'rss_cycle'
               ORDER BY created_at DESC LIMIT 1"""
        )

        return {
            "mode": "cron",
            "running": self._running,
            "rss_enabled": rss_enabled == "true",
            "last_checked_channel": self._last_checked_channel,
            "last_checked_at": self._last_checked_at,
            "feeds_pending": pending,
            "feeds_checked_total": self._feeds_checked_cycle,
            "last_cron_job": dict(last_cron_job) if last_cron_job else None,
            # Abo-Statistiken
            "subscriptions": {
                "total": total,
                "enabled": enabled,
                "disabled": disabled,
                "checked": checked,
                "unchecked": unchecked,
                "with_errors": with_errors,
                "channels_with_entries": channels_with_entries,
                "channels_without_entries": channels_without,
            },
            # RSS Entries
            "entries": {
                "total": total_entries,
            },
            # Auto-Download Status
            "auto_download": {
                "enabled": auto_dl == "true",
                "today_count": self._auto_dl_today,
                "daily_limit": int(daily_limit),
            },
            # Aktive Einstellungen
            "active_settings": {
                "max_age_days": int(max_age),
                "default_interval": int(interval),
                "rss_enabled": rss_enabled == "true",
            },
            # Check-Intervall Verteilung
            "interval_distribution": [
                {"interval": r["check_interval"], "count": r["cnt"]} for r in interval_stats
            ],
            "upcoming": [dict(u) for u in upcoming],
            "recent_errors": [dict(e) for e in recent_errors],
        }

    # ─── Helpers ─────────────────────────────────────────

    async def _get_setting(self, key: str) -> str:
        val = await db.fetch_val("SELECT value FROM settings WHERE key = ?", (key,))
        return val or ""

    async def _total_subs(self) -> int:
        return await db.fetch_val("SELECT COUNT(*) FROM subscriptions WHERE enabled = 1") or 0


rss_service = RSSService()

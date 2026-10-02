"""
TubeVault – RSS Service v1.6.2
YouTube RSS Feed Polling + Channel Scan (Videos/Shorts/Live)
Phasen-Fortschritt, Abbruch-Unterstützung, Fehler-Transparenz
© HalloWelt42 – Private Nutzung

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
from datetime import datetime, timedelta, timezone
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

import httpx

from app.config import AVATARS_DIR, BANNERS_DIR, RSS_THUMBS_DIR
from app.utils.file_utils import now_sqlite, past_sqlite
from app.database import db
from app.services.job_service import job_service
from app.services import feed_scope, loadable, video_classifier
from app.services.rate_limiter import rate_limiter
from app.services.channel_scanner import (
    fetch_all_channel_videos as _scan_channel,
    published_from_upload_date,
    refresh_type_counts,
)

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

# So viele der neuesten Einträge liest eine Prüfung je Kanal
POLL_DEPTH = 15

# Störungen, die nicht am einzelnen Kanal liegen (Netz weg, Quelle sperrt).
# Sie brechen den Durchlauf ab, statt jeden Kanal einzeln zu bestrafen.
_GLOBAL_ERROR_MARKERS = (
    "sign in to confirm", "429", "too many requests", "timed out", "timeout",
    "name resolution", "nodename nor servname", "connection refused",
    "network is unreachable", "connection reset", "unable to download webpage",
)
# So viele Kanäle in Folge ohne einen Erfolg dazwischen gelten als Störung
GLOBAL_FAILURE_STREAK = 3
# Pause nach einer Störung: 10 Minuten, je weitere Störung doppelt, höchstens 2 Stunden
DISTURBANCE_PAUSE_S = 600
DISTURBANCE_PAUSE_MAX_S = 7200


def is_global_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in _GLOBAL_ERROR_MARKERS)


def _utc_iso_now() -> str:
    """Jetzt in der Schreibweise von rss_entries.published."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


class ChannelNotFound(ValueError):
    """Die Quelle kennt den Kanal nicht oder gibt keine Auskunft."""


class RSSService:
    """YouTube RSS Feed Manager – produktionsreif."""

    def __init__(self):
        self._running = False
        self._polling = False  # Lock: verhindert parallele Prüfläufe
        # Scheduler-Status (für Frontend)
        self._last_checked_channel: str = ""
        self._last_checked_at: str = ""
        self._feeds_checked_cycle: int = 0
        # Log-Drossel: max. 3 "neue Videos"-Zeilen pro RSS-Zyklus, Rest als Summe
        self._feed_log_count: int = 0
        self._feed_log_suppressed: int = 0
        self._feeds_pending: int = 0
        # Letzter Anstoß, auch wenn er nichts geprüft hat (sichtbar im Status)
        self._last_tick: dict = {}
        self._ticks_skipped: int = 0
        # Störung der Quelle: bis wann pausiert wird und die wievielte in Folge
        self._disturbed_until: Optional[datetime] = None
        self._disturbance_count: int = 0
        self._disturbance_reason: str = ""

    # ─── Worker Lifecycle ─────────────────────────────────

    async def start_worker(self):
        """RSS-Service initialisieren (kein Background-Loop mehr, Cron übernimmt)."""
        self._running = True
        logger.info("RSS Service bereit – Feed-Checks werden per Cron ausgelöst")

    async def stop_worker(self):
        """RSS-Service stoppen."""
        self._running = False
        logger.info("RSS Service gestoppt")

    # ─── Prüfplanung ───────────────────────────────────────
    #
    # Alle 5 Minuten kommt ein Anstoß (main.py). Geprüft werden die Kanäle,
    # deren Intervall abgelaufen ist. Ohne neue Videos verdoppelt sich das
    # Intervall eines Kanals bis zur einstellbaren Obergrenze, neue Videos
    # setzen es auf den Basiswert zurück.
    #

    def _note_tick(self, result: dict) -> dict:
        """Ausgang des Anstoßes festhalten - auch übersprungene sind sichtbar."""
        status = result.get("status", "")
        self._ticks_skipped = self._ticks_skipped + 1 if status == "skipped" else 0
        self._last_tick = {
            "at": now_sqlite(),
            "status": status,
            "message": result.get("message", ""),
            "skipped_in_a_row": self._ticks_skipped,
        }
        return result

    async def _intervals(self) -> tuple[int, int]:
        """(Basis-Intervall, längstes Intervall) in Sekunden."""
        base = int(await self._get_setting("rss.interval") or 1800)
        longest = int(await self._get_setting("rss.max_interval") or 86400)
        return base, max(base, longest)

    def _disturbance_pause_left(self) -> int:
        """Sekunden, die die Prüfung wegen einer Störung noch pausiert."""
        if not self._disturbed_until:
            return 0
        return max(0, int((self._disturbed_until - datetime.now()).total_seconds()))

    def _note_disturbance(self, reason: str):
        self._disturbance_count += 1
        pause = min(DISTURBANCE_PAUSE_S * 2 ** (self._disturbance_count - 1),
                    DISTURBANCE_PAUSE_MAX_S)
        self._disturbed_until = datetime.now() + timedelta(seconds=pause)
        self._disturbance_reason = reason[:300]
        logger.warning(f"[PRÜFUNG] Quelle gestört, Pause {pause // 60} Min: {reason[:160]}")

    def _clear_disturbance(self):
        self._disturbed_until = None
        self._disturbance_count = 0
        self._disturbance_reason = ""

    async def tick(self, max_feeds: int = 20) -> dict:
        """Fällige Kanäle prüfen. Liefert immer einen Ausgang mit Begründung."""
        if self._polling:
            logger.info("[TICK] Übersprungen – vorheriger Durchlauf läuft noch")
            return self._note_tick(
                {"status": "skipped", "message": "Vorheriger Durchlauf läuft noch"})

        self._polling = True
        try:
            return self._note_tick(await self._do_tick(max_feeds))
        finally:
            self._polling = False

    _DUE_SQL = """enabled = 1
               AND (last_checked IS NULL
                    OR last_checked < datetime('now', '-' || check_interval || ' seconds'))"""

    async def _do_tick(self, max_feeds: int = 20) -> dict:
        """Eigentliche Tick-Logik (durch Lock geschützt)."""
        enabled = await self._get_setting("rss.enabled")
        if enabled != "true":
            return {"status": "disabled", "message": "Scanner ist in den Einstellungen abgeschaltet"}

        pause_left = self._disturbance_pause_left()
        if pause_left:
            return {"status": "skipped",
                    "message": f"Quelle gestört - nächster Versuch in {pause_left // 60 + 1} Min "
                               f"({self._disturbance_reason[:120]})"}

        # Scan, Import und Prüfung schließen sich aus. Statt auf einen langen
        # Scan zu warten, setzt die Prüfung aus und kommt in 5 Minuten wieder.
        if job_service.is_exclusive_running():
            return {"status": "skipped",
                    "message": "Ein anderer Hintergrundlauf ist aktiv (z.B. Kanal-Scan)"}

        base_interval, longest_interval = await self._intervals()
        # Obergrenze durchsetzen (auch nachträglich gesenkte)
        await db.execute(
            "UPDATE subscriptions SET check_interval = ? WHERE check_interval > ?",
            (longest_interval, longest_interval))

        await self.queue_pending_auto_downloads()

        subs = [dict(s) for s in await db.fetch_all(
            f"""SELECT * FROM subscriptions WHERE {self._DUE_SQL}
               ORDER BY last_checked ASC NULLS FIRST, error_count ASC
               LIMIT ?""",
            (max_feeds,)
        )]
        total_pending = await self._pending_count()
        self._feeds_pending = total_pending

        if not subs:
            return {
                "status": "idle",
                "message": "Keine fälligen Kanäle",
                "checked": 0,
                "new_videos": 0,
                "next_due_in_seconds": await self._next_due_seconds(),
            }

        job = await job_service.create(
            job_type="rss_cycle",
            title=f"Kanalprüfung ({len(subs)} von {total_pending} fälligen)",
            description=f"{len(subs)} Kanäle werden geprüft",
            metadata={"trigger": "tick", "batch_size": len(subs), "total_pending": total_pending},
            priority=8,
        )
        await job_service.start(job["id"])
        async with job_service.guard(job["id"]):
            outcome = await self._check_feeds(job["id"], subs, adaptive=True)
            await job_service.complete(job["id"], outcome["message"])
        logger.info(f"Kanalprüfung: {outcome['message']}")

        remaining = await self._pending_count()
        self._feeds_pending = remaining
        return {
            "status": "disturbed" if outcome["disturbed"] else "completed",
            "checked": outcome["checked"],
            "new_videos": outcome["new_videos"],
            "errors": outcome["errors"],
            "remaining_pending": remaining,
            "next_due_in_seconds": await self._next_due_seconds(),
            "message": outcome["message"],
        }

    async def _pending_count(self) -> int:
        return await db.fetch_val(
            f"SELECT COUNT(*) FROM subscriptions WHERE {self._DUE_SQL}") or 0

    async def _check_feeds(self, job_id: int, subs: list[dict], adaptive: bool) -> dict:
        """Kanäle der Reihe nach prüfen.

        adaptive=True (automatische Prüfung): ohne neue Videos wächst das
        Intervall des Kanals. Bei einer Prüfung von Hand bleibt es stehen.

        Fehler eines einzelnen Kanals bestrafen nur diesen Kanal. Fällt die
        Quelle insgesamt aus, bricht der Durchlauf ab und kein Kanal wird
        bestraft - sonst stünden nach einer Netzstörung hunderte Kanäle mit
        Fehlerzähler und verlängertem Intervall da.
        """
        self._feed_log_count = 0
        self._feed_log_suppressed = 0
        base_interval, longest_interval = await self._intervals()
        total_new = checked = errors = 0
        disturbed = False
        # Fehlschläge in Folge: erst bestrafen, wenn ein Erfolg zeigt, dass
        # die Quelle erreichbar ist und es am Kanal liegt
        streak: list[tuple[dict, Exception]] = []

        for i, sub in enumerate(subs):
            if job_service.is_cancelled(job_id):
                break
            try:
                await rate_limiter.acquire("rss")
                new_count = await self._poll_single_feed(sub)
            except Exception as e:
                rate_limiter.error("rss", str(e)[:200])
                logger.warning(f"Kanalprüfung Fehler {sub['channel_id']}: {e}")
                streak.append((sub, e))
                if is_global_error(e) or len(streak) >= GLOBAL_FAILURE_STREAK:
                    disturbed = True
                    self._note_disturbance(str(e))
                    break
                continue

            rate_limiter.success("rss")
            self._clear_disturbance()
            for failed_sub, error in streak:
                await self._penalize(failed_sub, error, longest_interval)
            errors += len(streak)
            streak = []

            checked += 1
            total_new += new_count
            self._last_checked_channel = sub.get("channel_name") or sub["channel_id"]
            self._last_checked_at = now_sqlite()
            self._feeds_checked_cycle += 1
            await self._reward(sub, new_count, base_interval, longest_interval, adaptive)

            if (i + 1) % 5 == 0 or i == len(subs) - 1:
                await job_service.progress(
                    job_id, (i + 1) / len(subs),
                    f"{i + 1}/{len(subs)} Kanäle, {total_new} neue Videos, {errors} Fehler")

        if not disturbed:
            for failed_sub, error in streak:
                await self._penalize(failed_sub, error, longest_interval)
            errors += len(streak)

        if self._feed_log_suppressed > 0:
            logger.info(f"Feed: +{self._feed_log_suppressed} weitere Kanäle mit neuen Videos (Log gedrosselt)")

        message = f"{total_new} neue Videos, {checked} Kanäle geprüft, {errors} Fehler"
        if disturbed:
            message += (f" - abgebrochen: Quelle gestört ({self._disturbance_reason[:120]}), "
                        f"Pause {self._disturbance_pause_left() // 60 + 1} Min")
        return {"checked": checked, "new_videos": total_new, "errors": errors,
                "disturbed": disturbed, "message": message}

    async def _reward(self, sub: dict, new_count: int, base_interval: int,
                      longest_interval: int, adaptive: bool):
        """Erfolgreiche Prüfung: Fehler löschen, Intervall anpassen."""
        current = sub.get("check_interval") or base_interval
        if new_count > 0:
            interval = base_interval
        elif adaptive:
            interval = min(current * 2, longest_interval)
        else:
            interval = current
        await db.execute(
            "UPDATE subscriptions SET error_count = 0, last_error = NULL, check_interval = ? "
            "WHERE id = ?",
            (interval, sub["id"]))

    async def _penalize(self, sub: dict, error: Exception, longest_interval: int):
        """Fehlgeschlagene Prüfung eines Kanals: Fehler merken, seltener prüfen.
        last_checked wird gesetzt, sonst wäre der Kanal sofort wieder fällig."""
        error_count = (sub.get("error_count") or 0) + 1
        message = str(error)[:500]
        if "404" in message:
            # Kanal evtl. gelöscht oder umgezogen: stark bremsen, nicht abschalten
            interval = min(86400, 21600 * error_count)
            message = (f"[404] Kanal nicht erreichbar ({error_count}x) - "
                       f"nächster Versuch in {interval // 3600} h")
        else:
            interval = min((sub.get("check_interval") or 1800) * 2, longest_interval)
        await db.execute(
            """UPDATE subscriptions SET error_count = ?, last_error = ?, check_interval = ?,
               last_checked = ? WHERE id = ?""",
            (error_count, message, interval, now_sqlite(), sub["id"]))

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

    async def check_channel_now(self, sub_id: int) -> dict:
        """Einen Kanal sofort prüfen (von Hand). Das Intervall wächst dabei nicht."""
        sub = await db.fetch_one("SELECT * FROM subscriptions WHERE id = ?", (sub_id,))
        if not sub:
            raise ChannelNotFound("Kanal nicht gefunden")
        sub = dict(sub)
        base_interval, longest_interval = await self._intervals()
        try:
            await rate_limiter.acquire("rss")
            new_count = await self._poll_single_feed(sub)
        except Exception as e:
            rate_limiter.error("rss", str(e)[:200])
            if not is_global_error(e):
                await self._penalize(sub, e, longest_interval)
            raise
        rate_limiter.success("rss")
        await self._reward(sub, new_count, base_interval, longest_interval, adaptive=False)
        return {"channel_id": sub["channel_id"], "new_videos": new_count}

    async def _fetch_latest(self, channel_id: str) -> tuple[str, list]:
        """Die neuesten Einträge eines Kanals (im Thread). Hat der Kanal keinen
        Videos-Reiter, kommen Shorts oder Livestreams."""
        from app.utils.pytube_client import make_channel

        def _fetch_tab(subpath: str):
            ch = make_channel(
                f"https://www.youtube.com/channel/{channel_id}{subpath}",
                max_videos=POLL_DEPTH,
            )
            # Erst die Liste, dann der Name: so genügt ein Abruf
            videos = list(ch.videos)
            return ch.channel_name, videos

        def _fetch():
            try:
                return _fetch_tab("/videos")
            except Exception as e:
                msg = str(e).lower()
                if "does not have a videos tab" not in msg and "no videos" not in msg:
                    raise
            for sub_tab in ("/shorts", "/streams"):
                ch = make_channel(
                    f"https://www.youtube.com/channel/{channel_id}", max_videos=POLL_DEPTH)
                ch.html_url = ch.shorts_url if sub_tab == "/shorts" else ch.live_url
                videos = list(ch.url_generator())
                if videos:
                    return ch.channel_name, videos
            return "", []

        return await asyncio.get_event_loop().run_in_executor(None, _fetch)

    async def _poll_single_feed(self, sub: dict) -> int:
        """Einen Kanal prüfen und neue Einträge speichern. Liefert deren Zahl.
        Bekannte Einträge kosten nichts: Typ-Bestimmung, Vorschaubild und
        Auto-Download laufen nur für neue."""
        channel_id = sub["channel_id"]

        # Ungültige channel_ids überspringen (z.B. URLs statt IDs)
        if not channel_id or not channel_id.startswith("UC") or len(channel_id) != 24:
            logger.warning(f"Ungültige channel_id übersprungen: {channel_id[:60]}… – deaktiviere")
            await db.execute(
                "UPDATE subscriptions SET enabled = 0, last_error = ? WHERE id = ?",
                (f"Ungültige channel_id: {channel_id[:100]}", sub["id"])
            )
            return 0

        channel_name, videos = await self._fetch_latest(channel_id)
        fetched_ids = [v.video_id for v in videos if v.video_id]

        if channel_name and (not sub.get("channel_name") or sub["channel_name"] == sub["channel_id"]):
            await db.execute(
                "UPDATE subscriptions SET channel_name = ? WHERE id = ?",
                (channel_name, sub["id"])
            )

        known: set[str] = set()
        if fetched_ids:
            placeholders = ",".join("?" * len(fetched_ids))
            known = {row["video_id"] for row in await db.fetch_all(
                f"SELECT video_id FROM rss_entries WHERE channel_id = ? "
                f"AND video_id IN ({placeholders})",
                (channel_id, *fetched_ids))}
        fresh = [v for v in videos if v.video_id and v.video_id not in known]

        # Listen der Quelle für Shorts und Livestreams (UUSH / UULV). Nur nötig,
        # wenn es Neues einzuordnen oder einen beendeten Livestream gibt.
        short_ids: set = set()
        live_ids: set = set()
        has_live = fetched_ids and await db.fetch_val(
            "SELECT 1 FROM rss_entries WHERE channel_id = ? AND video_type = 'live' LIMIT 1",
            (channel_id,))
        if fresh or has_live:
            short_ids, live_ids = await self._fetch_typed_video_ids(channel_id)

        max_age = int(await self._get_setting("rss.max_age_days") or 90)
        cutoff = past_sqlite(days=max_age)
        shorts_excluded = await video_classifier.shorts_excluded()

        new_count = 0
        for v in fresh:
            video_id = v.video_id
            # Ohne Datum der Quelle gilt der Zeitpunkt des Fundes
            published = published_from_upload_date(v.publish_date) or _utc_iso_now()
            if published < cutoff:
                continue

            # Video-Typ: Livestreams und Shorts aus den Listen der Quelle.
            # Steht ein kurzes Video in keiner der Listen, fragt der
            # video_classifier die Quelle - geraten wird nicht.
            if video_id in live_ids:
                video_type, type_verified = "live", video_classifier.VERIFIED
            elif video_id in short_ids:
                video_type, type_verified = "short", video_classifier.VERIFIED
            else:
                typed = await video_classifier.classify(video_id, duration=(v.length or None))
                video_type = typed.video_type
                type_verified = video_classifier.VERIFIED if typed.verified else video_classifier.UNVERIFIED

            cursor = await db.execute(
                """INSERT OR IGNORE INTO rss_entries
                   (video_id, channel_id, title, published, thumbnail_url, duration, views,
                    video_type, type_verified)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (video_id, channel_id, v.title or "", published, v.thumbnail_url,
                 v.length or None, v.views or None, video_type, type_verified)
            )
            if cursor.rowcount == 0:
                continue
            new_count += 1

            if v.thumbnail_url:
                await self._cache_rss_thumbnail(video_id, v.thumbnail_url)

            # Livestreams nicht automatisch laden (noch nicht zu Ende),
            # Shorts nur, solange sie nicht ausgeschlossen sind.
            skip_short = video_type == "short" and shorts_excluded
            if sub.get("auto_download") and video_type != "live" and not skip_short:
                await self._auto_queue_video(video_id, sub)

        # Beendete Livestreams: 'live'-Einträge, die jetzt in der Videoliste
        # stehen und nicht mehr in der Livestream-Liste, sind reguläre Videos.
        if has_live:
            placeholders = ",".join("?" * len(fetched_ids))
            ended = await db.fetch_all(
                f"SELECT video_id FROM rss_entries WHERE channel_id = ? "
                f"AND video_type = 'live' AND video_id IN ({placeholders})",
                (channel_id, *fetched_ids),
            )
            for row in ended:
                if row["video_id"] in live_ids:
                    continue  # steht weiter in der Livestream-Liste
                await db.execute(
                    "UPDATE rss_entries SET video_type = 'video' WHERE video_id = ?",
                    (row["video_id"],),
                )
                if sub.get("auto_download"):
                    await self._auto_queue_video(row["video_id"], sub)
                logger.info(f"[RSS] Ex-Livestream {row['video_id']} → Video, Kanal {channel_id}")

        await db.execute(
            """UPDATE subscriptions SET last_checked = ?,
               last_video_date = COALESCE(
                   (SELECT MAX(published) FROM rss_entries WHERE channel_id = ?), last_video_date)
               WHERE id = ?""",
            (now_sqlite(), channel_id, sub["id"])
        )
        if new_count > 0:
            await refresh_type_counts(channel_id)
            # Log-Drossel: nur die ersten 3 Kanäle pro Zyklus einzeln loggen,
            # der Rest wird gezählt und am Zyklus-Ende als Summe geloggt.
            self._feed_log_count += 1
            if self._feed_log_count <= 3:
                logger.info(f"Feed: {new_count} neue Videos von {sub.get('channel_name', channel_id)}")
            else:
                self._feed_log_suppressed += 1

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

    async def _auto_queue_video(self, video_id: str, sub: dict) -> bool:
        """Video automatisch einreihen. Ist das Tageslimit erreicht, wird es
        vorgemerkt und an einem der nächsten Tage nachgeholt - es geht nicht
        verloren."""
        if not await loadable.is_loadable(video_id):
            # Schon da, ignoriert, in der Warteschlange oder fehlgeschlagen
            await db.execute(
                "UPDATE rss_entries SET auto_pending = 0 WHERE video_id = ?", (video_id,))
            return False

        limit = int(await self._get_setting("rss.auto_dl_daily_limit") or AUTO_DL_DAILY_LIMIT)
        used = await self._auto_dl_count_today()
        if used >= limit:
            await db.execute(
                "UPDATE rss_entries SET auto_pending = 1 WHERE video_id = ?", (video_id,))
            logger.debug(f"Auto-DL Tageslimit ({limit}) erreicht, {video_id} vorgemerkt")
            return False

        rss_title = await db.fetch_val(
            "SELECT title FROM rss_entries WHERE video_id = ?", (video_id,))
        await job_service.create(
            job_type="download",
            title=rss_title[:256] if rss_title else video_id,
            description="Auto-Download",
            metadata={
                "video_id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                # Keine festen Werte: Qualität, Nur-Audio und Thumbnail löst
                # download_options beim Start auf (Kanal > Einstellungen).
                "download_options": {"origin": "auto"},
                "retry_count": 0, "max_retries": 3,
            },
            priority=5,
        )
        await db.execute(
            "UPDATE rss_entries SET status = 'queued', auto_queued = 1, auto_pending = 0 "
            "WHERE video_id = ?",
            (video_id,)
        )
        await self._auto_dl_count_today(add=1)
        logger.info(f"Auto-DL queued: {video_id} ({used + 1}/{limit} heute)")
        return True

    async def queue_pending_auto_downloads(self) -> int:
        """Am Tageslimit vorgemerkte Videos nachholen, älteste zuerst. Kanäle,
        deren Auto-Download inzwischen abgeschaltet ist, verlieren die Vormerkung."""
        await db.execute(
            """UPDATE rss_entries SET auto_pending = 0
               WHERE auto_pending = 1 AND channel_id NOT IN (
                   SELECT channel_id FROM subscriptions WHERE auto_download = 1 AND enabled = 1)""")
        limit = int(await self._get_setting("rss.auto_dl_daily_limit") or AUTO_DL_DAILY_LIMIT)
        free = limit - await self._auto_dl_count_today()
        if free <= 0:
            return 0
        pending = await db.fetch_all(
            """SELECT video_id, channel_id FROM rss_entries
               WHERE auto_pending = 1 ORDER BY published ASC, id ASC LIMIT ?""",
            (free,))
        queued = 0
        for row in pending:
            if await self._auto_queue_video(row["video_id"], {"channel_id": row["channel_id"]}):
                queued += 1
        return queued

    async def _auto_dl_count_today(self, add: int = 0) -> int:
        """Zahl der heutigen automatischen Downloads (interner Zähler in der
        settings-Tabelle, Form 'JJJJ-MM-TT:n'). add erhöht den Zähler."""
        today = datetime.now().strftime("%Y-%m-%d")
        raw = await db.fetch_val(
            "SELECT value FROM settings WHERE key = 'rss.auto_dl_counter'") or ""
        day, _, count = raw.partition(":")
        used = int(count) if day == today and count.isdigit() else 0
        if add:
            used += add
            await db.execute(
                """INSERT INTO settings (key, value, description, category)
                   VALUES ('rss.auto_dl_counter', ?, 'Interner Tageszähler', 'internal')
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (f"{today}:{used}",))
        return used

    # ─── Abo-Management ──────────────────────────────────

    async def add_subscription(self, channel_id: str, auto_download: bool = False,
                               quality: str = None) -> dict:
        """Neues Abo hinzufügen. Kennt die Quelle den Kanal nicht, entsteht
        kein Abo (ChannelNotFound) - sonst lägen Einträge ohne Namen herum,
        die bei jeder Prüfung scheitern."""
        existing = await db.fetch_one(
            "SELECT * FROM subscriptions WHERE channel_id = ?", (channel_id,))
        if existing:
            return {**dict(existing), "already_subscribed": True}

        # quality leer = Kanal erbt die Qualität aus den Einstellungen
        quality = quality or None
        channel_url = f"https://www.youtube.com/channel/{channel_id}"
        await rate_limiter.acquire("rss")
        try:
            from app.utils.pytube_client import make_channel

            def _fetch_meta():
                ch = make_channel(channel_url)
                return ch.channel_name, ch.vanity_url or channel_url

            channel_name, channel_url = await asyncio.get_event_loop().run_in_executor(
                None, _fetch_meta)
            rate_limiter.success("rss")
        except Exception as e:
            rate_limiter.error("rss", str(e)[:200])
            raise ChannelNotFound(
                f"Kanal {channel_id} ist bei der Quelle nicht abrufbar: {str(e)[:200]}") from e
        if not channel_name:
            raise ChannelNotFound(f"Kanal {channel_id} ist bei der Quelle nicht bekannt")

        default_interval = int(await self._get_setting("rss.interval") or 1800)
        cursor = await db.execute(
            """INSERT OR IGNORE INTO subscriptions
               (channel_id, channel_name, channel_url, auto_download, download_quality, check_interval)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (channel_id, channel_name, channel_url, auto_download, quality, default_interval)
        )
        sub = dict(await db.fetch_one(
            "SELECT * FROM subscriptions WHERE channel_id = ?", (channel_id,)))
        if cursor.rowcount:
            logger.info(f"Abo: {channel_name} ({channel_id})")
            # Kanalbild und erste Prüfung im Hintergrund - das Hinzufügen wartet nicht
            asyncio.create_task(self._finish_new_subscription(sub))
        return sub

    async def _finish_new_subscription(self, sub: dict):
        """Nach dem Hinzufügen: Kanalbild holen, dann die erste Prüfung."""
        try:
            await self._load_avatar(sub["channel_id"])
            await self._safe_poll(sub)
        except Exception as e:
            logger.warning(f"Nachbereitung des Abos {sub['channel_id']} fehlgeschlagen: {e}")

    async def _load_avatar(self, channel_id: str) -> bool:
        """Kanalbild holen und am Abo vermerken. Liefert, ob es geklappt hat."""
        await rate_limiter.acquire("avatar")
        avatar_path = await self._fetch_channel_avatar(channel_id)
        if not avatar_path:
            rate_limiter.error("avatar", "kein Kanalbild erhalten")
            return False
        rate_limiter.success("avatar")
        await db.execute(
            "UPDATE subscriptions SET avatar_path = ? WHERE channel_id = ?",
            (avatar_path, channel_id))
        return True

    async def _safe_poll(self, sub: dict):
        """Poll mit Error-Handling (für create_task)."""
        try:
            await rate_limiter.acquire("rss")
            await self._poll_single_feed(sub)
        except Exception as e:
            logger.warning(f"Erste Prüfung von {sub.get('channel_id')} fehlgeschlagen: {e}")

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
            from app.utils.pytube_client import make_channel
            ch = make_channel(f"https://www.youtube.com/channel/{channel_id}")
            return ch.thumbnail_url, ch.channel_name

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
        """Batch-Import: nur Namen holen, Kanalbilder danach einzeln im Hintergrund."""
        channel_ids = [cid.strip() for cid in channel_ids]
        job = await job_service.create(
            job_type="import",
            title=f"Abo-Import ({len(channel_ids)} Kanäle)",
            description="Importiere Kanal-Abonnements",
        )
        await job_service.start(job["id"])

        added = 0
        skipped = 0
        new_ids = []
        async with job_service.guard(job["id"]):
            for i, cid in enumerate(channel_ids):
                if job_service.is_cancelled(job["id"]):
                    break
                if not (cid.startswith("UC") and len(cid) == 24):
                    skipped += 1
                    continue
                try:
                    await rate_limiter.acquire("rss")
                    result = await self._add_subscription_fast(cid, auto_download=auto_download)
                    rate_limiter.success("rss")
                    if result.get("new"):
                        added += 1
                        new_ids.append(cid)
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

            if not job_service.is_cancelled(job["id"]):
                await job_service.complete(
                    job["id"], f"{added} Abos importiert, {skipped} übersprungen")

        # Kanalbilder nachträglich im Hintergrund (rate-limited, resume-fähig)
        if new_ids:
            asyncio.create_task(self._fetch_avatars_background(new_ids))

        return {"added": added, "skipped": skipped, "total": len(channel_ids)}

    async def _add_subscription_fast(self, channel_id: str,
                                     auto_download: bool = False) -> dict:
        """Schnell-Import: Kanalname holen (yt-dlp minimal). Kein Avatar, keine Videoliste."""
        channel_name = channel_id
        channel_url = f"https://www.youtube.com/channel/{channel_id}"

        try:
            from app.utils.pytube_client import make_channel
            loop = asyncio.get_event_loop()

            def _fetch_name():
                ch = make_channel(f"https://www.youtube.com/channel/{channel_id}")
                return ch.channel_name or channel_id, ch.vanity_url or channel_url

            channel_name, channel_url = await loop.run_in_executor(None, _fetch_name)
        except Exception:
            pass

        cursor = await db.execute(
            """INSERT OR IGNORE INTO subscriptions
               (channel_id, channel_name, channel_url, auto_download, download_quality)
               VALUES (?, ?, ?, ?, NULL)""",
            (channel_id, channel_name, channel_url, auto_download)
        )

        return {"new": cursor.rowcount > 0, "channel_id": channel_id}

    # ─── Avatar Background-Fetch (resume-fähig) ─────────

    async def _fetch_avatars_background(self, channel_ids: list[str]):
        """Kanalbilder im Hintergrund laden – rate-limited, resume-fähig."""
        job = await job_service.create(
            job_type="avatar_fetch",
            title=f"Kanalbilder laden ({len(channel_ids)} Kanäle)",
            description="Lade Kanalbilder",
            metadata={"channel_ids": channel_ids, "completed_index": 0},
        )
        await job_service.start(job["id"], exclusive=False)

        loaded = 0
        async with job_service.guard(job["id"]):
            for i, cid in enumerate(channel_ids):
                if job_service.is_cancelled(job["id"]):
                    return
                has_avatar = await db.fetch_val(
                    "SELECT 1 FROM subscriptions WHERE channel_id = ? AND avatar_path IS NOT NULL",
                    (cid,))
                try:
                    if has_avatar or await self._load_avatar(cid):
                        loaded += 1
                except Exception as e:
                    rate_limiter.error("avatar", str(e)[:200])
                    logger.debug(f"Avatar skip {cid}: {e}")

                # Stand merken, damit ein Neustart hier weitermacht
                if i % 5 == 0:
                    await job_service.progress(
                        job["id"], (i + 1) / len(channel_ids),
                        f"{loaded}/{i + 1} Kanalbilder geladen",
                        metadata={"completed_index": i + 1})

            await job_service.complete(
                job["id"], f"{loaded} von {len(channel_ids)} Kanalbildern geladen")

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
                # Der Rest läuft als neuer Job; der alte ist damit erledigt
                await job_service.complete(
                    job["id"], f"Nach Neustart fortgesetzt ({len(remaining)} verbleibend)")
                asyncio.create_task(self._fetch_avatars_background(remaining))
            else:
                await job_service.complete(job["id"], "Alle Kanalbilder geladen")

    # ─── Kanal komplett laden → channel_scanner.py ─────────────

    async def fetch_all_channel_videos(self, channel_id: str, job_id: int = None) -> dict:
        """Delegation an channel_scanner.py"""
        return await _scan_channel(channel_id, job_id=job_id)

    # ─── Abo CRUD ────────────────────────────────────────

    async def remove_subscription(self, sub_id: int, delete_videos: bool = False) -> dict:
        """Abo entfernen. delete_videos=True löscht zusätzlich alle Videos des
        Kanals restlos; sonst bleiben sie in Bibliothek und Archiv."""
        channel_id = await db.fetch_val(
            "SELECT channel_id FROM subscriptions WHERE id = ?", (sub_id,))
        if not channel_id:
            return {"removed": False, "videos_deleted": 0}
        videos_deleted = 0
        if delete_videos:
            from app.services.metadata_service import metadata_service
            videos_deleted = await metadata_service.delete_channel_videos(channel_id)
            await db.execute("DELETE FROM ignored_videos WHERE channel_id = ?", (channel_id,))
        await db.execute("DELETE FROM rss_entries WHERE channel_id = ?", (channel_id,))
        await db.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
        for folder, name in ((AVATARS_DIR, f"{channel_id}.jpg"), (BANNERS_DIR, f"{channel_id}.jpg")):
            (folder / name).unlink(missing_ok=True)
        return {"removed": True, "videos_deleted": videos_deleted}

    async def update_subscription(self, sub_id: int, updates: dict):
        import random
        allowed = {"auto_download", "download_quality", "audio_only",
                    "check_interval", "enabled", "drip_enabled", "drip_count",
                    "drip_auto_archive", "suggest_exclude"}
        filtered = {k: v for k, v in updates.items() if k in allowed}
        # Nur die Qualität darf geleert werden ("Standard aus den Einstellungen")
        filtered = {k: v for k, v in filtered.items()
                    if v is not None or k == "download_quality"}
        if not filtered:
            return
        if filtered.get("download_quality") == "":
            filtered["download_quality"] = None
        if filtered.get("download_quality") is not None:
            from app.settings_schema import VIDEO_QUALITIES
            if filtered["download_quality"] not in VIDEO_QUALITIES:
                raise ValueError(f"Unbekannte Qualität: {filtered['download_quality']}")

        # Drip aktiviert → erste Ausführungszeit würfeln
        if filtered.get("drip_enabled"):
            from app.utils.file_utils import next_drip_run
            filtered["drip_next_run"] = next_drip_run()
        elif "drip_enabled" in filtered and not filtered["drip_enabled"]:
            filtered["drip_next_run"] = None

        set_clause = ", ".join(f"{k} = ?" for k in filtered)
        values = list(filtered.values()) + [sub_id]
        await db.execute(f"UPDATE subscriptions SET {set_clause} WHERE id = ?", values)

    async def get_subscriptions(self, page: int = 1, per_page: int = 50) -> dict:
        total = await db.fetch_val("SELECT COUNT(*) FROM subscriptions")
        offset = (page - 1) * per_page
        # Zähler je Kanal in einem Durchgang je Tabelle (statt vier Unterabfragen
        # je Kanal - bei hunderten Kanälen dauerte die Liste sonst Sekunden).
        # Ausgeschlossene Shorts zählen nirgends mit.
        rows = await db.fetch_all(
            f"""WITH feed AS (
                   SELECT r.channel_id,
                          COUNT(*) AS rss_count,
                          SUM({feed_scope.new_entry("r")}) AS new_videos
                   FROM rss_entries r WHERE 1=1{await video_classifier.without_shorts("r")}
                   GROUP BY r.channel_id),
                 loaded AS (
                   SELECT v.channel_id, COUNT(*) AS downloaded_count
                   FROM videos v WHERE v.status = 'ready'{await video_classifier.without_shorts("v")}
                   GROUP BY v.channel_id),
                 problems AS (
                   SELECT r.channel_id, COUNT(*) AS problem_count
                   FROM jobs j
                   JOIN rss_entries r ON r.video_id = json_extract(j.metadata, '$.video_id')
                   WHERE j.type = 'download' AND j.status = 'parked'
                   GROUP BY r.channel_id)
               SELECT s.*,
                      COALESCE(feed.new_videos, 0) AS new_videos,
                      COALESCE(feed.rss_count, 0) AS rss_count,
                      COALESCE(loaded.downloaded_count, 0) AS downloaded_count,
                      COALESCE(problems.problem_count, 0) AS problem_count
               FROM subscriptions s
               LEFT JOIN feed ON feed.channel_id = s.channel_id
               LEFT JOIN loaded ON loaded.channel_id = s.channel_id
               LEFT JOIN problems ON problems.channel_id = s.channel_id
               ORDER BY s.channel_name COLLATE NOCASE ASC, s.id
               LIMIT ? OFFSET ?""",
            (per_page, offset)
        )
        return {
            "subscriptions": [dict(r) for r in rows],
            "total": total or 0,
            "page": page,
            "per_page": per_page,
        }

    async def get_problem_videos(self, channel_id: str) -> list[dict]:
        """Alle geparkten Downloads eines Kanals mit Fehler-Info.
        Wird im Frontend pro Abo als "Problem-Videos"-Sektion angezeigt.
        """
        rows = await db.fetch_all(
            """SELECT j.id as job_id, j.title, j.error_message, j.created_at, j.completed_at,
                      j.metadata,
                      r.video_id, r.thumbnail_url, r.published, r.video_type
               FROM jobs j
               INNER JOIN rss_entries r ON json_extract(j.metadata, '$.video_id') = r.video_id
               WHERE j.type = 'download' AND j.status = 'parked' AND r.channel_id = ?
               ORDER BY j.created_at DESC""",
            (channel_id,)
        )
        out = []
        for r in rows:
            d = dict(r)
            try:
                meta = json.loads(d.get("metadata") or "{}")
            except Exception:
                meta = {}
            d["retry_count"] = meta.get("retry_count", 0)
            d["url"] = meta.get("url", f"https://www.youtube.com/watch?v={d.get('video_id','')}")
            d.pop("metadata", None)
            out.append(d)
        return out


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

        # Shorts global ausgeschlossen? Dann fehlen sie in jeder Feed-Ansicht.
        shorts_clause = await video_classifier.without_shorts("r")

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
            status_filter = f"AND {feed_scope.new_entry('r')}"
        elif feed_tab == "later":
            status_filter = "AND r.feed_status = 'later'"
        elif feed_tab == "dismissed":
            status_filter = "AND r.feed_status = 'dismissed'"
        elif feed_tab == "archived":
            status_filter = "AND r.feed_status = 'archived'"
        # feed_tab == "all" → kein Filter

        base_where = f"WHERE 1=1 {status_filter} {channel_filter} {type_filter} {keyword_filter} {duration_filter}{shorts_clause}"
        all_params = channel_params + type_params + keyword_params + duration_params

        # Total
        total = await db.fetch_val(
            f"""SELECT COUNT(*) FROM rss_entries r
                JOIN subscriptions s ON r.channel_id = s.channel_id
                {base_where}""",
            tuple(all_params)
        ) or 0

        # Typ-Counts (fuer Filter-Badges) – basieren auf gleichem Status-Tab + Keyword-Filter
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
            tab_condition = feed_scope.new_entry("r") if tab == "active" else f"r.feed_status = '{tab}'"
            tc = await db.fetch_val(
                f"""SELECT COUNT(*) FROM rss_entries r
                    JOIN subscriptions s ON r.channel_id = s.channel_id
                    WHERE {tab_condition}{shorts_clause}"""
            ) or 0
            tab_counts[tab] = tc

        # Ergebnisse
        # is_in_queue + queue_status via EXISTS-Subquery auf jobs-Tabelle
        # (analog subscriptions.py – Feed-Card zeigt gelben Rahmen + disabled DL-Button)
        rows = await db.fetch_all(
            f"""SELECT r.*, s.channel_name, s.download_quality, s.audio_only,
                       v.status as video_status,
                       COALESCE(r.video_type, 'video') as video_type_safe,
                       CASE WHEN (SELECT j.id FROM jobs j
                                  WHERE j.type='download'
                                    AND json_extract(j.metadata, '$.video_id') = r.video_id
                                    AND j.status IN ('queued','active','retry_wait')
                                  LIMIT 1) IS NOT NULL
                            THEN 1 ELSE 0 END as is_in_queue,
                       COALESCE((SELECT j.status FROM jobs j
                                 WHERE j.type='download'
                                   AND json_extract(j.metadata, '$.video_id') = r.video_id
                                   AND j.status IN ('queued','active','retry_wait')
                                 LIMIT 1), '') as queue_status
                FROM rss_entries r
                JOIN subscriptions s ON r.channel_id = s.channel_id
                LEFT JOIN videos v ON r.video_id = v.id
                {base_where}
                ORDER BY r.published DESC, r.id DESC
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
        """Alle aktiven Kanäle sofort prüfen (von Hand, unabhängig vom Intervall).
        Läuft schon eine Prüfung, startet keine zweite daneben."""
        if self._polling:
            return {"triggered": False, "feed_count": 0,
                    "message": "Es läuft bereits eine Prüfung"}
        subs = await db.fetch_all(
            """SELECT * FROM subscriptions WHERE enabled = 1
               ORDER BY last_checked ASC NULLS FIRST"""
        )
        if not subs:
            return {"triggered": False, "feed_count": 0, "message": "Keine aktiven Kanäle"}
        self._polling = True
        asyncio.create_task(self._process_batch_now([dict(s) for s in subs]))
        return {"triggered": True, "feed_count": len(subs)}

    async def _process_batch_now(self, subs: list[dict]):
        """Von Hand ausgelöste Prüfung aller Kanäle, sichtbar als Job."""
        try:
            self._clear_disturbance()
            job = await job_service.create(
                job_type="rss_cycle",
                title=f"Kanalprüfung von Hand ({len(subs)} Kanäle)",
                description="Alle aktiven Kanäle werden geprüft",
                metadata={"trigger": "manual", "batch_size": len(subs)},
                priority=8,
            )
            await job_service.start(job["id"])
            async with job_service.guard(job["id"]):
                outcome = await self._check_feeds(job["id"], subs, adaptive=False)
                if not job_service.is_cancelled(job["id"]):
                    await job_service.complete(job["id"], outcome["message"])
            if outcome["new_videos"] > 0:
                from app.routers.jobs import activity_ws
                await activity_ws.broadcast(
                    {"type": "feed_updated", "new_videos": outcome["new_videos"]})
        except Exception as e:
            logger.error(f"Kanalprüfung von Hand fehlgeschlagen: {e}", exc_info=True)
        finally:
            self._polling = False

    async def get_stats(self) -> dict:
        total_subs = await db.fetch_val("SELECT COUNT(*) FROM subscriptions") or 0
        enabled_subs = await db.fetch_val("SELECT COUNT(*) FROM subscriptions WHERE enabled = 1") or 0
        new_videos = await db.fetch_val(
            f"SELECT COUNT(*) FROM rss_entries r WHERE {feed_scope.new_entry('r')}") or 0
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
            "auto_dl_today": await self._auto_dl_count_today(),
            "auto_dl_limit": int(await self._get_setting("rss.auto_dl_daily_limit")
                                 or AUTO_DL_DAILY_LIMIT),
            "auto_dl_pending": await db.fetch_val(
                "SELECT COUNT(*) FROM rss_entries WHERE auto_pending = 1") or 0,
        }

    async def get_scheduler_status(self) -> dict:
        """Aktueller Scheduler-Status für Frontend-Anzeige – volle Transparenz."""
        # Gesamtstatistiken
        total = await db.fetch_val("SELECT COUNT(*) FROM subscriptions") or 0
        enabled = await db.fetch_val("SELECT COUNT(*) FROM subscriptions WHERE enabled = 1") or 0
        checked = await db.fetch_val("SELECT COUNT(*) FROM subscriptions WHERE last_checked IS NOT NULL") or 0
        unchecked = await db.fetch_val("SELECT COUNT(*) FROM subscriptions WHERE last_checked IS NULL AND enabled = 1") or 0
        with_errors = await db.fetch_val("SELECT COUNT(*) FROM subscriptions WHERE error_count > 0") or 0
        disabled = total - enabled

        # Fällige Feeds
        pending = await self._pending_count()

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
        auto_dl_channels = await db.fetch_val(
            "SELECT COUNT(*) FROM subscriptions WHERE auto_download = 1 AND enabled = 1") or 0
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
            "polling": self._polling,
            "last_tick": self._last_tick or None,
            "disturbance": {
                "active": self._disturbance_pause_left() > 0,
                "pause_seconds_left": self._disturbance_pause_left(),
                "reason": self._disturbance_reason,
            },
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
                # Es gibt keinen globalen Schalter: aktiv ist Auto-Download,
                # sobald mindestens ein Kanal ihn eingeschaltet hat.
                "enabled": auto_dl_channels > 0,
                "channels": auto_dl_channels,
                "today_count": await self._auto_dl_count_today(),
                "daily_limit": int(daily_limit),
                "pending": await db.fetch_val(
                    "SELECT COUNT(*) FROM rss_entries WHERE auto_pending = 1") or 0,
            },
            # Aktive Einstellungen
            "active_settings": {
                "max_age_days": int(max_age),
                "default_interval": int(interval),
                "max_interval": (await self._intervals())[1],
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

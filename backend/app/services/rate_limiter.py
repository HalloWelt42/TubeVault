"""
TubeVault – Rate Limiter v1.7.2
Globales Rate-Limiting für alle YouTube-Anfragen
© HalloWelt42 – Private Nutzung

Kategorien + Standard-Limits:
- rss:           0.5s  (RSS XML, harmlos, öffentlich)
- pytubefix:     5.0s  (Scraping, Sperr-Gefahr!)
- avatar:        3.0s  (Avatar per pytubefix, Sperr-Gefahr)
- channel_scan:  5.0s  (Channel.videos, sehr gefährlich)
- thumbnail:     1.0s  (Bild-Downloads)
- download:      3.0s  (Video-Download Start)

Features:
- Exponential Backoff bei Fehlern (verdoppelt bis max 120s)
- Reset auf Standard nach Erfolg
- Manuell deaktivierbar (disabled=True → kein Delay)
- Unterscheidung: YouTube-Rate-Limit vs. normale Fehler (Video unavailable etc.)
- YouTube-LED zeigt ECHTEN YouTube-Block, nicht internen Limiter
"""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

DEFAULT_INTERVALS = {
    "rss": 0.5,
    "pytubefix": 5.0,
    "avatar": 3.0,
    "channel_scan": 5.0,
    "thumbnail": 1.0,
    "download": 3.0,
}

MAX_BACKOFF = 120.0

# Keywords die auf echtes YouTube-Rate-Limiting hindeuten
RATE_LIMIT_KEYWORDS = (
    "429", "too many requests", "rate limit", "throttl",
    "retries exceeded", "forbidden", "http error 403",
)


class RateLimiter:
    """Token-Bucket Rate Limiter mit Backoff, Stats und Disable-Modus."""

    def __init__(self):
        self._last_request: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self.intervals: dict[str, float] = {**DEFAULT_INTERVALS}
        self._stats: dict[str, dict] = {}
        self._error_counts: dict[str, int] = {}
        self._yt_block_count: int = 0      # Echte YouTube-Blocks (429 etc.)
        self._yt_block_last: float = 0.0   # Timestamp des letzten Blocks
        self.disabled: bool = False

    def _get_lock(self, category: str) -> asyncio.Lock:
        if category not in self._locks:
            self._locks[category] = asyncio.Lock()
        return self._locks[category]

    async def acquire(self, category: str):
        """Warten bis nächste Anfrage erlaubt ist."""
        if self.disabled:
            self._track(category, "requests")
            return
        lock = self._get_lock(category)
        async with lock:
            interval = self.intervals.get(category, 1.0)
            last = self._last_request.get(category, 0)
            elapsed = time.time() - last
            if elapsed < interval:
                await asyncio.sleep(interval - elapsed)
            self._last_request[category] = time.time()
            self._track(category, "requests")

    def success(self, category: str):
        """Nach erfolgreicher Anfrage: Backoff reset."""
        self._error_counts[category] = 0
        default = DEFAULT_INTERVALS.get(category, 1.0)
        if self.intervals.get(category, default) > default:
            self.intervals[category] = default
            logger.info(f"Rate limit '{category}': Backoff aufgehoben → {default}s")
        self._track(category, "successes")

    def error(self, category: str, error_msg: str = "") -> float:
        """Nach Fehler: Nur bei echtem YouTube-Rate-Limit Backoff verdoppeln.
        Normale Fehler (video unavailable, age restricted, private) triggern KEINEN Backoff.
        Gibt aktuelles Interval zurück."""
        self._track(category, "errors")

        # Prüfen ob es ein ECHTES YouTube-Rate-Limit ist
        is_rate_limit = error_msg and any(kw in error_msg.lower() for kw in RATE_LIMIT_KEYWORDS)

        if is_rate_limit:
            # NUR bei echtem Rate-Limit: Backoff verdoppeln
            self._error_counts[category] = self._error_counts.get(category, 0) + 1
            current = self.intervals.get(category, 1.0)
            new = min(current * 2.0, MAX_BACKOFF)
            self.intervals[category] = new
            self._yt_block_count += 1
            self._yt_block_last = time.time()
            self._track(category, "yt_blocks")
            logger.warning(f"YouTube RATE-LIMIT '{category}': Backoff → {new:.1f}s | {error_msg[:120]}")
            return new
        else:
            # Normale Fehler: KEIN Backoff, nur loggen
            logger.debug(f"Rate limit '{category}': Normaler Fehler (kein Backoff) | {error_msg[:120]}")
            return self.intervals.get(category, DEFAULT_INTERVALS.get(category, 1.0))

    def _track(self, category: str, event: str):
        if category not in self._stats:
            self._stats[category] = {
                "requests": 0, "errors": 0, "successes": 0, "yt_blocks": 0
            }
        self._stats[category][event] = self._stats[category].get(event, 0) + 1

    def is_youtube_healthy(self) -> bool:
        """YouTube-Gesundheit: basiert auf ECHTEN YouTube-Blocks (429 etc.),
        NICHT auf normalen Fehlern (Video unavailable, private etc.)."""
        if self._yt_block_last > 0:
            since_last = time.time() - self._yt_block_last
            if since_last < 600:  # 10 Minuten
                return False
        return True

    def get_stats(self) -> dict:
        """Stats fuer System-Endpoint / Frontend."""
        result = {}
        for cat in {**DEFAULT_INTERVALS, **self.intervals}:
            default = DEFAULT_INTERVALS.get(cat, 1.0)
            current = self.intervals.get(cat, default)
            s = self._stats.get(cat, {})
            result[cat] = {
                "interval_current": current,
                "interval_default": default,
                "in_backoff": current > default,
                "error_count": self._error_counts.get(cat, 0),
                "yt_blocks": s.get("yt_blocks", 0),
                **(self._stats.get(cat, {})),
            }
        return result

    def reset(self, category: str = None):
        """Backoff manuell zuruecksetzen. Ohne Kategorie: alles reset."""
        if category:
            default = DEFAULT_INTERVALS.get(category, 1.0)
            self.intervals[category] = default
            self._error_counts[category] = 0
            if category in self._stats:
                self._stats[category] = {
                    "requests": 0, "errors": 0, "successes": 0, "yt_blocks": 0
                }
            logger.info(f"Rate limit '{category}': manuell zurueckgesetzt -> {default}s")
        else:
            for cat in list(self.intervals.keys()):
                self.intervals[cat] = DEFAULT_INTERVALS.get(cat, 1.0)
            self._error_counts.clear()
            self._stats.clear()
            self._yt_block_count = 0
            self._yt_block_last = 0.0
            logger.info("Rate limit: ALLE Kategorien manuell zurueckgesetzt")


rate_limiter = RateLimiter()

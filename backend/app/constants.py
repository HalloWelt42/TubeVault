"""
TubeVault – Zentrale Konstanten

Settings-Keys und Default-Werte an EINER Stelle, damit Typos nicht
drei Module auseinanderlaufen lassen. Enumartige Struktur statt nakedter
Strings macht auch Auto-Complete in IDEs möglich.
"""


class SettingsKeys:
    """Setting-Keys in der DB. Das komplette Inventar der key-Strings."""

    # ── Download-Verhalten ────────────────────────────────
    DOWNLOAD_QUALITY = "download.quality"
    DOWNLOAD_FORMAT = "download.format"
    DOWNLOAD_CONCURRENT = "download.concurrent"
    DOWNLOAD_AUTO_THUMBNAIL = "download.auto_thumbnail"
    DOWNLOAD_AUTO_SUBTITLE = "download.auto_subtitle"
    DOWNLOAD_SUBTITLE_LANG = "download.subtitle_lang"
    DOWNLOAD_AUTO_CHAPTERS = "download.auto_chapters"

    # ── Cooldown + Throttle (Live-Einstellungen) ──────────
    DOWNLOAD_COOLDOWN_BASE_S = "download.cooldown_base_s"
    DOWNLOAD_THROTTLE_KBPS = "download.throttle_kbps"
    DOWNLOAD_THROTTLE_REALTIME = "download.throttle_realtime"

    # ── Queue / System ────────────────────────────────────
    QUEUE_PAUSED = "queue.paused"
    QUEUE_PAUSE_REASON = "queue.pause_reason"


class Defaults:
    """Default-Werte und Grenzen. Statt Magic-Numbers an vielen Stellen."""

    # Cooldown (Sekunden zwischen Downloads)
    COOLDOWN_BASE_S = 30
    COOLDOWN_MIN_S = 5           # Endpoint-Clamp, 0 = scheint wie aus
    COOLDOWN_MAX_S = 3600        # 1h, Router-Clamp
    COOLDOWN_HARD_MAX_S = 7200   # 2h, ab wo Queue in harte Pause geht

    # Throttle
    THROTTLE_KBPS_MAX = 100000   # 100 MB/s clamp im Endpoint
    THROTTLE_REALTIME_OVERHEAD = 1.2   # Download 20% schneller als Wiedergabe
    THROTTLE_MIN_BYTES_S = 32 * 1024   # Minimum bei realtime (yt-dlp Overhead)

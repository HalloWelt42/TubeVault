"""
TubeVault – File Utilities v1.5.54
© HalloWelt42 – Private Nutzung
"""

import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Zeitstempel in der Datenbank sind IMMER Weltzeit (UTC) ohne Zonenangabe -
# genau wie SQLites datetime('now'). Vorher lieferte now_sqlite() die Ortszeit
# des Rechners; verglichen wurde aber gegen datetime('now'). Das passte nur,
# solange der Container zufällig auf UTC lief. Die Oberfläche rechnet beim
# Anzeigen in Ortszeit um (format.js: parseServerTime).
_FORMAT = "%Y-%m-%d %H:%M:%S"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def now_sqlite() -> str:
    """Jetzt als Datenbank-Zeitstempel (UTC, Leerzeichen statt T, ohne Mikrosekunden)."""
    return utc_now().strftime(_FORMAT)


def future_sqlite(seconds: int = 0, minutes: int = 0, hours: int = 0, days: int = 0) -> str:
    """Datenbank-Zeitstempel in der Zukunft (UTC)."""
    dt = utc_now() + timedelta(seconds=seconds, minutes=minutes, hours=hours, days=days)
    return dt.strftime(_FORMAT)


def past_sqlite(seconds: int = 0, minutes: int = 0, hours: int = 0, days: int = 0) -> str:
    """Datenbank-Zeitstempel in der Vergangenheit (UTC)."""
    dt = utc_now() - timedelta(seconds=seconds, minutes=minutes, hours=hours, days=days)
    return dt.strftime(_FORMAT)


# Nächtliches Zeitfenster des Drip (Ortszeit des Rechners, Stunden)
DRIP_WINDOW_HOURS = (2, 9)


def next_drip_run() -> str:
    """Zufälliger Zeitpunkt morgen im nächtlichen Zeitfenster, als
    Datenbank-Zeitstempel (UTC). Das Fenster gilt in ORTSZEIT - dafür muss
    der Rechner bzw. Container seine Zeitzone kennen (TZ)."""
    import random
    local_now = datetime.now().astimezone()
    tomorrow = (local_now + timedelta(days=1)).replace(
        hour=random.randint(*DRIP_WINDOW_HOURS), minute=random.randint(0, 59), second=0, microsecond=0)
    return tomorrow.astimezone(timezone.utc).strftime(_FORMAT)


# Arbeitsdateien eines Downloads - nie ein fertiges Video
WORK_FILE_SUFFIXES = (".part", ".ytdl")
# Kleiner ist keine Mediendatei, sondern ein Rest (Statusdatei, abgebrochener Lauf)
MIN_MEDIA_BYTES = 1024


def is_media_file(path) -> bool:
    """True, wenn unter path eine brauchbare Mediendatei liegt.
    Die eine Regel für "Video hat eine Datei" (Start-Prüfung, Bereinigung)."""
    if not path:
        return False
    p = Path(path)
    try:
        return (p.is_file() and p.suffix not in WORK_FILE_SUFFIXES
                and p.stat().st_size >= MIN_MEDIA_BYTES)
    except OSError:
        return False


def human_size(size_bytes: int) -> str:
    """Bytes in lesbare Größe konvertieren."""
    if size_bytes < 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def human_duration(seconds: int) -> str:
    """Sekunden in lesbare Dauer konvertieren."""
    if seconds < 0:
        return "0:00"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def get_disk_usage(path: str = "/") -> dict:
    """Festplatten-Nutzung abrufen."""
    try:
        usage = shutil.disk_usage(path)
        return {
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "percent": round(usage.used / usage.total * 100, 1) if usage.total > 0 else 0,
            "total_human": human_size(usage.total),
            "used_human": human_size(usage.used),
            "free_human": human_size(usage.free),
        }
    except Exception:
        return {
            "total": 0, "used": 0, "free": 0, "percent": 0,
            "total_human": "N/A", "used_human": "N/A", "free_human": "N/A",
        }


def get_directory_size(path: Path) -> int:
    """Gesamtgröße eines Verzeichnisses in Bytes."""
    total = 0
    if path.exists():
        for entry in path.rglob("*"):
            if entry.is_file():
                total += entry.stat().st_size
    return total


def sanitize_filename(name: str) -> str:
    """Dateinamen bereinigen."""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, "_")
    return name.strip(". ")[:200]

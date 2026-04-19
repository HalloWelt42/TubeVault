"""
TubeVault – File Utilities v1.5.54
© HalloWelt42 – Private Nutzung
"""

import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path


def now_sqlite() -> str:
    """SQLite-kompatibles Timestamp (Space statt T, ohne Mikrosekunden)."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def future_sqlite(seconds: int = 0, minutes: int = 0, hours: int = 0, days: int = 0) -> str:
    """SQLite-kompatibles Timestamp in der Zukunft."""
    dt = datetime.now() + timedelta(seconds=seconds, minutes=minutes, hours=hours, days=days)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def past_sqlite(seconds: int = 0, minutes: int = 0, hours: int = 0, days: int = 0) -> str:
    """SQLite-kompatibles Timestamp in der Vergangenheit."""
    dt = datetime.now() - timedelta(seconds=seconds, minutes=minutes, hours=hours, days=days)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


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

"""
TubeVault -  Endpoint Service v1.8.38
Zentraler Zugriff auf konfigurierbare Service-URLs aus api_endpoints.
Alle externen Dienste lesen ihre Base-URL hierüber.
Fallback auf hardcoded Default falls DB nicht erreichbar.
© HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
"""

import logging
from app.database import db

logger = logging.getLogger(__name__)

# Hardcoded Fallbacks -  werden NUR genutzt wenn DB-Lookup fehlschlägt
_DEFAULTS = {
    "ryd_api": "https://returnyoutubedislikeapi.com",
    "lrclib_api": "https://lrclib.net/api",
    "sponsorblock_api": "https://sponsor.ajay.app",
    "youtube_rss": "https://www.youtube.com",
    "youtube_thumbs": "https://i.ytimg.com",
    "backend_api": "http://localhost:8031",
}


async def get_service_url(name: str) -> str | None:
    """Service-URL aus api_endpoints lesen.
    Gibt None zurück wenn der Service deaktiviert ist.
    Gibt die URL zurück wenn aktiv (aus DB oder Fallback).
    """
    try:
        row = await db.fetch_one(
            "SELECT url, enabled FROM api_endpoints WHERE name = ?", (name,)
        )
        if row:
            if not row["enabled"]:
                return None  # Service deaktiviert
            return row["url"].rstrip("/")
    except Exception as e:
        logger.debug(f"Endpoint-Lookup '{name}' fehlgeschlagen: {e}")

    # Fallback
    default = _DEFAULTS.get(name)
    return default.rstrip("/") if default else None


async def is_service_enabled(name: str) -> bool:
    """Prüft ob ein Service aktiviert ist."""
    try:
        row = await db.fetch_one(
            "SELECT enabled FROM api_endpoints WHERE name = ?", (name,)
        )
        if row:
            return bool(row["enabled"])
    except Exception:
        pass
    return True  # Default: aktiv

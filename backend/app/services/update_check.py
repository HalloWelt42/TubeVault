"""
TubeVault - Hinweis auf eine neue Version

Wer TubeVault selbst betreibt, soll im Kopf der Oberfläche sehen, dass eine
neue Version erschienen ist (Wunsch 15.10.2026). Dazu liest dieser Dienst
alle CHECK_INTERVAL_S die Versionsdatei des öffentlichen Projekts: eine
kleine Datei, ohne Konto und ohne Schlüssel. Abschaltbar (SWITCH). Die
Oberfläche fragt nur den hier gemerkten Stand ab, nie selbst nach draußen.
"""
import asyncio
import logging
import re
import time
from typing import Optional

import httpx
from pydantic import BaseModel

from app.config import VERSION
from app.services import setting_values

logger = logging.getLogger(__name__)

SWITCH = "system.update_check"
PROJECT_URL = "https://github.com/HalloWelt42/TubeVault"
VERSION_URL = "https://raw.githubusercontent.com/HalloWelt42/TubeVault/main/version.json"

CHECK_INTERVAL_S = 6 * 3600
RETRY_S = 30 * 60          # nach einem Fehlschlag früher noch einmal
WAKE_S = 5 * 60            # so oft sieht die Schleife nach dem Schalter
START_DELAY_S = 60
TIMEOUT_S = 10


class UpdateStatus(BaseModel):
    current: str
    latest: Optional[str] = None       # zuletzt gelesene Version des Projekts
    available: bool = False            # latest ist neuer als current
    url: str = PROJECT_URL
    checked_at: Optional[float] = None
    enabled: bool = True


_latest: Optional[str] = None
_checked_at: Optional[float] = None


def version_key(text: str) -> tuple[int, ...]:
    """'2.67.3' -> (2, 67, 3); Teile ohne Ziffern zählen als 0."""
    return tuple(int(match.group()) if (match := re.match(r"\d+", part)) else 0
                 for part in str(text).strip().split("."))


def is_newer(latest: str, current: str) -> bool:
    return version_key(latest) > version_key(current)


async def fetch_latest() -> str:
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        response = await client.get(VERSION_URL)
        response.raise_for_status()
        return str(response.json()["version"])


async def check() -> bool:
    """Liest die Version des Projekts; False, wenn das gerade nicht ging."""
    global _latest, _checked_at
    try:
        latest = await fetch_latest()
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
        logger.info(f"[UPDATE] Projektversion nicht lesbar: {e}")
        return False
    _latest, _checked_at = latest, time.time()
    if is_newer(latest, VERSION):
        logger.info(f"[UPDATE] Neue Version {latest} verfügbar (hier läuft {VERSION})")
    return True


async def status() -> UpdateStatus:
    enabled = await setting_values.is_on(SWITCH)
    if not enabled:
        return UpdateStatus(current=VERSION, enabled=False)
    return UpdateStatus(current=VERSION, latest=_latest, checked_at=_checked_at,
                        available=_latest is not None and is_newer(_latest, VERSION))


async def loop() -> None:
    await asyncio.sleep(START_DELAY_S)
    next_try = 0.0
    while True:
        try:
            if await setting_values.is_on(SWITCH) and time.time() >= next_try:
                next_try = time.time() + (CHECK_INTERVAL_S if await check() else RETRY_S)
        except Exception as e:
            logger.error(f"[UPDATE] Fehler: {e}", exc_info=True)
        await asyncio.sleep(WAKE_S)

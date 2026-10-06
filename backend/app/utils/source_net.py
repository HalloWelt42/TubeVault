"""
TubeVault – Netzweg zu den Video-Quellen

Über welche Adressfamilie Abrufe bei der Quelle laufen (Seiten, Listen,
Vorschaubilder, Videos). Die Quelle sperrt einzelne Adressen unterschiedlich
und zeitweise: Am Anschluss des Pi wurde erst die IPv4-Adresse abgewiesen
(429), Tage später die IPv6-Adresse ("Sign in to confirm you're not a bot"),
während die jeweils andere sofort durchkam. Gegen eine gesperrte Adresse hilft
weder ein Token noch ein anderer Abspieler - nur der andere Weg.

Deshalb: Meldet die Quelle eine Bot-Sperre, gilt die gerade benutzte Familie
für eine Weile als gesperrt und alle Abrufe nehmen die andere. Danach geht es
wieder auf die eingestellte zurück.

Einstellung über die Umgebung (docker-compose.yml):
    TUBEVAULT_SOURCE_IP           "6" IPv6 bevorzugt, "4" IPv4 bevorzugt,
                                  "" das Betriebssystem entscheidet (dann
                                  wird nicht ausgewichen)
    TUBEVAULT_SOURCE_BLOCK_HOURS  wie lange eine gesperrte Familie gemieden
                                  wird (Standard 6)

Alle Abrufe bei der Quelle holen sich ihre Verbindung hier, damit der Weg an
einer Stelle festgelegt ist.
"""
import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_BIND = {"6": "::", "4": "0.0.0.0"}
_OTHER = {"6": "4", "4": "6"}
# Familie -> Zeitpunkt (time.time), bis zu dem sie gemieden wird
_blocked_until: dict[str, float] = {}


def preferred_family() -> str:
    """Eingestellte Adressfamilie: "6", "4" oder "" (automatisch)."""
    return os.getenv("TUBEVAULT_SOURCE_IP", "").strip()


def block_seconds() -> float:
    return float(os.getenv("TUBEVAULT_SOURCE_BLOCK_HOURS", "6")) * 3600


def _is_blocked(fam: str) -> bool:
    return _blocked_until.get(fam, 0) > time.time()


def family() -> str:
    """Familie, über die jetzt abgerufen wird: die eingestellte, solange sie
    nicht gesperrt ist; sonst die andere. Sind beide gesperrt, die, deren
    Sperre zuerst abläuft."""
    preferred = preferred_family()
    if preferred not in _OTHER or not _is_blocked(preferred):
        return preferred
    other = _OTHER[preferred]
    if not _is_blocked(other):
        return other
    return min((preferred, other), key=lambda fam: _blocked_until[fam])


def report_bot_block() -> None:
    """Die Quelle hat einen Abruf als Bot abgewiesen: die benutzte Familie
    eine Weile meiden. Gilt sofort auch für laufende Wiederholungen."""
    current = family()
    if current not in _OTHER:
        return
    _blocked_until[current] = time.time() + block_seconds()
    logger.warning(f"[NETZWEG] Quelle sperrt IPv{current} (Bot-Verdacht) - "
                   f"Abrufe laufen jetzt über IPv{family()}")


def bind_address() -> Optional[str]:
    """Lokale Adresse, an die Abrufe gebunden werden (None = automatisch)."""
    return _BIND.get(family())


def ydl_options() -> dict:
    """Ergänzung für die Optionen des Abrufwerkzeugs (gilt für alle seine Verbindungen)."""
    address = bind_address()
    return {"source_address": address} if address else {}


def async_client(**kwargs) -> httpx.AsyncClient:
    """httpx-Client für Abrufe bei der Quelle."""
    address = bind_address()
    if address:
        kwargs["transport"] = httpx.AsyncHTTPTransport(local_address=address)
    return httpx.AsyncClient(**kwargs)


def client(**kwargs) -> httpx.Client:
    """Wie async_client, synchron (für Abrufe in Hintergrund-Threads)."""
    address = bind_address()
    if address:
        kwargs["transport"] = httpx.HTTPTransport(local_address=address)
    return httpx.Client(**kwargs)

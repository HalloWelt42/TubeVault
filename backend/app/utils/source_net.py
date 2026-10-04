"""
TubeVault – Netzweg zu den Video-Quellen

Über welche Adressfamilie Abrufe bei der Quelle laufen (Seiten, Listen,
Untertitel, Vorschaubilder, Videos). Die Quelle sperrt einzelne Adressen
unterschiedlich: Am Anschluss des Pi wurde die IPv4-Adresse für Untertitel
dauerhaft abgewiesen (429), über IPv6 kam derselbe Abruf sofort durch.

Einstellung über die Umgebung (docker-compose.yml):
    TUBEVAULT_SOURCE_IP = "6"  nur IPv6
                          "4"  nur IPv4
                          ""   das Betriebssystem entscheidet (Standard)

Alle Abrufe bei der Quelle holen sich ihre Verbindung hier, damit der Weg an
einer Stelle festgelegt ist.
"""
import os
from typing import Optional

import httpx

_BIND = {"6": "::", "4": "0.0.0.0"}


def family() -> str:
    """Eingestellte Adressfamilie: "6", "4" oder "" (automatisch)."""
    return os.getenv("TUBEVAULT_SOURCE_IP", "").strip()


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

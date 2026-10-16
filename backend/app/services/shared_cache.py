"""
TubeVault - Geteilte Ergebnisse teurer Abfragen

Mehrere Fenster und Geräte fragen dieselben Übersichten alle paar Sekunden
ab (Badges der Seitenleiste, Hintergrundarbeiten). Gemessen 16.10.2026 auf
dem Pi: Jede dieser Abfragen belegte die eine Datenbankverbindung 0,5 bis
1,1 s, je Fenster rund ein Drittel der Zeit - andere Anfragen warteten
dahinter 2 bis 5 s (db_watch, background_work).

Hier rechnet je Schlüssel höchstens ein Aufruf: Läuft die Rechnung schon,
warten weitere Aufrufer auf dasselbe Ergebnis; ein fertiges gilt ttl_s
Sekunden. Was sich langsam ändert (Fortschrittszahlen), darf länger gelten
als, was der Nutzer sofort sehen will.
"""
import asyncio
import time
from typing import Any, Awaitable, Callable

_values: dict[str, tuple[float, Any]] = {}
_running: dict[str, asyncio.Future] = {}


async def cached(key: str, ttl_s: float, compute: Callable[[], Awaitable[Any]]) -> Any:
    """Ergebnis von compute(), höchstens alle ttl_s Sekunden neu gerechnet."""
    hit = _values.get(key)
    if hit and time.monotonic() - hit[0] < ttl_s:
        return hit[1]
    running = _running.get(key)
    if running is None:
        running = asyncio.ensure_future(compute())
        _running[key] = running
        running.add_done_callback(lambda task: _finish(key, task))
    # shield: bricht ein Aufrufer ab, rechnet es für die anderen weiter
    return await asyncio.shield(running)


def _finish(key: str, task: asyncio.Future) -> None:
    if _running.get(key) is task:
        del _running[key]
    if not task.cancelled() and task.exception() is None:
        _values[key] = (time.monotonic(), task.result())


def forget(key: str) -> None:
    """Gilt sofort als veraltet (z.B. nach einer Änderung durch den Nutzer)."""
    _values.pop(key, None)


def clear() -> None:
    _values.clear()

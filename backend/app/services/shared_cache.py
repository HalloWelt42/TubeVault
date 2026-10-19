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

for_version: statt einer Frist gilt ein Ergebnis, solange sein Stand gleich
ist (z.B. der Datenstand der Datenbank, Database.data_version) - nie veraltet,
und ohne Änderung nie neu gerechnet.
"""
import asyncio
import time
from typing import Any, Awaitable, Callable

_values: dict[str, tuple[float, Any]] = {}
_running: dict[str, asyncio.Future] = {}
_versioned: dict[str, tuple[Any, Any]] = {}                    # Schlüssel -> (Stand, Ergebnis)
_running_versions: dict[str, tuple[Any, asyncio.Future]] = {}


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


async def for_version(key: str, version: Any, compute: Callable[[], Awaitable[Any]]) -> Any:
    """Ergebnis von compute(), neu gerechnet nur, wenn version sich geändert hat."""
    hit = _versioned.get(key)
    if hit and hit[0] == version:
        return hit[1]
    running = _running_versions.get(key)
    if running is None or running[0] != version:
        task = asyncio.ensure_future(compute())
        running = (version, task)
        _running_versions[key] = running
        task.add_done_callback(lambda done: _finish_version(key, version, done))
    return await asyncio.shield(running[1])


def _finish_version(key: str, version: Any, task: asyncio.Future) -> None:
    running = _running_versions.get(key)
    if running and running[1] is task:
        del _running_versions[key]
    if not task.cancelled() and task.exception() is None:
        _versioned[key] = (version, task.result())


def forget(key: str) -> None:
    """Gilt sofort als veraltet (z.B. nach einer Änderung durch den Nutzer)."""
    _values.pop(key, None)
    _versioned.pop(key, None)


def clear() -> None:
    _values.clear()
    _versioned.clear()
    _running_versions.clear()

"""
Geteilte Ergebnisse (app/services/shared_cache).

Kontrakt: Je Schlüssel rechnet höchstens ein Aufruf; gleichzeitige Aufrufer
bekommen dasselbe Ergebnis, ein fertiges gilt ttl_s Sekunden; ein Fehler
wird nicht gemerkt; ein abbrechender Aufrufer bricht die Rechnung der
anderen nicht ab.
"""
import asyncio

import pytest

from app.services import shared_cache


async def test_gleichzeitige_aufrufer_teilen_eine_rechnung():
    calls = []

    async def compute():
        calls.append(1)
        await asyncio.sleep(0.05)
        return len(calls)
    results = await asyncio.gather(*(shared_cache.cached("k", 10, compute) for _ in range(5)))
    assert results == [1] * 5 and len(calls) == 1
    assert await shared_cache.cached("k", 10, compute) == 1            # gilt noch
    assert await shared_cache.cached("k", 0, compute) == 2             # abgelaufen: neu


async def test_fehler_wird_nicht_gemerkt():
    async def broken():
        raise RuntimeError("kaputt")
    with pytest.raises(RuntimeError):
        await shared_cache.cached("f", 10, broken)

    async def fine():
        return 7
    assert await shared_cache.cached("f", 10, fine) == 7


async def test_abbruch_eines_aufrufers_trifft_die_anderen_nicht():
    async def slow():
        await asyncio.sleep(0.05)
        return "fertig"
    first = asyncio.ensure_future(shared_cache.cached("s", 10, slow))
    second = asyncio.ensure_future(shared_cache.cached("s", 10, slow))
    await asyncio.sleep(0.01)
    first.cancel()
    assert await second == "fertig"

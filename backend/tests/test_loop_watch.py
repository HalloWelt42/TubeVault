"""
Wächter der Ereignisschleife (app/services/loop_watch).

Kontrakt: Hängt die Schleife, meldet der Wächter das im Moment des Hängens
samt der Stelle, an der die Schleife steht, und danach die Dauer.
"""
import asyncio
import logging
import time

from app.services import loop_watch


async def test_haenger_wird_mit_stelle_gemeldet(monkeypatch, caplog):
    monkeypatch.setattr(loop_watch, "LAG_WARN_S", 0.3)
    monkeypatch.setattr(loop_watch, "REPORT_GAP_S", 0)
    caplog.set_level(logging.WARNING, logger="loop_watch")
    task = asyncio.create_task(loop_watch.loop())
    await asyncio.sleep(0.6)

    def blockiert_die_schleife():
        time.sleep(1.5)                      # synchron in der Schleife
    blockiert_die_schleife()
    await asyncio.sleep(1.2)
    task.cancel()

    texts = [record.getMessage() for record in caplog.records]
    hang = next(text for text in texts if text.startswith("Ereignisschleife hängt"))
    assert "Ereignisschleife: " in hang and "blockiert_die_schleife" in hang
    assert any(text.startswith("Ereignisschleife lief nach") for text in texts)

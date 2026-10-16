"""
Wächter der Datenbank (app/services/db_watch).

Kontrakt: Ein langer Schritt an der einen Verbindung steht im Live-Log mit
Dauer, SQL und auslösender Stelle; wer dahinter warten musste, zählt in der
Zusammenfassung der Wartezeiten.
"""
import asyncio
import logging

from app.services import db_watch

SLOW_SQL = ("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 400000) "
            "SELECT COUNT(*) FROM c")


async def test_langer_schritt_und_wartende(test_db, monkeypatch, caplog):
    monkeypatch.setattr(db_watch, "SLOW_RUN_S", 0.01)
    monkeypatch.setattr(db_watch, "SLOW_WAIT_S", 0.0)
    monkeypatch.setattr(db_watch, "SUMMARY_S", 0)
    monkeypatch.setattr(db_watch, "_last_report", {})
    caplog.set_level(logging.WARNING, logger="db_watch")

    async def lange_abfrage():
        return await test_db.fetch_val(SLOW_SQL)

    async def kurze_abfrage():
        return await test_db.fetch_val("SELECT 1")

    results = await asyncio.gather(lange_abfrage(), kurze_abfrage())
    assert results == [400000, 1]
    texts = [record.getMessage() for record in caplog.records]
    slow = next(text for text in texts if text.startswith("Datenbank: execute lief"))
    assert "WITH RECURSIVE" in slow and "lange_abfrage" in slow
    assert any("warteten über" in text for text in texts)


async def test_messen_verhindert_nie_eine_abfrage(test_db, monkeypatch):
    # Früher: Aufrufer ohne Pfad (z.B. "<string>") ließ die Abfrage scheitern
    def kaputt():
        raise IndexError("kaputt")
    monkeypatch.setattr(db_watch, "_caller", kaputt)
    assert await test_db.fetch_val("SELECT 42") == 42
    code = compile("import asyncio\nresult = asyncio.ensure_future(db.fetch_val('SELECT 7'))", "<string>", "exec")
    scope = {"db": test_db}
    monkeypatch.undo()
    exec(code, scope)
    assert await scope["result"] == 7

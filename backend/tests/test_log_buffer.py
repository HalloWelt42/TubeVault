"""
Tests für den LogBuffer (Phase 4 – Log-Fixes).

Pin-Punkte:
- Jeder Eintrag trägt epoch (numerisch) + seq (monoton steigend) –
  Grundlage für Mitternachts-feste Statistik und Reconnect-Dedup im Terminal.
- Mehrzeilige Meldungen (Tracebacks) werden in msg (1. Zeile) + trace getrennt.
- errors_last_hour zählt numerisch über epoch (kein Mitternachts-Bug mehr).
- Jede Verbindung liest mit eigenem Lesezeiger (boot + seq): nach einem
  Neustart beginnt das Terminal neu, statt alles zu verwerfen; was aus dem
  Ring gefallen ist, wird genau gezählt (gap).
- Gelingende lesende Abfragen sind DEBUG, Änderungen INFO.
- Meldungen aus dem Browser werden geprüft (Stufe, Länge, Anzahl).
- Unbehandelte Fehler eines Endpunkts erscheinen mit Traceback im Live-Log.
"""
import logging
import sys
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.routers import system
from app.routers.system import FrontendLogEntry, LogBuffer, compute_log_stats


def make_buffer() -> LogBuffer:
    """Frischer, isolierter Buffer (nicht der globale Handler)."""
    lb = LogBuffer(maxlen=100)
    lb.setFormatter(logging.Formatter("%(message)s"))
    return lb


def rec(msg: str, level: int = logging.INFO, exc_info=None,
        name: str = "test_service") -> logging.LogRecord:
    return logging.LogRecord(
        name=name, level=level, pathname=__file__, lineno=1,
        msg=msg, args=(), exc_info=exc_info)


class TestEintragFelder:
    def test_emit_setzt_epoch_und_monotone_seq(self):
        lb = make_buffer()
        lb.emit(rec("hallo"))
        lb.emit(rec("welt"))
        e1, e2 = list(lb.buffer)
        assert isinstance(e1["epoch"], float) and e1["epoch"] > 0
        assert e2["seq"] == e1["seq"] + 1
        assert e1["ts"].count(":") == 2  # Anzeige bleibt HH:MM:SS

    def test_alle_push_wege_haben_epoch_und_seq(self):
        lb = make_buffer()
        lb.push_api("GET", "/api/x", 200, 12.5)
        lb.push_event("system", "INFO", "test", "ereignis")
        lb.push_frontend([FrontendLogEntry(msg="aus dem browser")])
        assert len(lb.buffer) == 3
        for e in lb.buffer:
            assert e["epoch"] > 0
            assert e["seq"] > 0


class TestTraceTrennung:
    def test_traceback_landet_in_trace_nicht_in_msg(self):
        lb = make_buffer()
        try:
            raise ValueError("kaputt")
        except ValueError:
            lb.emit(rec("Fehler passiert", level=logging.ERROR,
                        exc_info=sys.exc_info()))
        e = list(lb.buffer)[-1]
        assert e["msg"] == "Fehler passiert"
        assert "\n" not in e["msg"]
        assert "Traceback" in e.get("trace", "")
        assert "ValueError" in e["trace"]

    def test_einzeilige_meldung_hat_kein_trace_feld(self):
        lb = make_buffer()
        lb.emit(rec("nur eine zeile"))
        assert "trace" not in list(lb.buffer)[-1]


class TestErrorsLastHour:
    def test_zaehlt_ueber_mitternacht_korrekt(self):
        # Simuliert die Mitternachts-Situation: der frische Fehler hat den
        # lexikografisch KLEINEREN ts-String ("00:05" < Cutoff "23:30"), der
        # alte den groesseren. Ein String-Vergleich zaehlt genau falsch herum;
        # die epoch-Zaehlung muss den frischen zaehlen, den alten nicht.
        now = time.time()
        entries = [
            {"level": "ERROR", "epoch": now - 60, "ts": "00:05:00", "cat": "backend"},
            {"level": "ERROR", "epoch": now - 7200, "ts": "23:59:00", "cat": "backend"},
            {"level": "INFO", "epoch": now - 30, "ts": "00:06:00", "cat": "api"},
        ]
        stats = compute_log_stats(entries, now=now)
        assert stats["errors_last_hour"] == 1
        assert stats["total"] == 3
        assert stats["by_level"]["ERROR"] == 2
        assert stats["by_category"]["backend"] == 2

    def test_critical_zaehlt_auch(self):
        now = time.time()
        entries = [{"level": "CRITICAL", "epoch": now - 10, "ts": "x", "cat": "backend"}]
        assert compute_log_stats(entries, now=now)["errors_last_hour"] == 1


class TestLesezeiger:
    def test_eintraege_nach_einer_nummer_und_luecke(self):
        lb = make_buffer()                       # Ring mit 100 Plätzen
        for i in range(130):
            lb.push_event("system", "INFO", "t", f"m{i}")
        entries, gap = lb.entries_after(120, limit=50)
        assert [e["seq"] for e in entries] == list(range(121, 131)) and gap == 0
        entries, gap = lb.entries_after(10, limit=5)
        assert [e["seq"] for e in entries] == [31, 32, 33, 34, 35]
        assert gap == 20                         # 11 bis 30 sind aus dem Ring gefallen

    def test_jeder_prozess_hat_eine_eigene_kennung(self):
        assert make_buffer().boot != make_buffer().boot

    def test_lesende_abfragen_sind_debug(self):
        lb = make_buffer()
        lb.push_api("GET", "/api/jobs", 200, 3)
        lb.push_api("POST", "/api/downloads", 200, 30)
        lb.push_api("GET", "/api/x", 404, 3)
        assert [e["level"] for e in lb.buffer] == ["DEBUG", "INFO", "WARNING"]


class TestBrowserMeldungen:
    def test_stufen_werden_vereinheitlicht(self):
        assert FrontendLogEntry(level="warn", msg="x").level == "WARNING"
        assert FrontendLogEntry(level="error", msg="x").level == "ERROR"

    def test_unpassendes_wird_abgelehnt(self):
        with pytest.raises(ValidationError):
            FrontendLogEntry(level="laut", msg="x")
        with pytest.raises(ValidationError):
            FrontendLogEntry(msg="x" * 2001)
        with pytest.raises(ValidationError):
            FrontendLogEntry(msg={"objekt": 1})

    def test_hoechstens_50_je_aufruf(self):
        app = FastAPI()
        app.include_router(system.router)
        client = TestClient(app)
        assert client.post("/api/system/logs/frontend", json=[{"msg": "a"}] * 50).json() == {"accepted": 50}
        assert client.post("/api/system/logs/frontend", json=[{"msg": "a"}] * 51).status_code == 422


class TestStrom:
    @pytest.fixture
    def client(self, monkeypatch):
        lb = make_buffer()
        monkeypatch.setattr(system, "log_buffer", lb)
        app = FastAPI()
        app.include_router(system.router)
        return TestClient(app), lb

    def test_neues_terminal_bekommt_den_verlauf(self, client):
        test_client, lb = client
        for i in range(3):
            lb.push_event("system", "INFO", "t", f"m{i}")
        with test_client.websocket_connect("/api/system/ws/logs") as ws:
            frame = ws.receive_json()
        assert frame["boot"] == lb.boot and frame["gap"] == 0 and "restarted" not in frame
        assert [e["msg"] for e in frame["entries"]] == ["m0", "m1", "m2"]

    def test_nach_neustart_beginnt_das_terminal_neu(self, client):
        # Vorher verwarf das Terminal alles mit kleinerer Nummer als vor dem Neustart
        test_client, lb = client
        lb.push_event("system", "INFO", "t", "nach dem Neustart")
        with test_client.websocket_connect("/api/system/ws/logs?boot=altesboot&after=5000") as ws:
            frame = ws.receive_json()
        assert frame["restarted"] is True and frame["entries"][0]["msg"] == "nach dem Neustart"

    def test_wiederverbinden_setzt_fort(self, client):
        test_client, lb = client
        for i in range(4):
            lb.push_event("system", "INFO", "t", f"m{i}")
        with test_client.websocket_connect(f"/api/system/ws/logs?boot={lb.boot}&after=2") as ws:
            frame = ws.receive_json()
        assert [e["seq"] for e in frame["entries"]] == [3, 4] and "restarted" not in frame


def test_unbehandelter_fehler_erscheint_im_live_log(monkeypatch):
    from app.main import APIAccessLogMiddleware
    lb = make_buffer()
    monkeypatch.setattr(system, "log_buffer", lb)
    logging.getLogger().addHandler(lb)
    try:
        app = FastAPI()
        app.add_middleware(APIAccessLogMiddleware)

        @app.get("/api/kaputt")
        async def kaputt():
            raise ValueError("Absicht")

        assert TestClient(app, raise_server_exceptions=False).get("/api/kaputt").status_code == 500
    finally:
        logging.getLogger().removeHandler(lb)
    error = next(e for e in lb.buffer if e["level"] == "ERROR" and e["cat"] != "api")
    assert "GET /api/kaputt" in error["msg"] and "ValueError: Absicht" in error["trace"]
    assert any(e["cat"] == "api" and e.get("status") == 500 for e in lb.buffer)

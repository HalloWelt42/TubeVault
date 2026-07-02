"""
Tests für den LogBuffer (Phase 4 – Log-Fixes).

Pin-Punkte:
- Jeder Eintrag trägt epoch (numerisch) + seq (monoton steigend) –
  Grundlage für Mitternachts-feste Statistik und Reconnect-Dedup im Terminal.
- Mehrzeilige Meldungen (Tracebacks) werden in msg (1. Zeile) + trace getrennt.
- errors_last_hour zählt numerisch über epoch (kein Mitternachts-Bug mehr).
- WS-Sende-Puffer verwirft nicht mehr still: Überlauf wird gezählt und als
  Warn-Marker in den Stream gestellt.
"""
import logging
import sys
import time

from app.routers.system import LogBuffer, compute_log_stats


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
        lb.push_frontend([{"msg": "aus dem browser"}])
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


class TestSendePufferUeberlauf:
    def test_ueberlauf_wird_gezaehlt_statt_still_verworfen(self):
        lb = make_buffer()
        lb.connections.append(object())  # simuliert verbundenes Terminal
        cap = lb._pending.maxlen
        for i in range(cap + 25):
            lb.push_event("system", "INFO", "t", f"m{i}")
        assert lb._dropped == 25

    def test_marker_wird_dem_batch_vorangestellt(self):
        lb = make_buffer()
        lb.connections.append(object())
        for i in range(lb._pending.maxlen + 5):
            lb.push_event("system", "INFO", "t", f"m{i}")
        batch = lb._drain_batch(limit=10)
        assert "übersprungen" in batch[0]["msg"]
        assert batch[0]["level"] == "WARNING"
        assert lb._dropped == 0  # zurückgesetzt

    def test_ohne_ueberlauf_kein_marker(self):
        lb = make_buffer()
        lb.connections.append(object())
        lb.push_event("system", "INFO", "t", "eins")
        batch = lb._drain_batch(limit=10)
        assert len(batch) == 1
        assert batch[0]["msg"] == "eins"

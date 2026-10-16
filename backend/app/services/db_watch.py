"""
TubeVault - Wächter der Datenbank

Messbefund 16.10.2026: Mehrere Endpunkte brauchten in derselben Sekunde 2,5
bis 5,5 s, ohne dass die Ereignisschleife hing (loop_watch meldete nichts).
Verdacht: Es gibt EINE Verbindung zur Datenbank (aiosqlite); alle Abfragen
laufen nacheinander in ihrem Faden, eine lange lässt alle anderen warten.

Gemessen wird dort, wo die Arbeit wirklich geschieht: an der Warteschlange
von aiosqlite (_execute). Je Schritt (Abfrage ausführen, Ergebnis lesen,
festschreiben) zählt, wie lange er lief und wie lange er davor wartete.
  - Läuft ein Schritt länger als SLOW_RUN_S, steht er im Live-Log: Dauer,
    SQL (gekürzt) und die Stelle im Code, die ihn ausgelöst hat - je
    Abfrage höchstens einmal je REPORT_GAP_S.
  - Wartezeiten über SLOW_WAIT_S fasst eine Meldung je SUMMARY_S zusammen.
"""
import logging
import sys
import time
from typing import Optional

logger = logging.getLogger("db_watch")

SLOW_RUN_S = 0.5
SLOW_WAIT_S = 1.0
REPORT_GAP_S = 60
SUMMARY_S = 60
SQL_CHARS = 220

_IGNORED_FILES = ("/aiosqlite/", "/app/database.py", "/app/services/db_watch.py", "/asyncio/")

_last_report: dict[str, float] = {}
_cursor_sql: dict[int, str] = {}
_waits = {"count": 0, "longest": 0.0, "since": time.monotonic()}


_place: dict = {}      # Code-Objekt -> "ordner/datei" bzw. None (übersprungen); je Ort einmal gerechnet


def _caller() -> str:
    """Erste Stelle im App-Code außerhalb von Datenbank-Hülle und aiosqlite."""
    frame = sys._getframe(2)
    while frame:
        code = frame.f_code
        place = _place.get(code, False)
        if place is False:
            name = code.co_filename.replace("\\", "/")
            place = None if any(part in name for part in _IGNORED_FILES) else "/".join(name.split("/")[-2:])
            if len(_place) > 5000:
                _place.clear()
            _place[code] = place
        if place:
            return f"{place}:{frame.f_lineno} {code.co_name}"
        frame = frame.f_back
    return "unbekannt"


def _describe(fn, args) -> tuple[str, Optional[str]]:
    """(Art des Schritts, SQL) aus dem, was aiosqlite ausführen soll."""
    name = getattr(fn, "__name__", "aufruf")
    if name in ("execute", "executemany", "executescript") and args and isinstance(args[0], str):
        return name, " ".join(args[0].split())
    owner = getattr(fn, "__self__", None)
    if name in ("fetchall", "fetchone", "fetchmany") and owner is not None:
        return "Ergebnis lesen", _cursor_sql.get(id(owner))
    return name, None


def _note(kind: str, sql: Optional[str], caller: str, run_s: float, wait_s: float) -> None:
    now = time.monotonic()
    if wait_s >= SLOW_WAIT_S:
        _waits["count"] += 1
        _waits["longest"] = max(_waits["longest"], wait_s)
    if now - _waits["since"] >= SUMMARY_S:
        if _waits["count"]:
            logger.warning(f"Datenbank: {_waits['count']} Schritte warteten über {SLOW_WAIT_S:g} s "
                           f"auf die Verbindung (längste {_waits['longest']:.1f} s)")
        _waits.update(count=0, longest=0.0, since=now)
    if run_s < SLOW_RUN_S:
        return
    key = f"{kind}:{(sql or '')[:120]}"
    if now - _last_report.get(key, 0) < REPORT_GAP_S:
        return
    _last_report[key] = now
    if len(_last_report) > 500:
        cutoff = now - REPORT_GAP_S
        for stale in [k for k, t in _last_report.items() if t < cutoff]:
            del _last_report[stale]
    text = (sql or "")[:SQL_CHARS] + ("..." if sql and len(sql) > SQL_CHARS else "")
    logger.warning(f"Datenbank: {kind} lief {run_s:.1f} s (wartete {wait_s:.1f} s) - {caller}\n{text}")


def install(connection) -> None:
    """Die Warteschlange einer aiosqlite-Verbindung vermessen (einmal je Verbindung)."""
    if getattr(connection, "_db_watch", False):
        return
    original = connection._execute

    async def timed(fn, *args, **kwargs):
        queued = time.monotonic()
        try:
            caller = _caller()
            kind, sql = _describe(fn, args)
        except Exception:                    # Messen darf eine Abfrage nie verhindern
            caller, kind, sql = "unbekannt", "aufruf", None
        marks = {}

        def run():
            marks["start"] = time.monotonic()
            try:
                result = fn(*args, **kwargs)
            finally:
                marks["end"] = time.monotonic()
            if sql and kind == "execute":
                if len(_cursor_sql) > 2000:
                    _cursor_sql.clear()
                _cursor_sql[id(result)] = sql
            return result

        try:
            return await original(run)
        finally:
            if "start" in marks:
                try:
                    _note(kind, sql, caller, marks["end"] - marks["start"], marks["start"] - queued)
                except Exception:
                    pass

    connection._execute = timed
    connection._db_watch = True

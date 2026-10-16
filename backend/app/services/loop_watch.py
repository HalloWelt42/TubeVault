"""
TubeVault - Wächter der Ereignisschleife

Messbefund 16.10.2026 (Live-Log am Pi): Beim Start eines Downloads brauchten
vier verschiedene Endpunkte in derselben Sekunde 4 bis 6,5 s - etwas hält
die ganze Ereignisschleife an. Die bekannten schweren Teile laufen schon in
Threads; Verdacht ist rechenlastiger Python-Code in einem Thread, der die
Interpretersperre (GIL) hält. Statt zu raten, misst dieser Wächter:

Die Schleife schlägt alle TICK_S einen Herzschlag (loop). Ein eigener Thread
schaut nach; bleibt der Herzschlag länger als LAG_WARN_S aus, hält er fest,
wo die Schleife und alle anderen Threads gerade stehen - im Moment des
Hängens, nicht danach - und meldet es im Live-Log. Läuft die Schleife
wieder, folgt die Dauer. Höchstens eine Meldung alle REPORT_GAP_S.
"""
import asyncio
import logging
import sys
import threading
import time
import traceback

logger = logging.getLogger("loop_watch")

TICK_S = 0.5
CHECK_S = 0.25
LAG_WARN_S = 1.5
REPORT_GAP_S = 30
FRAMES = 5              # so viele Aufrufstellen je Thread

_beat = time.monotonic()
_watcher: threading.Thread | None = None
_running = threading.Event()        # Herzschlag läuft; ohne ihn beendet sich der Wächter


def thread_snapshot(loop_thread: int) -> str:
    """Wo stehen die Threads gerade? Wartende ohne Arbeit fallen weg."""
    names = {thread.ident: thread.name for thread in threading.enumerate()}
    own = threading.get_ident()
    lines = []
    for ident, frame in sys._current_frames().items():
        if ident == own:
            continue
        stack = traceback.extract_stack(frame)[-FRAMES:]
        idle = all(any(part in entry.filename for part in ("threading.py", "concurrent/futures", "selectors.py", "queue.py"))
                   for entry in stack)
        if idle and ident != loop_thread:
            continue
        name = "Ereignisschleife" if ident == loop_thread else names.get(ident, str(ident))
        where = " <- ".join(f"{entry.filename.rsplit('/', 2)[-1]}:{entry.lineno} {entry.name}" for entry in reversed(stack))
        lines.append(f"{name}: {where}")
    return "\n".join(lines)


def _watch(loop_thread: int) -> None:
    last_report = 0.0
    stall_start = None
    while _running.is_set():
        time.sleep(CHECK_S)
        silent = time.monotonic() - _beat - TICK_S
        if silent >= LAG_WARN_S and stall_start is None:
            stall_start = _beat
            if time.monotonic() - last_report >= REPORT_GAP_S:
                last_report = time.monotonic()
                logger.warning(f"Ereignisschleife hängt seit {silent:.1f} s\n{thread_snapshot(loop_thread)}")
            else:
                stall_start = -1.0                      # nicht gemeldet, auch das Ende nicht
        elif silent < LAG_WARN_S and stall_start is not None:
            if stall_start >= 0:
                logger.warning(f"Ereignisschleife lief nach {_beat - stall_start:.1f} s weiter")
            stall_start = None


async def loop() -> None:
    """Herzschlag in der Ereignisschleife; startet einmal den Wächter-Thread."""
    global _beat, _watcher
    _beat = time.monotonic()
    _running.set()
    if _watcher is None or not _watcher.is_alive():
        _watcher = threading.Thread(target=_watch, args=(threading.get_ident(),), name="loop-watch", daemon=True)
        _watcher.start()
    try:
        while True:
            _beat = time.monotonic()
            await asyncio.sleep(TICK_S)
    finally:
        _running.clear()

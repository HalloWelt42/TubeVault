"""
TubeVault -  Task Manager v1.8.94
Zentrale Verwaltung aller Hintergrund-Tasks.
Stop/Restart via API, Auto-Restart bei Crash.
© HalloWelt42 -  Private Nutzung
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class ManagedTask:
    """Ein verwalteter Hintergrund-Task."""
    name: str
    label: str                                   # Anzeigename
    factory: Callable[[], Awaitable]             # Async-Funktion die den Task erzeugt
    auto_restart: bool = True                    # Bei Crash neu starten?
    essential: bool = True                       # Essentiell für den Betrieb?
    task: Optional[asyncio.Task] = field(default=None, repr=False)
    started_at: float = 0.0
    stopped_at: float = 0.0
    crash_count: int = 0
    last_error: str = ""
    manually_stopped: bool = False               # Vom User gestoppt → kein Auto-Restart

    @property
    def status(self) -> str:
        if self.task is None:
            return "stopped"
        if self.task.done():
            if self.task.cancelled():
                return "stopped"
            exc = self.task.exception() if not self.task.cancelled() else None
            if exc:
                return "crashed"
            return "completed"
        return "running"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "status": self.status,
            "auto_restart": self.auto_restart,
            "essential": self.essential,
            "manually_stopped": self.manually_stopped,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "uptime_seconds": round(time.time() - self.started_at) if self.status == "running" else 0,
            "crash_count": self.crash_count,
            "last_error": self.last_error,
        }


class TaskManager:
    """Verwaltet alle Hintergrund-Tasks mit Lifecycle-Management."""

    def __init__(self):
        self._tasks: dict[str, ManagedTask] = {}
        self._monitor_task: Optional[asyncio.Task] = None

    def register(self, name: str, label: str, factory: Callable[[], Awaitable],
                 auto_restart: bool = True, essential: bool = True) -> ManagedTask:
        """Task registrieren (startet noch nicht)."""
        mt = ManagedTask(
            name=name, label=label, factory=factory,
            auto_restart=auto_restart, essential=essential,
        )
        self._tasks[name] = mt
        return mt

    async def start(self, name: str) -> bool:
        """Einzelnen Task starten."""
        mt = self._tasks.get(name)
        if not mt:
            return False
        if mt.status == "running":
            return True  # Läuft bereits
        mt.manually_stopped = False
        mt.task = asyncio.create_task(self._run_wrapped(mt), name=f"tv:{name}")
        mt.started_at = time.time()
        logger.info(f"[TaskMgr] ▶ {mt.label} gestartet")
        return True

    async def stop(self, name: str) -> bool:
        """Einzelnen Task stoppen."""
        mt = self._tasks.get(name)
        if not mt or not mt.task:
            return False
        mt.manually_stopped = True
        mt.task.cancel()
        try:
            await mt.task
        except asyncio.CancelledError:
            pass
        mt.stopped_at = time.time()
        logger.info(f"[TaskMgr] ⏹ {mt.label} gestoppt")
        return True

    async def restart(self, name: str) -> bool:
        """Task stoppen und neu starten."""
        await self.stop(name)
        await asyncio.sleep(0.5)
        return await self.start(name)

    async def start_all(self):
        """Alle registrierten Tasks starten + Monitor."""
        for name in self._tasks:
            await self.start(name)
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop_all(self):
        """Alle Tasks stoppen."""
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        for name in list(self._tasks.keys()):
            mt = self._tasks[name]
            mt.manually_stopped = True  # Kein Auto-Restart beim Shutdown
            if mt.task and not mt.task.done():
                mt.task.cancel()
                try:
                    await mt.task
                except asyncio.CancelledError:
                    pass

    def list_tasks(self) -> list[dict]:
        """Alle Tasks als Liste von Dicts."""
        return [mt.to_dict() for mt in self._tasks.values()]

    def get(self, name: str) -> Optional[ManagedTask]:
        return self._tasks.get(name)

    async def _run_wrapped(self, mt: ManagedTask):
        """Wrapper der Exceptions fängt für Status-Tracking."""
        try:
            await mt.factory()
        except asyncio.CancelledError:
            raise  # Normal bei Stop
        except Exception as e:
            mt.crash_count += 1
            mt.last_error = f"{type(e).__name__}: {str(e)[:200]}"
            mt.stopped_at = time.time()
            logger.error(f"[TaskMgr] 💥 {mt.label} gecrasht: {mt.last_error}")
            raise

    async def _monitor_loop(self):
        """Alle 30s prüfen ob Tasks gecrasht sind → Auto-Restart."""
        await asyncio.sleep(30)
        while True:
            try:
                for mt in self._tasks.values():
                    if mt.status in ("crashed", "completed") and mt.auto_restart and not mt.manually_stopped:
                        # Backoff: 5s, 10s, 20s, 40s, max 120s
                        delay = min(5 * (2 ** min(mt.crash_count - 1, 4)), 120)
                        since_crash = time.time() - mt.stopped_at
                        if since_crash >= delay:
                            logger.info(f"[TaskMgr] 🔄 Auto-Restart: {mt.label} (Crash #{mt.crash_count})")
                            mt.task = asyncio.create_task(
                                self._run_wrapped(mt), name=f"tv:{mt.name}")
                            mt.started_at = time.time()
            except Exception as e:
                logger.error(f"[TaskMgr] Monitor-Fehler: {e}")
            await asyncio.sleep(30)


# Singleton
task_manager = TaskManager()

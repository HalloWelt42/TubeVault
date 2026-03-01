"""
TubeVault -  Job Service v1.6.36
Zentrales Job-System mit Stale-Recovery, Auto-Cleanup, Abbruch und Pause/Resume
© HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0

Job-Typen:
- download:      Video-Download
- rss_cycle:     RSS-Gesamtzyklus (manuell ausgelöst)
- import:        Batch-Import Abos
- avatar_fetch:  Avatar-Downloads (resume-fähig)
- channel_scan:  Alle Videos eines Kanals (manuell, pytubefix!)
- archive_scan:  Externes Archiv durchsuchen
- cleanup:       Speicher-Bereinigung

Status-Flow: queued → active → done | error | cancelled
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Callable

from app.database import db
from app.utils.file_utils import now_sqlite

logger = logging.getLogger(__name__)


class JobService:
    """Zentraler Job-Manager mit Echtzeit-Updates und Abbruch-Unterstützung.
    Nur EIN Job gleichzeitig aktiv (Semaphore)."""

    def __init__(self):
        self._callbacks: list[Callable] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cancelled: set[int] = set()  # Job-IDs die abgebrochen werden sollen
        self._paused_jobs: set[int] = set()  # Job-IDs die pausiert sind
        self._semaphore: Optional[asyncio.Semaphore] = None  # Max 1 Job gleichzeitig
        self._queue_task: Optional[asyncio.Task] = None
        self._sem_held_by: set[int] = set()  # Job-IDs die Semaphore halten
        # Pause-System: Queue-Verarbeitung anhalten
        self._paused: bool = False
        self._pause_reason: str = ""  # 'user' oder 'rate_limit'
        self._paused_at: Optional[str] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def add_callback(self, cb: Callable):
        self._callbacks.append(cb)

    def remove_callback(self, cb: Callable):
        if cb in self._callbacks:
            self._callbacks.remove(cb)

    async def notify(self, job: dict):
        """Alle Listener über Job-Update informieren."""
        for cb in self._callbacks:
            try:
                await cb({"type": "job_update", "job": job})
            except Exception as e:
                logger.error(f"Job callback error: {e}")

    # ─── Lifecycle ───────────────────────────────────────

    def is_exclusive_running(self) -> bool:
        """Prüft ob ein exklusiver Job (Scan, Enrich, etc.) gerade läuft."""
        return len(self._sem_held_by) > 0

    async def is_any_job_active(self, exclude_job_id: int = None, exclude_types: list = None) -> bool:
        """Prüft ob IRGENDEIN Job aktiv ist (außer exclude_job_id und exclude_types).
        Zentrale Stelle: nie 2 Prozesse gleichzeitig."""
        q = "SELECT COUNT(*) FROM jobs WHERE status = 'active'"
        params = []
        if exclude_job_id:
            q += " AND id != ?"
            params.append(exclude_job_id)
        if exclude_types:
            placeholders = ",".join("?" * len(exclude_types))
            q += f" AND type NOT IN ({placeholders})"
            params.extend(exclude_types)
        count = await db.fetch_val(q, tuple(params))
        return count > 0

    async def wait_for_idle(self, exclude_job_id: int = None, timeout: int = 300, label: str = "", exclude_types: list = None):
        """Wartet bis kein anderer Job aktiv ist. Gibt True zurück wenn idle."""
        for _ in range(timeout // 3):
            if not await self.is_any_job_active(exclude_job_id, exclude_types=exclude_types):
                return True
            await asyncio.sleep(3)
        logger.warning(f"wait_for_idle timeout ({label}): andere Jobs laufen seit >{timeout}s")
        return False

    # ─── Pause / Resume ─────────────────────────────────

    async def pause_queue(self, reason: str = "user"):
        """Queue pausieren -  laufende Jobs laufen fertig, keine neuen starten."""
        self._paused = True
        self._pause_reason = reason
        self._paused_at = now_sqlite()
        # Persistieren (überlebt Container-Restart)
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('queue.paused', 'true')")
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('queue.pause_reason', ?)",
            (reason,))
        logger.warning(f"Queue PAUSIERT (Grund: {reason})")
        await self.notify({
            "id": 0, "type": "queue_paused",
            "status": "paused", "reason": reason,
            "paused_at": self._paused_at,
        })

    async def resume_queue(self):
        """Queue fortsetzen -  neue Jobs werden wieder gestartet."""
        was_paused = self._paused
        self._paused = False
        self._pause_reason = ""
        self._paused_at = None
        # Persistieren
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('queue.paused', 'false')")
        await db.execute("DELETE FROM settings WHERE key = 'queue.pause_reason'")
        if was_paused:
            logger.info("Queue FORTGESETZT")
            await self.notify({
                "id": 0, "type": "queue_resumed", "status": "resumed",
            })

    async def _restore_pause_state(self):
        """Pause-Status aus DB wiederherstellen (nach Restart)."""
        paused = await db.fetch_val("SELECT value FROM settings WHERE key = 'queue.paused'")
        if paused == "true":
            self._paused = True
            self._pause_reason = await db.fetch_val(
                "SELECT value FROM settings WHERE key = 'queue.pause_reason'") or "user"
            self._paused_at = now_sqlite()
            logger.info(f"[STARTUP] Queue war pausiert (Grund: {self._pause_reason}) -  bleibt pausiert")

    def is_paused(self) -> bool:
        """Prüft ob die Queue pausiert ist."""
        return self._paused

    def get_queue_status(self) -> dict:
        """Aktuellen Queue-Status zurückgeben."""
        return {
            "paused": self._paused,
            "pause_reason": self._pause_reason,
            "paused_at": self._paused_at,
        }

    async def startup(self):
        """Beim App-Start: stale Jobs recovern, Pause wiederherstellen, Cleanup starten."""
        self._semaphore = asyncio.Semaphore(1)  # Max 1 Job gleichzeitig
        await self._recover_stale_jobs()
        await self._restore_pause_state()
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Job Service: Stale-Recovery + Auto-Cleanup gestartet (max 1 concurrent)")

    async def shutdown(self):
        """Beim App-Stop: Cleanup-Task stoppen."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _recover_stale_jobs(self):
        """Jobs die beim letzten Crash 'active' waren → markieren.
        avatar_fetch Jobs werden von rss_service.resume_avatar_jobs() fortgesetzt.
        Andere Jobs werden als 'error' markiert (außer resumable).
        """
        stale = await db.fetch_all(
            "SELECT * FROM jobs WHERE status = 'active'"
        )
        for job_row in stale:
            job = dict(job_row)
            jtype = job["type"]

            # avatar_fetch: wird separat resumed (rss_service)
            if jtype == "avatar_fetch":
                logger.info(f"Job #{job['id']} ({jtype}): wird resumed")
                continue

            # Andere aktive Jobs: als unterbrochen markieren
            await db.execute(
                """UPDATE jobs SET status = 'error',
                   error_message = 'Unterbrochen durch Neustart -  Retry möglich',
                   completed_at = ?
                   WHERE id = ?""",
                (now_sqlite(), job["id"])
            )
            self._sem_held_by.discard(job["id"])  # Sicherheitshalber
            logger.info(f"Job #{job['id']} ({jtype}): nach Neustart als Fehler markiert")

    async def _cleanup_loop(self):
        """Alle 6h: alte fertige Jobs aufräumen."""
        while True:
            try:
                await asyncio.sleep(6 * 3600)  # 6 Stunden
                await self.cleanup(max_age_hours=48)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup-Loop Fehler: {e}")
                await asyncio.sleep(3600)

    # --- Job CRUD ---

    async def create(
        self,
        job_type: str,
        title: str,
        description: str = "",
        metadata: dict = None,
        parent_id: int = None,
        priority: int = 0,
    ) -> dict:
        """Neuen Job erstellen."""
        meta_json = json.dumps(metadata or {})
        cursor = await db.execute(
            """INSERT INTO jobs (type, title, description, metadata, parent_id, priority)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (job_type, title, description, meta_json, parent_id, priority)
        )
        job_id = cursor.lastrowid
        job = await self.get(job_id)
        logger.info(f"Job #{job_id} erstellt: [{job_type}] {title}")
        await self.notify(job)
        return job

    async def get(self, job_id: int) -> dict | None:
        """Job abrufen."""
        row = await db.fetch_one("SELECT * FROM jobs WHERE id = ?", (job_id,))
        return self._row_to_dict(row) if row else None

    async def start(self, job_id: int, exclusive: bool = True) -> dict:
        """Job als aktiv markieren.
        exclusive=True: wartet bis keine anderen Jobs aktiv sind + Semaphore.
        Download-Jobs sollten exclusive=False nutzen (eigene Queue)."""
        if exclusive:
            # Warten bis kein anderer Job aktiv ist
            await self.wait_for_idle(exclude_job_id=job_id, label=f"job#{job_id}")
            if self._semaphore:
                logger.info(f"Job #{job_id}: wartet auf Ausführungsslot…")
                await self._semaphore.acquire()
                self._sem_held_by.add(job_id)
                logger.info(f"Job #{job_id}: Slot erhalten, starte")

        now = now_sqlite()
        await db.execute(
            "UPDATE jobs SET status = 'active', started_at = ? WHERE id = ?",
            (now, job_id)
        )
        job = await self.get(job_id)
        await self.notify(job)
        return job

    def _release_semaphore(self, job_id: int):
        """Semaphore freigeben wenn dieser Job sie hält."""
        if job_id in self._sem_held_by:
            self._sem_held_by.discard(job_id)
            if self._semaphore:
                self._semaphore.release()
                logger.info(f"Job #{job_id}: Slot freigegeben")

    async def progress(self, job_id: int, progress: float, description: str = None, metadata: dict = None) -> dict:
        """Job-Fortschritt aktualisieren. Optional mit Metadata (für X/Y, ETA)."""
        fields = ["progress = ?"]
        params = [round(progress, 3)]
        if description:
            fields.append("description = ?")
            params.append(description)
        if metadata:
            # Bestehende Metadata mergen
            existing = await db.fetch_one("SELECT metadata FROM jobs WHERE id = ?", (job_id,))
            old_meta = {}
            if existing and existing["metadata"]:
                try:
                    old_meta = json.loads(existing["metadata"]) if isinstance(existing["metadata"], str) else existing["metadata"]
                except Exception:
                    pass
            old_meta.update(metadata)
            fields.append("metadata = ?")
            params.append(json.dumps(old_meta))
        params.append(job_id)
        await db.execute(
            f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?",
            tuple(params)
        )
        job = await self.get(job_id)
        await self.notify(job)
        return job

    async def complete(self, job_id: int, result: str = None) -> dict:
        """Job als abgeschlossen markieren."""
        now = now_sqlite()
        await db.execute(
            "UPDATE jobs SET status = 'done', progress = 1.0, result = ?, completed_at = ? WHERE id = ?",
            (result, now, job_id)
        )
        self._release_semaphore(job_id)
        job = await self.get(job_id)
        logger.info(f"Job #{job_id} abgeschlossen")
        await self.notify(job)
        return job

    async def fail(self, job_id: int, error: str) -> dict:
        """Job als fehlgeschlagen markieren."""
        now = now_sqlite()
        await db.execute(
            "UPDATE jobs SET status = 'error', error_message = ?, completed_at = ? WHERE id = ?",
            (error, now, job_id)
        )
        self._release_semaphore(job_id)
        job = await self.get(job_id)
        logger.error(f"Job #{job_id} fehlgeschlagen: {error}")
        await self.notify(job)
        return job

    async def cancel(self, job_id: int) -> dict:
        """Job abbrechen -  signalisiert laufenden Tasks den Abbruch."""
        self._cancelled.add(job_id)
        now = now_sqlite()
        await db.execute(
            "UPDATE jobs SET status = 'cancelled', completed_at = ? WHERE id = ? AND status IN ('queued', 'active')",
            (now, job_id)
        )
        self._release_semaphore(job_id)
        job = await self.get(job_id)
        await self.notify(job)
        return job

    def is_cancelled(self, job_id: int) -> bool:
        """Prüfen ob ein Job abgebrochen wurde."""
        return job_id in self._cancelled

    def clear_cancel(self, job_id: int):
        """Abbruch-Flag entfernen nach Abschluss."""
        self._cancelled.discard(job_id)

    def pause_job(self, job_id: int):
        """Einzelnen Job pausieren."""
        self._paused_jobs.add(job_id)

    def resume_job(self, job_id: int):
        """Einzelnen Job fortsetzen."""
        self._paused_jobs.discard(job_id)

    def is_job_paused(self, job_id: int) -> bool:
        """Prüfen ob Job pausiert ist."""
        return job_id in self._paused_jobs

    # --- Abfragen ---

    async def get_active(self, limit: int = 50) -> list[dict]:
        """Alle aktiven und wartenden Jobs."""
        rows = await db.fetch_all(
            """SELECT * FROM jobs WHERE status IN ('active', 'queued')
               ORDER BY status = 'active' DESC, priority DESC, created_at ASC
               LIMIT ?""",
            (limit,)
        )
        return [self._row_to_dict(r) for r in rows]

    async def get_recent(self, limit: int = 100, job_type: str = None) -> list[dict]:
        """Letzte Jobs (alle Status)."""
        if job_type:
            rows = await db.fetch_all(
                """SELECT * FROM jobs WHERE type = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (job_type, limit)
            )
        else:
            rows = await db.fetch_all(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
        return [self._row_to_dict(r) for r in rows]

    async def get_stats(self) -> dict:
        """Job-Statistiken inkl. Pause-Status."""
        active = await db.fetch_val("SELECT COUNT(*) FROM jobs WHERE status = 'active'")
        queued = await db.fetch_val("SELECT COUNT(*) FROM jobs WHERE status = 'queued'")
        done = await db.fetch_val("SELECT COUNT(*) FROM jobs WHERE status = 'done'")
        errors = await db.fetch_val("SELECT COUNT(*) FROM jobs WHERE status = 'error'")
        parked = await db.fetch_val("SELECT COUNT(*) FROM jobs WHERE status = 'parked'")
        return {
            "active": active,
            "queued": queued,
            "done": done,
            "errors": errors,
            "parked": parked or 0,
            "total": active + queued + done + errors + (parked or 0),
            "paused": self._paused,
            "pause_reason": self._pause_reason,
            "paused_at": self._paused_at,
        }

    async def cleanup(self, max_age_hours: int = 24):
        """Alte abgeschlossene Jobs löschen."""
        await db.execute(
            """DELETE FROM jobs WHERE status IN ('done', 'cancelled')
               AND completed_at < datetime('now', ? || ' hours')""",
            (f"-{max_age_hours}",)
        )

    async def cleanup_all(self) -> int:
        """ALLE abgeschlossenen/fehlerhaften/abgebrochenen Jobs löschen."""
        cursor = await db.execute(
            "DELETE FROM jobs WHERE status IN ('done', 'error', 'cancelled', 'parked')"
        )
        count = cursor.rowcount
        # Alle Listener informieren (UI aktualisieren)
        await self.notify({"id": 0, "type": "cleanup", "status": "cleanup"})
        return count

    # --- Exklusive Ausführung (max 1 Job gleichzeitig) ---

    async def run_exclusive(self, job_id: int, coro_fn, *args, **kwargs):
        """Job exklusiv ausführen -  wartet bis kein anderer Job läuft.
        coro_fn bekommt job_id als erstes Argument.
        Setzt Status automatisch: queued → active → done/error."""
        if not self._semaphore:
            self._semaphore = asyncio.Semaphore(1)

        # Warten bis frei
        job = await self.get(job_id)
        if job and job["status"] == "queued":
            logger.info(f"Job #{job_id} wartet auf Semaphore…")

        async with self._semaphore:
            if self.is_cancelled(job_id):
                self.clear_cancel(job_id)
                return

            await self.start(job_id, exclusive=False)
            try:
                result = await coro_fn(job_id, *args, **kwargs)
                result_str = str(result)[:500] if result else None
                await self.complete(job_id, result_str)
                return result
            except asyncio.CancelledError:
                await self.cancel(job_id)
            except Exception as e:
                await self.fail(job_id, str(e)[:500])
                logger.error(f"Job #{job_id} Fehler: {e}", exc_info=True)

    def schedule_exclusive(self, job_id: int, coro_fn, *args, **kwargs) -> asyncio.Task:
        """Job als Task schedulen mit exklusiver Ausführung."""
        return asyncio.create_task(
            self.run_exclusive(job_id, coro_fn, *args, **kwargs)
        )

    def _row_to_dict(self, row) -> dict:
        d = dict(row)
        if "metadata" in d and isinstance(d["metadata"], str):
            try:
                d["metadata"] = json.loads(d["metadata"])
            except (json.JSONDecodeError, TypeError):
                d["metadata"] = {}
        return d


# Singleton
job_service = JobService()

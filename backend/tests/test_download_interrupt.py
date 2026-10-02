"""Ein Neustart darf laufende Downloads nicht zu Fehlern machen."""
import asyncio

from app.services.download_service import download_service
from app.services.job_service import job_service
from app.services.rate_limiter import rate_limiter


async def test_unterbrochener_download_wird_wieder_eingereiht(test_db, monkeypatch):
    """Wird das Programm beendet, während ein Download läuft, steht der Auftrag
    danach wieder in der Warteschlange - nicht als "Unklarer Zustand" im Fehler."""
    monkeypatch.setattr(rate_limiter, "disabled", True)
    started = asyncio.Event()

    async def never_finishes(url):
        started.set()
        await asyncio.sleep(3600)
    monkeypatch.setattr(download_service, "_resolve", never_finishes)

    async def quiet(*args, **kwargs):
        return None
    monkeypatch.setattr(download_service, "_ws_broadcast", quiet)

    job = await job_service.create(
        job_type="download", title="Langer Kurs",
        metadata={"video_id": "langerkurs1", "url": "https://www.youtube.com/watch?v=langerkurs1",
                  "retry_count": 1})
    await job_service.start(job["id"], exclusive=False)

    row = dict(await test_db.fetch_one("SELECT * FROM jobs WHERE id = ?", (job["id"],)))
    task = asyncio.create_task(download_service._process(row))
    done, _ = await asyncio.wait({task, asyncio.ensure_future(started.wait())}, timeout=5, return_when=asyncio.FIRST_COMPLETED)
    assert started.is_set(), task.exception() if task.done() else "hängt vor dem Auflösen"
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    after = await job_service.get(job["id"])
    assert after["status"] == "queued" and after["error_message"] is None
    assert after["metadata"]["retry_count"] == 1          # zählt nicht als Fehlversuch
    assert "langerkurs1" not in download_service._inflight_videos

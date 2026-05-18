"""
Tests für die Members-Only-Auto-Ignore-Logik.

Kontrakt:
- Wenn ein Video als Members-Only erkannt wurde, wird es in ignored_videos
  eingetragen und der Job auf 'error' gesetzt – kein retry_wait mehr.
- Vor jedem Job-Start prüft download_service ob die video_id ignoriert ist;
  wenn ja, wird der Job sofort beendet ohne YouTube-Call.
- ignored_videos enthält die channel_id für UI-Filterung pro Channel.
"""
import json
import pytest


@pytest.fixture
async def video_in_db(test_db):
    """Video + dazu passender Job, damit der Worker etwas hat."""
    await test_db.execute(
        "INSERT INTO videos (id, title, channel_id, status) VALUES (?, ?, ?, 'pending')",
        ("memvid12345", "Test", "UCtestchannel"),
    )
    cur = await test_db.execute(
        """INSERT INTO jobs (type, title, status, metadata, created_at)
           VALUES ('download', 'Test', 'queued', ?, datetime('now'))""",
        (json.dumps({"video_id": "memvid12345", "url": "https://youtube.com/watch?v=memvid12345"}),),
    )
    return {"video_id": "memvid12345", "job_id": cur.lastrowid}


async def test_pre_check_deletes_job_for_ignored_video(test_db, video_in_db):
    """Wenn video_id in ignored_videos: _process LÖSCHT den Job (kein
    rote Karte in der Queue, sondern weg)."""
    from app.services.download_service import download_service
    await test_db.execute(
        "INSERT INTO ignored_videos (video_id, channel_id, reason) VALUES (?, ?, ?)",
        (video_in_db["video_id"], "UCtestchannel", "members-only · test"),
    )
    item = await test_db.fetch_one(
        "SELECT id, metadata FROM jobs WHERE id = ?", (video_in_db["job_id"],)
    )
    await download_service._process(dict(item))

    # Job ist GELÖSCHT, nicht im Status 'error'
    job = await test_db.fetch_one(
        "SELECT id FROM jobs WHERE id = ?", (video_in_db["job_id"],)
    )
    assert job is None, "Pre-Check muss den Job löschen, nicht nur Status setzen"


async def test_pre_check_lets_normal_jobs_pass(test_db, video_in_db, monkeypatch):
    """Nicht-ignorierte Jobs laufen NICHT in den Skip – Pre-Check ist
    nur für Einträge in ignored_videos aktiv."""
    from app.services.download_service import download_service
    # Wir wollen NICHT den ganzen Download laufen lassen – wir patchen
    # die nächste Stage, damit der Test schnell endet
    called = {"resolve": False}

    async def fake_resolve(url):
        called["resolve"] = True
        raise RuntimeError("STOP_HERE")  # gestoppt nach dem Pre-Check

    monkeypatch.setattr(download_service, "_resolve", fake_resolve)
    item = await test_db.fetch_one(
        "SELECT id, metadata FROM jobs WHERE id = ?", (video_in_db["job_id"],)
    )
    try:
        await download_service._process(dict(item))
    except Exception:
        pass
    # Stage 1 (resolve) wurde gestartet → Pre-Check hat NICHT geblockt
    assert called["resolve"] is True


async def test_ignored_videos_get_ids_helper(test_db):
    """Helper aus ignored_videos.py liefert Set für RSS-Filter."""
    from app.routers.ignored_videos import get_ignored_ids
    await test_db.execute(
        "INSERT INTO ignored_videos (video_id, reason) VALUES (?, ?)",
        ("alpha111111", "members-only"),
    )
    await test_db.execute(
        "INSERT INTO ignored_videos (video_id, reason) VALUES (?, ?)",
        ("beta2222222", "members-only"),
    )
    ids = await get_ignored_ids()
    assert "alpha111111" in ids
    assert "beta2222222" in ids

"""
Reuploads: dasselbe Video unter neuer ID wird nicht noch einmal geladen.

Kontrakt:
- Gleich ist ein fertig geladenes Video desselben Kanals mit gleichem Titel
  (ohne "Reupload", Schreibweise egal) und gleicher Dauer (+-2 s).
- Anderer Kanal, andere Dauer oder ein nicht fertiges Video zählen nicht.
- Der Download-Auftrag endet als erledigt, ohne zu laden; er nennt das
  vorhandene Video, der Feed-Eintrag gilt als erledigt.
"""
import json

from app.services import download_service as ds_mod
from app.services import reupload_guard as guard
from app.services.download_service import download_service

NEW = "neuneuneu01"
OLD = "altaltalt01"
TITLE = "Avus - Rennstrecke und Legende | Doku HD | ARTE"


async def _video(test_db, vid=OLD, channel="UCarte", title=TITLE, duration=3151, status="ready"):
    await test_db.execute(
        "INSERT INTO videos (id, title, channel_id, duration, status) VALUES (?, ?, ?, ?, ?)",
        (vid, title, channel, duration, status))


def test_titel_ohne_reupload_und_schreibweise():
    assert guard.comparable_title("Avus - Rennstrecke und Legende | Doku HD Reupload | ARTE") \
        == guard.comparable_title("avus -  Rennstrecke und Legende | Doku HD | ARTE")
    assert guard.comparable_title("Reuploader erklärt") != guard.comparable_title("erklärt")


async def test_findet_denselben_upload(test_db):
    await _video(test_db)
    twin = await guard.find_twin(NEW, "UCarte", TITLE.replace("HD", "HD Reupload"), 3152)
    assert twin and twin.id == OLD


async def test_anderes_ist_kein_zwilling(test_db):
    await _video(test_db)
    assert await guard.find_twin(NEW, "UCanders", TITLE, 3151) is None      # anderer Kanal
    assert await guard.find_twin(NEW, "UCarte", TITLE, 3160) is None        # andere Dauer
    assert await guard.find_twin(NEW, "UCarte", "Anderer Titel", 3151) is None
    assert await guard.find_twin(OLD, "UCarte", TITLE, 3151) is None        # das Video selbst
    assert await guard.find_twin(NEW, "UCarte", TITLE, None) is None        # Dauer unbekannt


async def test_nicht_fertige_videos_zaehlen_nicht(test_db):
    await _video(test_db, status="metadata")
    assert await guard.find_twin(NEW, "UCarte", TITLE, 3151) is None


async def test_download_ueberspringt_reupload(test_db, monkeypatch):
    async def _noop(*a, **k):
        return None

    async def _resolve(url):
        return {"title": TITLE.replace("HD", "HD Reupload"), "channel_name": "ARTE",
                "channel_id": "UCarte", "duration": 3151, "stream_count": 3}

    async def _must_not_load(*a, **k):
        raise AssertionError("Reupload darf nicht geladen werden")

    monkeypatch.setattr(ds_mod.rate_limiter, "acquire", _noop)
    monkeypatch.setattr(download_service, "_ws_broadcast", _noop)
    monkeypatch.setattr(download_service, "_resolve", _resolve)
    monkeypatch.setattr(download_service, "_download", _must_not_load)
    await _video(test_db)
    await test_db.execute(
        "INSERT INTO rss_entries (video_id, channel_id, title) VALUES (?, 'UCarte', ?)", (NEW, TITLE))

    queued = await download_service.add_to_queue(f"https://www.youtube.com/watch?v={NEW}", origin="auto")
    job = dict(await test_db.fetch_one("SELECT * FROM jobs WHERE id = ?", (queued["job_id"],)))
    await download_service._process(job)

    job = await test_db.fetch_one("SELECT status, metadata FROM jobs WHERE id = ?", (queued["job_id"],))
    assert job["status"] == "done"
    assert json.loads(job["metadata"])["same_as"] == {"id": OLD, "title": TITLE}
    assert await test_db.fetch_val("SELECT feed_status FROM rss_entries WHERE video_id = ?", (NEW,)) == "dismissed"
    assert await test_db.fetch_val("SELECT COUNT(*) FROM videos WHERE id = ?", (NEW,)) == 0
    shown = next(i for i in (await download_service.get_queue())["queue"] if i["id"] == queued["job_id"])
    assert shown["same_as"]["id"] == OLD

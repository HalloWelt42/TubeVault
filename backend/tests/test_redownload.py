"""
Erneutes Laden eines vorhandenen Videos ("neu laden").

Kontrakt:
- Das Anstossen ändert weder Datei noch Status: das Video bleibt sichtbar und
  abspielbar, bis der neue Download fertig ist.
- Ein fehlgeschlagener Download lässt alles unberührt.
- Ein erfolgreicher Download ersetzt die Datei, hinterlässt genau einen
  Stream-Eintrag und bewahrt vom Nutzer gepflegte Angaben.
- Arbeitsdateien (.part, .ytdl) gelten nie als fertiges Video.
"""
import json
from pathlib import Path

import pytest

from app.routers import videos as videos_router
from app.services import download_service as ds_mod
from app.services.download_service import download_service, STAGING_DIRNAME
from app.utils.file_utils import is_media_file

VID = "abcdefghijk"


@pytest.fixture
def video_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(ds_mod, "VIDEOS_DIR", tmp_path)
    d = tmp_path / VID
    d.mkdir()
    return d


@pytest.fixture
async def ready_video(test_db, video_dir):
    old = video_dir / "video_tmp.mp4"
    old.write_bytes(b"A" * 5000)
    await test_db.execute(
        """INSERT INTO videos (id, title, channel_name, channel_id, status, file_path,
                               file_size, source, tags, video_type)
           VALUES (?, 'Mein eigener Titel', 'Kanal', 'UCx', 'ready', ?, 5000, 'youtube',
                   '["eigener-tag"]', 'short')""",
        (VID, str(old)))
    await test_db.execute(
        """INSERT INTO streams (video_id, stream_type, itag, quality, file_path, is_default, downloaded)
           VALUES (?, 'video', 18, '360p', ?, 1, 1)""", (VID, str(old)))
    return old


@pytest.fixture
def quiet_pipeline(monkeypatch):
    """Alles abklemmen, was Netz braucht oder wartet."""
    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(ds_mod.rate_limiter, "acquire", _noop)
    monkeypatch.setattr(download_service, "_stage", _noop)
    monkeypatch.setattr(download_service, "_ws_broadcast", _noop)
    import app.services.ryd_service as ryd
    monkeypatch.setattr(ryd, "fetch_votes", _noop)

    async def _resolve(url):
        return {"title": "Titel von der Quelle", "channel_name": "Kanal", "channel_id": "UCx",
                "description": "Beschreibung", "duration": 120, "upload_date": "2026-01-01",
                "view_count": 5, "tags": ["quelle"], "thumbnail_url": None,
                "stream_count": 3, "chapters": [], "video_type": "video"}
    monkeypatch.setattr(download_service, "_resolve", _resolve)


async def _queue_job(test_db):
    result = await download_service.add_to_queue(
        f"https://www.youtube.com/watch?v={VID}", quality="1080p", force=True)
    row = await test_db.fetch_one("SELECT * FROM jobs WHERE id = ?", (result["job_id"],))
    return dict(row)


async def test_anstossen_laesst_video_unberuehrt(test_db, ready_video, async_client_factory):
    async with await async_client_factory(videos_router.router) as client:
        r = await client.post(f"/api/videos/{VID}/upgrade?quality=1080p")
    assert r.status_code == 200
    row = await test_db.fetch_one("SELECT status, file_path FROM videos WHERE id = ?", (VID,))
    assert row["status"] == "ready"
    assert ready_video.exists(), "alte Datei darf vor dem Download nicht gelöscht werden"
    assert await test_db.fetch_val("SELECT COUNT(*) FROM jobs WHERE type='download'") == 1


async def test_zweites_anstossen_meldet_konflikt(test_db, ready_video, async_client_factory):
    async with await async_client_factory(videos_router.router) as client:
        await client.post(f"/api/videos/{VID}/upgrade")
        r = await client.post(f"/api/videos/{VID}/upgrade")
    assert r.status_code == 409


async def test_fehlschlag_aendert_nichts(test_db, ready_video, quiet_pipeline, monkeypatch):
    async def _fail(*a, **k):
        raise RuntimeError("HTTP Error 500: irgendwas")
    monkeypatch.setattr(download_service, "_download", _fail)

    await download_service._process(await _queue_job(test_db))

    row = await test_db.fetch_one("SELECT status, file_path, title FROM videos WHERE id = ?", (VID,))
    assert row["status"] == "ready"
    assert row["file_path"] == str(ready_video) and ready_video.read_bytes() == b"A" * 5000


async def test_erfolg_ersetzt_datei_und_bewahrt_angaben(
        test_db, ready_video, video_dir, quiet_pipeline, monkeypatch):
    new_file = video_dir / "video.mp4"

    async def _download(job_id, vid, url, opts, meta):
        new_file.write_bytes(b"B" * 9000)
        return str(new_file), 9000, {"type": "video", "itag": 137, "mime": "video/mp4",
                                     "quality": "1080p", "codec": "avc1"}, True
    monkeypatch.setattr(download_service, "_download", _download)

    await download_service._process(await _queue_job(test_db))

    row = dict(await test_db.fetch_one("SELECT * FROM videos WHERE id = ?", (VID,)))
    assert row["status"] == "ready"
    assert row["file_path"] == str(new_file) and row["file_size"] == 9000
    assert row["title"] == "Mein eigener Titel", "gepflegter Titel bleibt"
    assert json.loads(row["tags"]) == ["eigener-tag"], "gepflegte Tags bleiben"
    assert row["video_type"] == "short", "gepflegter Typ bleibt"
    assert row["description"] == "Beschreibung", "Leeres wird aufgefüllt"
    assert not ready_video.exists(), "Vorgängerdatei wird nach Erfolg entfernt"

    streams = await test_db.fetch_all("SELECT quality FROM streams WHERE video_id = ?", (VID,))
    assert [s["quality"] for s in streams] == ["1080p"], "genau ein Stream-Eintrag, der neue"


def test_promote_setzt_endgueltigen_namen(tmp_path):
    final_dir = tmp_path / VID
    staging = final_dir / STAGING_DIRNAME
    staging.mkdir(parents=True)
    old = final_dir / "video.mp4"
    old.write_bytes(b"A" * 4000)
    staged = staging / "video_tmp.mp4"
    staged.write_bytes(b"B" * 6000)

    target = download_service._promote(staged, final_dir, False)

    assert target == old and old.read_bytes() == b"B" * 6000
    assert not staged.exists()


def test_promote_lehnt_reste_ab(tmp_path):
    final_dir = tmp_path / VID
    staging = final_dir / STAGING_DIRNAME
    staging.mkdir(parents=True)
    old = final_dir / "video.mp4"
    old.write_bytes(b"A" * 4000)
    stub = staging / "video_tmp.mp4"
    stub.write_bytes(b"x" * 70)

    with pytest.raises(RuntimeError):
        download_service._promote(stub, final_dir, False)
    assert old.read_bytes() == b"A" * 4000


def test_is_media_file(tmp_path):
    good = tmp_path / "video.mp4"
    good.write_bytes(b"0" * 2000)
    state = tmp_path / "video_tmp.mp4.ytdl"
    state.write_bytes(b"0" * 2000)
    tiny = tmp_path / "tiny.mp4"
    tiny.write_bytes(b"0" * 70)
    assert is_media_file(good)
    assert not is_media_file(state), "Statusdatei von yt-dlp ist kein Video"
    assert not is_media_file(tiny)
    assert not is_media_file(tmp_path / "fehlt.mp4")
    assert not is_media_file(None)

"""Video nachbessern: Vorschaubild und Angaben eines Videos erneuern."""
import pytest

from app.services import video_repair
from app.services.video_repair import RepairError


async def _video(db, video_id="vid00000001", file_path=None):
    await db.execute(
        "INSERT INTO videos (id, title, status, file_path, duration) VALUES (?, 'Alt', 'ready', ?, 100)",
        (video_id, file_path))


async def test_vorschaubild_aus_datei(test_db, tmp_path, monkeypatch):
    clip = tmp_path / "video.mp4"
    clip.write_bytes(b"x")
    await _video(test_db, file_path=str(clip))
    calls = []

    def fake(path, destination, **kw):
        calls.append(kw)
        return destination
    monkeypatch.setattr(video_repair, "generate_ffmpeg_thumbnail", fake)

    await video_repair.thumbnail_from_file("vid00000001")
    result = await video_repair.thumbnail_from_file("vid00000001", position=42)

    assert calls == [{"duration": 100}, {"position": 42}]
    assert result["status"] == "ok"
    assert await test_db.fetch_val(
        "SELECT thumbnail_path FROM videos WHERE id = 'vid00000001'") == result["thumbnail_path"]


async def test_fehlende_datei_wird_gemeldet(test_db):
    await _video(test_db, file_path="/gibt/es/nicht.mp4")
    with pytest.raises(RepairError, match="Datei"):
        await video_repair.thumbnail_from_file("vid00000001")
    with pytest.raises(RepairError, match="nicht gefunden"):
        await video_repair.thumbnail_from_file("unbekannt")


async def test_angaben_von_der_quelle(test_db, monkeypatch):
    from app.services.rate_limiter import rate_limiter
    monkeypatch.setattr(rate_limiter, "disabled", True)
    await _video(test_db)
    monkeypatch.setattr(video_repair, "_fetch_metadata",
                        lambda video_id: {"title": "Neu", "duration": 222})

    async def no_thumbnail(*a, **kw):
        return None
    monkeypatch.setattr(video_repair, "download_yt_thumbnail", no_thumbnail)

    result = await video_repair.metadata_from_source("vid00000001")

    row = await test_db.fetch_one("SELECT title, duration FROM videos WHERE id = 'vid00000001'")
    assert (row["title"], row["duration"]) == ("Neu", 222)
    assert "title" in result["updated_fields"]
    with pytest.raises(RepairError):
        await video_repair.metadata_from_source("local_abc")

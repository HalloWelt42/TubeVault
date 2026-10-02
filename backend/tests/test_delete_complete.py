"""
Löschen ohne Reste.

Kontrakt:
- Ein gelöschtes Video hinterlässt weder Dateien noch Zeilen in abhängigen
  Tabellen; der Feed zeigt es wieder als nicht geladen; die Suche findet es
  nicht mehr.
- Von Hand lässt es sich erneut laden (die Sperre gilt nur für Automatik).
- Ein Kanal wird wahlweise mit oder ohne seine Videos entfernt.
"""
import pytest

from app.services import search_index
from app.services.download_service import download_service
from app.services.metadata_service import metadata_service
from app.services.rss_service import rss_service

CH = "UCkanal0000000000000001"


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    from app import config
    for name in ("VIDEOS_DIR", "THUMBNAILS_DIR", "SUBTITLES_DIR", "AUDIO_DIR", "METADATA_DIR"):
        monkeypatch.setattr(config, name, tmp_path / name.lower())
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setenv("TUBEVAULT_TEXTS_ROOT", str(tmp_path / "texts"))
    return tmp_path


async def _video(test_db, dirs, vid, channel_id=CH):
    from app import config
    folder = config.VIDEOS_DIR / vid
    folder.mkdir(parents=True)
    (folder / "video.mp4").write_bytes(b"x" * 2000)
    for extra in (config.THUMBNAILS_DIR / vid, config.SUBTITLES_DIR / vid,
                  config.AUDIO_DIR / vid / "tracks", dirs / "texts" / vid,
                  dirs / "chapter_thumbs" / vid):
        extra.mkdir(parents=True)
        (extra / "datei").write_text("x")
    await test_db.execute(
        "INSERT INTO videos (id, title, channel_id, status, file_path) VALUES (?, ?, ?, 'ready', ?)",
        (vid, f"Einzigartig{vid}", channel_id, str(folder / "video.mp4")))
    await test_db.execute(
        "INSERT INTO rss_entries (video_id, channel_id, title, status, auto_queued) VALUES (?, ?, 'T', 'downloaded', 1)",
        (vid, channel_id))
    for table, cols, vals in (
        ("chapters", "(video_id, title, start_time)", (vid, "K", 0)),
        ("watch_history", "(video_id, position)", (vid, 5)),
        ("streams", "(video_id, stream_type)", (vid, "video")),
        ("enrichment_log", "(video_id, type, attempted_at, success)", (vid, "chapters", "2026-01-01", 1)),
        ("audio_tracks", "(video_id, language, file_path)", (vid, "de", "/nirgends")),
        ("dub_requests", "(video_id, target_language)", (vid, "de")),
        ("video_links", "(video_id, linked_video_id, source_url)", ("anderes", vid, "u")),
    ):
        await test_db.execute(
            f"INSERT INTO {table} {cols} VALUES ({','.join('?' * len(vals))})", vals)
    return folder


async def test_video_restlos_weg(test_db, dirs):
    from app import config
    await _video(test_db, dirs, "v1")
    assert (await search_index.search_videos("Einzigartigv1"))["total"] == 1

    assert await metadata_service.delete_video("v1")

    for location in metadata_service._video_locations("v1"):
        assert not location.exists(), f"Rest gefunden: {location}"
    for table, column in metadata_service._VIDEO_ROWS:
        count = await test_db.fetch_val(f"SELECT COUNT(*) FROM {table} WHERE {column} = 'v1'")
        assert count == 0, f"Rest in {table}.{column}"
    assert await test_db.fetch_val("SELECT COUNT(*) FROM videos WHERE id = 'v1'") == 0
    assert (await search_index.search_videos("Einzigartigv1"))["total"] == 0

    feed = await test_db.fetch_one("SELECT status, auto_queued FROM rss_entries WHERE video_id = 'v1'")
    assert (feed["status"], feed["auto_queued"]) == ("new", 0), "Feed zeigt es wieder als nicht geladen"


async def test_fremde_datei_bleibt(test_db, dirs, tmp_path_factory):
    outside = tmp_path_factory.mktemp("eigene") / "urlaub.mp4"
    outside.write_bytes(b"x" * 2000)
    await test_db.execute(
        "INSERT INTO videos (id, title, status, source, file_path) VALUES ('local_1', 'Urlaub', 'ready', 'local', ?)",
        (str(outside),))
    assert await metadata_service.delete_video("local_1")
    assert outside.exists(), "Originale ausserhalb des Datenordners werden nicht gelöscht"


async def test_von_hand_wieder_ladbar(test_db, dirs):
    await _video(test_db, dirs, "abcdefghijk")
    await metadata_service.delete_video("abcdefghijk")
    assert await test_db.fetch_val(
        "SELECT COUNT(*) FROM ignored_videos WHERE video_id = 'abcdefghijk'") == 1

    await download_service.add_to_queue("https://www.youtube.com/watch?v=abcdefghijk")

    assert await test_db.fetch_val(
        "SELECT COUNT(*) FROM ignored_videos WHERE video_id = 'abcdefghijk'") == 0
    assert await test_db.fetch_val("SELECT COUNT(*) FROM jobs WHERE type = 'download'") == 1


async def test_automatik_respektiert_die_sperre(test_db, dirs):
    await _video(test_db, dirs, "abcdefghijk")
    await metadata_service.delete_video("abcdefghijk")
    await download_service.add_to_queue("https://www.youtube.com/watch?v=abcdefghijk", origin="auto")
    assert await test_db.fetch_val(
        "SELECT COUNT(*) FROM ignored_videos WHERE video_id = 'abcdefghijk'") == 1


async def _subscription(test_db):
    cursor = await test_db.execute(
        "INSERT INTO subscriptions (channel_id, channel_name) VALUES (?, 'Kanal')", (CH,))
    return cursor.lastrowid


async def test_kanal_entfernen_behaelt_videos(test_db, dirs):
    sub_id = await _subscription(test_db)
    folder = await _video(test_db, dirs, "v1")
    result = await rss_service.remove_subscription(sub_id)
    assert result == {"removed": True, "videos_deleted": 0}
    assert folder.exists()
    assert await test_db.fetch_val("SELECT COUNT(*) FROM videos") == 1
    assert await test_db.fetch_val("SELECT COUNT(*) FROM subscriptions") == 0


async def test_kanal_entfernen_mit_videos(test_db, dirs):
    sub_id = await _subscription(test_db)
    await _video(test_db, dirs, "v1")
    await _video(test_db, dirs, "v2")
    await _video(test_db, dirs, "fremd", channel_id="UCanderer")

    result = await rss_service.remove_subscription(sub_id, delete_videos=True)

    assert result == {"removed": True, "videos_deleted": 2}
    assert [r["id"] for r in await test_db.fetch_all("SELECT id FROM videos")] == ["fremd"]
    assert await test_db.fetch_val("SELECT COUNT(*) FROM ignored_videos") == 0
    assert await test_db.fetch_val("SELECT COUNT(*) FROM rss_entries WHERE channel_id = ?", (CH,)) == 0

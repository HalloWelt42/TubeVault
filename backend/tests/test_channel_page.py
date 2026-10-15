"""
Kanalseite (Entwurf mockups/kanal.html, Freigabe 16.10.2026).

Kontrakt:
- Die Kanalseite bekommt dieselben Zähler und Merkmale wie die Kanalübersicht
  (Medaille, Problem-Videos, Musikkanal, nie Shorts).
- Der Filter "Nicht geladen" zeigt Katalogeinträge ohne lokale Kopie, mit dem
  Grund einer Sperre; die Zähler aller Filter kommen mit.
- Die Diagnose prüft alle geladenen Videos auf ihre Dateien, auch die
  Begleitdateien, aus denen sich die Datenbank neu aufbauen lässt.
"""
import pytest

from app.routers.subscriptions import get_channel_detail, get_channel_diagnosis, get_channel_videos
from app.services import channel_diagnosis
from app.services.rss_service import rss_service

KANAL = "UCseite0000000000000001"


async def _kanal(db):
    await db.execute("INSERT INTO subscriptions (channel_id, channel_name, last_scanned) VALUES (?, 'Werkstatt', '2026-10-01 10:00:00')",
                     (KANAL,))
    for n in range(4):
        await db.execute("INSERT INTO rss_entries (video_id, channel_id, title, published) VALUES (?, ?, ?, ?)",
                         (f"seite{n:06d}", KANAL, f"Folge {n}", f"2026-10-0{n + 1} 10:00:00"))
    for n in (0, 1):
        await db.execute("INSERT INTO videos (id, title, channel_id, status) VALUES (?, 'T', ?, 'ready')", (f"seite{n:06d}", KANAL))


async def test_kanalseite_hat_die_merkmale_der_liste(test_db):
    await _kanal(test_db)
    await test_db.execute("INSERT INTO short_exempt_channels (channel_id) VALUES (?)", (KANAL,))
    detail = await get_channel_detail(KANAL)
    [listed] = (await rss_service.get_subscriptions())["subscriptions"]
    for key in ("wanted_count", "have_count", "medal", "problem_count", "music_channel", "short_exempt"):
        assert detail[key] == listed[key], key
    assert detail["short_exempt"] is True and detail["subscribed"] is True


async def test_filter_nicht_geladen(test_db):
    await _kanal(test_db)
    await test_db.execute("INSERT INTO ignored_videos (video_id, reason) VALUES ('seite000003', 'members-only · Join this channel')")
    page = await get_channel_videos(KANAL, source="missing", video_type="all", sort="newest", page=1, per_page=50, q="")
    assert [v["video_id"] for v in page["videos"]] == ["seite000003", "seite000002"]
    assert page["videos"][0]["blocked_reason"].startswith("members-only")
    assert page["source_counts"] == {"all": 4, "downloaded": 2, "missing": 2}


async def test_titelfilter_ueber_alle_videos(test_db):
    await _kanal(test_db)
    await test_db.execute("UPDATE rss_entries SET title = 'Brüche kürzen 100%' WHERE video_id = 'seite000002'")
    for source in ("all", "missing"):
        page = await get_channel_videos(KANAL, source=source, video_type="all", sort="newest", page=1, per_page=50,
                                        q="kürzen 100%")
        assert [v["video_id"] for v in page["videos"]] == ["seite000002"], source
    page = await get_channel_videos(KANAL, source="all", video_type="all", sort="newest", page=1, per_page=1, q="Folge")
    assert page["total"] == 3


@pytest.fixture
def ablage(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEVAULT_VIDEOS_ROOT", str(tmp_path / "videos"))
    monkeypatch.setenv("TUBEVAULT_TEXTS_ROOT", str(tmp_path / "texts"))
    monkeypatch.setattr(channel_diagnosis, "SUBTITLES_DIR", tmp_path / "subtitles")
    monkeypatch.setattr(channel_diagnosis, "AVATARS_DIR", tmp_path / "avatars")
    monkeypatch.setattr(channel_diagnosis, "BANNERS_DIR", tmp_path / "banners")
    return tmp_path


async def test_diagnose_zaehlt_alle_dateien(test_db, ablage):
    await _kanal(test_db)
    # Video 0: alles da; Video 1: nur das Video, Beschreibung nur in der Datenbank
    for name in ("videos/seite000000/video.mp4", "videos/seite000000/info.json", "thumbs/seite000000.jpg",
                 "texts/seite000000/description.txt", "subtitles/seite000000/a.de.vtt",
                 "videos/seite000001/video.mp4", "avatars/" + KANAL + ".jpg"):
        (ablage / name).parent.mkdir(parents=True, exist_ok=True)
        (ablage / name).write_text("x")
    await test_db.execute("UPDATE videos SET file_path = ?, thumbnail_path = ?, description = 'Hallo' WHERE id = 'seite000000'",
                          (str(ablage / "videos/seite000000/video.mp4"), str(ablage / "thumbs/seite000000.jpg")))
    await test_db.execute("UPDATE videos SET file_path = ?, description = 'Nur in der Datenbank' WHERE id = 'seite000001'",
                          (str(ablage / "videos/seite000001/video.mp4"),))
    await test_db.execute("UPDATE rss_entries SET video_type = 'short', duration = 30 WHERE video_id = 'seite000003'")

    result = await get_channel_diagnosis(KANAL)
    files = result.files
    assert (files.videos.present, files.videos.total) == (2, 2)
    assert (files.thumbnails.present, files.sidecars.present) == (1, 1)
    assert (files.descriptions.present, files.descriptions.total) == (1, 2)
    assert files.chapters.total == 0 and files.subtitles == 1
    assert (files.avatar, files.banner) == (True, False)
    catalog = result.catalog
    assert (catalog.entries, catalog.videos, catalog.shorts, catalog.no_duration) == (4, 3, 1, 3)
    assert catalog.last_scanned == "2026-10-01 10:00:00" and not catalog.scan_running


async def test_playlist_laedt_nur_ladbares_in_ihrer_reihenfolge(test_db, monkeypatch):
    # Früher gingen die ersten 20 Kennungen der Playlist in die Warteschlange,
    # auch schon geladene - waren das alle, kam der Stapel nie voran
    from app.routers.channel_playlists import queue_missing_playlist_videos
    from app.services.download_service import download_service
    await _kanal(test_db)
    await test_db.execute("INSERT INTO channel_playlists (playlist_id, channel_id, title, video_ids) VALUES ('PLx', ?, 'Brüche', ?)",
                          (KANAL, '["plda000001", "plneu00001", "plsperre01", "plneu00002", "plneu00003"]'))
    await test_db.execute("INSERT INTO videos (id, title, channel_id, status) VALUES ('plda000001', 'T', ?, 'ready')", (KANAL,))
    await test_db.execute("INSERT INTO ignored_videos (video_id, reason) VALUES ('plsperre01', 'private')")
    queued = []

    async def add(url, **_):
        queued.append(url.rsplit("=", 1)[1])
        return {"status": "queued"}
    monkeypatch.setattr(download_service, "add_to_queue", add)
    assert await queue_missing_playlist_videos("PLx", limit=2) == {"queued": 2, "remaining": 1}
    assert queued == ["plneu00001", "plneu00002"]

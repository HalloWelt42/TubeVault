"""
Unit-Tests der zentralen Zähl-Definitionen (counts_service).
Jede Definition genau einmal geprüft an einem kontrollierten Seed.
"""
import pytest
from app.services.counts_service import counts_service


async def _seed(db):
    async def vid(id, status="ready", archived=0, source="youtube", fsize=1000, fpath="/x.mp4", plays=0):
        await db.execute(
            "INSERT INTO videos (id, title, status, is_archived, source, file_size, file_path, play_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (id, id, status, archived, source, fsize, fpath, plays))
    await vid("lib1", plays=2); await vid("lib2"); await vid("lib3")
    await vid("arc1", archived=1); await vid("arc2", archived=1)
    await vid("own1", source="imported"); await vid("own2", source="local")
    await vid("ownArc", source="imported", archived=1)     # eigenes + archiviert
    await vid("ownZero", source="imported", fsize=0)       # keine echte Datei → Seite zeigt nicht
    await vid("pend", status="pending")
    await db.execute("INSERT INTO subscriptions (channel_id, channel_name, enabled) VALUES ('c1','A',1)")
    await db.execute("INSERT INTO subscriptions (channel_id, channel_name, enabled) VALUES ('c2','B',0)")
    await db.execute("INSERT INTO rss_entries (video_id, channel_id, status, feed_status) VALUES ('r1','c1','new','active')")
    await db.execute("INSERT INTO rss_entries (video_id, channel_id, status, feed_status) VALUES ('r2','c1','new','later')")
    await db.execute("INSERT INTO favorites (video_id) VALUES ('lib1')")


async def test_library_videos(test_db):
    await _seed(test_db)
    # ready & non-archived: lib1,lib2,lib3,own1,own2,ownZero = 6
    assert await counts_service.library_videos() == 6


async def test_archived_videos(test_db):
    await _seed(test_db)
    assert await counts_service.archived_videos() == 3   # arc1,arc2,ownArc


async def test_own_videos_matches_page_semantics(test_db):
    await _seed(test_db)
    # source local/imported, ready, file_path, file_size>0:
    #   own1, own2, ownArc (archiviert zählt!) — ownZero NICHT (fsize=0)
    assert await counts_service.own_videos() == 3


async def test_feed_and_subs(test_db):
    await _seed(test_db)
    assert await counts_service.feed_new() == 1          # r1 (active), r2 ist 'later'
    assert await counts_service.subscriptions_enabled() == 1
    assert await counts_service.subscriptions_total() == 2


async def test_history_played(test_db):
    await _seed(test_db)
    assert await counts_service.history_played() == 1    # nur lib1 hat play_count>0


async def test_favorites(test_db):
    await _seed(test_db)
    assert await counts_service.favorites() == 1


async def test_disk_mounts_shape(test_db):
    m = counts_service.disk_mounts()
    assert set(m.keys()) == {"media", "meta", "same_device"}
    assert m["media"]["label"] == "Medien"
    assert m["meta"]["label"] == "System"
    assert isinstance(m["same_device"], bool)

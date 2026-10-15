"""
Tests für gelöschte Videos (deleted_videos).

Kontrakt:
- Jedes Löschen trägt das Video in ignored_videos ein, damit RSS/Drip-
  Auto-Download es nicht wieder zieht - auch das Löschen mit dem Kanal.
- Die Angaben des Videos bleiben in deleted_videos erhalten.
- Wird es ausdrücklich neu geladen, kommen die eigenen Angaben zurück.
- _auto_queue_video skippt Videos, die in ignored_videos stehen.
"""
import json

import pytest

from app.services import deleted_videos
from app.services.metadata_service import metadata_service


@pytest.fixture
async def video_in_db(test_db):
    await test_db.execute(
        "INSERT INTO videos (id, title, channel_id, status) VALUES (?, ?, ?, 'ready')",
        ("delvid12345", "Schon gesehen", "UCdeletechannel"),
    )
    return "delvid12345"


async def test_delete_marks_video_ignored_by_default(test_db, video_in_db):
    """Manueller Delete im UI → Video kommt automatisch auf Ignore-Liste."""
    result = await metadata_service.delete_video(video_in_db)
    assert result is True

    row = await test_db.fetch_one(
        "SELECT reason, channel_id FROM ignored_videos WHERE video_id = ?",
        (video_in_db,),
    )
    assert row is not None, "Video muss in ignored_videos sein"
    assert "manuell gelöscht" in (row["reason"] or "")
    assert row["channel_id"] == "UCdeletechannel"


async def test_delete_keeps_metadata(test_db, video_in_db):
    """Die Angaben bleiben erhalten, die Bibliothek ist das Video los."""
    await test_db.execute(
        "UPDATE videos SET rating = 4, notes = 'Gute Stelle bei 3:10', play_count = 7, duration = 245 WHERE id = ?",
        (video_in_db,))
    await metadata_service.delete_video(video_in_db)

    assert await test_db.fetch_one("SELECT 1 FROM videos WHERE id = ?", (video_in_db,)) is None
    row = await test_db.fetch_one("SELECT * FROM deleted_videos WHERE video_id = ?", (video_in_db,))
    assert row["title"] == "Schon gesehen" and row["channel_id"] == "UCdeletechannel" and row["duration"] == 245
    kept = json.loads(row["data"])
    assert kept["notes"] == "Gute Stelle bei 3:10" and kept["rating"] == 4 and kept["play_count"] == 7


async def test_channel_delete_also_blocks(test_db, video_in_db):
    """Auch mit dem Kanal gelöschte Videos kommen nicht von selbst zurück."""
    await metadata_service.delete_channel_videos("UCdeletechannel")
    row = await test_db.fetch_one("SELECT reason FROM ignored_videos WHERE video_id = ?", (video_in_db,))
    assert row["reason"] == deleted_videos.MANUALLY_DELETED


async def test_unsubscribe_keeps_block_of_deleted(test_db, video_in_db):
    """Abo samt Videos entfernen: technische Sperren entfallen, gelöschte bleiben."""
    from app.services.rss_service import rss_service
    await test_db.execute(
        "INSERT INTO subscriptions (channel_id, channel_name, enabled) VALUES (?, ?, 1)",
        ("UCdeletechannel", "Kanal"))
    sub_id = await test_db.fetch_val("SELECT id FROM subscriptions WHERE channel_id = ?", ("UCdeletechannel",))
    await test_db.execute(
        "INSERT INTO ignored_videos (video_id, channel_id, reason) VALUES (?, ?, ?)",
        ("membervid01", "UCdeletechannel", "members-only"))

    await rss_service.remove_subscription(sub_id, delete_videos=True)

    left = {r["video_id"] for r in await test_db.fetch_all("SELECT video_id FROM ignored_videos")}
    assert left == {video_in_db}


async def test_reload_restores_user_data(test_db, video_in_db):
    """Ausdrücklich neu geladen: Bewertung, Notizen, Wiedergaben und die
    Musik-Wahl des Nutzers kommen zurück, der Merker entfällt."""
    await test_db.execute(
        """UPDATE videos SET rating = 5, notes = 'Lieblingsstück', play_count = 12,
               is_music = 1, music_source = 'user', music_artist = 'Interpret' WHERE id = ?""",
        (video_in_db,))
    await metadata_service.delete_video(video_in_db)
    # Der Download legt die Zeile neu an, mit frischen Angaben der Quelle
    await test_db.execute(
        "INSERT INTO videos (id, title, channel_id, status) VALUES (?, ?, ?, 'ready')",
        (video_in_db, "Schon gesehen (neu)", "UCdeletechannel"))

    assert await deleted_videos.restore(video_in_db) is True

    row = await test_db.fetch_one("SELECT * FROM videos WHERE id = ?", (video_in_db,))
    assert (row["rating"], row["notes"], row["play_count"]) == (5, "Lieblingsstück", 12)
    assert (row["is_music"], row["music_source"], row["music_artist"]) == (1, "user", "Interpret")
    assert row["title"] == "Schon gesehen (neu)"
    assert await test_db.fetch_one("SELECT 1 FROM deleted_videos WHERE video_id = ?", (video_in_db,)) is None
    assert await deleted_videos.restore(video_in_db) is False


async def test_delete_video_not_found_returns_false(test_db):
    """Nicht-existierendes Video löschen → False, kein ignore-Eintrag."""
    result = await metadata_service.delete_video("doesnotexist")
    assert result is False
    row = await test_db.fetch_one(
        "SELECT * FROM ignored_videos WHERE video_id = ?", ("doesnotexist",)
    )
    assert row is None


async def test_auto_queue_skips_ignored_video(test_db):
    """RSS-Auto-Download muss ignored_videos respektieren."""
    from app.services.rss_service import rss_service

    # Sub anlegen + Video als ignoriert markieren
    await test_db.execute(
        """INSERT INTO subscriptions (channel_id, channel_name, enabled)
           VALUES (?, ?, 1)""",
        ("UCtest", "TestChan"),
    )
    sub = dict(await test_db.fetch_one(
        "SELECT * FROM subscriptions WHERE channel_id = ?", ("UCtest",)
    ))
    await test_db.execute(
        "INSERT INTO ignored_videos (video_id, channel_id, reason) VALUES (?, ?, ?)",
        ("blockedvid1", "UCtest", "manuell gelöscht"),
    )

    # Vor Aufruf: keine Jobs
    n_before = await test_db.fetch_val("SELECT COUNT(*) FROM jobs WHERE type='download'")
    await rss_service._auto_queue_video("blockedvid1", sub)
    n_after = await test_db.fetch_val("SELECT COUNT(*) FROM jobs WHERE type='download'")
    assert n_after == n_before, "Ignoriertes Video darf NICHT in Queue landen"

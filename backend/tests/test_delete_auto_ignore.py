"""
Tests für Auto-Ignore beim manuellen Löschen.

Kontrakt:
- delete_video() trägt das Video standardmäßig in ignored_videos ein,
  damit RSS/Drip-Auto-Download es nicht wieder zieht.
- delete_video(ignore_for_future=False) für Test-Cleanup oder Re-Download.
- _auto_queue_video skippt Videos, die in ignored_videos stehen.
"""
import pytest

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


async def test_delete_with_ignore_false_does_not_mark(test_db, video_in_db):
    """ignore_for_future=False → kein ignored_videos-Eintrag (für Test/Re-Download)."""
    await metadata_service.delete_video(video_in_db, ignore_for_future=False)
    row = await test_db.fetch_one(
        "SELECT * FROM ignored_videos WHERE video_id = ?", (video_in_db,)
    )
    assert row is None


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

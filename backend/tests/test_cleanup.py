"""Aufräumen: Sichten, Mehrfachauswahl über alle Seiten, restloses Löschen."""
import pytest

from app.services import cleanup, video_classifier


@pytest.fixture
async def stock(test_db):
    rows = [
        ("short00001", "short", 1, "UCa", "A", 10, None),
        ("short00002", "short", 0, "UCa", "A", 20, None),
        ("video00001", "video", 1, "UCa", "A", 900, "2026-01-01 10:00:00"),
        ("video00002", "video", 1, "UCb", "B", 500, None),
    ]
    for vid, vtype, verified, ch, name, size, last in rows:
        await test_db.execute(
            """INSERT INTO videos (id, title, status, video_type, type_verified, channel_id,
                                   channel_name, file_size, last_played)
               VALUES (?, ?, 'ready', ?, ?, ?, ?, ?, ?)""",
            (vid, f"Titel {vid}", vtype, verified, ch, name, size, last))
    return test_db


async def test_sichten(stock):
    shorts = await cleanup.list_videos("shorts")
    assert {v.id for v in shorts.videos} == {"short00001", "short00002"}
    assert shorts.total == 2 and shorts.total_bytes == 30

    big = await cleanup.list_videos("big", limit=2)
    assert [v.id for v in big.videos] == ["video00001", "video00002"] and big.total == 4

    channel = await cleanup.list_videos("channel", channel_id="UCb")
    assert [v.id for v in channel.videos] == ["video00002"]
    with pytest.raises(ValueError):
        await cleanup.list_videos("channel")

    assert await cleanup.all_ids("shorts") and len(await cleanup.all_ids("shorts")) == 2
    by_size = await cleanup.channels()
    assert (by_size[0].channel_id, by_size[0].videos, by_size[0].bytes) == ("UCa", 3, 930)


async def test_kein_short_verschwindet_aus_der_sicht(stock):
    await video_classifier.set_manual(["short00002"], "video")
    assert {v.id for v in (await cleanup.list_videos("shorts")).videos} == {"short00001"}


async def test_restlos_loeschen(stock):
    result = await cleanup.delete(["short00001", "short00002", "gibtsnicht", "short00001"])
    assert (result.deleted, result.freed_bytes, result.missing) == (2, 30, ["gibtsnicht"])
    assert await stock.fetch_val("SELECT COUNT(*) FROM videos WHERE video_type = 'short'") == 0
    ignored = {r["video_id"] for r in await stock.fetch_all("SELECT video_id FROM ignored_videos")}
    assert {"short00001", "short00002"} <= ignored     # kommen nicht von selbst zurück

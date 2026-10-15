"""
Medaillen der Kanalübersicht (Wunsch 15.10.2026: sinnvolle Metrik): gemessen
an den gewünschten Feed-Einträgen, nicht an allen Videos des Kanals.
"""
from app.services import channel_coverage
from app.services.rss_service import rss_service


def test_stufen():
    assert channel_coverage.medal(10, 10) == "gold"
    assert channel_coverage.medal(10, 9) == "silver"
    assert channel_coverage.medal(100, 99) == "silver"     # kein "faktisch komplett" mehr
    assert channel_coverage.medal(20, 15) == "bronze"
    assert channel_coverage.medal(20, 14) is None
    assert channel_coverage.medal(2, 2) is None            # zu wenig für eine Aussage


async def test_videos_ausserhalb_des_feeds_gleichen_nichts_aus(test_db):
    await test_db.execute("INSERT INTO subscriptions (channel_id, channel_name) VALUES ('UCk', 'Kanal')")
    for n in range(4):
        await test_db.execute("INSERT INTO rss_entries (video_id, channel_id, title) VALUES (?, 'UCk', 'T')", (f"feed{n:07d}",))
    # zwei Feed-Videos geladen, dazu drei alte Videos des Kanals ohne Feed-Eintrag
    for vid in ("feed0000000", "feed0000001", "alt00000001", "alt00000002", "alt00000003"):
        await test_db.execute("INSERT INTO videos (id, title, channel_id, status) VALUES (?, 'T', 'UCk', 'ready')", (vid,))
    [sub] = (await rss_service.get_subscriptions())["subscriptions"]
    assert (sub["wanted_count"], sub["have_count"], sub["medal"]) == (4, 2, None)

    # ausgeblendet und nicht ladbar zählt nicht als fehlend
    await test_db.execute("UPDATE rss_entries SET feed_status = 'dismissed' WHERE video_id = 'feed0000002'")
    await test_db.execute("INSERT INTO ignored_videos (video_id, reason) VALUES ('feed0000003', 'Nur für Mitglieder')")
    await test_db.execute("INSERT INTO rss_entries (video_id, channel_id, title) VALUES ('feed0000004', 'UCk', 'T')")
    await test_db.execute("INSERT INTO videos (id, title, channel_id, status) VALUES ('feed0000004', 'T', 'UCk', 'ready')")
    [sub] = (await rss_service.get_subscriptions())["subscriptions"]
    assert (sub["wanted_count"], sub["have_count"], sub["medal"]) == (3, 3, "gold")


async def test_musikkanal_steht_in_der_liste(test_db):
    await test_db.execute("INSERT INTO subscriptions (channel_id, channel_name) VALUES ('UCm', 'Band'), ('UCt', 'Technik')")
    await test_db.execute("INSERT INTO music_channels (channel_id) VALUES ('UCm')")
    flags = {s["channel_id"]: s["music_channel"] for s in (await rss_service.get_subscriptions())["subscriptions"]}
    assert flags == {"UCm": True, "UCt": False}

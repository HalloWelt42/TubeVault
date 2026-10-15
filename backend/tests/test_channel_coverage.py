"""
Medaillen der Kanalübersicht (Nutzerentscheidung 15.10.2026): es zählen nur
die normalen Videos eines Kanals, Live und Shorts nie; Gold ist lückenlos,
Silber fehlen wenige Prozent (ab 95 %), Bronze ist fast voll (ab 80 %).
Bewertet wird nur ein vollständig gescannter Kanal.
"""
from app.services import channel_coverage
from app.services.rss_service import rss_service


def test_stufen():
    assert channel_coverage.medal(10, 10) == "gold"
    assert channel_coverage.medal(100, 99) == "silver"
    assert channel_coverage.medal(100, 95) == "silver"
    assert channel_coverage.medal(100, 94) == "bronze"
    assert channel_coverage.medal(10, 9) == "bronze"
    assert channel_coverage.medal(100, 80) == "bronze"
    assert channel_coverage.medal(100, 79) is None
    assert channel_coverage.medal(2, 2) is None                    # zu wenig für eine Aussage
    assert channel_coverage.medal(10, 10, scanned=False) == "never-scanned"


async def _kanal(db, scanned=True):
    await db.execute("INSERT INTO subscriptions (channel_id, channel_name, last_scanned) VALUES ('UCk', 'Kanal', ?)",
                     ("2026-10-01 10:00:00" if scanned else None,))


async def test_nur_normale_videos_zaehlen(test_db):
    await _kanal(test_db)
    for n in range(4):
        await test_db.execute("INSERT INTO rss_entries (video_id, channel_id, title) VALUES (?, 'UCk', 'T')", (f"feed{n:07d}",))
    await test_db.execute("INSERT INTO rss_entries (video_id, channel_id, title, video_type) VALUES ('short000001', 'UCk', 'S', 'short')")
    await test_db.execute("INSERT INTO rss_entries (video_id, channel_id, title, video_type) VALUES ('live0000001', 'UCk', 'L', 'live')")
    # zwei Feed-Videos geladen, dazu drei alte Videos des Kanals ohne Feed-Eintrag
    for vid in ("feed0000000", "feed0000001", "alt00000001", "alt00000002", "alt00000003"):
        await test_db.execute("INSERT INTO videos (id, title, channel_id, status) VALUES (?, 'T', 'UCk', 'ready')", (vid,))
    [sub] = (await rss_service.get_subscriptions())["subscriptions"]
    assert (sub["wanted_count"], sub["have_count"], sub["medal"]) == (4, 2, None)

    # Weggelegt zählt mit; nur dauerhaft nicht Ladbares fällt heraus
    await test_db.execute("UPDATE rss_entries SET feed_status = 'dismissed' WHERE video_id = 'feed0000002'")
    await test_db.execute("INSERT INTO ignored_videos (video_id, reason) VALUES ('feed0000003', 'members-only · Join this channel')")
    await test_db.execute("INSERT INTO videos (id, title, channel_id, status) VALUES ('feed0000002', 'T', 'UCk', 'ready')")
    [sub] = (await rss_service.get_subscriptions())["subscriptions"]
    assert (sub["wanted_count"], sub["have_count"], sub["medal"]) == (3, 3, "gold")


async def test_vorübergehend_verweigert_zaehlt_als_fehlend(test_db):
    await _kanal(test_db)
    for n in range(4):
        await test_db.execute("INSERT INTO rss_entries (video_id, channel_id, title) VALUES (?, 'UCk', 'T')", (f"feed{n:07d}",))
        if n < 3:
            await test_db.execute("INSERT INTO videos (id, title, channel_id, status) VALUES (?, 'T', 'UCk', 'ready')", (f"feed{n:07d}",))
    await test_db.execute(
        "INSERT INTO ignored_videos (video_id, reason) VALUES ('feed0000003', ?)",
        ("unavailable · Video unavailable. This content isn't available, try again later. rate-limited",))
    [sub] = (await rss_service.get_subscriptions())["subscriptions"]
    assert (sub["wanted_count"], sub["have_count"], sub["medal"]) == (4, 3, None)


async def test_ungescannter_kanal_bekommt_keine_medaille(test_db):
    await _kanal(test_db, scanned=False)
    for n in range(5):
        await test_db.execute("INSERT INTO rss_entries (video_id, channel_id, title) VALUES (?, 'UCk', 'T')", (f"feed{n:07d}",))
        await test_db.execute("INSERT INTO videos (id, title, channel_id, status) VALUES (?, 'T', 'UCk', 'ready')", (f"feed{n:07d}",))
    [sub] = (await rss_service.get_subscriptions())["subscriptions"]
    assert sub["medal"] == "never-scanned"


async def test_musikkanal_steht_in_der_liste(test_db):
    await test_db.execute("INSERT INTO subscriptions (channel_id, channel_name) VALUES ('UCm', 'Band'), ('UCt', 'Technik')")
    await test_db.execute("INSERT INTO music_channels (channel_id) VALUES ('UCm')")
    flags = {s["channel_id"]: s["music_channel"] for s in (await rss_service.get_subscriptions())["subscriptions"]}
    assert flags == {"UCm": True, "UCt": False}

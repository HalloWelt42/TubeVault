"""Short-Regel: Stichtag und Kanal-Ausnahme gelten für jeden Schreibweg.

Anlass: Die Quelle führt alte, kurze, quadratische Videos (ab 2010) im
Shorts-Reiter und spielt sie im Shorts-Player. Wichtige Kanäle mit kurzen,
aber vollwertigen Videos standen deshalb als Short da - mit dem Risiko, beim
Ausschließen oder Löschen von Shorts verloren zu gehen.
"""
from app.services import video_classifier as vc

CH = "UCkanal0000000000000001"


async def _video(db, vid, upload_date, vtype="short", verified=1, channel=CH):
    await db.execute(
        """INSERT INTO videos (id, title, status, video_type, type_verified, channel_id, upload_date)
           VALUES (?, ?, 'ready', ?, ?, ?, ?)""", (vid, vid, vtype, verified, channel, upload_date))


async def _type(db, vid):
    return await db.fetch_val("SELECT video_type FROM videos WHERE id = ?", (vid,))


async def test_vor_dem_start_von_shorts_kein_short(test_db):
    await _video(test_db, "alt20100001", "2010-10-07 00:00:00")
    await _video(test_db, "neu20210001", "2021-07-01 10:00:00-07:00")
    await _video(test_db, "ohnedatum01", None)
    assert await _type(test_db, "alt20100001") == "video"
    assert await _type(test_db, "neu20210001") == "short"
    assert await _type(test_db, "ohnedatum01") == "short"          # ohne Datum wird nicht geraten
    # Auch spätere Prüfungen stellen ein altes Video nicht zurück
    await test_db.execute("UPDATE videos SET video_type = 'short' WHERE id = 'alt20100001'")
    assert await _type(test_db, "alt20100001") == "video"


async def test_von_hand_gesetzt_bleibt(test_db):
    await _video(test_db, "hand2010001", "2010-01-01", verified=2)
    assert await _type(test_db, "hand2010001") == "short"


async def test_feed_eintraege_folgen_derselben_regel(test_db):
    await test_db.execute(
        """INSERT INTO rss_entries (video_id, channel_id, video_type, type_verified, published)
           VALUES ('alt20120001', ?, 'short', 1, '2012-05-01 10:00:00-07:00'),
                  ('neu20240001', ?, 'short', 1, '2024-05-01T00:00:00+00:00')""", (CH, CH))
    rows = {r["video_id"]: r["video_type"] for r in await test_db.fetch_all(
        "SELECT video_id, video_type FROM rss_entries")}
    assert rows == {"alt20120001": "video", "neu20240001": "short"}


async def test_kanal_ausnahme(test_db):
    await _video(test_db, "kurz2023001", "2023-03-01")
    await _video(test_db, "kurz2023002", "2023-03-02", verified=2)
    await _video(test_db, "anderer0001", "2023-03-03", channel="UCanderer000000000000001")

    assert await vc.set_channel_exempt(CH, True) == 1
    assert await vc.is_channel_exempt(CH)
    assert await _type(test_db, "kurz2023001") == "video"
    assert await _type(test_db, "kurz2023002") == "short"       # von Hand gesetzt bleibt
    assert await _type(test_db, "anderer0001") == "short"
    # Neue Videos des Kanals werden gar nicht erst Short
    await _video(test_db, "kurz2024001", "2024-12-01")
    assert await _type(test_db, "kurz2024001") == "video"

    # Aufheben stellt nichts zurück - es wird nichts wieder zum Short
    await vc.set_channel_exempt(CH, False)
    assert not await vc.is_channel_exempt(CH)
    assert await _type(test_db, "kurz2023001") == "video"

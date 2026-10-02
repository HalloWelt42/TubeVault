"""
Video-Typ bestimmen (app/services/video_classifier.py).

Kontrakt:
- Short ist, was die Quelle unter ihrer Shorts-Adresse führt - nicht, was
  kurz ist. Die Dauer entscheidet nur in eine Richtung: zu lang = kein Short.
- Livestream sagt die Quelle.
- Unklare Auskunft: nicht raten, ungeprüft lassen.
- Vom Nutzer gesetzte Typen bleiben.
"""
import httpx
import pytest

from app.services import video_classifier as vc


def _client(status, location=None):
    def handler(request):
        assert request.method == "HEAD" and "/shorts/" in request.url.path
        headers = {"location": location} if location else {}
        return httpx.Response(status, headers=headers)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# Die echte Probe, bevor conftest sie für alle Tests stilllegt
_real_probe = vc.probe_short


async def test_probe_antworten():
    vid = "abcdefghijk"
    assert await _real_probe(vid, _client(200)) is True
    assert await _real_probe(vid, _client(303, "https://www.youtube.com/watch?v=" + vid)) is False
    assert await _real_probe(vid, _client(302, "https://consent.youtube.com/m?continue=x")) is None, \
        "Einwilligungsseite ist keine Auskunft"
    assert await _real_probe(vid, _client(429)) is None
    assert await _real_probe("local_123", _client(200)) is False, "eigene Dateien sind nie Shorts"


async def test_classify_regeln(monkeypatch):
    async def short(video_id, client=None): return True
    async def normal(video_id, client=None): return False
    async def unknown(video_id, client=None): return None

    monkeypatch.setattr(vc, "probe_short", short)
    assert (await vc.classify("abcdefghijk", duration=30)).model_dump() == {"video_type": "short", "verified": True}
    assert (await vc.classify("abcdefghijk", duration=170)).video_type == "short", "Shorts dürfen fast 3 Minuten lang sein"
    assert (await vc.classify("abcdefghijk", duration=7490)).video_type == "video", "zu lang: ohne Nachfrage kein Short"
    assert (await vc.classify("abcdefghijk", is_live=True, duration=20)).video_type == "live"

    monkeypatch.setattr(vc, "probe_short", normal)
    assert (await vc.classify("abcdefghijk", duration=30)).model_dump() == {"video_type": "video", "verified": True}, \
        "kurzes normales Video ist kein Short"

    monkeypatch.setattr(vc, "probe_short", unknown)
    assert (await vc.classify("abcdefghijk", duration=30)).model_dump() == {"video_type": "video", "verified": False}


def test_live_aus_quellangaben():
    assert vc.live_from_info({"was_live": True})
    assert vc.live_from_info({"live_status": "is_upcoming"})
    assert not vc.live_from_info({"live_status": "not_live"})


async def _row(test_db, vid):
    return dict(await test_db.fetch_one("SELECT video_type, type_verified FROM videos WHERE id = ?", (vid,)))


async def test_bestand_ohne_nachfrage(test_db):
    await test_db.execute("INSERT INTO videos (id, title, duration, video_type) VALUES ('langlanglan', 'T', 7490, 'short')")
    await test_db.execute("INSERT INTO videos (id, title, duration, video_type) VALUES ('kurzkurzkur', 'T', 40, 'short')")
    await test_db.execute("INSERT INTO videos (id, title, duration, video_type) VALUES ('local_1', 'T', 20, 'short')")
    await vc.settle_without_probe()
    assert await _row(test_db, "langlanglan") == {"video_type": "video", "type_verified": 1}
    assert await _row(test_db, "local_1") == {"video_type": "video", "type_verified": 1}
    assert await _row(test_db, "kurzkurzkur") == {"video_type": "short", "type_verified": 0}, "braucht die Nachfrage"


async def test_nutzerwahl_bleibt(test_db):
    await test_db.execute("INSERT INTO videos (id, title, duration, video_type) VALUES ('abcdefghijk', 'T', 40, 'video')")
    await test_db.execute("INSERT INTO rss_entries (video_id, channel_id, title, video_type) VALUES ('abcdefghijk', 'UCx', 'T', 'video')")
    assert await vc.set_manual(["abcdefghijk"], "live") == 1
    await vc.apply("abcdefghijk", vc.Classification(video_type="short", verified=True))
    assert await _row(test_db, "abcdefghijk") == {"video_type": "live", "type_verified": 2}
    assert await test_db.fetch_val("SELECT video_type FROM rss_entries WHERE video_id = 'abcdefghijk'") == "live"
    with pytest.raises(ValueError):
        await vc.set_manual(["abcdefghijk"], "film")


async def test_gepruefter_typ_gilt_fuer_video_und_feed(test_db):
    await test_db.execute("INSERT INTO videos (id, title, video_type) VALUES ('abcdefghijk', 'T', 'video')")
    await test_db.execute("INSERT INTO rss_entries (video_id, channel_id, title, video_type) VALUES ('abcdefghijk', 'UCx', 'T', 'video')")
    await vc.apply("abcdefghijk", vc.Classification(video_type="short", verified=True))
    assert await _row(test_db, "abcdefghijk") == {"video_type": "short", "type_verified": 1}
    feed = await test_db.fetch_one("SELECT video_type, type_verified FROM rss_entries WHERE video_id = 'abcdefghijk'")
    assert (feed["video_type"], feed["type_verified"]) == ("short", 1)
    assert await vc.pending() == 0


async def test_unklare_auskunft_aendert_nichts(test_db):
    await test_db.execute("INSERT INTO videos (id, title, video_type) VALUES ('abcdefghijk', 'T', 'short')")
    await vc.apply("abcdefghijk", vc.Classification(video_type="video", verified=False))
    assert await _row(test_db, "abcdefghijk") == {"video_type": "short", "type_verified": 0}
    assert await vc.pending() == 1

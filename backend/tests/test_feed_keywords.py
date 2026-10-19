"""
Schlagwörter im Feed über den eigenen Index (feed_keywords, tag_index).

Kontrakt wie bei den Videos (test_video_tags.py): ein Schlagwort findet genau
seine Einträge, gleich wie es im JSON steht (\\u-Umschreibung), mit Umlaut
oder fremder Schrift, in beliebiger Groß- und Kleinschreibung; % und _ sind
gewöhnliche Zeichen; mehrere = oder. Die Schlagwortliste des Feeds zählt je
Schlüssel jeden Eintrag einmal - so viele, wie der Filter findet. Neue und
geänderte Einträge sind sofort findbar, gelöschte nehmen ihre Zeilen mit.
"""
import json

from app.routers import feed_router
from app.services import feed_keywords
from app.services.rss_service import rss_service


async def _entry(db, vid, keywords):
    await db.execute(
        "INSERT INTO rss_entries (video_id, channel_id, title, keywords, published) VALUES (?, 'UCx', ?, ?, '2026-01-01')",
        (vid, f"Eintrag {vid}", json.dumps(keywords)))          # ensure_ascii: \\u-umschrieben


async def _bestand(db):
    await db.execute("INSERT INTO subscriptions (channel_id, channel_name) VALUES ('UCx', 'Kanal')")
    await _entry(db, "militaer001", ["Militär", "Streitkräfte", "Analyse"])
    await _entry(db, "militaer002", ["MILITÄR", "Lagebericht"])
    await _entry(db, "techno00001", ["техно", "Musik"])
    await _entry(db, "prozent0001", ["100%", "a_b"])
    await _entry(db, "prozent0002", ["1000", "aXb", "musik"])


async def _ids(**params) -> list[str]:
    feed = await rss_service.get_new_videos(feed_tab="all", per_page=100, **params)
    return sorted(e["video_id"] for e in feed["entries"])


async def test_feedfilter_findet_jedes_schlagwort(test_db):
    await _bestand(test_db)
    assert await _ids(keywords="Militär") == ["militaer001", "militaer002"]
    assert await _ids(keywords="militär") == ["militaer001", "militaer002"]
    assert await _ids(keywords="streitkräfte") == ["militaer001"]
    assert await _ids(keywords="ТЕХНО") == ["techno00001"]
    assert await _ids(keywords="100%") == ["prozent0001"]          # kein Platzhalter
    assert await _ids(keywords="a_b") == ["prozent0001"]
    assert await _ids(keywords="Musik,Lagebericht") == ["militaer002", "prozent0002", "techno00001"]
    assert await _ids(keywords="Milit") == []                      # genau, kein Teilwort


async def test_schlagwortliste_zaehlt_wie_der_filter(test_db):
    await _bestand(test_db)
    counted = await feed_router.get_feed_tags(feed_tab="all")
    assert {e["key"]: e["count"] for e in counted}["militär"] == 2
    for entry in counted:
        assert len(await _ids(keywords=entry["tag"])) == entry["count"], entry


async def test_aenderung_und_loeschen(test_db):
    await _bestand(test_db)
    await test_db.execute("""UPDATE rss_entries SET keywords = '["Gespr\\u00e4che"]' WHERE video_id = 'techno00001'""")
    assert await _ids(keywords="GESPRÄCHE") == ["techno00001"]
    assert await _ids(keywords="техно") == []
    await test_db.execute("DELETE FROM rss_entries WHERE video_id = 'techno00001'")
    assert not await test_db.fetch_val("SELECT COUNT(*) FROM feed_keywords k JOIN rss_entries r ON r.id = k.entry_id "
                                       "WHERE r.video_id = 'techno00001'")
    assert not await test_db.fetch_val("SELECT COUNT(*) FROM feed_keywords WHERE tag_suche = 'gespräche'")


async def test_bestand_in_portionen(test_db, monkeypatch):
    await _bestand(test_db)
    await test_db.execute("DELETE FROM feed_keywords")
    await test_db.execute("INSERT OR IGNORE INTO feed_keywords_dirty (entry_id) SELECT id FROM rss_entries")
    assert await feed_keywords.INDEX.flush(limit=2) == 2
    assert await feed_keywords.INDEX.pending() == 3                 # der Rest bleibt vorgemerkt
    monkeypatch.setattr(feed_keywords.INDEX, "batch", 2)
    await feed_keywords.INDEX.background_catch_up()
    assert await feed_keywords.INDEX.pending() == 0
    assert await test_db.fetch_val("SELECT COUNT(*) FROM feed_keywords WHERE tag_suche = 'musik'") == 2

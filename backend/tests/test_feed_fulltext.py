"""
Schlagwörter im Volltext (Suche über alles), Feed und Videos.

Kontrakt: Schlagwörter stehen als JSON-Liste mit \\u-Umschreibung; die Suche
findet sie entschlüsselt - mit Umlaut, in fremder Schrift, in beliebiger
Schreibweise. Neue, geänderte und unlesbare Angaben brechen nichts; v61
schreibt die betroffenen Einträge des Bestands neu (reindex_feed_keywords).
"""
import json

from app.services.search import engine, index as search_extra_index
from app.services.search.filters import SearchFilters


async def _feed(db, entry_id, keywords, title="Ohne Treffer im Titel"):
    raw = keywords if isinstance(keywords, str) else json.dumps(keywords)       # ensure_ascii: \\u-umschrieben
    await db.execute(
        "INSERT INTO rss_entries (id, video_id, channel_id, title, keywords, published) VALUES (?, ?, 'UCx', ?, ?, '2026-05-04')",
        (entry_id, f"feed{entry_id:07d}", title, raw))


async def _matches(db, query) -> list[int]:
    return [row[0] for row in await db.fetch_all("SELECT rowid FROM feed_fts WHERE feed_fts MATCH ? ORDER BY rowid", (query,))]


async def _bestand(db):
    await db.execute("INSERT INTO subscriptions (channel_id, channel_name) VALUES ('UCx', 'Kanal')")
    await _feed(db, 1, ["Militär", "Streitkräfte"])
    await _feed(db, 2, ["техно", "Musik"])
    await _feed(db, 3, "kaputt, kein JSON")                                   # bleibt als Text findbar
    await _feed(db, 4, ["Analyse"])


async def test_feed_schlagwoerter_entschluesselt_im_volltext(test_db):
    await _bestand(test_db)
    assert await _matches(test_db, "keywords:Militär") == [1]
    assert await _matches(test_db, "keywords:militar") == [1]                # ohne Akzent, wie der Tokenizer
    assert await _matches(test_db, "keywords:STREITKRÄFTE") == [1]
    assert await _matches(test_db, "keywords:техно") == [2]
    assert await _matches(test_db, "keywords:kaputt") == [3]
    page = await engine.section("abos", "Streitkräfte", SearchFilters())
    assert [hit.video_id for hit in page.items] == ["feed0000001"]
    await test_db.execute("""UPDATE rss_entries SET keywords = '["Gespr\\u00e4che"]' WHERE id = 4""")
    assert await _matches(test_db, "keywords:Gespräche") == [4]
    assert await _matches(test_db, "keywords:Analyse") == []


async def test_bestand_wird_neu_geschrieben(test_db):
    """Wie vor v61: rohes JSON im Volltext; reindex_feed_keywords schreibt den
    Klartext der Einträge mit Umschreibung, die übrigen trafen schon."""
    await _bestand(test_db)
    await test_db.execute("DELETE FROM feed_fts")
    await test_db.execute(
        "INSERT INTO feed_fts (rowid, title, channel_name, description, keywords) "
        "SELECT id, title, 'Kanal', '', keywords FROM rss_entries")
    assert await _matches(test_db, "keywords:Militär") == []                 # der alte Fehler
    assert await search_extra_index.reindex_feed_keywords(test_db.conn) == 2     # Militär und техно
    assert await _matches(test_db, "keywords:Militär") == [1]
    assert await _matches(test_db, "keywords:Analyse") == [4]
    assert await _matches(test_db, "keywords:техно") == [2]
    await _feed(test_db, 5, ["Militär"])                                      # Trigger dieser Fassung
    assert await _matches(test_db, "keywords:Militär") == [1, 5]


async def test_videos_finden_schlagwoerter_mit_umlaut(test_db):
    """Der Videoindex entschlüsselt die Schlagwörter schon selbst (search_index)."""
    await test_db.execute(
        "INSERT INTO videos (id, title, channel_name, status, tags) VALUES ('koerper0001', 'Ohne', 'Kanal', 'ready', ?)",
        (json.dumps(["Körper", "техно"]),))
    for word in ("Körper", "körper", "техно"):
        page = await engine.section("videos", word, SearchFilters())
        assert [item.id for item in page.items] == ["koerper0001"], word

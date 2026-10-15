"""
Bedeutungssuche und hybride Rangfolge.

Der KI-Dienst ist hier eine Attrappe: Sie legt jeden Text auf wenige
Themenachsen (Backen, Elektronik, Astronomie), damit Verwandtschaft ohne
Wortgleichheit prüfbar ist.

Kontrakt:
- Ohne eingeschaltete oder erreichbare KI ist die Suche reine Wortsuche.
- Mit KI kommen inhaltlich verwandte Videos dazu - im eigenen Bereich
  "sinngemaess", nie vor den Worttreffern; was ein Wort trifft, steht dort
  nicht noch einmal.
- Bedeutungstreffer bestehen dieselben Filter (Archiv, Shorts).
- Geänderte und gelöschte Videos ziehen von selbst nach.
"""
import pytest

from app.services import semantic_index
from app.services.search import engine
from app.services.search.filters import SearchFilters

TOPICS = {
    "backen": ("brot", "teig", "sauerteig", "hefe", "backen", "ofen"),
    "elektronik": ("löten", "lötkolben", "platine", "schaltung", "widerstand"),
    "astronomie": ("mond", "stern", "teleskop", "galaxie", "planet"),
}


def _fake_vector(text: str) -> list[float]:
    low = text.lower()
    vector = [float(sum(low.count(word) for word in words)) for words in TOPICS.values()]
    return vector if any(vector) else [0.01, 0.01, 0.01]


@pytest.fixture
async def ai(test_db, set_setting, monkeypatch):
    calls = {"n": 0, "up": True}

    async def fake_embed(texts, url, model, timeout):
        if not calls["up"]:
            raise ConnectionError("aus")
        calls["n"] += 1
        return [_fake_vector(t) for t in texts]

    monkeypatch.setattr(semantic_index, "embed_texts", fake_embed)
    semantic_index.reset_availability()
    semantic_index._matrix = None
    semantic_index._query_cache.clear()
    await set_setting("ai.enabled", "true")
    await set_setting("ai.url", "http://ki.test/v1")
    # die Attrappe kennt nur grobe Themenachsen: mildere Schwelle für "ausgewogen"
    monkeypatch.setitem(semantic_index.PRECISIONS, "ausgewogen",
                        semantic_index.Precision("Ausgewogen", 0.25, 2.5, 80))
    yield calls
    semantic_index.reset_availability()
    semantic_index._matrix = None


async def _add(db, vid, title, archived=0, video_type="video"):
    await db.execute(
        "INSERT INTO videos (id, title, status, is_archived, video_type) VALUES (?, ?, 'ready', ?, ?)",
        (vid, title, archived, video_type))


async def _index():
    cfg = await semantic_index.config()
    while await semantic_index.index_batch(*cfg):
        pass


async def _search(query, **filters):
    """(Worttreffer, sinngemäß Verwandtes, Übersicht)."""
    overview = await engine.overview(query, SearchFilters(**filters), limit=20)
    words = [item.id for item in overview.sections["videos"].items] if overview.sections else []
    meaning = [item.id for item in overview.sections["sinngemaess"].items] if overview.sections else []
    return words, meaning, overview


async def test_ohne_ki_reine_wortsuche(test_db):
    await _add(test_db, "v1", "Sauerteig ansetzen")
    words, meaning, overview = await _search("Sauerteig")
    assert words == ["v1"] and meaning == [] and overview.semantic is False
    assert (await _search("Brot backen"))[:2] == ([], [])


async def test_verwandtes_ohne_wortgleichheit(test_db, ai):
    await _add(test_db, "teig", "Sauerteig ansetzen")
    await _add(test_db, "loet", "Platine löten für Anfänger")
    await _index()

    words, meaning, overview = await _search("Brot backen")
    assert overview.semantic is True
    assert (words, meaning) == ([], ["teig"]), "Thema passt, kein Wort gleich - das Lötvideo bleibt draussen"


async def test_worttreffer_vor_sinngemaessem(test_db, ai):
    await _add(test_db, "nurwort", "Brot")                       # Worttreffer, auch Thema
    await _add(test_db, "nursinn", "Hefe und Ofen")              # nur Thema
    await _add(test_db, "fremd", "Brot und Spiele im alten Rom") # Worttreffer
    await _index()
    words, meaning, _ = await _search("Brot")
    assert set(words) == {"nurwort", "fremd"}
    assert meaning == ["nursinn"], "was ein Wort trifft, steht nicht noch einmal unter sinngemäß"


async def test_filter_gelten_auch_fuer_bedeutungstreffer(test_db, ai, set_setting):
    await _add(test_db, "arch", "Hefe im Ofen", archived=1)
    await _add(test_db, "lib", "Teig kneten", archived=0)
    await _add(test_db, "kurz", "Ofen in 30 Sekunden", video_type="short")
    await _index()
    assert set((await _search("Brot backen", location="bibliothek"))[1]) == {"lib", "kurz"}
    await set_setting("shorts.exclude", "true")
    assert set((await _search("Brot backen"))[1]) == {"arch", "lib"}


async def test_ki_faellt_aus_suche_laeuft_weiter(test_db, ai):
    await _add(test_db, "teig", "Sauerteig ansetzen")
    await _index()
    ai["up"] = False
    semantic_index.reset_availability()
    semantic_index._query_cache.clear()
    words, meaning, overview = await _search("Sauerteig")
    assert words == ["teig"] and meaning == [] and overview.semantic is False


async def test_aenderung_und_loeschen_ziehen_nach(test_db, ai):
    await _add(test_db, "v1", "Sauerteig ansetzen")
    await _index()
    assert await semantic_index.pending() == 0

    await test_db.execute("UPDATE videos SET title = 'Teleskop für den Mond' WHERE id = 'v1'")
    assert await semantic_index.pending() == 1
    await _index()
    assert (await _search("Stern und Planet"))[1] == ["v1"]
    assert (await _search("Brot backen"))[1] == []

    await test_db.execute("DELETE FROM videos WHERE id = 'v1'")
    assert await test_db.fetch_val("SELECT COUNT(*) FROM video_embeddings") == 0


async def test_unveraenderter_text_wird_nicht_neu_gerechnet(test_db, ai):
    await _add(test_db, "v1", "Sauerteig ansetzen")
    await _index()
    before = ai["n"]
    await test_db.execute("UPDATE videos SET status = 'ready' WHERE id = 'v1'")   # merkt vor, Text gleich
    await _index()
    assert ai["n"] == before


async def test_genauigkeit_ist_je_suche_waehlbar(test_db, ai, set_setting):
    """Wunsch 15.10.2026: Genauigkeit selbst einstellen, mit Standard. "aus"
    sucht nur nach Wörtern; die Stufe kommt sonst aus den Einstellungen."""
    await _add(test_db, "teig", "Sauerteig ansetzen")
    await _index()
    words, meaning, overview = await _search("Brot backen")
    assert overview.semantic and meaning == ["teig"]
    words, meaning, overview = await _search("Brot backen", precision="aus")
    assert not overview.semantic and meaning == []
    await set_setting("ai.precision", "sehr_genau")
    assert (await semantic_index.precision()).label == "Sehr genau"
    assert (await semantic_index.precision("weit")).label == "Weit"


async def test_bedeutung_findet_kanaele_playlists_feed_und_liedtexte(ai, test_db, monkeypatch):
    """Kanalbeschreibungen, Playlists, noch nicht geladene Feed-Einträge und
    Liedtexte haben eigene Vektoren (semantic_items) und kommen in die Suche."""
    from app.services import lyrics_service, semantic_items
    semantic_items._codes.clear()
    await test_db.execute(
        "INSERT INTO subscriptions (channel_id, channel_name, channel_description) VALUES "
        "('UCback', 'Backstube', 'Rund um Brot und Hefe'), ('UCtech', 'Werkbank', 'Löten und Platinen')")
    await test_db.execute("INSERT INTO playlists (name, description) VALUES ('Sterne schauen', 'Abends draussen')")
    await test_db.execute(
        "INSERT INTO rss_entries (video_id, channel_id, title, description) VALUES "
        "('feedbrot001', 'UCback', 'Brot ohne Kneten', 'Teig über Nacht'), ('feedgeladen', 'UCback', 'Ofenbrot', 'Brot')")
    await _add(test_db, "feedgeladen", "Ofenbrot")
    await test_db.execute("INSERT INTO videos (id, title, status, has_lyrics, music_artist, music_title) "
                          "VALUES ('liedmond001', 'Ein Lied', 'ready', 1, 'Band', 'Nachtlied')")
    monkeypatch.setattr(lyrics_service, "load_lyrics",
                        lambda vid: {"plain": "Der Mond und die Sterne leuchten" if vid == "liedmond001" else ""})

    url, model = await semantic_index.config()
    while await semantic_items.index_batch(url, model):
        pass
    assert (await semantic_items.overview(model)) == {"channel": 2, "playlist": 1, "lyrics": 1, "feed": 1}

    backen = (await _search("Sauerteig backen", precision="ausgewogen"))[2]
    channels = backen.sections["kanaele"].items
    assert [c.channel_name for c in channels][:1] == ["Backstube"] and channels[0].meaning
    assert [f.video_id for f in backen.sections["abos"].items] == ["feedbrot001"]   # geladene fallen heraus

    sterne = (await _search("Teleskop", precision="ausgewogen"))[2]
    assert "liedmond001" in [v.id for v in sterne.sections["sinngemaess"].items]
    assert [p.name for p in sterne.sections["playlists"].items] == ["Sterne schauen"]

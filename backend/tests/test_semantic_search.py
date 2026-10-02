"""
Bedeutungssuche und hybride Rangfolge.

Der KI-Dienst ist hier eine Attrappe: Sie legt jeden Text auf wenige
Themenachsen (Backen, Elektronik, Astronomie), damit Verwandtschaft ohne
Wortgleichheit prüfbar ist.

Kontrakt:
- Ohne eingeschaltete oder erreichbare KI ist die Suche reine Wortsuche.
- Mit KI kommen inhaltlich verwandte Videos dazu; was Wort- und
  Bedeutungssuche beide finden, steht vorn.
- Bedeutungstreffer bestehen dieselben Filter (Archiv, Shorts).
- Geänderte und gelöschte Videos ziehen von selbst nach.
"""
import pytest

from app.services import search_index, semantic_index

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

    monkeypatch.setattr(semantic_index, "_embed", fake_embed)
    semantic_index.reset_availability()
    semantic_index._matrix = None
    semantic_index._query_cache.clear()
    await set_setting("ai.enabled", "true")
    await set_setting("ai.url", "http://ki.test/v1")
    # die Attrappe kennt nur grobe Themenachsen
    monkeypatch.setattr(semantic_index, "MIN_SIMILARITY", 0.25)
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


async def _search(query, **kwargs):
    result = await search_index.search_videos(query, **kwargs)
    return [(v["id"], v.get("match")) for v in result["videos"]], result


async def test_ohne_ki_reine_wortsuche(test_db):
    await _add(test_db, "v1", "Sauerteig ansetzen")
    hits, result = await _search("Sauerteig")
    assert hits == [("v1", None)] and result["semantic"] is False
    assert (await _search("Brot backen"))[0] == []


async def test_verwandtes_ohne_wortgleichheit(test_db, ai):
    await _add(test_db, "teig", "Sauerteig ansetzen")
    await _add(test_db, "loet", "Platine löten für Anfänger")
    await _index()

    hits, result = await _search("Brot backen")
    assert result["semantic"] is True
    assert hits == [("teig", "bedeutung")], "Thema passt, kein Wort gleich - das Lötvideo bleibt draussen"


async def test_doppelt_gefunden_steht_vorn(test_db, ai):
    await _add(test_db, "nurwort", "Brot")                       # Worttreffer, auch Thema
    await _add(test_db, "nursinn", "Hefe und Ofen")              # nur Thema
    await _add(test_db, "fremd", "Brot und Spiele im alten Rom") # Worttreffer
    await _index()
    hits, _ = await _search("Brot")
    kinds = dict(hits)
    assert kinds["nursinn"] == "bedeutung" and kinds["nurwort"] == "beides"
    assert hits[0][1] == "beides", "was beide Suchen finden, führt die Liste an"


async def test_filter_gelten_auch_fuer_bedeutungstreffer(test_db, ai, set_setting):
    await _add(test_db, "arch", "Hefe im Ofen", archived=1)
    await _add(test_db, "lib", "Teig kneten", archived=0)
    await _add(test_db, "kurz", "Ofen in 30 Sekunden", video_type="short")
    await _index()
    assert {h[0] for h in (await _search("Brot backen", archived=False))[0]} == {"lib", "kurz"}
    await set_setting("shorts.exclude", "true")
    assert {h[0] for h in (await _search("Brot backen"))[0]} == {"arch", "lib"}


async def test_ki_faellt_aus_suche_laeuft_weiter(test_db, ai):
    await _add(test_db, "teig", "Sauerteig ansetzen")
    await _index()
    ai["up"] = False
    semantic_index.reset_availability()
    semantic_index._query_cache.clear()
    hits, result = await _search("Sauerteig")
    assert hits == [("teig", None)] and result["semantic"] is False


async def test_aenderung_und_loeschen_ziehen_nach(test_db, ai):
    await _add(test_db, "v1", "Sauerteig ansetzen")
    await _index()
    assert await semantic_index.pending() == 0

    await test_db.execute("UPDATE videos SET title = 'Teleskop für den Mond' WHERE id = 'v1'")
    assert await semantic_index.pending() == 1
    await _index()
    assert (await _search("Stern und Planet"))[0] == [("v1", "bedeutung")]
    assert (await _search("Brot backen"))[0] == []

    await test_db.execute("DELETE FROM videos WHERE id = 'v1'")
    assert await test_db.fetch_val("SELECT COUNT(*) FROM video_embeddings") == 0


async def test_unveraenderter_text_wird_nicht_neu_gerechnet(test_db, ai):
    await _add(test_db, "v1", "Sauerteig ansetzen")
    await _index()
    before = ai["n"]
    await test_db.execute("UPDATE videos SET status = 'ready' WHERE id = 'v1'")   # merkt vor, Text gleich
    await _index()
    assert ai["n"] == before


def test_rangfolgen_verschmelzen():
    assert search_index.fuse_rankings(["a", "b", "c"], ["c", "a", "d"])[:2] == ["a", "c"]
    assert search_index.fuse_rankings(["a"], []) == ["a"]

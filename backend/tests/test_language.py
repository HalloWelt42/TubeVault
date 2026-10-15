"""
Sprache als durchgängiger Aspekt (Wunsch 15.10.2026): Kürzel vereinheitlichen,
Vorrang der Herkünfte, Schutz der Nutzerwahl, Kanalmehrheit, Nachziehen des
Bestands (idempotent) und der Sprachfilter samt Zählern in allen Listen.
"""
import pytest

from app.services import language, language_assign, language_detect, transcripts
from app.services.language import Assignment
from app.services.subtitle_segments import Segment

DEUTSCH = ("Wie man einen Sauerteig ansetzt und richtig füttert",
           "In diesem Video zeige ich dir Schritt für Schritt, wie du deinen eigenen Sauerteig ansetzt.")
ENGLISCH = ("How to build a wooden workbench from scratch",
            "In this video I show you step by step how to build a sturdy workbench for your garage.")


# ─── Kürzel, Namen, Flaggen ───────────────────────────────────────────

@pytest.mark.parametrize("raw, code", [
    ("en", "en"), ("en-US", "en"), ("EN_gb", "en"), ("eng", "en"), ("deu", "de"), ("ger", "de"),
    ("iw", "he"), ("nb", "no"), ("zh-Hans", "zh"), (" fr ", "fr"),
    ("und", None), ("zxx", None), ("xx", None), ("", None), (None, None), ("Deutschland", None),
])
def test_kuerzel_werden_vereinheitlicht(raw, code):
    assert language.normalize(raw) == code


def test_namen_und_flaggen():
    assert language.name("en") == "Englisch"
    assert language.name("de") == "Deutsch"
    assert language.name(language.MIXED) == "Gemischt"
    assert language.name(None) == "Unbekannt"
    assert language.flag("en") == "\U0001F1EC\U0001F1E7"        # Englisch: GB
    assert language.flag("uk") == "\U0001F1FA\U0001F1E6"        # Ukrainisch: UA
    assert language.flag("eu") is None                          # Baskisch: kein eindeutiges Land
    catalog = language.catalog()
    assert {lang.code for lang in catalog.languages} >= {"de", "en", "fr", "es", "it", "pl", "ru", "uk", "pt",
                                                          "nl", "ja", "zh", "tr", "ar", "hi"}
    assert [source.key for source in sorted(catalog.sources, key=lambda s: -s.rank)] == \
        ["hand", "quelle", "untertitel", "text", "kanal"]


def test_filterwerte():
    assert language.parse_filter(["en,DE", "en", "unsinn"]) == ["en", "de"]
    assert language.parse_filter("und,mul") == ["und", "mul"]
    assert language.parse_filter(None) == []


# ─── Vorrang ──────────────────────────────────────────────────────────

def test_vorrang_der_herkuenfte():
    evidence = {language.UNTERTITEL: "en", language.TEXT: "de", language.KANAL: "fr"}
    assert language.decide(language.NONE, evidence) == Assignment("en", "untertitel")
    assert language.decide(language.NONE, {language.TEXT: "de", language.KANAL: "fr"}) == Assignment("de", "text")
    assert language.decide(language.NONE, {language.KANAL: "fr"}) == Assignment("fr", "kanal")
    # Die Angabe beim Laden lässt sich lokal nicht wiederholen: sie bleibt
    assert language.decide(Assignment("es", "quelle"), evidence) == Assignment("es", "quelle")
    # Abgeleitetes ohne Hinweis mehr fällt weg (lieber unbekannt als falsch)
    assert language.decide(Assignment("de", "text"), {language.TEXT: None}) == language.NONE


def test_nutzerwahl_bleibt_immer():
    evidence = {language.UNTERTITEL: "en", language.TEXT: "en"}
    assert language.decide(Assignment("de", "hand"), evidence) == Assignment("de", "hand")
    assert not language.may_replace("hand", "quelle")
    assert language.may_replace("hand", "hand")
    assert language.may_replace("text", "quelle")
    assert language.may_replace("quelle", "quelle")
    assert not language.may_replace("quelle", "untertitel")


def test_kanalmehrheit():
    assert language.channel_language({"de": 2}) is None                     # zu wenige bekannte
    assert language.channel_language({"de": 9, "en": 1}) == "de"             # 90 %
    assert language.channel_language({"de": 8, "en": 2}) == language.MIXED   # 80 %: gemischt
    assert language.channel_language({"de": 3, "xx": 50}) == "de"            # Unbekanntes zählt nicht


# ─── Erkennung aus dem Text ───────────────────────────────────────────

def test_erkennung_aus_titel_und_beschreibung():
    assert language_detect.detect(*DEUTSCH).code == "de"
    assert language_detect.detect(*ENGLISCH).code == "en"
    assert language_detect.detect("Vlog 12") is None                          # zu kurz
    assert language_detect.detect("https://example.com #tag @name 12:30") is None


def test_text_wird_bereinigt():
    text = language_detect.clean_text("Titel #schlagwort", "Mehr unter https://example.com um 12:30 @kanal")
    assert "https" not in text and "#" not in text and "@" not in text and "12:30" not in text


# ─── Datenbank: Bestand, Vorrang, Nachziehen ──────────────────────────

async def _video(db, vid, title, description=None, channel="UCkanal0000000000000001", lang=None, source=None):
    await db.execute(
        """INSERT INTO videos (id, title, description, channel_id, channel_name, status, language, language_source)
           VALUES (?, ?, ?, ?, 'Kanal', 'ready', ?, ?)""", (vid, title, description, channel, lang, source))


async def _lang(db, vid, table="videos", key="id"):
    row = await db.fetch_one(f"SELECT language, language_source FROM {table} WHERE {key} = ?", (vid,))
    return row["language"], row["language_source"]


async def test_bestand_wird_uebernommen_und_vereinheitlicht(test_db):
    """Migration v53: vorhandene Angaben gelten als Angabe beim Laden."""
    for vid, raw in (("v1", "en-US"), ("v2", "de"), ("v3", "und")):
        await test_db.execute("INSERT INTO videos (id, title, status, language) VALUES (?, 'T', 'ready', ?)", (vid, raw))
    assert await language_assign.install_schema(test_db.conn, adopt_existing=True) == 2
    assert await _lang(test_db, "v1") == ("en", "quelle")
    assert await _lang(test_db, "v2") == ("de", "quelle")
    assert await _lang(test_db, "v3") == (None, None)
    # ein zweiter Lauf ändert nichts
    assert await language_assign.install_schema(test_db.conn, adopt_existing=True) == 0


async def test_angabe_beim_laden_hat_vorrang_vor_text(test_db):
    await _video(test_db, "v1", *ENGLISCH)
    await language_assign.refresh_videos(["v1"])
    assert await _lang(test_db, "v1") == ("en", "text")
    assert await language_assign.record("v1", "de-DE", language.QUELLE)
    await language_assign.refresh_videos(["v1"])
    assert await _lang(test_db, "v1") == ("de", "quelle")
    # Untertitel ist schwächer als die Angabe beim Laden
    assert not await language_assign.record("v1", "fr", language.UNTERTITEL)
    assert await _lang(test_db, "v1") == ("de", "quelle")


async def test_untertitel_vor_text(test_db):
    await _video(test_db, "v1", *DEUTSCH)
    await transcripts.store("v1", "en", "ai", [Segment(start=0, end=2, text="Hello there.")])
    await language_assign.refresh_videos(["v1"])
    assert await _lang(test_db, "v1") == ("en", "untertitel")


async def test_nutzerwahl_uebersteht_neubewertung(test_db):
    await _video(test_db, "v1", *ENGLISCH, lang="en", source="quelle")
    assert await language_assign.set_by_user(["v1"], "pl") == 1
    assert await _lang(test_db, "v1") == ("pl", "hand")
    # Laden, Transkript und ein neuer Stand der Regeln ändern nichts
    assert not await language_assign.record("v1", "en", language.QUELLE)
    await test_db.execute("UPDATE videos SET language_checked = 0")
    assert await language_assign.catch_up() >= 1
    await language_assign.refresh_videos(["v1"])
    assert await _lang(test_db, "v1") == ("pl", "hand")
    # Zurück auf automatisch: aus dem Text bestimmt
    assert await language_assign.set_by_user(["v1"], None) == 1
    assert await _lang(test_db, "v1") == ("en", "text")
    with pytest.raises(ValueError):
        await language_assign.set_by_user(["v1"], "klingonisch")


async def test_kanalsprache_und_kanalmehrheit(test_db):
    deutsch_kanal, gemischt_kanal = "UCdeutsch00000000000000a", "UCgemischt0000000000000a"
    for channel in (deutsch_kanal, gemischt_kanal):
        await test_db.execute("INSERT INTO subscriptions (channel_id, channel_name) VALUES (?, 'K')", (channel,))
    for n in range(4):
        await _video(test_db, f"de{n}", *DEUTSCH, channel=deutsch_kanal)
    await _video(test_db, "ohne", "Vlog 12", channel=deutsch_kanal)          # kein eigener Hinweis
    for n in range(2):
        await _video(test_db, f"mde{n}", *DEUTSCH, channel=gemischt_kanal)
        await _video(test_db, f"men{n}", *ENGLISCH, channel=gemischt_kanal)
    await _video(test_db, "mohne", "Vlog 13", channel=gemischt_kanal)

    while await language_assign.catch_up():
        pass
    await language_assign.refresh_channels(None)

    assert await test_db.fetch_val("SELECT language FROM subscriptions WHERE channel_id = ?", (deutsch_kanal,)) == "de"
    assert await test_db.fetch_val("SELECT language FROM subscriptions WHERE channel_id = ?", (gemischt_kanal,)) == "mul"
    assert await _lang(test_db, "ohne") == ("de", "kanal")
    assert await _lang(test_db, "mohne") == (None, None)            # gemischter Kanal: keine Vermutung
    assert await _lang(test_db, "de0") == ("de", "text")

    # Wird der Kanal gemischt, fällt die Kanalsprache an Videos ohne Hinweis weg
    for n in range(3):
        await _video(test_db, f"en{n}", *ENGLISCH, channel=deutsch_kanal)
    await language_assign.refresh_videos([f"en{n}" for n in range(3)])
    assert await test_db.fetch_val("SELECT language FROM subscriptions WHERE channel_id = ?", (deutsch_kanal,)) == "mul"
    assert await _lang(test_db, "ohne") == (None, None)


async def test_nachziehen_ist_idempotent(test_db):
    await _video(test_db, "v1", *DEUTSCH)
    await _video(test_db, "v2", *ENGLISCH, lang="es", source="quelle")
    await test_db.execute(
        """INSERT INTO rss_entries (video_id, channel_id, title) VALUES
           ('v2', 'UCkanal0000000000000001', 'Ein Titel'), ('neu1', 'UCkanal0000000000000001', ?)""",
        (ENGLISCH[0],))
    assert await language_assign.pending() == 4

    total = 0
    while done := await language_assign.catch_up(limit=1):
        total += done
    assert await language_assign.pending() == 0
    before = await test_db.fetch_all("SELECT id, language, language_source FROM videos ORDER BY id")
    feed_before = await test_db.fetch_all("SELECT video_id, language, language_source FROM rss_entries ORDER BY id")
    assert await language_assign.catch_up() == 0                   # nichts mehr offen
    await language_assign.refresh_channels(None)
    after = await test_db.fetch_all("SELECT id, language, language_source FROM videos ORDER BY id")
    feed_after = await test_db.fetch_all("SELECT video_id, language, language_source FROM rss_entries ORDER BY id")
    assert [tuple(r) for r in before] == [tuple(r) for r in after]
    assert [tuple(r) for r in feed_before] == [tuple(r) for r in feed_after]
    # Der Feed-Eintrag übernimmt die Angabe am geladenen Video
    assert await _lang(test_db, "v2", "rss_entries", "video_id") == ("es", "quelle")
    assert await _lang(test_db, "neu1", "rss_entries", "video_id") == ("en", "text")


async def test_neue_feed_eintraege_gleich_beim_eintragen(test_db):
    await test_db.execute(
        "INSERT INTO rss_entries (video_id, channel_id, title) VALUES ('neu1', 'UCkanal0000000000000001', ?)",
        (ENGLISCH[0],))
    await language_assign.refresh_new_entries("UCkanal0000000000000001")
    assert await _lang(test_db, "neu1", "rss_entries", "video_id") == ("en", "text")


async def test_ki_transkript_bekommt_nur_belegte_sprache(test_db):
    """Eine aus dem Titel erkannte Sprache wird der Spracherkennung nicht
    vorgegeben - deutscher Titel über englischem Ton würde sonst falsch."""
    await _video(test_db, "ausdemtext1", *DEUTSCH, lang="de", source="text")
    job = await transcripts.claim_ai("mac")
    assert job.video_id == "ausdemtext1" and job.language is None
    await test_db.execute("DELETE FROM ai_transcriptions")
    await test_db.execute("UPDATE videos SET language_source = 'quelle'")
    assert (await transcripts.claim_ai("mac")).language == "de"


# ─── Endpunkte: Filter und Zähler ─────────────────────────────────────

@pytest.fixture
async def stocked(test_db):
    await test_db.execute("INSERT INTO subscriptions (channel_id, channel_name, language) VALUES "
                          "('UCa', 'Deutsch', 'de'), ('UCb', 'Englisch', 'en'), ('UCc', 'Bunt', 'mul'), ('UCd', 'Neu', NULL)")
    for vid, title, lang, channel in (("d1", "Sauerteig Deutsch", "de", "UCa"), ("d2", "Sauerteig Brot", "de", "UCa"),
                                      ("e1", "Sauerteig english", "en", "UCb"), ("x1", "Sauerteig ohne", None, "UCd")):
        await test_db.execute(
            "INSERT INTO videos (id, title, channel_id, status, language, language_source) VALUES (?, ?, ?, 'ready', ?, ?)",
            (vid, title, channel, lang, "quelle" if lang else None))
        await test_db.execute(
            "INSERT INTO rss_entries (video_id, channel_id, title, language, language_source) VALUES (?, ?, ?, ?, ?)",
            (f"r{vid}", channel, title, lang, "text" if lang else None))
    return test_db


def _counts(items):
    return {item["code"]: item["count"] for item in items}


async def test_bibliothek_filter_und_zaehler(async_client_factory, stocked):
    from app.routers import videos
    async with await async_client_factory(videos.router) as client:
        r = await client.get("/api/videos", params={"language": "en", "with_language_counts": True})
        body = r.json()
        assert [v["id"] for v in body["videos"]] == ["e1"]
        assert body["videos"][0]["language"] == "en" and body["videos"][0]["language_source"] == "quelle"
        assert _counts(body["language_counts"]) == {"de": 2, "en": 1, "und": 1}   # ohne den Sprachfilter
        r = await client.get("/api/videos", params=[("language", "de"), ("language", "und")])
        assert {v["id"] for v in r.json()["videos"]} == {"d1", "d2", "x1"}
        assert r.json()["language_counts"] is None                               # nur auf Wunsch
        r = await client.get("/api/videos", params={"language": "en", "channel_ids": "UCa", "with_language_counts": True})
        assert r.json()["total"] == 0 and _counts(r.json()["language_counts"]) == {"de": 2}


async def test_sprache_von_hand_setzen(async_client_factory, stocked):
    from app.routers import videos
    async with await async_client_factory(videos.router) as client:
        r = await client.post("/api/videos/language/batch", json={"video_ids": ["x1"], "language": "fr-FR"})
        assert r.status_code == 200 and r.json() == {"updated": 1, "language": "fr"}
        assert await _lang(stocked, "x1") == ("fr", "hand")
        assert (await client.post("/api/videos/language/batch",
                                  json={"video_ids": ["x1"], "language": "xx"})).status_code == 400
        assert (await client.post("/api/videos/language/batch",
                                  json={"video_ids": ["gibtsnicht"], "language": "de"})).status_code == 404


async def test_feed_filter_und_zaehler(async_client_factory, stocked):
    from app.routers import feed_router
    async with await async_client_factory(feed_router.router) as client:
        r = await client.get("/api/subscriptions/feed", params={"language": "de,en"})
        body = r.json()
        assert {e["video_id"] for e in body["entries"]} == {"rd1", "rd2", "re1"}
        assert _counts(body["language_counts"]) == {"de": 2, "en": 1, "und": 1}


async def test_kanaele_filter_und_zaehler(async_client_factory, stocked):
    from app.routers import subscriptions
    async with await async_client_factory(subscriptions.router) as client:
        body = (await client.get("/api/subscriptions", params={"language": "mul"})).json()
        assert [s["channel_id"] for s in body["subscriptions"]] == ["UCc"] and body["total"] == 1
        assert _counts(body["language_counts"]) == {"de": 1, "en": 1, "mul": 1, "und": 1}
        body = (await client.get("/api/subscriptions")).json()
        assert body["total"] == 4 and {s["language"] for s in body["subscriptions"]} == {"de", "en", "mul", None}


async def test_suche_filter_und_zaehler(async_client_factory, stocked):
    from app.routers import search
    async with await async_client_factory(search.router) as client:
        body = (await client.get("/api/search", params={"q": "Sauerteig", "language": "en"})).json()
        videos = body["sections"]["videos"]
        assert [v["id"] for v in videos["items"]] == ["e1"] and videos["total"] == 1
        assert [e["video_id"] for e in body["sections"]["abos"]["items"]] == ["re1"]
        # Zähler über Videos und noch nicht geladene Feed-Einträge, ohne den Sprachfilter
        assert _counts(body["language_counts"]) == {"de": 4, "en": 2, "und": 2}


async def test_katalog(async_client_factory, test_db):
    from app.routers import languages
    async with await async_client_factory(languages.router) as client:
        body = (await client.get("/api/languages")).json()
        english = next(lang for lang in body["languages"] if lang["code"] == "en")
        assert english == {"code": "en", "name": "Englisch", "flag": "\U0001F1EC\U0001F1E7"}
        assert body["mixed"]["code"] == "mul" and body["unknown"]["code"] == "und"


async def test_nachziehen_ist_in_den_hintergrundarbeiten_sichtbar(test_db):
    from app.services import background_work
    for n in range(60):
        await test_db.execute("INSERT INTO videos (id, title, status) VALUES (?, 'T', 'ready')", (f"v{n:03d}",))
    item = next(i for i in await background_work.overview() if i.key == "languages")
    assert item.total == 60 and item.done == 0 and item.label == "Sprachen werden zugeordnet"
    while await language_assign.catch_up(limit=25):
        pass
    assert not [i for i in await background_work.overview() if i.key == "languages"]


async def test_schlagwoerter_folgen_dem_sprachfilter(async_client_factory, stocked):
    from app.routers import videos
    await stocked.execute("""UPDATE videos SET tags = '["brot"]' WHERE id = 'd1'""")
    await stocked.execute("""UPDATE videos SET tags = '["bread"]' WHERE id = 'e1'""")
    async with await async_client_factory(videos.router) as client:
        tags = (await client.get("/api/videos/tags", params={"language": "en"})).json()
        assert [t["tag"] for t in tags] == ["bread"]

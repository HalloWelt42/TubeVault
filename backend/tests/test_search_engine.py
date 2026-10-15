"""
Suche über alles (app/services/search).

Kontrakt:
- Suchsprache: "Wortfolge", -Wort, oder, kanal:, sprache:, länge:, jahr:, in:
- Wortanfänge erst ab vier Zeichen ("Lem" findet nicht "Lemma")
- Rangfolge: Titel vor Kanal vor Kapitel vor Beschreibung, ganze Wörter vor Wortanfängen
- Bereiche: Videos, Gesagtes (mit Zeit), Kapitel, Abos (noch nicht geladen),
  Kanäle, Playlists, Musik; jeder zählt nach denselben Filtern
- Meintest du, Ergänzen beim Tippen, gemerkte Suchen mit neuen Treffern
"""
import pytest

from app.services import search_index, transcripts
from app.services.search import engine, query as query_module, saved, vocabulary
from app.services.search.filters import SearchFilters
from app.services.search.saved import SavedSearchInput
from app.services.subtitle_segments import Segment


@pytest.fixture(autouse=True)
def fresh_vocabulary():
    vocabulary.reset()
    yield
    vocabulary.reset()


async def _video(db, vid, title, *, channel="Kanal", channel_id="UCkanal", description=None, archived=0,
                 duration=600, language="de", upload="2024-05-01 00:00:00", source="youtube", position=0,
                 download="2024-05-02 00:00:00"):
    await db.execute(
        """INSERT INTO videos (id, title, channel_name, channel_id, status, is_archived, description, duration,
                               language, upload_date, source, last_position, download_date)
           VALUES (?, ?, ?, ?, 'ready', ?, ?, ?, ?, ?, ?, ?, ?)""",
        (vid, title, channel, channel_id, archived, description, duration, language, upload, source, position, download))


async def _ids(text, section="videos", **filters):
    page = await engine.section(section, text, SearchFilters(**filters), per_page=100)
    return [item.id for item in page.items]


# ─── Suchsprache ──────────────────────────────────────────────────────

def test_suchsprache_wird_gelesen():
    q = query_module.parse('Kernfusion "Harald Lesch" -Werbung ITER oder Tokamak kanal:"Terra X" '
                           'sprache:englisch länge:>20 jahr:2020-2024 in:archiv')
    assert q.expression() == '"kernfusion"* AND "harald lesch" AND ("iter"* OR "tokamak"*)'
    assert q.full_expression().endswith('NOT ("werbung")')
    ops = q.operators
    assert (ops.channel, ops.languages, ops.min_seconds, ops.year_from, ops.year_to, ops.location) == \
        ("Terra X", ["en"], 1200, 2020, 2024, "archiv")


def test_unlesbare_angabe_zaehlt_als_woerter():
    q = query_module.parse("länge:viel")
    assert [t.words for t in q.terms] == [["länge"], ["viel"]]
    assert q.operators.min_seconds is None


def test_kurze_woerter_nur_ganz():
    assert query_module.parse("lem").expression() == '"lem"'
    assert query_module.parse("kernfu").expression() == '"kernfu"*'
    assert query_module.parse('"Kern fu"').expression() == '"kern fu"'


async def test_lem_findet_nicht_lemma(test_db):
    await _video(test_db, "lem00000001", "Stanislaw Lem: Solaris")
    await _video(test_db, "lem00000002", "Das Pumping Lemma")
    assert await _ids("Lem") == ["lem00000001"]
    assert await _ids("Lemma") == ["lem00000002"]


async def test_wortfolge_ausschluss_und_oder(test_db):
    await _video(test_db, "v1000000001", "Harald Lesch erklärt Kernfusion")
    await _video(test_db, "v1000000002", "Lesch und Harald über Kernfusion Werbung")
    await _video(test_db, "v1000000003", "Tokamak im Detail")
    assert await _ids('"Harald Lesch"') == ["v1000000001"]
    assert set(await _ids("Kernfusion")) == {"v1000000001", "v1000000002"}
    assert await _ids("Kernfusion -Werbung") == ["v1000000001"]
    assert set(await _ids("Tokamak oder Lesch")) == {"v1000000001", "v1000000002", "v1000000003"}


async def test_angaben_wirken_als_filter(test_db):
    await _video(test_db, "v2000000001", "Kernfusion kurz", duration=300, channel="ARTE")
    await _video(test_db, "v2000000002", "Kernfusion lang", duration=3000, channel="Terra X Lesch", language="en")
    assert await _ids("Kernfusion länge:>20") == ["v2000000002"]
    assert await _ids("Kernfusion kanal:terra") == ["v2000000002"]
    assert await _ids("Kernfusion sprache:de") == ["v2000000001"]


# ─── Rangfolge und Fundorte ───────────────────────────────────────────

async def test_titel_vor_kapitel_vor_beschreibung(test_db):
    await _video(test_db, "desc0000001", "Ein Vortrag", description="Es geht um Oszilloskope im Labor")
    await _video(test_db, "chap0000001", "Messtechnik")
    await _video(test_db, "titl0000001", "Oszilloskop für Einsteiger")
    await test_db.execute("INSERT INTO chapters (video_id, title, start_time) VALUES (?, ?, ?)",
                          ("chap0000001", "Das Oszilloskop einstellen", 95.0))
    assert await _ids("Oszilloskop") == ["titl0000001", "chap0000001", "desc0000001"]
    page = await engine.section("videos", "Oszilloskop", SearchFilters(), per_page=10)
    found = {item.id: [f.where for f in item.found] for item in page.items}
    assert found["chap0000001"] == ["kapitel"] and found["desc0000001"] == ["beschreibung"]


async def test_mehr_fundstellen_vor_kurzem_titel(test_db):
    await _video(test_db, "kurz0000001", "Brauchen wir die Kernfusion")
    await _video(test_db, "voll0000001", "Kernfusion: Löst sie alle Probleme?", description="Alles über Kernfusion")
    await test_db.execute("INSERT INTO chapters (video_id, title, start_time) VALUES ('voll0000001', 'Wie effizient ist Kernfusion?', 10)")
    assert await _ids("Kernfusion") == ["voll0000001", "kurz0000001"]


async def test_ganzes_wort_vor_wortanfang(test_db):
    await _video(test_db, "anf00000001", "Fusionskraftwerk gebaut")
    await _video(test_db, "gnz00000001", "Fusion verstehen")
    assert await _ids("Fusion") == ["gnz00000001", "anf00000001"]


async def test_kapitel_mit_zeit(test_db):
    await _video(test_db, "kap00000001", "Livestream")
    for title, start in [("Laserfusion", 1905.0), ("Wie effizient ist Kernfusion?", 3155.0), ("Fragen", 3220.0)]:
        await test_db.execute("INSERT INTO chapters (video_id, title, start_time) VALUES (?, ?, ?)",
                              ("kap00000001", title, start))
    page = await engine.section("kapitel", "Kernfusion", SearchFilters())
    assert page.total == 1
    assert [(s.start, s.text) for s in page.items[0].spots] == [(3155.0, "Wie effizient ist Kernfusion?")]


async def test_gesagtes_mit_ausschnitt_und_herkunft(test_db):
    await _video(test_db, "say00000001", "Interview")
    long_text = "Vorher reden wir lange über anderes. " * 12 + "Dann kommt die Kernfusion zur Sprache."
    await transcripts.store("say00000001", "de", "auto",
                            [Segment(start=1639.0, end=1650.0, text=long_text)], imported=True, spoken=True)
    page = await engine.section("gesagt", "Kernfusion", SearchFilters())
    spot = page.items[0].spots[0]
    assert spot.start == 1639.0 and spot.origin == "auto"
    assert "Kernfusion" in spot.text and spot.text.startswith("...")


# ─── Weitere Bereiche ─────────────────────────────────────────────────

async def test_abos_nur_noch_nicht_geladene(test_db):
    await test_db.execute("INSERT INTO subscriptions (channel_id, channel_name) VALUES ('UCurknall', 'Urknall, Weltall')")
    for entry_id, video_id, title in [(1, "feed0000001", "Tritium in der Kernfusion"),
                                      (2, "feed0000002", "Kernfusion schon geladen")]:
        await test_db.execute(
            "INSERT INTO rss_entries (id, video_id, channel_id, title, published) VALUES (?, ?, 'UCurknall', ?, '2026-05-04')",
            (entry_id, video_id, title))
    await _video(test_db, "feed0000002", "Kernfusion schon geladen")
    page = await engine.section("abos", "Kernfusion", SearchFilters())
    assert [hit.video_id for hit in page.items] == ["feed0000001"]
    assert page.items[0].channel_name == "Urknall, Weltall"
    # Feed-Einträge passen nicht zu "nur Archiv"
    assert (await engine.section("abos", "Kernfusion", SearchFilters(location="archiv"))).total == 0


async def test_kanaele_playlists_musik(test_db):
    await test_db.execute(
        "INSERT INTO subscriptions (channel_id, channel_name, channel_description) VALUES (?, ?, ?)",
        ("UClesch", "Terra X Lesch & Co", "Wissenschaft mit Harald Lesch: Kernfusion, Klima, Kosmos"))
    await test_db.execute("INSERT INTO playlists (name, description) VALUES ('Fusion und Plasma', 'Vorträge')")
    await test_db.execute(
        """INSERT INTO music_files (id, path, size, mtime, title, artist, genre, lyrics_text)
           VALUES ('f1', 'a/b.flac', 1, 1, 'Sonnenwind', 'Plasma Band', 'Ambient', 'tief im Kern der Fusion')""")
    overview = await engine.overview("Fusion", SearchFilters(), with_meaning=False)
    assert [c.channel_name for c in overview.sections["kanaele"].items] == ["Terra X Lesch & Co"]
    assert [p.name for p in overview.sections["playlists"].items] == ["Fusion und Plasma"]
    music = overview.sections["musik"].items[0]
    assert music.track.title == "Sonnenwind" and music.found == ["liedtext"]


async def test_ort_und_stand(test_db):
    await _video(test_db, "lib00000001", "Sauerteig ansetzen")
    await _video(test_db, "arc00000001", "Sauerteig füttern", archived=1)
    await _video(test_db, "own00000001", "Sauerteig eigener Film", source="local", position=590)
    assert set(await _ids("Sauerteig", location="bibliothek")) == {"lib00000001", "own00000001"}
    assert await _ids("Sauerteig", location="archiv") == ["arc00000001"]
    assert await _ids("Sauerteig in:eigene") == ["own00000001"]
    assert await _ids("Sauerteig", state="finished") == ["own00000001"]


async def test_sprachzaehler_vor_dem_sprachfilter(test_db):
    await _video(test_db, "de000000001", "Kernfusion erklärt", language="de")
    await _video(test_db, "en000000001", "Kernfusion explained", language="en")
    overview = await engine.overview("Kernfusion", SearchFilters(languages=["en"]), with_meaning=False)
    assert overview.sections["videos"].total == 1
    assert {c.code: c.count for c in overview.language_counts} == {"de": 1, "en": 1}


async def test_ordnung_neu(test_db):
    await _video(test_db, "alt00000001", "Kernfusion damals", upload="2010-01-01 00:00:00")
    await _video(test_db, "neu00000001", "Kernfusion heute", upload="2026-01-01 00:00:00")
    assert await _ids("Kernfusion", order="neu") == ["neu00000001", "alt00000001"]
    assert await _ids("Kernfusion", order="alt") == ["alt00000001", "neu00000001"]


# ─── Meintest du, Ergänzen, Vorschau ──────────────────────────────────

async def test_meintest_du(test_db):
    for i in range(3):
        await _video(test_db, f"kf000000{i:03d}", f"Kernfusion Teil {i}")
    overview = await engine.overview("kernfusoin", SearchFilters(), with_meaning=False)
    assert overview.sections["videos"].total == 0
    assert overview.suggestion and overview.suggestion.text == "kernfusion" and overview.suggestion.total == 3


async def test_ergaenzen_beim_tippen(test_db):
    for i in range(3):
        await _video(test_db, f"erg00000{i:03d}", f"Kernfusion und Kernspaltung {i}")
    await _video(test_db, "erg00000099", "Kernfusion Löten")
    assert await vocabulary.complete("Lesch kernf") == ["Lesch kernfusion"]
    assert await vocabulary.complete("kern") == ["kernfusion", "kernspaltung"]
    assert await vocabulary.complete("kernfusion ") == []


async def test_vorschau_mit_allen_fundstellen(test_db):
    await _video(test_db, "pre00000001", "Kernfusion: Löst sie alle Probleme?",
                 description="Was kann Kernfusion - und was nicht? " + "Mehr dazu. " * 60)
    await test_db.execute("INSERT INTO chapters (video_id, title, start_time) VALUES (?, ?, ?)",
                          ("pre00000001", "Wie effizient ist Kernfusion?", 3155.0))
    await transcripts.store("pre00000001", "de", "ai", [Segment(start=10.0, end=20.0, text="Die Kernfusion braucht Tritium.")])
    spots = await engine.spots_of("pre00000001", "Kernfusion")
    assert spots.title_hit and "Kernfusion" in spots.description
    assert [(s.kind, s.start) for s in spots.spots] == [("gesagt", 10.0), ("kapitel", 3155.0)]


# ─── Gemerkte Suchen ──────────────────────────────────────────────────

async def test_gemerkte_suche_zaehlt_neues(test_db):
    await _video(test_db, "old00000001", "Kernfusion alt", download="2020-01-01 00:00:00")
    created = await saved.create(SavedSearchInput(query="Kernfusion", filters=SearchFilters(languages=["de"])))
    assert created.name == "Kernfusion" and created.new_videos == 0
    await _video(test_db, "new00000001", "Kernfusion neu", download="2999-01-01 00:00:00")
    listed = await saved.all_saved()
    assert listed[0].new_videos == 1 and listed[0].filters.languages == ["de"]
    await test_db.execute("UPDATE saved_searches SET seen_at = '2999-06-01 00:00:00'")
    assert (await saved.all_saved())[0].new_videos == 0
    assert await saved.delete(created.id)


# ─── Listenfilter der Bibliothek ──────────────────────────────────────

async def test_listenfilter_folgt_den_wortregeln(test_db):
    await _video(test_db, "lst00000001", "Stanislaw Lem: Solaris")
    await _video(test_db, "lst00000002", "Das Pumping Lemma")
    await search_index.refresh_before_query()
    sql, params = search_index.condition("Lem")
    rows = await test_db.fetch_all(f"SELECT id FROM videos v WHERE {sql}", params)
    assert [r["id"] for r in rows] == ["lst00000001"]
    sql, params = search_index.condition("Solaris -Lemma")
    rows = await test_db.fetch_all(f"SELECT id FROM videos v WHERE {sql}", params)
    assert [r["id"] for r in rows] == ["lst00000001"]

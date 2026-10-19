"""
Eigener Schlagwort-Index (entschieden 19.10.2026, video_tags).

Kontrakt:
- Ein Schlagwort findet genau seine Videos, gleich wie es im JSON steht
  (\\u-Umschreibung), mit Umlaut oder fremder Schrift, in beliebiger
  Groß- und Kleinschreibung; Anführungszeichen, % und _ sind gewöhnliche
  Zeichen. Mehrere Schlagwörter: oder.
- Die Zählung der Schlagwortleiste ist genau die Zahl, die die Liste mit
  diesem Schlagwort zeigt (dieselben Filter, jedes Video einmal je Schlüssel).
- Jeder Schreibweg auf videos.tags hält den Index aktuell (Trigger und eine
  Funktion), Löschen nimmt die Zeilen mit.
- Der Bestand wird in Portionen aufgenommen, unterbrechbar; die Warteliste
  ist der Stand. Solange sie lang ist, zeigt die Statusleiste es.
- Kategorie-Regeln "Schlagwort enthält" suchen Teilwörter auf dem Schlüssel.
"""
import json

from app.models.categories import RuleIn
from app.routers import videos
from app.services import background_work, category_rules, video_tags
from app.services.metadata_service import metadata_service


async def _video(db, vid, tags, archived=0, raw=None):
    await db.execute(
        """INSERT INTO videos (id, title, channel_id, channel_name, tags, status, is_archived, upload_date)
           VALUES (?, ?, 'UCa', 'Kanal', ?, 'ready', ?, '20240101')""",
        (vid, f"Video {vid}", raw if raw is not None else json.dumps(tags), archived))   # ensure_ascii: \\u-umschrieben


async def _bestand(db):
    await _video(db, "koerper001", ["Körper", "einfach erklärt"])
    await _video(db, "koerper002", ["körper", "KÖRPER"])          # zwei Schreibweisen, ein Schlüssel
    await _video(db, "techno0001", ["техно", "Musik"])
    await _video(db, "zitat00001", ['Der "Beste"', "C:\\Pfad"])
    await _video(db, "prozent001", ["100%", "a_b"])
    await _video(db, "prozent002", ["1000", "aXb", "musik"])
    await _video(db, "archiv0001", ["Körper"], archived=1)


def test_suchschluessel():
    composed, decomposed = "Körper", "Ko\u0308rper"
    assert video_tags.search_key(composed) == video_tags.search_key(decomposed) == "körper"
    assert video_tags.search_key("  Einfach   Erklärt ") == "einfach erklärt"
    assert video_tags.search_key("ТЕХНО") == "техно"
    assert video_tags.rows_of("v", json.dumps(["Körper", "KÖRPER", " "])) == [("v", "körper", "Körper")]
    assert video_tags.parse("kaputt") == [] and video_tags.parse(None) == []


async def _list(client, **params):
    return (await client.get("/api/videos", params={"per_page": 100, **params})).json()


async def test_listenfilter_findet_jedes_schlagwort(test_db, async_client_factory):
    await _bestand(test_db)
    async with await async_client_factory(videos.router) as client:
        async def ids(tag, **extra):
            return sorted(v["id"] for v in (await _list(client, tags=tag, is_archived=False, **extra))["videos"])
        assert await ids("Körper") == ["koerper001", "koerper002"]
        assert await ids("KÖRPER") == ["koerper001", "koerper002"]
        assert await ids("einfach erklärt") == ["koerper001"]
        assert await ids("ТЕХНО") == ["techno0001"]
        assert await ids('der "beste"') == ["zitat00001"]
        assert await ids("C:\\Pfad") == ["zitat00001"]
        assert await ids("100%") == ["prozent001"]               # % ist kein Platzhalter
        assert await ids("a_b") == ["prozent001"]                # _ auch nicht
        assert await ids("Musik") == ["prozent002", "techno0001"]
        assert await ids("techno,musik") == ["prozent002", "techno0001"]   # mehrere: oder (techno ist anders geschrieben)
        assert await ids("техно,100%") == ["prozent001", "techno0001"]
        assert await ids("Körp") == []                           # genau, kein Teilwort
        archived = await _list(client, tags="Körper", is_archived=True)
        assert [v["id"] for v in archived["videos"]] == ["archiv0001"]


async def test_zaehlung_gleich_der_liste(test_db, async_client_factory):
    await _bestand(test_db)
    async with await async_client_factory(videos.router) as client:
        for archived in (False, True):
            counted = (await client.get("/api/videos/tags", params={"archived": archived})).json()
            assert counted, archived
            for entry in counted:
                listed = await _list(client, tags=entry["tag"], is_archived=archived)
                assert listed["total"] == entry["count"], entry
        counted = {e["key"]: e for e in (await client.get("/api/videos/tags")).json()}
        assert (counted["körper"]["count"], counted["musik"]["count"]) == (2, 2)
        assert counted["körper"]["tag"] in ("Körper", "körper")
        # weitere Filter der Liste gelten auch für die Zählung
        searched = (await client.get("/api/videos/tags", params={"search": "koerper001"})).json()
        listed = await _list(client, tags="Körper", is_archived=False, search="koerper001")
        assert {e["key"]: e["count"] for e in searched}.get("körper") == listed["total"]


async def test_jeder_schreibweg_haelt_den_index_aktuell(test_db, async_client_factory):
    await _bestand(test_db)
    async with await async_client_factory(videos.router) as client:
        assert (await _list(client, tags="Gespräche"))["total"] == 0
        await metadata_service.update_video("koerper001", {"tags": ["Gespräche"]})
        assert [v["id"] for v in (await _list(client, tags="gespräche"))["videos"]] == ["koerper001"]
        assert [v["id"] for v in (await _list(client, tags="Körper", is_archived=False))["videos"]] == ["koerper002"]
        await test_db.execute("""UPDATE videos SET tags = '["neu"]' WHERE id = 'techno0001'""")   # ein anderer Weg
        assert [v["id"] for v in (await _list(client, tags="NEU"))["videos"]] == ["techno0001"]
    await test_db.execute("DELETE FROM videos WHERE id = 'techno0001'")
    assert not await test_db.fetch_val("SELECT COUNT(*) FROM video_tags WHERE video_id = 'techno0001'")


async def test_bestand_in_portionen_unterbrechbar(test_db, monkeypatch):
    """Wie nach der Einführung: alle Videos stehen auf der Warteliste; jede
    Portion nimmt einige auf, ein Abbruch verliert nichts."""
    for n in range(120):
        await _video(test_db, f"v{n:09d}", [f"Schlagwort {n % 7}", "Gemeinsam"])
    await test_db.execute("DELETE FROM video_tags")
    await test_db.execute("INSERT OR IGNORE INTO video_tags_dirty (video_id) SELECT id FROM videos")
    background_work._forget("video_tags")
    item = await background_work._video_tags()
    assert item and (item.done, item.total, item.label) == (0, 120, "Schlagwörter werden erfasst")
    assert await video_tags.flush(limit=50) == 50
    assert await video_tags.pending() == 70                       # "Neustart": der Rest bleibt vorgemerkt
    assert (await background_work._video_tags()).done == 50
    monkeypatch.setattr(video_tags, "BATCH", 30)
    await video_tags.background_catch_up()
    assert await video_tags.pending() == 0
    assert await test_db.fetch_val("SELECT COUNT(DISTINCT video_id) FROM video_tags WHERE tag_suche = 'gemeinsam'") == 120
    assert await background_work._video_tags() is None


async def test_listenabfrage_nutzt_den_index(test_db):
    plan = await test_db.fetch_all(
        "EXPLAIN QUERY PLAN SELECT video_id FROM video_tags WHERE tag_suche IN (?, ?)", ("a", "b"))
    assert any("idx_video_tags_suche" in row["detail"] for row in plan)


async def test_kategorie_regel_teilwort_auf_dem_schluessel(test_db):
    await _bestand(test_db)
    cursor = await test_db.execute("INSERT INTO categories (name, color) VALUES ('Körper', '#2196F3')")
    cid = cursor.lastrowid
    await category_rules.save_rules(cid, [RuleIn(kind="tag", value="KÖRP"), RuleIn(kind="tag", value="тех")])
    members = {row["video_id"] for row in await test_db.fetch_all(
        "SELECT video_id FROM video_categories WHERE category_id = ?", (cid,))}
    assert members == {"koerper001", "koerper002", "archiv0001", "techno0001"}


async def test_regel_ruht_solange_der_index_nachzieht(test_db):
    """Nach der Einführung, bevor der Bestand aufgenommen ist: eine Regel
    "Schlagwort enthält" nimmt niemanden heraus."""
    await _bestand(test_db)
    cursor = await test_db.execute("INSERT INTO categories (name, color) VALUES ('Musik', '#2196F3')")
    cid = cursor.lastrowid
    await category_rules.save_rules(cid, [RuleIn(kind="tag", value="musik")])
    assert {r["video_id"] for r in await test_db.fetch_all(
        "SELECT video_id FROM video_categories WHERE category_id = ?", (cid,))} == {"techno0001", "prozent002"}
    for n in range(600):          # länger als ein Nachziehen vor der Abfrage
        await _video(test_db, f"w{n:09d}", ["anderes"])
    await test_db.execute("DELETE FROM video_tags")
    await test_db.execute("INSERT OR IGNORE INTO video_tags_dirty (video_id) SELECT id FROM videos")
    await category_rules.apply_category(cid)
    assert {r["video_id"] for r in await test_db.fetch_all(
        "SELECT video_id FROM video_categories WHERE category_id = ?", (cid,))} == {"techno0001", "prozent002"}

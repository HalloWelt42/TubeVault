"""
Suchindex-Tests.

Kontrakt (siehe app/services/search_index.py):
- Jede Änderung an einem Video landet über Trigger im Index - egal über
  welchen Schreibweg (kein händisches Nachziehen nötig).
- Die Suche findet Bibliothek UND Archiv; archived grenzt ein.
- Wortanfänge und Teilwörter in Titel/Kanal werden gefunden.
- Der Index übersteht neu vergebene rowids (INSERT OR REPLACE, VACUUM).
"""
import pytest

from app.services import search_index


async def _add(db, vid, title, *, channel="Kanal", archived=0, status="ready",
               tags="[]", description=None):
    await db.execute(
        "INSERT INTO videos (id, title, channel_name, status, is_archived, tags, description) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (vid, title, channel, status, archived, tags, description),
    )


async def _ids(query, **kwargs):
    result = await search_index.search_videos(query, **kwargs)
    return [v["id"] for v in result["videos"]]


async def test_findet_archiv_und_bibliothek(test_db):
    await _add(test_db, "a1", "Sauerteig ansetzen", archived=1)
    await _add(test_db, "b1", "Sauerteig backen", archived=0)

    assert set(await _ids("Sauerteig")) == {"a1", "b1"}
    assert await _ids("Sauerteig", archived=True) == ["a1"]
    assert await _ids("Sauerteig", archived=False) == ["b1"]


async def test_treffer_tragen_archiv_kennzeichen(test_db):
    await _add(test_db, "a1", "Weichenbau", archived=1)
    result = await search_index.search_videos("Weichenbau")
    assert result["total"] == 1
    assert result["videos"][0]["is_archived"] == 1


async def test_wortanfang_und_teilwort(test_db):
    await _add(test_db, "v1", "Sauerteig ansetzen")
    assert await _ids("Sauer") == ["v1"], "Wortanfang muss beim Tippen treffen"
    assert await _ids("teig") == ["v1"], "Teilwort im Titel muss treffen"
    assert await _ids("ansetzen Sauer") == ["v1"], "Wörter sind UND-verknüpft, Reihenfolge egal"
    assert await _ids("Sauer Hefe") == []


async def test_umlaute_und_gross_klein(test_db):
    await _add(test_db, "v1", "Löten für Anfänger")
    assert await _ids("löten") == ["v1"]
    assert await _ids("LOTEN") == ["v1"]


async def test_aenderung_ohne_haendisches_nachziehen(test_db):
    await _add(test_db, "v1", "Alter Titel")
    assert await _ids("Alter") == ["v1"]

    await test_db.execute("UPDATE videos SET title = 'Neuer Name' WHERE id = 'v1'")
    assert await _ids("Neuer") == ["v1"]
    assert await _ids("Alter") == []


async def test_tags_und_kanal_durchsuchbar(test_db):
    await _add(test_db, "v1", "Folge 1", channel="Werkbank Nord",
               tags='["oszilloskop", "messtechnik"]')
    assert await _ids("messtechnik") == ["v1"]
    assert await _ids("Werkbank") == ["v1"]
    assert await _ids("bank") == ["v1"], "Teilwort im Kanalnamen"


async def test_geloeschtes_video_verschwindet(test_db):
    await _add(test_db, "v1", "Mondfinsternis")
    assert await _ids("Mondfinsternis") == ["v1"]
    await test_db.execute("DELETE FROM videos WHERE id = 'v1'")
    assert await _ids("Mondfinsternis") == []
    assert await test_db.fetch_val("SELECT COUNT(*) FROM search_docs") == 0


async def test_nur_fertige_videos(test_db):
    await _add(test_db, "v1", "Signaltechnik", status="metadata")
    assert await _ids("Signaltechnik") == []


async def test_ueberlebt_neue_rowids(test_db):
    """INSERT OR REPLACE und VACUUM vergeben neue rowids - der Index darf
    danach nicht auf fremde Videos zeigen."""
    await _add(test_db, "v1", "Hefeteig")
    await _add(test_db, "v2", "Fräsen")
    await _add(test_db, "v3", "Sternbilder")
    assert await _ids("Hefeteig") == ["v1"]

    await test_db.execute("DELETE FROM videos WHERE id = 'v2'")
    await test_db.execute(
        "INSERT OR REPLACE INTO videos (id, title, channel_name, status) "
        "VALUES ('v1', 'Hefeteig', 'Kanal', 'ready')")
    await test_db.conn.commit()
    await test_db.conn.execute("VACUUM")

    assert await _ids("Hefeteig") == ["v1"]
    assert await _ids("Sternbilder") == ["v3"]
    assert await _ids("Fräsen") == []


async def test_sonderzeichen_brechen_nichts(test_db):
    await _add(test_db, "v1", 'C++ "Grundlagen" (Teil 1)')
    assert await _ids('c++') == ["v1"]
    assert await _ids('"Grundlagen"') == ["v1"]
    assert await _ids("100%") == []
    assert await _ids("()") == []


async def test_suche_nach_video_id(test_db):
    await _add(test_db, "dQw4w9WgXcQ", "Irgendein Titel")
    assert await _ids("dQw4w9WgXcQ") == ["dQw4w9WgXcQ"]


async def test_seiten_ohne_doppelte(test_db):
    for n in range(30):
        await _add(test_db, f"v{n:02d}", f"Brühe Folge {n}")
    seen = []
    for page in (1, 2, 3):
        seen += await _ids("Brühe", page=page, per_page=10)
    assert len(seen) == 30 and len(set(seen)) == 30


async def test_relevanz_titel_vor_beschreibung(test_db):
    await _add(test_db, "desc", "Etwas anderes", description="Hier geht es um Oszilloskop")
    await _add(test_db, "title", "Oszilloskop Grundlagen")
    assert await _ids("Oszilloskop") == ["title", "desc"]


async def test_listenfilter_nutzt_dieselben_regeln(test_db):
    from app.services.metadata_service import metadata_service
    await _add(test_db, "a1", "Sauerteig ansetzen", archived=1,
               description="mit Roggenmehl")
    await _add(test_db, "b1", "Hefezopf", archived=1)

    result = await metadata_service.get_videos(search="teig", is_archived=True)
    assert [v["id"] for v in result["videos"]] == ["a1"]
    result = await metadata_service.get_videos(search="Roggenmehl", is_archived=True)
    assert [v["id"] for v in result["videos"]] == ["a1"]


def test_build_match():
    assert search_index.build_match("foo bar") == '"foo"* AND "bar"*'
    assert search_index.build_match('  "  ') is None
    assert search_index.build_match("foo-bar") == '"foo bar"*'

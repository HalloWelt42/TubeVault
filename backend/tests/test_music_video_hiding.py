"""
Minus-Knopf: Videos aus der ganzen Musik abwählen (Wunsch 19.10.2026).

Kontrakt:
- Ein abgewähltes Video fehlt überall in der Musik: Titel, Suche, Interpreten,
  Alben, Kanäle, Lieblingssongs, Mixe, Wiedergabelisten, als Musik gespielte
  Sammlungen, Ton-Export, Zähler und Seitenleiste.
- Gelöscht wird nichts; die Videobibliothek außerhalb der Musik bleibt gleich.
- Der Bereich "Ausgeblendet" zeigt abgewählte Videos und Dateien zusammen und
  holt beide zurück, einzeln oder mehrere; die Sicherung behält die Wahl.
"""
import pytest

from app.routers import music
from app.services import counts_service, music_files, music_library, music_video_hiding, playlist_items, userdata_export

FILE_A = "f" + "a" * 15
SONG = "abba0000002"


@pytest.fixture
async def bestand(test_db):
    for vid, title, plays, last in [("abba0000001", "ABBA - Waterloo", 3, "2026-10-10"),
                                    (SONG, "ABBA - Fernando", 5, "2026-10-12"),
                                    ("abba0000003", "ABBA - Super Trouper", 0, None)]:
        await test_db.execute(
            """INSERT INTO videos (id, title, channel_id, channel_name, music_album, play_count, last_played,
                                   is_music, status, download_date, duration)
               VALUES (?, ?, 'UCabba', 'ABBA', 'Arrival', ?, ?, 1, 'ready', '2026-10-01', 200)""",
            (vid, title, plays, last))
    await test_db.execute("INSERT INTO favorites (video_id, list_name) VALUES (?, 'Standard')", (SONG,))
    await test_db.execute(
        """INSERT INTO music_files (id, path, title, artist, duration, category, added_at)
           VALUES (?, 'A/eins.flac', 'Eins', 'Datei-Band', 200, 'musik', '2026-10-02')""", (FILE_A,))
    list_id = await music_library.create_music_playlist("Autofahrt")
    await playlist_items.add(list_id, ["abba0000001", SONG, FILE_A])
    return list_id


async def _ids(source: str) -> set[str]:
    return {t.id for t in (await music_library.play_list(source)).tracks}


async def test_abgewaehltes_video_fehlt_ueberall_in_der_musik(test_db, bestand, async_client_factory):
    list_id = bestand
    library_before = await counts_service.CountsService().library_videos()
    async with await async_client_factory(music.router) as client:
        assert (await client.put(f"/api/music/videos/{SONG}/hidden", json={"hidden": True})).json() == {"hidden": True}
        assert (await client.put("/api/music/videos/gibtsnicht1/hidden", json={"hidden": True})).status_code == 404

        overview = (await client.get("/api/music/overview")).json()
        assert overview["counts"]["tracks"] == 3 and overview["counts"]["favorites"] == 0
        assert overview["counts"]["hidden"] == 1 and overview["sources"]["videos"] == 2
        assert SONG not in {t["id"] for t in overview["new"] + overview["often"]}
        assert SONG not in {t["id"] for t in (await client.get("/api/music/tracks?q=fernando")).json()["items"]}
        artists = {g["name"]: g["count"] for g in (await client.get("/api/music/artists")).json()}
        assert artists["ABBA"] == 2
        assert [g["count"] for g in (await client.get("/api/music/albums")).json()] == [2]
        assert [g["count"] for g in (await client.get("/api/music/channels")).json()] == [2]
        lists = {g["key"]: g["count"] for g in (await client.get("/api/music/playlists")).json()}
        assert lists[f"playlist:{list_id}"] == 2

    for source in ("all", "favorites", "often", "new", "recent", "forgotten", "artist:abba",
                   "album:abba|arrival", "channel:UCabba", f"playlist:{list_id}", f"sammlung:playlist:{list_id}",
                   "similar:abba0000001"):
        assert SONG not in await _ids(source), source
    assert await _ids(f"similar:{SONG}") <= {"abba0000001", "abba0000003"}
    _, exported = await music_library.export_items(f"playlist:{list_id}")
    assert [item_id for item_id, _ in exported] == ["abba0000001", FILE_A]
    assert await counts_service.CountsService().music() == 2

    # Nichts gelöscht: das Video bleibt in der Bibliothek
    assert await test_db.fetch_val("SELECT status FROM videos WHERE id = ?", (SONG,)) == "ready"
    assert await counts_service.CountsService().library_videos() == library_before
    assert await playlist_items.entries(list_id) == ["abba0000001", SONG, FILE_A]


async def test_ausgeblendet_zeigt_beide_arten_und_holt_zurueck(test_db, bestand, async_client_factory):
    await music_files.set_hidden(FILE_A, True)
    await music_video_hiding.set_hidden(SONG, True)
    await music_video_hiding.set_hidden("abba0000001", True)
    async with await async_client_factory(music.router) as client:
        area = (await client.get("/api/music/hidden")).json()
        assert {(t["id"], t["kind"]) for t in area["tracks"]} == {
            (FILE_A, "datei"), (SONG, "video"), ("abba0000001", "video")}
        assert (await client.get("/api/music/overview")).json()["counts"]["hidden"] == 3

        single = (await client.post("/api/music/hidden/restore", json={"tracks": [SONG]})).json()
        assert single == {"tracks": 1, "albums": 0}
        both = (await client.post("/api/music/hidden/restore", json={"tracks": [FILE_A, "abba0000001"]})).json()
        assert both == {"tracks": 2, "albums": 0}
        assert (await client.get("/api/music/hidden")).json()["tracks"] == []
    assert {SONG, "abba0000001", FILE_A} <= {t.id for t in await music_library.tracks()}


async def test_sicherung_behaelt_die_wahl(test_db, bestand, tmp_path, monkeypatch):
    from app.services import rebuild_service
    monkeypatch.setenv("TUBEVAULT_EXPORTS_ROOT", str(tmp_path))
    await music_video_hiding.set_hidden(SONG, True)
    rows = {r["id"]: dict(r) for r in await test_db.fetch_all(userdata_export.VIDEO_USERDATA_SQL)}
    assert rows[SONG]["music_hidden"] == 1 and rows[SONG]["music_hidden_at"]
    manifest = await userdata_export.export_userdata()
    await test_db.execute("UPDATE videos SET music_hidden = 0, music_hidden_at = NULL")
    await rebuild_service.restore_userdata(manifest["folder"])
    assert SONG in {t.id for t in await music_library.hidden_tracks()}

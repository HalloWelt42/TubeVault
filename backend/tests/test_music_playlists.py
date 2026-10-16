"""
Wiedergabelisten der Musik aus Videos und Dateien der Sammlung (Wunsch 16.10.2026).

Kontrakt:
- Eine Liste hält Videos und Dateien in einer gemeinsamen Reihenfolge
  (app/services/playlist_items); Anfügen, Umordnen (Ungenanntes dahinter),
  Entfernen; Doppeltes und Unbekanntes kommt nicht hinein.
- In der Musik angelegte Listen erscheinen sofort, auch leer; andere Listen
  nur, wenn Musik darin ist.
- Abspielen, ZIP-Ausgabe und Kopieren nehmen Dateien mit.
"""
import pytest

from app.routers import music, playlists
from app.services import music_library, playlist_items

FILE_A = "f" + "a" * 15
FILE_B = "f" + "b" * 15


@pytest.fixture
async def bestand(test_db):
    await test_db.execute(
        """INSERT INTO music_files (id, path, title, artist, duration, category) VALUES
           (?, 'A/eins.flac', 'Eins', 'Datei-Band', 200, 'musik'),
           (?, 'B/zwei.flac', 'Zwei', 'Datei-Band', 210, 'musik')""", (FILE_A, FILE_B))
    await test_db.execute(
        """INSERT INTO videos (id, title, channel_id, channel_name, is_music, status, download_date, duration) VALUES
           ('musikvideo1', 'Video-Band - Drei', 'UCv', 'Video-Band', 1, 'ready', '2026-10-01', 180),
           ('mathevideo1', 'Brüche kürzen', 'UCm', 'Mathe', 0, 'ready', '2026-10-01', 600)""")


async def test_liste_anlegen_fuellen_ordnen(test_db, bestand, async_client_factory):
    async with await async_client_factory(music.router) as client:
        created = (await client.post("/api/music/playlists", json={"name": "Autofahrt"})).json()
        list_id = int(created["key"].split(":")[1])
        assert [g["name"] for g in (await client.get("/api/music/playlists")).json()] == ["Autofahrt"]   # leer, aber da

        r = await client.post(f"/api/music/playlists/{list_id}/items", json={"ids": [FILE_A, "musikvideo1", FILE_A, "gibtsnicht1"]})
        assert r.json() == {"added": 2, "count": 2}
        await client.post(f"/api/music/playlists/{list_id}/items", json={"ids": [FILE_B]})
        await client.put(f"/api/music/playlists/{list_id}/items", json={"ids": [FILE_B]})     # vorn einordnen
        assert await playlist_items.entries(list_id) == [FILE_B, FILE_A, "musikvideo1"]

        played = await music_library.play_list(f"playlist:{list_id}")
        assert [t.id for t in played.tracks] == [FILE_B, FILE_A, "musikvideo1"]
        assert {t.kind for t in played.tracks} == {"datei", "video"}

        await client.put(f"/api/music/playlists/{list_id}/items", json={"ids": ["musikvideo1", FILE_B]})
        assert await playlist_items.entries(list_id) == ["musikvideo1", FILE_B, FILE_A]
        assert (await client.delete(f"/api/music/playlists/{list_id}/items/{FILE_B}")).json() == {"count": 2}
        assert (await client.post("/api/music/playlists/999/items", json={"ids": [FILE_A]})).status_code == 404

    group = next(g for g in await music_library.music_playlists() if g.name == "Autofahrt")
    assert (group.count, group.kinds) == (2, ["datei", "video"])


async def test_nur_listen_mit_musik(test_db, bestand):
    for name, video in (("Mathe", "mathevideo1"), ("Gemischt", "musikvideo1")):
        cursor = await test_db.execute("INSERT INTO playlists (name, source) VALUES (?, 'manual')", (name,))
        await playlist_items.add(cursor.lastrowid, [video])
    assert [g.name for g in await music_library.music_playlists()] == ["Gemischt"]


async def test_zip_und_kopie_nehmen_dateien_mit(test_db, bestand, async_client_factory):
    list_id = await music_library.create_music_playlist("Mix")
    await playlist_items.add(list_id, ["musikvideo1", FILE_A])
    title, items = await music_library.export_items(f"playlist:{list_id}")
    assert (title, items) == ("Mix", [("musikvideo1", "Video-Band - Drei"), (FILE_A, "Datei-Band - Eins")])

    async with await async_client_factory(playlists.router) as client:
        copied = (await client.post(f"/api/playlists/{list_id}/copy")).json()
        assert copied["video_count"] == 2
        assert await playlist_items.entries(copied["id"]) == ["musikvideo1", FILE_A]
        # auch über die allgemeinen Wege zählen Dateien mit
        added = (await client.post(f"/api/playlists/{list_id}/videos", json={"video_id": FILE_B})).json()
        assert added["video_count"] == 3
        assert (await client.post(f"/api/playlists/{list_id}/videos", json={"video_id": FILE_B})).status_code == 409
        assert (await client.delete(f"/api/playlists/{list_id}/videos/{FILE_A}")).json()["video_count"] == 2

"""
Musiksammlung: Titel, Interpreten, Alben, Kanäle und dynamische
Wiedergabelisten (Wunsch 15.10.2026: alles als Liste und zufällig).
"""
from app.routers import music
from app.services import music_library


async def _song(db, vid, title, channel="AbbaVEVO", artist=None, album=None, plays=0, is_music=1, added="2026-10-01"):
    await db.execute(
        """INSERT INTO videos (id, title, channel_id, channel_name, music_artist, music_album, play_count,
                               is_music, status, download_date, duration)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ready', ?, 200)""",
        (vid, title, "UC" + channel, channel, artist, album, plays, is_music, added))


async def _bestand(db):
    await _song(db, "abba0000001", "ABBA - Waterloo (Official Lyric Video)", plays=5, added="2026-10-03")
    await _song(db, "abba0000002", "ABBA - Fernando (Official Music Video)", album="Arrival", plays=1)
    await _song(db, "abba0000003", "ABBA - Super Trouper (Official Lyric Video)", album="Arrival")
    await _song(db, "gall0000001", "France Gall - Cézanne Peint (Audio officiel)", channel="France Gall et Michel Berger")
    await _song(db, "keinemusik1", "Wie oft - Tipps", channel="Tutorials", is_music=0)


def test_interpret_und_titel_ohne_zusaetze():
    row = {"id": "x", "title": "ABBA - Waterloo (Official Lyric Video)", "music_artist": None,
           "music_title": None, "channel_name": "AbbaVEVO"}
    assert music_library.names_of(row) == ("ABBA", "Waterloo")
    row = {"id": "x", "title": "Romulus Visualizer", "music_artist": None, "music_title": None,
           "channel_name": "Romulus Music"}
    assert music_library.names_of(row) == ("Romulus", "Romulus Visualizer")


async def test_gruppen_und_uebersicht(test_db, async_client_factory):
    await _bestand(test_db)
    async with await async_client_factory(music.router) as client:
        data = (await client.get("/api/music/overview")).json()
        assert data["counts"]["tracks"] == 4 and data["counts"]["artists"] == 2
        assert data["artists"][0]["name"] == "ABBA" and data["artists"][0]["count"] == 3
        assert data["new"][0]["id"] == "abba0000001"
        albums = (await client.get("/api/music/albums")).json()
        assert [(a["name"], a["subtitle"], a["count"]) for a in albums] == [("Arrival", "ABBA", 2)]
        found = (await client.get("/api/music/tracks?q=gall")).json()
        assert [t["id"] for t in found["items"]] == ["gall0000001"]


async def test_jede_gruppe_ist_eine_wiedergabeliste(test_db):
    await _bestand(test_db)
    artist = await music_library.play_list("artist:abba")
    assert artist.title == "ABBA" and [t.title for t in artist.tracks] == ["Fernando", "Super Trouper", "Waterloo"]
    channel = await music_library.play_list("channel:UCFrance Gall et Michel Berger")
    assert [t.id for t in channel.tracks] == ["gall0000001"]
    shuffled = await music_library.play_list("all", shuffle=True, start="gall0000001")
    assert shuffled.tracks[0].id == "gall0000001" and len(shuffled.tracks) == 4
    assert [t.id for t in (await music_library.play_list("often")).tracks] == ["abba0000001", "abba0000002"]
    # ohne Bedeutungssuche: ähnlich heißt derselbe Interpret oder Kanal
    similar = await music_library.play_list("similar:abba0000002")
    assert similar.tracks[0].id == "abba0000002" and {t.id for t in similar.tracks} == {
        "abba0000001", "abba0000002", "abba0000003"}


async def test_stelle_eines_titels_in_der_liste(test_db, async_client_factory):
    """Zur Stelle: dieselbe Liste wie /tracks (Sortierung, Suche, Lieblingssongs);
    fehlt der Titel dort, ist die Stelle leer."""
    await _bestand(test_db)
    await test_db.execute("INSERT INTO favorites (video_id, list_name) VALUES ('abba0000003', 'Standard')")
    async with await async_client_factory(music.router) as client:
        async def position(**params):
            return (await client.get("/api/music/tracks/position", params=params)).json()["position"]
        listed = [t["id"] for t in (await client.get("/api/music/tracks?sort=title")).json()["items"]]
        assert await position(id="abba0000001", sort="title") == listed.index("abba0000001")
        assert await position(id="gall0000001", sort="title", q="abba") is None
        assert await position(id="abba0000003", sort="title", q="abba") == 1           # Fernando, Super Trouper, Waterloo
        assert await position(id="abba0000003", favorites=True) == 0
        assert await position(id="abba0000001", favorites=True) is None
        assert await position(id="keinemusik1") is None

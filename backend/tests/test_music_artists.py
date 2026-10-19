"""
Interpreten trennen (entschieden 19.10.2026, "Bei jedem Genannten", "Automatisch und Liste").

Kontrakt:
- Getrennt wird an ", " und " feat. ", " ft. ", " featuring " (Schreibweise
  egal), nie an "&".
- Bandschutz: nur trennen, wenn ein Teil für sich als Interpret vorkommt
  (Dateien: Interpret oder Album-Interpret; Musikvideos); was eine Trennung
  ergibt, zählt danach mit. Ein ganz bleibender Name bleibt auch in längeren
  Angaben ganz.
- Listen: nie trennen (gilt vor immer trennen, schützt auch in längeren
  Angaben) und immer trennen.
- Ein Titel zählt bei jedem Genannten: Gruppe, Wiedergabeliste, Zahl der
  Interpreten; angezeigt wird die Angabe, wie sie ist.
"""
import json
from collections import Counter

from app.routers import music, settings as settings_router
from app.services import music_artists, music_files, music_library


def _naming(*credits, extra=(), never=(), always=()):
    return music_artists.build(Counter(credits), extra, never, always)


# ─── Regeln ───

def test_trennt_an_komma_und_feat_nie_an_und():
    naming = _naming("A", "B", "C", "D", "E", "Kool & The Gang")
    assert naming.names("A, B") == ["A", "B"]
    assert naming.names("A feat. B") == ["A", "B"]
    assert naming.names("A FEAT. B, C") == ["A", "B", "C"]
    assert naming.names("A Ft. B") == ["A", "B"]
    assert naming.names("A featuring B") == ["A", "B"]
    assert naming.names("Kool & The Gang") == ["Kool & The Gang"]
    assert naming.names("A & B") == ["A & B"]
    assert naming.names("A,B") == ["A,B"]                       # ohne Leerzeichen keine Trennung
    assert naming.names("A, a") == ["A"]                        # ein Name zählt einmal


def test_bandschutz_ohne_allein_stehenden_teil():
    naming = _naming("Earth, Wind & Fire", "Crosby, Stills, Nash & Young", "Young")
    assert naming.names("Earth, Wind & Fire") == ["Earth, Wind & Fire"]
    # "Young" kommt allein vor, aber "Nash & Young" ist ein anderer Teil
    assert naming.names("Crosby, Stills, Nash & Young") == ["Crosby, Stills, Nash & Young"]
    assert "earth, wind & fire" in naming.bands


def test_ein_allein_stehender_teil_genuegt():
    naming = _naming("50 Cent", "50 Cent, Nate Dogg")
    assert naming.names("50 Cent, Nate Dogg") == ["50 Cent", "Nate Dogg"]
    assert "50 cent, nate dogg" in naming.split


def test_album_interpret_zaehlt_als_allein_stehend():
    naming = _naming("50 Cent, Nate Dogg", extra=["50 Cent"])
    assert naming.names("50 Cent, Nate Dogg") == ["50 Cent", "Nate Dogg"]


def test_getrennte_namen_zaehlen_danach_mit():
    """50 Cent steht allein, also trennt "50 Cent, Akon"; danach ist Akon bekannt
    und "Akon, Kardinal Offishall" trennt auch."""
    naming = _naming("50 Cent", "50 Cent, Akon", "Akon, Kardinal Offishall", "Earth, Wind & Fire")
    assert naming.names("Akon, Kardinal Offishall") == ["Akon", "Kardinal Offishall"]
    assert naming.names("Earth, Wind & Fire") == ["Earth, Wind & Fire"]


def test_band_bleibt_in_laengerer_angabe_ganz():
    naming = _naming("Earth, Wind & Fire", "The Emotions", "Earth, Wind & Fire, The Emotions")
    assert naming.names("Earth, Wind & Fire, The Emotions") == ["Earth, Wind & Fire", "The Emotions"]
    assert naming.names("The Emotions feat. Earth, Wind & Fire") == ["The Emotions", "Earth, Wind & Fire"]


def test_listen_nie_und_immer_trennen():
    naming = _naming("50 Cent", "50 Cent, Nate Dogg", "Simon, Garfunkel", "Earth, Wind & Fire", "Earth",
                     never=["50 cent, nate dogg", "Earth, Wind & Fire"], always=["Simon, Garfunkel", "50 Cent, Nate Dogg"])
    assert naming.names("50 Cent, Nate Dogg") == ["50 Cent, Nate Dogg"]       # nie trennen gilt vor immer trennen
    assert naming.names("Simon, Garfunkel") == ["Simon", "Garfunkel"]
    # "Earth" kommt allein vor, die Liste schützt die Band trotzdem, auch in längeren Angaben
    assert naming.names("Earth, Wind & Fire") == ["Earth, Wind & Fire"]
    assert naming.names("Earth, Wind & Fire, 50 Cent") == ["Earth, Wind & Fire", "50 Cent"]


def test_namen_stehen_so_im_original():
    naming = _naming("Daft Punk", "Daft Punk  feat.  Pharrell Williams")
    assert naming.names(" Daft Punk  feat.  Pharrell Williams ") == ["Daft Punk", "Pharrell Williams"]


def test_listen_aus_den_einstellungen():
    assert music_artists.listed('["Earth, Wind & Fire", 3, " "]') == ["Earth, Wind & Fire"]
    assert music_artists.listed("kaputt") == [] and music_artists.listed("") == []


# ─── In der Musikbibliothek ───

async def _file(db, path, artist, album_artist=None, title=None, album=None):
    await db.execute(
        """INSERT INTO music_files (id, path, title, artist, album_artist, album, duration, added_at)
           VALUES (?, ?, ?, ?, ?, ?, 200, '2026-10-01')""",
        (music_files.file_id(path), path, title or path, artist, album_artist, album))
    return music_files.file_id(path)


async def _video(db, vid, artist, title):
    await db.execute(
        """INSERT INTO videos (id, title, music_artist, music_title, channel_id, channel_name, is_music, status,
                               download_date, duration)
           VALUES (?, ?, ?, ?, 'UCx', 'Kanal', 1, 'ready', '2026-10-01', 200)""",
        (vid, f"{artist} - {title}", artist, title))


async def _bestand(db):
    await _file(db, "Curtis/01.flac", "50 Cent", "50 Cent", "In da Club", "Curtis")
    collab = await _file(db, "Curtis/02.flac", "50 Cent, Nate Dogg", "50 Cent", "21 Questions", "Curtis")
    await _file(db, "Soul/01.flac", "Earth, Wind & Fire", "Earth, Wind & Fire", "September")
    await _file(db, "Soul/02.flac", "Kool & The Gang", None, "Celebration")
    await _video(db, "guetta00001", "David Guetta, Sia", "Titanium")
    await _video(db, "sia00000001", "Sia", "Chandelier")
    return collab


async def _artists() -> dict[str, music_library.Group]:
    return {g.key: g for g in music_library.artists(await music_library.tracks("alle"))}


async def test_titel_zaehlt_bei_jedem_genannten(test_db, async_client_factory):
    collab = await _bestand(test_db)
    artists = await _artists()
    assert {k: g.count for k, g in artists.items()} == {
        "artist:50 cent": 2, "artist:nate dogg": 1, "artist:earth, wind & fire": 1, "artist:kool & the gang": 1,
        "artist:david guetta": 1, "artist:sia": 2}
    assert artists["artist:nate dogg"].name == "Nate Dogg"
    async with await async_client_factory(music.router) as client:
        data = (await client.get("/api/music/overview")).json()
        assert data["counts"]["artists"] == 6
        nate = (await client.get("/api/music/play", params={"source": "artist:nate dogg"})).json()
        assert nate["title"] == "Nate Dogg" and [t["id"] for t in nate["tracks"]] == [collab]
        track = nate["tracks"][0]
        assert track["artist"] == "50 Cent, Nate Dogg"                   # angezeigt wird die Angabe
        assert track["artists"] == [{"name": "50 Cent", "source": "artist:50 cent"},
                                    {"name": "Nate Dogg", "source": "artist:nate dogg"}]
        cent = (await client.get("/api/music/play", params={"source": "artist:50 cent"})).json()
        assert sorted(t["title"] for t in cent["tracks"]) == ["21 Questions", "In da Club"]
        sia = (await client.get("/api/music/play", params={"source": "artist:sia"})).json()
        assert sorted(t["title"] for t in sia["tracks"]) == ["Chandelier", "Titanium"]
        found = (await client.get("/api/music/tracks", params={"q": "nate dogg"})).json()
        assert [t["id"] for t in found["items"]] == [collab]


async def test_album_eines_interpreten_bleibt_seins(test_db):
    await _bestand(test_db)
    curtis = next(g for g in music_library.albums(await music_library.tracks("sammlung")) if g.name == "Curtis")
    assert (curtis.count, curtis.subtitle) == (2, "50 Cent")


async def test_listen_wirken_sofort_und_bieten_vorschlaege(test_db, async_client_factory):
    await _bestand(test_db)
    async with await async_client_factory(settings_router.router, music.router) as client:
        whole = (await client.get(f"/api/settings/options/{music_artists.WHOLE}")).json()
        assert {o["value"]: o["hint"] for o in whole["options"]} == {
            "50 Cent, Nate Dogg": "wird getrennt, 1 Titel", "David Guetta, Sia": "wird getrennt, 1 Titel",
            "Earth, Wind & Fire": "bleibt ganz, 1 Titel"}
        split = (await client.get(f"/api/settings/options/{music_artists.SPLIT}")).json()
        assert [o["value"] for o in split["options"]] == ["Earth, Wind & Fire"]

        saved = await client.put(f"/api/settings/{music_artists.WHOLE}", json={"value": json.dumps(["50 Cent, Nate Dogg"])})
        assert saved.status_code == 200
        artists = await _artists()
        assert "artist:nate dogg" not in artists and artists["artist:50 cent, nate dogg"].count == 1
        await client.put(f"/api/settings/{music_artists.SPLIT}", json={"value": json.dumps(["Earth, Wind & Fire"])})
        artists = await _artists()
        assert {"artist:earth", "artist:wind & fire"} <= set(artists)
        bad = await client.put(f"/api/settings/{music_artists.SPLIT}", json={"value": "Earth, Wind & Fire"})
        assert bad.status_code == 422

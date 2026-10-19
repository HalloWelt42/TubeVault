"""
Alben der eigenen Sammlung (entschieden 19.10.2026, "Cover oder Ordner und Name").

Kontrakt:
- Dateien im selben Ordner mit demselben Albumnamen (Schreibweise egal) sind
  ein Album; Dateien mit demselben Cover auch, wenn es das Cover ihrer Gruppe
  ist (mindestens die Hälfte ihrer Titel trägt es); fortgesetzt.
- Ein Ordner wie "Space Night" mit einem Albumnamen und vielen Covern ist ein
  Album; ein Download-Ordner mit vielen Albumnamen zerfällt in seine Alben;
  ein Sampler mit den Covern der Originalalben hängt nicht an diesen.
- Ohne Albumnamen kein Album, auch mit Cover; so eine Datei verbindet nichts.
- Der Schlüssel ist der kleinste Schlüssel der Verbindungen: gleich bei jedem
  Aufruf und in jeder Reihenfolge. Wechselt er, führt ein früherer (auch ein
  Cover-Schlüssel aus der Zeit der reinen Cover-Regel) zum heutigen; Ausschluss
  und Abspielen gelten weiter.
"""
import random

from app.routers import music
from app.services import music_albums, music_files, music_library

SPACE_NIGHT = "BR - Space Night (Vol.01-12)"


def _cover(n: int) -> str:
    return f"{n:040x}"


def _space_night(count=30, covers=25):
    """Ein Ordner, ein Albumname (in zwei Schreibweisen), viele Cover."""
    return [(f"sn{i:03}", f"{SPACE_NIGHT}/{i:03}. Titel {i}.flac", "Space Night" if i % 3 else "space  night ",
             _cover(1000 + i % covers)) for i in range(count)]


def _download_folder():
    """Ein Ordner mit vier Albumnamen, jeder Titel mit eigenem Cover."""
    return [(f"dl{i:03}", f"Downloads/{i:03}.flac", f"Album {i % 4}", _cover(2000 + i)) for i in range(12)]


def _albums_of(index, entries):
    groups = {}
    for file_id, *_ in entries:
        key = index.of(file_id)
        if key:
            groups.setdefault(key, set()).add(file_id)
    return groups


def test_space_night_mit_vielen_covern_ist_ein_album():
    entries = _space_night()
    groups = _albums_of(music_albums.build(entries), entries)
    assert len(groups) == 1
    key, members = next(iter(groups.items()))
    assert len(members) == 30
    assert key.startswith(music_albums.FOLDER)                    # kein Cover der Gruppe: Ordner und Name


def test_download_ordner_zerfaellt_nach_albumnamen():
    """Der Ordner allein verbindet nie: vier Albumnamen, vier Alben."""
    entries = _download_folder()
    groups = _albums_of(music_albums.build(entries), entries)
    assert sorted(len(members) for members in groups.values()) == [3, 3, 3, 3]
    for members in groups.values():
        assert len({int(file_id[2:]) % 4 for file_id in members}) == 1


def test_gleiches_cover_ueber_ordner_und_namen():
    entries = [("a", "Bravo/01.flac", "Bravo Hits 1", _cover(7)),
               ("b", "Bravo Teil 2/01.flac", "Bravo Hits Vol. 1", _cover(7)),
               ("c", "Anderes/01.flac", "Bravo Hits 1", _cover(8))]
    groups = _albums_of(music_albums.build(entries), entries)
    assert sorted(map(sorted, groups.values())) == [["a", "b"], ["c"]]


def test_sampler_mit_originalcovern_haengt_nicht_an_den_originalalben():
    """Ein Titel des Samplers trägt das Cover von Violator: ein Viertel des
    Samplers, also nicht dessen Cover - Sampler und Violator bleiben zwei Alben."""
    entries = [(f"s{i}", f"Classic Rock Classics/{i:03}.flac", "Classic Rock Classics", _cover(10 + i)) for i in range(4)]
    entries += [(f"v{i}", f"Depeche Mode - Violator/{i:02}.flac", "Violator", _cover(11)) for i in range(3)]
    index = music_albums.build(entries)
    groups = _albums_of(index, entries)
    assert sorted(map(sorted, groups.values())) == [["s0", "s1", "s2", "s3"], ["v0", "v1", "v2"]]
    assert index.resolve(f"{music_albums.COVER}{_cover(11)}") == index.of("v0")


def test_fortgesetzt_ueber_cover_und_ordner():
    """a hängt über das Cover an b, b über Ordner und Namen an c: ein Album."""
    entries = [("a", "Eins/01.flac", "Eins", _cover(1)),
               ("b", "Zwei/01.flac", "Zwei", _cover(1)),
               ("c", "Zwei/02.flac", "zwei", _cover(2)),
               ("d", "Zwei/03.flac", "Drei", _cover(3))]
    index = music_albums.build(entries)
    groups = _albums_of(index, entries)
    assert sorted(map(sorted, groups.values())) == [["a", "b", "c"], ["d"]]


def test_ohne_albumnamen_kein_album():
    entries = [("a", "Ordner/01.flac", None, _cover(5)),
               ("b", "Ordner/02.flac", "", _cover(5)),
               ("c", "Ordner/03.flac", "Album", _cover(6)),
               ("d", "Ordner/04.flac", "Album", _cover(7))]
    index = music_albums.build(entries)
    assert index.of("a") is None and index.of("b") is None
    assert index.of("c") == index.of("d")


def test_schluessel_unabhaengig_von_reihenfolge():
    entries = _space_night() + _download_folder()
    expected = {file_id: music_albums.build(entries).of(file_id) for file_id, *_ in entries}
    shuffled = list(entries)
    random.Random(7).shuffle(shuffled)
    index = music_albums.build(shuffled)
    assert {file_id: index.of(file_id) for file_id, *_ in entries} == expected


def test_frueherer_schluessel_fuehrt_zum_heutigen():
    """Neue Titel bringen ein anderes Cover der Gruppe mit: der Schlüssel
    wechselt, der frühere führt weiter zum Album."""
    album = [("a1", "Album/01.flac", "Album", _cover(20)), ("a2", "Album/02.flac", "Album", _cover(20)),
             ("a3", "Album/03.flac", "Album", _cover(30))]
    before = music_albums.build(album)
    old_key = before.of("a1")
    assert old_key == f"{music_albums.COVER}{_cover(20)}"
    grown = album + [(f"n{i}", f"Album/1{i}.flac", "Album", _cover(5)) for i in range(3)]
    after = music_albums.build(grown)
    assert after.of("a1") == after.of("n0") == f"{music_albums.COVER}{_cover(5)}"
    assert after.resolve(old_key) == after.of("a1")
    assert after.resolve("album:abba|gold") == "album:abba|gold"     # Alben der Videos bleiben


# ─── In der Musikbibliothek ───

async def _file(db, path, album, cover_hash, artist="Diverse", title=None, added="2026-10-01"):
    await db.execute(
        """INSERT INTO music_files (id, path, title, artist, album, cover, cover_hash, duration, added_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 200, ?)""",
        (music_files.file_id(path), path, title or path, artist, album, "embedded" if cover_hash else None,
         cover_hash, added))
    return music_files.file_id(path)


async def _space_night_rows(db):
    for i in range(12):
        await _file(db, f"{SPACE_NIGHT}/{i:02}.flac", "Space Night" if i else "SPACE NIGHT", _cover(100 + i),
                    artist=f"Künstler {i % 5}")
    for i in range(6):
        await _file(db, f"Downloads/{i:02}.flac", f"Album {i % 3}", _cover(200 + i), artist="Band")


async def test_bibliothek_bildet_alben_nach_der_regel(test_db):
    await _space_night_rows(test_db)
    albums = music_library.albums(await music_library.tracks("sammlung"))
    by_name = {g.name: g for g in albums}
    assert sorted(by_name) == ["Album 0", "Album 1", "Album 2", "Space Night"]
    space = by_name["Space Night"]
    # Name: die häufigste Schreibweise; mehrere Interpreten; Kachel aus verschiedenen Bildern
    assert space.key.startswith("album:ordner:")
    assert (space.count, space.subtitle) == (12, music_library.VARIOUS_ARTISTS)
    assert len(space.covers) == music_library.COLLAGE
    assert [by_name[f"Album {n}"].count for n in range(3)] == [2, 2, 2]


async def test_frueherer_schluessel_abspielen_und_ausschliessen(test_db, async_client_factory):
    """Ein Schlüssel aus der Zeit der reinen Cover-Regel (ein Cover eines Titels)
    führt zum heutigen Album: Ausschließen merkt den heutigen, Abspielen findet es."""
    await _space_night_rows(test_db)
    old_key = f"album:cover:{_cover(100)}"
    async with await async_client_factory(music.router) as client:
        entry = (await client.post("/api/music/exclusions", json={"source": old_key})).json()
        assert entry["source"].startswith("album:ordner:") and entry["count"] == 12
        # Was später dazukommt, bleibt mit draußen
        await _file(test_db, f"{SPACE_NIGHT}/99.flac", "Space Night", _cover(1))
        names = {g.name for g in music_library.albums(await music_library.tracks("sammlung"))}
        assert "Space Night" not in names and "Album 0" in names
        await client.post("/api/music/hidden/restore", json={"albums": [entry["source"]]})
        played = (await client.get("/api/music/play", params={"source": old_key})).json()
    assert played["title"] == "Space Night" and len(played["tracks"]) == 13
    assert {t["album_source"] for t in played["tracks"]} == {entry["source"]}


async def test_ausgeblendeter_titel_trennt_kein_album(test_db):
    """Gerechnet wird über alle Dateien: blendet man das Bindeglied aus, bleibt das Album eins."""
    await _file(test_db, "Eins/01.flac", "Eins", _cover(1))
    bridge = await _file(test_db, "Zwei/01.flac", "Zwei", _cover(1))      # Cover wie Eins, Ordner wie Zwei/02
    await _file(test_db, "Zwei/02.flac", "Zwei", _cover(2))
    await music_files.set_hidden(bridge, True)
    albums = music_library.albums(await music_library.tracks("sammlung"))
    assert [(g.key, g.count) for g in albums] == [(f"album:cover:{_cover(1)}", 2)]

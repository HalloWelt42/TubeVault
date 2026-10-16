"""
Eigene Musiksammlung (FLAC usw.) als zweite Quelle der Musik (Wunsch 15.10.2026).

Kontrakt:
- Einlesen: Tags, Technik, eingebettetes Cover oder Ordnerbild, .lrc-Liedtext;
  ohne Tags hilft der Dateiname; erneut gelesen wird nur Geändertes,
  Verschwundenes fällt heraus.
- Musikbibliothek: Quelle alle / sammlung / videos; ein Song als Datei und
  als Video gilt bei "alle" einmal, als Datei.
- Abspielen mit Range, Cover, Liedtext, Wiedergaben, Lieblingssong, Ton-Export.
- Ausgeblendet (Wünsche 16.10.2026): ausgeblendete Dateien und ausgeschlossene
  Alben fallen überall heraus, ein leeres Album verschwindet, ihr Video-Doppel
  rückt nicht nach; zurückholen einzeln oder mehrere.
"""
import os
import shutil
import subprocess
from io import BytesIO

import pytest

from app.routers import music
from app.services import audio_export, music_files, music_library

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg fehlt")


def _flac(path, seconds=1):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                    "-ac", "2", "-ar", "44100", str(path)], check=True)


def _jpeg(color=(200, 30, 30)) -> bytes:
    from PIL import Image
    buffer = BytesIO()
    Image.new("RGB", (800, 800), color).save(buffer, "JPEG")
    return buffer.getvalue()


@pytest.fixture
def sammlung(tmp_path, monkeypatch):
    from mutagen.flac import FLAC, Picture
    root = tmp_path / "musik"
    monkeypatch.setattr(music_files, "MUSIC_FILES_DIR", root)
    monkeypatch.setattr(music_files, "MUSIC_COVERS_DIR", tmp_path / "cover")

    getaggt = root / "Depeche Mode" / "Violator" / "02. Enjoy the Silence.flac"
    _flac(getaggt)
    audio = FLAC(getaggt)
    audio.update({"artist": "Depeche Mode", "title": "Enjoy the Silence", "album": "Violator",
                  "tracknumber": "2/9", "date": "1990-02-05", "genre": "Synthpop"})
    picture = Picture()
    picture.type, picture.mime, picture.data = 3, "image/jpeg", _jpeg()
    audio.add_picture(picture)
    audio.save()

    ohne_tags = root / "01. Robert Miles - Children.flac"
    _flac(ohne_tags)
    (root / "01. Robert Miles - Children.lrc").write_text("[00:00.50]Erste Zeile\n[00:01.00]Zweite Zeile\n", encoding="utf-8")

    hoerspiel = root / "Jules Verne - Die geheimnisvolle Insel (Hörspiel)" / "01. Teil 1.flac"
    _flac(hoerspiel)

    lied_mit_hoerspiel_im_namen = root / "Welle Erdball - Der Kalte Krieg" / "15. Welle Erdball - Sendeschluss (Hörspiel Version).flac"
    _flac(lied_mit_hoerspiel_im_namen)

    mit_ordnerbild = root / "Sammler" / "Secret Garden - Nocturne.flac"
    _flac(mit_ordnerbild)
    (root / "Sammler" / "folder.jpg").write_bytes(_jpeg((30, 30, 200)))
    return root


async def test_einlesen_tags_dateiname_cover_liedtext(test_db, sammlung):
    result = await music_files.scan()
    assert (result.files, result.read, result.removed) == (5, 5, 0)
    # Hörspiel ist keine Musik; ein Lied mit "Hörspiel" nur im Dateinamen schon
    assert [f.title for f in await music_files.all_files(music_files.AUDIOBOOK)] == ["Teil 1"]
    assert len(await music_files.all_files()) == 4
    by_title = {f.title: f for f in await music_files.all_files()}

    dm = by_title["Enjoy the Silence"]
    assert (dm.artist, dm.album, dm.track_no, dm.year, dm.genre, dm.codec) == ("Depeche Mode", "Violator", 2, 1990, "Synthpop", "FLAC")
    assert dm.sample_rate == 44100 and dm.channels == 2 and dm.bit_depth == 16 and dm.has_cover
    assert music_files.is_file_id(dm.id)

    rm = by_title["Children"]
    assert rm.artist == "Robert Miles" and rm.has_lyrics and not rm.has_cover
    lyrics = await music_files.lyrics(rm.id)
    assert lyrics["synced"].startswith("[00:00.50]Erste Zeile") and lyrics["plain"] == "Erste Zeile\nZweite Zeile"

    sg = by_title["Nocturne"]
    assert sg.artist == "Secret Garden" and sg.has_cover
    for f in (dm, sg):
        cover = await music_files.cover_path(f.id)
        from PIL import Image
        assert cover and max(Image.open(cover).size) == music_files.COVER_SIZE


async def test_nur_geaendertes_wird_neu_gelesen(test_db, sammlung):
    await music_files.scan()
    again = await music_files.scan()
    assert (again.read, again.removed) == (0, 0)
    (sammlung / "Sammler" / "Secret Garden - Nocturne.flac").unlink()
    later = sammlung / "01. Robert Miles - Children.flac"
    os.utime(later, (later.stat().st_atime, later.stat().st_mtime + 10))
    third = await music_files.scan()
    assert (third.files, third.read, third.removed) == (4, 1, 1)


async def test_quelle_und_doppelte_songs(test_db, sammlung, set_setting):
    await music_files.scan()
    await test_db.execute(
        """INSERT INTO videos (id, title, channel_id, channel_name, is_music, status, download_date, duration)
           VALUES ('dmvideo0001', 'Depeche Mode - Enjoy the Silence (Official Video)', 'UCdm', 'Depeche Mode', 1, 'ready', '2026-10-01', 260),
                  ('dmvideo0002', 'Depeche Mode - Personal Jesus (Official Video)', 'UCdm', 'Depeche Mode', 1, 'ready', '2026-10-01', 230)""")
    alle = await music_library.tracks()
    assert sorted((t.title, t.kind) for t in alle if t.artist == "Depeche Mode") == [
        ("Enjoy the Silence", "datei"), ("Personal Jesus", "video")]
    await set_setting("music.source", "sammlung")
    assert {t.kind for t in await music_library.tracks()} == {"datei"}
    await set_setting("music.source", "videos")
    assert {t.id for t in await music_library.tracks()} == {"dmvideo0001", "dmvideo0002"}
    overview = await music.overview()
    assert (overview.source, overview.sources.videos, overview.sources.sammlung) == ("videos", 2, 4)


async def test_gruppen_nennen_herkunft_dateien_ihr_format(test_db, sammlung):
    """Für die Anzeige am Handy: "Sammlung, Videos" je Interpret und "FLAC" je Datei."""
    await music_files.scan()
    await test_db.execute(
        """INSERT INTO videos (id, title, channel_id, channel_name, is_music, status, download_date, duration)
           VALUES ('dmvideo0002', 'Depeche Mode - Personal Jesus (Official Video)', 'UCdm', 'Depeche Mode', 1, 'ready', '2026-10-01', 230)""")
    items = await music_library.tracks()
    by_name = {g.name: g for g in music_library.artists(items)}
    assert by_name["Depeche Mode"].kinds == ["datei", "video"]
    assert by_name["Robert Miles"].kinds == ["datei"]
    formats = {t.title: (t.kind, t.codec) for t in items}
    assert formats["Enjoy the Silence"] == ("datei", "FLAC")
    assert formats["Personal Jesus"] == ("video", None)


async def test_abspielen_wiedergaben_lieblingssong_export(test_db, sammlung, async_client_factory, tmp_path):
    await music_files.scan()
    rm = next(f for f in await music_files.all_files() if f.title == "Children")
    async with await async_client_factory(music.router) as client:
        part = await client.get(f"/api/music/files/{rm.id}/stream", headers={"Range": "bytes=0-99"})
        assert part.status_code == 206 and len(part.content) == 100 and part.headers["content-type"] == "audio/flac"
        assert (await client.post(f"/api/music/files/{rm.id}/played")).status_code == 200
        assert (await client.put(f"/api/music/files/{rm.id}/favorite", json={"favorite": True})).json() == {"favorite": True}
        assert (await client.get("/api/music/cover/abcdefghijk", follow_redirects=False)).status_code in (302, 307)
        assert (await client.get("/api/music/files/f000000000000000")).status_code == 404
    again = await music_files.get(rm.id)
    assert again.play_count == 1 and again.favorite
    info = await audio_export.info(rm.id)
    assert info.codec == "flac" and info.sample_rate == 44100
    out = tmp_path / "ausgabe"
    out.mkdir()
    copied = await audio_export.export(rm.id, audio_export.ORIGINAL, out)
    assert copied.name == "Robert Miles - Children.flac" and copied.stat().st_size == (sammlung / "01. Robert Miles - Children.flac").stat().st_size


async def test_hoerbuch_reihenfolge_und_weiterhoeren(test_db, sammlung):
    """Hörbuch: eigene Liste, feste Reihenfolge (Teil 2 vor Teil 10), nie in
    der Musik, Weiterhören beim gemerkten Teil an der gemerkten Stelle."""
    from app.services import audiobooks
    ordner = sammlung / "Jules Verne - Die geheimnisvolle Insel (Hörspiel)"
    for name in ("10. Teil 10.flac", "02. Teil 2.flac"):
        _flac(ordner / name)
    await music_files.scan()

    [buch] = await audiobooks.books()
    assert (buch.title, buch.parts, buch.current_part) == ("Jules Verne - Die geheimnisvolle Insel (Hörspiel)", 3, None)
    liste = await music_library.play_list(f"hoerbuch:{buch.key}", shuffle=True)
    assert [t.title for t in liste.tracks] == ["Teil 1", "Teil 2", "Teil 10"] and liste.start_index == 0
    assert all(t.title not in ("Teil 1", "Teil 2", "Teil 10") for t in await music_library.tracks())

    zweiter = liste.tracks[1]
    await audiobooks.save_progress(buch.key, zweiter.id, 0.4)
    weiter = await music_library.play_list(f"hoerbuch:{buch.key}")
    assert (weiter.start_index, weiter.start_at) == (1, 0.4)
    [buch] = await audiobooks.books()
    assert buch.current_part == 2 and not buch.finished

    await audiobooks.reset(buch.key)
    assert (await music_library.play_list(f"hoerbuch:{buch.key}")).start_index == 0


async def test_hoerbuecher_als_videos(test_db):
    """Videos mit Hörbuch/Hörspiel im Titel: erkannt, nie Musik; nummerierte
    Teile ergeben ein Buch in Folgenreihenfolge, ein Einzelvideo ist ein Buch."""
    from app.services import audiobook_flag, audiobooks
    for vid, title, upload in [
            ("hspteil00002", "Die drei Fragezeichen Hörspiel - Teil 2", "2026-01-02"),
            ("hspteil00001", "Die drei Fragezeichen Hörspiel - Teil 1", "2026-01-03"),
            ("hspteil00003", "Die drei Fragezeichen Hörspiel - Teil 3", "2026-01-01"),
            ("hbeinzel001", "Der Hobbit - Hörbuch komplett", "2026-01-04"),
            ("musikvideo1", "ABBA - Waterloo", "2026-01-05")]:
        await test_db.execute(
            """INSERT INTO videos (id, title, channel_id, channel_name, is_music, status, upload_date, download_date, duration)
               VALUES (?, ?, 'UCh', 'Hörkanal', 1, 'ready', ?, ?, 600)""", (vid, title, upload, upload))
        await audiobook_flag.apply_auto(vid, title, "[]")
    assert {t.id for t in await music_library.video_tracks()} == {"musikvideo1"}

    by_title = {b.title: b for b in await audiobooks.books()}
    reihe = next(b for t, b in by_title.items() if "Fragezeichen" in t)
    assert (reihe.kind, reihe.parts) == ("video", 3)
    assert [t.id for t in (await music_library.play_list(f"hoerbuch:{reihe.key}")).tracks] == [
        "hspteil00001", "hspteil00002", "hspteil00003"]
    assert by_title["Der Hobbit - Hörbuch komplett"].parts == 1

    # Nutzerwahl gilt, die Automatik ändert sie nie
    await audiobook_flag.set_by_user(["hbeinzel001"], False)
    await audiobook_flag.apply_auto("hbeinzel001", "Der Hobbit - Hörbuch komplett", "[]")
    assert "Der Hobbit - Hörbuch komplett" not in {b.title for b in await audiobooks.books()}


async def test_ausblenden_statt_loeschen(test_db, sammlung, async_client_factory):
    """Die Sammlung liegt nur lesend vor: "Gefällt nicht" blendet aus. Ausgeblendetes
    fehlt in allen Listen und Zählern, bleibt über erneutes Einlesen ausgeblendet
    und lässt sich wieder einblenden; die Datei bleibt unberührt."""
    await music_files.scan()
    children = next(f for f in await music_files.all_files() if f.title == "Children")
    datei = sammlung / "01. Robert Miles - Children.flac"
    async with await async_client_factory(music.router) as client:
        assert (await client.put(f"/api/music/files/{children.id}/hidden", json={"hidden": True})).json() == {"hidden": True}
        assert [t["title"] for t in (await client.get("/api/music/hidden")).json()["tracks"]] == ["Children"]
        assert (await client.get("/api/music/files/status")).json()["hidden"] == 1
    assert datei.exists()
    assert "Children" not in {t.title for t in await music_library.tracks()}
    assert (await music.overview()).sources.sammlung == 3

    os.utime(datei, (datei.stat().st_atime, datei.stat().st_mtime + 10))   # erneut einlesen
    await music_files.scan()
    assert (await music_files.get(children.id)).hidden

    await music_files.set_hidden(children.id, False)
    assert "Children" in {t.title for t in await music_library.tracks()}
    assert await music_files.hidden_files() == []


async def test_ausgeblendet_rueckt_kein_video_nach(test_db, sammlung):
    await music_files.scan()
    await test_db.execute(
        """INSERT INTO videos (id, title, channel_id, channel_name, is_music, status, download_date)
           VALUES ('dmvideo0001', 'Depeche Mode - Enjoy the Silence (Official Video)', 'UCdm', 'Depeche Mode', 1, 'ready', '2026-10-01')""")
    enjoy = next(f for f in await music_files.all_files() if f.title == "Enjoy the Silence")
    await music_files.set_hidden(enjoy.id, True)
    items = await music_library.tracks()
    assert "Enjoy the Silence" not in {t.title for t in items}
    assert "Violator" not in {g.name for g in music_library.albums(items)}     # nichts mehr drin: kein Album


async def test_album_ausschliessen_und_zurueckholen(test_db, sammlung, async_client_factory):
    await music_files.scan()
    await test_db.execute(
        """INSERT INTO videos (id, title, music_artist, music_title, music_album, channel_id, channel_name, is_music, status,
                               download_date)
           VALUES ('dmvideo0003', 'Depeche Mode - Halo', 'Depeche Mode', 'Halo', 'Violator', 'UCdm', 'Depeche Mode', 1,
                   'ready', '2026-10-01')""")
    album = next(g for g in music_library.albums(await music_library.tracks()) if g.name == "Violator")
    assert album.count == 2 and album.kinds == ["datei", "video"]
    async with await async_client_factory(music.router) as client:
        assert (await client.post("/api/music/exclusions", json={"source": "artist:depeche mode"})).status_code == 400
        entry = (await client.post("/api/music/exclusions", json={"source": album.key})).json()
        assert (entry["name"], entry["subtitle"], entry["count"]) == ("Violator", "Depeche Mode", 2)

        items = await music_library.tracks()
        assert not {"Enjoy the Silence", "Halo"} & {t.title for t in items}
        assert "Violator" not in {g.name for g in music_library.albums(items)}
        assert (await music.overview()).counts.hidden == 1
        assert [a["name"] for a in (await client.get("/api/music/hidden")).json()["albums"]] == ["Violator"]

        restored = (await client.post("/api/music/hidden/restore", json={"albums": [album.key]})).json()
        assert restored == {"tracks": 0, "albums": 1}
    assert {"Enjoy the Silence", "Halo"} <= {t.title for t in await music_library.tracks()}


async def test_mehrere_auf_einmal_zurueckholen(test_db, sammlung, async_client_factory):
    await music_files.scan()
    files = await music_files.all_files()
    for f in files[:2]:
        await music_files.set_hidden(f.id, True)
    async with await async_client_factory(music.router) as client:
        hidden = (await client.get("/api/music/hidden")).json()["tracks"]
        assert len(hidden) == 2
        restored = (await client.post("/api/music/hidden/restore", json={"tracks": [t["id"] for t in hidden]})).json()
    assert restored == {"tracks": 2, "albums": 0}
    assert await music_files.hidden_count() == 0


async def test_neuaufbau_dann_einlesen_behaelt_nutzerdaten(test_db, sammlung):
    """Nach einem Neuaufbau steht ein Eintrag aus der Sicherung; das Einlesen
    ergänzt Tags und Technik und lässt Lieblingssong und Ausgeblendet stehen."""
    await music_files.scan()
    enjoy = next(f for f in await music_files.all_files() if f.title == "Enjoy the Silence")
    await music_files.set_favorite(enjoy.id, True)
    await music_files.set_hidden(enjoy.id, True)
    saved = [dict(r) for r in await test_db.fetch_all(music_files.USERDATA_SQL)]
    await test_db.execute("DELETE FROM music_files")

    assert await music_files.restore_userdata(saved) == 1
    await music_files.scan()
    again = await music_files.get(enjoy.id)
    assert (again.favorite, again.hidden, again.codec, again.album) == (True, True, "FLAC", "Violator")

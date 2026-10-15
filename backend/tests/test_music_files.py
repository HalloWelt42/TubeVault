"""
Eigene Musiksammlung (FLAC usw.) als zweite Quelle der Musik (Wunsch 15.10.2026).

Kontrakt:
- Einlesen: Tags, Technik, eingebettetes Cover oder Ordnerbild, .lrc-Liedtext;
  ohne Tags hilft der Dateiname; erneut gelesen wird nur Geändertes,
  Verschwundenes fällt heraus.
- Musikbibliothek: Quelle alle / sammlung / videos; ein Song als Datei und
  als Video gilt bei "alle" einmal, als Datei.
- Abspielen mit Range, Cover, Liedtext, Wiedergaben, Lieblingssong, Ton-Export.
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

    mit_ordnerbild = root / "Sammler" / "Secret Garden - Nocturne.flac"
    _flac(mit_ordnerbild)
    (root / "Sammler" / "folder.jpg").write_bytes(_jpeg((30, 30, 200)))
    return root


async def test_einlesen_tags_dateiname_cover_liedtext(test_db, sammlung):
    result = await music_files.scan()
    assert (result.files, result.read, result.removed) == (4, 4, 0)
    # Hörspiel ist keine Musik
    assert [f.title for f in await music_files.all_files(music_files.AUDIOBOOK)] == ["Teil 1"]
    assert len(await music_files.all_files()) == 3
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
    assert (third.files, third.read, third.removed) == (3, 1, 1)


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
    assert (overview.source, overview.sources.videos, overview.sources.sammlung) == ("videos", 2, 3)


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

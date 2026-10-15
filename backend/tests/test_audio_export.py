"""
Tonspuren (Wünsche 15.10.2026): Bitrate im Spieler, Einzeltitel und ganze
Wiedergabelisten nur als Ton herunterladen - "original" ohne Neukodierung.
"""
import subprocess
import zipfile

import pytest

from app.routers import music
from app.services import audio_export


@pytest.fixture
def song(tmp_path):
    path = tmp_path / "song.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                    "-c:a", "aac", "-b:a", "128k", str(path)], check=True)
    return path


async def _video(db, vid, path, title="ABBA - Waterloo"):
    await db.execute("INSERT INTO videos (id, title, file_path, file_size, status, is_music) VALUES (?, ?, ?, ?, 'ready', 1)",
                     (vid, title, str(path), path.stat().st_size))


async def test_tonspur_wird_gemessen_und_gemerkt(test_db, song):
    await _video(test_db, "song0000001", song)
    info = await audio_export.info("song0000001")
    assert info.codec == "aac" and info.sample_rate == 44100 and 100_000 < info.bitrate < 160_000
    assert await test_db.fetch_val("SELECT codec FROM audio_info WHERE video_id = 'song0000001'") == "aac"


async def test_original_ohne_neukodierung(test_db, song, tmp_path):
    await _video(test_db, "song0000001", song)
    out = await audio_export.export("song0000001", "original", tmp_path, "ABBA - Waterloo")
    assert out.name == "ABBA - Waterloo.m4a"
    assert (await audio_export._probe(out)).codec == "aac"


async def test_wiedergabeliste_als_zip(test_db, song, tmp_path, async_client_factory):
    await _video(test_db, "song0000001", song, "ABBA - Waterloo")
    await _video(test_db, "song0000002", song, "Tutorial ohne Musik")
    await test_db.execute("UPDATE videos SET is_music = 0 WHERE id = 'song0000002'")
    await test_db.execute("INSERT INTO playlists (id, name) VALUES (7, 'Sommer')")
    await test_db.execute("INSERT INTO playlist_videos (playlist_id, video_id, position) VALUES (7, 'song0000001', 1), (7, 'song0000002', 2)")
    async with await async_client_factory(music.router) as client:
        r = await client.get("/api/music/export.zip?source=playlist:7")
    assert r.status_code == 200
    (tmp_path / "x.zip").write_bytes(r.content)
    names = zipfile.ZipFile(tmp_path / "x.zip").namelist()
    assert names == ["001 ABBA - Waterloo.m4a", "002 Tutorial ohne Musik.m4a"]

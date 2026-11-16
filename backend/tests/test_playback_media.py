"""
Abspielbare Fassung je Gerät (HELF-242).

Kontrakt:
- Beim Laden entscheidet die Einstellung download.codec innerhalb einer
  Auflösung über den Codec (kompatibel: H.264 zuerst), nie über die Auflösung.
- describe() liefert Container und Codec-Kennungen, mit denen der Player
  canPlayType fragt, und sagt, ob umgepackt oder umgewandelt werden müsste.
- Ein Auftrag legt kompatibel.mp4 (H.264, AAC) neben das Original; das
  Original bleibt. "umpacken" fasst nur H.264 an.
"""
import shutil
import subprocess

import pytest

from app.services import playback_media as pm
from app.services.download_service import CODEC_ORDERS, codec_family, download_service
from app.services.job_service import job_service

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg fehlt")


class _Stream:
    def __init__(self, resolution, codec):
        self.resolution, self.codecs = resolution, [codec]


class _Query:
    def __init__(self, streams):
        self._streams = streams

    def filter(self, **_):
        return self

    def __iter__(self):
        return iter(self._streams)


class _Yt:
    def __init__(self, streams):
        self.streams = _Query(streams)


SOURCE = [_Stream("1080p", "av01.0.08M.08"), _Stream("1080p", "vp9"), _Stream("1080p", "avc1.640028"),
          _Stream("720p", "avc1.4d401f"), _Stream("2160p", "vp09.00.50.08")]


def test_codec_familien():
    assert [codec_family(s) for s in SOURCE] == ["av1", "vp9", "h264", "h264", "vp9"]


@pytest.mark.parametrize("quality, order, expected", [
    ("1080p", "kompatibel", ("1080p", "h264")),
    ("1080p", "klein", ("1080p", "av1")),
    ("best", "kompatibel", ("2160p", "vp9")),      # Auflösung geht vor: 2160p gibt es nur als VP9
    ("900p", "kompatibel", ("2160p", "vp9")),      # unbekannte Qualität wie best
    ("1440p", "kompatibel", ("1080p", "h264")),    # nächst-kleinere, dort H.264
    ("480p", "kompatibel", ("720p", "h264")),      # alles darüber: die kleinste
])
def test_codec_innerhalb_der_aufloesung(quality, order, expected):
    picked = download_service._pick_adaptive_video(_Yt(SOURCE), quality, CODEC_ORDERS[order])
    assert (picked.resolution, codec_family(picked)) == expected


def test_kennungen_fuer_canplaytype():
    assert pm._avc_tag({"profile": "High", "level": 40}) == "avc1.640028"
    assert pm._avc_tag({"profile": "Constrained Baseline", "level": 30}) == "avc1.42e01e"
    assert pm._av1_tag({"height": 1080, "pix_fmt": "yuv420p"}) == "av01.0.08M.08"
    assert pm._vp9_tag({"height": 720, "pix_fmt": "yuv420p10le"}) == "vp09.02.31.10"
    info = pm.MediaInfo(container="mkv", video_codec="h264", video_tag="avc1.640028",
                        audio_codec="opus", audio_tag="opus", height=1080)
    assert (info.mime, info.codecs, info.label) == ("video/x-matroska", "avc1.640028, opus", "H.264, 1080p, mkv")


def _make(path, video_codec, audio_codec):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=25:duration=2",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                    "-c:v", video_codec, "-c:a", audio_codec, "-shortest", str(path)], check=True)


async def _video(test_db, tmp_path, video_id, name, video_codec, audio_codec):
    folder = tmp_path / video_id
    folder.mkdir()
    path = folder / name
    _make(path, video_codec, audio_codec)
    await test_db.execute(
        "INSERT INTO videos (id, title, status, file_path, storage_type, file_size) VALUES (?, ?, 'ready', ?, 'local', ?)",
        (video_id, f"Probe {video_id}", str(path), path.stat().st_size))
    return path


async def _work(job):
    await job_service.start(job["id"], exclusive=False)
    result = await pm._run(job["id"])
    await job_service.complete(job["id"], result)
    return result


@needs_ffmpeg
async def test_mkv_mit_h264_wird_umgepackt(test_db, tmp_path):
    original = await _video(test_db, tmp_path, "mkvh264abcd", "video.mkv", "libx264", "libopus")
    media = await pm.describe("mkvh264abcd")
    assert media.original.mime == "video/x-matroska" and media.original.codecs.startswith("avc1.")
    assert media.compatible is None and media.compatible_way == "umpacken"

    job = await pm.request(["mkvh264abcd"], "bei_bedarf", "Probe")
    assert (await pm.describe("mkvh264abcd")).job.id == job["id"]
    assert await _work(job) == "1 umgepackt"

    media = await pm.describe("mkvh264abcd")
    assert media.compatible.url == "/api/player/mkvh264abcd/compatible"
    converted = await pm._ffprobe(pm.compatible_path(original))
    assert (converted.container, converted.video_codec, converted.audio_codec) == ("mp4", "h264", "aac")
    assert original.exists()


@needs_ffmpeg
async def test_umpacken_laesst_vp9_liegen_bei_bedarf_wandelt_um(test_db, tmp_path):
    original = await _video(test_db, tmp_path, "webmvp9abcd", "video.webm", "libvpx-vp9", "libopus")
    assert (await pm.describe("webmvp9abcd")).compatible_way == "umwandeln"
    assert [c.video_id for c in await pm.repack_candidates()] == ["webmvp9abcd"]

    assert await _work(await pm.request(["webmvp9abcd"], "umpacken", "Alle")) == "1 braucht Umwandlung"
    assert not pm.compatible_path(original).exists()

    assert await _work(await pm.request(["webmvp9abcd"], "bei_bedarf", "Eins")) == "1 umgewandelt"
    converted = await pm._ffprobe(pm.compatible_path(original))
    assert converted.video_codec == "h264" and converted.height == 180
    assert await _work(await pm.request(["webmvp9abcd"], "bei_bedarf", "Nochmal")) == "1 vorhanden"


@needs_ffmpeg
async def test_messung_wird_gemerkt_bis_die_datei_sich_aendert(test_db, tmp_path):
    original = await _video(test_db, tmp_path, "mp4cacheabc", "video.mp4", "libx264", "aac")
    await pm.describe("mp4cacheabc")
    await test_db.execute("UPDATE media_info SET video_codec = 'gemerkt' WHERE video_id = 'mp4cacheabc'")
    assert (await pm.probe("mp4cacheabc", original)).video_codec == "gemerkt"
    _make(original, "libvpx-vp9", "aac")
    assert (await pm.probe("mp4cacheabc", original)).video_codec == "vp9"

"""
Audio-Fix Tests – nachträgliche Tonspur-Korrektur.

Schwerpunkt: der DESTRUKTIVE commit-Pfad (ersetzt das Video) muss
bombensicher sein. Echte ffmpeg-Test-Medien (kein Netzwerk):
  - "falsches" Video (testsrc + 1kHz-Ton)
  - "Original"-Audio (440Hz, opus) als Staging
→ build → fixed.mp4 → commit → ersetzt, validiert, DB-Größe aktualisiert.

Pure/Datei-Logik wird ohne ffmpeg getestet.
"""
import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest

from app.services import audio_fix


def _have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


pytestmark = pytest.mark.skipif(not _have_ffmpeg(), reason="ffmpeg/ffprobe fehlt")


@pytest.fixture
def audio_root(tmp_path, monkeypatch):
    """AUDIO_DIR auf tmp umbiegen, damit Staging isoliert ist."""
    root = tmp_path / "audio"
    root.mkdir()
    monkeypatch.setattr(audio_fix, "AUDIO_DIR", root)
    return root


def _make_video(path: Path, *, freq: int = 1000):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=10",
         "-f", "lavfi", "-i", f"sine=frequency={freq}:duration=1",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)],
        check=True, capture_output=True,
    )


def _make_audio(path: Path, *, freq: int = 440):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration=1",
         "-c:a", "libopus", str(path)],
        check=True, capture_output=True,
    )


# ─── Pure / Datei-Logik ───────────────────────────────────────────

def test_staging_dir_layout(audio_root):
    d = audio_fix._staging_dir("vid123")
    assert d == audio_root / "vid123" / "audiofix"


def test_status_empty(audio_root):
    st = audio_fix.status("nope")
    assert st["has_audio"] is False
    assert st["has_fixed"] is False
    assert st["meta"] is None


def test_status_reflects_staging(audio_root):
    d = audio_fix._staging_dir("v1")
    d.mkdir(parents=True)
    (d / "original_audio.webm").write_bytes(b"x")
    st = audio_fix.status("v1")
    assert st["has_audio"] is True
    assert st["has_fixed"] is False


async def test_discard_removes_staging(audio_root):
    d = audio_fix._staging_dir("v2")
    d.mkdir(parents=True)
    (d / "original_audio.webm").write_bytes(b"x")
    await audio_fix.discard("v2")
    assert not d.exists()


def test_stream_filters():
    probe = {"streams": [
        {"codec_type": "video", "codec_name": "h264"},
        {"codec_type": "audio", "codec_name": "aac"},
        {"codec_type": "audio", "codec_name": "opus"},
    ]}
    assert len(audio_fix._video_streams(probe)) == 1
    assert len(audio_fix._audio_streams(probe)) == 2


async def test_build_requires_audio(test_db, audio_root):
    await test_db.execute(
        "INSERT INTO videos (id, title, file_path, status) VALUES (?, ?, ?, 'ready')",
        ("nofx", "T", "/tmp/doesnotexist.mp4"),
    )
    with pytest.raises(ValueError, match="Original-Audio"):
        await audio_fix.build_fixed_video("nofx")


async def test_commit_requires_fixed(test_db, audio_root):
    await test_db.execute(
        "INSERT INTO videos (id, title, file_path, status) VALUES (?, ?, ?, 'ready')",
        ("nocommit", "T", "/tmp/x.mp4"),
    )
    with pytest.raises(ValueError, match="fertiges Video"):
        await audio_fix.commit("nocommit")


# ─── Echter End-to-End-Pfad (ffmpeg) ──────────────────────────────

async def test_build_and_commit_replaces_video(test_db, audio_root, tmp_path):
    vid = "e2evid12345"
    video_path = tmp_path / "videos" / vid / "video.mp4"
    _make_video(video_path, freq=1000)          # "falsches" Video
    orig_size = video_path.stat().st_size

    await test_db.execute(
        "INSERT INTO videos (id, title, file_path, file_size, status) VALUES (?, ?, ?, ?, 'ready')",
        (vid, "Test", str(video_path), orig_size),
    )

    # Staging-Audio platzieren (simuliert fetch_original_audio)
    staging = audio_fix._staging_dir(vid)
    staging.mkdir(parents=True)
    _make_audio(staging / "original_audio.webm", freq=440)

    # build
    binfo = await audio_fix.build_fixed_video(vid)
    fixed = staging / "fixed.mp4"
    assert fixed.exists()
    assert binfo["fixed_size"] > 0
    # fixed muss v+a haben
    probe = await audio_fix._ffprobe(fixed)
    assert audio_fix._video_streams(probe)
    assert audio_fix._audio_streams(probe)

    # commit
    r = await audio_fix.commit(vid)
    assert r["new_size"] > 0
    # Original ersetzt
    assert video_path.exists()
    # Staging weg
    assert not staging.exists()
    # kein zurückgebliebenes Backup
    assert not video_path.with_suffix(".mp4.audiofix-bak").exists()
    # DB-Größe aktualisiert
    row = await test_db.fetch_one("SELECT file_size FROM videos WHERE id = ?", (vid,))
    assert row["file_size"] == video_path.stat().st_size
    # neue Datei valide (v+a)
    post = await audio_fix._ffprobe(video_path)
    assert audio_fix._video_streams(post)
    assert audio_fix._audio_streams(post)


async def test_commit_keeps_original_on_invalid_fixed(test_db, audio_root, tmp_path):
    """Wenn fixed.mp4 kaputt ist (kein Audio), darf das Original NICHT
    ersetzt werden."""
    vid = "safevid12345"
    video_path = tmp_path / "videos" / vid / "video.mp4"
    _make_video(video_path, freq=1000)
    orig_bytes = video_path.read_bytes()

    await test_db.execute(
        "INSERT INTO videos (id, title, file_path, file_size, status) VALUES (?, ?, ?, ?, 'ready')",
        (vid, "T", str(video_path), len(orig_bytes)),
    )
    staging = audio_fix._staging_dir(vid)
    staging.mkdir(parents=True)
    # "fixed.mp4" ohne Audiospur (nur Video) → commit muss ablehnen
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=10",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(staging / "fixed.mp4")],
        check=True, capture_output=True,
    )
    with pytest.raises(RuntimeError):
        await audio_fix.commit(vid)
    # Original unverändert
    assert video_path.read_bytes() == orig_bytes

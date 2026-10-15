"""Werbestellen: Abgleich mit dem Dienst, Transkripte und Downloads ohne Werbung."""
import shutil
import subprocess

import pytest

from app.services import ad_free_export, ad_segments, transcripts
from app.services.search import engine
from app.services.search.filters import SearchFilters


async def _said(text):
    """Videos, in deren Gesagtem der Text vorkommt."""
    return [item.id for item in (await engine.section("gesagt", text, SearchFilters())).items]
from app.services.subtitle_segments import Segment

VIDEO = "werbung0001"   # 11 Zeichen wie eine Video-ID der Quelle


def test_abschnitte_zusammenfassen_und_rest():
    assert ad_segments.merge([(50, 60), (10, 20), (15, 30), (30, 35)]) == [(10, 35), (50, 60)]
    assert ad_segments.keep_ranges([(0, 5), (40, 50)], 100) == [(5, 40), (50, 100)]
    assert ad_segments.keep_ranges([(90, 120)], 100) == [(0, 90)]
    sentences = [Segment(start=0, end=4, text="a"), Segment(start=10, end=14, text="b"),
                 Segment(start=19, end=23, text="c")]
    # Maßgeblich ist die Mitte eines Satzes (b: 12, c: 21)
    assert [s.text for s in ad_segments.outside(sentences, [(11, 20)])] == ["a", "c"]


@pytest.fixture
async def video(test_db, monkeypatch, tmp_path):
    monkeypatch.setattr(transcripts, "SUBTITLES_DIR", tmp_path)
    await test_db.execute(
        "INSERT INTO videos (id, title, status, upload_date) VALUES (?, 'Test', 'ready', datetime('now'))",
        (VIDEO,))
    return test_db


def answer(*segments):
    async def fetch(video_id):
        return [{"UUID": uuid, "segment": [start, end], "category": category, "votes": 1}
                for uuid, start, end, category in segments]
    return fetch


async def test_abgleich_ersetzt_den_stand_des_dienstes(video, monkeypatch):
    """Der Dienst wird mit der Zeit vollständiger und zieht auch Stellen
    zurück; eigene Marken bleiben immer."""
    await video.execute(
        "INSERT INTO ad_markers (video_id, start_time, end_time, source) VALUES (?, 100, 110, 'manual')", (VIDEO,))
    monkeypatch.setattr(ad_segments, "_fetch", answer(("u1", 10, 20, "sponsor")))
    assert (await ad_segments.refresh(VIDEO)).changed
    monkeypatch.setattr(ad_segments, "_fetch", answer(("u2", 30, 40, "selfpromo"), ("u3", 0, 5, "intro")))
    result = await ad_segments.refresh(VIDEO)
    assert (result.found, result.changed) == (2, True)
    assert await ad_segments.skip_ranges(VIDEO) == [(0, 5), (30, 40), (100, 110)]
    assert not (await ad_segments.refresh(VIDEO)).changed      # unverändert: nichts neu schreiben


async def test_nachfragen_nur_wenn_es_zeit_ist(video, monkeypatch):
    calls = []

    async def fetch(video_id):
        calls.append(video_id)
        return []
    monkeypatch.setattr(ad_segments, "_fetch", fetch)
    await ad_segments.refresh_if_due(VIDEO)
    await ad_segments.refresh_if_due(VIDEO)
    assert calls == [VIDEO]                                     # gerade erst gefragt
    await video.execute("UPDATE ad_marker_checks SET checked_at = datetime('now', '-7 hours')")
    await ad_segments.refresh_if_due(VIDEO)
    assert len(calls) == 2                                      # junges Video: nach 6 Stunden wieder
    await video.execute("UPDATE videos SET upload_date = '2015-03-17 00:00:00'")
    await video.execute("UPDATE ad_marker_checks SET checked_at = datetime('now', '-7 days')")
    await ad_segments.refresh_if_due(VIDEO)
    assert len(calls) == 2                                      # altes Video: erst nach 30 Tagen
    await ad_segments.refresh_if_due("local_abc")               # eigene Videos fragen nie
    assert len(calls) == 2


async def test_transkript_ohne_werbung_und_nachtraeglich_korrigiert(video, monkeypatch, tmp_path):
    folder = tmp_path / VIDEO
    folder.mkdir()
    (folder / "de.vtt").write_text(
        "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nHeute bauen wir eine Lötstation.\n\n"
        "00:01:00.000 --> 00:01:04.000\nDieses Video wird präsentiert von Brausepulver.\n\n"
        "00:02:00.000 --> 00:02:04.000\nZuerst kommt der Trafo.\n", encoding="utf-8")
    await transcripts.store(VIDEO, "de", "manual",
                            transcripts.subtitle_segments.segments_from_file(folder / "de.vtt"))
    assert await _said("Brausepulver")

    # Der Dienst kennt die Stelle erst später: das Transkript wird nachgezogen
    monkeypatch.setattr(ad_segments, "_fetch", answer(("u1", 55, 70, "sponsor")))
    await ad_segments.refresh(VIDEO)
    assert await _said("Brausepulver") == []
    assert (await _said("Trafo"))[0] == VIDEO
    assert "Brausepulver" in (folder / "de.vtt").read_text(encoding="utf-8")   # Datei bleibt vollständig

    # Zieht der Dienst die Stelle zurück, ist der Satz wieder auffindbar
    monkeypatch.setattr(ad_segments, "_fetch", answer())
    await ad_segments.refresh(VIDEO)
    assert await _said("Brausepulver")


async def test_eigene_marken_aendern_das_transkript_dienstmarken_sind_fest(video, async_client_factory, tmp_path):
    from app.routers import ad_markers
    folder = tmp_path / VIDEO
    folder.mkdir()
    (folder / "de.vtt").write_text(
        "WEBVTT\n\n00:00:10.000 --> 00:00:14.000\nKauft meine Tassen im Laden.\n", encoding="utf-8")
    await transcripts.store(VIDEO, "de", "manual",
                            transcripts.subtitle_segments.segments_from_file(folder / "de.vtt"))
    client = await async_client_factory(ad_markers.router)
    created = await client.post(f"/api/ad-markers/{VIDEO}", json={"start_time": 5, "end_time": 20})
    assert created.status_code == 200
    assert await _said("Tassen") == []
    await client.delete(f"/api/ad-markers/{created.json()['id']}")
    assert await _said("Tassen")

    await video.execute(
        "INSERT INTO ad_markers (video_id, start_time, end_time, source, category) VALUES (?, 1, 2, 'sponsorblock', 'sponsor')",
        (VIDEO,))
    service_id = await video.fetch_val("SELECT id FROM ad_markers WHERE source = 'sponsorblock'")
    assert (await client.delete(f"/api/ad-markers/{service_id}")).status_code == 400


# ─── Downloads ohne Werbung (echtes ffmpeg) ───────────────────────────

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg fehlt")


def make_video(path):
    """20 s Testvideo mit einem Schlüsselbild je Sekunde."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=25:duration=20",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=20", "-c:v", "libx264", "-g", "25",
                    "-c:a", "aac", "-shortest", str(path)], check=True)


@needs_ffmpeg
async def test_video_download_ohne_werbung(tmp_path):
    src = tmp_path / "quelle.mp4"
    make_video(src)
    keep = ad_segments.keep_ranges([(4.5, 10.0)], await ad_free_export.duration(src))
    out = await ad_free_export.video(src, keep, tmp_path)
    # 0 - 4,5 s und ab dem Schlüsselbild bei 10 s: gut 14,5 s, keine Werbung
    assert 14.0 <= await ad_free_export.duration(out) <= 15.2
    assert (await ad_free_export.duration(src)) == pytest.approx(20, abs=0.2)   # Original unverändert


@needs_ffmpeg
async def test_ton_download_ohne_werbung_sekundengenau(tmp_path):
    src = tmp_path / "quelle.mp4"
    make_video(src)
    keep = ad_segments.keep_ranges([(4.5, 10.0)], 20)
    out = await ad_free_export.audio(src, keep, "mp3", tmp_path)
    assert await ad_free_export.duration(out) == pytest.approx(14.5, abs=0.2)


def test_stuecke_beginnen_am_naechsten_schluesselbild():
    frames = [0, 2, 4, 6, 8]
    assert ad_free_export.snap_to_keyframes([(0, 3), (5, 9)], frames) == [(0, 3), (6, 9)]
    assert ad_free_export.snap_to_keyframes([(8.5, 9)], frames) == []          # kein Schlüsselbild mehr

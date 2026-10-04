"""
Nachvertoner: Ablauf gegen nachgestellte Dienste.

Beide Gegenstellen (TubeVault, Vertonungsdienst) sind hier Attrappen; ffmpeg
arbeitet echt. Geprüft wird die Vermittlung: richtige Reihenfolge, richtige
Angaben, sichtbare Fehler, Aufräumen.

    backend/.venv/bin/python -m pytest nachvertoner -q
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nachvertoner as nv   # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg fehlt")


def _clip(path: Path) -> bytes:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "testsrc=duration=2:size=320x180:rate=10",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True)
    return path.read_bytes()


class Stage:
    """Merkt sich, was die beiden Attrappen gesehen haben."""

    def __init__(self, clip: bytes, job_states: list[dict], source_language="en"):
        self.clip = clip
        self.job_states = job_states
        self.source_language = source_language
        self.pi_calls: list[tuple[str, str]] = []
        self.dub_calls: list[tuple[str, str]] = []
        self.created_payload = None
        self.progress: list[dict] = []
        self.result_upload = None
        self.failed = None
        self.claimable = True
        self.progress_status = 200

    def pi(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.pi_calls.append((request.method, path))
        if path == "/api/dubbing/claim":
            if not self.claimable:
                return httpx.Response(200, json={"request": None})
            self.claimable = False
            return httpx.Response(200, json={
                "request": {"id": 7, "video_id": "abc", "title": "Ein Titel", "voice": "Zeit Stimme",
                            "source_language": self.source_language, "target_language": "de"},
                "media_url": "/api/player/abc", "result_url": "/api/dubbing/requests/7/result"})
        if path == "/api/player/abc":
            return httpx.Response(200, content=self.clip)
        if path.endswith("/progress"):
            self.progress.append(json.loads(request.content))
            return httpx.Response(self.progress_status, json={"ok": True})
        if path.endswith("/result"):
            self.result_upload = request.content
            return httpx.Response(200, json={"ok": True})
        if path.endswith("/fail"):
            self.failed = json.loads(request.content)
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404)

    def dub(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.dub_calls.append((request.method, path))
        if path == "/api/system/health":
            return httpx.Response(200, json={"worker_online": True, "llm_online": True})
        if path == "/api/jobs" and request.method == "GET":
            return httpx.Response(200, json={"active": []})
        if path == "/api/voices":
            return httpx.Response(200, json=[{"id": "v-zeit", "name": "Zeit Stimme"}, {"id": "v-x", "name": "Andere"}])
        if path == "/api/files/upload":
            return httpx.Response(200, json={"id": "f-quelle"})
        if path == "/api/jobs" and request.method == "POST":
            self.created_payload = json.loads(request.content)
            return httpx.Response(200, json={"id": "j-1"})
        if path == "/api/jobs/j-1":
            state = self.job_states.pop(0) if len(self.job_states) > 1 else self.job_states[0]
            return httpx.Response(200, json=state)
        if path == "/api/files/f-ergebnis/download":
            return httpx.Response(200, content=self.clip)
        if request.method == "DELETE" or path.endswith("/cancel"):
            return httpx.Response(200, json={})
        return httpx.Response(404)


@pytest.fixture
def make(tmp_path):
    clip = _clip(tmp_path / "clip.mp4")

    def _make(job_states, **kwargs):
        stage = Stage(clip, job_states, **kwargs)
        settings = nv.Settings(
            tubevault_url="http://pi", dub_url="http://dub", worker_name="testmac",
            work_dir=tmp_path / "arbeit",
            poll_seconds=0, progress_seconds=0)
        worker = nv.Nachvertoner(settings)
        worker.pi = httpx.Client(base_url="http://pi", transport=httpx.MockTransport(stage.pi))
        worker.dub = httpx.Client(base_url="http://dub", transport=httpx.MockTransport(stage.dub))
        return worker, stage
    return _make


DONE = {"status": "done", "result": {"video_id": "f-ergebnis", "coverage_failed": 0}}


def test_vollstaendiger_ablauf(make, tmp_path):
    worker, stage = make([{"status": "running", "progress": 0.5, "phase": "translate"}, DONE])

    assert worker.step() is True

    payload = stage.created_payload["payload"]
    assert stage.created_payload["type"] == "video_dub"
    assert payload == {"file_id": "f-quelle", "source_language": "english", "target_language": "german",
                       "mode": "fixed", "voice_id": "v-zeit", "num_speakers": 1}
    assert {"progress": 0.515, "note": "Übersetzen"} in [
        {"progress": round(p["progress"], 3), "note": p["note"]} for p in stage.progress]
    assert stage.result_upload and b"de.m4a" in stage.result_upload, "nur die Tonspur geht zurück"
    assert stage.failed is None
    assert ("DELETE", "/api/files/f-quelle") in stage.dub_calls
    assert ("DELETE", "/api/files/f-ergebnis") in stage.dub_calls
    assert not (tmp_path / "arbeit" / "abc").exists(), "Arbeitsordner ist aufgeräumt"


def test_fehler_wird_sichtbar_gemeldet(make):
    worker, stage = make([{"status": "error", "error": "RuntimeError: Worker weg\nTraceback ..."}])
    worker.step()
    assert stage.failed == {"note": "RuntimeError: RuntimeError: Worker weg", "skipped": False}
    assert stage.result_upload is None


def test_gleiche_sprache_wird_neu_gesprochen(make):
    """Ein deutsches Video nach Deutsch: kein Überspringen, sondern Vertonung
    ohne Übersetzung (Quell- und Zielsprache gleich)."""
    worker, stage = make([DONE], source_language="de")
    assert worker.step() is True
    payload = stage.created_payload["payload"]
    assert payload["source_language"] == payload["target_language"] == "german"
    assert stage.failed is None and stage.result_upload


def test_entfernter_auftrag_bricht_ab(make):
    worker, stage = make([{"status": "running", "progress": 0.1, "phase": "speak"}])
    stage.progress_status = 409
    worker.step()
    assert stage.created_payload is None and stage.result_upload is None and stage.failed is None


def test_beschaeftigter_dienst_holt_nichts_ab(make):
    worker, stage = make([DONE])
    original = stage.dub

    def busy(request):
        if request.url.path == "/api/jobs" and request.method == "GET":
            return httpx.Response(200, json={"active": [{"id": "anderer"}]})
        return original(request)
    worker.dub = httpx.Client(base_url="http://dub", transport=httpx.MockTransport(busy))

    assert worker.step() is False
    claims = [call for call in stage.pi_calls if call[1].endswith("/claim")]
    assert claims == [], "ohne freie Kapazität wird nichts reserviert"


def test_arbeitskopie_ist_klein_und_hat_ton(tmp_path):
    original = tmp_path / "o.mp4"
    _clip(original)
    proxy = tmp_path / "p.mp4"
    nv.build_proxy(original, proxy)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width", "-of", "json", str(proxy)],
        capture_output=True, text=True, check=True)
    streams = json.loads(probe.stdout)["streams"]
    assert {s["codec_type"] for s in streams} == {"video", "audio"}
    assert next(s for s in streams if s["codec_type"] == "video")["width"] == 64


def test_untertitel_der_quelle_ersparen_das_transkribieren(make):
    """Bietet TubeVault ein Transkript an, geht es mit dem Auftrag an den
    Dienst; seine Sprache gilt, wenn TubeVault die des Videos nicht kennt."""
    worker, stage = make([DONE], source_language=None)
    segments = [{"start": 0.0, "end": 4.0, "text": "Bonjour à tous."}]
    original = stage.pi

    def with_transcript(request):
        if request.url.path == "/api/dubbing/claim":
            answer = original(request)
            body = json.loads(answer.content)
            if body.get("request"):
                body["transcript_url"] = "/api/dubbing/requests/7/transcript"
            return httpx.Response(200, json=body)
        if request.url.path.endswith("/transcript"):
            return httpx.Response(200, json={"transcript": {"language": "fr", "kind": "manual", "segments": segments}})
        return original(request)
    worker.pi = httpx.Client(base_url="http://pi", transport=httpx.MockTransport(with_transcript))

    assert worker.step() is True
    payload = stage.created_payload["payload"]
    assert payload["source_segments"] == segments
    assert payload["source_language"] == "french"
    assert any("Untertitel der Quelle" in (p.get("note") or "") for p in stage.progress)


def test_ohne_untertitel_wird_der_grund_gemeldet(make):
    worker, stage = make([DONE])
    original = stage.pi

    def without_transcript(request):
        if request.url.path == "/api/dubbing/claim":
            body = json.loads(original(request).content)
            if body.get("request"):
                body["transcript_url"] = "/api/dubbing/requests/7/transcript"
            return httpx.Response(200, json=body)
        if request.url.path.endswith("/transcript"):
            return httpx.Response(200, json={"transcript": None, "reason": "Die Quelle hat keine Untertitel"})
        return original(request)
    worker.pi = httpx.Client(base_url="http://pi", transport=httpx.MockTransport(without_transcript))

    assert worker.step() is True
    assert "source_segments" not in stage.created_payload["payload"]
    assert any("Die Quelle hat keine Untertitel" in (p.get("note") or "") for p in stage.progress)


def test_unbekannte_sprache_erkennt_der_dienst(make):
    """Kennt weder TubeVault noch ein Transkript die Sprache, rät der
    Nachvertoner nicht, sondern lässt den Dienst sie erkennen; das Ergebnis
    meldet sie als Kürzel an TubeVault zurück."""
    done = {"status": "done", "result": {"video_id": "f-ergebnis", "coverage_failed": 0,
                                         "source_language": "german"}}
    worker, stage = make([done], source_language=None)
    assert worker.step() is True
    assert stage.created_payload["payload"]["source_language"] == "auto"
    assert b'name="source_language"\r\n\r\nde' in stage.result_upload


def test_ki_transkript_wenn_nichts_zu_vertonen(make, tmp_path):
    """Keine Vertonung offen: der Nachvertoner holt ein KI-Transkript, schickt
    nur den Ton zum Dienst, lässt die Sprache erkennen und liefert die Sätze ab."""
    worker, stage = make([DONE])
    delivered = {}
    calls = []

    def pi(request):
        path = request.url.path
        calls.append(path)
        if path == "/api/dubbing/claim":
            return httpx.Response(200, json={"request": None})
        if path == "/api/transcripts/ai/claim":
            return httpx.Response(200, json={
                "request": {"video_id": "ohneuntert1", "title": "Ohne Untertitel", "language": None},
                "media_url": "/api/player/ohneuntert1",
                "progress_url": "/api/transcripts/ai/ohneuntert1/progress",
                "result_url": "/api/transcripts/ai/ohneuntert1/result",
                "fail_url": "/api/transcripts/ai/ohneuntert1/fail"})
        if path == "/api/player/ohneuntert1":
            return httpx.Response(200, content=stage.clip)
        if path.endswith("/progress"):
            return httpx.Response(200, json={"ok": True})
        if path.endswith("/result"):
            delivered.update(json.loads(request.content))
            return httpx.Response(200, json={"ok": True})
        return stage.pi(request)

    created = {}

    def dub(request):
        path = request.url.path
        if path == "/api/jobs" and request.method == "POST":
            created.update(json.loads(request.content))
            return httpx.Response(200, json={"id": "t-1"})
        if path == "/api/jobs/t-1":
            return httpx.Response(200, json={"status": "done", "result": {"transcription_id": "tr-1"}})
        if path == "/api/transcribe/tr-1":
            return httpx.Response(200, json={"language": "german", "segments": [
                {"start": 0.0, "end": 2.5, "text": " Guten Tag. "}, {"start": 2.5, "end": 3.0, "text": " "}]})
        return stage.dub(request)

    worker.pi = httpx.Client(base_url="http://pi", transport=httpx.MockTransport(pi))
    worker.dub = httpx.Client(base_url="http://dub", transport=httpx.MockTransport(dub))

    assert worker.step() is True
    assert created["type"] == "transcribe" and created["payload"]["language"] == "auto"
    assert delivered == {"language": "de", "segments": [{"start": 0.0, "end": 2.5, "text": "Guten Tag."}]}
    assert not (tmp_path / "arbeit" / "ki_ohneuntert1").exists()

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
            work_dir=tmp_path / "arbeit", default_source_language="en",
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


def test_schon_zielsprache_wird_uebersprungen(make):
    worker, stage = make([DONE], source_language="de")
    worker.step()
    assert stage.failed["skipped"] is True
    assert stage.created_payload is None, "keine Vertonung angestossen"


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
    assert stage.pi_calls == [], "ohne freie Kapazität wird nichts reserviert"


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

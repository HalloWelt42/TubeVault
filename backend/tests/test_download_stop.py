"""
Anhalten und Abbrechen greifen sofort, auch mitten im Laden (Befund 15.10.2026:
die Pause hielt nur die Warteschlange an, ein laufender Download eines
7,6-Stunden-Streams lief einfach weiter; Abbrechen setzte nur den Status).

Kontrakt:
- Hat der Nutzer die Warteschlange angehalten oder den Job abgebrochen, hört
  das Ladeprogramm beim nächsten Fortschrittsschritt auf - ohne neuen Versuch.
- Eine automatische Pause (Drosselung) lässt den laufenden Download fertig laufen.
- Angehalten: der Job steht wieder in der Warteschlange, die Teildatei bleibt.
- Abgebrochen: der Job bleibt abgebrochen, die Teildateien sind weg.
"""
import pytest
import yt_dlp

from app.services import download_service as ds
from app.services.job_service import STOP_CANCEL, STOP_PAUSE, job_service
from app.utils.ytdlp_adapter import DownloadStopped, StreamAdapter


def test_ladeprogramm_hoert_beim_naechsten_schritt_auf(monkeypatch, tmp_path):
    versuche = []

    class FakeYoutubeDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def download(self, urls):
            versuche.append(urls)
            for hook in self.opts["progress_hooks"]:
                hook({"status": "downloading", "downloaded_bytes": 10, "total_bytes": 100})

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)
    stream = StreamAdapter({"format_id": "18", "ext": "mp4"}, watch_url="https://www.youtube.com/watch?v=abcdefghijk",
                           should_stop=lambda: STOP_PAUSE)
    with pytest.raises(DownloadStopped) as stopped:
        stream.download(output_path=str(tmp_path), filename="video_tmp.mp4")
    assert stopped.value.reason == STOP_PAUSE
    assert len(versuche) == 1                      # kein neuer Versuch mit anderem Client


async def test_grund_zum_aufhoeren(test_db):
    await job_service.resume_queue()
    assert job_service.stop_reason(4711) is None
    await job_service.pause_queue("rate_limit")
    assert job_service.stop_reason(4711) is None   # automatische Pause: fertig laden
    await job_service.pause_queue("user")
    assert job_service.stop_reason(4711) == STOP_PAUSE
    await job_service.resume_queue()
    job_service._cancelled.add(4711)
    assert job_service.stop_reason(4711) == STOP_CANCEL
    job_service.clear_cancel(4711)


async def test_angehalten_wieder_eingereiht_abgebrochen_aufgeraeumt(test_db, tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "VIDEOS_DIR", tmp_path)
    service = ds.DownloadService() if hasattr(ds, "DownloadService") else ds.download_service
    sent = []

    async def broadcast(data):
        sent.append(data)
    monkeypatch.setattr(service, "_ws_broadcast", broadcast)

    pausiert = await job_service.create(job_type="download", title="Langer Stream", metadata={"video_id": "langerstrm1"})
    await job_service.start(pausiert["id"], exclusive=False)
    teil = tmp_path / "langerstrm1" / ds.STAGING_DIRNAME / "video_tmp.mp4.part"
    teil.parent.mkdir(parents=True)
    teil.write_bytes(b"x" * 100)
    await service._after_stop(pausiert["id"], "langerstrm1", STOP_PAUSE)
    assert (await job_service.get(pausiert["id"]))["status"] == "queued"
    assert teil.exists()                           # beim Fortsetzen lädt es hier weiter

    abgebrochen = await job_service.create(job_type="download", title="Weg damit", metadata={"video_id": "langerstrm2"})
    await job_service.start(abgebrochen["id"], exclusive=False)
    rest = tmp_path / "langerstrm2" / ds.STAGING_DIRNAME / "video_tmp.mp4.part"
    rest.parent.mkdir(parents=True)
    rest.write_bytes(b"x")
    await job_service.cancel(abgebrochen["id"])
    await service._after_stop(abgebrochen["id"], "langerstrm2", STOP_CANCEL)
    assert (await job_service.get(abgebrochen["id"]))["status"] == "cancelled"
    assert not rest.parent.exists() and job_service.stop_reason(abgebrochen["id"]) is None
    assert [m["status"] for m in sent] == ["queued", "cancelled"]

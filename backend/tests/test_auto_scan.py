"""
Steuerbare Hintergrundarbeiten Kanalscan und Vertonen (Wunsch 15.10.2026).

Kontrakt Kanalscan (services/auto_scan.py):
- Ungescannt heißt: noch nie vollständig gelesen (last_scanned leer).
- Angehalten ist der Standard; dann wird nichts gelesen.
- Eingeschaltet: höchstens ein Kanal je 2 Stunden, nie versuchte zuerst;
  ein gescheiterter Kanal kommt erst nach allen anderen wieder dran.
- In der Liste der Hintergrundarbeiten mit Stand und Schalter, solange
  ungescannte Kanäle übrig sind.

Kontrakt Vertonen:
- Angehalten ist der Standard: der Nachvertoner bekommt keinen Auftrag.
- Angehalten bleibt es in der Liste sichtbar, damit es sich dort fortsetzen lässt.
"""
import pytest

from app.services import auto_scan, background_work
from app.services.rss_service import rss_service


@pytest.fixture
async def kanaele(test_db):
    for channel_id, name, scanned in [("UCa", "Alpha", None), ("UCb", "Beta", None), ("UCc", "Gamma", "2026-10-01 10:00:00")]:
        await test_db.execute("INSERT INTO subscriptions (channel_id, channel_name, last_scanned) VALUES (?, ?, ?)",
                              (channel_id, name, scanned))
    return test_db


@pytest.fixture
def scans(monkeypatch, kanaele):
    """Statt der Quelle: der Scan setzt last_scanned, außer für Kanäle in fails."""
    seen, fails = [], set()

    async def fake(channel_id, job_id=None):
        seen.append(channel_id)
        if channel_id in fails:
            raise RuntimeError("Kanal nicht erreichbar")
        await kanaele.execute("UPDATE subscriptions SET last_scanned = datetime('now') WHERE channel_id = ?", (channel_id,))
        return {"status": "ok"}
    monkeypatch.setattr(rss_service, "fetch_all_channel_videos", fake)
    return seen, fails


async def _zwei_stunden_spaeter(db):
    await db.execute("UPDATE subscriptions SET auto_scan_at = datetime(auto_scan_at, '-121 minutes') WHERE auto_scan_at IS NOT NULL")


async def test_angehalten_ist_standard(kanaele, scans):
    seen, _ = scans
    assert await auto_scan.pending() == 2
    assert await auto_scan.run_due() is None and seen == []
    [item] = [i for i in await background_work.compute_overview() if i.key == "channel_scan"]
    assert item.paused and item.switch_key == "scan.auto_enabled" and (item.done, item.total) == (1, 3)


async def test_einer_alle_zwei_stunden_bis_alle_erfasst(kanaele, scans, set_setting):
    seen, _ = scans
    await set_setting("scan.auto_enabled", "true")
    assert await auto_scan.run_due() == "Alpha"
    assert await auto_scan.run_due() is None                     # erst in zwei Stunden wieder
    assert 7000 < await auto_scan.seconds_until_due() <= 7200
    await _zwei_stunden_spaeter(kanaele)
    assert await auto_scan.run_due() == "Beta"
    await _zwei_stunden_spaeter(kanaele)
    assert await auto_scan.run_due() is None and seen == ["UCa", "UCb"]
    assert await auto_scan.pending() == 0
    assert not [i for i in await background_work.compute_overview() if i.key == "channel_scan"]


async def test_gescheiterter_kanal_kommt_zuletzt_wieder(kanaele, scans, set_setting):
    seen, fails = scans
    fails.add("UCa")
    await set_setting("scan.auto_enabled", "true")
    assert await auto_scan.run_due() == "Alpha"
    job = await kanaele.fetch_one("SELECT status FROM jobs WHERE type = 'channel_scan' ORDER BY id DESC LIMIT 1")
    assert job["status"] == "error"
    await _zwei_stunden_spaeter(kanaele)
    assert (await auto_scan.next_channel())["channel_id"] == "UCb"
    assert await auto_scan.run_due() == "Beta"
    await _zwei_stunden_spaeter(kanaele)
    assert (await auto_scan.next_channel())["channel_id"] == "UCa"


async def test_vertonen_angehalten_gibt_keinen_auftrag(test_db, set_setting):
    from app.services import dubbing
    await set_setting("dub.enabled", "true")
    [item] = [i for i in await background_work.compute_overview() if i.key == "dubbing"]
    assert item.paused and item.waiting == 0           # angehalten immer sichtbar, auch ohne Auftrag
    await test_db.execute("INSERT INTO videos (id, title, status) VALUES ('vid00000001', 'Ein Video', 'ready')")
    await test_db.execute("INSERT INTO dub_requests (video_id, target_language, status) VALUES ('vid00000001', 'de', 'queued')")
    assert await dubbing.claim("Rechner") is None
    [item] = [i for i in await background_work.compute_overview() if i.key == "dubbing"]
    assert (item.label, item.paused, item.waiting, item.switch_key) == ("Vertonen", True, 1, "dub.processing_enabled")

    await set_setting("dub.processing_enabled", "true")
    claimed = await dubbing.claim("Rechner")
    assert claimed and claimed.video_id == "vid00000001"
    [item] = [i for i in await background_work.compute_overview() if i.key == "dubbing"]
    assert not item.paused and item.label.startswith("Nachvertonung: Ein Video")

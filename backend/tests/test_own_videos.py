"""
Eigene Videos: Sammlung einlesen und abgleichen.

Kontrakt (Wünsche 15.10.2026):
- Ohne Sammlung (kein externes Laufwerk) gibt es keine Fehler, nur nichts zu tun.
- Einlesen läuft im Hintergrund, jede geprüfte Datei ist sofort sichtbar.
- Der Stand bleibt gespeichert; erneutes Einlesen öffnet nur neue oder
  geänderte Dateien, verschwundene gelten als fehlend.
- Abgleich: schon vorhanden / sicher erkannt / vermutlich / unbekannt.
"""
from pathlib import Path

import pytest

from app.models.own_files import Finding, MatchReason, ScanState
from app.routers import own_collection
from app.services import own_inventory, own_matching, own_scan
from app.services.own_inventory import FileFacts

NFO = """﻿<?xml version="1.0" encoding="utf-8"?>
<movie><title>{title}</title><fileinfo><streamdetails><video>
<width>1920</width><height>1080</height><durationinseconds>{duration}</durationinseconds>
</video></streamdetails></fileinfo></movie>"""


def _video(root: Path, rel: str, size: int = 1000, title: str = None, duration: int = None) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"v" * size)
    if title:
        path.with_name(path.stem + ".nfo").write_text(NFO.format(title=title, duration=duration), encoding="utf-8")
    return path


@pytest.fixture
def collection(tmp_path, monkeypatch):
    root = tmp_path / "sammlung"
    root.mkdir()
    monkeypatch.setattr(own_scan, "collection_root", lambda: root)
    monkeypatch.setattr(own_inventory, "_ffprobe", lambda video: {})   # Testdateien sind kein Video
    return root


# ─── Dateien ──────────────────────────────────────────────────────────

def test_titel_aus_dem_dateinamen():
    assert own_inventory.readable_title(
        "50 Shades of Greek - Alarm in Athen _ ARTE (720p_30fps_H264-192kbit_AAC)") \
        == "50 Shades of Greek - Alarm in Athen | ARTE"
    assert own_inventory.readable_title("Tails_ Dieses sichere Betriebssystem") == "Tails: Dieses sichere Betriebssystem"
    assert own_inventory.readable_title("Was bringen Custom-Tastaturen_") == "Was bringen Custom-Tastaturen?"


def test_kennung_der_quelle_im_dateinamen():
    assert own_inventory.source_id_of("Titel [dQw4w9WgXcQ].mp4") == ("dQw4w9WgXcQ", True)
    assert own_inventory.source_id_of("Titel-dQw4w9WgXcQ.mp4") == ("dQw4w9WgXcQ", False)
    assert own_inventory.source_id_of("Learn-Programming.mp4") == (None, False)   # ein Wort, keine Kennung


def test_angaben_aus_nfo_und_ordner(collection):
    _video(collection, "CT3003/Tails_ Betriebssystem.mp4", title="Tails: Betriebssystem", duration=784)
    (collection / "CT3003" / "Tails_ Betriebssystem-poster.jpg").write_bytes(b"jpg")
    facts = own_inventory.probe(collection, "CT3003/Tails_ Betriebssystem.mp4")
    assert (facts.title, facts.duration, facts.height, facts.channel_hint) == \
        ("Tails: Betriebssystem", 784, 1080, "CT3003")
    assert facts.thumbnail == "CT3003/Tails_ Betriebssystem-poster.jpg"


def test_begleitdateien_gehoeren_nur_zu_ihrem_video(collection):
    _video(collection, "K/Video.mp4", title="Video", duration=10)
    _video(collection, "K/Video.2.mp4")
    for name in ("Video-poster.jpg", "Video.de.srt", "Video.2.nfo", "Videoabend.txt"):
        (collection / "K" / name).write_text("x")
    names = sorted(p.name for p in own_inventory.companions(collection, "K/Video.mp4"))
    assert names == ["Video-poster.jpg", "Video.de.srt", "Video.nfo"]


def test_loeschen_nimmt_leeren_videoordner_mit(collection):
    _video(collection, "ARTE/Doku/Doku.mp4", title="Doku", duration=60)
    removed = own_inventory.remove_with_companions(collection, "ARTE/Doku/Doku.mp4", collection / "ARTE")
    assert sorted(removed) == ["Doku.mp4", "Doku.nfo"]
    assert not (collection / "ARTE" / "Doku").exists() and (collection / "ARTE").is_dir()


# ─── Abgleich ─────────────────────────────────────────────────────────

LIB = own_matching.KnownVideo("nP7N1_34lh8", "500 Euro für eine Tastatur | Was bringen Custom-Tastaturen?",
                              "UCct", "c't 3003", 914, 186_100_000, in_library=True)
FEED = own_matching.KnownVideo("arteVideo01", "50 Shades of Greek - Alarm in Athen | ARTE",
                               "UCarte", "ARTEde", 1560)


def _index():
    return own_matching.MatchIndex([LIB], [FEED], [("UCct", "c't 3003"), ("UCarte", "ARTEde")])


def _facts(title, duration=None, size=1, hint=None, source_id=None, certain=False):
    return FileFacts(title=title, size=size, duration=duration, channel_hint=hint,
                     source_id=source_id, source_id_certain=certain)


def test_gleiche_datei_ist_schon_vorhanden():
    result = own_matching.match(_facts("ganz anderer Name", 915, 186_100_000), _index())
    assert (result.finding, result.reason, result.video_id) == (Finding.DUPLICATE, MatchReason.SAME_FILE, LIB.id)


def test_gleicher_titel_und_dauer_ist_schon_vorhanden():
    result = own_matching.match(_facts("500 Euro für eine Tastatur _ Was bringen Custom-Tastaturen_", 913), _index())
    assert (result.finding, result.reason) == (Finding.DUPLICATE, MatchReason.TITLE_DURATION)


def test_feed_eintrag_mit_gleicher_dauer_ist_sicher_erkannt():
    result = own_matching.match(_facts("50 Shades of Greek - Alarm in Athen _ ARTE", 1561, hint="ARTE"), _index())
    assert (result.finding, result.video_id, result.in_library) == (Finding.CERTAIN, FEED.id, False)


def test_gleicher_titel_ohne_dauer_ist_vermutlich():
    result = own_matching.match(_facts("50 Shades of Greek - Alarm in Athen _ ARTE"), _index())
    assert (result.finding, result.reason) == (Finding.PROBABLE, MatchReason.TITLE)


def test_andere_dauer_ist_ein_anderes_video():
    result = own_matching.match(_facts("50 Shades of Greek - Alarm in Athen _ ARTE", 60), _index())
    assert result.finding == Finding.UNKNOWN


def test_aehnlicher_titel_im_vermuteten_kanal():
    result = own_matching.match(_facts("500 Euro fuer eine Tastatur - was bringen Custom Tastaturen", hint="CT3003"),
                                _index())
    assert (result.finding, result.reason, result.video_id) == (Finding.PROBABLE, MatchReason.SIMILAR_TITLE, LIB.id)


def test_kennung_entscheidet():
    index = _index()
    assert own_matching.match(_facts("x", source_id=LIB.id), index).finding == Finding.DUPLICATE
    assert own_matching.match(_facts("x", source_id="neuNeuNeu12", certain=True), index).finding == Finding.CERTAIN
    assert own_matching.match(_facts("x", source_id="neuNeuNeu12"), index).finding == Finding.UNKNOWN


# ─── Einlesen ─────────────────────────────────────────────────────────

async def _files(folder_id, finding=None):
    items, total = await own_scan.files(folder_id, finding)
    return {f.name: f for f in items}


async def test_einlesen_merkt_sich_den_stand(test_db, collection):
    await test_db.execute(
        """INSERT INTO videos (id, title, channel_id, channel_name, duration, file_size, status)
           VALUES ('nP7N1_34lh8', '500 Euro für eine Tastatur | Was bringen Custom-Tastaturen?',
                   'UCct', 'c''t 3003', 914, 3000, 'ready')""")
    _video(collection, "c't 3003/500 Euro für eine Tastatur _ Was bringen Custom-Tastaturen_.mp4", size=3000,
           title="500 Euro für eine Tastatur _ Was bringen Custom-Tastaturen_", duration=914)
    _video(collection, "c't 3003/Unbekannt.mp4", title="Etwas ganz anderes", duration=77)
    _video(collection, "Anderes/Fremd.mp4", title="Fremd", duration=5)

    folder_id = await own_scan.request_scan("c't 3003")
    await own_scan.scan(folder_id, "c't 3003")

    found = await _files(folder_id)
    assert set(found) == {"500 Euro für eine Tastatur _ Was bringen Custom-Tastaturen_.mp4", "Unbekannt.mp4"}
    duplicate = found["500 Euro für eine Tastatur _ Was bringen Custom-Tastaturen_.mp4"]
    assert duplicate.finding == Finding.DUPLICATE and duplicate.match.video_id == "nP7N1_34lh8"
    assert found["Unbekannt.mp4"].finding == Finding.UNKNOWN
    [folder] = await own_scan.folders()
    assert (folder.state, folder.files, folder.checked) == (ScanState.IDLE, 2, 2)
    assert folder.open_by_finding == {"duplicate": 1, "unknown": 1}

    # Zweiter Durchgang: Geprüftes wird nicht noch einmal geöffnet, Neues schon,
    # Verschwundenes fehlt
    opened = []
    original = own_inventory.probe
    monkey_probe = lambda root, rel: opened.append(rel) or original(root, rel)   # noqa: E731
    own_scan.own_inventory.probe = monkey_probe
    try:
        (collection / "c't 3003" / "Unbekannt.mp4").unlink()
        _video(collection, "c't 3003/Neu.mp4", title="Neu", duration=12)
        await own_scan.rescan(folder_id)
        await own_scan.scan(folder_id, "c't 3003")
    finally:
        own_scan.own_inventory.probe = original
    assert opened == ["c't 3003/Neu.mp4"]
    assert set(await _files(folder_id)) == {"500 Euro für eine Tastatur _ Was bringen Custom-Tastaturen_.mp4",
                                            "Neu.mp4"}


async def test_fehlende_sammlung_ist_kein_fehler(test_db, collection, async_client_factory):
    """Wer kein externes Laufwerk hat, sieht einfach eine leere Sammlung."""
    collection.rmdir()
    async with await async_client_factory(own_collection.router) as client:
        r = await client.get("/api/own-videos/collection")
        assert r.status_code == 200
        assert r.json() == {"available": False, "folders": [], "candidates": []}
        r = await client.post("/api/own-videos/folders", json={"path": "youtube"})
        assert r.status_code == 400


async def test_abgezogenes_laufwerk_loescht_keinen_stand(test_db, collection):
    _video(collection, "K/A.mp4", title="A", duration=10)
    folder_id = await own_scan.request_scan("K")
    await own_scan.scan(folder_id, "K")
    for path in sorted(collection.rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    await own_scan.scan(folder_id, "K")
    assert set(await _files(folder_id)) == {"A.mp4"}


async def test_anhalten_und_weitermachen(test_db, collection):
    for n in range(3):
        _video(collection, f"K/{n}.mp4", title=f"Video {n}", duration=10 + n)
    folder_id = await own_scan.request_scan("K")
    original = own_inventory.probe

    def probe_then_pause(root, rel):
        own_scan._stop.add(folder_id)   # wie ein Klick auf Anhalten während der ersten Datei
        return original(root, rel)
    own_scan.own_inventory.probe = probe_then_pause
    try:
        await own_scan.scan(folder_id, "K")
    finally:
        own_scan.own_inventory.probe = original
    await own_scan.pause(folder_id)
    [folder] = await own_scan.folders()
    assert (folder.state, folder.checked, folder.files) == (ScanState.PAUSED, 1, 3)

    await own_scan.rescan(folder_id)
    await own_scan.scan(folder_id, "K")
    [folder] = await own_scan.folders()
    assert (folder.state, folder.checked) == (ScanState.IDLE, 3)


async def test_pfade_nach_aussen_sind_verboten(test_db, collection):
    with pytest.raises(ValueError):
        await own_scan.request_scan("../etc")

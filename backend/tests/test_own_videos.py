"""
Eigene Videos: Sammlung einlesen und abgleichen.

Kontrakt (Wünsche 15.10.2026):
- Ohne Sammlung (kein externes Laufwerk) gibt es keine Fehler, nur nichts zu tun.
- Einlesen läuft im Hintergrund, jede geprüfte Datei ist sofort sichtbar.
- Der Stand bleibt gespeichert; erneutes Einlesen öffnet nur neue oder
  geänderte Dateien, verschwundene gelten als fehlend.
- Abgleich: schon vorhanden / sicher erkannt / vermutlich / unbekannt.
"""
import asyncio
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
        assert r.json() == {"available": False, "folders": [], "candidates": [], "bulk": None}
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


# ─── Einordnen ────────────────────────────────────────────────────────

from app.models.own_files import Decision   # noqa: E402
from app.services import own_actions       # noqa: E402


@pytest.fixture
def library_dirs(tmp_path, monkeypatch):
    videos, thumbs = tmp_path / "videos", tmp_path / "thumbs"
    monkeypatch.setattr(own_actions, "VIDEOS_DIR", videos)
    monkeypatch.setattr(own_actions, "THUMBNAILS_DIR", thumbs)
    monkeypatch.setattr(own_actions, "RSS_THUMBS_DIR", tmp_path / "rss")
    monkeypatch.setattr(own_actions, "_frame_thumbnail", lambda video, vid, duration: None)

    async def no_download(*a, **k):
        return None
    import app.utils.thumbnail_utils as thumbnail_utils
    monkeypatch.setattr(thumbnail_utils, "download_yt_thumbnail", no_download)
    return videos, thumbs


async def _scanned(collection, folder="K"):
    folder_id = await own_scan.request_scan(folder)
    await own_scan.scan(folder_id, folder)
    return folder_id, await _files(folder_id)


async def test_sicher_erkanntes_wird_uebernommen(test_db, collection, library_dirs):
    videos, thumbs = library_dirs
    await test_db.execute("INSERT INTO subscriptions (channel_id, channel_name) VALUES ('UCarte', 'ARTEde')")
    await test_db.execute(
        """INSERT INTO rss_entries (video_id, channel_id, title, published, duration)
           VALUES ('arteVideo01', 'UCarte', 'Alarm in Athen | ARTE', '2026-01-02', 1560)""")
    _video(collection, "K/Athen/Alarm in Athen _ ARTE.mp4", size=500, title="Alarm in Athen _ ARTE", duration=1561)
    (collection / "K" / "Athen" / "Alarm in Athen _ ARTE-poster.jpg").write_bytes(b"bild")
    _video(collection, "K/Kopie/Alarm in Athen _ ARTE.mp4", size=400, title="Alarm in Athen _ ARTE", duration=1560)
    folder_id, _ = await _scanned(collection)
    items, _ = await own_scan.files(folder_id)
    first = next(f for f in items if f.folder == "K/Athen")
    assert first.finding == Finding.CERTAIN

    assert await own_actions.adopt(first.id) == "arteVideo01"
    video = await test_db.fetch_one("SELECT * FROM videos WHERE id = 'arteVideo01'")
    assert (video["title"], video["channel_name"], video["status"], video["source"]) == \
        ("Alarm in Athen | ARTE", "ARTEde", "ready", "imported")
    assert Path(video["file_path"]) == videos / "arteVideo01" / "video.mp4" and Path(video["file_path"]).is_file()
    assert (thumbs / "arteVideo01" / "thumbnail.jpg").read_bytes() == b"bild"
    assert not (collection / "K" / "Athen").exists(), "Begleitdateien und leerer Ordner sind weg"
    # die zweite Kopie desselben Videos ist jetzt doppelt
    rest = await _files(folder_id)
    assert [f.finding for f in rest.values()] == [Finding.DUPLICATE]
    with pytest.raises(own_actions.ActionError):
        await own_actions.adopt(next(iter(rest.values())).id, "arteVideo01")


async def test_eigener_kanal_bleibt_derselbe(test_db, collection, library_dirs):
    await test_db.execute("INSERT INTO subscriptions (channel_id, channel_name) VALUES ('UCct', 'c''t 3003')")
    for name in ("Spot 1", "Spot 2", "Tasten"):
        _video(collection, f"K/{name}.mp4", title=name, duration=30)
    _, found = await _scanned(collection)
    a = await own_actions.make_own(found["Spot 1.mp4"].id, "Werbespots")
    b = await own_actions.make_own(found["Spot 2.mp4"].id, "werbespots")
    c = await own_actions.make_own(found["Tasten.mp4"].id, "c't 3003")
    rows = {r["id"]: r for r in await test_db.fetch_all("SELECT id, channel_id, source FROM videos")}
    assert a.startswith("own_") and rows[a]["source"] == "local"
    assert rows[a]["channel_id"] == rows[b]["channel_id"] == own_actions.own_channel_id("Werbespots")
    assert rows[c]["channel_id"] == "UCct"
    assert {ch["channel_name"] for ch in await own_actions.channels()} >= {"c't 3003", "Werbespots"}


async def test_loeschen_und_ueberspringen(test_db, collection, library_dirs):
    _video(collection, "K/Weg.mp4", title="Weg", duration=10)
    (collection / "K" / "Weg-poster.jpg").write_bytes(b"x")
    _video(collection, "K/Bleibt.mp4", title="Bleibt", duration=11)
    folder_id, found = await _scanned(collection)
    await own_actions.delete(found["Weg.mp4"].id)
    assert sorted(p.name for p in (collection / "K").iterdir()) == ["Bleibt.mp4", "Bleibt.nfo"]
    await own_actions.skip(found["Bleibt.mp4"].id)
    assert await _files(folder_id) == {}
    done = await _files(folder_id, "done")
    assert {f.name: f.decision for f in done.values()} == {"Weg.mp4": Decision.DELETED, "Bleibt.mp4": Decision.SKIPPED}
    await own_actions.reopen(found["Bleibt.mp4"].id)
    assert set(await _files(folder_id)) == {"Bleibt.mp4"}


async def test_ersetzen_tauscht_die_bibliotheksdatei(test_db, collection, library_dirs):
    videos, _ = library_dirs
    old = videos / "nP7N1_34lh8" / "video.webm"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"alt")
    await test_db.execute(
        """INSERT INTO videos (id, title, duration, file_size, file_path, status)
           VALUES ('nP7N1_34lh8', 'Tastatur', 914, 3, ?, 'ready')""", (str(old),))
    _video(collection, "K/Tastatur.mp4", size=9000, title="Tastatur", duration=914)
    _, found = await _scanned(collection)
    assert found["Tastatur.mp4"].finding == Finding.DUPLICATE
    await own_actions.replace(found["Tastatur.mp4"].id)
    row = await test_db.fetch_one("SELECT file_path, file_size FROM videos WHERE id = 'nP7N1_34lh8'")
    assert row["file_path"].endswith("nP7N1_34lh8/video.mp4") and row["file_size"] == 9000
    assert not old.exists() and not (collection / "K" / "Tastatur.mp4").exists()


async def test_archivvideos_werden_nicht_ersetzt(test_db, collection, library_dirs):
    await test_db.execute(
        """INSERT INTO videos (id, title, duration, file_size, file_path, status, storage_type)
           VALUES ('archivVid01', 'Archiv', 50, 3, '/archiv/x.mp4', 'ready', 'archive')""")
    _video(collection, "K/Archiv.mp4", title="Archiv", duration=50)
    _, found = await _scanned(collection)
    with pytest.raises(own_actions.ActionError):
        await own_actions.replace(found["Archiv.mp4"].id)
    assert (collection / "K" / "Archiv.mp4").exists()


async def test_doppelte_auf_einmal_loeschen(test_db, collection, library_dirs):
    await test_db.execute(
        "INSERT INTO videos (id, title, duration, file_size, status) VALUES ('vorhanden01', 'Da', 100, 77, 'ready')")
    for n in range(3):
        _video(collection, f"K/Kopie {n}.mp4", size=77, title=f"Kopie {n}", duration=100)
    _video(collection, "K/Anders.mp4", title="Anders", duration=5)
    folder_id, _ = await _scanned(collection)
    run = await own_actions.start_bulk(folder_id, "delete_duplicates")
    assert run.total == 3
    while own_actions.bulk_running():
        await asyncio.sleep(0.01)
    assert sorted(p.name for p in (collection / "K").iterdir()) == ["Anders.mp4", "Anders.nfo"]


async def test_eingeordnet_zeigt_ordnerpfade_als_kanal(test_db, async_client_factory):
    await test_db.execute(
        """INSERT INTO videos (id, title, channel_name, status, source, file_size, file_path) VALUES
           ('own_1', 'A', 'youtube/ARTE/Reihe', 'ready', 'local', 10, '/v/1.mp4'),
           ('own_2', 'B', 'Werbespots', 'ready', 'local', 5, '/v/2.mp4'),
           ('nP7N1_34lh8', 'C', 'c''t 3003', 'ready', 'youtube', 1, '/v/3.mp4')""")
    async with await async_client_factory(own_collection.router) as client:
        page = (await client.get("/api/own-videos/library")).json()
    assert (page["total"], page["total_bytes"], page["folder_named_channels"]) == (2, 15, 1)


def test_bei_gleicher_groesse_entscheidet_der_titel():
    """Mehrere gleich große Kandidaten gleicher Dauer: der mit passendem Titel."""
    a = own_matching.KnownVideo("aaaaaaaaaaa", "Anderes Video", None, None, 415, 500, in_library=True)
    b = own_matching.KnownVideo("bbbbbbbbbbb", "Sauerteig Folge 176", None, None, 416, 500, in_library=True)
    index = own_matching.MatchIndex([a, b], [], [])
    assert own_matching.match(_facts("Sauerteig Folge 176", 415, 500), index).video_id == "bbbbbbbbbbb"

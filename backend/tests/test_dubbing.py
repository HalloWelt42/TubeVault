"""
Nachvertonung: Warteliste und zusätzliche Tonspuren.

Kontrakt:
- Vormerken nur bei eingeschalteter Erweiterung; doppelte, schon vertonte und
  bereits zielsprachige Videos werden mit Grund übersprungen.
- Ein Auftrag geht an genau einen Nachvertoner; verwaiste gehen zurück.
- Die abgelieferte Tonspur wird geprüft, am Video gespeichert und ist
  abspielbar; das Video selbst bleibt unverändert.
"""
import shutil
import subprocess

import pytest

from app.routers import dubbing as dubbing_router
from app.services import audio_tracks, dubbing

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg fehlt")


@pytest.fixture
async def client(async_client_factory, monkeypatch, tmp_path):
    from app import config
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(config, "TEMP_DIR", tmp_path / "temp")
    c = await async_client_factory(dubbing_router.router)
    async with c:
        yield c


@pytest.fixture
async def videos(test_db, set_setting):
    await set_setting("dub.enabled", "true")
    for vid, lang, status in (("en1", "en", "ready"), ("en2", None, "ready"),
                              ("de1", "de", "ready"), ("stub", "en", "metadata")):
        await test_db.execute(
            "INSERT INTO videos (id, title, status, language) VALUES (?, ?, ?, ?)",
            (vid, f"Titel {vid}", status, lang))


def _tone(path, seconds=2):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", f"sine=frequency=440:duration={seconds}", "-c:a", "aac", str(path)], check=True)
    return path


async def test_ausgeschaltet_nimmt_nichts_an(client, test_db):
    await test_db.execute("INSERT INTO videos (id, title, status) VALUES ('en1', 'T', 'ready')")
    r = await client.post("/api/dubbing/requests", json={"video_id": "en1"})
    assert r.status_code == 409
    assert (await client.post("/api/dubbing/claim", json={"worker": "mac"})).json()["request"] is None


async def test_vormerken_mit_gruenden(client, videos):
    async def vormerken(video_id, **extra):
        return (await client.post("/api/dubbing/requests", json={"video_id": video_id, **extra})).json()

    first = await vormerken("en1", voice="Andere", subtitles="any")
    assert first["queued"] and first["request"]["voice"] == "Andere"
    assert first["request"]["subtitles"] == "any"
    assert (await vormerken("en2"))["queued"]
    assert "bereits Deutsch" in (await vormerken("de1"))["reason"]
    assert "nicht geladen" in (await vormerken("stub"))["reason"]
    again = await vormerken("en1")
    assert not again["queued"] and "vorgemerkt" in again["reason"]


async def test_stimmen_kommen_vom_nachvertoner(client, videos):
    assert (await client.get("/api/dubbing/voices")).json()["voices"] == []
    reported = (await client.post(
        "/api/dubbing/voices", json={"voices": ["Bert", "Zeit Stimme", "anna", "Bert"]})).json()
    assert reported["voices"] == ["anna", "Bert", "Zeit Stimme"]
    assert reported["default"] == "Zeit Stimme"
    # Ohne Angabe gilt die Vorauswahl
    queued = (await client.post("/api/dubbing/requests", json={"video_id": "en1"})).json()
    assert queued["request"]["voice"] == "Zeit Stimme"
    assert queued["request"]["subtitles"] == "any"


async def test_abholen_geht_an_genau_einen(client, videos):
    await client.post("/api/dubbing/requests", json={"video_id": "en1"})
    first = (await client.post("/api/dubbing/claim", json={"worker": "mac-a"})).json()
    second = (await client.post("/api/dubbing/claim", json={"worker": "mac-b"})).json()
    # Noch keine Stimmen gemeldet: die Vorauswahl trifft dann der Nachvertoner
    assert first["request"]["video_id"] == "en1" and first["request"]["voice"] is None
    assert first["media_url"] == "/api/player/en1"
    assert second["request"] is None


async def test_verwaister_auftrag_kehrt_zurueck(client, videos, test_db):
    await client.post("/api/dubbing/requests", json={"video_id": "en1"})
    claimed = (await client.post("/api/dubbing/claim", json={"worker": "mac-a"})).json()["request"]
    await test_db.execute(
        "UPDATE dub_requests SET heartbeat_at = datetime('now', '-2 hours') WHERE id = ?", (claimed["id"],))
    again = (await client.post("/api/dubbing/claim", json={"worker": "mac-b"})).json()["request"]
    assert again["id"] == claimed["id"] and again["worker"] == "mac-b"


async def test_lebenszeichen_und_abbruch(client, videos):
    await client.post("/api/dubbing/requests", json={"video_id": "en1"})
    job = (await client.post("/api/dubbing/claim", json={"worker": "mac"})).json()["request"]
    ok = await client.post(f"/api/dubbing/requests/{job['id']}/progress", json={"progress": 0.4, "note": "Übersetzen"})
    assert ok.status_code == 200
    # Ein laufender Auftrag lässt sich nicht einfach löschen, nur abbrechen
    assert (await client.delete(f"/api/dubbing/requests/{job['id']}")).status_code == 409
    assert (await client.post(f"/api/dubbing/requests/{job['id']}/cancel")).status_code == 200
    gone = await client.post(f"/api/dubbing/requests/{job['id']}/progress", json={"progress": 0.5})
    assert gone.status_code == 409, "abgebrochener Auftrag: Nachvertoner soll aufhören"

    # Er bleibt sichtbar, mit dem Stand beim Abbruch
    listed = (await client.get("/api/dubbing/requests")).json()
    assert listed["counts"]["cancelled"] == 1
    assert listed["requests"][0]["status"] == "cancelled" and "40 %" in listed["requests"][0]["note"]
    # Eine späte Fehlermeldung des Nachvertoners ändert daran nichts
    await client.post(f"/api/dubbing/requests/{job['id']}/fail", json={"note": "abgebrochen"})
    assert (await client.get("/api/dubbing/requests")).json()["requests"][0]["status"] == "cancelled"
    # Erneut vormerken oder aus der Liste nehmen
    assert (await client.post(f"/api/dubbing/requests/{job['id']}/retry")).status_code == 200
    assert (await client.post(f"/api/dubbing/requests/{job['id']}/cancel")).status_code == 200
    assert (await client.delete(f"/api/dubbing/requests/{job['id']}")).status_code == 200


async def test_videoliste_kennzeichnet_und_filtert_nachvertonte(client, videos, test_db):
    await test_db.execute(
        "INSERT INTO audio_tracks (video_id, language, label, origin, file_path) "
        "VALUES ('en2', 'de', 'Deutsch', 'dub', '/x/de.m4a')")
    from app.models.video import VideoResponse
    from app.services.metadata_service import metadata_service
    everything = (await metadata_service.get_videos())["videos"]
    assert {v["id"]: v["extra_audio"] for v in everything}["en2"] == ["de"]
    assert {v["id"]: v["extra_audio"] for v in everything}["en1"] == []
    en2 = next(v for v in everything if v["id"] == "en2")
    assert VideoResponse(**en2).extra_audio == ["de"]        # kommt in der Antwort an
    only = await metadata_service.get_videos(has_extra_audio=True)
    assert [v["id"] for v in only["videos"]] == ["en2"] and only["total"] == 1



async def test_fehlschlag_und_wiederholen(client, videos):
    await client.post("/api/dubbing/requests", json={"video_id": "en1"})
    job = (await client.post("/api/dubbing/claim", json={"worker": "mac"})).json()["request"]
    await client.post(f"/api/dubbing/requests/{job['id']}/fail", json={"note": "Worker nicht erreichbar"})
    listed = (await client.get("/api/dubbing/requests?status=error")).json()
    assert listed["requests"][0]["note"] == "Worker nicht erreichbar" and listed["counts"]["error"] == 1
    assert (await client.post(f"/api/dubbing/requests/{job['id']}/retry")).status_code == 200
    assert (await client.post("/api/dubbing/claim", json={"worker": "mac"})).json()["request"]["id"] == job["id"]


@needs_ffmpeg
async def test_tonspur_abliefern_und_abspielen(client, videos, tmp_path):
    await client.post("/api/dubbing/requests", json={"video_id": "en2"})
    job = (await client.post("/api/dubbing/claim", json={"worker": "mac"})).json()["request"]
    audio = _tone(tmp_path / "deutsch.m4a")

    with audio.open("rb") as fh:
        r = await client.post(
            f"/api/dubbing/requests/{job['id']}/result",
            files={"file": ("deutsch.m4a", fh, "audio/mp4")},
            data={"source_language": "en", "voice": "Zeit Stimme"})
    assert r.status_code == 200, r.text
    track = r.json()["track"]
    assert track["language"] == "de" and track["label"] == "Deutsch" and track["duration"] > 1

    tracks = (await client.get("/api/videos/en2/audio-tracks")).json()["tracks"]
    assert [t["language"] for t in tracks] == ["de"]
    part = await client.get(f"/api/player/en2/track/{track['id']}", headers={"Range": "bytes=0-99"})
    assert part.status_code == 206 and len(part.content) == 100

    done = (await client.get("/api/dubbing/requests?status=done")).json()["requests"][0]
    assert done["progress"] == 1 and done["source_language"] == "en", "unbekannte Quellsprache wird nachgetragen"

    again = (await client.post("/api/dubbing/requests", json={"video_id": "en2"})).json()
    assert "schon vorhanden" in again["reason"]


@needs_ffmpeg
async def test_kaputte_datei_wird_abgelehnt(client, videos, tmp_path):
    await client.post("/api/dubbing/requests", json={"video_id": "en1"})
    job = (await client.post("/api/dubbing/claim", json={"worker": "mac"})).json()["request"]
    bad = tmp_path / "kaputt.m4a"
    bad.write_bytes(b"kein audio")
    with bad.open("rb") as fh:
        r = await client.post(f"/api/dubbing/requests/{job['id']}/result",
                              files={"file": ("kaputt.m4a", fh, "audio/mp4")})
    assert r.status_code == 422
    assert (await client.get("/api/videos/en1/audio-tracks")).json()["tracks"] == []
    assert (await dubbing.get(job["id"])).status == "working", "Auftrag bleibt offen"


@needs_ffmpeg
async def test_tonspur_loeschen(client, videos, tmp_path):
    track = await audio_tracks.store_track("en1", "de", _tone(tmp_path / "a.m4a"), suffix=".m4a")
    assert (await client.delete(f"/api/videos/en1/audio-tracks/{track.id}")).status_code == 200
    assert await audio_tracks.list_tracks("en1") == []

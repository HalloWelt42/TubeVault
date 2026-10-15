"""
Seite Nachvertonung: was sie aus der Warteliste ableitet.

Kontrakt:
- Die fünf Schritte eines laufenden Auftrags folgen allein aus Fortschritt
  und Notiz des Nachvertoners; unbekannte Notizen entscheidet der Fortschritt.
- Die Restzeit eines Schritts gibt es erst, wenn sein Tempo gemessen ist.
- Jeder Reiter zählt genau seine Aufträge; "Alle" zählt die laufenden mit,
  listet sie aber nicht (sie stehen als Karten darüber).
- Mit anderer Stimme neu vertonen: der Auftrag kommt ans Ende der
  Warteliste, die alte Tonspur bleibt, bis die neue sie ersetzt.
- Das Lebenszeichen des Nachvertoners kommt aus seinen Meldungen (Stimmen,
  Fortschritt einer Vertonung oder eines KI-Transkripts).
- Vorauswahl-Stimme und Untertitel-Vorauswahl sind Einstellungen.
"""
import shutil
import subprocess

import pytest

from app.routers import dubbing as dubbing_router
from app.services import audio_tracks, dubbing, dubbing_steps
from app.services.dubbing_steps import StepClock, activity, steps_for

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
    await set_setting("dub.processing_enabled", "true")   # Vertonen läuft (Standard: angehalten)
    for vid, lang in (("en1", "en"), ("en2", "en"), ("en3", "en"), ("fr1", "fr")):
        await test_db.execute(
            "INSERT INTO videos (id, title, status, language, duration) VALUES (?, ?, 'ready', ?, 600)",
            (vid, f"Titel {vid}", lang))


def _tone(path, seconds=2):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", f"sine=frequency=440:duration={seconds}", "-c:a", "aac", str(path)], check=True)
    return path


async def _request(test_db, video_id, status, voice="Zeit Stimme", minutes_ago=0):
    cursor = await test_db.execute(
        f"""INSERT INTO dub_requests (video_id, target_language, voice, status, created_at, finished_at)
            VALUES (?, 'de', ?, ?, datetime('now', '-{minutes_ago} minutes'),
                    CASE WHEN ? IN ('done', 'error', 'skipped', 'cancelled')
                         THEN datetime('now', '-{minutes_ago} minutes') END)""",
        (video_id, voice, status, status))
    return cursor.lastrowid


async def _track(test_db, video_id, voice, duration=40.0, minutes_ago=0):
    cursor = await test_db.execute(
        f"""INSERT INTO audio_tracks (video_id, language, origin, voice, file_path, duration, created_at)
            VALUES (?, 'de', 'dub', ?, '/x/de.m4a', ?, datetime('now', '-{minutes_ago} minutes'))""",
        (video_id, voice, duration))
    return cursor.lastrowid


# ─── Schritte ──────────────────────────────────────────────────────────

def _states(steps):
    return [(s.key, s.state, s.percent) for s in steps]


def test_schritt_nach_notiz_des_nachvertoners():
    loading = steps_for(0.02, "Video laden")
    assert _states(loading)[0] == ("fetch", "current", 11)
    assert all(s.state == "pending" for s in loading[1:])

    # Sprechen bei 62 % seines Abschnitts: Dienst-Anteil 0.45 + 0.45 * 0.62
    overall = 0.08 + 0.87 * (0.45 + 0.45 * 0.62)
    speaking = steps_for(overall, "Sprechen")
    assert [s.state for s in speaking] == ["done", "done", "done", "current", "pending"]
    assert speaking[3].label == "Sprechen" and speaking[3].percent == 62
    assert [s.percent for s in speaking if s.state != "current"] == [None] * 4

    # Die Notiz entscheidet, auch wenn der Fortschritt noch im Schritt davor liegt
    assert steps_for(0.30, "Übersetzen")[2].state == "current"
    assert steps_for(0.96, "Tonspur abliefern")[4].state == "current"
    assert steps_for(0.03, "Vorhandenes Transkript verwendet (Untertitel vom Autor)")[0].state == "current"


def test_unbekannte_notiz_entscheidet_der_fortschritt():
    assert steps_for(0.30, "Erkannte Sprache: french")[1].state == "current"
    assert steps_for(0.5, None)[3].state == "current"
    assert steps_for(0.0, None)[0].percent == 0
    # Außerhalb des Abschnitts wird begrenzt, nie über 100
    assert steps_for(0.99, "Sprechen")[3].percent == 100


def test_taetigkeit_nur_wenn_sie_mehr_sagt():
    assert activity("Sprechen", 0.6) is None
    assert activity("Video laden", 0.02) == "Video laden"
    assert activity(None, 0.5) is None


def test_restzeit_erst_mit_gemessenem_tempo():
    clock = StepClock()
    clock.observe(1, "t0", 0.50, "Sprechen", now=0)
    assert clock.remaining(1, "t0", 0.50, "Sprechen", now=10) is None, "noch kein Fortschritt"
    assert clock.remaining(1, "t0", 0.51, "Sprechen", now=20) is None, "zu kurz beobachtet"
    # 0.1 in 600 s, bis zum Ende des Schritts fehlen noch 0.863 - 0.6
    left = clock.remaining(1, "t0", 0.60, "Sprechen", now=600)
    end = dubbing_steps.STEPS[4].start
    assert left == round(600 / 0.1 * (end - 0.60))
    # Ein neuer Schritt misst neu; ein neu abgeholter Auftrag ebenso
    clock.observe(1, "t0", 0.87, "Zusammenfügen", now=700)
    assert clock.remaining(1, "t0", 0.87, "Zusammenfügen", now=700) is None
    assert clock.remaining(1, "t1", 0.60, "Sprechen", now=800) is None
    clock.keep_only(set())
    assert clock.remaining(1, "t0", 0.90, "Zusammenfügen", now=900) is None


# ─── Reiter und Liste ──────────────────────────────────────────────────

async def test_zaehlung_je_reiter(client, videos, test_db):
    await _request(test_db, "en1", "working")
    first_waiting = await _request(test_db, "en2", "queued", minutes_ago=10)
    second_waiting = await _request(test_db, "en3", "queued", minutes_ago=5)
    old_done = await _request(test_db, "fr1", "done", minutes_ago=60)
    new_done = await _request(test_db, "en1", "done", minutes_ago=1)
    failed = await _request(test_db, "en2", "error")
    await _request(test_db, "en3", "cancelled")

    overview = (await client.get("/api/dubbing/overview")).json()
    assert overview["tabs"] == {"all": 7, "working": 1, "queued": 2, "done": 2, "error": 1}
    assert overview["counts"]["cancelled"] == 1

    everything = (await client.get("/api/dubbing/requests?tab=all")).json()
    assert everything["total"] == 6, "laufende stehen als Karten darüber, nicht in der Liste"
    ids = [item["id"] for item in everything["items"]]
    assert ids[:5] == [first_waiting, second_waiting, new_done, old_done, failed], \
        "Wartende in Abholreihenfolge, dann Fertiges, das Neueste zuerst"
    assert [i["status"] for i in (await client.get("/api/dubbing/requests?tab=error")).json()["items"]] == ["error"]

    page = (await client.get("/api/dubbing/requests?tab=all&offset=2&limit=2")).json()
    assert [i["id"] for i in page["items"]] == [new_done, old_done] and page["total"] == 6
    assert (await client.get("/api/dubbing/requests?tab=unsinn")).status_code == 422


async def test_fertiger_auftrag_kennt_seine_tonspur(client, videos, test_db):
    done = await _request(test_db, "en1", "done")
    track = await _track(test_db, "en1", "Zeit Stimme")
    items = (await client.get("/api/dubbing/requests?tab=done")).json()["items"]
    assert items[0]["id"] == done and items[0]["track_id"] == track


# ─── Laufender Auftrag ─────────────────────────────────────────────────

async def test_uebersicht_zeigt_schritte_des_laufenden(client, videos):
    await client.post("/api/dubbing/requests", json={"video_id": "en1"})
    job = (await client.post("/api/dubbing/claim", json={"worker": "rechner"})).json()["request"]
    await client.post(f"/api/dubbing/requests/{job['id']}/progress", json={"progress": 0.40, "note": "Übersetzen"})

    running = (await client.get("/api/dubbing/overview")).json()["running"]
    assert len(running) == 1 and running[0]["request"]["id"] == job["id"]
    assert [s["state"] for s in running[0]["steps"]] == ["done", "done", "current", "pending", "pending"]
    assert running[0]["steps"][2]["percent"] == 48
    assert running[0]["activity"] is None and running[0]["step_remaining_seconds"] is None


# ─── Mit anderer Stimme neu vertonen ───────────────────────────────────

async def test_neu_vertonen_mit_anderer_stimme(client, videos, test_db):
    done = await _request(test_db, "en1", "done", voice="Zeit Stimme", minutes_ago=60)
    track = await _track(test_db, "en1", "Zeit Stimme")
    waiting = await _request(test_db, "en2", "queued", minutes_ago=30)

    same = (await client.post(f"/api/dubbing/requests/{done}/revoice", json={"voice": "Zeit Stimme"})).json()
    assert not same["queued"] and "schon gewählt" in same["reason"]

    again = (await client.post(f"/api/dubbing/requests/{done}/revoice", json={"voice": "Kerstin"})).json()
    assert again["queued"] and again["request"]["status"] == "queued"
    assert again["request"]["voice"] == "Kerstin" and again["request"]["track_id"] == track, \
        "die alte Tonspur bleibt abspielbar, bis die neue sie ersetzt"
    # Ans Ende der Warteliste: der länger wartende wird zuerst abgeholt
    assert (await client.post("/api/dubbing/claim", json={"worker": "rechner"})).json()["request"]["id"] == waiting
    assert (await client.post("/api/dubbing/claim", json={"worker": "rechner"})).json()["request"]["id"] == done

    busy = (await client.post(f"/api/dubbing/requests/{done}/revoice", json={"voice": "Bert"})).json()
    assert not busy["queued"] and "erst abbrechen" in busy["reason"]


async def test_neu_vertonen_wartend_und_doppelt(client, videos, test_db):
    waiting = await _request(test_db, "en1", "queued")
    changed = (await client.post(f"/api/dubbing/requests/{waiting}/revoice", json={"voice": "Bert"})).json()
    assert changed["queued"] and changed["request"]["voice"] == "Bert" and changed["request"]["status"] == "queued"

    failed = await _request(test_db, "en1", "error")
    twice = (await client.post(f"/api/dubbing/requests/{failed}/revoice", json={"voice": "Anna"})).json()
    assert not twice["queued"] and "vorgemerkt" in twice["reason"]
    assert (await client.post("/api/dubbing/requests/999/revoice", json={"voice": "Anna"})).json()["queued"] is False


@needs_ffmpeg
async def test_neue_stimme_ersetzt_die_tonspur(client, videos, tmp_path):
    await client.post("/api/dubbing/requests", json={"video_id": "en1", "voice": "Zeit Stimme"})

    async def deliver(voice):
        job = (await client.post("/api/dubbing/claim", json={"worker": "rechner"})).json()["request"]
        with _tone(tmp_path / "de.m4a").open("rb") as fh:
            r = await client.post(f"/api/dubbing/requests/{job['id']}/result",
                                  files={"file": ("de.m4a", fh, "audio/mp4")}, data={"voice": voice})
        assert r.status_code == 200, r.text
        return job["id"]

    request_id = await deliver("Zeit Stimme")
    await client.post(f"/api/dubbing/requests/{request_id}/revoice", json={"voice": "Kerstin"})
    assert await deliver("Kerstin") == request_id
    tracks = await audio_tracks.list_tracks("en1")
    assert [(t.language, t.voice) for t in tracks] == [("de", "Kerstin")], "eine Spur je Sprache, die neue"
    assert (await client.get("/api/dubbing/requests?tab=done")).json()["total"] == 1


# ─── Entfernen ─────────────────────────────────────────────────────────

async def test_entfernen_mit_und_ohne_tonspur(client, videos, test_db, tmp_path):
    keep = await _request(test_db, "en1", "done")
    await _track(test_db, "en1", "Zeit Stimme")
    assert (await client.delete(f"/api/dubbing/requests/{keep}")).status_code == 200
    assert len(await audio_tracks.list_tracks("en1")) == 1, "ohne Angabe bleibt die Tonspur"

    discard = await _request(test_db, "en2", "done")
    audio = tmp_path / "de.m4a"
    audio.write_bytes(b"x")
    await test_db.execute(
        "INSERT INTO audio_tracks (video_id, language, origin, file_path) VALUES ('en2', 'de', 'dub', ?)", (str(audio),))
    assert (await client.delete(f"/api/dubbing/requests/{discard}?with_track=true")).status_code == 200
    assert await audio_tracks.list_tracks("en2") == [] and not audio.exists()
    assert (await client.delete(f"/api/dubbing/requests/{discard}")).status_code == 404


# ─── Nachvertoner und Stimmen ──────────────────────────────────────────

async def test_lebenszeichen_des_nachvertoners(client, videos, test_db):
    assert (await dubbing.worker_presence()).last_seen is None
    await client.post("/api/dubbing/voices", json={"voices": ["Zeit Stimme"]})
    fresh = (await client.get("/api/dubbing/overview")).json()["worker"]
    assert fresh["online"] and fresh["seconds_ago"] < 60

    await test_db.execute("UPDATE dub_voices SET reported_at = datetime('now', '-3 days')")
    stale = await dubbing.worker_presence()
    assert not stale.online and stale.seconds_ago >= 3 * 86400 - 5

    # Ein KI-Transkript in Arbeit ist auch ein Lebenszeichen
    await test_db.execute(
        "INSERT INTO ai_transcriptions (video_id, status, heartbeat_at) VALUES ('en1', 'working', datetime('now'))")
    assert (await dubbing.worker_presence()).online


async def test_vorauswahl_stimme_ist_einstellung(client, videos, set_setting):
    await client.post("/api/dubbing/voices", json={"voices": ["Bert", "Zeit Stimme", "Kerstin"]})
    assert (await client.get("/api/dubbing/voices")).json()["default"] == "Zeit Stimme"
    await set_setting("dub.default_voice", "Kerstin")
    assert (await client.get("/api/dubbing/voices")).json()["default"] == "Kerstin"
    queued = (await client.post("/api/dubbing/requests", json={"video_id": "en1"})).json()
    assert queued["request"]["voice"] == "Kerstin"
    # Nicht mehr gemeldet: dann gilt wieder die Regel
    await client.post("/api/dubbing/voices", json={"voices": ["Bert", "Zeit Stimme"]})
    assert (await client.get("/api/dubbing/voices")).json()["default"] == "Zeit Stimme"


async def test_untertitel_vorauswahl_ist_einstellung(client, videos, set_setting):
    assert (await client.post("/api/dubbing/requests", json={"video_id": "en1"})).json()["request"]["subtitles"] == "any"
    await set_setting("dub.default_subtitles", "manual")
    assert (await client.post("/api/dubbing/requests", json={"video_id": "en2"})).json()["request"]["subtitles"] == "manual"
    chosen = (await client.post("/api/dubbing/requests", json={"video_id": "en3", "subtitles": "never"})).json()
    assert chosen["request"]["subtitles"] == "never", "je Video bleibt jede Wahl möglich"


async def test_hoerprobe_aus_fertiger_tonspur(client, videos, test_db):
    await client.post("/api/dubbing/voices", json={"voices": ["Zeit Stimme", "Kerstin"]})
    await _track(test_db, "en1", "Zeit Stimme", duration=40, minutes_ago=30)
    newest = await _track(test_db, "fr1", "Zeit Stimme", duration=100, minutes_ago=1)
    details = {d["name"]: d for d in (await client.get("/api/dubbing/voices")).json()["details"]}
    assert details["Zeit Stimme"]["dubs"] == 2
    assert details["Zeit Stimme"]["sample"] == {"video_id": "fr1", "track_id": newest, "start": 25.0}
    assert details["Kerstin"] == {"name": "Kerstin", "dubs": 0, "sample": None}, "ohne Tonspur keine Hörprobe"

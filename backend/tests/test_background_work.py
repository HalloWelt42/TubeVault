"""
Laufende Hintergrundarbeiten: sichtbar mit Stand, Laufzeit und Restdauer.
"""
import pytest

from app.services import background_work


@pytest.fixture(autouse=True)
def fresh():
    background_work._peak.clear()
    background_work._first_seen.clear()


async def test_nichts_laeuft(test_db):
    assert await background_work.overview() == []


async def test_typ_pruefung_mit_fortschritt(test_db):
    for n in range(4):
        await test_db.execute(
            "INSERT INTO videos (id, title, duration, video_type) VALUES (?, 'T', 30, 'video')",
            (f"abcdefghi{n:02d}",))
    first = (await background_work.overview())[0]
    assert (first.key, first.done, first.total) == ("type_check", 0, 4)
    assert first.eta_seconds == 8 and first.since

    await test_db.execute("UPDATE videos SET type_verified = 1 WHERE id = 'abcdefghi00'")
    second = (await background_work.overview())[0]
    assert (second.done, second.total, second.progress) == (1, 4, 0.25)


async def test_nachvertonung_in_arbeit(test_db, set_setting):
    await set_setting("dub.enabled", "true")
    await set_setting("dub.processing_enabled", "true")
    await test_db.execute(
        "INSERT INTO videos (id, title, status, type_verified) VALUES ('abcdefghijk', 'Ein Film', 'ready', 1)")
    await test_db.execute(
        "INSERT INTO dub_requests (video_id, target_language, status, progress, note, worker, claimed_at) "
        "VALUES ('abcdefghijk', 'de', 'working', 0.4, 'Übersetzen', 'Mac', datetime('now'))")
    await test_db.execute("INSERT INTO dub_requests (video_id, target_language) VALUES ('abcdefghijk', 'en')")
    item = (await background_work.overview())[0]
    assert item.label == "Nachvertonung: Ein Film"
    assert (item.progress, item.detail, item.waiting) == (0.4, "Übersetzen · Mac", 1)


async def test_ki_transkripte_mit_erledigt_und_restzeit(test_db):
    """Wunsch 15.10.2026: wie viel von wie viel erledigt, Restzeit aus der
    Dauer der zuletzt fertigen Aufträge."""
    for n in range(5):
        await test_db.execute(
            "INSERT INTO videos (id, title, status, download_date) VALUES (?, 'T', 'ready', datetime('now'))",
            (f"kivideo{n:04d}",))
    await test_db.execute(
        """INSERT INTO ai_transcriptions (video_id, status, claimed_at, finished_at) VALUES
           ('kivideo0000', 'done', datetime('now', '-30 minutes'), datetime('now', '-20 minutes')),
           ('kivideo0001', 'done', datetime('now', '-20 minutes'), datetime('now', '-10 minutes')),
           ('kivideo0002', 'working', datetime('now', '-1 minutes'), NULL)""")
    item = next(i for i in await background_work.overview() if i.key == "ai_transcripts")
    assert (item.done, item.total) == (2, 5)                 # 2 fertig, 1 läuft, 2 warten
    assert abs(item.eta_seconds - 3 * 600) < 5               # 3 offen zu je 10 Minuten


async def test_ki_transkripte_lassen_sich_anhalten(test_db, set_setting):
    """Wunsch 15.10.2026: auch die KI-Transkripte anhaltbar. Angehalten wird
    kein neues Video vergeben; die Zeile bleibt sichtbar, damit es weitergeht."""
    from app.services import transcripts
    for n in range(3):
        await test_db.execute(
            "INSERT INTO videos (id, title, status, download_date) VALUES (?, 'T', 'ready', datetime('now'))",
            (f"kivideo{n:04d}",))
    await set_setting("transcripts.ai_enabled", "false")
    assert await transcripts.claim_ai("mac") is None
    item = next(i for i in await background_work.overview() if i.key == "ai_transcripts")
    assert item.paused and item.switch_key == "transcripts.ai_enabled"
    assert (item.done, item.total) == (0, 3) and item.eta_seconds is None

    await set_setting("transcripts.ai_enabled", "true")
    assert (await transcripts.claim_ai("mac")).video_id.startswith("kivideo")

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


async def test_nachvertonung_in_arbeit(test_db):
    await test_db.execute(
        "INSERT INTO videos (id, title, status, type_verified) VALUES ('abcdefghijk', 'Ein Film', 'ready', 1)")
    await test_db.execute(
        "INSERT INTO dub_requests (video_id, target_language, status, progress, note, worker, claimed_at) "
        "VALUES ('abcdefghijk', 'de', 'working', 0.4, 'Übersetzen', 'Mac', datetime('now', 'localtime'))")
    await test_db.execute("INSERT INTO dub_requests (video_id, target_language) VALUES ('abcdefghijk', 'en')")
    item = (await background_work.overview())[0]
    assert item.label == "Nachvertonung: Ein Film"
    assert (item.progress, item.detail, item.waiting) == (0.4, "Übersetzen · Mac", 1)

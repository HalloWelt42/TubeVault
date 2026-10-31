"""
Videoliste: Nachladen ab Cursor statt ab Versatz (HELF-71).

Kontrakt:
- Wer mit next_cursor blättert, bekommt jede Seite direkt hinter der letzten,
  in derselben Reihenfolge wie ohne Cursor, für jede Sortierung und Richtung,
  auch bei Gleichstand und NULL-Werten.
- Fällt zwischen zwei Seiten etwas aus der Trefferliste (archiviert), fehlt
  dahinter kein Video; kommt etwas hinzu, erscheint nichts doppelt.
- Am Ende ist next_cursor leer; ein fremder oder kaputter Cursor gibt 400.
"""
import pytest

from app.services.metadata_service import metadata_service

SORTS = ["created_at", "upload_date", "title", "duration", "rating", "play_count", "file_size",
         "channel_name", "is_favorite"]


@pytest.fixture
async def bestand(test_db):
    # Absichtlich viele Gleichstände und NULL-Werte: dieselbe Ladezeit, fehlende Upload-Daten, gleiche Titel
    for i in range(53):
        await test_db.execute(
            "INSERT INTO videos (id, title, status, channel_name, duration, upload_date, rating, play_count, "
            "file_size, created_at) VALUES (?, ?, 'ready', ?, ?, ?, ?, ?, ?, ?)",
            (f"vid{i:08d}", f"Titel {i % 7}", None if i % 5 == 0 else f"Kanal {i % 3}",
             None if i % 4 == 0 else 60 * (i % 6), None if i % 3 == 0 else f"2026-0{1 + i % 9}-01",
             i % 4, i % 2, None if i % 6 == 0 else 1000 * (i % 5), f"2026-10-{1 + i % 4:02d} 12:00:00"))
    for i in range(0, 53, 9):
        await test_db.execute("INSERT INTO favorites (video_id) VALUES (?)", (f"vid{i:08d}",))


async def _alle_mit_cursor(per_page=10, zwischendurch=None, **filter_):
    seite = await metadata_service.get_videos(per_page=per_page, **filter_)
    ids, runde = [v["id"] for v in seite["videos"]], 0
    while seite["next_cursor"]:
        if zwischendurch:
            await zwischendurch(runde, ids)
        runde += 1
        seite = await metadata_service.get_videos(per_page=per_page, after=seite["next_cursor"], **filter_)
        ids += [v["id"] for v in seite["videos"]]
    return ids


@pytest.mark.parametrize("sort_by", SORTS)
@pytest.mark.parametrize("sort_order", ["desc", "asc"])
async def test_cursor_blaettert_wie_eine_einzige_seite(bestand, sort_by, sort_order):
    ganz = [v["id"] for v in (await metadata_service.get_videos(per_page=100, sort_by=sort_by,
                                                                 sort_order=sort_order))["videos"]]
    assert len(ganz) == 53
    assert await _alle_mit_cursor(sort_by=sort_by, sort_order=sort_order) == ganz


async def test_archivieren_zwischen_den_seiten_verliert_nichts(bestand, test_db):
    """Wie in der Bibliothek: beim Rollen wird je Seite ein schon gezeigtes Video archiviert."""
    vorher = {v["id"] for v in (await metadata_service.get_videos(per_page=100, is_archived=False))["videos"]}

    async def archivieren(runde, gezeigt):
        await test_db.execute("UPDATE videos SET is_archived = 1 WHERE id = ?", (gezeigt[runde],))

    ids = await _alle_mit_cursor(zwischendurch=archivieren, is_archived=False, sort_by="created_at")
    assert set(ids) == vorher and len(ids) == len(set(ids))


async def test_neue_videos_zwischen_den_seiten_kommen_nicht_doppelt(bestand, test_db):
    async def neu(runde, gezeigt):
        await test_db.execute("INSERT INTO videos (id, title, status, created_at) VALUES (?, 'Neu', 'ready', "
                              "'2026-12-01 00:00:00')", (f"neu{runde:08d}",))

    ids = await _alle_mit_cursor(zwischendurch=neu, sort_by="created_at")
    assert len(ids) == len(set(ids)) == 53


async def test_versatz_verliert_beim_archivieren_den_naechsten(bestand, test_db):
    """Gegenprobe: so verlor die Bibliothek bisher Kacheln (Seite per Versatz)."""
    erste = [v["id"] for v in (await metadata_service.get_videos(page=1, per_page=10, is_archived=False,
                                                                  sort_by="created_at"))["videos"]]
    await test_db.execute("UPDATE videos SET is_archived = 1 WHERE id = ?", (erste[0],))
    zweite = [v["id"] for v in (await metadata_service.get_videos(page=2, per_page=10, is_archived=False,
                                                                   sort_by="created_at"))["videos"]]
    ganz = [v["id"] for v in (await metadata_service.get_videos(per_page=100, is_archived=False,
                                                                 sort_by="created_at"))["videos"]]
    assert ganz[9] not in erste + zweite      # das erste Video der zweiten Seite rutschte auf Seite 1 und fehlt


async def test_ende_und_falscher_cursor(bestand):
    from app.services import keyset
    letzte = await metadata_service.get_videos(per_page=100)
    assert letzte["next_cursor"] is None
    cursor = (await metadata_service.get_videos(per_page=5, sort_by="title"))["next_cursor"]
    with pytest.raises(keyset.CursorError):
        await metadata_service.get_videos(per_page=5, sort_by="duration", after=cursor)
    with pytest.raises(keyset.CursorError):
        await metadata_service.get_videos(per_page=5, after="kaputt!")
    assert "_key0" not in (await metadata_service.get_videos(per_page=5))["videos"][0]

"""
Mitgeladene Untertitel einlesen (app/services/subtitle_import).

Kontrakt:
- je Video eine Datei: vom Autor in der Videosprache, sonst automatisch im
  Original, sonst automatisch in der Videosprache, sonst irgendeine
- als gesprochene Sprache zählt nur, was die Datei belegt
- eingelesene Abschnitte sind per Wort auffindbar, bekommen aber keine Vektoren
- ohne lesbare Datei wird das Video vermerkt und nicht wieder versucht
"""
import pytest

from app.services import semantic_index, subtitle_import, transcripts
from app.services.search import engine
from app.services.search.filters import SearchFilters

VTT = "WEBVTT\n\n00:00:05.000 --> 00:00:09.000\n{text}\n"


def test_wahl_der_datei():
    choose = subtitle_import.choose
    assert choose(["a.de.vtt", "de.vtt", "a.en.vtt"], "de").name == "de.vtt"
    pick = choose(["a.de.vtt", "a.en-orig.vtt"], "de")
    assert (pick.name, pick.language, pick.kind, pick.spoken) == ("a.en-orig.vtt", "en", "auto", True)
    pick = choose(["a.de.vtt"], "de")
    assert pick.spoken is True
    pick = choose(["de-DE.vtt"], "en")                      # Autor, aber andere Sprache: vielleicht übersetzt
    assert (pick.language, pick.kind, pick.spoken) == ("de", "manual", False)
    assert choose(["ki.de.vtt", "notizen.txt"], "de") is None


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(subtitle_import, "SUBTITLES_DIR", tmp_path)
    monkeypatch.setattr(transcripts, "SUBTITLES_DIR", tmp_path)
    return tmp_path


async def _video(db, video_id, language="de"):
    await db.execute("INSERT INTO videos (id, title, status, language, download_date) VALUES (?, 'Werkstatt', 'ready', ?, ?)",
                     (video_id, language, f"2026-01-0{video_id[-1]} 00:00:00"))


async def test_einlesen_macht_gesagtes_durchsuchbar(test_db, folder, set_setting):
    await _video(test_db, "sub00000001")
    await _video(test_db, "sub00000002")
    (folder / "sub00000001").mkdir()
    (folder / "sub00000001" / "a.de-orig.vtt").write_text(VTT.format(text="Jetzt kommt die Lötspitze."), encoding="utf-8")
    (folder / "sub00000002").mkdir()                       # leerer Ordner

    assert await subtitle_import.pending_ids() == ["sub00000002", "sub00000001"]
    assert await subtitle_import.run_batch() == 2
    assert await subtitle_import.pending_ids() == []

    page = await engine.section("gesagt", "Lötspitze", SearchFilters())
    assert [item.id for item in page.items] == ["sub00000001"]
    assert page.items[0].spots[0].start == 5.0 and page.items[0].spots[0].origin == "auto"
    row = await test_db.fetch_one("SELECT status, kind, imported, spoken, note FROM transcripts WHERE video_id = 'sub00000001'")
    assert tuple(row) == ("ok", "auto", 1, 1, "a.de-orig.vtt")
    assert await test_db.fetch_val("SELECT status FROM transcripts WHERE video_id = 'sub00000002'") == "none"

    # Werbestellen nachziehen liest dieselbe Datei wieder
    assert await transcripts.rebuild("sub00000001") == 1

    # Keine Vektoren für eingelesene Abschnitte
    await set_setting("ai.enabled", "true")
    await set_setting("ai.url", "http://ki.test/v1")
    _, model = await semantic_index.config()
    assert await semantic_index.pending_chunks(model) == 0


async def test_angehalten_liest_nichts(test_db, folder, set_setting):
    await set_setting(subtitle_import.SWITCH, "false")
    await _video(test_db, "sub00000003")
    (folder / "sub00000003").mkdir()
    (folder / "sub00000003" / "de.vtt").write_text(VTT.format(text="Hallo."), encoding="utf-8")
    assert await subtitle_import.run_batch() == 0
    assert await subtitle_import.remaining() == 1
    subtitle_import._queue.clear()

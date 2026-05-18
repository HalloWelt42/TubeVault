"""
Text-Resolver Tests (Phase 3a – Read-Pfad).

Kontrakt von get_description():
- File vorhanden        → Datei-Inhalt
- nur DB                → DB-Inhalt (Fallback)
- File leer, DB gefüllt → DB-Inhalt (leer = wie nicht da)
- File und DB leer      → None
- kein Video vorhanden  → None
- File hat Vorrang vor DB wenn beide unterschiedlich
"""
import pytest

from app.services.text_resolver import get_description, has_description


@pytest.fixture
async def video_row(test_db):
    await test_db.execute(
        "INSERT INTO videos (id, title, description) VALUES (?, ?, ?)",
        ("res_vid", "T", "DB-Inhalt"),
    )
    return "res_vid"


async def test_file_is_primary_source(test_db, video_row, tmp_path, monkeypatch):
    """File vorhanden → Datei-Inhalt, auch wenn DB was Anderes hat."""
    from app.services import text_export as te
    monkeypatch.setattr(te, "TEXTS_DIR", tmp_path)

    vd = tmp_path / video_row
    vd.mkdir()
    (vd / "description.txt").write_text("Aus-Datei")

    result = await get_description(video_row)
    assert result == "Aus-Datei"


async def test_db_is_fallback_when_file_missing(test_db, video_row, tmp_path, monkeypatch):
    """Keine Datei → DB-Spalte liefern."""
    from app.services import text_export as te
    monkeypatch.setattr(te, "TEXTS_DIR", tmp_path)

    result = await get_description(video_row)
    assert result == "DB-Inhalt"


async def test_empty_file_falls_back_to_db(test_db, video_row, tmp_path, monkeypatch):
    """Leere Datei (Grenze) → DB-Fallback statt leerem String zurück."""
    from app.services import text_export as te
    monkeypatch.setattr(te, "TEXTS_DIR", tmp_path)

    vd = tmp_path / video_row
    vd.mkdir()
    (vd / "description.txt").write_text("")

    result = await get_description(video_row)
    assert result == "DB-Inhalt"


async def test_returns_none_when_nothing(test_db, tmp_path, monkeypatch):
    """Kein Video, keine Datei → None."""
    from app.services import text_export as te
    monkeypatch.setattr(te, "TEXTS_DIR", tmp_path)

    result = await get_description("gibts_nicht")
    assert result is None


async def test_returns_none_when_db_empty_and_no_file(test_db, tmp_path, monkeypatch):
    """Video da, aber description=NULL und keine Datei → None."""
    from app.services import text_export as te
    monkeypatch.setattr(te, "TEXTS_DIR", tmp_path)
    await test_db.execute(
        "INSERT INTO videos (id, title, description) VALUES (?, ?, NULL)",
        ("empty_vid", "T"),
    )
    assert await get_description("empty_vid") is None


async def test_resolver_does_not_modify_db(test_db, video_row, tmp_path, monkeypatch):
    """SAFETY: Resolver ist read-only, auch beim Fallback-Pfad."""
    from app.services import text_export as te
    monkeypatch.setattr(te, "TEXTS_DIR", tmp_path)

    before = await test_db.fetch_one(
        "SELECT description FROM videos WHERE id=?", (video_row,)
    )
    await get_description(video_row)       # DB-Fallback
    await get_description(video_row)       # zweimal

    after = await test_db.fetch_one(
        "SELECT description FROM videos WHERE id=?", (video_row,)
    )
    assert before["description"] == after["description"]


async def test_resolver_does_not_write_file(test_db, video_row, tmp_path, monkeypatch):
    """SAFETY: Resolver legt keine Datei an, wenn nur DB etwas hat."""
    from app.services import text_export as te
    monkeypatch.setattr(te, "TEXTS_DIR", tmp_path)

    await get_description(video_row)
    # Datei darf NICHT entstanden sein – Self-Heal ist explizit aus
    assert not (tmp_path / video_row / "description.txt").exists()


async def test_has_description_checks_both_sources(test_db, video_row, tmp_path, monkeypatch):
    from app.services import text_export as te
    monkeypatch.setattr(te, "TEXTS_DIR", tmp_path)

    assert await has_description(video_row) is True
    assert await has_description("gibts_nicht") is False

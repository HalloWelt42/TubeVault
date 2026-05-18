"""
FTS5-Rebuild-Tests (Phase 3a – Such-Pfad).

Kontrakt:
- fts_rebuild_from_resolver() holt description aus text_resolver
  (File-first) und baut den Index komplett neu.
- Suche via fts_search funktioniert nach Rebuild, auch wenn die DB-Spalte
  videos.description leer ist (weil der Inhalt aus der Datei kommt).
"""
import pytest


@pytest.fixture
async def search_video(test_db):
    await test_db.execute(
        "INSERT INTO videos (id, title, channel_name, status, description) "
        "VALUES (?, ?, ?, 'ready', ?)",
        ("fts_vid", "Titel", "Kanal", "Apfelstrudel mit Vanillesauce"),
    )
    return "fts_vid"


async def test_rebuild_populates_fts_from_file(
    test_db, search_video, tmp_path, monkeypatch
):
    """DB leer, Datei gefüllt → Rebuild macht Inhalt findbar."""
    from app.services import text_export as te
    monkeypatch.setattr(te, "TEXTS_DIR", tmp_path)

    # DB-Spalte simulieren wir als geleert
    await test_db.execute(
        "UPDATE videos SET description = NULL WHERE id = ?", (search_video,)
    )
    # Datei schreiben mit eindeutigem Suchbegriff
    vd = tmp_path / search_video
    vd.mkdir()
    (vd / "description.txt").write_text(
        "Apfelstrudel mit Vanillesauce – altes Rezept aus 1890"
    )

    stats = await test_db.fts_rebuild_from_resolver()
    assert stats["rebuilt"] >= 1

    # Suchbegriff aus dem FILE-Inhalt muss Hit geben
    hits = await test_db.fts_search("Apfelstrudel")
    assert any(h["id"] == search_video for h in hits), (
        "FTS muss Videos finden, deren description nur in der Datei steht"
    )


async def test_rebuild_uses_file_over_db(
    test_db, search_video, tmp_path, monkeypatch
):
    """Beide gefüllt → Datei gewinnt (File-first)."""
    from app.services import text_export as te
    monkeypatch.setattr(te, "TEXTS_DIR", tmp_path)

    # DB hat altes, Datei hat neues
    await test_db.execute(
        "UPDATE videos SET description = ? WHERE id = ?",
        ("ALT-TEXT", search_video),
    )
    vd = tmp_path / search_video
    vd.mkdir()
    (vd / "description.txt").write_text("NEU-TEXT Quantenverschränkung")

    await test_db.fts_rebuild_from_resolver()

    hits_new = await test_db.fts_search("Quantenverschränkung")
    assert any(h["id"] == search_video for h in hits_new), "FTS nutzt File-Inhalt"


async def test_rebuild_skips_non_ready_videos(test_db, tmp_path, monkeypatch):
    """Nur status='ready' wird indexiert."""
    from app.services import text_export as te
    monkeypatch.setattr(te, "TEXTS_DIR", tmp_path)

    await test_db.execute(
        "INSERT INTO videos (id, title, status, description) VALUES (?, ?, ?, ?)",
        ("pending_vid", "T", "pending", "Uniquekeyword12345"),
    )
    await test_db.fts_rebuild_from_resolver()
    hits = await test_db.fts_search("Uniquekeyword12345")
    assert not any(h["id"] == "pending_vid" for h in hits)

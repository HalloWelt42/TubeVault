"""
Write-Hook-Tests (Phase 3a – Teil 2).

Nach jedem Schreib-Pfad auf videos.description MUSS die Text-Datei
automatisch aktualisiert werden. Kontrakt:

- metadata_service.update_video({description:..}) schreibt Datei sofort
- update ohne description-Key fasst die Datei NICHT an
- leerer description-String schreibt keine Datei (konsistent zu export)

Die Download-Pfade (download_service, own_videos) rufen dieselbe
export_description() auf, das ist in test_text_export.py abgedeckt.
Hier steht der User-Pfad über das Edit-Panel im Fokus.
"""
import pytest

from app.services.metadata_service import metadata_service


@pytest.fixture
async def video_with_desc(test_db):
    await test_db.execute(
        "INSERT INTO videos (id, title, description, status) VALUES (?, ?, ?, ?)",
        ("wh_vid", "Test", "Alte Beschreibung", "ready"),
    )
    return "wh_vid"


async def test_update_video_writes_description_to_file(
    test_db, video_with_desc, tmp_path, monkeypatch
):
    """Kernkontrakt: update_video mit neuer description schreibt die Datei."""
    from app.services import text_export as te_mod
    monkeypatch.setattr(te_mod, "TEXTS_DIR", tmp_path)

    await metadata_service.update_video(
        video_with_desc, {"description": "Neuer Text aus dem UI"}
    )

    file = tmp_path / video_with_desc / "description.txt"
    assert file.exists(), "Write-Hook muss Datei anlegen"
    assert file.read_text() == "Neuer Text aus dem UI"


async def test_update_video_without_description_leaves_file_untouched(
    test_db, video_with_desc, tmp_path, monkeypatch
):
    """Negativer Kontrakt: update ohne description-Key schreibt keine Datei."""
    from app.services import text_export as te_mod
    monkeypatch.setattr(te_mod, "TEXTS_DIR", tmp_path)

    await metadata_service.update_video(video_with_desc, {"title": "Neuer Titel"})

    file = tmp_path / video_with_desc / "description.txt"
    assert not file.exists(), (
        "Nur Title-Update darf description-Datei nicht triggern"
    )


async def test_update_video_description_overwrites_existing_file(
    test_db, video_with_desc, tmp_path, monkeypatch
):
    """Bereits vorhandene Datei wird bei description-Update überschrieben."""
    from app.services import text_export as te_mod
    monkeypatch.setattr(te_mod, "TEXTS_DIR", tmp_path)

    # Erstes Update → Datei entsteht
    await metadata_service.update_video(video_with_desc, {"description": "v1"})
    file = tmp_path / video_with_desc / "description.txt"
    assert file.read_text() == "v1"

    # Zweites Update → Datei bekommt neuen Inhalt
    await metadata_service.update_video(video_with_desc, {"description": "v2"})
    assert file.read_text() == "v2"

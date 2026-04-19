"""
Text-Export Tests (Phase 3a – Daten aus DB in Dateien auslagern).

Kontrakt des Export-Services:
- schreibt Datei <video_id>.<kind>.<ext> in TEXTS_DIR
- registriert Metadata (size, sha256, synced_at) in text_files-Tabelle
- idempotent: gleicher Content → kein Write, kein Timestamp-Update
- verändertes DB-Feld → neuer Hash, File wird überschrieben
- leeres/None-Feld → kein File, kein Registry-Eintrag
- Restore: aus File zurück in DB lesen
"""
import hashlib
from pathlib import Path

import pytest

from app.services.text_export import (
    export_description,
    export_all_descriptions,
    read_description_from_file,
    get_export_overview,
)


@pytest.fixture
async def video_row(test_db):
    """Fügt ein Test-Video in videos-Tabelle ein."""
    await test_db.execute(
        "INSERT INTO videos (id, title, description) VALUES (?, ?, ?)",
        ("vidABC", "Test-Titel", "Das ist die Beschreibung.\nZweite Zeile."),
    )
    return "vidABC"


async def test_export_writes_file(test_db, video_row, tmp_path, monkeypatch):
    # Override TEXTS_DIR auf tmp
    from app.services import text_export as mod
    monkeypatch.setattr(mod, "TEXTS_DIR", tmp_path)

    result = await export_description(video_row)

    assert result is not None
    expected_file = tmp_path / f"{video_row}.description.txt"
    assert expected_file.exists()
    assert expected_file.read_text() == "Das ist die Beschreibung.\nZweite Zeile."


async def test_export_registers_in_db(test_db, video_row, tmp_path, monkeypatch):
    from app.services import text_export as mod
    monkeypatch.setattr(mod, "TEXTS_DIR", tmp_path)

    await export_description(video_row)

    row = await test_db.fetch_one(
        "SELECT * FROM text_files WHERE video_id=? AND kind='description'",
        (video_row,),
    )
    assert row is not None
    assert row["filename"] == f"{video_row}.description.txt"
    assert row["size_bytes"] > 0
    assert len(row["sha256"]) == 64  # hex-length
    assert row["synced_at"] is not None


async def test_export_idempotent(test_db, video_row, tmp_path, monkeypatch):
    """Zweiter Export mit identischem Content → keine Neu-Schreibung.
    r1.skipped=False (erst geschrieben), r2.skipped=True (keine Änderung)."""
    from app.services import text_export as mod
    monkeypatch.setattr(mod, "TEXTS_DIR", tmp_path)

    r1 = await export_description(video_row)
    first_synced = (await test_db.fetch_one(
        "SELECT synced_at FROM text_files WHERE video_id=?", (video_row,)
    ))["synced_at"]

    # Zweiter Export – erkennt via sha256 dass identisch ist
    r2 = await export_description(video_row)
    second_synced = (await test_db.fetch_one(
        "SELECT synced_at FROM text_files WHERE video_id=?", (video_row,)
    ))["synced_at"]

    assert r1["skipped"] is False
    assert r2["skipped"] is True
    # File + Hash stabil
    assert r1["filename"] == r2["filename"]
    assert r1["sha256"] == r2["sha256"]
    assert r1["size"] == r2["size"]
    # Timestamp darf sich nicht ändern (Idempotenz)
    assert first_synced == second_synced


async def test_export_rewrites_when_content_changes(test_db, video_row, tmp_path, monkeypatch):
    from app.services import text_export as mod
    monkeypatch.setattr(mod, "TEXTS_DIR", tmp_path)

    await export_description(video_row)
    hash1 = (await test_db.fetch_one(
        "SELECT sha256 FROM text_files WHERE video_id=?", (video_row,)
    ))["sha256"]

    # Beschreibung in DB ändern
    await test_db.execute(
        "UPDATE videos SET description=? WHERE id=?",
        ("Geänderter Text", video_row),
    )
    await export_description(video_row)

    hash2 = (await test_db.fetch_one(
        "SELECT sha256 FROM text_files WHERE video_id=?", (video_row,)
    ))["sha256"]
    assert hash1 != hash2

    file = tmp_path / f"{video_row}.description.txt"
    assert file.read_text() == "Geänderter Text"


async def test_export_skips_empty_description(test_db, tmp_path, monkeypatch):
    """Video ohne/mit leerer description → keine Datei, kein Registry-Eintrag."""
    from app.services import text_export as mod
    monkeypatch.setattr(mod, "TEXTS_DIR", tmp_path)

    await test_db.execute(
        "INSERT INTO videos (id, title, description) VALUES (?, ?, ?)",
        ("emptyvid", "Leer", ""),
    )
    r = await export_description("emptyvid")
    assert r is None
    assert not (tmp_path / "emptyvid.description.txt").exists()
    row = await test_db.fetch_one(
        "SELECT * FROM text_files WHERE video_id='emptyvid'"
    )
    assert row is None


async def test_export_all_reports_counts(test_db, tmp_path, monkeypatch):
    """Batch-Export gibt Statistik: {written, skipped, errors}."""
    from app.services import text_export as mod
    monkeypatch.setattr(mod, "TEXTS_DIR", tmp_path)

    for i in range(3):
        await test_db.execute(
            "INSERT INTO videos (id, title, description) VALUES (?, ?, ?)",
            (f"v{i}", f"Titel {i}", f"Beschreibung {i}" if i > 0 else ""),
        )

    stats = await export_all_descriptions()
    assert stats["written"] == 2   # v1, v2 (v0 hat leere description)
    assert stats["skipped"] == 1   # v0 leer
    assert stats["errors"] == 0


async def test_read_from_file_restores_content(test_db, tmp_path, monkeypatch):
    """Reverse-Pfad: File lesen, in DB zurueckschreiben."""
    from app.services import text_export as mod
    monkeypatch.setattr(mod, "TEXTS_DIR", tmp_path)

    # DB leer, File existiert
    await test_db.execute(
        "INSERT INTO videos (id, title) VALUES (?, ?)", ("restore1", "x"),
    )
    file = tmp_path / "restore1.description.txt"
    file.write_text("Restauriert aus Datei")

    content = await read_description_from_file("restore1")
    assert content == "Restauriert aus Datei"


async def test_overview_shows_counts(test_db, tmp_path, monkeypatch):
    """Overview fuer Frontend-Tabelle."""
    from app.services import text_export as mod
    monkeypatch.setattr(mod, "TEXTS_DIR", tmp_path)

    # 3 Videos, 1 mit Beschreibung, 0 exportiert
    for i in range(3):
        await test_db.execute(
            "INSERT INTO videos (id, title, description) VALUES (?, ?, ?)",
            (f"ov{i}", f"T{i}", "x" if i == 0 else ""),
        )
    ov = await get_export_overview()
    assert ov["description"]["in_db"] == 1    # nur ov0 hat text
    assert ov["description"]["as_file"] == 0
    assert ov["description"]["pending"] == 1

    # Nach Export: pending=0, as_file=1
    await export_description("ov0")
    ov2 = await get_export_overview()
    assert ov2["description"]["as_file"] == 1
    assert ov2["description"]["pending"] == 0

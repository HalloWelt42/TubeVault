"""
Chapters-Export Tests (Phase 3b).

Kontrakt:
- export_chapters schreibt JSON-Array-Datei chapters.json
- Idempotent via sha256 (wiederholter Call → skip)
- Leere Chapter-Liste → keine Datei, kein Registry-Eintrag
- Inhalt enthält title/start_time/end_time/source, kein thumbnail_url
- read_chapters_from_file gibt Array zurück
- Resolver get_chapters: File-first, DB-Fallback
- Write-Hook (via chapters-Router): neuer/geänderter Chapter synchronisiert Datei
"""
import json

import pytest
from httpx import AsyncClient, ASGITransport

from app.services.text_export import (
    export_chapters,
    read_chapters_from_file,
    delete_chapters_export,
    get_export_overview,
)
from app.services.text_resolver import get_chapters


@pytest.fixture
async def video_with_chapters(test_db):
    await test_db.execute(
        "INSERT INTO videos (id, title, status) VALUES (?, ?, 'ready')",
        ("ch_vid", "T"),
    )
    # Drei Kapitel einfügen
    for i, (t, s, e) in enumerate([
        ("Intro", 0, 60),
        ("Main", 60, 600),
        ("Outro", 600, 720),
    ]):
        await test_db.execute(
            """INSERT INTO chapters (video_id, title, start_time, end_time, source)
               VALUES (?, ?, ?, ?, 'youtube')""",
            ("ch_vid", t, s, e),
        )
    return "ch_vid"


async def test_export_writes_json_array(test_db, video_with_chapters, tmp_path, monkeypatch):
    from app.services import text_export as mod
    monkeypatch.setattr(mod, "TEXTS_DIR", tmp_path)

    r = await export_chapters(video_with_chapters)
    assert r is not None
    f = tmp_path / video_with_chapters / "chapters.json"
    assert f.exists()

    data = json.loads(f.read_text())
    assert isinstance(data, list) and len(data) == 3
    assert data[0]["title"] == "Intro"
    assert data[0]["start_time"] == 0
    assert data[0]["end_time"] == 60
    # Sortiert nach start_time
    assert [c["title"] for c in data] == ["Intro", "Main", "Outro"]
    # thumbnail_url bewusst NICHT persistiert (Implementation-Detail)
    assert "thumbnail_url" not in data[0]


async def test_export_idempotent(test_db, video_with_chapters, tmp_path, monkeypatch):
    from app.services import text_export as mod
    monkeypatch.setattr(mod, "TEXTS_DIR", tmp_path)

    r1 = await export_chapters(video_with_chapters)
    r2 = await export_chapters(video_with_chapters)
    assert r1["skipped"] is False
    assert r2["skipped"] is True
    assert r1["sha256"] == r2["sha256"]


async def test_export_rewrites_on_change(test_db, video_with_chapters, tmp_path, monkeypatch):
    from app.services import text_export as mod
    monkeypatch.setattr(mod, "TEXTS_DIR", tmp_path)

    await export_chapters(video_with_chapters)
    # Ein Kapitel umbenennen
    await test_db.execute(
        "UPDATE chapters SET title = ? WHERE video_id = ? AND title = ?",
        ("Einführung", video_with_chapters, "Intro"),
    )
    r = await export_chapters(video_with_chapters)
    assert r["skipped"] is False

    data = json.loads((tmp_path / video_with_chapters / "chapters.json").read_text())
    assert data[0]["title"] == "Einführung"


async def test_export_skips_video_without_chapters(test_db, tmp_path, monkeypatch):
    from app.services import text_export as mod
    monkeypatch.setattr(mod, "TEXTS_DIR", tmp_path)

    await test_db.execute(
        "INSERT INTO videos (id, title, status) VALUES (?, ?, 'ready')",
        ("no_ch", "T"),
    )
    r = await export_chapters("no_ch")
    assert r is None
    assert not (tmp_path / "no_ch" / "chapters.json").exists()


async def test_resolver_file_first(test_db, video_with_chapters, tmp_path, monkeypatch):
    """Datei hat Vorrang vor DB (auch wenn DB was Anderes hat)."""
    from app.services import text_export as mod
    monkeypatch.setattr(mod, "TEXTS_DIR", tmp_path)

    # File mit einem eigenen Kapitel hinschreiben
    d = tmp_path / video_with_chapters
    d.mkdir()
    (d / "chapters.json").write_text(json.dumps(
        [{"title": "FILE-ONLY", "start_time": 0, "end_time": 10, "source": "manual"}]
    ))

    result = await get_chapters(video_with_chapters)
    assert len(result) == 1
    assert result[0]["title"] == "FILE-ONLY"


async def test_resolver_db_fallback(test_db, video_with_chapters, tmp_path, monkeypatch):
    """Keine Datei → DB-Fallback liefert 3 Chapters."""
    from app.services import text_export as mod
    monkeypatch.setattr(mod, "TEXTS_DIR", tmp_path)

    result = await get_chapters(video_with_chapters)
    assert len(result) == 3
    titles = [c["title"] for c in result]
    assert "Intro" in titles


async def test_resolver_none_when_empty(test_db, tmp_path, monkeypatch):
    from app.services import text_export as mod
    monkeypatch.setattr(mod, "TEXTS_DIR", tmp_path)
    assert await get_chapters("gibts_nicht") is None


async def test_delete_removes_file_and_registry(test_db, video_with_chapters, tmp_path, monkeypatch):
    from app.services import text_export as mod
    monkeypatch.setattr(mod, "TEXTS_DIR", tmp_path)

    await export_chapters(video_with_chapters)
    f = tmp_path / video_with_chapters / "chapters.json"
    assert f.exists()

    deleted = await delete_chapters_export(video_with_chapters)
    assert deleted is True
    assert not f.exists()
    reg = await test_db.fetch_one(
        "SELECT * FROM text_files WHERE video_id=? AND kind='chapters'",
        (video_with_chapters,),
    )
    assert reg is None


async def test_overview_includes_chapters(test_db, video_with_chapters, tmp_path, monkeypatch):
    from app.services import text_export as mod
    monkeypatch.setattr(mod, "TEXTS_DIR", tmp_path)

    ov = await get_export_overview()
    assert "chapters" in ov
    assert ov["chapters"]["in_db"] == 1
    assert ov["chapters"]["as_file"] == 0
    assert ov["chapters"]["pending"] == 1

    await export_chapters(video_with_chapters)
    ov2 = await get_export_overview()
    assert ov2["chapters"]["as_file"] == 1
    assert ov2["chapters"]["pending"] == 0


# ─── Write-Hook über HTTP-Router ──────────────────────────────────

async def test_add_chapter_syncs_file(test_db, video_with_chapters, tmp_path, monkeypatch, make_test_app):
    """POST /api/chapters/{video_id} → Datei wird sofort aktualisiert."""
    from app.services import text_export as mod
    monkeypatch.setattr(mod, "TEXTS_DIR", tmp_path)

    from app.routers.chapters import router as chapters_router
    app = make_test_app(chapters_router)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post(
            f"/api/chapters/{video_with_chapters}",
            json={"title": "Neu", "start_time": 1000},
        )
        assert r.status_code == 200

    f = tmp_path / video_with_chapters / "chapters.json"
    assert f.exists()
    data = json.loads(f.read_text())
    assert any(c["title"] == "Neu" for c in data)


async def test_delete_all_chapters_removes_file(test_db, video_with_chapters, tmp_path, monkeypatch, make_test_app):
    """DELETE /api/chapters/{video_id}/all → Datei wird gelöscht (kein leeres JSON)."""
    from app.services import text_export as mod
    monkeypatch.setattr(mod, "TEXTS_DIR", tmp_path)

    # Erst exportieren, Datei muss da sein
    await export_chapters(video_with_chapters)
    f = tmp_path / video_with_chapters / "chapters.json"
    assert f.exists()

    from app.routers.chapters import router as chapters_router
    app = make_test_app(chapters_router)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.delete(f"/api/chapters/{video_with_chapters}/all")
        assert r.status_code == 200

    assert not f.exists(), "Delete-all muss die Datei entfernen"
    reg = await test_db.fetch_one(
        "SELECT * FROM text_files WHERE video_id=? AND kind='chapters'",
        (video_with_chapters,),
    )
    assert reg is None

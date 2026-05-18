"""
Purge-Safety-Tests (Phase 3a – letzter Schritt: DB-Spalte leeren).

Kontrakt:
- Nur leeren wo eine Export-Datei existiert (text_files-Eintrag).
- Videos ohne Export bleiben unberührt – sonst Datenverlust.
- Ohne confirm=YES kein Effekt.
- Files werden NIE gelöscht.
"""
import pytest
from httpx import AsyncClient, ASGITransport

from app.routers.admin import router as admin_router


async def _client(test_db, make_test_app):
    return AsyncClient(
        transport=ASGITransport(app=make_test_app(admin_router)),
        base_url="http://testserver",
    )


@pytest.fixture
async def mixed_videos(test_db, tmp_path, monkeypatch):
    """Drei Videos:
      v_exp  – Description + Export vorhanden (wird geleert)
      v_new  – Description aber KEIN Export (bleibt!)
      v_null – kein Text (keine Aktion)"""
    from app.services import text_export as te
    monkeypatch.setattr(te, "TEXTS_DIR", tmp_path)

    await test_db.execute(
        "INSERT INTO videos (id, title, description) VALUES (?, ?, ?)",
        ("v_exp", "A", "Exportiert"),
    )
    await test_db.execute(
        "INSERT INTO videos (id, title, description) VALUES (?, ?, ?)",
        ("v_new", "B", "Noch nicht exportiert"),
    )
    await test_db.execute(
        "INSERT INTO videos (id, title, description) VALUES (?, ?, NULL)",
        ("v_null", "C"),
    )
    # Nur für v_exp eine Datei + Registry-Eintrag erzeugen
    await te.export_description("v_exp")
    return tmp_path


async def test_purge_requires_confirm(test_db, mixed_videos, make_test_app):
    c = await _client(test_db, make_test_app)
    async with c as client:
        r = await client.post("/api/admin/text-export/purge-db-descriptions")
        assert r.status_code == 400

    # DB unverändert
    row = await test_db.fetch_one(
        "SELECT description FROM videos WHERE id = ?", ("v_exp",)
    )
    assert row["description"] == "Exportiert"


async def test_purge_only_touches_exported(test_db, mixed_videos, make_test_app):
    """v_exp (mit Datei) → NULL, v_new (ohne Datei) → bleibt, v_null → bleibt NULL."""
    c = await _client(test_db, make_test_app)
    async with c as client:
        r = await client.post(
            "/api/admin/text-export/purge-db-descriptions?confirm=YES"
        )
        assert r.status_code == 200
        body = r.json()

    assert body["purged"] == 1
    # v_exp → geleert
    r_exp = await test_db.fetch_one(
        "SELECT description FROM videos WHERE id=?", ("v_exp",)
    )
    assert r_exp["description"] is None
    # v_new → NICHT angetastet (Safety!)
    r_new = await test_db.fetch_one(
        "SELECT description FROM videos WHERE id=?", ("v_new",)
    )
    assert r_new["description"] == "Noch nicht exportiert"


async def test_purge_preserves_export_files(test_db, mixed_videos, make_test_app):
    """Purge darf KEINE Dateien löschen."""
    file = mixed_videos / "v_exp" / "description.txt"
    assert file.exists()
    content_before = file.read_text()

    c = await _client(test_db, make_test_app)
    async with c as client:
        r = await client.post(
            "/api/admin/text-export/purge-db-descriptions?confirm=YES"
        )
        assert r.status_code == 200

    # Datei muss noch da und unverändert sein
    assert file.exists()
    assert file.read_text() == content_before


async def test_purge_does_not_affect_text_files_registry(
    test_db, mixed_videos, make_test_app
):
    """Die Registry-Tabelle text_files muss unberührt bleiben."""
    before = await test_db.fetch_val("SELECT COUNT(*) FROM text_files")

    c = await _client(test_db, make_test_app)
    async with c as client:
        await client.post(
            "/api/admin/text-export/purge-db-descriptions?confirm=YES"
        )

    after = await test_db.fetch_val("SELECT COUNT(*) FROM text_files")
    assert before == after

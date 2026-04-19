"""
Admin-Router Tests – text-export Endpoints.
"""
import pytest

from app.routers import admin as admin_router


@pytest.fixture
async def client(async_client_factory, tmp_path, monkeypatch):
    # TEXTS_DIR auf tmp umbiegen, damit Tests sich nicht gegenseitig stören
    from app.services import text_export as te
    monkeypatch.setattr(te, "TEXTS_DIR", tmp_path)

    c = await async_client_factory(admin_router.router)
    yield c
    await c.aclose()


async def test_overview_empty(client):
    r = await client.get("/api/admin/text-export/overview")
    assert r.status_code == 200
    data = r.json()
    assert "description" in data
    assert data["description"]["in_db"] == 0
    assert data["description"]["as_file"] == 0


async def test_overview_with_data(client, test_db):
    await test_db.execute(
        "INSERT INTO videos (id, title, description) VALUES (?, ?, ?)",
        ("v1", "T", "Hello"),
    )
    r = await client.get("/api/admin/text-export/overview")
    data = r.json()
    assert data["description"]["in_db"] == 1
    assert data["description"]["pending"] == 1


async def test_sync_all(client, test_db):
    for i in range(3):
        await test_db.execute(
            "INSERT INTO videos (id, title, description) VALUES (?, ?, ?)",
            (f"vv{i}", f"T{i}", f"text {i}"),
        )
    r = await client.post("/api/admin/text-export/description/sync-all")
    assert r.status_code == 200
    stats = r.json()
    assert stats["written"] == 3
    assert stats["errors"] == 0


async def test_sync_single(client, test_db):
    await test_db.execute(
        "INSERT INTO videos (id, title, description) VALUES (?, ?, ?)",
        ("vid1", "T", "Inhalt"),
    )
    r = await client.post("/api/admin/text-export/description/vid1")
    assert r.status_code == 200
    assert r.json()["skipped"] is False


async def test_sync_nonexistent_returns_404(client):
    r = await client.post("/api/admin/text-export/description/does-not-exist")
    assert r.status_code == 404


async def test_get_file_content(client, test_db):
    await test_db.execute(
        "INSERT INTO videos (id, title, description) VALUES (?, ?, ?)",
        ("vid2", "T", "Text-Inhalt"),
    )
    await client.post("/api/admin/text-export/description/vid2")

    r = await client.get("/api/admin/text-export/description/vid2/file")
    assert r.status_code == 200
    assert r.text == "Text-Inhalt"
    assert r.headers["content-type"].startswith("text/plain")


async def test_get_file_404_when_not_exported(client):
    r = await client.get("/api/admin/text-export/description/unknown/file")
    assert r.status_code == 404


async def test_delete_export(client, test_db):
    await test_db.execute(
        "INSERT INTO videos (id, title, description) VALUES (?, ?, ?)",
        ("vid3", "T", "abc"),
    )
    await client.post("/api/admin/text-export/description/vid3")

    r = await client.delete("/api/admin/text-export/description/vid3")
    assert r.status_code == 200
    assert r.json() == {"video_id": "vid3", "deleted": True}

    # Nach delete: file 404
    r2 = await client.get("/api/admin/text-export/description/vid3/file")
    assert r2.status_code == 404


async def test_delete_idempotent(client):
    r = await client.delete("/api/admin/text-export/description/never-existed")
    assert r.status_code == 200
    assert r.json()["deleted"] is False

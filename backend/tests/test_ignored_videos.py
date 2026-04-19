"""
Ignored-Videos Router Tests.

Sichert ab:
- GET/POST/DELETE Endpoints
- Channel-Filter im GET
- Channel-ID Auto-Ableitung aus rss_entries/videos wenn nicht übergeben
- get_ignored_ids() Filter-Helper
"""
import pytest

from app.routers import ignored_videos
from app.routers.ignored_videos import get_ignored_ids


@pytest.fixture
async def client(async_client_factory):
    c = await async_client_factory(ignored_videos.router)
    yield c
    await c.aclose()


# ─────────────────────── GET ───────────────────────

async def test_list_empty(client):
    r = await client.get("/api/ignored-videos")
    assert r.status_code == 200
    assert r.json() == []


async def test_list_returns_ignored(client, test_db):
    await test_db.execute(
        "INSERT INTO ignored_videos (video_id, channel_id, reason) VALUES (?, ?, ?)",
        ("vid123", "UCabc", "Test"),
    )
    r = await client.get("/api/ignored-videos")
    data = r.json()
    assert len(data) == 1
    assert data[0]["video_id"] == "vid123"


async def test_list_filters_by_channel(client, test_db):
    await test_db.execute(
        "INSERT INTO ignored_videos (video_id, channel_id) VALUES (?, ?), (?, ?), (?, ?)",
        ("v1", "UCa", "v2", "UCa", "v3", "UCb"),
    )
    r_all = await client.get("/api/ignored-videos")
    assert len(r_all.json()) == 3

    r_a = await client.get("/api/ignored-videos?channel_id=UCa")
    assert len(r_a.json()) == 2

    r_b = await client.get("/api/ignored-videos?channel_id=UCb")
    assert len(r_b.json()) == 1
    assert r_b.json()[0]["video_id"] == "v3"


# ─────────────────────── POST ───────────────────────

async def test_ignore_basic(client):
    r = await client.post(
        "/api/ignored-videos",
        json={"video_id": "vid1", "channel_id": "UCabc", "reason": "Test"},
    )
    assert r.status_code == 200
    assert r.json() == {"video_id": "vid1", "ignored": True}


async def test_ignore_derives_channel_id_from_videos_table(client, test_db):
    """Wenn channel_id nicht übergeben, wird sie aus videos/rss_entries abgeleitet."""
    await test_db.execute(
        "INSERT INTO videos (id, title, channel_id) VALUES (?, ?, ?)",
        ("vid-derived", "Test", "UC-auto"),
    )
    r = await client.post(
        "/api/ignored-videos",
        json={"video_id": "vid-derived"},  # ohne channel_id
    )
    assert r.status_code == 200
    # Channel_id wurde abgeleitet
    rows = await test_db.fetch_all("SELECT * FROM ignored_videos")
    assert rows[0]["channel_id"] == "UC-auto"


async def test_ignore_missing_video_id_rejected(client):
    r = await client.post("/api/ignored-videos", json={})
    assert r.status_code == 422


async def test_ignore_empty_video_id_rejected(client):
    r = await client.post("/api/ignored-videos", json={"video_id": ""})
    assert r.status_code == 400


async def test_ignore_idempotent(client):
    """INSERT OR REPLACE → zweites POST überschreibt reason."""
    await client.post("/api/ignored-videos", json={"video_id": "vid1", "reason": "a"})
    await client.post("/api/ignored-videos", json={"video_id": "vid1", "reason": "b"})
    r = await client.get("/api/ignored-videos")
    assert len(r.json()) == 1
    assert r.json()[0]["reason"] == "b"


# ─────────────────────── DELETE ───────────────────────

async def test_unignore(client, test_db):
    await test_db.execute(
        "INSERT INTO ignored_videos (video_id) VALUES (?)", ("vid1",)
    )
    r = await client.delete("/api/ignored-videos/vid1")
    assert r.status_code == 200
    assert r.json() == {"video_id": "vid1", "ignored": False}
    rows = await test_db.fetch_all("SELECT * FROM ignored_videos")
    assert len(rows) == 0


async def test_unignore_nonexistent_is_ok(client):
    r = await client.delete("/api/ignored-videos/does-not-exist")
    assert r.status_code == 200


# ─────────────────────── get_ignored_ids() ───────────────────────

async def test_get_ignored_ids_empty(test_db):
    ids = await get_ignored_ids()
    assert ids == set()


async def test_get_ignored_ids_returns_set(test_db):
    await test_db.execute(
        "INSERT INTO ignored_videos (video_id) VALUES (?), (?), (?)",
        ("v1", "v2", "v3"),
    )
    ids = await get_ignored_ids()
    assert ids == {"v1", "v2", "v3"}
    assert isinstance(ids, set)

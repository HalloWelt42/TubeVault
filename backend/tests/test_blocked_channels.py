"""
Blocked-Channels Router Tests.

Sichert ab:
- GET/POST/DELETE Endpoints
- Dedup via INSERT OR REPLACE
- get_blocked_ids() Filter-Helper
- Validierung leerer channel_id
"""
import pytest

from app.routers import blocked_channels
from app.routers.blocked_channels import get_blocked_ids


@pytest.fixture
async def client(async_client_factory):
    c = await async_client_factory(blocked_channels.router)
    yield c
    await c.aclose()


# ─────────────────────── GET (list) ───────────────────────

async def test_list_empty(client):
    r = await client.get("/api/blocked-channels")
    assert r.status_code == 200
    assert r.json() == []


async def test_list_returns_blocked(client, test_db):
    await test_db.execute(
        "INSERT INTO blocked_channels (channel_id, channel_name, reason) VALUES (?, ?, ?)",
        ("UCabc", "Test-Channel", "Spam"),
    )
    r = await client.get("/api/blocked-channels")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["channel_id"] == "UCabc"
    assert data[0]["channel_name"] == "Test-Channel"
    assert data[0]["reason"] == "Spam"


# ─────────────────────── POST (block) ───────────────────────

async def test_block_minimal(client):
    r = await client.post(
        "/api/blocked-channels",
        json={"channel_id": "UCxyz"},
    )
    assert r.status_code == 200
    assert r.json() == {"channel_id": "UCxyz", "blocked": True}


async def test_block_with_name_and_reason(client):
    r = await client.post(
        "/api/blocked-channels",
        json={"channel_id": "UCabc", "channel_name": "Bad", "reason": "Spam"},
    )
    assert r.status_code == 200
    r2 = await client.get("/api/blocked-channels")
    data = r2.json()
    assert data[0]["channel_name"] == "Bad"
    assert data[0]["reason"] == "Spam"


async def test_block_idempotent_via_insert_or_replace(client):
    """INSERT OR REPLACE: zweites POST überschreibt, duplicate keys nicht möglich."""
    await client.post("/api/blocked-channels", json={"channel_id": "UCabc", "reason": "Erst"})
    await client.post("/api/blocked-channels", json={"channel_id": "UCabc", "reason": "Neu"})
    r = await client.get("/api/blocked-channels")
    data = r.json()
    assert len(data) == 1
    assert data[0]["reason"] == "Neu"


async def test_block_empty_channel_id_rejected(client):
    r = await client.post("/api/blocked-channels", json={"channel_id": ""})
    assert r.status_code == 400
    assert "channel_id" in r.json()["detail"].lower()


async def test_block_missing_channel_id_rejected(client):
    r = await client.post("/api/blocked-channels", json={})
    assert r.status_code == 422  # FastAPI validation error


# ─────────────────────── DELETE (unblock) ───────────────────────

async def test_unblock(client, test_db):
    await test_db.execute(
        "INSERT INTO blocked_channels (channel_id) VALUES (?)", ("UCabc",)
    )
    r = await client.delete("/api/blocked-channels/UCabc")
    assert r.status_code == 200
    assert r.json() == {"channel_id": "UCabc", "blocked": False}

    # Nach delete ist Liste leer
    r2 = await client.get("/api/blocked-channels")
    assert r2.json() == []


async def test_unblock_nonexistent_is_idempotent(client):
    """Kein Fehler wenn channel gar nicht geblockt ist."""
    r = await client.delete("/api/blocked-channels/UCnever-existed")
    assert r.status_code == 200


# ─────────────────────── get_blocked_ids() Helper ───────────────────────

async def test_get_blocked_ids_empty(test_db):
    ids = await get_blocked_ids()
    assert ids == set()


async def test_get_blocked_ids_returns_set(test_db):
    await test_db.execute(
        "INSERT INTO blocked_channels (channel_id) VALUES (?), (?)",
        ("UC1", "UC2"),
    )
    ids = await get_blocked_ids()
    assert ids == {"UC1", "UC2"}
    assert isinstance(ids, set), "set() nötig für O(1) lookup im Filter"

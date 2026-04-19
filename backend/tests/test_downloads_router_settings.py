"""
Downloads-Router: /cooldown und /throttle Endpoints.

Sichert die Validierungs-Logik ab (v2.4.6 Regression):
- seconds < 5 wird auf 5 geclampt (kein 0)
- seconds > 3600 wird auf 3600 geclampt
- Setting wird korrekt in settings-Tabelle persistiert
- reload_cooldown_base() wird ausgelöst (_cooldown_base aktualisiert)
- Throttle-Endpoint akzeptiert beide Parameter (kbps + realtime)
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.routers import downloads as downloads_router


@pytest.fixture
async def client(async_client_factory):
    c = await async_client_factory(downloads_router.router)
    yield c
    await c.aclose()


# ─────────────────────── /cooldown ───────────────────────

async def test_cooldown_sets_setting_and_reloads(client, test_db):
    """Normaler Pfad: 60s wird persistiert + download_service.reload_cooldown_base aufgerufen."""
    with patch.object(downloads_router.download_service,
                      "reload_cooldown_base", new_callable=AsyncMock) as m:
        r = await client.put("/api/downloads/cooldown?seconds=60")
        assert r.status_code == 200
        assert r.json() == {"cooldown_base_s": 60}
        m.assert_awaited_once()
    # Persistiert in DB?
    row = await test_db.fetch_one(
        "SELECT value FROM settings WHERE key='download.cooldown_base_s'")
    assert row["value"] == "60"


async def test_cooldown_clamp_minimum_5(client, test_db):
    """v2.4.6: 0 darf nicht durchgehen (User-Bug: Wartezeit verschwand)."""
    with patch.object(downloads_router.download_service,
                      "reload_cooldown_base", new_callable=AsyncMock):
        r = await client.put("/api/downloads/cooldown?seconds=0")
    assert r.status_code == 200
    assert r.json() == {"cooldown_base_s": 5}
    row = await test_db.fetch_one(
        "SELECT value FROM settings WHERE key='download.cooldown_base_s'")
    assert row["value"] == "5"


async def test_cooldown_clamp_negative(client, test_db):
    with patch.object(downloads_router.download_service,
                      "reload_cooldown_base", new_callable=AsyncMock):
        r = await client.put("/api/downloads/cooldown?seconds=-10")
    assert r.json()["cooldown_base_s"] == 5


async def test_cooldown_clamp_maximum_3600(client, test_db):
    """Obere Grenze: 2h. 10000s soll auf 3600 geclampt."""
    with patch.object(downloads_router.download_service,
                      "reload_cooldown_base", new_callable=AsyncMock):
        r = await client.put("/api/downloads/cooldown?seconds=10000")
    assert r.json()["cooldown_base_s"] == 3600


async def test_cooldown_missing_param_uses_default_30(client, test_db):
    """Ohne Query-Param → Default 30 aus FastAPI-Signature."""
    with patch.object(downloads_router.download_service,
                      "reload_cooldown_base", new_callable=AsyncMock):
        r = await client.put("/api/downloads/cooldown")
    assert r.json()["cooldown_base_s"] == 30


# ─────────────────────── /throttle ───────────────────────

async def test_throttle_fixed_kbps(client, test_db):
    r = await client.put("/api/downloads/throttle?kbps=500&realtime=false")
    assert r.status_code == 200
    assert r.json() == {"throttle_kbps": 500, "throttle_realtime": False}
    kb = await test_db.fetch_one(
        "SELECT value FROM settings WHERE key='download.throttle_kbps'")
    rt = await test_db.fetch_one(
        "SELECT value FROM settings WHERE key='download.throttle_realtime'")
    assert kb["value"] == "500"
    assert rt["value"] == "false"


async def test_throttle_realtime_mode(client, test_db):
    r = await client.put("/api/downloads/throttle?kbps=0&realtime=true")
    data = r.json()
    assert data["throttle_realtime"] is True
    assert data["throttle_kbps"] == 0


async def test_throttle_clamp_upper(client, test_db):
    r = await client.put("/api/downloads/throttle?kbps=999999")
    assert r.json()["throttle_kbps"] == 100000


async def test_throttle_clamp_negative(client, test_db):
    r = await client.put("/api/downloads/throttle?kbps=-50")
    assert r.json()["throttle_kbps"] == 0


async def test_throttle_default_off(client, test_db):
    """Ohne Params: kbps=0 (FastAPI-Default) und realtime=False."""
    r = await client.put("/api/downloads/throttle")
    assert r.json() == {"throttle_kbps": 0, "throttle_realtime": False}

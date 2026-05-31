"""
Thumbnail-Endpoint Tests – kein 404 mehr für nicht-heruntergeladene
YouTube-Videos (Bug: 404-Flut in der Konsole, leere Platzhalter im Feed).

Kontrakt:
- lokales Thumbnail vorhanden → FileResponse
- kein lokales, aber gültige 11-Zeichen-YT-ID → 307-Redirect auf rss-thumb
- local_-Importe ohne Thumbnail → bleibt 404 (kein YouTube-Fallback möglich)
"""
import pytest
from httpx import AsyncClient, ASGITransport

from app.routers.player import router as player_router


async def _client(make_test_app):
    return AsyncClient(
        transport=ASGITransport(app=make_test_app(player_router)),
        base_url="http://testserver",
    )


async def test_thumbnail_redirects_for_youtube_id(test_db, make_test_app):
    """Nicht-heruntergeladenes YT-Video (11-Zeichen-ID) → 307 auf rss-thumb."""
    c = await _client(make_test_app)
    async with c as client:
        r = await client.get("/api/player/pw78d5T2CFI/thumbnail", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/api/subscriptions/rss-thumb/pw78d5T2CFI"


async def test_thumbnail_404_for_local_import(test_db, make_test_app):
    """local_-Importe ohne Thumbnail haben kein YouTube-Fallback → 404."""
    c = await _client(make_test_app)
    async with c as client:
        r = await client.get("/api/player/local_abc123/thumbnail", follow_redirects=False)
    assert r.status_code == 404

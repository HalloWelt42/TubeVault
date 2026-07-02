"""
Charakterisierung der Zähl-Semantik (Phase 1 – VOR dem counts_service-Umbau).

Friert das heutige Verhalten von /api/system/badges + /api/system/stats ein,
damit der Umbau nachweislich nichts unbeabsichtigt verändert. Die EINE gewollte
Änderung (own_videos-Badge soll die OwnVideos-Seite exakt spiegeln) ist als
xfail(strict) markiert und wird nach dem Fix grün.

Regel (bestätigt am Code): videos-Badge == Library-Seite (ready & non-archived),
archives-Badge == Archiv-Seite (ready & archived). own_videos-Badge weicht heute
von der OwnVideos-Seite ab (Seite hat file_size>0, Badge nicht).
"""
import json
import pytest
from httpx import AsyncClient, ASGITransport


async def _client(make_test_app, *routers):
    from httpx import AsyncClient, ASGITransport
    app = make_test_app(*routers)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def _seed(db):
    """Kontrollierte Mischung für exakte Zähl-Assertions."""
    async def vid(id, status="ready", archived=0, source="youtube", fsize=1000, fpath="/x.mp4"):
        await db.execute(
            "INSERT INTO videos (id, title, status, is_archived, source, file_size, file_path) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (id, id, status, archived, source, fsize, fpath))
    # Library (ready, non-archived, youtube): 3
    await vid("lib1"); await vid("lib2"); await vid("lib3")
    # Archiviert (ready, archived, youtube): 2
    await vid("arc1", archived=1); await vid("arc2", archived=1)
    # Eigene, non-archived (imported/local, ready, fsize>0): 2
    await vid("own1", source="imported"); await vid("own2", source="local")
    # Eigenes ARCHIVIERTES Video (imported, ready, archived): 1
    #   → zählt heute im own_videos-Badge (kein Archiv-Filter) UND im archives-Badge
    await vid("ownArc", source="imported", archived=1)
    # Eigenes mit file_size=0 (Seite zeigt es NICHT, Badge zählt es heute): 1
    await vid("ownZero", source="imported", fsize=0)
    # Pending (nicht ready): zählt nirgends
    await vid("pend1", status="pending")

    await db.execute("INSERT INTO subscriptions (channel_id, channel_name, enabled) VALUES ('c1','A',1)")
    await db.execute("INSERT INTO subscriptions (channel_id, channel_name, enabled) VALUES ('c2','B',0)")
    await db.execute("INSERT INTO rss_entries (video_id, channel_id, status, feed_status) VALUES ('r1','c1','new','active')")
    await db.execute("INSERT INTO rss_entries (video_id, channel_id, status, feed_status) VALUES ('r2','c1','new','later')")


async def test_badges_frozen_semantics(test_db, make_test_app):
    from app.routers import system
    await _seed(test_db)
    c = await _client(make_test_app, system.router)
    async with c as client:
        b = (await client.get("/api/system/badges")).json()

    # videos = ready & non-archived, OHNE source-Filter → lib1-3 + own1,own2,ownZero = 6
    # (eigene non-archived Videos zählen bewusst auch hier; sie stehen in der Library)
    assert b["videos"] == 6
    assert b["archives"] == 3        # ready & archived (arc1,arc2,ownArc)
    assert b["subscriptions"] == 1   # enabled=1
    assert b["new_feed"] == 1        # new & feed_status active
    # own_videos NACH Fix: = OwnVideos-Seite (file_size>0), ownZero fällt raus
    #   → own1, own2, ownArc = 3
    assert b["own_videos"] == 3


async def test_stats_frozen_semantics(test_db, make_test_app):
    from app.routers import system
    await _seed(test_db)
    c = await _client(make_test_app, system.router)
    async with c as client:
        s = (await client.get("/api/system/stats")).json()
    assert s["video_count"] == 6
    assert s["archives_count"] == 3


async def test_own_videos_badge_matches_page(test_db, make_test_app):
    """Das Badge zählt exakt das, was die OwnVideos-Seite anzeigt
    (source local/imported, ready, file_path, file_size>0). Seit Phase-1-Fix
    konsistent (vorher xfail)."""
    from app.routers import system, own_videos
    await _seed(test_db)
    c = await _client(make_test_app, system.router, own_videos.router)
    async with c as client:
        badge = (await client.get("/api/system/badges")).json()["own_videos"]
        page = (await client.get("/api/own-videos?per_page=100")).json()
    page_total = page.get("total") if isinstance(page, dict) else len(page)
    assert badge == page_total

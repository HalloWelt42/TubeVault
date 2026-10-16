"""
Wiederherstellen (routers/restore, Einstellungen > System).

Kontrakt: Der Stand nennt Nutzerdaten-Sicherungen, den Wiederaufbau und die
noch fehlenden Inhaltsdateien; ein zweiter Wiederaufbau während des ersten
wird abgelehnt.
"""
from app.routers import restore
from app.services import rebuild_service


async def test_stand_und_doppelter_wiederaufbau(test_db, make_test_app, monkeypatch):
    from httpx import ASGITransport, AsyncClient
    app = make_test_app(restore.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status = (await client.get("/api/restore/status")).json()
        assert set(status) == {"userdata_exports", "rebuild", "content_files_missing"}
        assert status["content_files_missing"] == 0
        monkeypatch.setitem(rebuild_service.rebuild_state, "running", True)
        assert (await client.post("/api/restore/rebuild?dry_run=true")).status_code == 409

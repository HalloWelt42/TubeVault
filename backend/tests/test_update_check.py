"""
Hinweis auf eine neue Version (app/services/update_check).

Kontrakt:
- Versionen werden als Zahlen verglichen (2.100.0 ist neuer als 2.67.3)
- verfügbar ist ein Update nur, wenn die gelesene Version neuer ist
- ausgeschaltet meldet der Dienst nichts
- ist das Projekt nicht erreichbar, bleibt der letzte Stand stehen
"""
import httpx
import pytest

from app.services import update_check


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(update_check, "_latest", None)
    monkeypatch.setattr(update_check, "_checked_at", None)
    monkeypatch.setattr(update_check, "VERSION", "2.67.3")


def answer(monkeypatch, version=None, error=None):
    async def fetch():
        if error:
            raise error
        return version
    monkeypatch.setattr(update_check, "fetch_latest", fetch)


def test_versionen_als_zahlen():
    assert update_check.is_newer("2.100.0", "2.67.3")
    assert update_check.is_newer("3.0.0", "2.99.99")
    assert not update_check.is_newer("2.67.3", "2.67.3")
    assert not update_check.is_newer("2.9.0", "2.67.3")


async def test_neuere_version_wird_gemeldet(test_db, monkeypatch):
    answer(monkeypatch, "2.68.0")
    assert await update_check.check()
    status = await update_check.status()
    assert (status.available, status.latest, status.current) == (True, "2.68.0", "2.67.3")
    assert status.url == update_check.PROJECT_URL


async def test_gleiche_version_ist_kein_update(test_db, monkeypatch):
    answer(monkeypatch, "2.67.3")
    await update_check.check()
    assert not (await update_check.status()).available


async def test_ausgeschaltet_meldet_nichts(test_db, monkeypatch, set_setting):
    answer(monkeypatch, "2.68.0")
    await update_check.check()
    await set_setting(update_check.SWITCH, "false")
    status = await update_check.status()
    assert (status.enabled, status.available, status.latest) == (False, False, None)


async def test_nicht_erreichbar_behaelt_den_stand(test_db, monkeypatch):
    answer(monkeypatch, "2.68.0")
    await update_check.check()
    answer(monkeypatch, error=httpx.ConnectError("keine Verbindung"))
    assert not await update_check.check()
    assert (await update_check.status()).latest == "2.68.0"

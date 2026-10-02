"""
Einstellungs-Schema: eine Liste für Datenbank, Prüfung und Oberfläche.
"""
import re
from pathlib import Path

import pytest

from app import settings_schema
from app.routers import settings as settings_router

APP_DIR = Path(__file__).resolve().parent.parent / "app"
FRONTEND_SRC = APP_DIR.parent.parent / "frontend" / "src"


@pytest.fixture
async def client(async_client_factory):
    c = await async_client_factory(settings_router.router)
    async with c:
        yield c


def _sources() -> str:
    files = [p for p in APP_DIR.rglob("*.py") if p.name != "settings_schema.py"]
    files += [p for p in FRONTEND_SRC.rglob("*") if p.suffix in (".svelte", ".js") and "tests" not in p.parts]
    return "\n".join(p.read_text(encoding="utf-8") for p in files)


def test_jede_einstellung_hat_einen_verbraucher():
    """Kein Regler ohne Wirkung: jeder Schlüssel wird irgendwo im Code gelesen."""
    code = _sources()
    unused = [d.key for d in settings_schema.SETTINGS if d.key not in code]
    assert not unused, f"Einstellungen ohne Verbraucher: {unused}"


def test_entfernte_schluessel_sind_nicht_mehr_im_schema():
    assert not set(settings_schema.REMOVED_KEYS) & set(settings_schema.BY_KEY)


def test_standardwerte_bestehen_die_eigene_pruefung():
    for d in settings_schema.SETTINGS:
        assert settings_schema.validate(d.key, d.default) == d.default, d.key


async def test_datenbank_kennt_alle_schluessel(test_db):
    keys = {r["key"] for r in await test_db.fetch_all("SELECT key FROM settings")}
    assert set(settings_schema.BY_KEY) <= keys
    assert not set(settings_schema.REMOVED_KEYS) & keys


async def test_speichern_prueft_grenzen(client, test_db):
    r = await client.put("/api/settings/general.videos_per_page", json={"value": "500"})
    assert r.status_code == 422 and "höchstens" in r.json()["detail"]
    r = await client.put("/api/settings/general.videos_per_page", json={"value": "abc"})
    assert r.status_code == 422
    r = await client.put("/api/settings/general.videos_per_page", json={"value": "48"})
    assert r.status_code == 200
    assert await test_db.fetch_val(
        "SELECT value FROM settings WHERE key='general.videos_per_page'") == "48"


async def test_speichern_prueft_auswahl_und_schalter(client):
    assert (await client.put("/api/settings/download.quality", json={"value": "777p"})).status_code == 422
    assert (await client.put("/api/settings/download.quality", json={"value": "240p"})).status_code == 200
    assert (await client.put("/api/settings/rss.enabled", json={"value": "vielleicht"})).status_code == 422
    assert (await client.put("/api/settings/download.subtitle_lang", json={"value": "DE, en"})).json()["value"] == "de,en"


async def test_unbekannter_schluessel(client):
    assert (await client.put("/api/settings/gibt.es.nicht", json={"value": "1"})).status_code == 404
    assert (await client.put("/api/settings/download.format", json={"value": "mkv"})).status_code == 404


async def test_schluessel_ohne_zeile_wird_angelegt(client, test_db):
    """Der Drosselungs-Regler scheiterte früher mit 404, solange die Zeile fehlte."""
    await test_db.execute("DELETE FROM settings WHERE key = 'download.throttle_kbps'")
    r = await client.put("/api/settings/download.throttle_kbps", json={"value": "800"})
    assert r.status_code == 200
    assert await test_db.fetch_val(
        "SELECT value FROM settings WHERE key='download.throttle_kbps'") == "800"


async def test_schema_endpunkt(client):
    r = await client.get("/api/settings/schema")
    assert r.status_code == 200
    keys = {d["key"] for d in r.json()}
    assert "download.quality" in keys and "download.format" not in keys


async def test_zuruecksetzen(client, test_db):
    await client.put("/api/settings/general.videos_per_page", json={"value": "48"})
    await client.post("/api/settings/reset")
    assert await test_db.fetch_val("SELECT value FROM settings WHERE key='general.videos_per_page'") == "24"

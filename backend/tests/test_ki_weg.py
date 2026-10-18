"""
Weg zum KI-Dienst (Wunsch 16.10.2026): direkt oder über die Leitstelle, jederzeit umschaltbar.

Kontrakt:
- Direkt: Adresse ai.url, keine zusätzlichen Köpfe (wie bisher).
- Leitstelle: Adresse ai.leitstelle_url, Schlüssel als Bearer, lesbarer Titel prozentkodiert,
  Stapelarbeit mit Vorrang Hintergrund.
- Umschalten wirkt sofort, ohne Neustart; beide Adressen bleiben gespeichert.
- Nur die KI nimmt diesen Weg (hier: Bedeutungssuche und Textaufgaben fragen headers()).
"""
import json
from urllib.parse import unquote

import httpx
import pytest

from app import settings_schema
from app.services import ai_chat, semantic_index


@pytest.fixture
async def ki(test_db, set_setting):
    await set_setting("ai.enabled", "true")
    await set_setting("ai.url", "http://mac-studio.test:1234/v1")
    await set_setting("ai.leitstelle_url", "http://leitstelle.test:8530/v1")
    await set_setting("ai.leitstelle_key", "ls_geheim")
    semantic_index.reset_availability()
    yield set_setting
    semantic_index.reset_availability()


async def test_direkt_ist_vorgabe_und_ohne_koepfe(ki):
    assert settings_schema.default("ai.route") == "direct"
    assert await semantic_index.config() == ("http://mac-studio.test:1234/v1", semantic_index.EMBEDDING_MODEL)
    assert await semantic_index.headers("Bedeutungssuche") == {}


async def test_leitstelle_adresse_schluessel_titel_vorrang(ki):
    await ki("ai.route", "leitstelle")
    assert (await semantic_index.config())[0] == "http://leitstelle.test:8530/v1"
    kopf = await semantic_index.headers("Gesagtes einbetten", background=True)
    assert kopf["Authorization"] == "Bearer ls_geheim"
    assert kopf["X-Leitstelle-Prioritaet"] == "hintergrund"
    assert kopf["X-Leitstelle-Titel"].isascii() and unquote(kopf["X-Leitstelle-Titel"]) == "TubeVault: Gesagtes einbetten"
    assert "X-Leitstelle-Prioritaet" not in await semantic_index.headers("Bedeutungssuche")


async def test_umschalten_zurueck_ohne_neustart(ki):
    await ki("ai.route", "leitstelle")
    await ki("ai.route", "direct")
    assert (await semantic_index.config())[0] == "http://mac-studio.test:1234/v1"
    assert await semantic_index.headers("Bedeutungssuche") == {}


async def test_leitstelle_ohne_adresse_ist_aus(ki):
    await ki("ai.route", "leitstelle")
    await ki("ai.leitstelle_url", "")
    assert await semantic_index.config() is None


async def test_anfragen_tragen_die_koepfe(ki, monkeypatch):
    """Einbettung und Textaufgabe schicken die Köpfe wirklich mit (Transport-Attrappe)."""
    await ki("ai.route", "leitstelle")
    gesehen: list[httpx.Request] = []

    def antwort(request: httpx.Request) -> httpx.Response:
        gesehen.append(request)
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})
        if request.url.path.endswith("/v1/models"):
            return httpx.Response(200, json={"data": [{"id": "qwen/qwen3-next-80b", "x-leitstelle": {"faehigkeiten": ["text"], "extern": False}}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "{\"themen\": []}"}}]})

    echter_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: echter_client(transport=httpx.MockTransport(antwort), **kw))
    ai_chat.forget_model()
    await semantic_index.embed_texts(["hallo"], "http://leitstelle.test:8530/v1", "m", 4, purpose="Bedeutungssuche")
    await ai_chat.complete_json("s", "u", "themen", {"type": "object"})
    assert [r.url.host for r in gesehen] == ["leitstelle.test"] * 3
    assert all(r.headers["authorization"] == "Bearer ls_geheim" for r in gesehen)
    assert unquote(gesehen[-1].headers["x-leitstelle-titel"]) == "TubeVault: Textaufgabe themen"
    assert json.loads(gesehen[-1].content)["model"] == "leitstelle", "über die Leitstelle wählt sie das Modell"


def test_schluessel_wird_geprueft():
    with pytest.raises(ValueError):
        settings_schema.validate("ai.leitstelle_key", "mit leerzeichen")
    assert settings_schema.validate("ai.leitstelle_key", " ls_abc ") == "ls_abc"
    with pytest.raises(ValueError):
        settings_schema.validate("ai.leitstelle_url", "leitstelle:8530")

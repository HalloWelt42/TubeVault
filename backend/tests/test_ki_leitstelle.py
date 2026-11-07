"""
KI über die Leitstelle: TubeVault nennt immer selbst das Sprachmodell aus ai.leitstelle_text_model (LS-19: die
Leitstelle wählt nie), Ausweichen nach extern nur über die Erlaubnisliste ai.leitstelle_extern (Kopf X-Leitstelle-Extern).
"""
from urllib.parse import unquote

import httpx
import pytest

from app import settings_schema
from app.services import ai_chat, semantic_index

LISTE = {"object": "list", "data": [
    {"id": "Qwen/Qwen3.8-27B", "object": "model", "x-leitstelle": {"name": "Qwen3.8-27B", "geladen": True, "extern": True,
     "faehigkeiten": ["text", "uebersetzen"], "steckbrief": {"zweck": "", "anfragen_je_minute": 10}}},
    {"id": "qwen/qwen3-next-80b", "object": "model", "x-leitstelle": {"name": "Qwen3 Next 80B", "geladen": False, "extern": False,
     "faehigkeiten": ["text", "uebersetzen"]}},
    {"id": "text-embedding-bge-m3", "object": "model", "x-leitstelle": {"name": "Bge M3", "geladen": True, "extern": False,
     "faehigkeiten": ["einbettung"]}}]}


@pytest.fixture
def leitstelle(monkeypatch, set_setting):
    gesehen = []

    def antwort(request):
        gesehen.append(request)
        return httpx.Response(200, json=LISTE)

    echt = httpx.AsyncClient
    monkeypatch.setattr(ai_chat.httpx, "AsyncClient", lambda **kw: echt(transport=httpx.MockTransport(antwort), **kw))

    async def einrichten(extern: str = "", modell: str = ""):
        await set_setting("ai.enabled", "true")
        await set_setting("ai.route", "leitstelle")
        await set_setting("ai.leitstelle_url", "http://ls.test/v1")
        await set_setting("ai.leitstelle_extern", extern)
        await set_setting("ai.leitstelle_text_model", modell)
        ai_chat.forget_model()
    return einrichten, gesehen


async def test_erlaubnisliste_als_kopf(test_db, leitstelle):
    einrichten, _ = leitstelle
    await einrichten()
    assert "X-Leitstelle-Extern" not in await semantic_index.headers("Probe"), "ohne Liste nie nach extern"
    await einrichten("Qwen/Qwen3.8-27B,Qwen3.6 35B")
    kopf = await semantic_index.headers("Probe")
    assert unquote(kopf["X-Leitstelle-Extern"]) == "Qwen/Qwen3.8-27B,Qwen3.6 35B"


def test_liste_wird_bereinigt():
    assert settings_schema.validate("ai.leitstelle_extern", " a , b ,a ,, ") == "a,b"
    with pytest.raises(ValueError):
        settings_schema.validate("ai.leitstelle_extern", "a\nb")


async def test_tubevault_nennt_das_eingestellte_modell(test_db, leitstelle):
    """Auch wenn ein externes Modell als geladen gilt: TubeVault nennt das eingestellte (Vorgabe), nie "leitstelle"."""
    einrichten, gesehen = leitstelle
    await einrichten()
    assert settings_schema.default("ai.leitstelle_text_model") == "qwen/qwen3-next-80b"
    assert await ai_chat.pick_model() == "qwen/qwen3-next-80b"
    assert [r.url.path for r in gesehen] == ["/v1/models"]
    await einrichten(modell="Qwen/Qwen3.8-27B")
    assert await ai_chat.pick_model() == "Qwen/Qwen3.8-27B", "die Wahl der Einstellung gilt, auch extern"


async def test_nicht_angebotenes_modell_heisst_kein_sprachmodell(test_db, leitstelle):
    """Bietet die Leitstelle das eingestellte Modell nicht an (oder ist es kein Sprachmodell), fragt TubeVault nicht."""
    einrichten, _ = leitstelle
    await einrichten(modell="gibt/es-nicht")
    assert await ai_chat.pick_model() is None
    await einrichten(modell="text-embedding-bge-m3")
    assert await ai_chat.pick_model() is None
    with pytest.raises(ai_chat.ChatUnavailable):
        await ai_chat.complete_json("s", "u", "themen", {"type": "object"})


async def test_angebot_der_sprachmodelle(test_db, leitstelle):
    einrichten, _ = leitstelle
    await einrichten()
    a = await ai_chat.text_model_choices()
    assert a["options"] == [
        {"value": "Qwen/Qwen3.8-27B", "label": "Qwen3.8-27B", "hint": "extern, Texte verlassen das Heimnetz, geladen"},
        {"value": "qwen/qwen3-next-80b", "label": "Qwen3 Next 80B", "hint": "im Heimnetz"}]
    assert a["state"].startswith("gefunden")


def test_modellname_wird_geprueft():
    assert settings_schema.validate("ai.leitstelle_text_model", " qwen/qwen3-next-80b ") == "qwen/qwen3-next-80b"
    for falsch in ("", "a\nb", "x" * 201):
        with pytest.raises(ValueError):
            settings_schema.validate("ai.leitstelle_text_model", falsch)


async def test_angebot_externer_modelle(test_db, leitstelle):
    einrichten, _ = leitstelle
    await einrichten()
    a = await ai_chat.extern_choices()
    assert a["options"] == [{"value": "Qwen/Qwen3.8-27B", "label": "Qwen3.8-27B", "hint": "extern, höchstens 10 je Minute"}]
    assert a["state"].startswith("gefunden")

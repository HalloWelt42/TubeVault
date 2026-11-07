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
    assert kopf["X-Leitstelle-Art"] == "masse", "Stapel sind Masse (LS-24)"
    assert kopf["X-Leitstelle-Titel"].isascii() and unquote(kopf["X-Leitstelle-Titel"]) == "TubeVault: Gesagtes einbetten"
    suche = await semantic_index.headers("Bedeutungssuche")
    assert "X-Leitstelle-Prioritaet" not in suche and "X-Leitstelle-Art" not in suche, "die Suche ist ein Einzelauftrag"


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
    """Einbettung und Textaufgabe schicken die Köpfe und ein echtes Modell wirklich mit (Transport-Attrappe)."""
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
    adresse, einbettungsmodell = await semantic_index.config()
    await semantic_index.embed_texts(["hallo"], adresse, einbettungsmodell, 4, purpose="Bedeutungssuche")
    await ai_chat.complete_json("s", "u", "themen", {"type": "object"})
    assert [r.url.host for r in gesehen] == ["leitstelle.test"] * 3
    assert all(r.headers["authorization"] == "Bearer ls_geheim" for r in gesehen)
    assert unquote(gesehen[-1].headers["x-leitstelle-titel"]) == "TubeVault: Textaufgabe themen"
    modell = json.loads(gesehen[-1].content)["model"]
    assert modell == "qwen/qwen3-next-80b" != "leitstelle", "TubeVault nennt das eingestellte Modell, nie den Platzhalter"
    assert json.loads(gesehen[0].content)["model"] == semantic_index.EMBEDDING_MODEL, "auch die Einbettung nennt ihr Modell"


def test_schluessel_wird_geprueft():
    with pytest.raises(ValueError):
        settings_schema.validate("ai.leitstelle_key", "mit leerzeichen")
    assert settings_schema.validate("ai.leitstelle_key", " ls_abc ") == "ls_abc"
    with pytest.raises(ValueError):
        settings_schema.validate("ai.leitstelle_url", "leitstelle:8530")


def test_ki_client_vertraut_der_hausstelle(monkeypatch, tmp_path):
    """Leitstelle über HTTPS (Hausstelle): der KI-Client prüft gegen die üblichen Stellen und TUBEVAULT_CA_DATEI."""
    ohne = len(semantic_index.tls_pruefung().get_ca_certs())
    hausstelle = tmp_path / "rootCA.pem"
    hausstelle.write_text(_FREMDE_STELLE)
    monkeypatch.setenv("TUBEVAULT_CA_DATEI", str(hausstelle))
    semantic_index.tls_pruefung.cache_clear()
    try:
        assert len(semantic_index.tls_pruefung().get_ca_certs()) == ohne + 1
        assert isinstance(semantic_index.ki_client(5), httpx.AsyncClient)
    finally:
        monkeypatch.delenv("TUBEVAULT_CA_DATEI")
        semantic_index.tls_pruefung.cache_clear()


# Wegwerf-Wurzelzertifikat (nur der öffentliche Teil, Schlüssel verworfen); sicher nicht unter den üblichen Stellen
_FREMDE_STELLE = """-----BEGIN CERTIFICATE-----
MIIBKDCBzgIJAOQX6sMq/hz9MAoGCCqGSM49BAMCMBsxGTAXBgNVBAMMEEhhdXNz
dGVsbGUgUHJvYmUwIBcNMjYxMTA2MjI1OTM4WhgPMjEyNjEwMTMyMjU5MzhaMBsx
GTAXBgNVBAMMEEhhdXNzdGVsbGUgUHJvYmUwWTATBgcqhkjOPQIBBggqhkjOPQMB
BwNCAAS0lbhJ/hsjhNNkEk/FNOKabhHNDMKrx3NImSCUwAlvgrKnKOV+lkqkUP9F
+I5MsfUCEH1IPO0ftSNYtdiXurRQMAoGCCqGSM49BAMCA0kAMEYCIQClrPuzdmu6
FzHPbWt5oM1wFxAKcMlAhLXkKrfX2nTCoAIhAPiA0bmvJKpEMnuCJTFhutxOSkc2
Ncox/Bo+wseCaC7r
-----END CERTIFICATE-----
"""

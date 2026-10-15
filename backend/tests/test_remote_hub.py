"""
Fernsteuerung: Geräte sehen einander, steuern einander und geben die
Wiedergabe weiter (Wunsch 15.10.2026).

Kontrakt:
- Wer sich verbindet, bekommt sich selbst und alle Geräte; die anderen
  erfahren davon.
- Ein gemeldeter Wiedergabestand geht an alle anderen und steht in der Liste.
- Befehle und Übergaben gehen nur an das Ziel, mit Absender; ein
  verschwundenes Ziel meldet sich als Fehler beim Absender.
- Übergaben sind geprüft; die Titel der Warteschlange reisen vollständig mit.
- Ein Name gilt für alle Fenster desselben Browsers.
- Neu laden ersetzt die alte Verbindung; deren spätes Schließen wirft das
  Gerät nicht hinaus.
"""
import pytest

from app.routers import remote
from app.services.remote_hub import Hub


class FakeSocket:
    def __init__(self):
        self.received = []

    async def send_json(self, data):
        self.received.append(data)

    def of(self, typ):
        return [m for m in self.received if m["typ"] == typ]


async def _two(hub):
    rechner, handy = FakeSocket(), FakeSocket()
    await hub.join(rechner, "fenster-rechner", "browser-rechner", "Rechner", "rechner")
    await hub.join(handy, "fenster-handy", "browser-handy", "Handy", "handy")
    return rechner, handy


async def test_beitreten_und_sehen():
    hub = Hub()
    rechner, handy = await _two(hub)
    [hallo] = handy.of("willkommen")
    assert hallo["du"]["name"] == "Handy" and [d["name"] for d in hallo["geraete"]] == ["Rechner", "Handy"]
    assert rechner.of("geraete")[-1]["geraete"][1]["art"] == "handy"
    assert not handy.of("geraete")              # sich selbst muss man nicht melden


async def test_zustand_geht_an_die_anderen():
    hub = Hub()
    rechner, handy = await _two(hub)
    await hub.handle("fenster-rechner", {"typ": "zustand", "zustand": {
        "art": "musik", "kennung": "f0123456789abcde", "titel": "Dancing Queen", "untertitel": "ABBA",
        "stelle": 72.5, "dauer": 231, "laeuft": True, "lautstaerke": 0.64, "unbekannt": "fällt weg"}})
    [meldung] = handy.of("zustand")
    assert meldung["id"] == "fenster-rechner" and meldung["zustand"]["titel"] == "Dancing Queen"
    assert "unbekannt" not in meldung["zustand"] and not rechner.of("zustand")
    assert hub.devices()[0].zustand.laeuft

    await hub.handle("fenster-rechner", {"typ": "zustand", "zustand": None})
    assert handy.of("zustand")[-1]["zustand"] is None and hub.devices()[0].zustand is None


async def test_befehl_nur_ans_ziel_mit_absender():
    hub = Hub()
    rechner, handy = await _two(hub)
    await hub.handle("fenster-handy", {"typ": "befehl", "an": "fenster-rechner", "aktion": "pause"})
    [befehl] = rechner.of("befehl")
    assert (befehl["aktion"], befehl["von"], befehl["von_name"]) == ("pause", "fenster-handy", "Handy")
    assert not handy.of("befehl")

    await hub.handle("fenster-handy", {"typ": "befehl", "an": "weg", "aktion": "pause"})
    await hub.handle("fenster-handy", {"typ": "befehl", "an": "fenster-rechner", "aktion": "formatieren"})
    assert [f["text"] for f in handy.of("fehler")] == ["Das Gerät ist nicht mehr da", "Nachricht nicht verstanden"]


async def test_uebergabe_mit_warteschlange():
    hub = Hub()
    rechner, handy = await _two(hub)
    titel = {"id": "f0123456789abcde", "title": "Dancing Queen", "artist": "ABBA", "kind": "datei", "duration": 231.09}
    await hub.handle("fenster-rechner", {"typ": "uebergabe", "an": "fenster-handy", "paket": {
        "art": "musik", "musik": {"queue": [titel], "index": 0, "title": "ABBA Gold", "time": 72.5}}})
    [uebergabe] = handy.of("uebergabe")
    assert uebergabe["von_name"] == "Rechner"
    assert uebergabe["paket"]["musik"]["queue"] == [titel]       # nichts geht verloren
    assert uebergabe["paket"]["musik"]["time"] == 72.5

    await hub.handle("fenster-rechner", {"typ": "uebergabe", "an": "fenster-handy", "paket": {"musik": {}}})
    assert rechner.of("fehler") and len(handy.of("uebergabe")) == 1


async def test_name_gilt_fuer_alle_fenster_des_browsers():
    hub = Hub()
    erstes, zweites = FakeSocket(), FakeSocket()
    await hub.join(erstes, "fenster-1-aaaa", "browser-rechner", "Rechner", "rechner")
    await hub.join(zweites, "fenster-2-aaaa", "browser-rechner", "Rechner", "rechner")
    await hub.handle("fenster-1-aaaa", {"typ": "name", "name": "  Rechner   Arbeitszimmer  "})
    assert {d.name for d in hub.devices()} == {"Rechner Arbeitszimmer"}
    await hub.handle("fenster-1-aaaa", {"typ": "name", "name": "   "})
    assert {d.name for d in hub.devices()} == {"Rechner Arbeitszimmer"}


async def test_neu_laden_ersetzt_die_verbindung():
    hub = Hub()
    alt, neu = FakeSocket(), FakeSocket()
    await hub.join(alt, "fenster-rechner", "browser-rechner", "Rechner", "rechner")
    await hub.join(neu, "fenster-rechner", "browser-rechner", "Rechner", "rechner")
    await hub.leave("fenster-rechner", alt)
    assert [d.id for d in hub.devices()] == ["fenster-rechner"]
    await hub.leave("fenster-rechner", neu)
    assert hub.devices() == []


def test_websocket_ende_zu_ende(make_test_app, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(remote, "hub", Hub())
    client = TestClient(make_test_app(remote.router))
    with client.websocket_connect("/api/remote/ws?id=fenster-rechner&geraet=browser-rechner&name=Rechner") as rechner:
        assert rechner.receive_json()["typ"] == "willkommen"
        with client.websocket_connect("/api/remote/ws?id=fenster-handy&geraet=browser-handy&name=Handy&art=handy") as handy:
            assert handy.receive_json()["typ"] == "willkommen"
            assert rechner.receive_json()["typ"] == "geraete"
            handy.send_text("ping")
            assert handy.receive_text() == "pong"
            handy.send_json({"typ": "befehl", "an": "fenster-rechner", "aktion": "sprung", "wert": 30})
            befehl = rechner.receive_json()
            assert (befehl["aktion"], befehl["wert"], befehl["von_name"]) == ("sprung", 30, "Handy")
            assert [d["name"] for d in client.get("/api/remote/devices").json()] == ["Rechner", "Handy"]
        assert [d["id"] for d in rechner.receive_json()["geraete"]] == ["fenster-rechner"]

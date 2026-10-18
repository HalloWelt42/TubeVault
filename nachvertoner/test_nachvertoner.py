"""
Nachvertoner: Ablauf gegen nachgestellte Dienste (TubeVault, Vertonung, Kellerwolke); ffmpeg arbeitet echt. Geprüft
wird die Vermittlung: richtige Reihenfolge und Angaben, Stimmen nur aus Privat und Fremd, sichtbare Fehler, Abbruch,
Abholen, Aufräumen.

    nachvertoner/.venv/bin/python -m pytest nachvertoner -q
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nachvertoner as nv   # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg fehlt")
ZEIT = "7ce9880d-9f61-4220-ae2b-648076764afd"


def _clip(path: Path) -> bytes:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x180:rate=10",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(path)], check=True)
    return path.read_bytes()


class Buehne:
    """Merkt sich, was die Attrappen gesehen haben."""

    def __init__(self, clip: bytes, staende: list[dict], untertitel: dict | None = None, stimme: str = "Zeit Stimme"):
        self.clip, self.staende, self.untertitel, self.stimme = clip, staende, untertitel, stimme
        self.fortschritt: list[dict] = []
        self.ergebnis_tv = None
        self.gescheitert = None
        self.vertonen_daten = None
        self.abgebrochen = self.abgeholt = False
        self.gemeldet_stimmen = None
        self.fortschritt_status = 200
        self.offen = True

    def tubevault(self, r: httpx.Request) -> httpx.Response:
        p = r.url.path
        if p == "/api/dubbing/claim":
            if not self.offen:
                return httpx.Response(200, json={"request": None})
            self.offen = False
            return httpx.Response(200, json={
                "request": {"id": 7, "video_id": "abc", "title": "Ein Titel", "voice": self.stimme,
                            "source_language": None, "target_language": "de"},
                "media_url": "/api/player/abc", "result_url": "/api/dubbing/requests/7/result",
                "transcript_url": "/api/dubbing/requests/7/transcript"})
        if p == "/api/dubbing/requests/7/transcript":
            return httpx.Response(200, json={"transcript": self.untertitel} if self.untertitel else
                                  {"transcript": None, "reason": "Für dieses Video gibt es noch kein Transkript"})
        if p == "/api/player/abc":
            return httpx.Response(200, content=self.clip)
        if p.endswith("/progress"):
            self.fortschritt.append(json.loads(r.content))
            return httpx.Response(self.fortschritt_status, json={})
        if p.endswith("/result"):
            self.ergebnis_tv = r.content
            return httpx.Response(200, json={"ok": True})
        if p.endswith("/fail"):
            self.gescheitert = json.loads(r.content)
            return httpx.Response(200, json={})
        if p == "/api/dubbing/voices":
            self.gemeldet_stimmen = json.loads(r.content)["voices"]
            return httpx.Response(200, json={})
        if p == "/api/transcripts/ai/claim":
            return httpx.Response(200, json={"request": None})
        return httpx.Response(404)

    def vertonung(self, r: httpx.Request) -> httpx.Response:
        p = r.url.path
        if p == "/api/v1/verbindungen":
            return httpx.Response(200, json=[{"name": "Kellerwolke", "ok": True}, {"name": "Leitstelle", "ok": True}])
        if p == "/api/v1/stimmen":
            if r.url.params["bereich"] == "privat":
                return httpx.Response(200, json=[{"id": ZEIT, "name": "Zeit Stimme", "bereich": "privat"}])
            return httpx.Response(200, json=[{"id": "f1", "name": "Kerstin", "bereich": "fremd"}])
        if p == "/api/v1/dienst/vertonen":
            self.vertonen_daten = r.content
            return httpx.Response(201, json={"id": "a1", "zustand": "wartet"})
        if p == "/api/v1/auftraege/a1":
            st = self.staende.pop(0) if len(self.staende) > 1 else self.staende[0]
            return httpx.Response(200, json=st)
        if p == "/api/v1/auftraege/a1/abbrechen":
            self.abgebrochen = True
            return httpx.Response(200, json={})
        if p == "/api/v1/inhalt/plaene/p1/ergebnis":
            return httpx.Response(200, content=b"M4A-ERGEBNIS")
        if p == "/api/v1/dienst/a1/abgeholt":
            self.abgeholt = True
            return httpx.Response(200, json={"behalten": False})
        return httpx.Response(404)


FERTIG = {"zustand": "fertig", "ergebnis": {"plan_id": "p1", "ausgangssprache": "en"}}


@pytest.fixture
def bauen(tmp_path):
    clip = _clip(tmp_path / "clip.mp4")

    def _bauen(staende, **weiter):
        b = Buehne(clip, staende, **weiter)
        s = nv.Einstellungen(tubevault="http://tv", vertonung="https://vt", kellerwolke="http://kw", schluessel="k",
                             ca_datei=None, stimme="Zeit Stimme", transkription="Transkription", arbeit=tmp_path / "arbeit",
                             name="pi", abfrage_s=0, fortschritt_s=0)
        tv = nv.TubeVault(httpx.AsyncClient(base_url="http://tv", transport=httpx.MockTransport(b.tubevault)))
        vt = nv.Vertonung(httpx.AsyncClient(base_url="https://vt", transport=httpx.MockTransport(b.vertonung)))
        return nv.Nachvertoner(s, tv, vt, kellerwolke=None), b
    return _bauen


async def test_vollstaendiger_ablauf(bauen, tmp_path):
    n, b = bauen([{"zustand": "laeuft", "fortschritt": 0.5, "schritt": "Übersetzen"}, FERTIG])
    assert await n.schritt() is True
    assert b.gemeldet_stimmen == ["Kerstin", "Zeit Stimme"], "nur Klonstimmen, nie der Katalog des Sprachmodells"
    daten = b.vertonen_daten.decode("latin-1")
    assert ZEIT in daten and 'name="behalten"\r\n\r\nfalse' in daten and "ausgangssprache" not in daten
    assert {"progress": 0.515, "note": "Übersetzen"} in [{"progress": round(f["progress"], 3), "note": f["note"]}
                                                          for f in b.fortschritt if f["progress"] is not None]
    assert b"M4A-ERGEBNIS" in b.ergebnis_tv and b'name="source_language"\r\n\r\nen' in b.ergebnis_tv
    assert b.abgeholt and b.gescheitert is None
    assert not any((tmp_path / "arbeit").iterdir()), "Arbeitsordner ist aufgeräumt"


async def test_kurzer_ausfall_der_vertonung_bricht_nichts_ab(bauen, monkeypatch):
    """Ein Neustart der Vertonung (502) während des Wartens: weiter nachfragen statt scheitern."""
    monkeypatch.setattr(nv.asyncio, "sleep", _sofort)
    n, b = bauen([{"zustand": "laeuft", "fortschritt": 0.3, "schritt": "Sprechen"}, FERTIG])
    original, ausfaelle = b.vertonung, [2]

    def mit_ausfall(r: httpx.Request) -> httpx.Response:
        if r.url.path == "/api/v1/auftraege/a1" and ausfaelle[0]:
            ausfaelle[0] -= 1
            return httpx.Response(502)
        return original(r)
    n.vt = nv.Vertonung(httpx.AsyncClient(base_url="https://vt", transport=httpx.MockTransport(mit_ausfall)))
    await n.schritt()
    assert b.gescheitert is None and b.abgeholt and b.ergebnis_tv


async def _sofort(*_):
    return None


async def test_untertitel_gehen_als_segmente_mit(bauen):
    untertitel = {"language": "en", "kind": "manual", "segments": [{"start": 0.0, "end": 1.5, "text": "Hello there."}]}
    n, b = bauen([FERTIG], untertitel=untertitel)
    await n.schritt()
    daten = b.vertonen_daten.decode("utf-8", "replace")
    assert '"ende": 1.5' in daten and 'name="ausgangssprache"\r\n\r\nen' in daten
    assert b.fortschritt[0]["note"] == "Untertitel: Untertitel vom Autor"


async def test_fehler_wird_sichtbar_gemeldet(bauen):
    n, b = bauen([{"zustand": "fehler", "fehler": "Sprechdienst weg\nTraceback ..."}])
    await n.schritt()
    assert b.gescheitert == {"note": "RuntimeError: Sprechdienst weg", "skipped": False} and b.ergebnis_tv is None


async def test_unbekannte_stimme_scheitert_mit_auswahl(bauen):
    n, b = bauen([FERTIG], stimme="Gibtsnicht")
    n.s = nv.Einstellungen(**{**n.s.__dict__, "stimme": "Auch nicht"})
    await n.schritt()
    assert "Kerstin, Zeit Stimme" in b.gescheitert["note"] and b.vertonen_daten is None


async def test_entfernter_auftrag_bricht_in_der_vertonung_ab(bauen):
    n, b = bauen([{"zustand": "laeuft", "fortschritt": 0.1, "schritt": "Sprechen"}])
    b.fortschritt_status = 409
    await n.schritt()
    # schon das erste Lebenszeichen trifft auf 409: noch nichts hochgeladen, nichts abzubrechen
    assert b.vertonen_daten is None and b.ergebnis_tv is None and b.gescheitert is None


def test_stimme_waehlen():
    stimmen = {"Zeit Stimme": "z", "Kerstin": "k"}
    assert nv.stimme_waehlen(stimmen, "zeit", "Kerstin") == ("Zeit Stimme", "z")
    assert nv.stimme_waehlen(stimmen, None, "Kerstin") == ("Kerstin", "k")


class KellerwolkeAttrappe:
    def __init__(self, zustaende: list[str], transkript: dict):
        self.zustaende, self.transkript = zustaende, transkript
        self.weitergegeben = None
        self.geloescht: list[str] = []

    async def ich(self):
        return SimpleNamespace(zweig="Apps/Nachvertoner")

    async def ordner(self, pfad):
        return SimpleNamespace(id="o1", pfad=pfad)

    async def schreiben(self, pfad, inhalt, **_):
        assert Path(inhalt).is_file()
        return SimpleNamespace(id="t1", pfad=pfad)

    async def weitergeben(self, app, aktion, knoten_id, optionen=None):
        self.weitergegeben = (app, aktion, knoten_id, optionen)
        return SimpleNamespace(anfrage=SimpleNamespace(id="an1"))

    async def anfrage(self, anfrage_id):
        z = self.zustaende.pop(0) if len(self.zustaende) > 1 else self.zustaende[0]
        return SimpleNamespace(zustand=z, meldung="Hören")

    async def begleiter(self, knoten_id):
        return [SimpleNamespace(id="b1", rolle="transkript")]

    async def lesen_ganz(self, knoten_id):
        return json.dumps(self.transkript).encode()

    async def loeschen(self, knoten_id):
        self.geloescht.append(knoten_id)


async def test_ki_transkript_ueber_die_transkription(bauen):
    n, b = bauen([FERTIG])
    kw = KellerwolkeAttrappe(["laeuft", "fertig"], {"sprache": "en", "segmente": [
        {"start": 0.0, "ende": 1.2, "text": " Hello. "}, {"start": 1.2, "ende": 1.4, "text": "  "}]})
    n.kw = kw
    geliefert = {}

    def tv(r: httpx.Request) -> httpx.Response:
        p = r.url.path
        if p == "/api/transcripts/ai/claim":
            return httpx.Response(200, json={"request": {"video_id": "abc", "title": "T", "language": "en"},
                                             "media_url": "/api/player/abc", "result_url": "/api/transcripts/ai/abc/result",
                                             "progress_url": "/api/transcripts/ai/abc/progress", "fail_url": "/api/transcripts/ai/abc/fail"})
        if p == "/api/transcripts/ai/abc/result":
            geliefert.update(json.loads(r.content))
            return httpx.Response(200, json={})
        if p == "/api/dubbing/claim":
            return httpx.Response(200, json={"request": None})
        return b.tubevault(r)
    n.tv = nv.TubeVault(httpx.AsyncClient(base_url="http://tv", transport=httpx.MockTransport(tv)))
    assert await n.schritt() is True
    assert kw.weitergegeben == ("Transkription", "transkribieren", "t1", {"sprache": "en"})
    assert geliefert == {"language": "en", "segments": [{"start": 0.0, "end": 1.2, "text": "Hello."}]}
    assert kw.geloescht == ["t1"], "Ton samt Transkript in den Papierkorb"

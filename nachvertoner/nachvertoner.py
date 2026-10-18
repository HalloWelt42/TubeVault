"""
TubeVault - Nachvertoner

Eigenes Programm (Regel: Anbindungen an fremde Dienste sind eigene Programme). Es verbindet Dienste, die nichts
voneinander wissen, und läuft als Container auf dem Pi neben TubeVault:

    TubeVault       führt die Warteliste (Vertonungen, KI-Transkripte) und speichert Tonspuren und Transkripte
    Vertonung       vertont über ihren Dienst (POST /api/v1/dienst/vertonen); transkribiert bei Bedarf selbst
    Kellerwolke     Ablage für den Ton eines KI-Transkripts; die Transkription bekommt ihn als Weitergabe

Vertonen (je Auftrag):
    1. Auftrag bei TubeVault abholen, Untertitel der Quelle erfragen, Video laden, nur den Ton herauslösen.
    2. Ton an den Dienst der Vertonung (Stimme aus Privat oder Fremd, nie eine eingebaute des Sprachmodells; die
       Dateien bleiben nicht in der Kellerwolke: behalten=false).
    3. Fortschritt als Lebenszeichen an TubeVault; zieht TubeVault den Auftrag zurück, wird abgebrochen.
    4. Tonspur abliefern, der Vertonung "abgeholt" melden (dann liegt dort alles im Papierkorb).

KI-Transkript (nur wenn nichts zu vertonen ist):
    Ton in den eigenen Zweig der Kellerwolke, Weitergabe an die Transkription mit der Sprache des Videos, Transkript
    lesen, an TubeVault liefern, Ton samt Transkript in den Papierkorb der Kellerwolke.

Einstellungen aus der Umgebung (NACHVERTONER_...), der Schlüssel der Kellerwolke nur aus einer Datei.

    python nachvertoner.py              läuft dauerhaft
    python nachvertoner.py --einmal     höchstens ein Auftrag
    python nachvertoner.py --pruefen    Erreichbarkeit und Stimmen
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shutil
import ssl
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from appkern.kellerwolke import Kellerwolke, NichtErreichbar, pfad_aus

log = logging.getLogger("nachvertoner")
OHNE_FRIST = httpx.Timeout(None, connect=30)
UNTERTITEL_ARTEN = {"manual": "Untertitel vom Autor", "auto": "Untertitel der Quelle, automatisch", "ai": "KI-Transkript"}
WARTEN_TRANSKRIPT_S = 6 * 3600
ORIGINALSTIMMEN = "Originalstimmen"   # Wahl in TubeVault: je Sprecher seine eigene Stimme, die Vorgabestimme als Ersatz
TRANSKRIPT_ORDNER = "Transkripte"   # Arbeitsordner im eigenen Zweig der Kellerwolke, nur Arbeitskopien
AUSFALL_S = 15 * 60          # so lange gilt ein Dienst als kurz weg (Neustart, Ausrollen), bevor ein Auftrag scheitert


class Abbruch(Exception):
    """Der Auftrag wurde bei TubeVault entfernt oder neu vergeben."""


@dataclass(frozen=True)
class Einstellungen:
    tubevault: str
    vertonung: str
    kellerwolke: str
    schluessel: str
    ca_datei: str | None
    stimme: str
    transkription: str
    arbeit: Path
    name: str
    abfrage_s: int
    fortschritt_s: int

    @classmethod
    def aus_umgebung(cls) -> Einstellungen:
        e = os.environ
        datei = Path(e.get("NACHVERTONER_SCHLUESSEL_DATEI", "/geheim/schluessel"))
        if not datei.is_file():
            raise SystemExit(f"Schlüssel der Kellerwolke fehlt: {datei}")
        return cls(
            tubevault=e.get("NACHVERTONER_TUBEVAULT", "http://tubevault-backend:8031").rstrip("/"),
            vertonung=e.get("NACHVERTONER_VERTONUNG", "https://192.168.178.49:8641").rstrip("/"),
            kellerwolke=e.get("NACHVERTONER_KELLERWOLKE", "http://192.168.178.49:39278").rstrip("/"),
            schluessel=datei.read_text().strip(),
            ca_datei=e.get("NACHVERTONER_CA_DATEI") or None,
            stimme=e.get("NACHVERTONER_STIMME", "Zeit Stimme"),
            transkription=e.get("NACHVERTONER_TRANSKRIPTION", "Transkription"),
            arbeit=Path(e.get("NACHVERTONER_ARBEIT", "/arbeit")),
            name=e.get("NACHVERTONER_NAME", "pi"),
            abfrage_s=int(e.get("NACHVERTONER_ABFRAGE_S", "60")),
            fortschritt_s=int(e.get("NACHVERTONER_FORTSCHRITT_S", "15")),
        )


async def ffmpeg(*argumente: str) -> None:
    prozess = await asyncio.create_subprocess_exec("ffmpeg", "-nostdin", "-y", "-loglevel", "error", *argumente,
                                                   stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
    _, fehler = await prozess.communicate()
    if prozess.returncode != 0:
        raise RuntimeError(f"ffmpeg: {fehler.decode(errors='replace').strip()[-300:]}")


async def ton_herausloesen(video: Path, ziel_ordner: Path) -> Path:
    """Nur die Tonspur, unverändert (AAC bleibt AAC in .m4a); andere Kodierungen verlustarm als AAC 192 kbit/s."""
    ziel = ziel_ordner / "ton.m4a"
    try:
        await ffmpeg("-i", str(video), "-vn", "-map", "0:a:0", "-c:a", "copy", str(ziel))
    except RuntimeError:
        await ffmpeg("-i", str(video), "-vn", "-map", "0:a:0", "-c:a", "aac", "-b:a", "192k", str(ziel))
    return ziel


async def geduldig(aufruf, *, was: str, frist_s: float = AUSFALL_S, takt_s: float = 10.0):
    """Ein lesender Aufruf, der bei kurzen Ausfällen (Neustart, 502, keine Verbindung) wiederholt wird, bis zur Frist;
    die Aufträge der Vertonung und der Transkription laufen über einen Neustart hinweg weiter."""
    ende = time.monotonic() + frist_s
    while True:
        try:
            return await aufruf()
        except (httpx.TransportError, httpx.HTTPStatusError, NichtErreichbar) as f:
            if isinstance(f, httpx.HTTPStatusError) and f.response.status_code < 500:
                raise
            if time.monotonic() > ende:
                raise
            log.info("%s gerade nicht erreichbar (%s), neuer Versuch", was, type(f).__name__)
            await asyncio.sleep(takt_s)


class TubeVault:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.c = client

    async def abholen(self, name: str) -> dict | None:
        r = await self.c.post("/api/dubbing/claim", json={"worker": name}, timeout=30)
        return r.json() if r.status_code == 200 else None

    async def transkript_abholen(self, name: str) -> dict | None:
        r = await self.c.post("/api/transcripts/ai/claim", json={"worker": name}, timeout=30)
        return r.json() if r.status_code == 200 else None

    async def lebenszeichen(self, url: str, daten: dict) -> None:
        """409 heißt: Auftrag zurückgezogen. Ist TubeVault kurz nicht erreichbar (Neustart), läuft die Arbeit weiter."""
        try:
            r = await self.c.post(url, json=daten, timeout=30)
        except httpx.HTTPError as f:
            log.info("TubeVault gerade nicht erreichbar (%s), Arbeit läuft weiter", type(f).__name__)
            return
        if r.status_code == 409:
            raise Abbruch()

    async def scheitern(self, url: str, notiz: str, uebersprungen: bool = False) -> None:
        await self.c.post(url, json={"note": notiz[:480], "skipped": uebersprungen}, timeout=30)

    async def untertitel(self, url: str | None) -> tuple[dict | None, str]:
        """Untertitel der Quelle ({language, kind, segments}) oder None samt Grund."""
        if not url:
            return None, "keine Untertitel angeboten"
        try:
            r = await self.c.get(url, timeout=180)
            r.raise_for_status()
            antwort = r.json()
        except Exception as f:  # noqa: BLE001 - dann transkribiert die Vertonung selbst
            return None, f"Untertitel nicht erhalten ({type(f).__name__})"
        t = antwort.get("transcript")
        if not t or not t.get("segments"):
            return None, antwort.get("reason") or "keine Untertitel vorhanden"
        return t, UNTERTITEL_ARTEN.get(t.get("kind"), "vorhandenes Transkript")

    async def laden(self, url: str, ziel: Path) -> None:
        async with self.c.stream("GET", url) as r:
            r.raise_for_status()
            with ziel.open("wb") as datei:
                async for stueck in r.aiter_bytes(1024 * 1024):
                    datei.write(stueck)

    async def stimmen_melden(self, namen: list[str]) -> None:
        try:
            await self.c.post("/api/dubbing/voices", json={"voices": namen}, timeout=15)
        except httpx.HTTPError as f:
            log.debug("Stimmen nicht gemeldet (%s)", type(f).__name__)


class Vertonung:
    """Der Dienst der Vertonung (App-Schlüssel der Kellerwolke)."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.c = client

    async def problem(self) -> str | None:
        try:
            r = await self.c.get("/api/v1/verbindungen", timeout=15)
            r.raise_for_status()
        except httpx.HTTPError as f:
            return f"Vertonung nicht erreichbar ({type(f).__name__})"
        schlecht = [v["name"] for v in r.json() if not v.get("ok")]
        return f"Vertonung ohne {', '.join(schlecht)}" if schlecht else None

    async def beschaeftigt(self) -> bool:
        """Arbeitet die Vertonung gerade (für wen auch immer)? Dann warten KI-Transkripte: sie teilen sich die Rechner
        mit dem Sprechen und sollen nur freie Rechenzeit nutzen."""
        try:
            r = await self.c.get("/api/v1/app", timeout=15)
            return int(r.json().get("auftraege_laufend") or 0) > 0
        except (httpx.HTTPError, ValueError):
            return True

    async def stimmen(self) -> dict[str, str]:
        """Name -> Kennung der Klonstimmen (Privat, soweit erlaubt, und Fremd); nie der Katalog des Sprachmodells."""
        aus: dict[str, str] = {}
        for bereich in ("privat", "fremd"):
            r = await self.c.get("/api/v1/stimmen", params={"bereich": bereich}, timeout=60)
            if r.status_code == 200:
                aus |= {s["name"]: s["id"] for s in r.json()}
        return aus

    async def vertonen(self, ton: Path, name: str, ausgang: str | None, ziel: str, stimme_id: str,
                       segmente: list[dict] | None, original: bool = False) -> str:
        """`original`: je Sprecher seine Stimme aus dem Video (die Vertonung transkribiert dann selbst), `stimme_id`
        als Ersatz."""
        daten = {"name": name[:200], "sprache": ziel, "format": "m4a", "behalten": "false",
                 "stimme": json.dumps({"art": "klon", "knoten_id": stimme_id}),
                 "stimmen": "original" if original else "fest"}
        if ausgang:
            daten["ausgangssprache"] = ausgang
        if segmente:
            daten["segmente"] = json.dumps([{"start": s["start"], "ende": s["end"], "text": s["text"]} for s in segmente],
                                           ensure_ascii=False)
        with ton.open("rb") as datei:
            r = await self.c.post("/api/v1/dienst/vertonen", data=daten, files={"datei": (ton.name, datei, "audio/mp4")})
        r.raise_for_status()
        return r.json()["id"]

    async def stand(self, auftrag: str) -> dict:
        r = await self.c.get(f"/api/v1/auftraege/{auftrag}", timeout=30)
        r.raise_for_status()
        return r.json()

    async def abbrechen(self, auftrag: str) -> None:
        await self.c.post(f"/api/v1/auftraege/{auftrag}/abbrechen", timeout=30)

    async def ergebnis(self, plan_id: str, ziel: Path) -> None:
        async with self.c.stream("GET", f"/api/v1/inhalt/plaene/{plan_id}/ergebnis") as r:
            r.raise_for_status()
            with ziel.open("wb") as datei:
                async for stueck in r.aiter_bytes(1024 * 1024):
                    datei.write(stueck)

    async def abgeholt(self, auftrag: str) -> None:
        await self.c.post(f"/api/v1/dienst/{auftrag}/abgeholt", timeout=60)


def stimme_waehlen(stimmen: dict[str, str], gewuenscht: str | None, vorgabe: str) -> tuple[str, str]:
    """(Name, Kennung): gleicher Name, sonst Teil des Namens (ohne Groß- und Kleinschreibung), sonst die Vorgabe."""
    for wunsch in (gewuenscht, vorgabe):
        if not wunsch:
            continue
        w = wunsch.strip().lower()
        gleich = [n for n in stimmen if n.lower() == w]
        teil = [n for n in stimmen if w in n.lower() or n.lower() in w]
        if gleich or teil:
            name = (gleich or teil)[0]
            return name, stimmen[name]
    raise RuntimeError(f"Stimme '{gewuenscht or vorgabe}' gibt es in der Vertonung nicht "
                       f"(vorhanden: {', '.join(sorted(stimmen)) or 'keine'})")


class Nachvertoner:
    def __init__(self, s: Einstellungen, tubevault: TubeVault, vertonung: Vertonung, kellerwolke: Kellerwolke) -> None:
        self.s, self.tv, self.vt, self.kw = s, tubevault, vertonung, kellerwolke

    # --- Vertonen -----------------------------------------------------------------------------------------------

    async def vertonen(self, abgeholt: dict) -> None:
        job = abgeholt["request"]
        nr, video_id = job["id"], job["video_id"]
        titel = job.get("title") or video_id
        fortschritt_url = f"/api/dubbing/requests/{nr}/progress"
        ordner = self.s.arbeit / f"vertonen-{video_id}"
        ordner.mkdir(parents=True, exist_ok=True)
        auftrag = None

        async def melden(anteil: float | None, notiz: str) -> None:
            await self.tv.lebenszeichen(fortschritt_url, {"progress": anteil, "note": notiz})

        log.info("Vertonung %s: %s", nr, titel)
        try:
            untertitel, herkunft = await self.tv.untertitel(abgeholt.get("transcript_url"))
            await melden(0.02, f"Untertitel: {herkunft}" if untertitel else f"Ohne Untertitel: {herkunft}")
            # Sprache des Originals: vom Auftrag, sonst von den Untertiteln, sonst erkennt die Transkription sie
            ausgang = (job.get("source_language") or (untertitel or {}).get("language") or "").lower() or None
            ziel = job["target_language"].lower()
            original = (job.get("voice") or "").strip().lower() == ORIGINALSTIMMEN.lower()
            name, stimme_id = stimme_waehlen(await self.vt.stimmen(), None if original else job.get("voice"), self.s.stimme)
            await melden(0.03, "Video laden")
            video = ordner / "video"
            await self.tv.laden(abgeholt["media_url"], video)
            ton = await ton_herausloesen(video, ordner)
            video.unlink(missing_ok=True)
            await melden(0.06, "An die Vertonung")
            auftrag = await self.vt.vertonen(ton, titel, ausgang, ziel, stimme_id, (untertitel or {}).get("segments"), original)
            ergebnis = await self._verfolgen(auftrag, melden)
            await melden(0.96, "Tonspur abliefern")
            spur = ordner / f"{ziel}.m4a"
            await geduldig(lambda: self.vt.ergebnis(ergebnis["plan_id"], spur), was="Vertonung")
            erkannt = ergebnis.get("ausgangssprache") or ausgang or ""
            with spur.open("rb") as datei:
                r = await self.tv.c.post(abgeholt["result_url"], files={"file": (spur.name, datei, "audio/mp4")},
                                         data={"source_language": erkannt, "voice": ORIGINALSTIMMEN if original else name},
                                         timeout=OHNE_FRIST)
            r.raise_for_status()
            await geduldig(lambda: self.vt.abgeholt(auftrag), was="Vertonung")
            log.info("Vertonung %s fertig (%s, Stimme %s)", nr, erkannt or "Sprache unbekannt", name)
        except Abbruch:
            log.info("Vertonung %s wurde bei TubeVault entfernt, abgebrochen", nr)
            if auftrag:
                await self.vt.abbrechen(auftrag)
        except Exception as f:  # noqa: BLE001 - jeder Fehler geht sichtbar an TubeVault zurück
            log.exception("Vertonung %s fehlgeschlagen", nr)
            await self.tv.scheitern(f"/api/dubbing/requests/{nr}/fail", f"{type(f).__name__}: {f}")
        finally:
            shutil.rmtree(ordner, ignore_errors=True)

    async def _verfolgen(self, auftrag: str, melden) -> dict:
        """Bis der Auftrag der Vertonung endet; der Fortschritt belegt 8 bis 95 Prozent des Ganzen."""
        while True:
            st = await geduldig(lambda: self.vt.stand(auftrag), was="Vertonung")
            if st["zustand"] == "fertig":
                return st.get("ergebnis") or {}
            if st["zustand"] in ("fehler", "abgebrochen"):
                raise RuntimeError((st.get("fehler") or "Vertonung abgebrochen").strip().splitlines()[0])
            await melden(0.08 + 0.87 * float(st.get("fortschritt") or 0), st.get("schritt") or "Vertonen")
            await asyncio.sleep(self.s.fortschritt_s)

    # --- KI-Transkript ------------------------------------------------------------------------------------------

    async def transkribieren(self, abgeholt: dict) -> None:
        job = abgeholt["request"]
        video_id = job["video_id"]
        ordner = self.s.arbeit / f"transkript-{video_id}"
        ordner.mkdir(parents=True, exist_ok=True)
        knoten = None

        async def notiz(text: str) -> None:
            await self.tv.lebenszeichen(abgeholt["progress_url"], {"note": text})

        log.info("KI-Transkript: %s", job.get("title") or video_id)
        try:
            await notiz("Ton laden")
            video = ordner / "video"
            await self.tv.laden(abgeholt["media_url"], video)
            ton = await ton_herausloesen(video, ordner)
            video.unlink(missing_ok=True)
            ziel = await self._transkript_ordner()
            knoten = await self.kw.schreiben(pfad_aus(ziel.pfad, f"{video_id}.m4a"), ton, inhaltstyp="audio/mp4")
            sprache = (job.get("language") or "auto").lower()
            neu = await self.kw.weitergeben(self.s.transkription, "transkribieren", knoten.id, {"sprache": sprache})
            await notiz("Transkribieren")
            transkript = await self._transkript_abwarten(neu.anfrage.id, knoten.id, notiz)
            segmente = [{"start": s["start"], "end": s["ende"], "text": s["text"].strip()}
                        for s in transkript.get("segmente") or [] if s.get("text", "").strip()]
            erkannt = transkript.get("sprache") if transkript.get("sprache") not in (None, "", "auto") else job.get("language")
            if not segmente or not erkannt:
                raise RuntimeError("Die Transkription lieferte keinen Text oder keine Sprache")
            r = await self.tv.c.post(abgeholt["result_url"], json={"language": erkannt, "segments": segmente}, timeout=60)
            if r.status_code == 409:
                raise Abbruch()
            r.raise_for_status()
            log.info("KI-Transkript fertig: %s (%d Sätze, %s)", video_id, len(segmente), erkannt)
        except Abbruch:
            log.info("KI-Transkript für %s wurde bei TubeVault zurückgezogen", video_id)
        except Exception as f:  # noqa: BLE001
            log.exception("KI-Transkript für %s fehlgeschlagen", video_id)
            await self.tv.c.post(abgeholt["fail_url"], json={"note": f"{type(f).__name__}: {f}"[:480]}, timeout=30)
        finally:
            shutil.rmtree(ordner, ignore_errors=True)
            if knoten is not None:
                try:
                    await self.kw.loeschen(knoten.id)       # Papierkorb, samt Transkript (Begleiter)
                except Exception:  # noqa: BLE001
                    log.warning("Ton %s blieb in der Kellerwolke liegen", knoten.pfad)

    async def _transkript_ordner(self):
        return await self.kw.ordner(pfad_aus((await self.kw.ich()).zweig, TRANSKRIPT_ORDNER))

    async def aufraeumen(self) -> int:
        """Beim Start: was im Arbeitsordner der Kellerwolke liegt, ist der Ton eines abgebrochenen KI-Transkripts
        (Absturz, Neustart); er kommt samt Transkript in den Papierkorb. Nur eigene Arbeitskopien liegen dort."""
        ordner = await self._transkript_ordner()
        reste = [k async for k in self.kw.alle_kinder(ordner.id) if k.haupt_id is None]
        for k in reste:
            await self.kw.loeschen(k.id)
        if reste:
            log.info("Aufgeräumt: %d liegengebliebene Töne in den Papierkorb", len(reste))
        return len(reste)

    async def _transkript_abwarten(self, anfrage_id, knoten_id, notiz) -> dict:
        warten = 0
        while warten < WARTEN_TRANSKRIPT_S:
            a = await geduldig(lambda: self.kw.anfrage(anfrage_id), was="Kellerwolke")
            if a.zustand == "fertig":
                b = next((x for x in await self.kw.begleiter(knoten_id) if x.rolle == "transkript"), None)
                if b is None:
                    raise RuntimeError("Die Transkription meldete fertig, aber kein Transkript liegt neben dem Ton")
                return json.loads(await self.kw.lesen_ganz(b.id))
            if a.zustand in ("fehler", "abgebrochen"):
                raise RuntimeError(f"Transkription: {a.meldung or a.zustand}")
            await notiz(a.meldung or "Transkribieren")
            await asyncio.sleep(self.s.fortschritt_s)
            warten += self.s.fortschritt_s
        raise RuntimeError("Die Transkription hat in sechs Stunden kein Transkript geliefert")

    # --- Dauerbetrieb -------------------------------------------------------------------------------------------

    async def schritt(self) -> bool:
        """Ein Durchgang; True, wenn etwas bearbeitet wurde. Vertonungen gehen vor KI-Transkripten."""
        problem = await self.vt.problem()
        if problem:
            log.info("Pause: %s", problem)
            return False
        try:
            await self.tv.stimmen_melden([ORIGINALSTIMMEN, *sorted(await self.vt.stimmen())])
            abgeholt = await self.tv.abholen(self.s.name)
            if abgeholt and abgeholt.get("request"):
                await self.vertonen(abgeholt)
                return True
            if await self.vt.beschaeftigt():
                log.debug("Vertonung arbeitet, KI-Transkripte warten")
                return False
            transkript = await self.tv.transkript_abholen(self.s.name)
            if transkript and transkript.get("request"):
                await self.transkribieren(transkript)
                return True
        except httpx.HTTPError as f:
            log.info("TubeVault oder Vertonung nicht erreichbar (%s)", type(f).__name__)
        return False

    async def pruefen(self) -> int:
        problem = await self.vt.problem()
        print("Vertonung:", problem or "bereit")
        stimmen = await self.vt.stimmen() if not problem else {}
        print(f"Stimmen: {len(stimmen)}; Vorgabe {self.s.stimme}:",
              "vorhanden" if any(self.s.stimme.lower() in n.lower() for n in stimmen) else "fehlt")
        try:
            r = await self.tv.c.get("/api/dubbing/status", timeout=10)
            status = r.json()
            print("TubeVault: erreichbar, Nachvertonung", "eingeschaltet" if status.get("enabled") else "ausgeschaltet")
        except Exception as f:  # noqa: BLE001
            print("TubeVault:", f"{type(f).__name__}: {f}")
            return 1
        return 1 if problem else 0


def ssl_kontext(ca_datei: str | None) -> ssl.SSLContext | bool:
    return ssl.create_default_context(cafile=ca_datei) if ca_datei else True


async def haupt(args) -> int:
    s = Einstellungen.aus_umgebung()
    s.arbeit.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(base_url=s.tubevault, timeout=OHNE_FRIST) as tv, \
            httpx.AsyncClient(base_url=s.vertonung, timeout=OHNE_FRIST, verify=ssl_kontext(s.ca_datei),
                              headers={"Authorization": f"Bearer {s.schluessel}"}) as vt:
        kw = Kellerwolke(s.kellerwolke, s.schluessel)
        try:
            n = Nachvertoner(s, TubeVault(tv), Vertonung(vt), kw)
            if args.pruefen:
                return await n.pruefen()
            try:
                await n.aufraeumen()
            except Exception:  # noqa: BLE001 - die Kellerwolke kann beim Start fehlen; dann beim nächsten Start
                log.warning("Aufräumen in der Kellerwolke nicht möglich", exc_info=True)
            log.info("Nachvertoner '%s' bereit: TubeVault %s, Vertonung %s", s.name, s.tubevault, s.vertonung)
            while True:
                gearbeitet = await n.schritt()
                if args.einmal:
                    return 0
                if not gearbeitet:
                    await asyncio.sleep(s.abfrage_s)
        finally:
            await kw.schliessen()


def main() -> int:
    p = argparse.ArgumentParser(description="Nachvertoner für TubeVault")
    p.add_argument("--einmal", action="store_true", help="höchstens ein Auftrag, dann Ende")
    p.add_argument("--pruefen", action="store_true", help="nur Erreichbarkeit und Stimmen prüfen")
    p.add_argument("--ausfuehrlich", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.ausfuehrlich else logging.INFO, format="%(asctime)s %(message)s",
                        datefmt="%d.%m. %H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg fehlt")
    return asyncio.run(haupt(args))


if __name__ == "__main__":
    sys.exit(main())

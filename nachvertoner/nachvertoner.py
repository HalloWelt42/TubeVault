#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///
"""
TubeVault – Nachvertoner

Eigenes Programm für den Rechner, der vertonen kann (Mac). Es verbindet zwei
Dienste, die nichts voneinander wissen:

    TubeVault (Pi)        führt die Warteliste und speichert die Tonspuren
    Vertonungsdienst      transkribiert, übersetzt und spricht (lokal)

Ablauf je Auftrag:
    1. Warten, bis der Vertonungsdienst frei ist (kein laufender Auftrag).
    2. Auftrag bei TubeVault abholen, Video laden.
    3. Leichte Arbeitskopie bauen (Originalton + winziges Bild) - der Dienst
       braucht ein Video, das volle Bild wäre unnötige Last.
    4. Vertonung anstossen: eine feste Stimme, ein Sprecher.
    5. Fortschritt als Lebenszeichen an TubeVault melden.
    6. Deutsche Tonspur aus dem Ergebnis lösen und bei TubeVault abliefern.
    7. Arbeitsdateien hier und im Vertonungsdienst wieder entfernen.

Aufruf:
    ./nachvertoner.py                 läuft dauerhaft
    ./nachvertoner.py --einmal        höchstens ein Auftrag, dann Ende
    ./nachvertoner.py --pruefen       nur Erreichbarkeit und Stimme prüfen

Einstellungen: nachvertoner.toml neben diesem Skript (Vorlage:
nachvertoner.beispiel.toml).
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import socket
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
log = logging.getLogger("nachvertoner")

# Sprachkürzel von TubeVault → Sprachnamen des Vertonungsdienstes
LANGUAGE_NAMES = {"en": "english", "de": "german", "fr": "french", "es": "spanish", "it": "italian"}
LANGUAGE_CODES = {name: code for code, name in LANGUAGE_NAMES.items()}
PHASE_LABELS = {
    "audio": "Ton auslesen", "transcribe": "Transkribieren", "speakers": "Sprecher erkennen",
    "translate": "Übersetzen", "voices": "Stimme vorbereiten", "speak": "Sprechen", "mux": "Zusammenfügen",
}
NO_TIMEOUT = httpx.Timeout(None, connect=30)
# Herkunft eines Transkripts von TubeVault, so wie sie am Auftrag erscheint
TRANSCRIPT_KINDS = {"manual": "Untertitel vom Autor", "auto": "Untertitel der Quelle, automatisch",
                    "ai": "KI-Transkript"}
# Ton für die Spracherkennung: unkomprimiert, eine Spur, 16 kHz - genau das,
# womit die Erkennung rechnet; jedes andere Format würde dort erst umgerechnet
RECOGNITION_AUDIO = ("-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le")


class Abbruch(Exception):
    """Der Auftrag wurde bei TubeVault entfernt oder neu vergeben."""


class Uebersprungen(Exception):
    """Es gibt nichts zu tun (z.B. Material ist schon in der Zielsprache)."""


@dataclass
class Settings:
    tubevault_url: str
    dub_url: str
    worker_name: str
    work_dir: Path
    poll_seconds: int
    progress_seconds: int

    @classmethod
    def load(cls, path: Path) -> "Settings":
        if not path.exists():
            raise SystemExit(
                f"Einstellungen fehlen: {path}\n"
                f"Vorlage kopieren: cp {HERE / 'nachvertoner.beispiel.toml'} {path}")
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        work_dir = Path(raw.get("arbeitsordner") or HERE / "arbeit").expanduser()
        return cls(
            tubevault_url=raw["tubevault"]["url"].rstrip("/"),
            dub_url=raw["vertonungsdienst"]["url"].rstrip("/"),
            worker_name=raw.get("name") or socket.gethostname().split(".")[0],
            work_dir=work_dir,
            poll_seconds=int(raw.get("abfrage_sekunden", 60)),
            progress_seconds=int(raw.get("fortschritt_sekunden", 15)),
        )


# Ohne Angabe am Auftrag spricht die Stimme, deren Name so beginnt
DEFAULT_VOICE = "zeit"


class Nachvertoner:
    def __init__(self, settings: Settings):
        self.s = settings
        self.pi = httpx.Client(base_url=settings.tubevault_url, timeout=NO_TIMEOUT)
        self.dub = httpx.Client(base_url=settings.dub_url, timeout=NO_TIMEOUT)

    # ─── Vertonungsdienst ────────────────────────────────────────────

    def service_problem(self) -> str | None:
        """None, wenn der Dienst arbeitsbereit ist; sonst der Grund."""
        try:
            health = self.dub.get("/api/system/health", timeout=10).json()
        except httpx.HTTPError as e:
            return f"Vertonungsdienst nicht erreichbar ({e.__class__.__name__})"
        if not health.get("worker_online"):
            return "Sprach-Worker des Vertonungsdienstes läuft nicht"
        if not health.get("llm_online"):
            return "Sprachmodell für die Übersetzung ist nicht erreichbar"
        return None

    def service_busy(self) -> bool:
        return bool(self.dub.get("/api/jobs", timeout=10).json().get("active"))

    def voices(self) -> list[dict]:
        voices = self.dub.get("/api/voices", timeout=30).json()
        return voices.get("voices", voices) if isinstance(voices, dict) else voices

    def report_voices(self) -> None:
        """TubeVault mitteilen, welche Stimmen es gerade gibt - daraus wird
        dort die Auswahl beim Vormerken. Ein Fehlschlag hält nichts auf."""
        try:
            names = [str(v.get("name")) for v in self.voices() if v.get("name")]
            self.pi.post("/api/dubbing/voices", json={"voices": names}, timeout=15)
        except httpx.HTTPError as e:
            log.debug("Stimmen nicht gemeldet (%s)", e.__class__.__name__)

    def voice_id(self, name: str) -> str:
        voices = self.voices()
        wanted = name.strip().lower()
        exact = [v for v in voices if str(v.get("name", "")).strip().lower() == wanted]
        partial = [v for v in voices if wanted in str(v.get("name", "")).lower()]
        match = (exact or partial or [None])[0]
        if not match:
            known = ", ".join(sorted(str(v.get("name")) for v in voices)) or "keine"
            raise RuntimeError(f"Stimme '{name}' gibt es im Vertonungsdienst nicht (vorhanden: {known})")
        return match["id"]

    def upload(self, path: Path, mime: str = "video/mp4") -> str:
        with path.open("rb") as fh:
            r = self.dub.post("/api/files/upload", files={"files": (path.name, fh, mime)})
        body = r.json()
        if r.status_code == 409:   # inhaltsgleiche Datei liegt schon dort
            return body["detail"]["existing_file"]["id"]
        r.raise_for_status()
        first = body[0] if isinstance(body, list) else (body.get("files") or [body])[0]
        return first["id"]

    def remove_remote(self, *file_ids: str | None) -> None:
        for file_id in filter(None, file_ids):
            try:
                self.dub.delete(f"/api/files/{file_id}", timeout=30)
            except httpx.HTTPError:
                log.warning("Datei %s blieb im Vertonungsdienst liegen", file_id)

    # ─── TubeVault ───────────────────────────────────────────────────

    def claim(self) -> dict | None:
        return self.pi.post("/api/dubbing/claim", json={"worker": self.s.worker_name}, timeout=30).json()

    def heartbeat(self, url: str, payload: dict) -> None:
        """Lebenszeichen an TubeVault. 409 heißt: Auftrag zurückgezogen -
        abbrechen. Ist TubeVault kurz nicht erreichbar (Neustart), läuft die
        Arbeit weiter; das nächste Lebenszeichen kommt ja gleich."""
        try:
            r = self.pi.post(url, json=payload, timeout=30)
        except httpx.HTTPError as e:
            log.info("TubeVault gerade nicht erreichbar (%s) - Arbeit läuft weiter", e.__class__.__name__)
            return
        if r.status_code == 409:
            raise Abbruch()

    def report(self, request_id: int, progress: float | None, note: str | None) -> None:
        self.heartbeat(f"/api/dubbing/requests/{request_id}/progress", {"progress": progress, "note": note})

    def fail(self, request_id: int, note: str, skipped: bool = False) -> None:
        self.pi.post(f"/api/dubbing/requests/{request_id}/fail",
                     json={"note": note[:480], "skipped": skipped}, timeout=30)

    def source_transcript(self, claimed: dict, request_id: int) -> dict | None:
        """Fertiges Transkript von TubeVault (Untertitel der Quelle):
        {language, kind, segments}. Gibt es keines, transkribiert der Dienst
        selbst - der Grund wird am Auftrag sichtbar gemeldet."""
        url = claimed.get("transcript_url")
        if not url:
            return None
        try:
            response = self.pi.get(url, timeout=180)
            response.raise_for_status()
            answer = response.json()
        except Exception as e:
            answer = {"reason": f"Transkript nicht erhalten ({e.__class__.__name__})"}
        transcript = answer.get("transcript")
        if not transcript or not transcript.get("segments"):
            reason = answer.get("reason") or "kein Transkript vorhanden"
            log.info("Kein Transkript von TubeVault: %s - der Dienst transkribiert selbst", reason)
            self.report(request_id, 0.03, f"Ohne Untertitel: {reason}")
            return None
        kind = TRANSCRIPT_KINDS.get(transcript.get("kind"), "vorhandenes Transkript")
        log.info("Transkript von TubeVault (%s): %d Sätze", kind, len(transcript["segments"]))
        self.report(request_id, 0.03, f"Vorhandenes Transkript verwendet ({kind})")
        return transcript

    # ─── Ein Auftrag ─────────────────────────────────────────────────

    def process(self, claimed: dict) -> None:
        job = claimed["request"]
        request_id, video_id = job["id"], job["video_id"]
        title = job.get("title") or video_id
        folder = self.s.work_dir / video_id
        folder.mkdir(parents=True, exist_ok=True)
        source_id = result_id = dub_job_id = None
        log.info("Auftrag %s: %s", request_id, title)
        try:
            # Untertitel der Quelle ersparen dem Dienst das Transkribieren und
            # sagen zugleich, in welcher Sprache das Original gesprochen ist
            transcript = self.source_transcript(claimed, request_id)
            # Sprache des Originals: vom Auftrag, sonst vom Transkript, sonst
            # erkennt der Dienst sie selbst ("auto"). Raten wäre falsch: ein
            # deutsches Video als Englisch transkribiert ergibt Unsinn.
            source = (job.get("source_language") or (transcript or {}).get("language") or "auto").lower()
            target = job["target_language"].lower()
            # source == target ist gewollt: neu sprechen mit anderer Stimme.
            # Der Dienst übersetzt dann nicht.
            voice_id = self.voice_id(job.get("voice") or DEFAULT_VOICE)

            self.report(request_id, 0.02, "Video laden")
            original = folder / "original.mp4"
            with self.pi.stream("GET", claimed["media_url"]) as r:
                r.raise_for_status()
                with original.open("wb") as fh:
                    for chunk in r.iter_bytes(1024 * 1024):
                        fh.write(chunk)

            self.report(request_id, 0.05, "Arbeitskopie bauen")
            proxy = folder / f"tubevault_{video_id}.mp4"
            build_proxy(original, proxy)
            original.unlink(missing_ok=True)

            payload = {
                "source_language": LANGUAGE_NAMES.get(source, source),   # "auto" bleibt "auto"
                "target_language": LANGUAGE_NAMES.get(target, target),
                "mode": "fixed", "voice_id": voice_id,
                "num_speakers": 1,   # eine Stimme, keine Aufteilung nach Sprechern
            }
            if transcript:
                payload["source_segments"] = transcript["segments"]

            source_id = self.upload(proxy)
            payload["file_id"] = source_id
            created = self.dub.post("/api/jobs", json={
                "type": "video_dub", "label": f"TubeVault: {title[:80]}",
                "payload": payload,
            })
            created.raise_for_status()
            dub_job_id = created.json()["id"]

            result = self.wait_for(dub_job_id, request_id)
            result_id = result.get("video_id")
            self.report(request_id, 0.96, "Tonspur abliefern")
            dubbed = folder / "vertont.mp4"
            with self.dub.stream("GET", f"/api/files/{result_id}/download") as r:
                r.raise_for_status()
                with dubbed.open("wb") as fh:
                    for chunk in r.iter_bytes(1024 * 1024):
                        fh.write(chunk)
            track = folder / f"{target}.m4a"
            run_ffmpeg("-i", str(dubbed), "-vn", "-c:a", "copy", str(track))

            if source == "auto":
                # Der Dienst hat die Sprache erkannt; TubeVault bekommt das Kürzel
                source = LANGUAGE_CODES.get(str(result.get("source_language") or "").lower(), "")
            with track.open("rb") as fh:
                done = self.pi.post(
                    claimed["result_url"], files={"file": (track.name, fh, "audio/mp4")},
                    data={"source_language": source, "voice": job.get("voice") or ""})
            done.raise_for_status()
            missing = result.get("coverage_failed") or 0
            log.info("Auftrag %s fertig%s", request_id,
                     f" ({missing} Abschnitte ohne Ton)" if missing else "")
        except Abbruch:
            log.info("Auftrag %s wurde bei TubeVault entfernt - abgebrochen", request_id)
            if dub_job_id:
                self.dub.post(f"/api/jobs/{dub_job_id}/cancel", timeout=30)
        except Uebersprungen as e:
            log.info("Auftrag %s übersprungen: %s", request_id, e)
            self.fail(request_id, str(e), skipped=True)
        except Exception as e:   # jeder Fehler geht sichtbar an TubeVault zurück
            log.exception("Auftrag %s fehlgeschlagen", request_id)
            self.fail(request_id, f"{e.__class__.__name__}: {e}")
        finally:
            shutil.rmtree(folder, ignore_errors=True)
            self.remove_remote(source_id, result_id)

    def wait_for(self, dub_job_id: str, request_id: int) -> dict:
        """Auf das Ende der Vertonung warten und den Fortschritt weitermelden."""
        while True:
            state = self.dub.get(f"/api/jobs/{dub_job_id}", timeout=30).json()
            status = state.get("status")
            if status == "done":
                return state.get("result") or {}
            if status in ("error", "cancelled"):
                reason = (state.get("error") or "Vertonung abgebrochen").strip().splitlines()[0]
                raise RuntimeError(reason)
            label = PHASE_LABELS.get(state.get("phase"), state.get("progress_label") or "Vertonen")
            # Vertonung belegt den Bereich 8 % bis 95 % des gesamten Auftrags
            self.report(request_id, 0.08 + 0.87 * float(state.get("progress") or 0), label)
            time.sleep(self.s.progress_seconds)

    # ─── KI-Transkript ───────────────────────────────────────────────
    #
    # Videos ohne Transkript: TubeVault vergibt immer das zuletzt geladene.
    # Abgeholt wird nur, wenn der Vertonungsdienst frei ist und nichts zu
    # vertonen ansteht - Vertonungen sind ausdrückliche Wünsche, Transkripte
    # füllen die Suche im Hintergrund mit freier Rechenzeit.

    def claim_transcript(self) -> dict | None:
        return self.pi.post("/api/transcripts/ai/claim",
                            json={"worker": self.s.worker_name}, timeout=30).json()

    def process_transcript(self, claimed: dict) -> None:
        job = claimed["request"]
        video_id = job["video_id"]
        title = job.get("title") or video_id
        folder = self.s.work_dir / f"ki_{video_id}"
        folder.mkdir(parents=True, exist_ok=True)
        source_id = dub_job_id = None
        log.info("KI-Transkript: %s", title)

        def note(text: str) -> None:
            self.heartbeat(claimed["progress_url"], {"note": text})

        try:
            note("Ton laden")
            original = folder / "original.mp4"
            with self.pi.stream("GET", claimed["media_url"]) as r:
                r.raise_for_status()
                with original.open("wb") as fh:
                    for chunk in r.iter_bytes(1024 * 1024):
                        fh.write(chunk)
            # Nur der Ton geht zum Dienst, klein als Mono mit 16 kHz
            audio = folder / f"tubevault_{video_id}.wav"
            run_ffmpeg("-i", str(original), *RECOGNITION_AUDIO, str(audio))
            original.unlink(missing_ok=True)
            source_id = self.upload(audio, mime="audio/wav")

            # Bekannte Sprache vorgeben, sonst erkennt der Dienst sie selbst
            language = LANGUAGE_NAMES.get((job.get("language") or "").lower(), "auto")
            created = self.dub.post("/api/jobs", json={
                "type": "transcribe", "label": f"TubeVault-Transkript: {title[:80]}",
                "payload": {"file_id": source_id, "language": language},
            })
            created.raise_for_status()
            dub_job_id = created.json()["id"]
            note("Transkribieren")
            while True:
                state = self.dub.get(f"/api/jobs/{dub_job_id}", timeout=30).json()
                if state.get("status") == "done":
                    result = state.get("result") or {}
                    break
                if state.get("status") in ("error", "cancelled"):
                    raise RuntimeError((state.get("error") or "Transkription abgebrochen").strip().splitlines()[0])
                note(state.get("progress_label") or "Transkribieren")
                time.sleep(self.s.progress_seconds)

            transcription = self.dub.get(f"/api/transcribe/{result['transcription_id']}", timeout=30).json()
            raw = transcription.get("segments") or []
            if isinstance(raw, str):
                raw = json.loads(raw or "[]")
            segments = [{"start": float(s["start"]), "end": float(s["end"]), "text": str(s.get("text", "")).strip()}
                        for s in raw if str(s.get("text", "")).strip()]
            detected = LANGUAGE_CODES.get(str(transcription.get("language") or "").lower()) \
                or (job.get("language") or "")
            if not segments or not detected:
                raise RuntimeError("Die Spracherkennung lieferte keinen Text oder keine Sprache")
            done = self.pi.post(claimed["result_url"], json={"language": detected, "segments": segments}, timeout=60)
            if done.status_code == 409:
                raise Abbruch()
            done.raise_for_status()
            log.info("KI-Transkript fertig: %s (%d Sätze, %s)", title, len(segments), detected)
        except Abbruch:
            log.info("KI-Transkript für %s wurde bei TubeVault zurückgezogen", video_id)
            if dub_job_id:
                self.dub.post(f"/api/jobs/{dub_job_id}/cancel", timeout=30)
        except Exception as e:   # jeder Fehler geht sichtbar an TubeVault zurück
            log.exception("KI-Transkript für %s fehlgeschlagen", video_id)
            self.pi.post(claimed["fail_url"], json={"note": f"{e.__class__.__name__}: {e}"[:480]}, timeout=30)
        finally:
            shutil.rmtree(folder, ignore_errors=True)
            # Löscht im Dienst auch die zugehörige Transkription mit
            self.remove_remote(source_id)

    # ─── Dauerbetrieb ────────────────────────────────────────────────

    def step(self) -> bool:
        """Einen Durchgang. True, wenn ein Auftrag bearbeitet wurde."""
        problem = self.service_problem()
        if problem:
            log.info("Pause: %s", problem)
            return False
        self.report_voices()
        if self.service_busy():
            log.debug("Vertonungsdienst ist beschäftigt")
            return False
        try:
            claimed = self.claim()
            if not claimed or not claimed.get("request"):
                # Nichts zu vertonen: ein KI-Transkript abarbeiten
                transcript = self.claim_transcript()
                if transcript and transcript.get("request"):
                    self.process_transcript(transcript)
                    return True
                return False
        except httpx.HTTPError as e:
            log.info("TubeVault nicht erreichbar (%s)", e.__class__.__name__)
            return False
        self.process(claimed)
        return True

    def check(self) -> int:
        problem = self.service_problem()
        print("Vertonungsdienst:", problem or "bereit")
        try:
            status = self.pi.get("/api/dubbing/status", timeout=10).json()
            print("TubeVault: erreichbar, Nachvertonung",
                  "eingeschaltet" if status["enabled"] else "ausgeschaltet",
                  f"- {status['counts']['queued']} warten")
            if not problem:
                self.report_voices()
                choice = self.pi.get("/api/dubbing/voices", timeout=10).json()
                print(f"Stimmen an TubeVault gemeldet: {len(choice['voices'])}, "
                      f"Vorauswahl: {choice['default'] or 'keine'}")
        except Exception as e:
            print("TubeVault:", f"{e.__class__.__name__}: {e}")
            return 1
        return 1 if problem else 0


def run_ffmpeg(*args: str) -> None:
    result = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg: {result.stderr.strip()[-300:]}")


def build_proxy(original: Path, proxy: Path) -> None:
    """Originalton plus winziges schwarzes Bild. Der Vertonungsdienst verlangt
    eine Bildspur; das echte Bild würde nur Platz und Rechenzeit kosten."""
    run_ffmpeg(
        "-i", str(original), "-f", "lavfi", "-i", "color=c=black:s=64x36:r=5",
        "-map", "1:v:0", "-map", "0:a:0", "-shortest",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", str(proxy))


def main() -> int:
    parser = argparse.ArgumentParser(description="Nachvertoner für TubeVault")
    parser.add_argument("--einstellungen", type=Path, default=HERE / "nachvertoner.toml")
    parser.add_argument("--einmal", action="store_true", help="höchstens ein Auftrag, dann Ende")
    parser.add_argument("--pruefen", action="store_true", help="nur Erreichbarkeit und Stimme prüfen")
    parser.add_argument("--ausfuehrlich", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.ausfuehrlich else logging.INFO,
                        format="%(asctime)s %(message)s", datefmt="%d.%m. %H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg fehlt (brew install ffmpeg)")

    settings = Settings.load(args.einstellungen)
    worker = Nachvertoner(settings)
    if args.pruefen:
        return worker.check()

    log.info("Nachvertoner '%s' bereit - TubeVault %s, Vertonungsdienst %s",
             settings.worker_name, settings.tubevault_url, settings.dub_url)
    while True:
        worked = worker.step()
        if args.einmal:
            return 0
        if not worked:
            time.sleep(settings.poll_seconds)


if __name__ == "__main__":
    sys.exit(main())

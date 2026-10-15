"""
TubeVault - Nachvertonung: Schritte eines laufenden Auftrags v1.0.0

Der Nachvertoner meldet mit jedem Lebenszeichen nur zwei Angaben: den
Gesamtfortschritt (0..1) und eine kurze Notiz, was er gerade tut
(nachvertoner/nachvertoner.py). Daraus leitet dieses Modul die fünf
Schritte ab, die die Oberfläche zeigt - ohne etwas hinzuzuerfinden:

  - Welcher Schritt läuft, sagt die Notiz (feste Bezeichnungen des
    Nachvertoners). Ist sie unbekannt, entscheidet der Fortschritt.
  - Wie weit der Schritt ist, folgt aus dem Fortschritt innerhalb seines
    Abschnitts. Die Abschnitte ergeben sich aus der Aufteilung des
    Nachvertoners: bis 8 % eigene Vorarbeit, danach 8 % + 87 % des
    Vertonungsdienstes mit dessen Phasen (Ton 3-10 %, Transkript und
    Sprecher bis 30 %, Übersetzen bis 44 %, Sprechen 45-90 %, Video bauen
    ab 92 %), ab 96 % das Abliefern der Tonspur.
  - Die Restzeit eines Schritts schätzt StepClock aus dem Tempo, das der
    Schritt seit seinem Beginn zeigt. Ohne gemessenes Tempo gibt es keine
    Angabe.
"""
from dataclasses import dataclass
from typing import Literal, NamedTuple, Optional

from pydantic import BaseModel

StepState = Literal["done", "current", "pending"]


class StepDef(NamedTuple):
    key: str
    label: str
    start: float                 # Gesamtfortschritt, ab dem der Schritt läuft
    notes: tuple[str, ...]       # Notizen des Nachvertoners (Anfang der Notiz) in diesem Schritt


def _overall(service_share: float) -> float:
    """Anteil des Vertonungsdienstes in den Gesamtfortschritt umrechnen."""
    return round(0.08 + 0.87 * service_share, 3)


STEPS: tuple[StepDef, ...] = (
    StepDef("fetch", "Ton holen", 0.0,
            ("Video laden", "Arbeitskopie bauen", "Ton auslesen", "Ohne Untertitel",
             "Vorhandenes Transkript verwendet")),
    StepDef("understand", "Verstehen", _overall(0.10), ("Transkribieren", "Sprecher erkennen")),
    StepDef("translate", "Übersetzen", _overall(0.30), ("Übersetzen",)),
    StepDef("speak", "Sprechen", _overall(0.44), ("Stimme vorbereiten", "Sprechen")),
    StepDef("mix", "Mischen", _overall(0.90), ("Zusammenfügen", "Tonspur abliefern")),
)


class DubStep(BaseModel):
    key: str
    label: str
    state: StepState
    percent: Optional[int] = None      # nur beim laufenden Schritt


def step_index(progress: float, note: Optional[str]) -> int:
    """Index des laufenden Schritts: nach der Notiz, sonst nach dem Fortschritt."""
    text = (note or "").strip().lower()
    if text:
        for index, step in enumerate(STEPS):
            if any(text.startswith(known.lower()) for known in step.notes):
                return index
    current = 0
    for index, step in enumerate(STEPS):
        if progress >= step.start:
            current = index
    return current


def step_end(index: int) -> float:
    return STEPS[index + 1].start if index + 1 < len(STEPS) else 1.0


def step_percent(index: int, progress: float) -> int:
    """Fortschritt innerhalb des Schritts in Prozent (0..100)."""
    start, end = STEPS[index].start, step_end(index)
    share = (progress - start) / (end - start) if end > start else 0.0
    return int(max(0.0, min(1.0, share)) * 100)


def steps_for(progress: float, note: Optional[str]) -> list[DubStep]:
    """Die fünf Schritte eines laufenden Auftrags mit ihrem Stand."""
    current = step_index(progress, note)
    return [
        DubStep(key=step.key, label=step.label,
                state="done" if index < current else "current" if index == current else "pending",
                percent=step_percent(index, progress) if index == current else None)
        for index, step in enumerate(STEPS)
    ]


def activity(note: Optional[str], progress: float) -> Optional[str]:
    """Die Notiz des Nachvertoners, wenn sie mehr sagt als der Schrittname."""
    text = (note or "").strip()
    if not text:
        return None
    label = STEPS[step_index(progress, text)].label
    return None if text.lower() == label.lower() else text


# ─── Restzeit eines Schritts ───────────────────────────────────────────

# Erst nach dieser Beobachtungszeit im Schritt gibt es eine Schätzung
MIN_OBSERVED_SECONDS = 30


@dataclass
class _Arrival:
    step: str
    at: float            # Zeitpunkt (monotone Uhr), zu dem der Schritt zuerst gesehen wurde
    progress: float      # Gesamtfortschritt zu diesem Zeitpunkt


class StepClock:
    """Merkt sich je laufendem Auftrag, wann er im aktuellen Schritt zuerst
    gesehen wurde und mit welchem Fortschritt. Daraus folgt das Tempo des
    Schritts und seine Restzeit. Nur im Speicher: nach einem Neustart
    beginnt die Messung mit dem nächsten Lebenszeichen neu."""

    def __init__(self) -> None:
        self._seen: dict[tuple[int, str], _Arrival] = {}

    def observe(self, request_id: int, claimed_at: str, progress: float,
                note: Optional[str], now: float) -> None:
        key = (request_id, claimed_at or "")
        step = STEPS[step_index(progress, note)].key
        known = self._seen.get(key)
        if known is None or known.step != step:
            self._seen[key] = _Arrival(step=step, at=now, progress=progress)

    def remaining(self, request_id: int, claimed_at: str, progress: float,
                  note: Optional[str], now: float) -> Optional[int]:
        """Geschätzte Sekunden bis zum Ende des laufenden Schritts, sonst None."""
        index = step_index(progress, note)
        known = self._seen.get((request_id, claimed_at or ""))
        if known is None or known.step != STEPS[index].key:
            return None
        elapsed, gained = now - known.at, progress - known.progress
        if elapsed < MIN_OBSERVED_SECONDS or gained <= 0:
            return None
        left = max(0.0, step_end(index) - progress)
        return int(round(elapsed / gained * left))

    def keep_only(self, running: set[tuple[int, str]]) -> None:
        """Einträge beendeter Aufträge vergessen."""
        for key in [k for k in self._seen if k not in running]:
            del self._seen[key]

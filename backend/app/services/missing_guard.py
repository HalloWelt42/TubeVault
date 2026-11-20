"""Schutz vor falschen Fehlmeldungen bei nicht erreichbarem Bestand (NETZ-28).

Liegt der Bestand auf einem Netzlaufwerk oder einer externen Platte, sieht ein fehlendes oder halb eingehängtes
Laufwerk für einen Abgleich genauso aus wie viele gelöschte Dateien. Deshalb gilt für jede Stelle, die Einträge als
fehlend markiert oder austrägt (Videos ohne Datei, Musiksammlung, eigene Videos), dieselbe Regel:

- Der Ordner muss erreichbar sein und mindestens einen Eintrag haben; ein leerer Einhängepunkt zählt nicht.
- Fehlt auf einmal mehr als ein kleiner Anteil, ist das kein echtes Verschwinden, sondern ein Laufwerk, das nicht
  (ganz) da ist.

Trifft eines davon zu, bleibt der Stand unverändert, und der Grund steht im Protokoll. Einzelne fehlende Dateien
werden wie bisher markiert.
"""
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

# Bis hierhin gilt Fehlendes immer als echt (Einzelfälle, kleine Bestände) ...
ALWAYS_ALLOWED = 25
# ... darüber nur, wenn es höchstens dieser Anteil des Bestands ist
MAX_SHARE = 0.02


@dataclass(frozen=True)
class Verdict:
    """Ob ein Abgleich Fehlendes markieren darf, und wenn nicht, warum."""
    allowed: bool
    missing: int
    total: int
    reason: str = ""


def root_reachable(root: Path) -> bool:
    """True, wenn der Ordner lesbar ist und mindestens einen Eintrag hat."""
    try:
        with os.scandir(root) as entries:
            return any(True for _ in entries)
    except OSError:
        return False


def unreachable_roots(roots: Iterable[Path]) -> list[Path]:
    """Die Ordner aus roots, die nicht erreichbar oder leer sind."""
    return [root for root in roots if not root_reachable(root)]


def judge(missing: int, total: int, roots: Iterable[Path], what: str) -> Verdict:
    """Entscheidet, ob missing von total Einträgen als fehlend gelten dürfen.

    roots sind die Ordner, in denen die Dateien liegen müssten; what benennt den Abgleich im Protokoll.
    """
    if missing == 0:
        return Verdict(True, 0, total)
    gone = unreachable_roots(roots)
    if gone:
        reason = "Ordner nicht erreichbar oder leer: " + ", ".join(str(root) for root in gone)
    elif missing > ALWAYS_ALLOWED and missing > total * MAX_SHARE:
        reason = (f"{missing} von {total} fehlen auf einmal (mehr als {MAX_SHARE:.0%}); "
                  "das Laufwerk ist vermutlich nicht vollständig erreichbar")
    else:
        return Verdict(True, missing, total)
    logger.warning(f"[BESTAND] {what}: nichts als fehlend markiert, {reason}")
    return Verdict(False, missing, total, reason)

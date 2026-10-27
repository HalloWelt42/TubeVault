"""
TubeVault - Sicherung der Datenbank: Anlass und Ergebnis eines Laufs (services/sicherung.py)
"""
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class Anlass(str, Enum):
    """Wer die Sicherung anstößt; davon hängt ab, ob eine neue fällig ist."""
    HAND = "hand"                    # Knopf "Jetzt sichern": fällig, sofern sich etwas geändert hat
    REGELMAESSIG = "regelmaessig"    # Zeitplan: frühestens am sicherung_abstand_tage-ten Kalendertag nach der jüngsten
    AUSROLLEN = "ausrollen"          # vor dem Ausrollen: nur, wenn die jüngste älter ist als sicherung_vor_ausrollen_ab_stunden


class Ausgang(str, Enum):
    """Was der Lauf getan hat (aufgeräumt wird in jedem Fall)."""
    ANGELEGT = "angelegt"            # neue Sicherung angelegt
    NICHT_FAELLIG = "nicht_faellig"  # die jüngste ist für diesen Anlass jung genug
    UNVERAENDERT = "unveraendert"    # die Datenbank hat sich seit der jüngsten nicht geändert


class SicherungsLauf(BaseModel):
    """Ergebnis eines Laufs, für Oberfläche und scripts/backup_db.sh."""
    anlass: Anlass
    ausgang: Ausgang
    meldung: str                         # Klartext für Hinweis und Protokoll
    filename: Optional[str] = None       # die angelegte Sicherung
    size: Optional[int] = None
    entfernt: list[str] = []             # beim Aufräumen entfernte ältere Stände

"""
TubeVault – Eigene Videos: Datenmodell

Alte Dateien aus früheren Sammlungen werden eingelesen, mit Bibliothek und
Feed abgeglichen und dann eingeordnet. Der Stand jeder Datei liegt in der
Datenbank (own_files) und bleibt über Neustarts erhalten.
"""
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class Finding(str, Enum):
    """Was der Abgleich über eine Datei weiß."""
    PENDING = "pending"        # noch nicht geprüft
    DUPLICATE = "duplicate"    # liegt schon in der Bibliothek
    CERTAIN = "certain"        # das Quellvideo ist sicher bekannt, aber nicht in der Bibliothek
    PROBABLE = "probable"      # wahrscheinlich ein bekanntes Video, nicht bestätigt
    UNKNOWN = "unknown"        # kein Treffer


class MatchReason(str, Enum):
    """Woran der Treffer erkannt wurde."""
    SOURCE_ID = "source_id"              # Kennung der Quelle im Dateinamen
    SAME_FILE = "same_file"              # gleiche Dauer und gleiche Größe
    TITLE_DURATION = "title_duration"    # gleicher Titel und gleiche Dauer
    TITLE = "title"                      # gleicher Titel, Dauer nicht bestätigt
    SIMILAR_TITLE = "similar_title"      # ähnlicher Titel im vermuteten Kanal


class Decision(str, Enum):
    """Was mit der Datei geschehen ist."""
    OPEN = "open"
    DELETED = "deleted"        # alte Datei gelöscht (war doppelt)
    ADOPTED = "adopted"        # als Quellvideo in die Bibliothek übernommen
    OWN = "own"                # als eigenes Video einem Kanal zugeordnet
    REPLACED = "replaced"      # hat die Datei eines Bibliotheksvideos ersetzt
    SKIPPED = "skipped"


class ScanState(str, Enum):
    IDLE = "idle"              # nicht in Arbeit (fertig oder nie eingelesen)
    QUEUED = "queued"          # wartet auf den Einleser (auch nach einem Neustart)
    RUNNING = "running"
    PAUSED = "paused"          # vom Nutzer angehalten


class ScanPhase(str, Enum):
    LISTING = "listing"        # Dateien werden gesucht
    ANALYSING = "analysing"    # Dateien werden geprüft


class Match(BaseModel):
    """Ergebnis des Abgleichs einer Datei."""
    finding: Finding
    reason: Optional[MatchReason] = None
    video_id: Optional[str] = None       # Bibliotheks- oder Quellvideo
    title: Optional[str] = None
    channel_name: Optional[str] = None
    duration: Optional[int] = None
    size: Optional[int] = None
    in_library: bool = False             # video_id ist ein Video der Bibliothek


class OwnFolder(BaseModel):
    """Ein eingelesener Ordner (Pfad relativ zum Sammlungsordner, leer = alles)."""
    id: int
    path: str
    state: ScanState
    phase: Optional[ScanPhase] = None
    present: bool                        # Ordner ist gerade erreichbar
    files: int = 0                       # vorhandene Videodateien
    checked: int = 0                     # davon geprüft
    found_so_far: Optional[int] = None   # während der Suche: bisher gefunden
    open_by_finding: dict[str, int] = {}
    scan_started_at: Optional[str] = None
    scan_finished_at: Optional[str] = None


class OwnFile(BaseModel):
    id: int
    rel_path: str
    name: str
    folder: str                          # Ordner der Datei relativ zum Sammlungsordner
    size: Optional[int] = None
    duration: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    title: Optional[str] = None
    channel_hint: Optional[str] = None
    channel_id_hint: Optional[str] = None
    source_id: Optional[str] = None
    has_thumbnail: bool = False
    finding: Finding
    reason: Optional[MatchReason] = None
    match: Optional[Match] = None
    decision: Decision
    result_video_id: Optional[str] = None
    present: bool = True

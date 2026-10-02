"""
TubeVault – Untertitel als Transkript

Untertitel der Quelle in Sätze mit Zeitangabe übersetzen (reine Aufbereitung;
Holen und Ablegen macht services/transcripts).

Untertitel sind zum Mitlesen gebaut, nicht zum Sprechen: kurze Zeilen, mitten
im Satz umbrochen; automatisch erzeugte wiederholen dazu jede Zeile im
nächsten Eintrag. Deshalb werden Wiederholungen entfernt und die Zeilen zu
Sätzen gebündelt - ein Sprecher braucht ganze Sätze.
"""
import html
import logging
import re
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel


logger = logging.getLogger(__name__)

# Welche Untertitel als Transkript dienen dürfen (Einstellung dub.subtitles)
SubtitleUse = Literal["never", "manual", "any"]

_TIME = r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{3})"
_CUE_LINE = re.compile(rf"{_TIME}\s*-->\s*{_TIME}")
_TAG = re.compile(r"<[^>]+>")
_SENTENCE_END = re.compile(r"[.!?…][\"')\]]*$")

# Ein gebündelter Satz wird spätestens nach so vielen Sekunden abgeschlossen
MAX_SEGMENT_SECONDS = 14.0
# Eine Sprechpause ab dieser Länge trennt immer
MAX_GAP_SECONDS = 1.5
# Einträge unter dieser Dauer sind Übergangs-Einträge automatischer Untertitel
MIN_CUE_SECONDS = 0.05


class Segment(BaseModel):
    start: float
    end: float
    text: str


def _seconds(hours, minutes, seconds, millis) -> float:
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def parse_vtt(text: str) -> list[Segment]:
    """Einträge einer WebVTT- oder SRT-Datei, Zeile für Zeile, ohne Auszeichnung."""
    cues: list[Segment] = []
    start = end = None
    lines: list[str] = []

    def flush():
        if start is not None and lines:
            cues.append(Segment(start=start, end=end, text="\n".join(lines)))

    for raw in text.splitlines():
        match = _CUE_LINE.search(raw)
        if match:
            flush()
            start, end = _seconds(*match.groups()[:4]), _seconds(*match.groups()[4:])
            lines = []
        elif not raw.strip():
            flush()
            start, lines = None, []
        elif start is not None:
            line = " ".join(html.unescape(_TAG.sub("", raw)).split())
            if line:
                lines.append(line)
    flush()
    return cues


def without_repeats(cues: list[Segment]) -> list[Segment]:
    """Wiederholungen automatischer Untertitel entfernen: dort steht jede Zeile
    zweimal (erst als neue, dann als obere Zeile des nächsten Eintrags)."""
    result: list[Segment] = []
    last_line = ""
    for cue in cues:
        if cue.end - cue.start < MIN_CUE_SECONDS:
            continue
        fresh = []
        for line in cue.text.split("\n"):
            if line != last_line:
                fresh.append(line)
                last_line = line
        if fresh:
            result.append(Segment(start=cue.start, end=cue.end, text=" ".join(fresh)))
    return result


def into_sentences(cues: list[Segment]) -> list[Segment]:
    """Zeilen zu Sätzen bündeln: bis zum Satzende, zur nächsten Sprechpause
    oder zur Höchstdauer."""
    sentences: list[Segment] = []
    current: Optional[Segment] = None
    for cue in cues:
        if current and (cue.start - current.end > MAX_GAP_SECONDS
                        or cue.end - current.start > MAX_SEGMENT_SECONDS):
            sentences.append(current)
            current = None
        if current is None:
            current = cue.model_copy()
        else:
            current.end = cue.end
            current.text = f"{current.text} {cue.text}"
        if _SENTENCE_END.search(current.text):
            sentences.append(current)
            current = None
    if current:
        sentences.append(current)
    return sentences


def segments_from_file(path: Path) -> list[Segment]:
    return into_sentences(without_repeats(parse_vtt(path.read_text(encoding="utf-8"))))

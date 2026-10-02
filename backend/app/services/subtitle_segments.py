"""
TubeVault – Untertitel als Transkript

Für die Nachvertonung: Untertitel der Quelle in Segmente (Start, Ende, Text)
übersetzen, damit der Vertonungsdienst nicht selbst transkribieren muss.

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

from app.config import SUBTITLES_DIR

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


class Transcript(BaseModel):
    language: str
    kind: Literal["manual", "auto"]
    segments: list[Segment]


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


def _stored_file(video_id: str, language: str, use: SubtitleUse) -> tuple[Path, str] | None:
    """Gespeicherte Untertitel der Sprache: vom Autor erstellte zuerst,
    automatisch erzeugte (Kennung "a.<sprache>") nur, wenn erlaubt."""
    folder = SUBTITLES_DIR / video_id
    if not folder.is_dir():
        return None
    files = sorted(folder.glob("*.vtt")) + sorted(folder.glob("*.srt"))

    def matches(path: Path, prefix: str) -> bool:
        code = path.stem
        return code == f"{prefix}{language}" or code.startswith(f"{prefix}{language}-")

    for path in files:
        if matches(path, ""):
            return path, "manual"
    if use == "any":
        for path in files:
            if matches(path, "a."):
                return path, "auto"
    return None


async def for_dubbing(video_id: str, language: str, use: SubtitleUse) -> Transcript | None:
    """Transkript aus den Untertiteln der Quelle - oder None, wenn es keine
    passenden gibt. Fehlen sie lokal, werden sie einmal bei der Quelle geholt."""
    if use == "never" or not language:
        return None
    found = _stored_file(video_id, language, use)
    if not found:
        from app.services.download_service import download_service
        try:
            await download_service.download_subtitles(video_id, language)
        except Exception as e:
            logger.info(f"[UNTERTITEL] {video_id}: nicht abrufbar ({str(e)[:160]})")
            return None
        found = _stored_file(video_id, language, use)
    if not found:
        return None
    path, kind = found
    segments = segments_from_file(path)
    if not segments:
        return None
    return Transcript(language=language, kind=kind, segments=segments)

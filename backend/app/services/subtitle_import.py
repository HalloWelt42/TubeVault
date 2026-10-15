"""
TubeVault - Mitgeladene Untertitel einlesen

Beim Laden kamen zu vielen Videos Untertitel-Dateien mit (data/subtitles/
<video>/*.vtt). Sie lagen ungenutzt: gesucht wurde nur in Transkripten.
Gemessen am 15.10.2026 auf dem Pi: Dateien zu 14.040 Videos, eingelesen etwa
440.000 Abschnitte (262 MB Text), rund 7 Minuten Lesen. Diese Arbeit macht aus
je einer Datei pro Video ein Transkript (transcripts.store) - damit ist das
Gesagte dieser Videos durchsuchbar.

Welche Datei (eine je Video), in dieser Reihenfolge:
  1. Untertitel vom Autor in der Sprache des Videos
  2. automatische in der Originalsprache ("a.<sprache>-orig.vtt")
  3. automatische in der Sprache des Videos
  4. Untertitel vom Autor in einer anderen Sprache
  5. automatische in einer anderen Sprache
Als gesprochene Sprache (language_assign) zählt nur, was die Datei belegt:
1., 2. und 3. ohne eine "-orig"-Datei daneben; der Rest kann übersetzt sein.

Nur Wortsuche: Bedeutungsvektoren entstehen für diese Abschnitte nicht
(semantic_index), sie würden den Speicher sprengen. Läuft als
Hintergrundarbeit mit Schalter (transcripts.import_enabled, Standard an),
bis alles eingelesen ist; danach schaut sie selten nach Neuem.
"""
import asyncio
import logging
import os
import time
from typing import Literal, Optional

from pydantic import BaseModel

from app.config import SUBTITLES_DIR
from app.database import db
from app.services import language, setting_values, subtitle_segments, transcripts

logger = logging.getLogger(__name__)

SWITCH = "transcripts.import_enabled"
BATCH = 40                      # Videos je Durchgang, danach kurz Luft für Anfragen
START_DELAY_S = 120
IDLE_CHECK_S = 6 * 3600         # alles eingelesen: so selten nach Neuem schauen
PAUSED_CHECK_S = 60


class Choice(BaseModel):
    """Gewählte Untertitel-Datei eines Videos."""
    name: str
    language: str
    kind: Literal["manual", "auto"]
    spoken: bool


class _File(BaseModel):
    name: str
    language: str
    kind: Literal["manual", "auto"]
    original: bool


def _parse(name: str) -> Optional[_File]:
    """"a.de-orig.vtt" -> automatisch, de, Original; KI-Transkripte ("ki.") nicht."""
    if not name.endswith(".vtt") or name.startswith("ki."):
        return None
    stem = name[:-4]
    kind = "auto" if stem.startswith("a.") else "manual"
    if kind == "auto":
        stem = stem[2:]
    original = stem.endswith("-orig")
    if original:
        stem = stem[:-5]
    code = language.normalize(stem)
    return _File(name=name, language=code, kind=kind, original=original) if code else None


def choose(names: list[str], video_language: Optional[str]) -> Optional[Choice]:
    """Die beste Datei eines Videos nach der Reihenfolge im Kopf."""
    files = [f for f in map(_parse, sorted(names)) if f]
    if not files:
        return None
    any_original = any(f.original for f in files)
    ranked = [
        ([f for f in files if f.kind == "manual" and f.language == video_language], True),
        ([f for f in files if f.kind == "auto" and f.original], True),
        ([f for f in files if f.kind == "auto" and f.language == video_language], not any_original),
        ([f for f in files if f.kind == "manual"], False),
        ([f for f in files if f.kind == "auto"], False),
    ]
    for candidates, spoken in ranked:
        if candidates:
            best = candidates[0]
            return Choice(name=best.name, language=best.language, kind=best.kind, spoken=spoken)
    return None


# ─── Bestand ──────────────────────────────────────────────────────────

_queue: list[str] = []   # noch einzulesen im laufenden Durchgang (neueste zuerst)
_total = 0               # so viele waren es zu Beginn des Durchgangs


def _listing() -> list[str]:
    return os.listdir(SUBTITLES_DIR) if SUBTITLES_DIR.is_dir() else []


async def pending_ids() -> list[str]:
    """Fertige Videos mit Untertitel-Ordner, aber ohne Transkript (neueste zuerst)."""
    folders = set(await asyncio.to_thread(_listing))
    if not folders:
        return []
    rows = await db.fetch_all(
        """SELECT v.id FROM videos v LEFT JOIN transcripts t ON t.video_id = v.id
           WHERE v.status = 'ready' AND t.video_id IS NULL
           ORDER BY v.download_date DESC, v.id""")
    return [row["id"] for row in rows if row["id"] in folders]


_estimate: tuple[float, int] = (0.0, 0)   # (Zeitpunkt, Zahl) der letzten Zählung ohne Durchgang
ESTIMATE_TTL_S = 300


async def remaining() -> int:
    """Wie viele noch warten: im Durchgang genau, sonst gezählt (höchstens alle
    ESTIMATE_TTL_S, die Anzeige fragt alle paar Sekunden)."""
    global _estimate
    if _queue:
        return len(_queue)
    if time.monotonic() - _estimate[0] > ESTIMATE_TTL_S:
        _estimate = (time.monotonic(), len(await pending_ids()))
    return _estimate[1]


def progress() -> tuple[int, int]:
    """(eingelesen, insgesamt) des laufenden Durchgangs; (0, 0) ohne Durchgang."""
    return _total - len(_queue), _total


def _read(video_id: str, video_language: Optional[str]) -> tuple[Optional[Choice], list]:
    folder = SUBTITLES_DIR / video_id
    choice = choose(os.listdir(folder), video_language) if folder.is_dir() else None
    if not choice:
        return None, []
    return choice, subtitle_segments.segments_from_file(folder / choice.name)


async def import_one(video_id: str) -> int:
    """Ein Video einlesen; gibt die Zahl der Abschnitte zurück. Ohne lesbare
    Datei wird "keine Untertitel" vermerkt, damit es nicht wieder drankommt."""
    video_language = await db.fetch_val("SELECT language FROM videos WHERE id = ?", (video_id,))
    choice, sentences = await asyncio.to_thread(_read, video_id, video_language)
    if not choice:
        await transcripts.mark_none(video_id, "Keine lesbare Untertitel-Datei")
        return 0
    count = await transcripts.store(video_id, choice.language, choice.kind, sentences,
                                    imported=True, spoken=choice.spoken, note=choice.name)
    if choice.spoken:
        from app.services import language_assign
        await language_assign.reassess(video_id)
    return count


async def run_batch() -> int:
    """Einen Teil einlesen; liefert die Zahl der bearbeiteten Videos (0 = nichts zu tun).
    Der Bestand wird zu Beginn eines Durchgangs einmal ermittelt."""
    global _queue, _total
    if not _queue:
        _queue = await pending_ids()
        _total = len(_queue)
        if not _queue:
            return 0
    handled = 0
    while _queue and handled < BATCH:
        if not await setting_values.is_on(SWITCH):
            break
        video_id = _queue.pop(0)
        try:
            await import_one(video_id)
        except Exception as e:
            logger.warning(f"[UNTERTITEL] {video_id}: {e}")
            await transcripts.mark_none(video_id, f"Einlesen gescheitert: {e}"[:300])
        handled += 1
        await asyncio.sleep(0)
    if not _queue:
        logger.info(f"[UNTERTITEL] Durchgang fertig: {_total} Videos eingelesen")
        _total = 0
    return handled


async def loop() -> None:
    await asyncio.sleep(START_DELAY_S)
    while True:
        try:
            if not await setting_values.is_on(SWITCH):
                await asyncio.sleep(PAUSED_CHECK_S)
                continue
            if await run_batch():
                await asyncio.sleep(0.2)
                continue
        except Exception as e:
            logger.error(f"[UNTERTITEL] Fehler: {e}", exc_info=True)
        await asyncio.sleep(IDLE_CHECK_S)

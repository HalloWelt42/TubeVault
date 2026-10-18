"""
TubeVault – Laufende Hintergrundarbeiten v1.0.0

Lang laufende Vorgänge sollen sichtbar sein: was läuft, wie weit, wie lange
noch. Diese Übersicht sammelt den Stand aller Arbeiten, die ohne Zutun des
Nutzers im Hintergrund laufen, an einer Stelle - die Oberfläche zeigt sie in
der Statusleiste. (Downloads haben ihre eigene, ausführlichere Anzeige.)

Eine neue Hintergrundarbeit trägt sich hier mit einer Funktion ein, die
ihren Stand als WorkItem liefert (oder None, wenn nichts zu tun ist).
"""
import logging
import time

from app.utils.file_utils import now_sqlite
from datetime import datetime
from typing import Awaitable, Callable, Optional

from pydantic import BaseModel

from app.database import db

logger = logging.getLogger(__name__)


class WorkItem(BaseModel):
    key: str
    label: str
    detail: Optional[str] = None      # was gerade geschieht
    done: Optional[int] = None        # erledigte Einheiten
    total: Optional[int] = None       # Einheiten insgesamt
    progress: Optional[float] = None  # 0..1, falls bekannt
    since: Optional[str] = None       # läuft seit (UTC)
    eta_seconds: Optional[int] = None # geschätzte Restdauer
    waiting: int = 0                  # weitere wartende Aufträge dahinter
    switch_key: Optional[str] = None  # Einstellung, die die Arbeit an- und abschaltet
    paused: bool = False              # angehalten (switch_key steht auf aus)


_STAMP = "%Y-%m-%d %H:%M:%S"     # Schreibweise von now_sqlite

# Höchststand je Arbeit seit Programmstart: daraus ergibt sich "x von y"
_peak: dict[str, int] = {}
_first_seen: dict[str, str] = {}


def _countdown(key: str, remaining: int) -> tuple[int, int, str]:
    """(erledigt, gesamt, seit) aus einer schrumpfenden Restmenge ableiten."""
    if remaining > _peak.get(key, 0):
        _peak[key] = remaining
        _first_seen.setdefault(key, now_sqlite())
    total = _peak[key]
    return total - remaining, total, _first_seen[key]


def _forget(key: str) -> None:
    _peak.pop(key, None)
    _first_seen.pop(key, None)


async def _content_files() -> Optional[WorkItem]:
    """Inhalte als Datei: fehlende Beschreibungen, Kapitel und Begleitdateien (content_files)."""
    from app.services import content_files
    remaining = await content_files.remaining()
    if remaining < 20:   # einzelne schreibt die nächste Runde von selbst
        _forget("content_files")
        return None
    done, total, since = _countdown("content_files", remaining)
    return WorkItem(key="content_files", label="Inhalte werden als Datei geschrieben",
                    detail="Beschreibungen, Kapitel und Begleitdateien neben die Videos; daraus lässt sich die Datenbank neu aufbauen.",
                    done=done, total=total, progress=done / total if total else None, since=since)


async def _cover_hashes() -> Optional[WorkItem]:
    """Cover der Musiksammlung vergleichen (music_files.fill_cover_hashes): einmal für den Bestand."""
    from app.services import music_files
    remaining = await music_files.missing_cover_hashes() if music_files.available() else 0
    if remaining < 20:   # einzelne holt der nächste Lauf nach
        _forget("cover_hashes")
        return None
    done, total, since = _countdown("cover_hashes", remaining)
    return WorkItem(key="cover_hashes", label="Cover der Musiksammlung werden verglichen",
                    detail="Titel mit gleichem Cover werden ein Album; bis dahin fehlen manche Alben noch.",
                    done=done, total=total, progress=done / total if total else None, since=since)


async def _search_index() -> Optional[WorkItem]:
    from app.services import search_index
    remaining = await search_index.pending()
    if remaining < 50:   # einzelne Änderungen zieht die nächste Suche nach
        _forget("search_index")
        return None
    done, total, since = _countdown("search_index", remaining)
    return WorkItem(key="search_index", label="Suchindex wird aufgebaut",
                    detail="Die Suche findet bis dahin noch nicht alle Videos.",
                    done=done, total=total, progress=done / total if total else None, since=since)


async def _type_check() -> Optional[WorkItem]:
    from app.services import video_classifier
    remaining = await video_classifier.pending()
    if remaining == 0:
        _forget("type_check")
        return None
    done, total, since = _countdown("type_check", remaining)
    paused = not await video_classifier.check_enabled()
    return WorkItem(
        key="type_check", label="Video-Typen werden geprüft",
        detail=("Angehalten - fragt die Quelle erst nach dem Fortsetzen weiter." if paused
                else "Fragt die Quelle, was Short und was Video ist (bewusst langsam)."),
        done=done, total=total, progress=done / total if total else None, since=since,
        eta_seconds=None if paused else int(remaining * video_classifier.SECONDS_PER_PROBE),
        switch_key="types.check_enabled", paused=paused)


async def _dubbing() -> Optional[WorkItem]:
    """Der Auftrag, den der Nachvertoner gerade spricht. Angehalten bleibt das
    Vertonen immer sichtbar, damit es sich hier fortsetzen lässt."""
    from app.services import dubbing, setting_values
    if not await setting_values.is_on("dub.enabled"):
        return None
    paused = not await setting_values.is_on(dubbing.PROCESSING_SWITCH)
    row = await db.fetch_one(
        """SELECT d.progress, d.note, d.claimed_at, d.worker, v.title
           FROM dub_requests d LEFT JOIN videos v ON v.id = d.video_id
           WHERE d.status = 'working' ORDER BY d.claimed_at LIMIT 1""")
    waiting = await db.fetch_val("SELECT COUNT(*) FROM dub_requests WHERE status = 'queued'") or 0
    if not row and not paused:
        return None   # wartende Aufträge ohne Nachvertoner zeigt die Seite Nachvertonung
    if row:
        label = f"Nachvertonung: {(row['title'] or 'Video')[:60]}"
        detail = " · ".join(filter(None, [row["note"], row["worker"]])) or None
        if paused:
            detail = "Hält nach diesem Auftrag an." + (f" {detail}" if detail else "")
    else:
        label = "Vertonen"
        detail = (f"Angehalten - {waiting} Aufträge warten, der Nachvertoner bekommt keinen neuen." if waiting
                  else "Angehalten - neue Aufträge bleiben liegen, bis du fortsetzt.")
    return WorkItem(key="dubbing", label=label, detail=detail,
                    progress=(row["progress"] or 0) if row else None, since=row["claimed_at"] if row else None,
                    waiting=waiting, switch_key=dubbing.PROCESSING_SWITCH, paused=paused)


async def _channel_scan() -> Optional[WorkItem]:
    """Ungescannte Kanäle von selbst erfassen: einer alle 2 Stunden (auto_scan)."""
    from app.services import auto_scan, setting_values
    remaining = await auto_scan.pending()
    if remaining == 0:
        return None
    total = await auto_scan.total()
    paused = not await setting_values.is_on(auto_scan.SWITCH)
    running = auto_scan.running()
    if paused:
        detail = "Angehalten - Fortsetzen liest alle 2 Stunden einen Kanal, bis alle erfasst sind."
    elif running:
        detail = f"Liest gerade: {running}"
    else:
        wait = await auto_scan.seconds_until_due()
        channel = await auto_scan.next_channel()
        name = (channel or {}).get("channel_name") or ""
        detail = (f"Nächster Kanal in {wait // 60 + 1} Min: {name}" if wait else f"Als Nächstes: {name}").strip()
    done = max(0, total - remaining)
    return WorkItem(key="channel_scan", label="Kanalscan: ungescannte Kanäle", detail=detail,
                    done=done, total=total, progress=done / total if total else None,
                    eta_seconds=None if paused else remaining * auto_scan.INTERVAL_S,
                    switch_key=auto_scan.SWITCH, paused=paused)


async def _semantic_index() -> Optional[WorkItem]:
    from app.services import semantic_index
    if not await semantic_index.config():
        return None
    remaining = await semantic_index.pending()
    if remaining < 50:
        _forget("semantic_index")
        return None
    done, total, since = _countdown("semantic_index", remaining)
    reachable = await semantic_index.available()
    return WorkItem(
        key="semantic_index", label="Bedeutungssuche: Videos werden eingebettet",
        detail=None if reachable else "Wartet auf den KI-Dienst (nicht erreichbar).",
        done=done, total=total, progress=done / total if total else None, since=since)


async def _ai_transcripts() -> Optional[WorkItem]:
    """Das KI-Transkript, das gerade entsteht; die übrigen warten dahinter,
    bis der Rechner mit der Spracherkennung wieder frei ist."""
    from app.services import setting_values, transcripts
    paused = not await setting_values.is_on(transcripts.AI_SWITCH)
    row = await db.fetch_one(
        """SELECT a.note, a.claimed_at, a.worker, v.title FROM ai_transcriptions a
           LEFT JOIN videos v ON v.id = a.video_id WHERE a.status = 'working' LIMIT 1""")
    # Erledigt von insgesamt: fertige gegen fertige plus laufende plus wartende
    counts = await transcripts.ai_counts()
    # Videos ohne Transkript zählen ist teuer (0,5 s), der Fortschritt verträgt eine Minute
    from app.services import shared_cache
    remaining = await shared_cache.cached("ai_transcripts_pending", 60, transcripts.pending) + counts["working"]
    if not row and not (paused and remaining):
        return None   # wartende ohne Bearbeiter: kein laufender Vorgang
    done = counts["done"]
    total = done + remaining
    average = await transcripts.average_ai_seconds()
    if row:
        label = f"KI-Transkript: {(row['title'] or 'Video')[:60]}"
        detail = " · ".join(filter(None, [row["note"], row["worker"]])) or None
        if paused:
            detail = "Hält nach diesem Video an." + (f" {detail}" if detail else "")
    else:
        # angehalten und nichts in Arbeit: sichtbar bleiben, damit es sich fortsetzen lässt
        label, detail = "KI-Transkripte", "Angehalten - es wird kein neues Video bearbeitet."
    return WorkItem(key="ai_transcripts", label=label, detail=detail,
                    since=row["claimed_at"] if row else None, done=done, total=total,
                    progress=done / total if total else None,
                    eta_seconds=int(remaining * average) if average and not paused else None,
                    switch_key=transcripts.AI_SWITCH, paused=paused)


async def _subtitle_import() -> Optional[WorkItem]:
    """Mitgeladene Untertitel werden durchsuchbar gemacht (subtitle_import)."""
    from app.services import setting_values, subtitle_import
    paused = not await setting_values.is_on(subtitle_import.SWITCH)
    done, total = subtitle_import.progress()
    if not total:
        waiting = await subtitle_import.remaining() if paused else 0
        if not waiting:
            return None
        return WorkItem(key="subtitle_import", label="Untertitel einlesen", waiting=waiting,
                        detail=f"Angehalten - {waiting} Videos mit Untertiteln sind noch nicht durchsuchbar.",
                        switch_key=subtitle_import.SWITCH, paused=True)
    return WorkItem(key="subtitle_import", label="Untertitel einlesen",
                    detail="Macht das Gesagte von Videos mit mitgeladenen Untertiteln durchsuchbar.",
                    done=done, total=total, progress=done / total, switch_key=subtitle_import.SWITCH, paused=paused)


async def _passage_index() -> Optional[WorkItem]:
    from app.services import semantic_index
    cfg = await semantic_index.config()
    if not cfg:
        return None
    remaining = await semantic_index.pending_chunks(cfg[1])
    if remaining < 200:
        _forget("passage_index")
        return None
    done, total, since = _countdown("passage_index", remaining)
    reachable = await semantic_index.available()
    from app.services import setting_values
    paused = not await setting_values.is_on(semantic_index.PASSAGES_SWITCH)
    detail = ("Angehalten - die Bedeutungssuche findet im Gesagten nur, was schon eingebettet ist." if paused
              else None if reachable else "Wartet auf den KI-Dienst (nicht erreichbar).")
    return WorkItem(
        key="passage_index", label="Bedeutungssuche: Gesagtes wird eingebettet", detail=detail,
        done=done, total=total, progress=done / total if total else None, since=since,
        switch_key=semantic_index.PASSAGES_SWITCH, paused=paused)


async def _languages() -> Optional[WorkItem]:
    """Sprache des Bestands zuordnen (language_assign): rein lokal, in Portionen."""
    from app.services import language_assign
    remaining = await language_assign.pending()
    if remaining < 50:   # einzelne neue Einträge sind sofort bewertet
        _forget("languages")
        return None
    done, total, since = _countdown("languages", remaining)
    # Restdauer aus dem bisherigen Tempo (der Lauf ist rein lokal und gleichmäßig)
    elapsed = (datetime.strptime(now_sqlite(), _STAMP) - datetime.strptime(since, _STAMP)).total_seconds()
    eta = int(elapsed / done * remaining) if done and elapsed > 0 else None
    return WorkItem(key="languages", label="Sprachen werden zugeordnet",
                    detail="Aus Untertiteln, Titel und Beschreibung, sonst nach dem Kanal - rein lokal.",
                    done=done, total=total, progress=done / total if total else None, since=since,
                    eta_seconds=eta)


async def _own_videos() -> Optional[WorkItem]:
    from app.models.own_files import ScanPhase
    from app.services import own_actions, own_scan
    bulk = own_actions.bulk_running()
    if bulk:
        _, verb = own_actions.BULK_ACTIONS[bulk.action]
        return WorkItem(key="own_videos", label=f"Eigene Videos werden {verb}",
                        detail=f"{bulk.folder_path or 'ganze Sammlung'}"
                               + (f" - {bulk.failed} nicht möglich" if bulk.failed else ""),
                        done=bulk.done + bulk.failed, total=bulk.total,
                        progress=(bulk.done + bulk.failed) / bulk.total if bulk.total else None, since=bulk.since)
    scan = await own_scan.live()
    if not scan:
        return None
    folder = scan.path or "ganze Sammlung"
    if scan.phase == ScanPhase.LISTING:
        return WorkItem(key="own_videos", label="Eigene Videos: Dateien werden gesucht",
                        detail=f"{folder} - bisher {scan.found:,} gefunden".replace(",", "."), since=scan.since)
    return WorkItem(key="own_videos", label="Eigene Videos werden eingelesen",
                    detail=f"{folder} - Angaben lesen und mit der Bibliothek abgleichen",
                    done=scan.checked, total=scan.files,
                    progress=scan.checked / scan.files if scan.files else None, since=scan.since)


SOURCES: list[Callable[[], Awaitable[Optional[WorkItem]]]] = [
    _dubbing, _ai_transcripts, _channel_scan, _subtitle_import, _own_videos, _search_index, _semantic_index, _passage_index,
    _type_check, _languages, _content_files, _cover_hashes]


SLOW_OVERVIEW_S = 1.0      # dauert die Übersicht länger, steht im Live-Log, was wie lange brauchte
_REPORT_GAP_S = 300
_last_slow_report = 0.0


OVERVIEW_TTL_S = 8     # Statusleiste und Übersichtskarte jedes Fensters fragen alle 8 s


async def overview() -> list[WorkItem]:
    """Stand aller Hintergrundarbeiten - einmal gerechnet gilt für alle Fenster."""
    from app.services import shared_cache
    return await shared_cache.cached("background_overview", OVERVIEW_TTL_S, compute_overview)


async def compute_overview() -> list[WorkItem]:
    """Stand aller Hintergrundarbeiten, frisch gerechnet (overview teilt ihn)."""
    global _last_slow_report
    items = []
    spent = []
    started = time.monotonic()
    for source in SOURCES:
        before = time.monotonic()
        item = await source()
        spent.append((source.__name__.lstrip("_"), time.monotonic() - before))
        if item:
            items.append(item)
    total = time.monotonic() - started
    if total >= SLOW_OVERVIEW_S and time.monotonic() - _last_slow_report >= _REPORT_GAP_S:
        _last_slow_report = time.monotonic()
        parts = ", ".join(f"{name} {seconds:.1f} s" for name, seconds in sorted(spent, key=lambda x: -x[1]) if seconds >= 0.05)
        logger.warning(f"Übersicht der Hintergrundarbeiten brauchte {total:.1f} s: {parts}")
    return items

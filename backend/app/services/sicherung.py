"""
TubeVault - Sicherung der Datenbank nach der Sicherungsregel

Eine Sicherung ist eine Kopie der Datenbank im Ordner exports/backups (config.BACKUP_DIR). Ob ein Lauf eine neue
anlegt, entscheidet er selbst über das Alter der jüngsten, nicht der Takt des Aufrufs (die Werte in config.py):
- regelmäßig (Zeitplan auf dem Pi, scripts/backup_db.sh): frühestens am SICHERUNG_ABSTAND_TAGE-ten Kalendertag nach
  der jüngsten; gezählt in Kalendertagen, damit ein Zeitplan im selben Takt nicht an Sekunden scheitert;
- vor dem Ausrollen (scripts/backup_db.sh --vor-ausrollen): nur, wenn die jüngste älter ist als
  SICHERUNG_VOR_AUSROLLEN_AB_STUNDEN;
- von Hand (Knopf "Jetzt sichern"): ohne Altersgrenze;
- nie ohne Änderung: sind Datenbankdatei und -wal beide älter als die jüngste Sicherung, entsteht keine neue. Dafür
  trägt jede Sicherung als Änderungszeit den Zeitpunkt, zu dem ihre Kopie begann.

Die Kopie entsteht unter einem Namen mit Punkt vorn (.<name>.teil), der nicht zum Muster passt, und wird erst fertig
umbenannt. Jeder Lauf räumt danach auf höchstens SICHERUNG_BEHALTEN Stände ab, auch wenn keine neue entstand; er
fasst nur Dateien mit dem Muster der Sicherungen an. In den Ordner kommen keine Begleitdateien: das Holen auf den Mac
nimmt die neuesten Einträge des Ordners als Stände.
"""
import asyncio
import logging
import os
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

from app import config
from app.database import db
from app.models.sicherung import Anlass, Ausgang, SicherungsLauf

logger = logging.getLogger(__name__)

MUSTER = "tubevault_backup_*.db"
TEIL_MUSTER = f".{MUSTER}.teil"

# Ein Lauf zur Zeit: Zeitplan, Ausrollen und Knopf können sich treffen
_lauf = asyncio.Lock()


def staende(ordner: Path) -> list[Path]:
    """Die Sicherungen im Ordner, neueste zuerst (nach Änderungszeit)."""
    if not ordner.is_dir():
        return []
    return sorted((p for p in ordner.glob(MUSTER) if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)


def faellig(anlass: Anlass, juengste: datetime, jetzt: datetime) -> bool:
    """Ob der Anlass nach dem Alter der jüngsten Sicherung eine neue verlangt."""
    if anlass is Anlass.HAND:
        return True
    if anlass is Anlass.AUSROLLEN:
        return jetzt - juengste > timedelta(hours=config.SICHERUNG_VOR_AUSROLLEN_AB_STUNDEN)
    return (jetzt.date() - juengste.date()).days >= config.SICHERUNG_ABSTAND_TAGE


def _aenderungszeit(pfad: Path) -> float | None:
    try:
        return pfad.stat().st_mtime
    except FileNotFoundError:
        return None


def unveraendert(datenbank: Path, juengste: float) -> bool:
    """Ob die Datenbank seit der jüngsten Sicherung unverändert ist: Datei und -wal (falls vorhanden) sind beide älter
    als der Beginn ihrer Kopie. Liest nichts aus der Datenbank, nur die Änderungszeiten."""
    zeiten = (_aenderungszeit(datenbank), _aenderungszeit(datenbank.with_name(datenbank.name + "-wal")))
    return all(z < juengste for z in zeiten if z is not None)


def aufraeumen(ordner: Path, behalten: int) -> list[str]:
    """Hält höchstens `behalten` Sicherungen, ältere gehen. Gibt die Namen der entfernten zurück."""
    weg = staende(ordner)[behalten:]
    for p in weg:
        p.unlink()
        logger.info(f"[SICHERUNG] Entfernt: {p.name}")
    return [p.name for p in weg]


def _reste_entfernen(ordner: Path) -> None:
    """Halbe Kopien eines abgebrochenen Laufs (nur die eigenen .teil-Dateien)."""
    for teil in ordner.glob(TEIL_MUSTER):
        teil.unlink(missing_ok=True)
        logger.warning(f"[SICHERUNG] Halbe Kopie entfernt: {teil.name}")


def _dateiname(frontend_version: str | None) -> str:
    zeit = datetime.now().strftime("%Y%m%d_%H%M%S")
    be = config.VERSION.replace(".", "-")
    fe = (frontend_version or config.VERSION).replace(".", "-")
    return f"tubevault_backup_{zeit}_be{be}_fe{fe}.db"


async def _kopieren(ziel: Path) -> None:
    """Konsistente Kopie der laufenden Datenbank (VACUUM INTO), ersatzweise die Datei nach einem Checkpoint."""
    try:
        await db.execute(f'VACUUM INTO "{ziel}"')
    except Exception as e:
        logger.warning(f"[SICHERUNG] VACUUM INTO fehlgeschlagen: {e}, nutze Dateikopie")
        ziel.unlink(missing_ok=True)
        try:
            await db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass
        await asyncio.to_thread(shutil.copyfile, db.db_path, ziel)


async def _anlegen(ordner: Path, frontend_version: str | None) -> Path:
    """Neue Sicherung: Kopie unter dem Teilnamen, dann umbenennen; Änderungszeit ist der Beginn der Kopie."""
    name = _dateiname(frontend_version)
    teil = ordner / f".{name}.teil"
    fertig = ordner / name
    beginn = time.time()
    try:
        await _kopieren(teil)
        teil.rename(fertig)
    except Exception:
        teil.unlink(missing_ok=True)
        raise
    os.utime(fertig, (beginn, beginn))
    logger.info(f"[SICHERUNG] Angelegt: {name}")
    return fertig


def _zeit(zeitstempel: float) -> str:
    return datetime.fromtimestamp(zeitstempel).strftime("%d.%m.%Y %H:%M")


async def sichern(anlass: Anlass, ordner: Path, frontend_version: str | None = None) -> SicherungsLauf:
    """Ein Lauf nach der Sicherungsregel: neue Sicherung, falls fällig und geändert; danach aufräumen."""
    async with _lauf:
        ordner.mkdir(parents=True, exist_ok=True)
        _reste_entfernen(ordner)
        vorhanden = staende(ordner)
        juengste = vorhanden[0].stat().st_mtime if vorhanden else None
        neu: Path | None = None
        if juengste is not None and not faellig(anlass, datetime.fromtimestamp(juengste), datetime.now()):
            ausgang, meldung = Ausgang.NICHT_FAELLIG, f"Nicht fällig: die jüngste Sicherung ist vom {_zeit(juengste)}"
        elif juengste is not None and unveraendert(db.db_path, juengste):
            ausgang = Ausgang.UNVERAENDERT
            meldung = f"Keine neue Sicherung: die Datenbank ist seit der jüngsten vom {_zeit(juengste)} unverändert"
        else:
            neu = await _anlegen(ordner, frontend_version)
            ausgang, meldung = Ausgang.ANGELEGT, f"Gesichert: {neu.name}"
        groesse = neu.stat().st_size if neu else None
        entfernt = await asyncio.to_thread(aufraeumen, ordner, config.SICHERUNG_BEHALTEN)
    if entfernt:
        meldung += f"; entfernt: {', '.join(entfernt)}"
    return SicherungsLauf(anlass=anlass, ausgang=ausgang, meldung=meldung, entfernt=entfernt,
                          filename=neu.name if neu else None, size=groesse)

"""
Sicherung der Datenbank nach der Sicherungsregel (services/sicherung.py, routers/backup).

Kontrakt:
- regelmäßig fällig ab dem sicherung_abstand_tage-ten Kalendertag nach der jüngsten (ein Zeitplan im selben Takt
  scheitert nicht an Sekunden), vor dem Ausrollen erst, wenn die jüngste älter ist als
  sicherung_vor_ausrollen_ab_stunden, von Hand immer;
- ohne Änderung der Datenbank entsteht keine neue;
- jede neue trägt als Änderungszeit den Beginn ihrer Kopie, keine Teildatei bleibt liegen;
- jeder Lauf hält höchstens sicherung_behalten Stände, auch ohne neue, und fasst nichts anderes im Ordner an.
"""
import os
import time
from datetime import datetime, timedelta

import pytest

from app import config
from app.models.sicherung import Anlass, Ausgang
from app.routers import backup
from app.services import sicherung


@pytest.fixture
def ordner(tmp_path):
    """Eigener Ordner der Sicherungen je Test."""
    pfad = tmp_path / "backups"
    pfad.mkdir()
    return pfad


def _stand(ordner, name, alter_s):
    """Eine Sicherung (oder fremde Datei) mit gegebenem Alter."""
    pfad = ordner / name
    pfad.write_bytes(b"x")
    zeit = time.time() - alter_s
    os.utime(pfad, (zeit, zeit))
    return pfad


def test_regelmaessig_nach_kalendertagen():
    juengste = datetime(2026, 10, 25, 3, 0, 1, 500000)     # Sonntag, Lauf des Zeitplans
    # eine Woche später ein paar Millisekunden früher: trotzdem fällig
    assert sicherung.faellig(Anlass.REGELMAESSIG, juengste, datetime(2026, 11, 1, 3, 0, 1, 200000))
    assert not sicherung.faellig(Anlass.REGELMAESSIG, juengste, datetime(2026, 10, 31, 23, 59))
    # nach einer Sicherung vor dem Ausrollen am Mittwoch zählt der Sonntag darauf noch nicht
    assert not sicherung.faellig(Anlass.REGELMAESSIG, datetime(2026, 10, 28, 17, 0), datetime(2026, 11, 1, 3, 0))


def test_vor_ausrollen_nach_stunden_und_hand_immer():
    jetzt = datetime(2026, 10, 27, 20, 0)
    grenze = timedelta(hours=config.SICHERUNG_VOR_AUSROLLEN_AB_STUNDEN)
    assert not sicherung.faellig(Anlass.AUSROLLEN, jetzt - grenze + timedelta(minutes=1), jetzt)
    assert sicherung.faellig(Anlass.AUSROLLEN, jetzt - grenze - timedelta(minutes=1), jetzt)
    assert sicherung.faellig(Anlass.HAND, jetzt - timedelta(minutes=1), jetzt)


def test_unveraendert_nach_aenderungszeiten(tmp_path):
    datenbank = tmp_path / "tubevault.db"
    wal = tmp_path / "tubevault.db-wal"
    datenbank.write_bytes(b"x")
    os.utime(datenbank, (100, 100))
    assert sicherung.unveraendert(datenbank, 200)
    wal.write_bytes(b"x")
    os.utime(wal, (300, 300))
    assert not sicherung.unveraendert(datenbank, 200)


async def test_erster_lauf_legt_an_dann_keine_ohne_aenderung(test_db, ordner):
    vorher = time.time()
    lauf = await sicherung.sichern(Anlass.REGELMAESSIG, ordner, "cron")
    assert lauf.ausgang is Ausgang.ANGELEGT
    neu = ordner / lauf.filename
    assert neu.name.startswith("tubevault_backup_") and neu.name.endswith("_fecron.db")
    assert lauf.size == neu.stat().st_size > 0
    assert vorher <= neu.stat().st_mtime <= time.time()      # Beginn der Kopie, nicht ihr Ende
    assert [p.name for p in ordner.iterdir()] == [neu.name]  # keine Teildatei, keine Begleitdatei

    zweiter = await sicherung.sichern(Anlass.HAND, ordner)
    assert zweiter.ausgang is Ausgang.UNVERAENDERT and zweiter.filename is None
    assert len(sicherung.staende(ordner)) == 1


async def test_nach_aenderung_neue_sicherung(test_db, ordner):
    # eigene Kennung je Lauf: beide entstehen in derselben Sekunde und hießen sonst gleich
    erste = await sicherung.sichern(Anlass.HAND, ordner, "erste")
    alt = time.time() - 60
    os.utime(ordner / erste.filename, (alt, alt))            # jüngste liegt eine Minute zurück
    await test_db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('sicherung.probe', '1')")
    zweite = await sicherung.sichern(Anlass.HAND, ordner, "zweite")
    assert zweite.ausgang is Ausgang.ANGELEGT
    assert [p.name for p in sicherung.staende(ordner)] == [zweite.filename, erste.filename]


async def test_aufraeumen_auch_ohne_neue_und_nur_eigene(test_db, ordner):
    staende = [_stand(ordner, f"tubevault_backup_2026100{i}_000000_be2-90-2_fecron.db", alter_s=3600 * (i + 1))
               for i in range(5)]
    fremde = [_stand(ordner, "scan_index_20260702_100908.db", alter_s=10 ** 7),
              _stand(ordner, "tubevault_pre_restore_20261001_000000.db", alter_s=10 ** 7)]
    rest = _stand(ordner, ".tubevault_backup_20261001_000000_be2-90-2_fecron.db.teil", alter_s=10)

    lauf = await sicherung.sichern(Anlass.REGELMAESSIG, ordner)
    assert lauf.ausgang is Ausgang.NICHT_FAELLIG
    behalten = config.SICHERUNG_BEHALTEN
    assert sicherung.staende(ordner) == staende[:behalten]
    assert lauf.entfernt == [p.name for p in staende[behalten:]]
    assert all(p.exists() for p in fremde)
    assert not rest.exists()


async def test_schnittstelle_mit_anlass(test_db, ordner, make_test_app, monkeypatch):
    from httpx import ASGITransport, AsyncClient
    monkeypatch.setattr(backup, "BACKUP_DIR", ordner)
    _stand(ordner, "tubevault_backup_20261027_000000_be2-90-4_fecron.db", alter_s=3600)
    app = make_test_app(backup.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        antwort = (await client.post("/api/backup/create?anlass=ausrollen&frontend_version=cron")).json()
        assert antwort["anlass"] == "ausrollen" and antwort["ausgang"] == "nicht_faellig"
        assert antwort["filename"] is None and "jüngste Sicherung" in antwort["meldung"]
        assert (await client.post("/api/backup/create?anlass=woche")).status_code == 422

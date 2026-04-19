"""
Zentrale Test-Fixtures.

Strategie:
- Test-DB ist eine temporäre Datei (nicht :memory:), weil aiosqlite + WAL +
  gemeinsame Connection über mehrere Services am besten mit echter Datei spielt.
- Der globale `db`-Singleton wird auf die Test-DB umgebogen (path + reconnect),
  damit alle Services die Test-DB sehen ohne Dependency-Injection nachrüsten.
- `tmp_data_dir` sorgt dafür, dass keine Tests versehentlich auf /app/data schreiben.
"""
import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

# Test-Daten-Verzeichnis setzen BEVOR app.config importiert wird
_TMP_ROOT = Path(tempfile.mkdtemp(prefix="tubevault-tests-"))
(_TMP_ROOT / "db").mkdir(parents=True, exist_ok=True)
(_TMP_ROOT / "config").mkdir(parents=True, exist_ok=True)
os.environ["TUBEVAULT_DATA_DIR"] = str(_TMP_ROOT)
os.environ["TUBEVAULT_CONFIG_DIR"] = str(_TMP_ROOT / "config")
# Kein echter POT-Provider im Test
os.environ["POT_PROVIDER_URL"] = "http://127.0.0.1:1"  # unerreichbar

# Backend-Root in sys.path damit 'from app...' klappt
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def pytest_sessionfinish(session, exitstatus):
    """Temp-Verzeichnis am Ende aller Tests entfernen."""
    try:
        shutil.rmtree(_TMP_ROOT, ignore_errors=True)
    except Exception:
        pass


@pytest_asyncio.fixture
async def test_db():
    """Frische SQLite-DB pro Test-Funktion.

    Gibt das globale `db`-Objekt zurück, nachdem es auf eine neue leere
    Datei verbunden wurde. Services in app.* nutzen diesen Singleton direkt,
    also bekommen sie automatisch die Test-DB.
    """
    from app.database import Database
    import app.database as db_mod

    # Eigene Datei pro Test (isoliert) – WAL braucht echte Datei
    tmp = Path(tempfile.mkdtemp(prefix="tv-test-db-", dir=str(_TMP_ROOT)))
    db_file = tmp / "tubevault.db"

    # Neue Instance bauen, global austauschen
    test_instance = Database(db_path=db_file)
    await test_instance.connect()
    original = db_mod.db
    db_mod.db = test_instance

    # Auch in bereits importierten Modulen austauschen
    # (wichtig: viele Services haben 'from app.database import db' cached)
    import importlib
    for mod_name in list(sys.modules):
        mod = sys.modules[mod_name]
        if mod and hasattr(mod, "db") and getattr(mod, "db", None) is original:
            try:
                setattr(mod, "db", test_instance)
            except Exception:
                pass

    try:
        yield test_instance
    finally:
        await test_instance.disconnect()
        db_mod.db = original
        # Auch zurücksetzen
        for mod_name in list(sys.modules):
            mod = sys.modules[mod_name]
            if mod and hasattr(mod, "db") and getattr(mod, "db", None) is test_instance:
                try:
                    setattr(mod, "db", original)
                except Exception:
                    pass
        shutil.rmtree(tmp, ignore_errors=True)


@pytest_asyncio.fixture
async def set_setting(test_db):
    """Helper zum Schreiben von Settings in die Test-DB."""
    async def _set(key: str, value):
        await test_db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, str(value)),
        )
    return _set

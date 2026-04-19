"""
Cooldown-Logic Tests

Sichert ab:
- reload_cooldown_base() liest aus settings-Tabelle und setzt _cooldown_base + _cooldown
- User-Override greift auch wenn Backoff hochgefahren ist (Regressions-Test v2.4.4)
- Invalidierung auf 0 per Setting funktioniert (aber ≤ Clamp im Router)
"""
import pytest
from app.services.download_service import DownloadService


@pytest.fixture
def fresh_service():
    """Neue DownloadService-Instanz (ohne run_task) – Ausgangszustand wie vor Worker-Start."""
    svc = DownloadService()
    # Die Attribute die der queue_loop normalerweise beim Start setzt.
    svc._cooldown = 30
    svc._cooldown_base = 30
    svc._cooldown_max = 7200
    svc._cooldown_until = 0.0
    svc._cooldown_active = False
    return svc


async def test_reload_from_empty_db_defaults_to_30(fresh_service, test_db):
    """Ohne Setting-Eintrag → Default 30s."""
    await fresh_service.reload_cooldown_base()
    assert fresh_service._cooldown_base == 30


async def test_reload_reads_setting(fresh_service, test_db, set_setting):
    """Setting in DB → wird übernommen."""
    await set_setting("download.cooldown_base_s", "45")
    await fresh_service.reload_cooldown_base()
    assert fresh_service._cooldown_base == 45


async def test_reload_lowers_active_cooldown(fresh_service, test_db, set_setting):
    """User senkt Wert von 30 auf 5 → sowohl _base als auch aktives _cooldown fallen."""
    fresh_service._cooldown = 30
    await set_setting("download.cooldown_base_s", "5")
    await fresh_service.reload_cooldown_base()
    assert fresh_service._cooldown_base == 5
    assert fresh_service._cooldown == 5


async def test_reload_overrides_active_backoff(fresh_service, test_db, set_setting):
    """Regressions-Test v2.4.4:
    Nach Bot-Detection ist _cooldown evtl. auf 240s hoch (exponential backoff).
    User setzt im UI 5s → reload muss auch die hohe aktive Zeit runterziehen."""
    fresh_service._cooldown = 240  # Backoff-Eskalation
    fresh_service._cooldown_base = 30
    await set_setting("download.cooldown_base_s", "5")
    await fresh_service.reload_cooldown_base()
    assert fresh_service._cooldown_base == 5
    assert fresh_service._cooldown == 5, (
        "Bug v2.4.3: _cooldown blieb bei 240s weil es größer als base*8 war. "
        "Fix v2.4.4: User-Override greift immer."
    )


async def test_reload_raises_cooldown_when_user_increases(fresh_service, test_db, set_setting):
    """User erhöht Wert → _cooldown folgt."""
    fresh_service._cooldown = 30
    fresh_service._cooldown_base = 30
    await set_setting("download.cooldown_base_s", "120")
    await fresh_service.reload_cooldown_base()
    assert fresh_service._cooldown_base == 120
    assert fresh_service._cooldown == 120


async def test_reload_no_change_when_same_value(fresh_service, test_db, set_setting):
    """Gleicher Wert → keine Mutation, kein Log (Idempotenz)."""
    await set_setting("download.cooldown_base_s", "30")
    fresh_service._cooldown = 30
    fresh_service._cooldown_base = 30
    await fresh_service.reload_cooldown_base()
    assert fresh_service._cooldown_base == 30
    assert fresh_service._cooldown == 30


async def test_reload_zero_accepted_in_service(fresh_service, test_db, set_setting):
    """Service akzeptiert 0 wenn in DB (Router clamped zwar auf min 5, aber Service ist permissiv).
    Schützt davor, dass ein manuell gesetztes 0-Setting nicht crashed."""
    await set_setting("download.cooldown_base_s", "0")
    await fresh_service.reload_cooldown_base()
    assert fresh_service._cooldown_base == 0


async def test_reload_non_numeric_setting_ignored(fresh_service, test_db, set_setting):
    """Korrupte DB-Werte (non-numeric) dürfen nicht crashen – bleiben bei aktuellem Wert."""
    fresh_service._cooldown_base = 30
    await set_setting("download.cooldown_base_s", "abc")
    # Exception wird in reload_cooldown_base abgefangen → _base bleibt unverändert
    await fresh_service.reload_cooldown_base()
    assert fresh_service._cooldown_base == 30

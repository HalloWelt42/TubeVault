"""
Cookie-Detection Tests.

ytdlp_adapter._cookiefile() liest /app/config/cookies.txt wenn vorhanden
und > 0 Bytes. Tests nutzen die conftest-Env-Variable TUBEVAULT_CONFIG_DIR.
"""
import os
from pathlib import Path

import pytest


@pytest.fixture
def cookies_path():
    """Pfad zur cookies.txt aus Test-Config-Dir."""
    # conftest setzt TUBEVAULT_CONFIG_DIR auf tmp dir
    # _cookiefile() hardcodet aber /app/config/cookies.txt – wir müssen
    # deshalb diesen Pfad mocken.
    return Path("/app/config/cookies.txt")


def test_no_cookies_file_returns_none(cookies_path):
    """Kein File → None."""
    if cookies_path.exists():
        cookies_path.unlink()
    from app.utils.ytdlp_adapter import _cookiefile
    assert _cookiefile() is None


def test_empty_cookies_file_returns_none(cookies_path):
    """Leeres File → None (size > 0 Check)."""
    cookies_path.parent.mkdir(parents=True, exist_ok=True)
    cookies_path.write_text("")
    from app.utils.ytdlp_adapter import _cookiefile
    assert _cookiefile() is None
    cookies_path.unlink()


def test_cookies_file_returns_path(cookies_path):
    """Nicht-leeres File → absoluter Pfad."""
    cookies_path.parent.mkdir(parents=True, exist_ok=True)
    cookies_path.write_text(
        "# Netscape HTTP Cookie File\n"
        ".youtube.com\tTRUE\t/\tFALSE\t0\tSID\tdummy-value\n"
    )
    from app.utils.ytdlp_adapter import _cookiefile
    result = _cookiefile()
    assert result is not None
    assert result.endswith("cookies.txt")
    cookies_path.unlink()


def test_bot_setup_log_runs_on_import():
    """_log_bot_setup läuft beim Import und crasht nicht auch wenn POT unerreichbar.
    Regression-Test – früher konnte ein fehlgeschlagener Ping den Import blockieren."""
    # Importieren darf nicht werfen, auch wenn tubevault-pot:4416 nicht reachable
    from app.utils import ytdlp_adapter
    assert hasattr(ytdlp_adapter, "_POT_BASE_URL")
    assert hasattr(ytdlp_adapter, "get_current_throttle_kbps")

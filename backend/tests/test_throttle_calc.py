"""
Throttle-Berechnungs Tests.

Sichert die Kern-Logik der Ratelimit-Berechnung ab – getrennt von sqlite
und yt-dlp. Regression-Test fuer:
- realtime=False + 0 KB/s → off (keine Division durch 0 etc.)
- realtime=True ohne Metadaten → fallback oder off, nicht crash
- filesize-Fallback via tbr funktioniert
- Minimum 32 KB/s wird respektiert
"""
import pytest

from app.services.throttle_calc import compute, ThrottleDecision


# ─────────────────────── OFF-Fälle ───────────────────────

def test_off_when_fixed_zero_and_no_realtime():
    r = compute(realtime=False, fixed_kbps=0, duration_s=None, filesize_bytes=None)
    assert r.active is False
    assert r.bytes_per_sec == 0
    assert r.reason == "off"


def test_off_when_fixed_negative():
    r = compute(realtime=False, fixed_kbps=-100, duration_s=None, filesize_bytes=None)
    assert r.active is False


# ─────────────────────── Fixed-Mode ───────────────────────

def test_fixed_300_kbps():
    r = compute(realtime=False, fixed_kbps=300, duration_s=None, filesize_bytes=None)
    assert r.bytes_per_sec == 300 * 1024
    assert r.kbps == 300
    assert r.reason == "fixed"
    assert r.active is True


def test_fixed_ignores_video_metadata():
    """Bei realtime=False spielen duration/filesize keine Rolle."""
    r = compute(realtime=False, fixed_kbps=500, duration_s=600, filesize_bytes=50_000_000)
    assert r.kbps == 500
    assert r.reason == "fixed"


# ─────────────────────── Realtime-Mode ───────────────────────

def test_realtime_basic():
    """100 MB / 600s = 166.67 KB/s × 1.2 = 200 KB/s."""
    r = compute(
        realtime=True,
        fixed_kbps=0,
        duration_s=600,
        filesize_bytes=100 * 1024 * 1024,
    )
    assert r.active is True
    assert r.reason == "realtime"
    # 100MB / 600s * 1.2 ≈ 209715 bytes/s
    assert 200_000 <= r.bytes_per_sec <= 220_000


def test_realtime_respects_minimum():
    """Sehr kurzes Video / kleine Datei → muss ≥ 32 KB/s sein."""
    # 10s Video, 100 KB → 10 KB/s × 1.2 = 12 KB/s → hoch auf 32 KB/s
    r = compute(
        realtime=True,
        fixed_kbps=0,
        duration_s=10,
        filesize_bytes=100 * 1024,
    )
    assert r.bytes_per_sec == 32 * 1024
    assert r.reason == "realtime"


def test_realtime_overhead_is_120_percent():
    """1 MB / 1s = 1 MB/s → × 1.2 = 1.2 MB/s."""
    r = compute(
        realtime=True,
        fixed_kbps=0,
        duration_s=1,
        filesize_bytes=1024 * 1024,
    )
    expected = int(1024 * 1024 * 1.2)
    assert r.bytes_per_sec == expected


# ─────────────────────── Realtime-Fallbacks ───────────────────────

def test_realtime_falls_back_on_tbr_when_filesize_missing():
    """Wenn filesize fehlt aber tbr + duration gegeben → Berechnung über tbr."""
    # tbr = 1000 kbit/s = 125 KB/s, Video 60s = 7.5 MB
    r = compute(
        realtime=True,
        fixed_kbps=0,
        duration_s=60,
        filesize_bytes=0,
        tbr_kbps=1000,
    )
    assert r.active is True
    assert r.reason == "realtime"
    # 7.5 MB / 60s * 1.2 = 150 KB/s
    assert 140_000 <= r.bytes_per_sec <= 160_000


def test_realtime_no_metadata_uses_fixed_fallback():
    """Realtime aktiviert aber keine duration+filesize → fallback auf fixed_kbps."""
    r = compute(
        realtime=True,
        fixed_kbps=800,
        duration_s=None,
        filesize_bytes=None,
    )
    assert r.kbps == 800
    assert r.reason == "fixed_fallback"


def test_realtime_no_metadata_no_fixed_is_off():
    """Realtime ohne Metadaten ohne fixed-fallback → off, aber kein Crash."""
    r = compute(
        realtime=True,
        fixed_kbps=0,
        duration_s=None,
        filesize_bytes=None,
    )
    assert r.active is False
    assert r.reason == "realtime_no_metadata"


# ─────────────────────── Input-Robustheit ───────────────────────

@pytest.mark.parametrize("value", [None, "", "abc", [], {}])
def test_safe_handling_of_weird_types(value):
    """yt-dlp liefert gelegentlich None oder Strings für duration → kein Crash."""
    r = compute(realtime=True, fixed_kbps=0, duration_s=value, filesize_bytes=value)
    # Soll entweder off oder fixed_fallback sein, nie crashen
    assert r.reason in ("realtime_no_metadata", "off", "fixed_fallback")


def test_string_duration_is_parsed():
    """yt-dlp kann duration als String liefern → muss geparst werden."""
    r = compute(
        realtime=True,
        fixed_kbps=0,
        duration_s="60",            # String!
        filesize_bytes="10485760",  # String!
    )
    # 10 MB / 60s * 1.2 ≈ 209715 bytes/s
    assert r.active is True
    assert 200_000 <= r.bytes_per_sec <= 220_000


# ─────────────────────── Property-Tests ───────────────────────

def test_kbps_property_matches_bytes_per_sec():
    r = ThrottleDecision(bytes_per_sec=512 * 1024)
    assert r.kbps == 512


def test_active_property():
    assert ThrottleDecision(bytes_per_sec=0).active is False
    assert ThrottleDecision(bytes_per_sec=1).active is True
